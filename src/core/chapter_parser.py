"""章节解析模块

负责书籍内容的章节解析、加载和管理。
全量加载模式——一次性将所有章节读入内存。
"""
from typing import List, Optional

from src.core.base_chapter_parser import BaseChapterParser


class ChapterParser(BaseChapterParser):
    """全量加载章节解析器

    将所有章节一次性读入内存，适合中小型书籍。
    """

    def __init__(self, cache_dir: str = None):
        super().__init__(cache_dir)
        self._chapters: List[str] = []
        self._chapter_html: List[str] = []

    # ── 抽象属性实现 ──

    @property
    def chapters(self) -> List[str]:
        return self._chapters

    @property
    def chapter_count(self) -> int:
        return len(self._chapters)

    # ── 抽象方法实现 ──

    def get_chapter(self, index: int) -> Optional[str]:
        if 0 <= index < len(self._chapters):
            return self._chapters[index]
        return None

    def get_chapter_html(self, index: int) -> str:
        if 0 <= index < len(self._chapter_html):
            if self._pending_colors and self._cached_result and index < len(self._cached_result.chapters):
                self._chapter_html[index] = self._regenerate_html(
                    self._cached_result.chapters[index], self._pending_colors
                )
                self._pending_colors = None
            return self._chapter_html[index]
        return ''

    def set_chapter_html(self, index: int, html: str) -> None:
        if 0 <= index < len(self._chapter_html):
            self._chapter_html[index] = html

    def _on_book_loaded(self, book, chapters, html, titles, cover):
        self._chapters = chapters
        self._chapter_html = html

    def _get_chapters_for_cache(self) -> List[str]:
        return self._chapters

    def _get_html_for_cache(self) -> List[str]:
        return self._chapter_html

    def _clear_chapter_data(self) -> None:
        self._chapters.clear()
        self._chapter_html.clear()
