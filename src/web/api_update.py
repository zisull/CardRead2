"""自动更新接口 Mixin

暴露给前端的是「轮询状态 + 手动触发」这一组方法：所有耗时动作（检查、测速、下载）
都在后台线程里跑，调用立即返回当前状态，前端据此渲染徽标与进度条。
"""
import contextlib
import json
import os
import sys
import threading
from typing import Any, Dict, List, Optional

from loguru import logger

from src.core import updater as _updater_mod
from src.core.updater import DEFAULT_MIRROR_PREFIXES, Updater

_CHECK_DELAY = 30.0              # 启动后多久做第一次静默检查（避开冷启动峰值）
_CHECK_INTERVAL = 24 * 3600.0    # 之后每隔多久复查一次
_MIRROR_SETTING = 'update_mirrors'
_DIRECT_TOKEN = 'direct'         # 配置里存不住空串，用字面量代表「GitHub 直连」


def _encode_mirrors(mirrors: List[str]) -> str:
    return '\n'.join(_DIRECT_TOKEN if not m else m for m in mirrors)


def _decode_mirrors(raw: str) -> List[str]:
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            out.append('' if line == _DIRECT_TOKEN else line)
    return out


class UpdateMixin:
    """pywebview 更新接口

    依赖 Api 提供的 _appdata_dir / _data_store / _window / _reader_windows / _windows_lock。
    """

    def _init_update(self) -> None:
        self._updater: Optional[Updater] = None
        self._updater_lock = threading.Lock()
        self._update_timer: Optional[threading.Timer] = None

    # ── 内部装配 ──

    def _updater_obj(self) -> Updater:
        with self._updater_lock:
            if self._updater is None:
                self._updater = Updater(
                    os.path.join(self._appdata_dir, 'update'),
                    self._app_version(),
                    self._current_exe_path(),
                    prefixes=self._load_mirrors(),
                )
            return self._updater

    @staticmethod
    def _app_version() -> str:
        from src.config import APP_VERSION
        return APP_VERSION

    @staticmethod
    def _current_exe_path() -> str:
        """打包后是 exe 本体，源码运行是 python 解释器（apply 会据此拒绝替换）"""
        return os.path.abspath(sys.executable)

    def _load_mirrors(self) -> List[str]:
        raw = self._data_store.get_setting(_MIRROR_SETTING)
        mirrors = _decode_mirrors(raw) if isinstance(raw, str) else []
        return mirrors or list(DEFAULT_MIRROR_PREFIXES)

    def _schedule_check(self, delay: float) -> None:
        with self._updater_lock:
            if self._update_timer:
                self._update_timer.cancel()
            self._update_timer = threading.Timer(delay, self._check_in_background)
            self._update_timer.daemon = True
            self._update_timer.start()

    def _check_in_background(self) -> None:
        """静默检查：失败只记日志，然后照常排下一次"""
        try:
            self._updater_obj().check()
            self._notify_update_status()
        except Exception as e:
            logger.warning(f"自动更新检查失败: {e}")
        finally:
            self._schedule_check(_CHECK_INTERVAL)

    def _notify_update_status(self) -> None:
        """把检查结果推给前端，省掉前端常驻轮询

        evaluate_js 只能往已存在的窗口里写，且窗口可能正在销毁，一律忽略失败。
        """
        window = getattr(self, '_window', None)
        if not window:
            return
        st = self._updater_obj().status()
        # ensure_ascii 保持默认 True：非 ASCII 全转义后才是可拼进 JS 源码的安全字面量
        payload = json.dumps({'phase': st['phase'],
                              'remote_version': st['remote_version'],
                              'local_version': st['local_version'],
                              # 面板开着时推送要能顶掉上一行文案，否则错误信息会消失
                              'error': st['error']})
        try:
            window.evaluate_js('if (window.onUpdateNotify) onUpdateNotify(%s);' % payload)
        except Exception as e:
            logger.debug(f"推送更新状态失败: {e}")

    # ── 对外接口 ──

    def start_update_watchdog(self) -> None:
        """启动时清理上次换身留下的 .old，并安排第一次静默检查"""
        try:
            Updater.cleanup_backup(self._current_exe_path())
        except Exception as e:
            logger.warning(f"清理旧版本备份失败: {e}")
        self._schedule_check(_CHECK_DELAY)
        logger.info(f"已安排自动更新检查：{int(_CHECK_DELAY)}s 后首次，之后每 "
                    f"{int(_CHECK_INTERVAL // 3600)}h")

    def get_update_status(self) -> Dict[str, Any]:
        """前端轮询用：当前阶段、进度、速度、源排名"""
        return self._updater_obj().status()

    def check_for_updates(self) -> Dict[str, Any]:
        return self._updater_obj().check_async()

    def start_update_download(self) -> Dict[str, Any]:
        return self._updater_obj().start_download()

    def cancel_update_download(self) -> Dict[str, Any]:
        return self._updater_obj().cancel()

    def apply_update(self) -> Dict[str, Any]:
        result = self._updater_obj().apply()
        if result.get('success'):
            # 新版本已经被拉起，这里只负责把自己关掉（不等 pywebview 事件循环自然退出）
            self._shutdown_for_relaunch()
        return result

    def get_update_mirrors(self) -> Dict[str, Any]:
        return {
            'mirrors': self._load_mirrors(),
            'default_mirrors': list(DEFAULT_MIRROR_PREFIXES),
            'direct_token': _DIRECT_TOKEN,
        }

    def set_update_mirrors(self, mirrors: List[str]) -> Dict[str, Any]:
        """保存用户自定义的源列表；留空则恢复默认

        直连以空串或 'direct' 表示，测速时它与各镜像同权竞争。
        """
        if not isinstance(mirrors, list):
            return {'success': False, 'error': '更新源列表必须是字符串数组'}
        cleaned: List[str] = []
        for item in mirrors:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if not value or value == _DIRECT_TOKEN:
                if '' not in cleaned:
                    cleaned.append('')
                continue
            if not value.startswith(('http://', 'https://')):
                return {'success': False, 'error': f'更新源必须以 http(s):// 开头: {value}'}
            if value not in cleaned:
                cleaned.append(value)
        if not cleaned:
            cleaned = list(DEFAULT_MIRROR_PREFIXES)
        self._data_store.set_setting(_MIRROR_SETTING, _encode_mirrors(cleaned))
        self._save_deferred()
        self._updater_obj().set_prefixes(cleaned)
        logger.info(f"更新源已保存: {cleaned}")
        return {'success': True, 'mirrors': cleaned}

    def open_release_page(self) -> Dict[str, Any]:
        """下载失败时的兜底：把用户送到 releases 页手动下载"""
        return {'success': self.open_url_in_browser(_updater_mod.RELEASE_PAGE_URL)}

    # ── 换身后的收尾 ──

    def _shutdown_for_relaunch(self) -> None:
        with contextlib.suppress(Exception):
            with self._windows_lock:
                for name in list(self._reader_windows):
                    with contextlib.suppress(Exception):
                        self._reader_windows[name].destroy()
                        del self._reader_windows[name]
        self.close_window()
        # 留一点时间让上面的 JS 调用把响应发回前端
        timer = threading.Timer(0.5, lambda: os._exit(0))
        timer.daemon = True
        timer.start()
