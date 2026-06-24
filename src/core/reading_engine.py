"""阅读引擎模块

负责阅读状态管理、章节加载和切换。
"""
from typing import Optional

from src.core.chapter_parser import ChapterParser
from src.models.book import Book


class ReadingEngine:
    """阅读引擎

    管理阅读状态，提供章节加载、切换和进度管理功能。

    Attributes:
        chapter_parser: 章节解析器
        current_book: 当前书籍
        current_chapter: 当前章节索引
    """

    def __init__(self, cache_dir: str = None):
        """初始化阅读引擎"""
        self.chapter_parser = ChapterParser(cache_dir=cache_dir)
        self.current_book: Optional[Book] = None
        self.current_chapter: int = 0
        self.scroll_position: int = 0

    @property
    def is_loaded(self) -> bool:
        """是否有书籍加载"""
        return self.current_book is not None

    @property
    def chapter_count(self) -> int:
        """获取章节数量"""
        return self.chapter_parser.chapter_count

    def load_book(self, book: Book, chapter: int = 0, position: int = 0, theme_colors: dict = None) -> bool:
        """加载书籍

        Args:
            book: Book 对象
            chapter: 初始章节索引
            position: 初始滚动位置
            theme_colors: 主题颜色字典（用于 MD 渲染）

        Returns:
            是否加载成功
        """
        success, _ = self.chapter_parser.load_book(book, theme_colors)
        if not success:
            return False

        self.current_book = book
        self.current_chapter = max(0, min(chapter, self.chapter_count - 1))
        self.scroll_position = position

        return True

    def get_chapter_content(self, index: int = None) -> Optional[str]:
        """获取章节内容

        Args:
            index: 章节索引，为 None 时返回当前章节

        Returns:
            章节内容
        """
        if index is None:
            index = self.current_chapter
        return self.chapter_parser.get_chapter(index)

    def get_current_content(self) -> Optional[str]:
        """获取当前章节内容

        Returns:
            当前章节内容
        """
        return self.get_chapter_content(self.current_chapter)

    def get_current_html(self) -> str:
        """获取当前章节的 HTML 内容

        Returns:
            HTML 内容，无 HTML 则返回空字符串
        """
        return self.chapter_parser.get_chapter_html(self.current_chapter)

    def get_chapter_title(self, index: int = None) -> str:
        """获取章节标题

        Args:
            index: 章节索引

        Returns:
            章节标题
        """
        if index is None:
            index = self.current_chapter
        return self.chapter_parser.get_chapter_title(index)

    def load_chapter(self, index: int) -> bool:
        """加载指定章节

        Args:
            index: 章节索引

        Returns:
            是否加载成功
        """
        if not self.is_loaded:
            return False

        if index < 0 or index >= self.chapter_count:
            return False

        self.current_chapter = index
        self.scroll_position = 0

        return True
