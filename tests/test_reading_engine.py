"""阅读引擎测试

测试 ReadingEngine 的核心逻辑。
"""
import os
import tempfile
import pytest

from src.core.reading_engine import ReadingEngine
from src.models.book import Book


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_txt(tmp_dir):
    path = os.path.join(tmp_dir, 'engine_test.txt')
    content = "第一章 开始\n这是第一章内容。\n\n第二章 发展\n这是第二章内容。\n\n第三章 结局\n这是第三章内容。\n"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return path


@pytest.fixture
def sample_book(sample_txt):
    return Book(name='engine_test', file_path=sample_txt)


class TestReadingEngine:
    def test_init(self, tmp_dir):
        engine = ReadingEngine(cache_dir=tmp_dir)
        assert engine.is_loaded is False
        assert engine.chapter_count == 0

    def test_load_book(self, tmp_dir, sample_book):
        engine = ReadingEngine(cache_dir=tmp_dir)
        result = engine.load_book(sample_book)
        assert result is True
        assert engine.is_loaded is True
        assert engine.chapter_count > 0
        assert engine.current_book is sample_book

    def test_load_book_with_chapter(self, tmp_dir, sample_book):
        engine = ReadingEngine(cache_dir=tmp_dir)
        engine.load_book(sample_book, chapter=1)
        assert engine.current_chapter == 1

    def test_load_book_chapter_clamped(self, tmp_dir, sample_book):
        engine = ReadingEngine(cache_dir=tmp_dir)
        engine.load_book(sample_book, chapter=999)
        assert engine.current_chapter == engine.chapter_count - 1

    def test_get_chapter_content(self, tmp_dir, sample_book):
        engine = ReadingEngine(cache_dir=tmp_dir)
        engine.load_book(sample_book)
        content = engine.get_chapter_content(0)
        assert content is not None
        assert len(content) > 0

    def test_get_current_content(self, tmp_dir, sample_book):
        engine = ReadingEngine(cache_dir=tmp_dir)
        engine.load_book(sample_book)
        content = engine.get_current_content()
        assert content is not None

    def test_get_chapter_title(self, tmp_dir, sample_book):
        engine = ReadingEngine(cache_dir=tmp_dir)
        engine.load_book(sample_book)
        title = engine.get_chapter_title()
        assert isinstance(title, str)
        assert len(title) > 0

    def test_load_chapter(self, tmp_dir, sample_book):
        engine = ReadingEngine(cache_dir=tmp_dir)
        engine.load_book(sample_book)
        if engine.chapter_count > 1:
            result = engine.load_chapter(1)
            assert result is True
            assert engine.current_chapter == 1

    def test_load_chapter_invalid(self, tmp_dir, sample_book):
        engine = ReadingEngine(cache_dir=tmp_dir)
        engine.load_book(sample_book)
        assert engine.load_chapter(-1) is False
        assert engine.load_chapter(999) is False

    def test_load_chapter_not_loaded(self, tmp_dir):
        engine = ReadingEngine(cache_dir=tmp_dir)
        assert engine.load_chapter(0) is False
