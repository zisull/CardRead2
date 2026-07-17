"""数据持久化模块

负责配置数据和业务数据的读写。
- 基础配置（设置项）使用 TOML 格式存储
- 业务数据（书籍、书签、阅读进度、便签）使用 SQLite 数据库存储
"""
import os
import time
import threading
from typing import Dict, Any, List, Optional

from confull import Config
from loguru import logger

from src.core.db_store import DbStore
from src.models.bookmark import Bookmark
from src.models.reading_progress import ReadingProgress


class _BookmarkManagerAdapter:
    def __init__(self, store: 'DataStore'):
        self._store = store

    def add_bookmark(self, book_name: str, bookmark: Bookmark) -> None:
        self._store.add_bookmark(book_name, bookmark.to_dict())

    def get_bookmarks(self, book_name: str) -> List[Bookmark]:
        return [Bookmark.from_dict(item) for item in self._store.get_bookmarks(book_name)]

    def remove_bookmark(self, book_name: str, index: int) -> bool:
        return self._store.remove_bookmark(book_name, index)


class _ProgressManagerAdapter:
    def __init__(self, store: 'DataStore'):
        self._store = store

    def update_progress(self, book_name: str, chapter: int, scroll_percent: int) -> None:
        self._store.update_progress(book_name, chapter, scroll_percent)

    def get_progress(self, book_name: str) -> ReadingProgress:
        data = self._store.get_progress(book_name)
        return ReadingProgress.from_dict(data or {})

    def has_progress(self, book_name: str) -> bool:
        return self._store.get_progress(book_name) is not None

    def remove_progress(self, book_name: str) -> bool:
        return self._store.remove_progress(book_name)


class _BookshelfAdapter:
    def __init__(self, store: 'DataStore'):
        self._store = store

    def get_books(self) -> List[Dict[str, Any]]:
        return self._store.get_books()


class DataStore:
    """数据持久化管理器

    统一管理配置和业务数据的读写。
    - 配置项：TOML 文件
    - 业务数据：SQLite 数据库

    使用 threading.RLock 保护共享数据，支持多线程并发访问。

    Attributes:
        config_file: 配置文件路径
        db_store: 数据库存储管理器
    """

    def __init__(self, config_file: str, db_path: str = None):
        """初始化数据存储

        Args:
            config_file: 配置文件路径
            db_path: 数据库文件路径，默认与配置文件同目录
        """
        self.config_file = config_file
        self._config = Config(file=config_file, way='toml')
        self._lock = threading.RLock()

        # 初始化数据库
        if db_path is None:
            db_dir = os.path.dirname(config_file)
            db_path = os.path.join(db_dir, 'cardread.db')
        self.db_store = DbStore(db_path)

        self._settings: Dict[str, Any] = {}
        self._reading_time: int = 0
        self._last_session_time: float = 0
        self._active_sessions: Dict[str, float] = {}
        self.bookshelf = _BookshelfAdapter(self)
        self.bookmark_manager = _BookmarkManagerAdapter(self)
        self.progress_manager = _ProgressManagerAdapter(self)

    def load(self) -> None:
        """加载所有数据

        1. 从 TOML 加载配置
        2. 检查是否需要数据迁移
        3. 从数据库加载业务数据（通过各 API 模块）
        """
        raw = self._config.to_dict() if self._config else {}
        data = raw if isinstance(raw, dict) else {}

        # 加载设置
        self._load_settings(data)

        # 加载阅读时长
        self._reading_time = data.get('reading_time', 0)

        # 检查是否需要数据迁移（TOML 中有业务数据，数据库为空）
        self._check_and_migrate(data)

    def _check_and_migrate(self, toml_data: Dict[str, Any]) -> None:
        """检查并执行数据迁移

        如果 TOML 中有业务数据且数据库为空，则执行迁移。

        Args:
            toml_data: TOML 配置数据
        """
        # 检查 TOML 中是否有业务数据
        has_toml_data = (
            toml_data.get('bookshelf') or 
            toml_data.get('bookmarks') or 
            toml_data.get('reading_progress') or
            toml_data.get('notes')
        )
        
        if has_toml_data and not self.db_store.has_data():
            logger.info("检测到 TOML 中有业务数据，开始迁移到数据库...")
            if self.db_store.migrate_from_toml(toml_data):
                logger.info("数据迁移成功，清理 TOML 中的业务数据...")
                self._clean_toml_data()
            else:
                logger.error("数据迁移失败，将继续使用 TOML 数据")

    def _clean_toml_data(self) -> None:
        """清理 TOML 中的业务数据（迁移完成后）"""
        with self._lock:
            try:
                data = self._config.to_dict() if self._config else {}
                # 保留配置项，删除业务数据键
                keys_to_remove = {'bookshelf', 'bookmarks', 'reading_progress', 'notes'}
                cleaned = {k: v for k, v in data.items() if k not in keys_to_remove}
                self._config.set_data(cleaned)
                self._config.save()
                logger.info("TOML 业务数据已清理")
            except Exception as e:
                logger.warning(f"清理 TOML 业务数据失败: {e}")

    def save(self) -> bool:
        """保存配置数据到 TOML 文件

        业务数据由各 API 模块实时写入数据库，此处只保存配置。

        Returns:
            是否保存成功
        """
        with self._lock:
            data = {
                'reading_time': self._reading_time,
            }
            _RESERVED_KEYS = {'bookshelf', 'bookmarks', 'reading_progress', 'reading_time', 'notes'}
            safe_settings = {k: v for k, v in self._settings.items() if k not in _RESERVED_KEYS}
            data.update(safe_settings)

            try:
                self._config.set_data(data)
                self._config.save()
                return True
            except Exception as e:
                logger.error(f"保存配置失败: {e}")
                return False

    def reset(self) -> None:
        """重置所有数据，清空配置文件和数据库"""
        with self._lock:
            self._config.del_clean()
            self._config = Config(file=self.config_file, way='toml')

            self.db_store.close()
            db_path = self.db_store.db_path
            if os.path.exists(db_path):
                for suffix in ('', '-wal', '-shm'):
                    target = db_path + suffix if suffix else db_path
                    if os.path.exists(target):
                        for _ in range(50):
                            try:
                                os.remove(target)
                                break
                            except PermissionError:
                                time.sleep(0.1)
                        if os.path.exists(target):
                            raise PermissionError(f"无法删除数据库文件: {target}")
            self.db_store = DbStore(db_path)

            self._settings = {}
            self._reading_time = 0
            self._last_session_time = 0
            self._active_sessions.clear()

    def close(self) -> None:
        """关闭数据存储，释放资源"""
        self.save()
        self.db_store.close()

    def __del__(self):
        try:
            self.db_store.close()
        except Exception:
            pass

    def _load_settings(self, data: Dict[str, Any]) -> None:
        """加载设置项

        以 config.DEFAULT_SETTINGS 为基线，用文件加载的数据覆盖，避免默认值散落多处。

        Args:
            data: 配置数据字典
        """
        from src.config import DEFAULT_SETTINGS
        # 以 DEFAULT_SETTINGS 为基线，确保所有默认值集中管理
        self._settings = dict(DEFAULT_SETTINGS)
        # 补充 DEFAULT_SETTINGS 未覆盖的设置项
        self._settings.update({
            'page_turn_mode': data.get('page_turn_mode', 'none'),
            'page_turn_speed': data.get('page_turn_speed', 200),
            'nav_auto_hide': data.get('nav_auto_hide', False),
            'background_image_path': data.get('background_image_path', None),
            'background_image_opacity': data.get('background_image_opacity', 0.3),
            'background_image_scale_mode': data.get('background_image_scale_mode', 'cover'),
            'books_dir': data.get('books_dir', ''),
            'shortcut_scroll_up': data.get('shortcut_scroll_up', 'Up'),
            'shortcut_scroll_down': data.get('shortcut_scroll_down', 'Down'),
            'shortcut_scroll_lines': data.get('shortcut_scroll_lines', 5),
            'shortcut_prev_chapter': data.get('shortcut_prev_chapter', 'Ctrl+Up'),
            'shortcut_next_chapter': data.get('shortcut_next_chapter', 'Ctrl+Down'),
        })
        reserved_keys = {'bookshelf', 'bookmarks', 'reading_progress', 'reading_time', 'notes'}
        self._settings.update({k: v for k, v in data.items() if k not in reserved_keys})

    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取设置项

        Args:
            key: 设置键名
            default: 默认值

        Returns:
            设置值
        """
        return self._settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """设置配置项

        Args:
            key: 设置键名
            value: 设置值
        """
        with self._lock:
            self._settings[key] = value

    def update_settings(self, settings: Dict[str, Any]) -> None:
        """批量更新设置

        Args:
            settings: 设置字典
        """
        with self._lock:
            self._settings.update(settings)

    def get_all_settings(self) -> Dict[str, Any]:
        """获取所有设置

        Returns:
            设置字典
        """
        return self._settings.copy()

    def get_shortcut_settings(self) -> Dict[str, Any]:
        """获取快捷键设置

        Returns:
            快捷键设置字典
        """
        return {
            'scroll_up': self._settings.get('shortcut_scroll_up', 'Up'),
            'scroll_down': self._settings.get('shortcut_scroll_down', 'Down'),
            'scroll_lines': self._settings.get('shortcut_scroll_lines', 5),
            'prev_chapter': self._settings.get('shortcut_prev_chapter', 'Ctrl+Up'),
            'next_chapter': self._settings.get('shortcut_next_chapter', 'Ctrl+Down'),
        }

    def set_shortcut_settings(self, shortcuts: Dict[str, Any]) -> None:
        """保存快捷键设置

        Args:
            shortcuts: 快捷键设置字典
        """
        self._settings['shortcut_scroll_up'] = shortcuts.get('scroll_up', 'Up')
        self._settings['shortcut_scroll_down'] = shortcuts.get('scroll_down', 'Down')
        self._settings['shortcut_scroll_lines'] = shortcuts.get('scroll_lines', 5)
        self._settings['shortcut_prev_chapter'] = shortcuts.get('prev_chapter', 'Ctrl+Up')
        self._settings['shortcut_next_chapter'] = shortcuts.get('next_chapter', 'Ctrl+Down')

    def start_reading_session(self, book_name: str = None) -> None:
        with self._lock:
            if book_name:
                self._active_sessions[book_name] = time.time()
            else:
                self._last_session_time = time.time()

    def stop_reading_session(self, book_name: str = None) -> None:
        with self._lock:
            if book_name and book_name in self._active_sessions:
                elapsed = round(time.time() - self._active_sessions.pop(book_name))
                self._reading_time += max(1, elapsed)
            elif not book_name and self._last_session_time > 0:
                elapsed = round(time.time() - self._last_session_time)
                self._reading_time += max(1, elapsed)
                self._last_session_time = 0

    def get_active_sessions(self) -> Dict[str, float]:
        """获取活跃阅读会话

        Returns:
            活跃会话字典 {book_name: start_time}
        """
        return self._active_sessions.copy()

    def get_reading_time_display(self) -> str:
        """获取格式化的阅读时长显示"""
        total_seconds = self._reading_time
        if total_seconds < 60:
            return f"{total_seconds}秒"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes}分钟"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if minutes > 0:
                return f"{hours}小时{minutes}分"
            return f"{hours}小时"

    # ==================== 书籍操作（代理到 db_store） ====================

    def get_books(self) -> List[Dict[str, Any]]:
        """获取所有书籍"""
        return self.db_store.get_books()

    def get_book(self, name: str) -> Optional[Dict[str, Any]]:
        """获取指定书籍"""
        return self.db_store.get_book(name)

    def add_book(self, book_data: Dict[str, Any]) -> bool:
        """添加书籍"""
        return self.db_store.add_book(book_data)

    def update_book(self, name: str, updates: Dict[str, Any]) -> bool:
        """更新书籍信息"""
        return self.db_store.update_book(name, updates)

    def remove_book(self, name: str) -> bool:
        """移除书籍及其相关数据"""
        return self.db_store.remove_book(name)

    def clear_all_books(self) -> bool:
        """清空所有书籍记录（不级联清理进度/书签，调用方需自行处理）"""
        return self.db_store.clear_all_books()

    def has_book(self, name: str) -> bool:
        """检查书籍是否存在"""
        return self.db_store.has_book(name)

    # ==================== 书签操作（代理到 db_store） ====================

    def get_bookmarks(self, book_name: str) -> List[Dict[str, Any]]:
        """获取书籍的所有书签"""
        return self.db_store.get_bookmarks(book_name)

    def get_all_bookmarks(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有书签，按书籍分组"""
        return self.db_store.get_all_bookmarks()

    def add_bookmark(self, book_name: str, bookmark_data: Dict[str, Any]) -> bool:
        """添加书签"""
        return self.db_store.add_bookmark(book_name, bookmark_data)

    def update_bookmark(self, book_name: str, index: int, description: str) -> bool:
        """更新书签描述"""
        return self.db_store.update_bookmark(book_name, index, description)

    def remove_bookmark(self, book_name: str, index: int) -> bool:
        """移除书签"""
        return self.db_store.remove_bookmark(book_name, index)

    def remove_book_bookmarks(self, book_name: str) -> bool:
        """移除书籍的所有书签"""
        return self.db_store.remove_book_bookmarks(book_name)

    def clear_all_bookmarks(self) -> bool:
        """清空所有书签"""
        return self.db_store.clear_all_bookmarks()

    def count_bookmarks(self, book_name: Optional[str] = None) -> int:
        """统计书签数量"""
        return self.db_store.count_bookmarks(book_name)

    def get_bookmark_book_names(self) -> List[str]:
        """获取有书签的书籍名称"""
        return self.db_store.get_bookmark_book_names()

    # ==================== 阅读进度操作（代理到 db_store） ====================

    def get_progress(self, book_name: str) -> Optional[Dict[str, Any]]:
        """获取书籍的阅读进度"""
        return self.db_store.get_progress(book_name)

    def get_all_progress(self) -> Dict[str, Dict[str, Any]]:
        """获取所有阅读进度"""
        return self.db_store.get_all_progress()

    def update_progress(self, book_name: str, chapter: int, scroll_percent: int) -> bool:
        """更新阅读进度"""
        return self.db_store.update_progress(book_name, chapter, scroll_percent)

    def remove_progress(self, book_name: str) -> bool:
        """移除阅读进度"""
        return self.db_store.remove_progress(book_name)

    def clear_all_progress(self) -> bool:
        """清空所有阅读进度"""
        return self.db_store.clear_all_progress()

    def get_last_read_book(self) -> Optional[str]:
        """获取最近阅读的书籍"""
        return self.db_store.get_last_read_book()

    # ==================== 便签操作（代理到 db_store） ====================

    def get_notes(self) -> List[Dict[str, Any]]:
        """获取所有便签"""
        return self.db_store.get_notes()

    def get_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        """获取指定便签"""
        return self.db_store.get_note(note_id)

    def add_note(self, note_data: Dict[str, Any]) -> bool:
        """添加便签"""
        return self.db_store.add_note(note_data)

    def update_note(self, note_id: str, updates: Dict[str, Any]) -> bool:
        """更新便签"""
        return self.db_store.update_note(note_id, updates)

    def remove_note(self, note_id: str) -> bool:
        """移除便签"""
        return self.db_store.remove_note(note_id)

    def remove_notes(self, note_ids: List[str]) -> int:
        """批量移除便签"""
        return self.db_store.remove_notes(note_ids)

    def clear_notes(self) -> bool:
        """清空所有便签"""
        return self.db_store.clear_notes()

    def search_notes(self, query: str) -> List[Dict[str, Any]]:
        """搜索便签"""
        return self.db_store.search_notes(query)
