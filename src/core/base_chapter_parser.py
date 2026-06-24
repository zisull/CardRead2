"""章节解析器基类

提取 ChapterParser 的公共逻辑，消除代码重复。
"""
import gzip
import hashlib
import json
import os
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from loguru import logger

from src.models.book import Book
from src.parsers.parser_factory import get_parser_for_file
from src.parsers.md_parser import MarkdownParser
from src.parsers.txt_parser import TxtParser
from src.parsers.epub_parser import EpubParser
from src.utils.encoding import EncodingDetector
from src.utils.text_parser import TextParser


class BaseChapterParser(ABC):
    """章节解析器基类

    公共职责：
    - 缓存路径计算与磁盘缓存读写
    - 书籍加载流程（解析器选择、缓存命中判断、纯文本回退）
    - HTML 重新生成、标题/字数/封面查询
    - 清理资源

    子类只需实现章节存储策略（全量列表 vs 懒加载字典）。
    """

    def __init__(self, cache_dir: str = None):
        self._encoding_detector = EncodingDetector()
        self._chapter_titles: List[str] = []
        self._current_book: Optional[Book] = None
        self._cached_parser = None
        self._cached_result = None
        self._last_colors: Optional[dict] = None
        self._cache_dir = cache_dir
        self._pending_colors: Optional[dict] = None
        self._cover_data: str = ""
        self._total_word_count: Optional[int] = None
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    # ── 抽象属性/方法 ──

    @property
    @abstractmethod
    def chapter_count(self) -> int:
        """章节数量"""
        ...

    @property
    @abstractmethod
    def chapters(self) -> List[str]:
        """所有章节（兼容接口）"""
        ...

    @abstractmethod
    def get_chapter(self, index: int) -> Optional[str]:
        """获取指定章节内容"""
        ...

    @abstractmethod
    def get_chapter_html(self, index: int) -> str:
        """获取指定章节 HTML"""
        ...

    @abstractmethod
    def set_chapter_html(self, index: int, html: str) -> None:
        """设置章节 HTML"""
        ...

    @abstractmethod
    def _on_book_loaded(self, book: Book, chapters: List[str], html: List[str],
                        titles: List[str], cover: str) -> None:
        """子类在书籍加载完成后存储章节数据"""
        ...

    @abstractmethod
    def _get_chapters_for_cache(self) -> List[str]:
        """返回用于缓存保存的章节列表"""
        ...

    @abstractmethod
    def _get_html_for_cache(self) -> List[str]:
        """返回用于缓存保存的 HTML 列表"""
        ...

    @abstractmethod
    def _clear_chapter_data(self) -> None:
        """清除子类特有的章节数据"""
        ...

    # ── 公共缓存逻辑 ──

    def _get_cache_path(self, file_path: str) -> Optional[str]:
        if not self._cache_dir:
            return None
        h = hashlib.md5(os.path.abspath(file_path).encode()).hexdigest()[:12]
        name = os.path.splitext(os.path.basename(file_path))[0]
        return os.path.join(self._cache_dir, f'{name}_{h}.cache.gz')

    def _load_from_cache(self, file_path: str) -> Optional[Tuple[List[str], List[str], List[str], str]]:
        cache_path = self._get_cache_path(file_path)
        if not cache_path or not os.path.exists(cache_path):
            return None
        try:
            mtime = os.path.getmtime(file_path)
            with gzip.open(cache_path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('mtime') != mtime or data.get('size') != os.path.getsize(file_path):
                return None
            return data['chapters'], data['html'], data['titles'], data.get('encoding', 'utf-8')
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"缓存文件格式错误: {cache_path}: {e}")
            return None
        except (OSError, IOError) as e:
            logger.warning(f"缓存文件读取失败: {cache_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"缓存加载异常: {cache_path}: {type(e).__name__}: {e}")
            return None

    def _save_to_cache(self, file_path: str, encoding: str):
        cache_path = self._get_cache_path(file_path)
        if not cache_path:
            return
        chapters = self._get_chapters_for_cache()
        if not chapters:
            return
        try:
            data = {
                'mtime': os.path.getmtime(file_path),
                'size': os.path.getsize(file_path),
                'encoding': encoding,
                'chapters': chapters,
                'html': self._get_html_for_cache(),
                'titles': self._chapter_titles,
            }
            with gzip.open(cache_path, 'wt', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except (OSError, IOError) as e:
            logger.warning(f"缓存文件写入失败: {cache_path}: {e}")
        except Exception as e:
            logger.error(f"缓存保存异常: {cache_path}: {type(e).__name__}: {e}")

    # ── 公共书籍加载流程 ──

    def load_book(self, book: Book, theme_colors: dict = None) -> Tuple[bool, str]:
        if not book.file_exists():
            return False, "文件不存在"

        try:
            parser = get_parser_for_file(book.file_path)
            if parser:
                need_colors = isinstance(parser, (MarkdownParser, TxtParser, EpubParser))

                if (self._cached_parser is parser and
                    self._current_book and
                    self._current_book.file_path == book.file_path and
                    self._last_colors == theme_colors):
                    return True, self._current_book.current_encoding or 'utf-8'

                if (self._cached_result is not None and
                    self._current_book and
                    self._current_book.file_path == book.file_path and
                    need_colors and theme_colors):
                    self._last_colors = theme_colors
                    self._pending_colors = theme_colors
                    return True, self._current_book.current_encoding or 'utf-8'

                disk_cache = self._load_from_cache(book.file_path)
                if disk_cache:
                    chapters, html, titles, encoding = disk_cache
                    self._current_book = book
                    self._current_book.current_encoding = encoding
                    self._chapter_titles = titles
                    self._cached_parser = parser
                    self._last_colors = theme_colors
                    self._on_book_loaded(book, chapters, html, titles, "")
                    logger.debug(f"从磁盘缓存加载: {book.file_path}")
                    return True, encoding or 'utf-8'

                if need_colors and theme_colors:
                    result = parser.parse(book.file_path, colors=theme_colors)
                else:
                    result = parser.parse(book.file_path)

                self._cached_parser = parser
                self._cached_result = result
                self._last_colors = theme_colors
                self._current_book = book
                self._current_book.current_encoding = result.encoding
                self._chapter_titles = [ch.title for ch in result.chapters]
                self._cover_data = result.cover_data or ""

                chapters = [ch.content for ch in result.chapters]
                html = [ch.html_content for ch in result.chapters]
                self._on_book_loaded(book, chapters, html, self._chapter_titles, self._cover_data)
                self._save_to_cache(book.file_path, result.encoding)
            else:
                disk_cache = self._load_from_cache(book.file_path)
                if disk_cache:
                    chapters, html, titles, encoding = disk_cache
                    self._current_book = book
                    self._current_book.current_encoding = encoding
                    self._chapter_titles = titles
                    self._on_book_loaded(book, chapters, html, titles, "")
                    logger.debug(f"从磁盘缓存加载: {book.file_path}")
                    return True, encoding or 'utf-8'

                content, encoding = self._encoding_detector.read_file(book.file_path)
                self._current_book = book
                self._current_book.current_encoding = encoding
                chapters = TextParser.parse_chapters(content)
                html = [''] * len(chapters)
                titles = [''] * len(chapters)
                self._chapter_titles = titles
                self._on_book_loaded(book, chapters, html, titles, "")
                self._save_to_cache(book.file_path, encoding)

            return True, self._current_book.current_encoding or 'utf-8'

        except Exception as e:
            self.clear()
            return False, str(e)

    # ── 公共查询方法 ──

    def _regenerate_html(self, chapter_data, colors: dict) -> str:
        if not hasattr(chapter_data, 'html_content') or not chapter_data.html_content:
            return ''

        if self._cached_parser and isinstance(self._cached_parser, MarkdownParser):
            content_for_md = getattr(chapter_data, 'raw_md', '') or chapter_data.content
            return self._cached_parser._md_to_html(content_for_md, colors)

        if self._cached_parser and isinstance(self._cached_parser, TxtParser):
            return self._cached_parser._txt_to_html(chapter_data.content, '', colors)

        if self._cached_parser and isinstance(self._cached_parser, EpubParser):
            return chapter_data.html_content

        return chapter_data.html_content

    def get_chapter_title(self, index: int, max_length: int = 50) -> str:
        if 0 <= index < len(self._chapter_titles):
            title = self._chapter_titles[index]
            if title and title.strip():
                return title.strip()[:max_length]
        chapter = self.get_chapter(index)
        if chapter:
            return TextParser.get_chapter_title(chapter, max_length)
        return f"第{index + 1}章"

    def get_chapter_word_count(self, index: int) -> int:
        chapter = self.get_chapter(index)
        if chapter:
            return TextParser.count_characters(chapter)
        return 0

    def get_cover_data(self) -> str:
        return self._cover_data

    def get_total_word_count(self) -> int:
        if self._total_word_count is not None:
            return self._total_word_count
        total = 0
        for chapter in self.chapters:
            total += TextParser.count_characters(chapter)
        self._total_word_count = total
        return total

    def clear(self) -> None:
        self._chapter_titles.clear()
        self._current_book = None
        self._cached_parser = None
        self._cached_result = None
        self._last_colors = None
        self._pending_colors = None
        self._cover_data = ""
        self._total_word_count = None
        self._clear_chapter_data()
