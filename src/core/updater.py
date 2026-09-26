"""自动更新

流程：读 manifest → 比版本 → 多源 Range 测速择优 → 断点续传下载 → SHA256 校验 →
从压缩包解出主体 → 换身重启。

网络全走标准库（urllib），与打包产物保持一致的依赖面。国内直连 GitHub 不稳，
所以测速择优是主路径而非装饰；镜像前缀列表可由用户在设置里覆盖。
"""
import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from loguru import logger

REPO = 'zisull/CardRead2'
MANIFEST_URL = f'https://github.com/{REPO}/releases/latest/download/latest.json'
RELEASE_PAGE_URL = f'https://github.com/{REPO}/releases/latest'

# 空串代表直连 GitHub；其余为反代前缀（拼在完整 github.com URL 前面）
DEFAULT_MIRROR_PREFIXES = ['', 'https://ghproxy.net/', 'https://ghfast.top/', 'https://gh-proxy.com/']

_PROBE_BYTES = 8192          # 测速只取 8KB，够区分数量级又不心疼流量
_PROBE_TIMEOUT = 6.0
_CHUNK = 64 * 1024
_DOWNLOAD_TIMEOUT = 20.0


# ── 纯逻辑（可单测，不碰网络） ──

def parse_version(text: str) -> tuple:
    """'v0.0.4' / '0.0.4-beta1' → (0, 0, 4)；解析失败返回 ()"""
    m = re.search(r'(\d+)(?:\.(\d+))?(?:\.(\d+))?', text or '')
    if not m:
        return ()
    return tuple(int(x) for x in m.groups() if x is not None)


def is_newer(remote: str, local: str) -> bool:
    """远端版本严格高于本地才算有更新（拒绝降级推送）"""
    r, l = parse_version(remote), parse_version(local)
    return bool(r) and r > l


def platform_key(system: Optional[str] = None, machine: Optional[str] = None) -> str:
    system = (system or sys.platform).lower()
    machine = (machine or platform.machine() or '').lower()
    if system.startswith('win'):
        return 'windows-x64'
    if system == 'darwin':
        return 'macos-arm64' if machine in ('arm64', 'aarch64') else 'macos-x64'
    return 'linux-arm64' if machine in ('arm64', 'aarch64') else 'linux-x64'


def pick_asset(manifest: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    assets = manifest.get('assets') or {}
    asset = assets.get(key)
    if asset and asset.get('url'):
        return asset
    return None


def with_prefix(url: str, prefix: str) -> str:
    return url if not prefix else prefix.rstrip('/') + '/' + url


def rank_sources(url: str, prefixes: List[str],
                 probe: Callable[[str], Optional[Dict[str, Any]]] = None,
                 timeout: float = _PROBE_TIMEOUT) -> List[Dict[str, Any]]:
    """并发探测各源，按实测吞吐降序返回成功的（失败的剔除）

    只接受「206 + 恰好 _PROBE_BYTES 字节」的源：不支持 Range 的反代会返回 200
    整包（实测 ghproxy.cn 如此），那种源没法断点续传，宁可不用。
    """
    probe = probe or _probe_source
    results: List[Dict[str, Any]] = []
    lock = threading.Lock()

    def run(prefix: str):
        full = with_prefix(url, prefix)
        info = probe(full)
        if not info:
            return
        info = dict(info)
        info['prefix'] = prefix
        info['label'] = 'GitHub 直连' if not prefix else prefix.split('//')[-1].rstrip('/')
        with lock:
            results.append(info)

    threads = [threading.Thread(target=run, args=(p,), daemon=True) for p in prefixes]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout + 2)
    results.sort(key=lambda r: r.get('speed', 0), reverse=True)
    return results


def range_header(start: int) -> str:
    return f'bytes={start}-'


def plan_resume(part_path: str) -> int:
    """已落地的字节数即续传起点；分片不存在则从 0 开始"""
    try:
        return max(0, os.path.getsize(part_path))
    except OSError:
        return 0


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(_CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def extract_payload(archive_path: str, dest_dir: str) -> str:
    """从 zip/tar.gz 里取回程序本体（体积最大的那个常规文件），返回其路径

    产物是「一个可执行文件压成包」，最大文件必然是本体，无需按扩展名猜。
    """
    os.makedirs(dest_dir, exist_ok=True)
    for existing in os.listdir(dest_dir):
        p = os.path.join(dest_dir, existing)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as zf:
            members = [i for i in zf.infolist() if not i.is_dir() and i.file_size > 0]
            if not members:
                raise ValueError('压缩包内没有可用文件')
            best = max(members, key=lambda i: i.file_size)
            target = os.path.join(dest_dir, os.path.basename(best.filename))
            with zf.open(best) as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst, _CHUNK)
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, 'r:*') as tf:   # r:* 自动识别 gz/xz/bz2
            members = [m for m in tf.getmembers() if m.isfile() and m.size > 0]
            if not members:
                raise ValueError('压缩包内没有可用文件')
            best = max(members, key=lambda m: m.size)
            target = os.path.join(dest_dir, os.path.basename(best.name))
            src = tf.extractfile(best)
            if src is None:
                raise ValueError(f'压缩包内条目无法读取: {best.name}')
            with src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst, _CHUNK)
    else:
        raise ValueError(f'无法识别的压缩包格式: {archive_path}')

    if os.name != 'nt':
        os.chmod(target, os.stat(target).st_mode | 0o755)
    return target


def build_install_plan(current_exe: str, staged: str, platform_name: Optional[str] = None) -> Dict[str, Any]:
    """算出换身步骤；macOS 的 .app 是目录，首版不做原地替换，只给下载页"""
    platform_name = platform_name or platform_key()
    if platform_name.startswith('macos'):
        return {'mode': 'manual', 'reason': 'macOS 产物为 .app 目录，请手动替换', 'url': RELEASE_PAGE_URL}
    return {
        'mode': 'swap',
        'backup': current_exe + '.old',
        'target': current_exe,
        'staged': staged,
        'relaunch': current_exe,
    }


# ── 网络 ──

def _opener():
    # build_opener() 默认带 ProxyHandler，会读系统/环境变量代理
    return build_opener()


def _http_get(url: str, timeout: float = _PROBE_TIMEOUT, headers: Optional[dict] = None,
              size_limit: int = 0):
    req = Request(url, headers={'User-Agent': 'CardRead2-updater', **(headers or {})})
    resp = _opener().open(req, timeout=timeout)
    try:
        body = resp.read(size_limit) if size_limit else resp.read()
        return resp.status, body, dict(resp.headers)
    finally:
        resp.close()


def _probe_source(url: str, timeout: float = _PROBE_TIMEOUT, nbytes: int = _PROBE_BYTES) -> Optional[Dict[str, Any]]:
    """取前 nbytes 字节测吞吐；返回 None 表示该源不可用"""
    start = time.monotonic()
    try:
        status, body, _ = _http_get(url, timeout=timeout, headers={'Range': f'bytes=0-{nbytes - 1}'})
    except (HTTPError, URLError, OSError, ValueError) as e:
        logger.debug(f"更新测速失败 {url}: {type(e).__name__}: {e}")
        return None
    elapsed = max(time.monotonic() - start, 1e-6)
    if status != 206 or len(body) != nbytes:
        logger.debug(f"更新源不支持 Range，弃用: {url} (status={status}, got={len(body)})")
        return None
    return {'bytes': len(body), 'seconds': elapsed, 'speed': len(body) / elapsed,
            'first_byte': elapsed}


# fetch_manifest 的取回结果分类：三种失败要分开告诉用户，「没发布」和「连不上」的处置完全不同
OK = ''
NOT_FOUND = 'not_found'
NETWORK = 'network'
BAD_MANIFEST = 'bad_manifest'


def fetch_manifest(prefixes: List[str]) -> Tuple[Optional[Dict[str, Any]], str]:
    """按给定顺序尝试取 manifest（几十 KB，不做测速，命中即止）

    返回 (manifest, 失败原因)，原因见 NOT_FOUND / NETWORK / BAD_MANIFEST，成功时为 OK。
    「源可达但清单没发布」和「根本连不上」要分开报，否则用户看到的全是"无法连接"。
    """
    reasons: List[str] = []
    for prefix in prefixes:
        url = with_prefix(MANIFEST_URL, prefix)
        try:
            status, body, _ = _http_get(url, timeout=_PROBE_TIMEOUT, size_limit=512 * 1024)
        except HTTPError as e:
            code = getattr(e, 'code', 0)
            reasons.append(NOT_FOUND if code == 404 else NETWORK)
            logger.debug(f"manifest 拉取失败 {url}: HTTP {code}")
            continue
        except (URLError, OSError, ValueError) as e:
            reasons.append(NETWORK)
            logger.debug(f"manifest 拉取失败 {url}: {type(e).__name__}: {e}")
            continue
        if status == 404:
            reasons.append(NOT_FOUND)
            continue
        if status != 200:
            reasons.append(NETWORK)
            continue
        try:
            data = json.loads(body.decode('utf-8', 'replace'))
        except json.JSONDecodeError as e:
            logger.warning(f"manifest 解析失败 {url}: {e}")
            reasons.append(BAD_MANIFEST)
            continue
        if isinstance(data, dict) and data.get('version'):
            data['_source'] = prefix or 'direct'
            return data, OK
        reasons.append(BAD_MANIFEST)
    # 只要有一个源明确回了 404，就说明链路是通的、清单确实没发布，这比"连不上"更有指导性
    for pref in (NOT_FOUND, BAD_MANIFEST):
        if pref in reasons:
            return None, pref
    return None, NETWORK


# ── 状态机 ──

IDLE = 'idle'
CHECKING = 'checking'
AVAILABLE = 'available'
UP_TO_DATE = 'up_to_date'
BENCHMARKING = 'benchmarking'
DOWNLOADING = 'downloading'
VERIFYING = 'verifying'
READY = 'ready'
INSTALLING = 'installing'
FAILED = 'failed'
# 检查没跑成（区别于下载失败）：不弹徽标打扰，只在用户点开面板时说明原因
CHECK_FAILED = 'check_failed'

CHECK_ERRORS = {
    NOT_FOUND: '更新清单尚未发布：GitHub Releases 里还没有 latest.json',
    BAD_MANIFEST: '更新清单内容异常，无法解析',
    NETWORK: '无法连接更新源，请检查网络或代理后重试',
}


class Updater:
    """一次一个下载任务；状态给前端轮询

    Args:
        work_dir: 存放分片与解包产物的目录（appdata/update）
        current_version: 本地版本号
        current_exe: 本体路径（开发模式下传 python 路径，install 会拒绝执行）
        prefixes: 镜像前缀列表，可由用户覆盖
    """

    def __init__(self, work_dir: str, current_version: str, current_exe: str,
                 prefixes: Optional[List[str]] = None, frozen: Optional[bool] = None):
        self._work_dir = work_dir
        self._current_version = current_version
        self._current_exe = current_exe
        self._prefixes = list(prefixes or DEFAULT_MIRROR_PREFIXES)
        self._frozen = _is_frozen() if frozen is None else bool(frozen)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._cancel = threading.Event()
        self._manifest: Optional[Dict[str, Any]] = None
        self._plan: Optional[Dict[str, Any]] = None
        self._st = {
            'phase': IDLE,
            'local_version': current_version,
            'remote_version': '',
            'notes': '',
            'published_at': '',
            'checked_at': 0.0,
            'available': False,
            'progress': 0.0,
            'downloaded': 0,
            'total': 0,
            'speed': 0.0,
            'eta': 0.0,
            'source': '',
            'sources': [],
            'error': '',
            'installable': False,
        }

    # ── 状态读写 ──

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._st)

    def _patch(self, **kw):
        with self._lock:
            self._st.update(kw)

    @property
    def prefixes(self) -> List[str]:
        return list(self._prefixes)

    def set_prefixes(self, prefixes: List[str]) -> None:
        self._prefixes = [p for p in (prefixes or []) if p is not None] or list(DEFAULT_MIRROR_PREFIXES)

    # ── 检测 ──

    def check_async(self) -> Dict[str, Any]:
        """点版本号用的非阻塞检查：立刻返回 CHECKING，结果由前端轮询 status() 取

        下载进行中不重复发起，否则两个线程会同时改写同一份状态。
        """
        with self._lock:
            if self._st['phase'] in (CHECKING, BENCHMARKING, DOWNLOADING, VERIFYING, INSTALLING):
                return dict(self._st)
            self._st['phase'] = CHECKING
            self._st['error'] = ''
        threading.Thread(target=self.check, daemon=True, name='cardread-update-check').start()
        return self.status()

    def check(self) -> Dict[str, Any]:
        """静默检查：任何失败都不抛，只记日志和状态"""
        self._patch(phase=CHECKING, error='')
        manifest, reason = fetch_manifest(self._prefixes)
        if not manifest:
            logger.info(f"更新检查未成功: {reason}")
            self._patch(phase=CHECK_FAILED, error=CHECK_ERRORS.get(reason, CHECK_ERRORS[NETWORK]),
                        checked_at=time.time(), remote_version='', available=False)
            return self.status()
        if manifest.get('enabled') is False:
            logger.info('更新源已禁用（manifest.enabled=false）')
            self._patch(phase=IDLE)
            return self.status()
        remote = str(manifest.get('version'))
        self._manifest = manifest
        newer = is_newer(remote, self._current_version)
        self._patch(
            phase=AVAILABLE if newer else UP_TO_DATE,
            remote_version=remote,
            notes=str(manifest.get('notes') or '')[:4000],
            published_at=str(manifest.get('published_at') or ''),
            checked_at=time.time(),
            available=newer,
            error='',
        )
        logger.info(f"更新检查完成: 本地 {self._current_version} / 远端 {remote} → {'有新版' if newer else '已最新'}")
        return self.status()

    # ── 测速 + 下载 ──

    def start_download(self) -> Dict[str, Any]:
        if not self._manifest:
            # 检查就没成时别报「请先检查更新」——用户刚点过检查，要给他真实原因
            reason = self._st.get('error') if self._st.get('phase') == CHECK_FAILED else ''
            self._patch(phase=FAILED, error=reason or '尚未获取到更新信息，请先检查更新')
            return self.status()
        with self._lock:
            if self._st['phase'] in (DOWNLOADING, VERIFYING, BENCHMARKING, INSTALLING):
                return self.status()
        asset = pick_asset(self._manifest, platform_key())
        if not asset:
            self._patch(phase=FAILED, error=f'更新包里没有适配当前平台的产物（{platform_key()}）')
            return self.status()

        self._cancel.clear()
        self._patch(phase=BENCHMARKING, error='', sources=[], source='',
                    total=int(asset.get('size') or 0), downloaded=0, progress=0.0, installable=False)
        self._thread = threading.Thread(target=self._run, args=(asset,), daemon=True,
                                        name='cardread-update')
        self._thread.start()
        return self.status()

    def _run(self, asset: Dict[str, Any]):
        url = asset['url']
        try:
            sources = rank_sources(url, self._prefixes)
            self._patch(phase=DOWNLOADING if sources else FAILED,
                        sources=[{'label': s['label'], 'speed': round(s['speed'], 1)} for s in sources],
                        error='' if sources else '所有更新源都不可用')
            if not sources:
                return
            os.makedirs(self._work_dir, exist_ok=True)
            name = os.path.basename(url.split('?')[0]) or 'update.bin'
            part = os.path.join(self._work_dir, name + '.part')
            final = os.path.join(self._work_dir, name)
            for idx, src in enumerate(sources):
                if self._cancel.is_set():
                    self._patch(phase=IDLE, error='已取消')
                    return
                self._patch(source=src['label'])
                try:
                    got = _download_resume(with_prefix(url, src['prefix']), part, self._on_progress,
                                           expect_size=int(asset.get('size') or 0),
                                           cancel=self._cancel)
                except _Cancelled:
                    self._patch(phase=IDLE, error='已取消')
                    return
                except (HTTPError, URLError, OSError, ValueError) as e:
                    logger.warning(f"源 {src['label']} 下载中断: {type(e).__name__}: {e}")
                    self._patch(error=f'{src["label"]} 中断，切换下一个源')
                    continue
                logger.info(f"更新包下载完成: {name} ({got} 字节) 来自 {src['label']}")
                break
            else:
                self._patch(phase=FAILED, error='所有可用源都没下完')
                return

            self._patch(phase=VERIFYING, progress=1.0)
            digest = asset.get('sha256')
            if digest:
                actual = sha256_of(part)
                if actual.lower() != str(digest).lower():
                    os.remove(part)
                    self._patch(phase=FAILED, error='校验失败（SHA256 不匹配），已丢弃下载内容')
                    return
            else:
                logger.warning('manifest 未提供 sha256，仅按字节数校验')
            expected = int(asset.get('size') or 0)
            if expected and os.path.getsize(part) != expected:
                os.remove(part)
                self._patch(phase=FAILED, error='校验失败（体积不符），已丢弃下载内容')
                return

            staged_dir = os.path.join(self._work_dir, 'staged')
            staged = extract_payload(part, staged_dir)
            os.replace(part, final)
            plan = build_install_plan(self._current_exe, staged)
            with self._lock:
                self._plan = plan
            self._patch(phase=READY, installable=plan['mode'] == 'swap', progress=1.0, error='')
            logger.info(f"更新包就绪: {staged}")
        except Exception as e:
            logger.exception(f"更新流程异常: {e}")
            self._patch(phase=FAILED, error=f'{type(e).__name__}: {e}')

    def _on_progress(self, downloaded: int, total: int, speed: float):
        self._patch(downloaded=downloaded, total=total or self._st['total'],
                    speed=round(speed, 1),
                    progress=round(min(1.0, downloaded / total), 4) if total else 0.0,
                    eta=round((total - downloaded) / speed, 1) if total and speed > 0 else 0.0)

    def cancel(self) -> Dict[str, Any]:
        self._cancel.set()
        with self._lock:
            if self._st['phase'] in (BENCHMARKING, DOWNLOADING):
                self._st['phase'] = IDLE
                self._st['error'] = '已取消'
        return self.status()

    # ── 换身 ──

    def apply(self) -> Dict[str, Any]:
        with self._lock:
            if self._st['phase'] != READY:
                return {'success': False, 'error': '尚未下载完成'}
            plan = dict(self._plan or {})
        if plan.get('mode') != 'swap':
            return {'success': False, 'manual': True, 'url': plan.get('url') or RELEASE_PAGE_URL,
                    'error': plan.get('reason') or '当前平台不支持自动替换'}
        if not self._frozen:
            return {'success': False, 'error': '开发模式下不替换自身（请用打包后的程序更新）'}
        return self._swap_and_relaunch(plan)

    def _swap_and_relaunch(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        target, backup, staged = plan['target'], plan['backup'], plan['staged']
        try:
            # Windows 允许改名正在运行的 exe，但不允许覆盖 —— 先让位再落新件
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(target, backup)
        except OSError as e:
            self._patch(phase=FAILED, error=f'备份旧版本失败: {e}')
            return {'success': False, 'error': str(e)}
        try:
            shutil.copyfile(staged, target)
            if os.name != 'nt':
                os.chmod(target, 0o755)
        except OSError as e:
            with contextlib.suppress(OSError):
                os.rename(backup, target)   # 回滚，绝不让程序「消失」
            self._patch(phase=FAILED, error=f'写入新版本失败: {e}')
            return {'success': False, 'error': str(e)}

        self._patch(phase=INSTALLING)
        try:
            flags = 0x00000008 if os.name == 'nt' else 0   # DETACHED_PROCESS
            subprocess.Popen([plan['relaunch']], cwd=os.path.dirname(target) or None,
                             creationflags=flags, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as e:
            os.remove(target)
            os.rename(backup, target)
            self._patch(phase=FAILED, error=f'启动新版本失败，已回滚: {e}')
            return {'success': False, 'error': str(e)}

        logger.info('新版本已启动，当前进程退出')
        return {'success': True, 'backup': backup}

    @staticmethod
    def cleanup_backup(exe_path: str) -> None:
        """新版本启动后清掉上一次留下的 .old（旧进程此刻已退出）"""
        backup = exe_path + '.old'
        for _ in range(10):
            if not os.path.exists(backup):
                return
            try:
                os.remove(backup)
                logger.info('已清理旧版本备份')
                return
            except OSError:
                time.sleep(0.5)


class _Cancelled(Exception):
    pass


def _download_resume(url: str, part_path: str,
                     on_progress: Optional[Callable[[int, int, float], None]] = None,
                     expect_size: int = 0, cancel: Optional[threading.Event] = None,
                     timeout: float = _DOWNLOAD_TIMEOUT) -> int:
    """带续传的下载；返回落地的总字节数

    起点由 .part 现有大小决定；源不支持 Range 时（返回 200）从头重写。
    """
    offset = plan_resume(part_path)
    if expect_size and offset >= expect_size:
        # 上次已经下全了，只是没来得及校验：再发请求只会拿到 416
        return offset
    report = on_progress or (lambda *_: None)
    req = Request(url, headers={'User-Agent': 'CardRead2-updater', 'Range': range_header(offset)})
    resp = _opener().open(req, timeout=timeout)
    try:
        status = resp.status
        if status == 206:
            start = _range_start(resp.headers.get('Content-Range'), offset)
            if start != offset:
                raise ValueError(f'续传起点不符: 期望 {offset} 实际 {start}')
            mode = 'ab'
        else:
            offset = 0
            mode = 'wb'
        total = expect_size
        header_total = _content_total(resp.headers.get('Content-Range'))
        if header_total:
            total = header_total
        elif status == 200:
            try:
                total = int(resp.headers.get('Content-Length') or 0)
            except ValueError:
                total = expect_size

        downloaded = offset
        last_tick = time.monotonic()
        last_bytes = offset
        with open(part_path, mode) as f:
            while True:
                if cancel is not None and cancel.is_set():
                    raise _Cancelled()
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_tick >= 0.4:
                    speed = (downloaded - last_bytes) / max(now - last_tick, 1e-6)
                    report(downloaded, total, speed)
                    last_tick, last_bytes = now, downloaded
        report(downloaded, total, 0.0)
        if total and downloaded != total:
            raise ValueError(f'下载不完整: {downloaded}/{total}')
        return downloaded
    finally:
        resp.close()


def _range_start(content_range: Optional[str], fallback: int) -> int:
    m = re.match(r'\s*bytes\s+(\d+)-', content_range or '')
    return int(m.group(1)) if m else fallback


def _content_total(content_range: Optional[str]) -> int:
    m = re.match(r'\s*bytes\s+\d+-\d+/(\d+)', content_range or '')
    return int(m.group(1)) if m else 0


def _is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False)) or '__compiled__' in globals()
