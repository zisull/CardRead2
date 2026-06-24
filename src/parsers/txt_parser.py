"""TXT 格式解析器

解析纯文本文件，支持自动编码检测和章节分割。
支持章节标题美化渲染。
"""
import os
from html import escape as html_escape
from pathlib import Path
from typing import List

from src.utils.encoding import EncodingDetector
from src.utils.text_parser import TextParser
from .base_parser import BaseParser, ParseResult, ChapterData
from .registry import register_parser


@register_parser
class TxtParser(BaseParser):
    """TXT 格式解析器"""

    def __init__(self):
        self._encoding_detector = EncodingDetector()

    @property
    def extensions(self) -> List[str]:
        return ['.txt', '.text', '.log']

    def supports(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in self.extensions

    def parse(self, file_path: str, colors: dict = None) -> ParseResult:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        content, encoding = self._encoding_detector.read_file(file_path)
        title = Path(file_path).stem
        raw_chapters = TextParser.parse_chapters(content)

        chapters = []
        for raw in raw_chapters:
            ch_title = TextParser.get_chapter_title(raw)
            html = self._txt_to_html(raw, ch_title, colors)
            chapters.append(ChapterData(title=ch_title, content=raw, html_content=html))

        return ParseResult(
            title=title,
            chapters=chapters,
            encoding=encoding
        )

    def _txt_to_html(self, text: str, chapter_title: str, colors: dict = None) -> str:
        """将文本转换为 HTML（纯结构无内联颜色，colors 保留参数当前未用，主题靠前端 CSS 变量）"""
        lines = text.split('\n')
        parts = []
        group = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if group:
                    parts.append('<p>' + '<br>'.join(html_escape(ln) for ln in group) + '</p>')
                    group = []
                continue
            if TextParser.is_chapter_title(stripped):
                if group:
                    parts.append('<p>' + '<br>'.join(html_escape(ln) for ln in group) + '</p>')
                    group = []
                parts.append(f'<h2>{html_escape(stripped)}</h2>')
            else:
                group.append(stripped)

        if group:
            parts.append('<p>' + '<br>'.join(html_escape(ln) for ln in group) + '</p>')

        return '\n'.join(parts)
