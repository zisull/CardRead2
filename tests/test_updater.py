"""自动更新模块测试

纯逻辑（版本比较、平台产物挑选、续传数学、校验、换身计划）离线可测；
下载相关用本机 http.server 起一个支持 Range 的假源，不碰真实网络。
"""
import hashlib
import io
import json
import os
import tarfile
import urllib.request
import zipfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.core import updater


PAYLOAD = bytes(range(256)) * 400   # 102400 字节，够测速探针取满 8KB


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _write_zip(path, files):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in files:
            zf.writestr(name, data)


def _write_targz(path, files):
    with tarfile.open(path, 'w:gz') as tf:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


class _FakeServer:
    """支持 Range 的临时 HTTP 源；support_range=False 时模拟无视 Range 的反代"""

    def __init__(self, content, support_range=True, truncate_at=None):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.requests.append(self.headers.get('Range'))
                rng = self.headers.get('Range')
                if outer.support_range and rng and rng.startswith('bytes='):
                    spec = rng[len('bytes='):]
                    start_s, _, end_s = spec.partition('-')
                    start = int(start_s or 0)
                    end = int(end_s) if end_s else len(outer.content) - 1
                    chunk = outer.content[start:end + 1]
                    self.send_response(206)
                    self.send_header('Content-Length', str(len(chunk)))
                    self.send_header('Content-Range',
                                     f'bytes {start}-{start + len(chunk) - 1}/{len(outer.content)}')
                    self.end_headers()
                    # 半路掐断：声明的字节数比真发的多，用来验证「下载不完整」的判定
                    self.wfile.write(chunk if outer.truncate_at is None
                                     else chunk[:outer.truncate_at])
                    return
                self.send_response(200)
                self.send_header('Content-Length', str(len(outer.content)))
                self.end_headers()
                self.wfile.write(outer.content)

        self.content = content
        self.support_range = support_range
        self.truncate_at = truncate_at
        self.requests = []
        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self._server.server_address[1]}/CardRead2.zip'

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def no_proxy(monkeypatch):
    """测速/下载走 build_opener()，会读系统代理；测试环境里必须直连本机端口"""
    monkeypatch.setattr(updater, '_opener',
                        lambda: urllib.request.build_opener(urllib.request.ProxyHandler({})))


@pytest.fixture
def work_dir(tmp_path):
    d = tmp_path / 'update'
    d.mkdir()
    return str(d)


class TestVersionCompare:
    def test_parse_version(self):
        assert updater.parse_version('v0.0.4') == (0, 0, 4)
        assert updater.parse_version('0.10.2-beta1') == (0, 10, 2)
        assert updater.parse_version('1.2') == (1, 2)
        assert updater.parse_version('weird') == ()
        assert updater.parse_version('') == ()
        assert updater.parse_version(None) == ()

    def test_is_newer_strictly_greater(self):
        assert updater.is_newer('0.0.5', '0.0.4') is True
        assert updater.is_newer('0.0.4', '0.0.4') is False
        assert updater.is_newer('0.0.3', '0.0.4') is False   # 拒绝降级推送
        assert updater.is_newer('0.10.0', '0.9.9') is True

    def test_is_newer_ignores_unparsable(self):
        assert updater.is_newer('', '0.0.4') is False
        assert updater.is_newer('0.0.5', 'unknown') is True


class TestPlatformAndAsset:
    def test_platform_key(self):
        assert updater.platform_key('win32', 'AMD64') == 'windows-x64'
        assert updater.platform_key('darwin', 'arm64') == 'macos-arm64'
        assert updater.platform_key('darwin', 'x86_64') == 'macos-x64'
        assert updater.platform_key('linux', 'aarch64') == 'linux-arm64'
        assert updater.platform_key('linux', 'x86_64') == 'linux-x64'

    def test_pick_asset(self):
        manifest = {'assets': {'windows-x64': {'url': 'u', 'sha256': 's'}, 'linux-x64': {}}}
        assert updater.pick_asset(manifest, 'windows-x64')['url'] == 'u'
        assert updater.pick_asset(manifest, 'linux-x64') is None
        assert updater.pick_asset(manifest, 'macos-x64') is None
        assert updater.pick_asset({}, 'windows-x64') is None

    def test_with_prefix(self):
        assert updater.with_prefix('https://a/b', '') == 'https://a/b'
        assert updater.with_prefix('https://a/b', 'https://gh/') == 'https://gh/https://a/b'
        assert updater.with_prefix('https://a/b', 'https://gh') == 'https://gh/https://a/b'


class TestSourceRanking:
    def test_rank_sources_sorts_by_speed_and_drops_failures(self):
        seen = []

        def probe(url):
            seen.append(url)
            if 'dead-proxy' in url:
                return None
            if 'fast-proxy' in url:
                return {'speed': 900.0, 'bytes': 8192}
            return {'speed': 10.0, 'bytes': 8192}

        ranked = updater.rank_sources('https://gh/x.bin',
                                     ['', 'https://fast-proxy.top/', 'https://dead-proxy.cn/'],
                                     probe=probe)
        assert [r['label'] for r in ranked] == ['fast-proxy.top', 'GitHub 直连']
        assert ranked[0]['speed'] == 900.0
        assert len(seen) == 3

    def test_rank_sources_all_dead(self):
        assert updater.rank_sources('https://gh/x', ['', 'https://a/'], probe=lambda u: None) == []

    def test_probe_rejects_non_206(self, monkeypatch):
        # 实测 ghproxy.cn 会返回 200 整包：那种源无法续传，必须弃用
        monkeypatch.setattr(updater, '_http_get',
                            lambda url, timeout=6.0, headers=None, size_limit=0: (200, b'x' * 8192, {}))
        assert updater._probe_source('https://gh/x') is None

    def test_probe_rejects_short_body(self, monkeypatch):
        monkeypatch.setattr(updater, '_http_get',
                            lambda url, timeout=6.0, headers=None, size_limit=0: (206, b'x' * 10, {}))
        assert updater._probe_source('https://gh/x') is None

    def test_probe_accepts_exact_206(self, monkeypatch):
        monkeypatch.setattr(updater, '_http_get',
                            lambda url, timeout=6.0, headers=None, size_limit=0:
                            (206, b'x' * updater._PROBE_BYTES, {}))
        info = updater._probe_source('https://gh/x')
        assert info['bytes'] == updater._PROBE_BYTES
        assert info['speed'] > 0

    def test_probe_swallows_exceptions(self, monkeypatch):
        def boom(*a, **kw):
            raise OSError('connection reset')
        monkeypatch.setattr(updater, '_http_get', boom)
        assert updater._probe_source('https://gh/x') is None


class TestResumeMath:
    def test_plan_resume_missing_file(self, tmp_path):
        assert updater.plan_resume(str(tmp_path / 'none.part')) == 0

    def test_plan_existing_part(self, tmp_path):
        p = tmp_path / 'a.part'
        p.write_bytes(b'12345')
        assert updater.plan_resume(str(p)) == 5

    def test_range_parsing(self):
        assert updater.range_header(1024) == 'bytes=1024-'
        assert updater._range_start('bytes 1024-2047/5000', 0) == 1024
        assert updater._range_start(None, 77) == 77
        assert updater._content_total('bytes 0-99/5000') == 5000
        assert updater._content_total('bytes 0-99/*') == 0
        assert updater._content_total(None) == 0

    def test_sha256_of(self, tmp_path):
        p = tmp_path / 'f.bin'
        p.write_bytes(PAYLOAD)
        assert updater.sha256_of(str(p)) == _sha256(PAYLOAD)


class TestExtractPayload:
    def test_zip_picks_largest_member(self, tmp_path):
        archive = str(tmp_path / 'a.zip')
        _write_zip(archive, [('readme.txt', b'note'), ('CardRead2.exe', PAYLOAD),
                             ('nested/dir/empty.txt', b'')])
        out = updater.extract_payload(archive, str(tmp_path / 'out'))
        assert os.path.basename(out) == 'CardRead2.exe'
        assert open(out, 'rb').read() == PAYLOAD

    def test_zip_clears_previous_run(self, tmp_path):
        archive = str(tmp_path / 'a.zip')
        _write_zip(archive, [('CardRead2.exe', PAYLOAD)])
        dest = tmp_path / 'out'
        dest.mkdir()
        (dest / 'stale.txt').write_text('x')
        updater.extract_payload(archive, str(dest))
        assert sorted(os.listdir(str(dest))) == ['CardRead2.exe']

    def test_targz_picks_largest_member(self, tmp_path):
        archive = str(tmp_path / 'a.tar.gz')
        _write_targz(archive, [('small.txt', b'hi'), ('cardread2', PAYLOAD)])
        out = updater.extract_payload(archive, str(tmp_path / 'out'))
        assert os.path.basename(out) == 'cardread2'
        assert open(out, 'rb').read() == PAYLOAD
        if os.name != 'nt':
            assert os.stat(out).st_mode & 0o111

    def test_empty_archive_rejected(self, tmp_path):
        archive = str(tmp_path / 'a.zip')
        _write_zip(archive, [])
        with pytest.raises(ValueError):
            updater.extract_payload(archive, str(tmp_path / 'out'))

    def test_unknown_format_rejected(self, tmp_path):
        raw = tmp_path / 'a.bin'
        raw.write_bytes(b'not an archive')
        with pytest.raises(ValueError):
            updater.extract_payload(str(raw), str(tmp_path / 'out'))


class TestInstallPlan:
    def test_windows_swap(self):
        plan = updater.build_install_plan('C:/app/CardRead2.exe', 'C:/tmp/staged/CardRead2.exe',
                                         platform_name='windows-x64')
        assert plan['mode'] == 'swap'
        assert plan['backup'] == 'C:/app/CardRead2.exe.old'
        assert plan['target'] == 'C:/app/CardRead2.exe'
        assert plan['relaunch'] == 'C:/app/CardRead2.exe'

    def test_linux_swap(self):
        plan = updater.build_install_plan('/opt/cardread2', '/tmp/staged/cardread2',
                                         platform_name='linux-x64')
        assert plan['mode'] == 'swap'

    def test_macos_is_manual(self):
        plan = updater.build_install_plan('/Applications/Card.app', '/tmp/staged/Card',
                                         platform_name='macos-arm64')
        assert plan['mode'] == 'manual'
        assert plan['url'] == updater.RELEASE_PAGE_URL


class TestManifest:
    def test_fetch_manifest_first_source_wins(self, monkeypatch):
        calls = []
        body = json.dumps({'version': '0.0.5', 'notes': 'n'}).encode()

        def fake(url, timeout=6.0, headers=None, size_limit=0):
            calls.append(url)
            if url.startswith('https://ghproxy'):
                raise OSError('refused')
            return (200, body, {})

        monkeypatch.setattr(updater, '_http_get', fake)
        data = updater.fetch_manifest(['https://ghproxy.net/', ''])
        assert data['version'] == '0.0.5'
        assert data['_source'] == 'direct'
        assert len(calls) == 2

    def test_fetch_manifest_rejects_bad_json(self, monkeypatch):
        monkeypatch.setattr(updater, '_http_get',
                            lambda url, **kw: (200, b'<html>rate limited</html>', {}))
        assert updater.fetch_manifest(['']) is None

    def test_fetch_manifest_requires_version(self, monkeypatch):
        monkeypatch.setattr(updater, '_http_get',
                            lambda url, **kw: (200, json.dumps({'notes': 'x'}).encode(), {}))
        assert updater.fetch_manifest(['']) is None


class TestDownloadResume:
    def test_fresh_download(self, tmp_path, no_proxy):
        srv = _FakeServer(PAYLOAD)
        try:
            part = str(tmp_path / 'f.part')
            got = updater._download_resume(srv.url, part)
            assert got == len(PAYLOAD)
            assert open(part, 'rb').read() == PAYLOAD
            assert srv.requests == ['bytes=0-']
        finally:
            srv.stop()

    def test_resume_from_existing_part(self, tmp_path, no_proxy):
        srv = _FakeServer(PAYLOAD)
        try:
            part = str(tmp_path / 'f.part')
            with open(part, 'wb') as f:
                f.write(PAYLOAD[:4096])
            got = updater._download_resume(srv.url, part, expect_size=len(PAYLOAD))
            assert got == len(PAYLOAD)
            assert open(part, 'rb').read() == PAYLOAD
            assert srv.requests == ['bytes=4096-']    # 只补后半段
        finally:
            srv.stop()

    def test_already_complete_part_short_circuits(self, tmp_path, no_proxy):
        srv = _FakeServer(PAYLOAD)
        try:
            part = str(tmp_path / 'f.part')
            with open(part, 'wb') as f:
                f.write(PAYLOAD)
            assert updater._download_resume(srv.url, part, expect_size=len(PAYLOAD)) == len(PAYLOAD)
            assert srv.requests == []
        finally:
            srv.stop()

    def test_source_ignoring_range_restarts_from_zero(self, tmp_path, no_proxy):
        srv = _FakeServer(PAYLOAD, support_range=False)
        try:
            part = str(tmp_path / 'f.part')
            with open(part, 'wb') as f:
                f.write(b'garbage prefix that must not survive')
            got = updater._download_resume(srv.url, part)
            assert got == len(PAYLOAD)
            assert open(part, 'rb').read() == PAYLOAD
        finally:
            srv.stop()

    def test_truncated_stream_raises(self, tmp_path, no_proxy):
        # 源声明 102400 字节却只发一半：必须判为不完整，而不是「下完了」
        srv = _FakeServer(PAYLOAD, truncate_at=len(PAYLOAD) // 2)
        try:
            with pytest.raises(ValueError):
                updater._download_resume(srv.url, str(tmp_path / 'f.part'))
        finally:
            srv.stop()

    def test_cancel_stops_before_transfer(self, tmp_path, no_proxy):
        srv = _FakeServer(PAYLOAD)
        try:
            ev = threading.Event()
            ev.set()
            with pytest.raises(updater._Cancelled):
                updater._download_resume(srv.url, str(tmp_path / 'f.part'), cancel=ev)
        finally:
            srv.stop()

    def test_progress_callback_sees_growth(self, tmp_path, no_proxy):
        srv = _FakeServer(PAYLOAD)
        ticks = []
        try:
            updater._download_resume(srv.url, str(tmp_path / 'f.part'),
                                     on_progress=lambda d, t, s: ticks.append((d, t, s)))
            assert ticks[-1][0] == len(PAYLOAD)
            assert ticks[-1][1] == len(PAYLOAD)
        finally:
            srv.stop()


def _manifest_for(url, raw, version='0.0.9'):
    return {
        'version': version,
        'notes': '修复搜索',
        'published_at': '2026-09-26T00:00:00Z',
        'enabled': True,
        'assets': {
            'windows-x64': {'url': url, 'sha256': _sha256(raw), 'size': len(raw)},
            'linux-x64': {'url': url, 'sha256': _sha256(raw), 'size': len(raw)},
            'macos-x64': {'url': url, 'sha256': _sha256(raw), 'size': len(raw)},
            'macos-arm64': {'url': url, 'sha256': _sha256(raw), 'size': len(raw)},
            'linux-arm64': {'url': url, 'sha256': _sha256(raw), 'size': len(raw)},
        },
    }


class TestUpdaterState:
    def _updater(self, work_dir, **kw):
        return updater.Updater(work_dir, '0.0.4', os.path.join(work_dir, 'CardRead2.exe'),
                               prefixes=[''], frozen=False, **kw)

    def test_check_available(self, monkeypatch, work_dir):
        monkeypatch.setattr(updater, 'fetch_manifest',
                            lambda prefixes: _manifest_for('https://x/y.zip', b'z'))
        u = self._updater(work_dir)
        st = u.check()
        assert st['phase'] == updater.AVAILABLE
        assert st['available'] is True
        assert st['remote_version'] == '0.0.9'
        assert st['notes'] == '修复搜索'

    def test_check_up_to_date(self, monkeypatch, work_dir):
        manifest = _manifest_for('https://x/y.zip', b'z', version='0.0.4')
        monkeypatch.setattr(updater, 'fetch_manifest', lambda prefixes: manifest)
        st = self._updater(work_dir).check()
        assert st['phase'] == updater.UP_TO_DATE
        assert st['available'] is False

    def test_check_failure_is_silent(self, monkeypatch, work_dir):
        monkeypatch.setattr(updater, 'fetch_manifest', lambda prefixes: None)
        st = self._updater(work_dir).check()
        assert st['phase'] == updater.IDLE
        assert st['error'] == '无法连接更新源'

    def test_check_disabled_manifest(self, monkeypatch, work_dir):
        manifest = _manifest_for('https://x/y.zip', b'z')
        manifest['enabled'] = False
        monkeypatch.setattr(updater, 'fetch_manifest', lambda prefixes: manifest)
        assert self._updater(work_dir).check()['phase'] == updater.IDLE

    def test_check_async_returns_immediately(self, monkeypatch, work_dir):
        started, release = threading.Event(), threading.Event()
        calls = []

        def fake_fetch(prefixes):
            calls.append(prefixes)
            started.set()
            release.wait(timeout=5)
            return _manifest_for('https://x/y.zip', b'z')

        monkeypatch.setattr(updater, 'fetch_manifest', fake_fetch)
        u = self._updater(work_dir)
        began = time.monotonic()
        st = u.check_async()
        assert st['phase'] == updater.CHECKING
        assert time.monotonic() - began < 1.0     # 点徽标绝不能被网络卡住
        assert started.wait(timeout=5)
        release.set()
        for _ in range(200):
            if u.status()['phase'] != updater.CHECKING:
                break
            time.sleep(0.02)
        assert u.status()['phase'] == updater.AVAILABLE
        assert len(calls) == 1

    def test_check_async_noop_while_downloading(self, monkeypatch, work_dir):
        calls = []
        monkeypatch.setattr(updater, 'fetch_manifest', lambda prefixes: calls.append(1))
        u = self._updater(work_dir)
        u._patch(phase=updater.DOWNLOADING)
        assert u.check_async()['phase'] == updater.DOWNLOADING
        time.sleep(0.2)
        assert calls == []

    def test_download_without_manifest_fails(self, work_dir):
        st = self._updater(work_dir).start_download()
        assert st['phase'] == updater.FAILED

    def test_download_without_platform_asset_fails(self, monkeypatch, work_dir):
        monkeypatch.setattr(updater, 'fetch_manifest',
                            lambda prefixes: {'version': '0.0.9', 'assets': {}})
        monkeypatch.setattr(updater, 'platform_key', lambda *a: 'windows-x64')
        u = self._updater(work_dir)
        u.check()
        st = u.start_download()
        assert st['phase'] == updater.FAILED
        assert 'windows-x64' in st['error']

    def test_apply_requires_ready(self, work_dir):
        assert self._updater(work_dir).apply()['success'] is False

    def test_status_has_no_private_keys(self, work_dir):
        st = self._updater(work_dir).status()
        assert not [k for k in st if k.startswith('_')]

    def test_set_prefixes_falls_back_to_defaults(self, work_dir):
        u = self._updater(work_dir)
        u.set_prefixes([])
        assert u.prefixes == updater.DEFAULT_MIRROR_PREFIXES
        u.set_prefixes([None, 'https://a/'])
        assert u.prefixes == ['https://a/']


class TestUpdaterEndToEnd:
    """假源跑完整链路：测速 → 下载 → 校验 → 解包 → 就绪（绝不真替换正在运行的二进制）"""

    def _run_flow(self, tmp_path, monkeypatch, raw, mutate_manifest=None):
        srv = _FakeServer(raw)
        try:
            manifest = _manifest_for(srv.url, raw)
            if mutate_manifest:
                mutate_manifest(manifest)
            monkeypatch.setattr(updater, 'fetch_manifest', lambda prefixes: manifest)
            monkeypatch.setattr(updater, 'platform_key', lambda *a: 'windows-x64')
            work = str(tmp_path / 'update')
            os.makedirs(work, exist_ok=True)
            u = updater.Updater(work, '0.0.4', os.path.join(work, 'CardRead2.exe'),
                                prefixes=[''], frozen=False)
            u.check()
            u.start_download()
            u._thread.join(timeout=30)
            return u, u.status(), srv
        finally:
            srv.stop()

    def test_ready_and_staged_payload_matches(self, tmp_path, monkeypatch, no_proxy):
        archive = tmp_path / 'pkg.zip'
        _write_zip(str(archive), [('CardRead2.exe', PAYLOAD), ('notes.txt', b'changelog')])
        raw = archive.read_bytes()
        u, st, srv = self._run_flow(tmp_path, monkeypatch, raw)
        assert st['phase'] == updater.READY, st['error']
        assert st['installable'] is True
        assert st['progress'] == 1.0
        assert st['sources'][0]['speed'] > 0
        assert st['source'] == 'GitHub 直连'
        staged = os.path.join(str(tmp_path), 'update', 'staged', 'CardRead2.exe')
        assert open(staged, 'rb').read() == PAYLOAD
        # 换身必须显式拒绝开发模式，绝不在测试里动真实文件
        assert u.apply() == {'success': False, 'error': '开发模式下不替换自身（请用打包后的程序更新）'}
        assert os.path.exists(os.path.join(str(tmp_path), 'update', 'CardRead2.zip'))

    def test_tampered_sha256_discards_download(self, tmp_path, monkeypatch, no_proxy):
        archive = tmp_path / 'pkg.zip'
        _write_zip(str(archive), [('CardRead2.exe', PAYLOAD)])
        raw = archive.read_bytes()

        def mutate(manifest):
            manifest['assets']['windows-x64']['sha256'] = 'dead' * 32

        u, st, srv = self._run_flow(tmp_path, monkeypatch, raw, mutate_manifest=mutate)
        assert st['phase'] == updater.FAILED
        assert 'SHA256' in st['error']
        assert u.apply()['success'] is False
        part_dir = os.path.join(str(tmp_path), 'update')
        assert not [f for f in os.listdir(part_dir) if f.endswith('.part')]

    def test_all_sources_dead_reports_failure(self, tmp_path, monkeypatch, no_proxy):
        manifest = _manifest_for('http://127.0.0.1:1/nope.zip', PAYLOAD)
        monkeypatch.setattr(updater, 'fetch_manifest', lambda prefixes: manifest)
        monkeypatch.setattr(updater, 'platform_key', lambda *a: 'windows-x64')
        work = str(tmp_path / 'update')
        os.makedirs(work, exist_ok=True)
        u = updater.Updater(work, '0.0.4', os.path.join(work, 'CardRead2.exe'),
                            prefixes=[''], frozen=False)
        u.check()
        u.start_download()
        u._thread.join(timeout=30)
        st = u.status()
        assert st['phase'] == updater.FAILED
        assert st['sources'] == []

    def test_cancel_during_download_returns_to_idle(self, tmp_path, monkeypatch):
        manifest = _manifest_for('http://127.0.0.1:1/x.zip', PAYLOAD)
        monkeypatch.setattr(updater, 'fetch_manifest', lambda prefixes: manifest)
        monkeypatch.setattr(updater, 'platform_key', lambda *a: 'windows-x64')
        monkeypatch.setattr(updater, 'rank_sources',
                            lambda url, prefixes, probe=None, timeout=6.0:
                            [{'label': 'GitHub 直连', 'prefix': '', 'speed': 1.0}])

        def blocked_download(url, part, on_progress, expect_size=0, cancel=None, timeout=20.0):
            assert cancel.wait(timeout=10)      # 挂住直到 cancel() 被点
            raise updater._Cancelled()

        monkeypatch.setattr(updater, '_download_resume', blocked_download)
        work = str(tmp_path / 'update')
        os.makedirs(work, exist_ok=True)
        u = updater.Updater(work, '0.0.4', os.path.join(work, 'CardRead2.exe'),
                            prefixes=[''], frozen=False)
        u.check()
        u.start_download()
        for _ in range(200):
            if u.status()['phase'] == updater.DOWNLOADING:
                break
            time.sleep(0.02)
        assert u.cancel()['phase'] == updater.IDLE
        u._thread.join(timeout=10)
        assert u.status()['error'] == '已取消'


class TestCleanupBackup:
    def test_removes_existing_backup(self, tmp_path):
        exe = tmp_path / 'CardRead2.exe'
        exe.write_bytes(b'new')
        backup = tmp_path / 'CardRead2.exe.old'
        backup.write_bytes(b'old')
        updater.Updater.cleanup_backup(str(exe))
        assert not backup.exists()
        assert exe.exists()

    def test_missing_backup_is_fine(self, tmp_path):
        updater.Updater.cleanup_backup(str(tmp_path / 'nothing.exe'))
