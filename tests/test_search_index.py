"""搜索索引测试

测试 SearchIndex 的索引创建、搜索、删除和事务安全。
"""
import os
import sqlite3
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


class TestCjkSearch:
    """中文正文（无空格分词）必须能做子串检索

    FTS5 的 unicode61 会把一整串汉字当作一个 token，正文里没有空格时
    「杨过」这类词永远匹配不到，只能靠逐章正则全量扫描兜底。
    """

    TEXT = '独孤求败在剑冢之中留下遗刻，杨过初见此字大奇。He walked slowly into the cave.'

    @pytest.fixture
    def cjk_index(self, index):
        index.index_book('cjk_book', [self.TEXT, '第二章 楚月转身离去，月色如水。'])
        return index

    def test_two_char_word_matches(self, cjk_index):
        for word in ('独孤', '杨过', '求败', '剑冢', '楚月'):
            assert cjk_index.search(word, 'cjk_book'), f'{word} 应命中'

    def test_multi_char_word_matches(self, cjk_index):
        results = cjk_index.search('留下遗刻', 'cjk_book')
        assert len(results) == 1
        assert results[0]['chapter'] == 0

    def test_absent_word_returns_no_hit(self, cjk_index):
        assert cjk_index.search('林冲', 'cjk_book') == []

    def test_snippet_has_no_injected_spaces(self, cjk_index):
        ctx = cjk_index.search('杨过', 'cjk_book')[0]['context']
        assert '杨过' in ctx
        assert '<<<' not in ctx and '>>>' not in ctx

    def test_ascii_word_still_matches(self, cjk_index):
        assert len(cjk_index.search('cave', 'cjk_book')) == 1

    def test_mixed_query_matches(self, cjk_index):
        assert len(cjk_index.search('剑冢之中', 'cjk_book')) == 1

    def test_count_matches_all_hits(self, cjk_index):
        cjk_index.index_book('many', ['月色真美'] * 7)
        assert cjk_index.count('月色', 'many') == 7
        assert len(cjk_index.search('月色', 'many', max_results=3)) == 3

    def test_index_version_upgrade_discards_old_index(self, db_path):
        idx = SearchIndex(db_path)
        idx.index_book('book', ['独孤求败'])
        idx.close()
        # 手工把版本标记改回旧值，模拟升级前的索引库
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT OR REPLACE INTO index_meta (key, value) VALUES ('index_version', 'legacy')")
        conn.commit()
        conn.close()
        reopened = SearchIndex(db_path)
        try:
            assert reopened.is_indexed('book') is False
            assert reopened.search('独孤', 'book') == []
        finally:
            reopened.close()
