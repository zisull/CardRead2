"""pywebview API 模块

提供 JavaScript 可调用的 Python 接口。
通过 Mixin 拆分为：书架(api_books)、阅读(api_reader)、主题(api_themes)、窗口(api_windows)。
"""
import os
import threading
from typing import Any, Dict, List, Optional

from loguru import logger

from src.core.book_manager import BookManager
from src.core.data_store import DataStore
from src.core.reading_engine import ReadingEngine
from src.core.search_index import SearchIndex
from src.themes.theme_manager import ThemeManager
from src.utils.file_utils import get_appdata_dir, get_resource_dirs, ensure_dirs_exist, get_bundle_base_path
from src.utils.lru_cache import LRUCache
from src.web.api_helpers import AVAILABLE_LAYOUTS, LAYOUTS_META  # 保留供外部引用
from src.web.api_books import BooksMixin
from src.web.api_notes import NotesMixin
from src.web.api_reader import ReaderMixin
from src.web.api_themes import ThemesMixin
from src.web.api_windows import WindowsMixin

from src.config import PREVIEW_CACHE_CAPACITY, COVER_CACHE_CAPACITY


class Api(BooksMixin, NotesMixin, ReaderMixin, ThemesMixin, WindowsMixin):
    """pywebview API 类

    所有公共方法都可以被 JavaScript 调用。
    调用方式: await window.pywebview.api.method_name(args)

    方法按职责拆分到五个 Mixin：
    - BooksMixin:   书架列表、封面、统计、导入/删除/重命名
    - NotesMixin:   便签增删改查、编辑窗口、桌面展示窗口
    - ReaderMixin:  打开书籍、章节导航、搜索、书签
    - ThemesMixin:  主题管理、自定义配色、布局、设置
    - WindowsMixin: 窗口控制、日志、应用信息
    """

    def __init__(self):
        self._window = None
        self._reader_windows: Dict[str, Any] = {}

        self._appdata_dir = get_appdata_dir()
        self._dirs = get_resource_dirs(self._appdata_dir)
        self._dirs['books'] = os.path.join(self._appdata_dir, 'book')
        self._dirs['cache'] = os.path.join(self._appdata_dir, 'cache')
        ensure_dirs_exist(self._dirs)

        self._data_store = DataStore(os.path.join(self._dirs['style'], 'read_config.toml'))
        self._data_store.load()

        self._book_manager = BookManager(self._dirs['books'], data_store=self._data_store)
        self._theme_manager = ThemeManager(self._dirs['theme'])

        self._reading_engines: Dict[str, ReadingEngine] = {}
        self._engines_lock = threading.RLock()
        self._windows_lock = threading.RLock()
        self._current_book: Optional[str] = None
        self._is_maximized = False
        self._preview_cache: LRUCache[List[Dict[str, str]]] = LRUCache(capacity=PREVIEW_CACHE_CAPACITY)

        self._save_timer: Optional[threading.Timer] = None
        self._save_lock = threading.RLock()

        self._books_cache: Optional[List[Dict[str, Any]]] = None
        self._books_cache_dirty = True
        self._cached_stats_from_books: Optional[Dict[str, Any]] = None
        self._cover_cache: LRUCache[str] = LRUCache(capacity=COVER_CACHE_CAPACITY)
        self._all_themes_cache: Optional[List[Dict[str, Any]]] = None

        # 初始化搜索索引
        search_index_path = os.path.join(self._appdata_dir, 'search_index.db')
        self._search_index = SearchIndex(search_index_path)

        self._init_notes()

        self._load_data()

    def _load_data(self) -> None:
        """加载初始数据"""
        try:
            bookshelf_count = len(self._book_manager.get_all_books_list())
            new_count = self._book_manager.scan_books_directory()
            if new_count > 0:
                self._save_immediate()
                self._books_cache_dirty = True
            elif bookshelf_count == 0:
                logger.warning("书架为空且扫描未发现书籍")
        except Exception as e:
            logger.error(f"扫描书籍失败: {e}")

        settings = self._data_store.get_all_settings()
        saved_theme = settings.get('current_theme', '深渊')
        if saved_theme.startswith('ct_'):
            self._ensure_custom_theme_in_core(saved_theme)
        self._theme_manager.current_theme = saved_theme

        if not settings.get('home_bg_image'):
            default_bg = self._get_default_bg_path()
            if default_bg:
                self._data_store.set_setting('home_bg_image', default_bg)
                self._data_store.set_setting('home_bg_opacity', 0.10)
                self._data_store.set_setting('reader_bg_image', default_bg)
                self._data_store.set_setting('reader_bg_opacity', 0.08)
                self._data_store.set_setting('notes_bg_image', default_bg)
                self._data_store.set_setting('notes_bg_opacity', 0.08)
                self._save_immediate()

    def _get_default_bg_path(self) -> Optional[str]:
        try:
            base = get_bundle_base_path(__file__)
            path = os.path.join(base, 'static', 'assets', 'default_bg.jpg')
            if os.path.isfile(path):
                return os.path.abspath(path)
        except OSError:
            pass
        return None

    def _get_theme_colors(self) -> Dict[str, Any]:
        theme = self._theme_manager.get_current_theme()
        all_settings = self._data_store.get_all_settings()
        font_color = all_settings.get('font_color', theme.get('font_color', theme.get('fg', '#4a4030')))
        return {
            'fg': theme.get('fg', '#4a4030'),
            'accent': theme.get('accent', '#b09050'),
            'accent2': theme.get('accent2', '#b98dff'),
            'secondary': theme.get('secondary', '#f5efe2'),
            'card_bg': theme.get('card_bg', '#f9f2e7'),
            'border': theme.get('border', '#e0d5c0'),
            'tip': theme.get('tip', '#888070'),
            'font_color': font_color,
            'code_bg': theme.get('code_bg', theme.get('secondary', '#f5efe2')),
            'code_color': theme.get('code_color', font_color),
            'highlight': theme.get('highlight', 'rgba(176,144,80,0.12)'),
            'bg': theme.get('bg', '#f5eed8'),
        }

    # ── 数据保存（延迟写入） ──

    def _save_immediate(self) -> None:
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
                self._save_timer = None
            try:
                self._data_store.save()
            except Exception as e:
                logger.error(f"保存数据失败: {e}")

    def _save_deferred(self, delay: float = 5.0):
        """延迟保存数据（防抖）"""
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(delay, self._save_immediate)
            self._save_timer.daemon = True
            self._save_timer.start()
