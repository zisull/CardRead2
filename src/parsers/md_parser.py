"""Markdown 格式解析器

解析 Markdown 文件，按标题层级分割章节。
支持将 Markdown 转换为 HTML 用于富文本展示。
使用 mistune 库进行 Markdown 解析。
"""
import base64
import os
import re
from pathlib import Path
from typing import List, Optional

import mistune
from mistune.plugins.abbr import abbr
from mistune.plugins.def_list import def_list
from mistune.plugins.footnotes import footnotes
from mistune.plugins.formatting import strikethrough, mark, insert, superscript, subscript
from mistune.plugins.table import table
from mistune.plugins.task_lists import task_lists
from mistune.plugins.url import url

from src.utils.encoding import EncodingDetector
from .base_parser import BaseParser, ParseResult, ChapterData
from .registry import register_parser


class CardReadRenderer(mistune.HTMLRenderer):
    """自定义 mistune 渲染器，输出纯结构 HTML（无内联颜色）。

    主题配色由前端 CSS 变量控制（reader.js _applyThemeVars），
    colors 参数为保留参数当前未使用，避免主题切换时重渲染。
    """

    def __init__(self, colors: dict = None, **kwargs):
        super().__init__(**kwargs)

    def heading(self, text: str, level: int, **attrs) -> str:
        return f'<h{level}>{text}</h{level}>'

    def paragraph(self, text: str) -> str:
        return f'<p>{text}</p>'

    def block_quote(self, text: str) -> str:
        return f'<blockquote>{text}</blockquote>'

    def block_code(self, code: str, info: str = None, **attrs) -> str:
        if info and info.strip().lower() == 'mermaid':
            return f'<pre class="mermaid">{code}</pre>\n'
        lang_attr = f' class="language-{mistune.escape(info)}"' if info else ''
        return f'<pre><code{lang_attr}>{mistune.escape(code)}</code></pre>\n'

    def block_html(self, html: str) -> str:
        return html + '\n'

    # ── 表格 ──

    def table(self, text: str) -> str:
        return f'<table>{text}</table>'

    def table_head(self, text: str) -> str:
        return f'<thead><tr>{text}</tr></thead>'

    def table_body(self, text: str) -> str:
        return f'<tbody>{text}</tbody>'

    def table_row(self, text: str) -> str:
        return f'<tr>{text}</tr>'

    def table_cell(self, text: str, align: str = None, head: bool = False, **attrs) -> str:
        align_attr = f' style="text-align:{align}"' if align else ''
        tag = 'th' if head else 'td'
        return f'<{tag}{align_attr}>{text}</{tag}>'

    # ── 列表 ──

    def list(self, body: str, ordered: bool, **attrs) -> str:
        tag = 'ol' if ordered else 'ul'
        return f'<{tag}>{body}</{tag}>'

    def list_item(self, text: str, **attrs) -> str:
        return f'<li>{text}</li>'

    # ── 任务列表 ──

    def task_list_item(self, text: str, checked: bool = False, **attrs) -> str:
        checkbox = '&#9745;' if checked else '&#9744;'
        return f'<li class="task-list-item">{checkbox} {text}</li>'

    # ── 脚注 ──

    def footnotes(self, text: str) -> str:
        return f'<section class="footnotes"><ol>{text}</ol></section>'

    def footnote_item(self, text: str, key: str, index: int) -> str:
        return f'<li id="fn-{index}">{text}</li>'

    def footnote_ref(self, key: str, index: int) -> str:
        return f'<sup><a href="#fn-{index}">[{index}]</a></sup>'

    # ── 定义列表 ──

    def def_list(self, text: str) -> str:
        return f'<dl>{text}</dl>'

    def def_list_head(self, text: str) -> str:
        return f'<dt>{text}</dt>'

    def def_list_item(self, text: str) -> str:
        return f'<dd>{text}</dd>'

    # ── 行内元素 ──

    def link(self, text: str, url: str, title: str = None) -> str:
        title_attr = f' title="{mistune.escape(title)}"' if title else ''
        return f'<a href="{url}"{title_attr}>{text}</a>'

    def image(self, alt: str, url: str, title: str = None) -> str:
        if hasattr(self, '_file_dir') and self._file_dir and not url.startswith(('http://', 'https://')):
            abs_path = os.path.normpath(os.path.join(self._file_dir, url))
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, 'rb') as f:
                        img_data = f.read()
                    ext = os.path.splitext(abs_path)[1].lower()
                    mime_map = {
                        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                        '.png': 'image/png', '.gif': 'image/gif',
                        '.svg': 'image/svg+xml', '.webp': 'image/webp',
                        '.bmp': 'image/bmp'
                    }
                    mime = mime_map.get(ext, 'image/png')
                    b64 = base64.b64encode(img_data).decode('ascii')
                    return f'<img src="data:{mime};base64,{b64}" alt="{alt}">'
                except Exception:
                    pass
        return f'<img src="{url}" alt="{alt}">'

    def codespan(self, text: str) -> str:
        return f'<code>{text}</code>'

    def emphasis(self, text: str) -> str:
        return f'<em>{text}</em>'

    def strong(self, text: str) -> str:
        return f'<strong>{text}</strong>'

    def strikethrough(self, text: str) -> str:
        return f'<del>{text}</del>'

    def mark(self, text: str) -> str:
        return f'<mark>{text}</mark>'

    def insert(self, text: str) -> str:
        return f'<ins>{text}</ins>'

    def superscript(self, text: str) -> str:
        return f'<sup>{text}</sup>'

    def subscript(self, text: str) -> str:
        return f'<sub>{text}</sub>'

    def abbr(self, text: str, title: str) -> str:
        return f'<abbr title="{title}">{text}</abbr>'

    def hr(self) -> str:
        return '<hr>'

    def inline_html(self, html: str) -> str:
        from html import escape
        return escape(html)


@register_parser
class MarkdownParser(BaseParser):
    """Markdown 格式解析器"""

    HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

    def __init__(self):
        self._encoding_detector = EncodingDetector()
        self._ast_md = mistune.create_markdown(renderer='ast')
        self._cached_colors_key: Optional[str] = None
        self._cached_md_parser = None
        self._cached_file_dir: str = ''

    @property
    def extensions(self) -> List[str]:
        return ['.md', '.markdown']

    def supports(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in self.extensions

    def parse(self, file_path: str, colors: dict = None) -> ParseResult:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        content, encoding = self._encoding_detector.read_file(file_path)
        title = self._extract_title(content) or Path(file_path).stem
        file_dir = os.path.dirname(os.path.abspath(file_path))
        chapters = self._split_chapters(content, colors, file_dir=file_dir)

        if not chapters:
            html = self._md_to_html(content, colors, file_dir=file_dir)
            chapters = [ChapterData(title=title, content=content, html_content=html, raw_md=content)]

        return ParseResult(
            title=title,
            chapters=chapters,
            encoding=encoding
        )

    def _extract_title(self, content: str) -> str:
        in_code_block = False
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            match = re.match(r'^#\s+(.+)$', stripped)
            if match:
                return match.group(1).strip()
        return ''

    def _get_headings_from_ast(self, content: str) -> List[tuple]:
        """使用 mistune AST 模式获取标题列表，自动排除代码块内的标题"""
        tokens = self._ast_md(content)
        headings = []

        def _extract_text(children):
            result = []
            for child in children:
                if child.get('type') == 'text':
                    result.append(child.get('raw', '') or child.get('text', ''))
                elif 'children' in child:
                    result.append(_extract_text(child['children']))
            return ''.join(result)

        for tok in tokens:
            if tok.get('type') == 'heading':
                level = tok.get('attrs', {}).get('level', 1)
                children = tok.get('children', [])
                title = _extract_text(children).strip()
                if title:
                    headings.append((level, title))

        return headings

    def _extract_plain_text_from_ast(self, content: str) -> str:
        """使用 mistune AST 提取纯文本（替代正则 _strip_markdown）"""
        tokens = self._ast_md(content)
        parts = []

        def _walk(nodes):
            for node in nodes:
                t = node.get('type', '')
                if t == 'text':
                    parts.append(node.get('raw', '') or node.get('text', ''))
                elif t == 'softbreak':
                    parts.append('\n')
                elif t == 'linebreak':
                    parts.append('\n')
                elif t == 'block_code':
                    pass  # 跳过代码块
                elif t == 'block_quote':
                    children = node.get('children', [])
                    _walk(children)
                elif t == 'paragraph':
                    children = node.get('children', [])
                    _walk(children)
                    parts.append('\n\n')
                elif t == 'heading':
                    children = node.get('children', [])
                    _walk(children)
                    parts.append('\n')
                elif t == 'list':
                    children = node.get('children', [])
                    _walk(children)
                elif t == 'list_item':
                    children = node.get('children', [])
                    _walk(children)
                elif t == 'table':
                    children = node.get('children', [])
                    _walk(children)
                elif t == 'table_head' or t == 'table_body':
                    children = node.get('children', [])
                    _walk(children)
                elif t == 'table_row':
                    children = node.get('children', [])
                    _walk(children)
                    parts.append('\n')
                elif t == 'table_cell':
                    children = node.get('children', [])
                    _walk(children)
                    parts.append(' | ')
                elif t == 'thematic_break':
                    parts.append('\n')
                elif t == 'blank_line':
                    parts.append('\n')
                elif 'children' in node:
                    _walk(node['children'])

        _walk(tokens)
        text = ''.join(parts)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _find_heading_pos(self, content: str, level: int, title: str, start_from: int = 0) -> int:
        """在原始内容中查找标题的位置"""
        pattern = re.compile(r'^' + re.escape('#' * level) + r'\s+' + re.escape(title) + r'\s*$', re.MULTILINE)
        match = pattern.search(content, start_from)
        return match.start() if match else -1

    def _split_chapters(self, content: str, colors: dict = None, file_dir: str = '') -> List[ChapterData]:
        ast_headings = self._get_headings_from_ast(content)

        if not ast_headings:
            return []

        headings = []
        last_pos = 0
        for level, title in ast_headings:
            pos = self._find_heading_pos(content, level, title, last_pos)
            if pos >= 0:
                headings.append((level, title, pos))
                last_pos = pos + 1

        if not headings:
            return []

        from collections import Counter
        level_counts = Counter(h[0] for h in headings)
        best_level = None
        best_count = 0
        for level, count in sorted(level_counts.items()):
            if count >= 2 and count > best_count:
                best_level = level
                best_count = count

        if best_level is None:
            for level, count in sorted(level_counts.items()):
                if count >= 1:
                    best_level = level
                    break

        if best_level is None:
            return []

        split_points = [(h[1], h[2]) for h in headings if h[0] == best_level]

        if len(split_points) < 2:
            if len(split_points) == 1:
                ch_title, start_pos = split_points[0]
                raw = content[start_pos:].strip()
                plain = self._extract_plain_text_from_ast(raw)
                html = self._md_to_html(raw, colors, file_dir=file_dir)
                if plain:
                    return [ChapterData(title=ch_title, content=plain, html_content=html, raw_md=raw)]
            return []

        chapters = []

        first_split_pos = split_points[0][1]
        intro_raw = content[:first_split_pos].strip()
        if intro_raw:
            intro_plain = self._extract_plain_text_from_ast(intro_raw)
            if intro_plain:
                intro_html = self._md_to_html(intro_raw, colors, file_dir=file_dir)
                intro_title = ''
                for h in headings:
                    if h[1] not in [sp[0] for sp in split_points]:
                        intro_title = h[1]
                        break
                if not intro_title:
                    intro_title = self._extract_title(content) or '简介'
                chapters.append(ChapterData(title=intro_title, content=intro_plain, html_content=intro_html, raw_md=intro_raw))

        for i, (ch_title, start_pos) in enumerate(split_points):
            end_pos = split_points[i + 1][1] if i + 1 < len(split_points) else len(content)
            raw = content[start_pos:end_pos].strip()
            plain = self._extract_plain_text_from_ast(raw)
            html = self._md_to_html(raw, colors, file_dir=file_dir)
            if plain:
                chapters.append(ChapterData(title=ch_title, content=plain, html_content=html, raw_md=raw))

        return chapters

    def _md_to_html(self, md: str, colors: dict = None, file_dir: str = '') -> str:
        c = colors or {}
        colors_key = (file_dir, c.get('bg'), c.get('fg'), c.get('accent'), c.get('tip'), c.get('font_color'))
        if self._cached_md_parser and self._cached_colors_key == colors_key:
            return self._cached_md_parser(md)

        renderer = CardReadRenderer(colors=colors, escape=False)
        renderer._file_dir = file_dir
        md_parser = mistune.create_markdown(
            renderer=renderer,
            plugins=[
                table, task_lists, strikethrough,
                footnotes, def_list, url,
                mark, insert, superscript, subscript, abbr,
            ],
        )
        self._cached_md_parser = md_parser
        self._cached_colors_key = colors_key
        return md_parser(md)
