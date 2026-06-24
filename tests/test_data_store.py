"""数据持久化测试

测试 DataStore 的核心逻辑。
"""
import os
import tempfile
import pytest

from src.core.data_store import DataStore
from src.models.book import Book
from src.models.bookmark import Bookmark


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def config_file(tmp_dir):
    return os.path.join(tmp_dir, 'test_config.toml')


@pytest.fixture
def store(config_file):
    s = DataStore(config_file)
    s.load()
    try:
        yield s
    finally:
        s.close()


class TestDataStore:
    def test_init(self, store):
        assert store.bookshelf is not None
        assert store.bookmark_manager is not None
        assert store.progress_manager is not None

    def test_default_settings(self, store):
        settings = store.get_all_settings()
        assert 'current_theme' in settings
        assert 'font_family' in settings
        assert 'font_size' in settings

    def test_get_setting(self, store):
        val = store.get_setting('font_size', 18)
        assert isinstance(val, (int, float))

    def test_set_setting(self, store):
        store.set_setting('test_key', 'test_value')
        assert store.get_setting('test_key') == 'test_value'

    def test_update_settings(self, store):
        store.update_settings({'a': 1, 'b': 2})
        assert store.get_setting('a') == 1
        assert store.get_setting('b') == 2

    def test_save_and_load(self, config_file):
        # 写入已知设置项
        s1 = DataStore(config_file)
        s1.load()
        s1.set_setting('font_size', 24)
        s1.save()
        s1.close()

        # 重新加载验证
        s2 = DataStore(config_file)
        s2.load()
        assert s2.get_setting('font_size') == 24
        s2.close()

    def test_shortcut_settings(self, store):
        shortcuts = store.get_shortcut_settings()
        assert 'scroll_up' in shortcuts
        assert 'scroll_down' in shortcuts

    def test_set_shortcut_settings(self, store):
        store.set_shortcut_settings({'scroll_up': 'W', 'scroll_down': 'S'})
        shortcuts = store.get_shortcut_settings()
        assert shortcuts['scroll_up'] == 'W'
        assert shortcuts['scroll_down'] == 'S'

    def test_reading_session(self, store):
        store.start_reading_session('test_book')
        sessions = store.get_active_sessions()
        assert 'test_book' in sessions
        store.stop_reading_session('test_book')
        sessions = store.get_active_sessions()
        assert 'test_book' not in sessions

    def test_reading_time_display(self, store):
        display = store.get_reading_time_display()
        assert isinstance(display, str)
        assert len(display) > 0

    def test_reset(self, store):
        store.set_setting('will_be_gone', True)
        store.reset()
        assert store.get_setting('will_be_gone') is None


class TestDataStoreBookmarks:
    def test_add_and_get_bookmark(self, store):
        bm = Bookmark(chapter=0, position=100, description='test')
        store.bookmark_manager.add_bookmark('my_book', bm)
        bookmarks = store.bookmark_manager.get_bookmarks('my_book')
        assert len(bookmarks) == 1
        assert bookmarks[0].description == 'test'

    def test_remove_bookmark(self, store):
        bm = Bookmark(chapter=0, position=100, description='to_remove')
        store.bookmark_manager.add_bookmark('my_book', bm)
        result = store.bookmark_manager.remove_bookmark('my_book', 0)
        assert result is True
        bookmarks = store.bookmark_manager.get_bookmarks('my_book')
        assert len(bookmarks) == 0


class TestDataStoreProgress:
    def test_update_and_get_progress(self, store):
        store.progress_manager.update_progress('test_book', 5, 50)
        progress = store.progress_manager.get_progress('test_book')
        assert progress.chapter == 5
        assert progress.scroll_percent == 50

    def test_has_progress(self, store):
        assert store.progress_manager.has_progress('nonexistent') is False
        store.progress_manager.update_progress('exists', 0, 0)
        assert store.progress_manager.has_progress('exists') is True

    def test_remove_progress(self, store):
        store.progress_manager.update_progress('to_remove', 0, 0)
        store.progress_manager.remove_progress('to_remove')
        assert store.progress_manager.has_progress('to_remove') is False
