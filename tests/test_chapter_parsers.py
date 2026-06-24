"""章节解析器测试

测试 ChapterParser 和 BaseChapterParser 的核心逻辑。
"""
import os
import tempfile
import pytest

from src.core.chapter_parser import ChapterParser
from src.models.book import Book


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_txt(tmp_dir):
    """创建一个包含多章节的测试 TXT 文件"""
    path = os.path.join(tmp_dir, 'test_book.txt')
    content = "第一章 开始\n这是第一章内容。\n\n第二章 发展\n这是第二章内容。\n\n第三章 结局\n这是第三章内容。\n"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


@pytest.fixture
def sample_book(sample_txt):
    return Book(name='test_book', file_path=sample_txt)


# ── ChapterParser 测试 ──

class TestChapterParser:
    def test_init(self, tmp_dir):
        cp = ChapterParser(cache_dir=tmp_dir)
        assert cp.chapter_count == 0
        assert cp.chapters == []

    def test_load_book(self, tmp_dir, sample_book):
        cp = ChapterParser(cache_dir=tmp_dir)
        success, encoding = cp.load_book(sample_book)
        assert success is True
        assert cp.chapter_count > 0

    def test_get_chapter(self, tmp_dir, sample_book):
        cp = ChapterParser(cache_dir=tmp_dir)
        cp.load_book(sample_book)
        ch = cp.get_chapter(0)
        assert ch is not None
        assert len(ch) > 0

    def test_get_chapter_invalid_index(self, tmp_dir, sample_book):
        cp = ChapterParser(cache_dir=tmp_dir)
        cp.load_book(sample_book)
        assert cp.get_chapter(-1) is None
        assert cp.get_chapter(999) is None

    def test_get_chapter_html(self, tmp_dir, sample_book):
        cp = ChapterParser(cache_dir=tmp_dir)
        cp.load_book(sample_book)
        # TXT 文件默认无 HTML
        html = cp.get_chapter_html(0)
        assert isinstance(html, str)

    def test_set_chapter_html(self, tmp_dir, sample_book):
        cp = ChapterParser(cache_dir=tmp_dir)
        cp.load_book(sample_book)
        cp.set_chapter_html(0, '<p>custom</p>')
        assert cp.get_chapter_html(0) == '<p>custom</p>'

    def test_get_chapter_title(self, tmp_dir, sample_book):
        cp = ChapterParser(cache_dir=tmp_dir)
        cp.load_book(sample_book)
        title = cp.get_chapter_title(0)
        assert isinstance(title, str)
        assert len(title) > 0

    def test_get_chapter_word_count(self, tmp_dir, sample_book):
        cp = ChapterParser(cache_dir=tmp_dir)
        cp.load_book(sample_book)
        wc = cp.get_chapter_word_count(0)
        assert wc > 0

    def test_get_total_word_count(self, tmp_dir, sample_book):
        cp = ChapterParser(cache_dir=tmp_dir)
        cp.load_book(sample_book)
        total = cp.get_total_word_count()
        assert total > 0

    def test_clear(self, tmp_dir, sample_book):
        cp = ChapterParser(cache_dir=tmp_dir)
        cp.load_book(sample_book)
        assert cp.chapter_count > 0
        cp.clear()
        assert cp.chapter_count == 0

    def test_cache_save_and_load(self, tmp_dir, sample_book):
        """测试缓存保存和加载"""
        # 第一次加载，创建缓存
        cp1 = ChapterParser(cache_dir=tmp_dir)
        cp1.load_book(sample_book)
        count1 = cp1.chapter_count

        # 第二次加载，应从缓存读取
        cp2 = ChapterParser(cache_dir=tmp_dir)
        cp2.load_book(sample_book)
        assert cp2.chapter_count == count1

    def test_load_nonexistent_file(self, tmp_dir):
        cp = ChapterParser(cache_dir=tmp_dir)
        book = Book(name='missing', file_path='nonexistent.txt')
        success, msg = cp.load_book(book)
        assert success is False

    def test_chapters_property_returns_all(self, tmp_dir, sample_book):
        """访问 .chapters 属性应返回所有章节"""
        cp = ChapterParser(cache_dir=tmp_dir)
        cp.load_book(sample_book)
        chapters = cp.chapters
        assert len(chapters) == cp.chapter_count

    def test_public_api_complete(self, tmp_dir):
        """确保公共接口完整"""
        cp = ChapterParser(cache_dir=tmp_dir)
        public_attrs = {'chapter_count', 'chapters', 'get_chapter', 'get_chapter_html',
                        'set_chapter_html', 'get_chapter_title', 'get_chapter_word_count',
                        'get_cover_data', 'get_total_word_count', 'clear', 'load_book'}
        for attr in public_attrs:
            assert hasattr(cp, attr), f'ChapterParser missing: {attr}'
