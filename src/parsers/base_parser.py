"""解析器基础接口模块

定义所有文件格式解析器的抽象基类和数据结构。
"""
from dataclasses import dataclass
from typing import List, Protocol, runtime_checkable


@dataclass
class ChapterData:
    """章节数据"""
    title: str
    content: str
    html_content: str = ""
    raw_md: str = ""  # 原始 Markdown 文本（用于主题切换时重新渲染）

    @property
    def word_count(self) -> int:
        return len([c for c in self.content if not c.isspace()])

    @property
    def is_html(self) -> bool:
        return bool(self.html_content)

    def get_display_text(self) -> str:
        return self.html_content if self.html_content else self.content


@dataclass
class ParseResult:
    """解析结果"""
    title: str
    chapters: List[ChapterData]
    encoding: str = 'utf-8'
    cover_data: str = ""

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    @property
    def total_word_count(self) -> int:
        return sum(ch.word_count for ch in self.chapters)

    @property
    def all_content(self) -> str:
        return '\n\n'.join(ch.content for ch in self.chapters)


@runtime_checkable
class BaseParser(Protocol):
    """文件解析器协议

    所有格式解析器都应实现此协议。
    新增格式只需：
    1. 实现 extensions、supports、parse 方法
    2. 在 ParserFactory 中注册
    """

    extensions: List[str]

    def supports(self, file_path: str) -> bool:
        """判断是否支持该文件

        Args:
            file_path: 文件路径

        Returns:
            是否支持
        """
        ...

    def parse(self, file_path: str, colors: dict = None) -> ParseResult:
        """解析文件

        Args:
            file_path: 文件路径

        Returns:
            ParseResult 对象

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误
            IOError: 读取失败
        """
        ...
