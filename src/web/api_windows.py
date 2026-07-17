"""窗口控制与应用信息 Mixin

提供窗口操作、日志查看、应用信息等接口。
"""
import json
import os
import re
import sys
from contextlib import suppress
from typing import Any, Dict

from loguru import logger


class WindowsMixin:
    """窗口控制与应用信息"""

    # ── 线程安全的窗口置顶 ──

    @staticmethod
    def _set_window_on_top(win, value: bool):
        """设置窗口置顶，通过 WinForms Invoke 确保在 UI 线程执行。
        pywebview 6.x 的 set_on_top 平台代码直接在调用线程设置 TopMost，
        从 JS 回调线程调用会死锁，因此这里手动做线程调度。"""
        try:
            import clr  # noqa: F811
            from System import Func
            from System.Windows.Forms import Form
            native = win.native
            if hasattr(native, 'InvokeRequired') and native.InvokeRequired:
                native.Invoke(Func[Form](lambda: setattr(native, 'TopMost', value)))
            else:
                native.TopMost = value
        except Exception:
            # 非 WinForms 平台或原生接口不可用，回退到属性赋值
            with suppress(Exception):
                win.on_top = value

    # ── 窗口控制 ──

    def open_data_folder(self) -> bool:
        try:
            if sys.platform == 'win32':
                os.startfile(self._appdata_dir)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.run(['open', self._appdata_dir])
            else:
                import subprocess
                subprocess.run(['xdg-open', self._appdata_dir])
            return True
        except Exception as e:
            logger.error(f"打开文件夹失败: {e}")
            return False

    def open_url_in_browser(self, url: str) -> bool:
        try:
            if not url.startswith(('http://', 'https://')):
                logger.warning(f"拒绝打开非 http(s) 链接: {url}")
                return False
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.error(f"打开链接失败: {e}")
            return False

    def show_bookshelf(self) -> bool:
        try:
            import webview
            w = getattr(self, '_window', None)
            # 通过 webview.windows 判断主窗口是否仍然存活
            # destroy() 后 self._window 仍可能持有失效引用，直接调用会静默失败
            if w is not None and w not in webview.windows:
                w = None
                self._window = None
            if w:
                with suppress(Exception):
                    w.restore()
                with suppress(Exception):
                    w.show()
                with suppress(Exception):
                    self._set_window_on_top(w, True)
                    self._set_window_on_top(w, False)
            else:
                # 主窗口已被关闭（用户点了×但阅读器仍开着），重建主窗口
                self._recreate_main_window()
            return True
        except Exception as e:
            logger.error(f"显示书架失败: {e}")
            return False

    def _recreate_main_window(self) -> None:
        """重新创建主书架窗口。

        场景：用户关闭主窗口后，仍保留阅读器窗口；此时从阅读器点击"打开书架"
        需要重新拉起主窗口。pywebview 6.x 支持在 webview.start() 之后从任意
        线程调用 create_window（内部会调度到 UI 线程）。
        """
        import webview
        from src.config import APP_DISPLAY_NAME, APP_VERSION, MAIN_WINDOW_HEIGHT
        from src.web.main import get_html_path

        layout = self.get_home_layout()
        html_path = get_html_path(layout)
        window = webview.create_window(
            title=f'{APP_DISPLAY_NAME} v{APP_VERSION}',
            url=html_path,
            js_api=self,
            width=1200,
            height=MAIN_WINDOW_HEIGHT,
            min_size=(900, 650),
            resizable=True,
            text_select=True,
            frameless=True,
            easy_drag=False,
            background_color='#0c0c14'
        )
        self._window = window
        self._is_maximized = False

    def minimize_window(self) -> bool:
        try:
            if self._window:
                self._window.minimize()
            return True
        except Exception as e:
            logger.error(f"最小化窗口失败: {e}")
            return False

    def toggle_maximize(self) -> bool:
        try:
            if self._window:
                if self._is_maximized:
                    self._window.restore()
                    self._is_maximized = False
                else:
                    self._window.maximize()
                    self._is_maximized = True
            return self._is_maximized
        except Exception as e:
            logger.error(f"切换最大化失败: {e}")
            return False

    def close_window(self) -> bool:
        try:
            for name in list(self._data_store.get_active_sessions().keys()):
                self._data_store.stop_reading_session(name)
            self._save_immediate()
            if self._window:
                self._window.destroy()
                # 清除引用，避免后续 show_bookshelf 等拿到失效对象
                self._window = None
            return True
        except Exception as e:
            logger.error(f"关闭窗口失败: {e}")
            return False

    def close_reader_window(self, book_name: str) -> bool:
        try:
            with self._windows_lock:
                if book_name in self._reader_windows:
                    self._reader_windows[book_name].destroy()
                    del self._reader_windows[book_name]
            try:
                self.close_book(book_name)
            except Exception:
                logger.warning(f"关闭书籍失败: {book_name}")
            if self._window:
                try:
                    self._window.evaluate_js(
                        'if(typeof loadBooks==="function")'
                        'loadBooks().then(function(){'
                        'if(typeof loadStats==="function")loadStats(true);'
                        '});'
                    )
                except Exception:
                    pass
            return True
        except Exception as e:
            logger.warning(f"关闭阅读窗口异常 [{book_name}]: {e}")
            return False

    def move_main_window(self, dx: int, dy: int) -> bool:
        try:
            if self._window:
                self._window.move(self._window.x + dx, self._window.y + dy)
            return True
        except Exception:
            return False

    def move_reader_window(self, book_name: str, dx: int, dy: int) -> bool:
        try:
            with self._windows_lock:
                if book_name in self._reader_windows:
                    w = self._reader_windows[book_name]
                    w.move(w.x + dx, w.y + dy)
            return True
        except Exception:
            return False

    def resize_reader_window(self, book_name: str, width: int, height: int) -> bool:
        try:
            with self._windows_lock:
                if book_name in self._reader_windows:
                    w = self._reader_windows[book_name]
                    w.resize(width, height)
            return True
        except Exception:
            return False

    def get_reader_window_size(self, book_name: str) -> Dict[str, int]:
        try:
            with self._windows_lock:
                if book_name in self._reader_windows:
                    w = self._reader_windows[book_name]
                    return {'width': w.width, 'height': w.height}
            return {'width': 500, 'height': 800}
        except Exception:
            return {'width': 500, 'height': 800}

    def save_reader_window_geometry(self, book_name: str) -> bool:
        try:
            with self._windows_lock:
                if book_name not in self._reader_windows:
                    return False
                w = self._reader_windows[book_name]
                geom_x, geom_y = w.x, w.y
                geom_w, geom_h = w.width, w.height
            all_geom = self._data_store.get_setting('reader_window_geometry', {})
            if not isinstance(all_geom, dict):
                all_geom = {}
            all_geom[book_name] = {'x': geom_x, 'y': geom_y, 'width': geom_w, 'height': geom_h}
            self._data_store.set_setting('reader_window_geometry', all_geom)
            self._save_deferred(delay=0.5)
            return True
        except Exception:
            return False

    def reset_reader_window_geometry(self, book_name: str) -> bool:
        from src.config import MAIN_WINDOW_HEIGHT
        try:
            with self._windows_lock:
                if book_name not in self._reader_windows:
                    return False
                w = self._reader_windows[book_name]
            all_geom = self._data_store.get_setting('reader_window_geometry', {})
            if isinstance(all_geom, dict) and book_name in all_geom:
                del all_geom[book_name]
                self._data_store.set_setting('reader_window_geometry', all_geom)
                self._save_immediate()
            rx, ry = 0, 0
            rw = max(320, int(MAIN_WINDOW_HEIGHT * 472 / 761))
            if self._window:
                try:
                    rx = self._window.x + self._window.width + 8
                    ry = self._window.y
                except Exception:
                    pass
            w.move(rx, ry)
            w.resize(rw, MAIN_WINDOW_HEIGHT)
            return True
        except Exception:
            return False

    def refresh_reader_settings(self) -> bool:
        try:
            with self._windows_lock:
                windows = list(self._reader_windows.items())
            for name, w in windows:
                try:
                    w.evaluate_js('setTimeout(function(){if(typeof refreshFromMain==="function")refreshFromMain();},50)')
                except Exception:
                    pass
            return True
        except Exception:
            return False

    def refresh_reader_shortcuts(self) -> bool:
        try:
            with self._windows_lock:
                windows = list(self._reader_windows.items())
            for name, w in windows:
                try:
                    w.evaluate_js('setTimeout(function(){if(typeof loadShortcutSettings==="function")loadShortcutSettings();},50)')
                except Exception:
                    pass
            return True
        except Exception:
            return False

    def toggle_reader_always_on_top(self, book_name: str) -> bool:
        try:
            with self._windows_lock:
                if book_name not in self._reader_windows:
                    return False
                w = self._reader_windows[book_name]
            # 获取当前置顶状态（通过检查按钮状态）
            current_state = self._data_store.get_setting('reader_always_on_top', {})
            if not isinstance(current_state, dict):
                current_state = {}
            is_on_top = current_state.get(book_name, False)
            new_state = not is_on_top
            # 设置窗口置顶（通过 WinForms Invoke 确保线程安全）
            self._set_window_on_top(w, new_state)
            # 保存状态
            current_state[book_name] = new_state
            self._data_store.set_setting('reader_always_on_top', current_state)
            self._save_deferred(delay=0.5)
            return new_state
        except Exception as e:
            logger.error(f"切换置顶状态失败: {e}")
            return False

    def get_reader_always_on_top(self, book_name: str) -> bool:
        try:
            current_state = self._data_store.get_setting('reader_always_on_top', {})
            if not isinstance(current_state, dict):
                current_state = {}
            return current_state.get(book_name, False)
        except Exception:
            return False

    def preview_reader_theme(self, colors: Dict[str, str]) -> bool:
        try:
            js = 'setTimeout(function(){if(typeof applyThemeDirect==="function")applyThemeDirect(' + json.dumps(colors) + ');},30)'
            with self._windows_lock:
                windows = list(self._reader_windows.items())
            for name, w in windows:
                try:
                    w.evaluate_js(js)
                except Exception:
                    pass
            try:
                note_js = 'setTimeout(function(){if(typeof applyNoteTheme==="function")applyNoteTheme(' + json.dumps(colors) + ');},30)'
                with self._windows_lock:
                    note_wins = list(self._note_editor_windows.items()) + list(self._note_viewer_windows.items())
                for nid, w in note_wins:
                    try:
                        w.evaluate_js(note_js)
                    except Exception:
                        pass
            except Exception:
                pass
            return True
        except Exception:
            return False

    def preview_typography(self, settings: Dict[str, Any]) -> bool:
        try:
            js = 'setTimeout(function(){if(typeof applyTypographyPreview==="function")applyTypographyPreview(' + json.dumps(settings) + ');},30)'
            with self._windows_lock:
                windows = list(self._reader_windows.items())
            for name, w in windows:
                try:
                    w.evaluate_js(js)
                except Exception:
                    pass
            return True
        except Exception:
            return False

    # ── 应用信息 ──

    def get_app_info(self) -> Dict[str, Any]:
        from src.config import (
            APP_DISPLAY_NAME, APP_VERSION, COPYRIGHT, get_version_text,
            AUTHOR_INFO,
        )
        return {
            'name': APP_DISPLAY_NAME,
            'version': APP_VERSION,
            'copyright': COPYRIGHT,
            'version_text': get_version_text(),
            'author_info': AUTHOR_INFO,
        }

    def get_logs(self, level: str = 'ALL', limit: int = 500, search: str = '') -> Dict[str, Any]:
        try:
            log_file = os.path.join(self._appdata_dir, 'cardread_web.log')
            if not os.path.isfile(log_file):
                return {'logs': [], 'total': 0, 'file': log_file}
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            entries = []
            _LEVEL_RE = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s*\|\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*\|\s*(.+?):(.+)$')
            for line in reversed(lines):
                line = line.rstrip('\n\r')
                if not line:
                    continue
                m = _LEVEL_RE.match(line)
                if m:
                    entry = {
                        'time': m.group(1), 'level': m.group(2),
                        'source': m.group(3).strip(), 'message': m.group(4).strip(),
                    }
                else:
                    if entries and not line.startswith(('20', '19')):
                        entries[-1]['message'] += '\n' + line
                        continue
                    entry = {'time': '', 'level': 'INFO', 'source': '', 'message': line}
                if level and level != 'ALL' and entry['level'] != level:
                    continue
                if search and search.lower() not in entry['message'].lower() and search.lower() not in entry['source'].lower():
                    continue
                entries.append(entry)
                if len(entries) >= limit:
                    break
            entries.reverse()
            return {'logs': entries, 'total': len(entries), 'file': log_file}
        except Exception as e:
            logger.error(f"读取日志失败: {e}")
            return {'logs': [], 'total': 0, 'error': str(e)}

    def clear_logs(self) -> Dict[str, Any]:
        try:
            import sys as _sys
            from loguru import logger as _logger
            log_file = os.path.join(self._appdata_dir, 'cardread_web.log')
            error_log = os.path.join(self._appdata_dir, 'cardread_error.log')
            # loguru 持续占用日志文件句柄，Windows 上直接 open('w') 会 PermissionError
            # 方案：先 complete() 刷新缓冲，remove() 释放句柄，清空文件，再重新 add handler
            _logger.complete()
            _logger.remove()
            for f in [log_file, error_log]:
                if os.path.isfile(f):
                    try:
                        with open(f, 'w', encoding='utf-8') as fh:
                            fh.write('')
                    except OSError as e:
                        logger.warning(f"清空日志文件失败（将跳过）: {f}: {e}")
            # 重新添加 handler（与 main.setup_logging 配置保持一致）
            _logger.add(log_file, rotation="1 MB", retention="7 days", encoding="utf-8", level="DEBUG")
            _logger.add(error_log, rotation="512 KB", retention="30 days", encoding="utf-8", level="ERROR")
            if _sys.stderr is not None:
                _logger.add(_sys.stderr, level="INFO")
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
