"""阅读与书签 Mixin

提供打开书籍、章节导航、搜索、书签等接口。
"""
import json
import os
import re
import sys
import threading
from contextlib import suppress
from html import escape as html_escape
from typing import Any, Dict, List

from loguru import logger

from src.config import MAIN_WINDOW_HEIGHT, DEFAULT_SETTINGS, SEARCH_MAX_RESULTS_DEFAULT, SEARCH_MAX_RESULTS_LIMIT
from src.core.reading_engine import ReadingEngine
from src.utils.file_utils import get_bundle_base_path
from src.utils.text_parser import TextParser
from src.web.api_helpers import _detect_chapter_level, _validate_book_name, ErrorCode


class ReaderMixin:
    """阅读与书签操作"""

    # ── 打开/关闭书籍 ──

    def open_book(self, book_name: str) -> Dict[str, Any]:
        try:
            if not _validate_book_name(book_name):
                return {'success': False, 'error': '无效的书名'}
            book = self._book_manager.get_book(book_name)
            if not book:
                with self._windows_lock:
                    if book_name in self._reader_windows:
                        with suppress(Exception):
                            self._reader_windows[book_name].evaluate_js(
                                'document.getElementById("contentArea").textContent="未找到书籍";'
                                'if(typeof hideLoading==="function")hideLoading();'
                            )
                return {'success': False, 'error': '未找到书籍', 'code': ErrorCode.BOOK_NOT_FOUND}
            with self._engines_lock:
                if book_name not in self._reading_engines:
                    engine = ReadingEngine(cache_dir=self._dirs.get('cache'))
                    theme_colors = self._get_theme_colors()
                    if not engine.load_book(book, theme_colors=theme_colors):
                        return {'success': False, 'error': '无法加载书籍', 'code': ErrorCode.PARSE_ERROR}
                    progress_data = self._data_store.get_progress(book_name)
                    chapter = progress_data.get('chapter', 0) if progress_data else 0
                    if not engine.load_chapter(chapter):
                        engine.chapter_parser.clear()
                        return {'success': False, 'error': '无法加载章节', 'code': ErrorCode.PARSE_ERROR}
                    self._reading_engines[book_name] = engine
                    self._current_book = book_name
                    self._data_store.start_reading_session(book_name)
                    self._index_book_async(book_name, engine)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _index_book_async(self, book_name: str, engine: ReadingEngine):
        def _do_index():
            try:
                if self._search_index.is_indexed(book_name):
                    indexed_count = self._search_index.get_indexed_chapter_count(book_name)
                    if indexed_count == engine.chapter_count:
                        return
                chapters = []
                for i in range(engine.chapter_count):
                    content = engine.get_chapter_content(i)
                    chapters.append(content or '')
                self._search_index.index_book(book_name, chapters)
                logger.info(f"搜索索引创建完成: {book_name}")
            except Exception as e:
                logger.warning(f"搜索索引创建失败: {book_name}: {e}")
        threading.Thread(target=_do_index, daemon=True).start()

    def open_reader_window(self, book_name: str) -> bool:
        import webview
        try:
            with self._windows_lock:
                if book_name in self._reader_windows:
                    w = self._reader_windows[book_name]
                    with suppress(Exception):
                        w.evaluate_js('window.focus()')
                    return True
            self._current_book = book_name
            _base = get_bundle_base_path(__file__)
            reader_html = os.path.join(_base, 'static', 'reader.html')
            if not os.path.exists(reader_html):
                return False
            abs_path = os.path.abspath(reader_html)
            reader_url = 'file:///' + abs_path.replace('\\', '/')
            saved = self._data_store.get_setting('reader_window_geometry', {})
            geom = saved.get(book_name, {}) if isinstance(saved, dict) else {}
            if geom:
                rx = geom.get('x', 0)
                ry = geom.get('y', 0)
                rw = geom.get('width', 496)
            else:
                rx, ry = 0, 0
                rw = 496
                if self._window:
                    with suppress(Exception):
                        rx = self._window.x + self._window.width + 8
                        ry = self._window.y
            rh = MAIN_WINDOW_HEIGHT
            if not geom and self._window:
                with suppress(Exception):
                    rw = max(320, int(MAIN_WINDOW_HEIGHT * 472 / 761))
            # 检查是否之前已设为置顶
            all_on_top = self._data_store.get_setting('reader_always_on_top', {})
            was_on_top = isinstance(all_on_top, dict) and all_on_top.get(book_name, False)
            reader_window = webview.create_window(
                title=f'📖 {book_name}',
                url=reader_url,
                js_api=self,
                x=rx, y=ry,
                width=rw, height=rh,
                min_size=(320, 450),
                resizable=True,
                text_select=True,
                frameless=True,
                easy_drag=False,
                background_color='#0c0c14',
                on_top=was_on_top
            )
            with self._windows_lock:
                self._reader_windows[book_name] = reader_window
            return True
        except Exception as e:
            logger.error(f"打开阅读窗口失败: {e}")
            return False

    def get_current_book_name(self) -> str:
        return self._current_book or ''

    def _get_book_display_data(self, book_name: str) -> Dict[str, Any]:
        with self._engines_lock:
            if book_name not in self._reading_engines:
                return {'success': False, 'error': '书籍未加载'}
            engine = self._reading_engines[book_name]
            progress_data = self._data_store.get_progress(book_name)
            chapter_count = engine.chapter_count
            chapter_titles = [engine.get_chapter_title(i) for i in range(chapter_count)]
            content = engine.get_current_content()
            html = engine.get_current_html()
            chapter_title = engine.get_chapter_title()
            current_chapter = engine.current_chapter
        all_settings = self._data_store.get_all_settings()
        scroll_percent = progress_data.get('scroll_percent', 0) if progress_data else 0
        return {
            'success': True,
            'book_name': book_name,
            'chapter_title': chapter_title,
            'content': content,
            'html': html,
            'current_chapter': current_chapter,
            'chapter_count': chapter_count,
            'chapters': [{'title': t, 'preview': '', 'level': _detect_chapter_level(t)} for t in chapter_titles],
            'scroll_percent': scroll_percent if scroll_percent > 0 else 0,
            'settings': {
                'font_family': all_settings.get('font_family', DEFAULT_SETTINGS['font_family']),
                'font_size': all_settings.get('font_size', DEFAULT_SETTINGS['font_size']),
                'line_spacing': all_settings.get('line_spacing', DEFAULT_SETTINGS['line_spacing']),
                'paragraph_spacing': all_settings.get('paragraph_spacing', DEFAULT_SETTINGS.get('paragraph_spacing', 20)),
                'text_indent': all_settings.get('text_indent', DEFAULT_SETTINGS.get('text_indent', 2)),
                'auto_next_chapter_enabled': all_settings.get('auto_next_chapter_enabled', DEFAULT_SETTINGS['auto_next_chapter_enabled']),
                'page_turn_speed': all_settings.get('page_turn_speed', 200),
                'reader_bg_image': all_settings.get('reader_bg_image', all_settings.get('background_image', '')),
                'reader_bg_opacity': all_settings.get('reader_bg_opacity', all_settings.get('background_opacity', 0.08)),
            }
        }

    def get_book_display_data(self, book_name: str) -> Dict[str, Any]:
        return self._get_book_display_data(book_name)

    @staticmethod
    def _build_txt_html(content: str) -> str:
        if not content:
            return ''
        content = re.sub(r'([ \t\r]*\n){2,}', '\n\n', content)
        paras = content.split('\n\n')
        parts = []
        for p in paras:
            p = p.strip()
            if not p:
                continue
            lines = p.split('\n')
            clean_lines = [ln for ln in lines if ln.strip()]
            if not clean_lines:
                continue
            html_body = '<br>'.join(html_escape(ln.strip()) for ln in clean_lines)
            parts.append(f'<p>{html_body}</p>')
        return ''.join(parts) if parts else ''

    # ── 章节导航 ──

    def get_chapters_range(self, book_name: str, start: int, count: int) -> Dict[str, Any]:
        try:
            # 锁内仅取 engine 引用和校验，锁外执行 HTML 生成，避免阻塞其他引擎操作
            with self._engines_lock:
                if book_name not in self._reading_engines:
                    return {'success': False, 'error': '书籍未加载', 'code': ErrorCode.BOOK_NOT_FOUND}
                engine = self._reading_engines[book_name]
                total = engine.chapter_count
            start = max(0, min(start, total - 1))
            end = min(start + count, total)
            parts = []
            for i in range(start, end):
                html = engine.chapter_parser.get_chapter_html(i)
                title = engine.get_chapter_title(i)
                anchor = f'<div class="ch-anchor" data-chapter="{i}" id="ch-{i}"></div>'
                if html:
                    parts.append(anchor + html)
                else:
                    content = engine.get_chapter_content(i)
                    header = f'<h2 class="ch-title" data-chapter="{i}">{title}</h2>'
                    generated = header + self._build_txt_html(content)
                    engine.chapter_parser.set_chapter_html(i, generated)
                    parts.append(anchor + generated)
            return {
                'success': True,
                'html': '\n<hr class="ch-sep">\n'.join(parts),
                'start': start, 'end': end, 'total': total,
            }
        except Exception as e:
            logger.error(f"获取章节范围失败: {e}")
            return {'success': False, 'error': str(e)}

    def search_in_book(self, book_name: str, query: str, max_results: int = SEARCH_MAX_RESULTS_DEFAULT) -> Dict[str, Any]:
        try:
            if not query or not query.strip():
                return {'success': True, 'results': [], 'total': 0}
            max_results = min(max(1, max_results), SEARCH_MAX_RESULTS_LIMIT)
            if self._search_index.is_indexed(book_name):
                results = self._search_index.search(query, book_name, max_results)
                if results:
                    return {'success': True, 'results': results, 'total': len(results)}
            # fallback：锁内取 engine 引用，锁外执行正则扫描，避免持锁阻塞翻页等操作
            with self._engines_lock:
                if book_name not in self._reading_engines:
                    return {'success': False, 'error': '书籍未加载'}
                engine = self._reading_engines[book_name]
                chapter_count = engine.chapter_count
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            results = []
            total_matches = 0
            for i in range(chapter_count):
                content = engine.get_chapter_content(i)
                if not content:
                    continue
                for match in pattern.finditer(content):
                    total_matches += 1
                    if len(results) < max_results:
                        idx = match.start()
                        start = max(0, idx - 20)
                        end = min(len(content), idx + len(query) + 20)
                        context = content[start:end]
                        results.append({'chapter': i, 'position': idx, 'context': context})
            return {'success': True, 'results': results, 'total': total_matches}
        except Exception as e:
            logger.error(f"全文检索失败: {e}")
            return {'success': False, 'error': str(e)}

    def get_chapter_previews(self, book_name: str) -> List[Dict[str, str]]:
        try:
            if book_name in self._preview_cache:
                return self._preview_cache[book_name]
            with self._engines_lock:
                if book_name not in self._reading_engines:
                    return []
                engine = self._reading_engines[book_name]
                result = []
                for i in range(engine.chapter_count):
                    title = engine.get_chapter_title(i)
                    preview = TextParser.get_chapter_preview(engine.get_chapter_content(i) or '')
                    result.append({'title': title, 'preview': preview, 'level': _detect_chapter_level(title)})
                self._preview_cache[book_name] = result
                return result
        except Exception as e:
            logger.error(f"获取章节预览失败: {e}")
            return []

    def get_chapter(self, book_name: str, chapter_index: int) -> Dict[str, Any]:
        try:
            with self._engines_lock:
                if book_name not in self._reading_engines:
                    return {'success': False, 'error': '书籍未加载', 'code': ErrorCode.BOOK_NOT_FOUND}
                engine = self._reading_engines[book_name]
                if not engine.load_chapter(chapter_index):
                    return {'success': False, 'error': '无法加载章节', 'code': ErrorCode.PARSE_ERROR}
                self._current_book = book_name
                content = engine.get_current_content()
                html = engine.get_current_html()
                chapter_title = engine.get_chapter_title()
            self._data_store.update_progress(book_name, chapter_index, 0)
            self._save_deferred()
            return {
                'success': True, 'chapter_title': chapter_title,
                'content': content, 'html': html, 'current_chapter': chapter_index
            }
        except Exception as e:
            logger.error(f"获取章节失败: {e}")
            return {'success': False, 'error': str(e)}

    def prev_chapter(self, book_name: str) -> Dict[str, Any]:
        with self._engines_lock:
            if book_name not in self._reading_engines:
                return {'success': False, 'error': '书籍未加载'}
            engine = self._reading_engines[book_name]
            current = engine.current_chapter
        if current > 0:
            return self.get_chapter(book_name, current - 1)
        return {'success': False, 'error': '已经是第一章'}

    def next_chapter(self, book_name: str) -> Dict[str, Any]:
        with self._engines_lock:
            if book_name not in self._reading_engines:
                return {'success': False, 'error': '书籍未加载'}
            engine = self._reading_engines[book_name]
            current = engine.current_chapter
            chapter_count = engine.chapter_count
        if current < chapter_count - 1:
            return self.get_chapter(book_name, current + 1)
        return {'success': False, 'error': '已经是最后一章'}

    def update_reading_progress(self, book_name: str, chapter: int, scroll_percent: int) -> bool:
        try:
            self._data_store.update_progress(book_name, chapter, scroll_percent)
            self._save_deferred()
            return True
        except Exception as e:
            logger.error(f"更新阅读进度失败: {e}")
            return False

    def close_book(self, book_name: str) -> bool:
        try:
            with self._engines_lock:
                if book_name in self._reading_engines:
                    engine = self._reading_engines[book_name]
                    engine.chapter_parser.clear()
                    del self._reading_engines[book_name]
                    self._preview_cache.pop(book_name, None)
                    if self._current_book == book_name:
                        self._current_book = None
                    self._data_store.stop_reading_session(book_name)
                    self._save_immediate()
                    self._invalidate_books_cache()
                    return True
            return False
        except Exception as e:
            logger.error(f"关闭书籍失败: {e}")
            return False

    def continue_reading(self) -> Dict[str, Any]:
        last_read = self._data_store.get_last_read_book()
        if last_read:
            return self.open_book(last_read)
        return {'success': False, 'error': '没有阅读记录'}

    def reset_app(self) -> bool:
        try:
            with self._windows_lock:
                for name, w in list(self._reader_windows.items()):
                    with suppress(Exception):
                        w.destroy()
                self._reader_windows.clear()
            with self._engines_lock:
                engine_names = list(self._reading_engines.keys())
            for book_name in engine_names:
                self.close_book(book_name)

            import subprocess, tempfile, json
            with suppress(Exception):
                self._data_store.close()

            lock_file = os.path.join(tempfile.gettempdir(), 'cardread2.lock')
            with suppress(OSError):
                if os.path.exists(lock_file):
                    os.remove(lock_file)

            appdata_dir = getattr(self, '_appdata_dir', None) or os.path.dirname(os.path.dirname(self._data_store.config_file))
            exe_path = os.path.abspath(sys.argv[0])
            if exe_path.lower().endswith('.exe'):
                restart_cmd = f'start "" {json.dumps(exe_path)}'
                wait_name = os.path.basename(exe_path)
            else:
                python_exe = sys.executable
                if os.name == 'nt':
                    candidate = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
                    if os.path.exists(candidate):
                        python_exe = candidate
                restart_cmd = f'start "" {json.dumps(python_exe)} {json.dumps(exe_path)}'
                wait_name = os.path.basename(sys.executable)

            bat_path = os.path.join(tempfile.gettempdir(), f'cardread_reset_{os.getpid()}.bat')
            bat = f'''@echo off
chcp 65001 >nul
set "APPDIR={appdata_dir}"
set "LOCKFILE={lock_file}"
set "WAITNAME={wait_name}"
timeout /t 1 /nobreak >nul
for /l %%i in (1,1,30) do (
    tasklist /fi "imagename eq %WAITNAME%" | find /i "%WAITNAME%" >nul
    if errorlevel 1 goto cleanup
    timeout /t 1 /nobreak >nul
)
:cleanup
if exist "%LOCKFILE%" del /f /q "%LOCKFILE%" >nul 2>nul
if exist "%APPDIR%" rmdir /s /q "%APPDIR%" >nul 2>nul
for /l %%i in (1,1,20) do (
    if not exist "%APPDIR%" goto restart
    timeout /t 1 /nobreak >nul
    rmdir /s /q "%APPDIR%" >nul 2>nul
)
:restart
{restart_cmd}
del /f /q "%~f0" >nul 2>nul
'''
            with open(bat_path, 'w', encoding='utf-8') as f:
                f.write(bat)
            logger.info(f"重置应用脚本: {bat_path}")
            subprocess.Popen(['cmd.exe', '/c', bat_path], cwd=tempfile.gettempdir(), close_fds=True)
            if self._window:
                with suppress(Exception):
                    self._window.destroy()
            return True
        except Exception as e:
            logger.error(f"重置应用失败: {e}")
            return False

    # ── 书签 ──

    def add_bookmark(self, book_name: str, chapter: int, position: int, description: str) -> bool:
        try:
            bookmark_data = {'chapter': chapter, 'position': position, 'description': description}
            self._data_store.add_bookmark(book_name, bookmark_data)
            self._save_deferred()
            return True
        except Exception as e:
            logger.error(f"添加书签失败: {e}")
            return False

    def get_bookmarks(self, book_name: str) -> List[Dict[str, Any]]:
        try:
            return self._data_store.get_bookmarks(book_name)
        except Exception as e:
            logger.error(f"获取书签失败: {e}")
            return []

    def get_all_bookmarks(self) -> List[Dict[str, Any]]:
        try:
            result = []
            all_bookmarks = self._data_store.get_all_bookmarks()
            for name, bookmarks in all_bookmarks.items():
                for i, bm in enumerate(bookmarks):
                    result.append({
                        'book_name': name, 'index': i, 'chapter': bm.get('chapter', 0),
                        'position': bm.get('position', 0), 'description': bm.get('description', ''), 'time': bm.get('time', ''),
                    })
            result.sort(key=lambda x: x.get('time', ''), reverse=True)
            return result
        except Exception as e:
            logger.error(f"获取全部书签失败: {e}")
            return []

    def remove_bookmark(self, book_name: str, index: int) -> bool:
        try:
            result = self._data_store.remove_bookmark(book_name, index)
            if result:
                self._save_deferred()
            return result
        except Exception as e:
            logger.error(f"删除书签失败: {e}")
            return False

    def update_bookmark(self, book_name: str, index: int, description: str) -> bool:
        try:
            result = self._data_store.update_bookmark(book_name, index, description)
            if result:
                self._save_deferred()
            return result
        except Exception as e:
            logger.error(f"更新书签失败: {e}")
            return False

    def remove_bookmarks(self, book_name: str, indices: List[int]) -> bool:
        try:
            removed = 0
            for idx in sorted(indices, reverse=True):
                if self._data_store.remove_bookmark(book_name, idx):
                    removed += 1
            if removed > 0:
                self._save_deferred()
            return removed > 0
        except Exception as e:
            logger.error(f"批量删除书签失败: {e}")
            return False

    def goto_bookmark(self, book_name: str, index: int) -> Dict[str, Any]:
        try:
            bookmarks = self._data_store.get_bookmarks(book_name)
            if index >= len(bookmarks):
                return {'success': False, 'error': '书签不存在'}
            bookmark = bookmarks[index]
            chapter = int(bookmark.get('chapter', 0))
            position = int(bookmark.get('position', 0))
            result = self.get_chapter(book_name, chapter)
            if result.get('success'):
                result['scroll_percent'] = position
                self._data_store.update_progress(book_name, chapter, position)
                self._save_deferred()
            with self._windows_lock:
                has_window = book_name in self._reader_windows
                w = self._reader_windows[book_name] if has_window else None
            if has_window and w is not None:
                try:
                    # 后端只调前端暴露的函数，JS 逻辑留在 reader.js 维护
                    ch_json = json.dumps(chapter)
                    pos_json = json.dumps(position)
                    w.evaluate_js(
                        f'if(typeof window.gotoBookmark==="function")'
                        f'window.gotoBookmark({ch_json},{pos_json});'
                    )
                    w.evaluate_js('window.focus()')
                except Exception:
                    pass
            return result
        except Exception as e:
            logger.error(f"跳转书签失败: {e}")
            return {'success': False, 'error': str(e)}
