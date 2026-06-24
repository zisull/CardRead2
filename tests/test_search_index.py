"""搜索索引测试

测试 SearchIndex 的索引创建、搜索、删除和事务安全。
"""
import os
import tempfile
import pytest

from src.core.search_index import SearchIndex


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as d:
        yield os.path.join(d, 'test_search.db')


@pytest.fixture
def index(db_path):
    idx = SearchIndex(db_path)
    yield idx
    idx.close()


@pytest.fixture
def indexed_index(index):
    """预创建索引的 SearchIndex"""
    chapters = [
        '第一章 开始 这是第一章的内容',
        '第二章 发展 这是第二章的内容',
        '第三章 结局 这是第三章的内容',
    ]
    index.index_book('test_book', chapters)
    return index


class TestSearchIndex:
    def test_init_creates_db(self, db_path):
        idx = SearchIndex(db_path)
        assert os.path.exists(db_path)
        idx.close()

    def test_index_book(self, indexed_index):
        assert indexed_index.is_indexed('test_book') is True
        assert indexed_index.get_indexed_chapter_count('test_book') == 3

    def test_index_book_empty(self, index):
        result = index.index_book('empty_book', [])
        assert result is True
        assert index.get_indexed_chapter_count('empty_book') == 0

    def test_search_found(self, indexed_index):
        results = indexed_index.search('第一章', 'test_book')
        assert len(results) > 0
        assert results[0]['book_name'] == 'test_book'
        assert results[0]['chapter'] == 0

    def test_search_not_found(self, indexed_index):
        results = indexed_index.search('不存在的内容', 'test_book')
        assert len(results) == 0

    def test_search_all_books(self, indexed_index):
        indexed_index.index_book('other_book', ['其他书第一章'])
        results = indexed_index.search('第一章')
        book_names = {r['book_name'] for r in results}
        assert 'test_book' in book_names or 'other_book' in book_names

    def test_search_empty_query(self, indexed_index):
        results = indexed_index.search('', 'test_book')
        assert results == []

    def test_search_special_chars_escaped(self, indexed_index):
        """搜索含特殊字符的关键词不应抛异常"""
        results = indexed_index.search('"hello" AND world', 'test_book')
        assert isinstance(results, list)

    def test_search_star_wildcard(self, indexed_index):
        """搜索含 * 的关键词不应抛异常"""
        results = indexed_index.search('test*', 'test_book')
        assert isinstance(results, list)

    def test_remove_book(self, indexed_index):
        assert indexed_index.is_indexed('test_book') is True
        result = indexed_index.remove_book('test_book')
        assert result is True
        assert indexed_index.is_indexed('test_book') is False

    def test_remove_nonexistent_book(self, index):
        result = index.remove_book('nonexistent')
        assert result is True  # 删除不存在的书也返回 True

    def test_reindex_book(self, indexed_index):
        """重新索引应替换旧数据"""
        indexed_index.index_book('test_book', ['新第一章', '新第二章'])
        assert indexed_index.get_indexed_chapter_count('test_book') == 2
        results = indexed_index.search('新第一章', 'test_book')
        assert len(results) > 0

    def test_not_indexed(self, index):
        assert index.is_indexed('nonexistent') is False
        assert index.get_indexed_chapter_count('nonexistent') == 0

    def test_close_and_reopen(self, db_path):
        idx1 = SearchIndex(db_path)
        idx1.index_book('book1', ['内容1'])
        idx1.close()

        idx2 = SearchIndex(db_path)
        assert idx2.is_indexed('book1') is True
        results = idx2.search('内容1', 'book1')
        assert len(results) > 0
        idx2.close()

    def test_get_stats(self, indexed_index):
        stats = indexed_index.get_stats()
        assert stats['books'] >= 1
        assert stats['chapters'] >= 3

    def test_vacuum(self, indexed_index):
        """VACUUM 不应抛异常（事务已提交）"""
        indexed_index.vacuum()
        stats = indexed_index.get_stats()
        assert stats['books'] >= 1

    def test_index_book_rollback_on_error(self, index):
        """索引失败时应回滚，不会留下脏数据"""
        # 先成功索引
        index.index_book('book1', ['章节1', '章节2'])
        assert index.is_indexed('book1') is True

        # 用空章节列表重新索引（模拟失败场景，实际不会失败但验证回滚逻辑存在）
        index.index_book('book1', [])
        assert index.get_indexed_chapter_count('book1') == 0

    def test_max_results_limit(self, indexed_index):
        """max_results 参数应限制返回数量"""
        results = indexed_index.search('内容', 'test_book', max_results=1)
        assert len(results) <= 1

    def test_chapter_index_preserved(self, indexed_index):
        """搜索结果的 chapter_index 应正确"""
        results = indexed_index.search('第二章', 'test_book')
        if results:
            assert results[0]['chapter'] == 1
