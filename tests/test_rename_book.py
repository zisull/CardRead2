"""书籍重命名与级联删除测试

覆盖 DbStore/DataStore 的事务式 rename_book / remove_book / clear_all_books
与 BookManager.rename_book（物理文件 + 记录 + 书签/进度需一并迁移，失败需回滚）。
"""
import os
import tempfile
import pytest

from src.core.data_store import DataStore
from src.core.book_manager import BookManager


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def store(tmp_dir):
    s = DataStore(os.path.join(tmp_dir, 'test_config.toml'))
    s.load()
    try:
        yield s
    finally:
        s.close()


def _seed_book(store, name, file_path):
    store.add_book({'name': name, 'file_path': file_path, 'total_chapters': 5})
    store.add_bookmark(name, {'chapter': 1, 'position': 100, 'description': 'd1'})
    store.add_bookmark(name, {'chapter': 3, 'position': 250, 'description': 'd2'})
    store.update_progress(name, 2, 45)


class TestDbStoreRename:
    def test_migrates_bookmarks_and_progress(self, store):
        _seed_book(store, 'old', '/tmp/old.txt')
        assert store.rename_book('old', 'new', '/tmp/new.txt') is True

        assert store.get_book('old') is None
        book = store.get_book('new')
        assert book is not None
        assert book['file_path'] == '/tmp/new.txt'

        assert store.get_bookmarks('old') == []
        marks = store.get_bookmarks('new')
        assert len(marks) == 2
        assert {m['description'] for m in marks} == {'d1', 'd2'}

        assert store.get_progress('old') is None
        prog = store.get_progress('new')
        assert prog['chapter'] == 2
        assert prog['scroll_percent'] == 45

    def test_unknown_old_name_returns_false(self, store):
        _seed_book(store, 'old', '/tmp/old.txt')
        assert store.rename_book('missing', 'new', '/tmp/new.txt') is False
        assert store.get_book('old') is not None
        assert store.get_book('new') is None
        # 原数据未被波及
        assert len(store.get_bookmarks('old')) == 2

    def test_orphan_progress_under_target_name_is_replaced(self, store):
        _seed_book(store, 'old', '/tmp/old.txt')
        # 目标名残留孤儿进度行（无对应书籍记录）会撞主键，需被旧书的进度覆盖
        store.update_progress('new', 9, 99)
        assert store.rename_book('old', 'new', '/tmp/new.txt') is True
        assert store.get_progress('new')['chapter'] == 2
        assert store.get_progress('old') is None
        assert len(store.get_bookmarks('new')) == 2

    def test_duplicate_target_name_returns_false(self, store):
        _seed_book(store, 'old', '/tmp/old.txt')
        _seed_book(store, 'new', '/tmp/new.txt')
        assert store.rename_book('old', 'new', '/tmp/new2.txt') is False
        assert store.get_book('old') is not None
        assert len(store.get_bookmarks('old')) == 2


class TestCascadeDelete:
    """删书必须连带清掉书签与进度：外键约束未开启，级联由 DbStore 在同一事务里显式完成"""

    def test_remove_book_cascades(self, store):
        _seed_book(store, 'old', '/tmp/old.txt')
        assert store.remove_book('old') is True
        assert store.get_book('old') is None
        assert store.get_bookmarks('old') == []
        assert store.get_progress('old') is None

    def test_clear_all_books_cascades(self, store):
        _seed_book(store, 'a', '/tmp/a.txt')
        _seed_book(store, 'b', '/tmp/b.txt')
        assert store.clear_all_books() is True
        assert store.get_books() == []
        assert store.get_all_bookmarks() == {}
        assert store.get_all_progress() == {}

    def test_orphans_cleaned_on_open(self, tmp_dir):
        """历史版本留下的孤儿书签/进度（无对应书籍记录）在打开数据库时被清掉"""
        cfg = os.path.join(tmp_dir, 'orphan_config.toml')
        s = DataStore(cfg)
        s.load()
        s.add_book({'name': 'gone', 'file_path': '/tmp/gone.txt'})
        s.add_bookmark('gone', {'chapter': 0, 'position': 1, 'description': 'x'})
        s.update_progress('gone', 0, 10)
        conn = s.db_store._get_conn()
        conn.execute("DELETE FROM books WHERE name = 'gone'")  # 只删父行，模拟旧 bug
        conn.commit()
        assert s.get_bookmarks('gone') != []
        s.close()

        reopened = DataStore(cfg)
        reopened.load()
        try:
            assert reopened.get_bookmarks('gone') == []
            assert reopened.get_progress('gone') is None
        finally:
            reopened.close()


class _FailingStore:
    """模拟库内迁移失败的桩"""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, item):
        return getattr(self._real, item)

    def rename_book(self, old_name, new_name, new_file_path):
        return False


class TestBookManagerRename:
    def _make(self, tmp_dir, store, name='book'):
        books_dir = os.path.join(tmp_dir, 'books')
        os.makedirs(books_dir, exist_ok=True)
        path = os.path.join(books_dir, name + '.txt')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('第一章\n正文内容')
        _seed_book(store, name, path)
        return BookManager(books_dir=books_dir, data_store=store), path

    def test_happy_path_returns_effective_name(self, tmp_dir, store):
        manager, path = self._make(tmp_dir, store)
        assert manager.rename_book('book', '新名字') == '新名字'
        assert not os.path.exists(path)
        assert os.path.exists(os.path.join(manager.books_dir, '新名字.txt'))
        assert manager.get_book('新名字') is not None

    def test_illegal_characters_are_sanitized(self, tmp_dir, store):
        manager, _ = self._make(tmp_dir, store)
        # 返回值必须是清洗后的名字（API 层以此作为内存结构键）
        assert manager.rename_book('book', 'a<b>c') == 'a_b_c'
        assert manager.get_book('a_b_c') is not None
        assert manager.get_book('a<b>c') is None

    def test_existing_name_is_rejected(self, tmp_dir, store):
        manager, path = self._make(tmp_dir, store)
        store.add_book({'name': 'taken', 'file_path': '/tmp/taken.txt'})
        assert manager.rename_book('book', 'taken') is None
        assert os.path.exists(path)
        assert manager.get_book('book') is not None

    def test_same_name_is_rejected(self, tmp_dir, store):
        manager, _ = self._make(tmp_dir, store)
        assert manager.rename_book('book', 'book') is None

    def test_db_failure_rolls_back_physical_file(self, tmp_dir, store):
        manager, path = self._make(tmp_dir, store)
        manager.data_store = _FailingStore(store)
        assert manager.rename_book('book', 'renamed') is None
        # 文件必须回到原名，避免与库内记录指向不一致
        assert os.path.exists(path)
        assert not os.path.exists(os.path.join(manager.books_dir, 'renamed.txt'))
        assert manager.get_book('book') is not None
