"""书架与书籍操作 Mixin

提供书籍列表、封面、统计、导入、删除、重命名等接口。
"""
import base64
import json
import mimetypes
import os
import shutil
import sys
import threading
import zipfile
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.web.api_helpers import (
    _MAX_IMPORT_SIZE, _MAX_IMAGE_SIZE, _MAX_IMAGE_DATA_URL_SIZE,
    _get_cover_char, _get_pinyin_initials, _get_pinyin_full, _validate_book_name,
)
from src.utils.decorators import handle_api_error


class BooksMixin:
    """书架与书籍操作"""

    # ── 书架列表 ──

    def _invalidate_books_cache(self) -> None:
        self._books_cache_dirty = True
        self._cached_stats_from_books = None

    def get_books(self) -> List[Dict[str, Any]]:
        if not self._books_cache_dirty and self._books_cache is not None:
            return self._books_cache
        books = self._get_all_books()
        result, skipped_no_file, stats = self._serialize_books(books)
        self._books_cache = result
        self._books_cache_dirty = False
        self._cached_stats_from_books = stats
        logger.debug(f"返回 {len(result)} 本书 (书架共 {len(books)} 本, 跳过: {skipped_no_file})")
        return result

    def _get_all_books(self) -> list:
        books = self._book_manager.get_all_books_list()
        if not books:
            try:
                new_count = self._book_manager.scan_books_directory()
                if new_count > 0:
                    self._save_immediate()
                    books = self._book_manager.get_all_books_list()
            except Exception as e:
                logger.error(f"兜底扫描失败: {e}")
        return books

    def _serialize_books(self, books: list) -> tuple:
        result = []
        skipped_no_file = 0
        stats_total_chapters = 0
        stats_word_count_sum = 0
        stats_total_progress = 0
        stats_books_with_progress = 0
        for book in books:
            try:
                if not book.file_exists():
                    skipped_no_file += 1
                    logger.debug(f"跳过文件不存在: {book.name} -> {book.file_path}")
                    continue
                book_info = self._serialize_single_book(book)
                if book_info:
                    result.append(book_info)
                    stats_total_chapters += book_info.get('chapters', 0)
                    stats_word_count_sum += book_info.get('word_count', 0)
                    # 累计进度百分比，避免 get_stats 重复遍历计算
                    total_chapters = book.total_chapters or 0
                    if total_chapters > 0:
                        progress_data = self._data_store.get_progress(book.name)
                        if progress_data:
                            chapter = progress_data.get('chapter', 0)
                            stats_total_progress += min(100, int((chapter + 1) / total_chapters * 100))
                            stats_books_with_progress += 1
            except Exception as e:
                logger.warning(f"序列化书籍失败 [{book.name}]: {e}")
                continue
        stats = {
            'total_books': len(books),
            'total_chapters': stats_total_chapters,
            'word_count_sum': stats_word_count_sum,
            'progress_percent': int(stats_total_progress / stats_books_with_progress) if stats_books_with_progress > 0 else 0,
        }
        return result, skipped_no_file, stats

    def _serialize_single_book(self, book) -> Optional[Dict[str, Any]]:
        progress_data = self._data_store.get_progress(book.name)
        has_progress = progress_data is not None
        word_count = book.word_count or 0
        if word_count >= 10000:
            word_count_text = f"{word_count / 10000:.1f}万"
        elif word_count >= 1000:
            word_count_text = f"{word_count / 1000:.1f}千"
        else:
            word_count_text = str(word_count)
        total_chapters = book.total_chapters or 0
        if has_progress and total_chapters > 0:
            chapter = progress_data.get('chapter', 0)
            percent = min(100, int((chapter + 1) / total_chapters * 100))
            progress_text = f"{percent}%"
        else:
            progress_text = "未读"
        display_name = book.get_display_name()
        return {
            'name': book.name,
            'display_name': display_name,
            'cover_char': _get_cover_char(display_name),
            'pinyin_initials': _get_pinyin_initials(display_name),
            'pinyin_full': _get_pinyin_full(display_name),
            'chapters': total_chapters,
            'size': book.get_display_size(),
            'word_count': word_count,
            'word_count_text': word_count_text,
            'progress': progress_text,
            'file_path': book.file_path,
            'format': os.path.splitext(book.file_path)[1].upper().lstrip('.') or 'TXT',
            'last_read': progress_data.get('last_read', '') if has_progress else ''
        }

    # ── 封面 ──

    def get_book_cover(self, book_name: str) -> Dict[str, Any]:
        try:
            if book_name in self._cover_cache:
                cached = self._cover_cache[book_name]
                return {'success': bool(cached), 'cover': cached}
            with self._engines_lock:
                if book_name in self._reading_engines:
                    engine = self._reading_engines[book_name]
                    cover_data = engine.chapter_parser.get_cover_data()
                    self._cover_cache[book_name] = cover_data or ''
                    if cover_data:
                        return {'success': True, 'cover': cover_data}
            book = self._book_manager.get_book(book_name)
            if not book or not book.file_exists():
                self._cover_cache[book_name] = ''
                return {'success': False, 'cover': ''}
            if not book.file_path.lower().endswith(('.epub', '.mobi', '.pdb')):
                self._cover_cache[book_name] = ''
                return {'success': False, 'cover': ''}
            from src.parsers.registry import get_registry
            for parser in get_registry():
                if hasattr(parser, 'get_cover_image') and parser.supports(book.file_path):
                    try:
                        cover_data = parser.get_cover_image(book.file_path)
                        if cover_data:
                            self._cover_cache[book_name] = cover_data
                            return {'success': True, 'cover': cover_data}
                    except Exception as e:
                        logger.warning(f"EpubParser.get_cover_image 失败: {e}")
                    break
            with zipfile.ZipFile(book.file_path, 'r') as zf:
                candidates = []
                for entry in zf.namelist():
                    el = entry.lower()
                    if el.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                        candidates.append(entry)
                for entry in candidates:
                    el = entry.lower()
                    if 'cover' in el or 'title' in el:
                        img_data = zf.read(entry)
                        if img_data and len(img_data) < _MAX_IMAGE_SIZE:
                            mime = mimetypes.guess_type(el)[0] or 'image/jpeg'
                            b64 = base64.b64encode(img_data).decode('ascii')
                            cover = f'data:{mime};base64,{b64}'
                            self._cover_cache[book_name] = cover
                            return {'success': True, 'cover': cover}
                for entry in candidates:
                    img_data = zf.read(entry)
                    if img_data and len(img_data) < _MAX_IMAGE_SIZE:
                        mime = mimetypes.guess_type(entry.lower())[0] or 'image/jpeg'
                        b64 = base64.b64encode(img_data).decode('ascii')
                        cover = f'data:{mime};base64,{b64}'
                        self._cover_cache[book_name] = cover
                        return {'success': True, 'cover': cover}
            self._cover_cache[book_name] = ''
            return {'success': False, 'cover': ''}
        except (OSError, KeyError):
            return {'success': False, 'cover': ''}

    # ── 统计 ──

    @handle_api_error(
        default_return={'total_books': 0, 'total_chapters': 0, 'reading_time': '0秒', 'progress_percent': 0, 'last_read_book': None, 'last_read_time': ''},
        error_message="获取统计数据失败"
    )
    def get_stats(self) -> Dict[str, Any]:
        if self._cached_stats_from_books is not None:
            total_books = self._cached_stats_from_books['total_books']
            total_chapters = self._cached_stats_from_books['total_chapters']
            progress_percent = self._cached_stats_from_books.get('progress_percent', 0)
        else:
            books = self._book_manager.get_all_books_list()
            total_books = len(books)
            total_chapters = sum((book.total_chapters or 0) for book in books if book.file_exists())
            # 缓存未命中时计算 progress_percent（缓存命中时已在 _serialize_books 算好）
            total_progress = 0
            books_with_progress = 0
            for book in books:
                try:
                    if book.file_exists() and (book.total_chapters or 0) > 0:
                        progress_data = self._data_store.get_progress(book.name)
                        if progress_data:
                            chapter = progress_data.get('chapter', 0)
                            total_progress += min(100, int((chapter + 1) / (book.total_chapters or 1) * 100))
                            books_with_progress += 1
                except Exception:
                    continue
            progress_percent = int(total_progress / books_with_progress) if books_with_progress > 0 else 0
        reading_time_display = self._data_store.get_reading_time_display()
        last_read_book = self._data_store.get_last_read_book()
        last_read_time = ''
        if last_read_book:
            progress_data = self._data_store.get_progress(last_read_book)
            if progress_data and progress_data.get('last_read'):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(progress_data['last_read'])
                    last_read_time = dt.strftime('%m-%d %H:%M')
                except (ValueError, TypeError):
                    last_read_time = progress_data['last_read']
        return {
            'total_books': total_books,
            'total_chapters': total_chapters,
            'reading_time': reading_time_display,
            'progress_percent': progress_percent,
            'last_read_book': last_read_book,
            'last_read_time': last_read_time,
        }

    @handle_api_error(
        default_return={'books': [], 'stats': {'total_books': 0, 'total_chapters': 0, 'reading_time': '0秒', 'progress_percent': 0, 'last_read_book': None, 'last_read_time': ''}},
        error_message="获取仪表盘数据失败"
    )
    def get_dashboard_data(self) -> Dict[str, Any]:
        books_list = self.get_books()
        stats = self.get_stats()
        return {'books': books_list, 'stats': stats}

    # ── 文件对话框 ──

    @handle_api_error(default_return=[], error_message="文件对话框错误")
    def open_file_dialog(self) -> List[str]:
        import webview
        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=(
                '支持格式 (*.txt;*.text;*.log;*.md;*.markdown;*.epub;*.mobi;*.pdb)',
                '文本文件 (*.txt;*.text;*.log)',
                'Markdown (*.md;*.markdown)',
                'EPUB (*.epub)',
                'MOBI (*.mobi;*.pdb)',
                '所有文件 (*.*)',
            ),
        )
        if not result:
            return []
        return list(result) if isinstance(result, (list, tuple)) else [result]

    def open_image_dialog(self, target: str = 'background') -> Dict[str, Any]:
        try:
            import hashlib
            import webview
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=(
                    '图片文件 (*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp)',
                    '所有文件 (*.*)',
                ),
            )
            if not result:
                return {'success': False, 'cancelled': True}
            source = result if isinstance(result, str) else result[0]
            if not os.path.isfile(source):
                return {'success': False, 'error': '图片文件不存在'}
            size = os.path.getsize(source)
            if size > _MAX_IMAGE_DATA_URL_SIZE:
                return {'success': False, 'error': '图片不能超过10MB'}
            extension = Path(source).suffix.lower()
            if extension not in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}:
                return {'success': False, 'error': '不支持的图片格式'}
            safe_target = target if target in {'home', 'reader', 'notes'} else 'background'
            digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()[:16]
            os.makedirs(self._dirs['imgs'], exist_ok=True)
            destination = os.path.join(self._dirs['imgs'], f'{safe_target}_{digest}{extension}')
            if os.path.abspath(source) != os.path.abspath(destination):
                shutil.copy2(source, destination)
            data_url = self.get_image_data_url(destination)
            if not data_url:
                with suppress(OSError):
                    if os.path.abspath(source) != os.path.abspath(destination):
                        os.remove(destination)
                return {'success': False, 'error': '图片读取失败'}
            return {'success': True, 'path': destination, 'data_url': data_url}
        except Exception as e:
            logger.error(f"图片对话框错误: {e}")
            return {'success': False, 'error': '选择图片失败'}

    def get_image_data_url(self, file_path: str) -> Optional[str]:
        try:
            if not os.path.isfile(file_path):
                return None
            if os.path.getsize(file_path) > _MAX_IMAGE_DATA_URL_SIZE:
                return None
            mime = mimetypes.guess_type(file_path)[0] or 'image/png'
            with open(file_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
            return f'data:{mime};base64,{data}'
        except Exception as e:
            logger.error(f"读取图片失败: {e}")
            return None

    # ── 书籍操作 ──

    def import_books(self, file_paths: List[str]) -> Dict[str, Any]:
        logger.info(f"导入 {len(file_paths)} 个文件")
        added_count = 0
        errors = []
        skipped = []
        for file_path in file_paths:
            try:
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    if file_size > _MAX_IMPORT_SIZE:
                        errors.append(f"{os.path.basename(file_path)}: 文件过大（{file_size // 1024 // 1024}MB），限制200MB")
                        continue
                    book_name = Path(file_path).stem
                    if self._book_manager.has_book(book_name):
                        skipped.append(os.path.basename(file_path))
                        errors.append(f"{os.path.basename(file_path)}: 书籍已存在（同名）")
                        continue
                    book = self._book_manager.import_book(file_path)
                    if book:
                        added_count += 1
                    else:
                        errors.append(f"{os.path.basename(file_path)}: 解析失败，格式可能不支持")
                else:
                    errors.append(f"{os.path.basename(file_path)}: 文件不存在")
            except UnicodeDecodeError:
                errors.append(f"{os.path.basename(file_path)}: 编码识别失败")
            except OSError as e:
                errors.append(f"{os.path.basename(file_path)}: {str(e)}")
            except Exception as e:
                logger.error(f"导入书籍异常 [{file_path}]: {type(e).__name__}: {e}")
                errors.append(f"{os.path.basename(file_path)}: 导入异常 {type(e).__name__}")
        if added_count > 0:
            self._save_immediate()
            self._invalidate_books_cache()
        return {'added': added_count, 'total': len(file_paths), 'errors': errors, 'skipped': skipped}

    def import_books_async(self, file_paths: List[str]) -> Dict[str, Any]:
        import uuid as _uuid
        task_id = str(_uuid.uuid4())[:8]

        def _do_import():
            try:
                result = self.import_books(file_paths)
                logger.info(f"异步导入完成 [{task_id}]: {result}")
                if self._window:
                    try:
                        self._window.evaluate_js(f"window.onImportComplete && window.onImportComplete('{task_id}', {json.dumps(result)})")
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"异步导入失败 [{task_id}]: {e}")

        threading.Thread(target=_do_import, daemon=True).start()
        return {'task_id': task_id, 'status': 'started', 'total': len(file_paths)}

    def import_book_from_content(self, filename: str, content_base64: str) -> Dict[str, Any]:
        try:
            if not _validate_book_name(Path(filename).stem):
                return {'added': 0, 'errors': [f"{filename}: 无效的文件名"], 'skipped': []}
            raw = base64.b64decode(content_base64)
            if len(raw) > _MAX_IMPORT_SIZE:
                return {'added': 0, 'errors': [f"{filename}: 文件过大，限制200MB"], 'skipped': []}
            safe_name = Path(filename).stem
            ext = Path(filename).suffix.lower()
            supported = {'.txt', '.text', '.log', '.md', '.markdown', '.epub', '.mobi', '.pdb'}
            if ext not in supported:
                return {'added': 0, 'errors': [f"{filename}: 不支持的格式"], 'skipped': []}
            if self._book_manager.has_book(safe_name):
                return {'added': 0, 'errors': [f"{filename}: 书籍已存在（同名）"], 'skipped': [filename]}
            
            # 使用 tempfile 创建临时文件，确保在函数结束时自动清理
            import tempfile
            with tempfile.NamedTemporaryFile(
                dir=self._dirs['books'],
                prefix='_drag_tmp_',
                suffix=ext,
                delete=False
            ) as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(raw)
            
            try:
                book = self._book_manager.import_book(tmp_path, book_name_override=safe_name)
            finally:
                # 确保临时文件被删除
                if os.path.isfile(tmp_path):
                    with suppress(OSError):
                        os.remove(tmp_path)
            
            if book:
                self._save_immediate()
                self._invalidate_books_cache()
                return {'added': 1, 'errors': [], 'skipped': []}
            return {'added': 0, 'errors': [f"{filename}: 解析失败"], 'skipped': []}
        except Exception as e:
            logger.error(f"拖放导入失败: {e}")
            return {'added': 0, 'errors': [f"{filename}: {e}"], 'skipped': []}

    def delete_book(self, book_name: str) -> bool:
        try:
            if not _validate_book_name(book_name):
                return False
            with self._engines_lock:
                if book_name in self._reading_engines:
                    return False
            with self._windows_lock:
                if book_name in self._reader_windows:
                    with suppress(Exception):
                        self._reader_windows[book_name].destroy()
                        del self._reader_windows[book_name]
            book = self._book_manager.get_book(book_name)
            if book and book.file_exists():
                abs_books_dir = os.path.abspath(self._dirs['books'])
                abs_file_path = os.path.abspath(book.file_path)
                if not abs_file_path.startswith(abs_books_dir + os.sep):
                    logger.warning(f"拒绝删除书架目录外的文件: {book.file_path}")
                    return False
                with suppress(OSError):
                    os.remove(book.file_path)
            if self._book_manager.remove_book(book_name):
                self._data_store.remove_progress(book_name)
                self._data_store.remove_book_bookmarks(book_name)
                self._cover_cache.pop(book_name, None)
                self._preview_cache.pop(book_name, None)
                # 清理搜索索引，避免 DB 残留膨胀 + 搜索返回已删书籍的无效结果
                with suppress(Exception):
                    self._search_index.remove_book(book_name)
                self._save_immediate()
                self._invalidate_books_cache()
                return True
            return False
        except Exception as e:
            logger.error(f"删除书籍失败: {e}")
            return False

    def clear_bookshelf(self) -> Dict[str, Any]:
        """清空整个书架：删除所有书籍文件 + 阅读进度 + 书签 + 搜索索引。

        Returns:
            {'success': bool, 'deleted_files': int, 'error': str}
        """
        try:
            # 1. 关闭所有阅读器窗口
            with self._windows_lock:
                for name, w in list(self._reader_windows.items()):
                    with suppress(Exception):
                        w.destroy()
                self._reader_windows.clear()

            # 2. 关闭所有阅读引擎，释放资源
            with self._engines_lock:
                engine_names = list(self._reading_engines.keys())
            for book_name in engine_names:
                with suppress(Exception):
                    engine = self._reading_engines.get(book_name)
                    if engine:
                        engine.chapter_parser.clear()
                with self._engines_lock:
                    self._reading_engines.pop(book_name, None)
                with suppress(Exception):
                    self._data_store.stop_reading_session(book_name)
            self._current_book = None

            # 3. 清空书籍物理文件 + books 表
            deleted_files = self._book_manager.clear_all_books(delete_files=True)

            # 4. 清空所有书签
            self._data_store.clear_all_bookmarks()

            # 5. 清空所有阅读进度
            self._data_store.clear_all_progress()

            # 6. 清空封面/预览缓存
            with suppress(Exception):
                self._cover_cache.clear()
                self._preview_cache.clear()

            # 7. 清空搜索索引
            with suppress(Exception):
                self._search_index.clear_all()

            # 8. 保存并失效书架缓存
            self._save_immediate()
            self._invalidate_books_cache()

            logger.info(f"书架已清空，删除物理文件 {deleted_files} 个")
            return {'success': True, 'deleted_files': deleted_files}
        except Exception as e:
            logger.error(f"清空书架失败: {e}")
            return {'success': False, 'deleted_files': 0, 'error': str(e)}

    def rename_book(self, old_name: str, new_name: str) -> Dict[str, Any]:
        try:
            if not _validate_book_name(old_name):
                return {'success': False, 'error': '无效的原书名'}
            if not new_name or not new_name.strip():
                return {'success': False, 'error': '新书名不能为空'}
            if len(new_name.strip()) > 100:
                return {'success': False, 'error': '新书名不能超过100个字符'}
            with self._engines_lock:
                if old_name in self._reading_engines:
                    return {'success': False, 'error': '书籍正在阅读中，无法重命名'}
            if self._book_manager.rename_book(old_name, new_name):
                old_progress = self._data_store.get_progress(old_name)
                if old_progress:
                    self._data_store.update_progress(new_name, old_progress['chapter'], old_progress['scroll_percent'])
                    self._data_store.remove_progress(old_name)
                old_bookmarks = self._data_store.get_bookmarks(old_name)
                if old_bookmarks:
                    for bm in old_bookmarks:
                        self._data_store.add_bookmark(new_name, bm)
                    self._data_store.remove_book_bookmarks(old_name)
                with self._windows_lock:
                    if old_name in self._reader_windows:
                        self._reader_windows[new_name] = self._reader_windows.pop(old_name)
                if old_name in self._preview_cache:
                    self._preview_cache[new_name] = self._preview_cache.pop(old_name)
                if old_name in self._cover_cache:
                    self._cover_cache[new_name] = self._cover_cache.pop(old_name)
                # 删除旧书名的搜索索引（FTS5 不支持 UPDATE 文档），新书名打开时自动重建
                with suppress(Exception):
                    self._search_index.remove_book(old_name)
                self._save_immediate()
                self._invalidate_books_cache()
                return {'success': True, 'new_name': new_name}
            return {'success': False, 'error': '重命名失败，名称可能已存在'}
        except Exception as e:
            logger.error(f"重命名书籍失败: {e}")
            return {'success': False, 'error': str(e)}

    def set_display_name(self, book_name: str, new_display_name: str) -> Dict[str, Any]:
        try:
            if not _validate_book_name(book_name):
                return {'success': False, 'error': '无效的书名'}
            if not new_display_name or not new_display_name.strip():
                return {'success': False, 'error': '显示名称不能为空'}
            if len(new_display_name) > 100:
                return {'success': False, 'error': '显示名称不能超过100个字符'}
            book = self._book_manager.get_book(book_name)
            if not book:
                return {'success': False, 'error': '书籍不存在'}
            clean_name = new_display_name.strip()
            if self._data_store.update_book(book_name, {'display_name': clean_name}):
                self._invalidate_books_cache()
                return {'success': True}
            return {'success': False, 'error': '更新失败'}
        except Exception as e:
            logger.error(f"设置显示名称失败: {e}")
            return {'success': False, 'error': str(e)}

    def open_book_directory(self, book_name: str) -> bool:
        try:
            book = self._book_manager.get_book(book_name)
            if book and book.file_exists():
                import subprocess
                normalized = os.path.normpath(book.file_path)
                if sys.platform == 'win32':
                    subprocess.Popen(['explorer', '/select,', normalized])
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', '-R', normalized])
                else:
                    subprocess.Popen(['xdg-open', os.path.dirname(normalized)])
                return True
            return False
        except Exception as e:
            logger.error(f"打开目录失败: {e}")
            return False
