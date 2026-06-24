"""文本解析工具模块

提供章节分割、标题提取、字符统计等功能。
支持多种常见的中文章节标题格式。
"""
import io
import re
from typing import List, Tuple


class TextParser:
    """文本解析器 - 负责章节分割和文本处理

    支持的章节标题格式：
    - 第X章、第X节、第X回、第X卷（中文数字或阿拉伯数字）
    - Chapter X、CHAPTER X（英文）
    - 卷一、卷二等
    - X、X.（数字加标点）
    - 【章节标题】格式
    - 正文、序章、终章、番外等特殊标记
    """

    # 编译后的章节标题正则模式（按优先级排序）
    CHAPTER_PATTERNS: Tuple[re.Pattern, ...] = (
        re.compile(r'^第[零一二三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟\d]+[章节回卷].{0,30}$'),
        re.compile(r'^[Cc][Hh][Aa][Pp][Tt][Ee][Rr]\s*\d+.{0,30}$'),
        re.compile(r'^(序章|序幕|终章|终卷|番外|楔子|尾声|引子|前言|后记|正文|开篇|结局).{0,30}$'),
        re.compile(r'^第[零一二三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟\d]+卷.{0,30}$'),
        re.compile(r'^[零一二三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]{1,6}[、.．]\s*.{2,30}$'),
        re.compile(r'^【.{1,20}】$'),
        re.compile(r'^卷[零一二三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟\d]+.{0,20}$'),
    )

    _CHAPTER_START_CHARS = frozenset(
        '第序终番楔尾引前後后正开结结局卷章C c0123456789'
        '零一二三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟【'
    )

    @classmethod
    def parse_chapters(cls, content: str) -> List[str]:
        """解析文本内容，按章节分割

        Args:
            content: 文本内容

        Returns:
            章节列表，每个元素是一个章节的内容
        """
        if not content or not content.strip():
            return [content]

        chapters: List[str] = []
        current_chapter: List[str] = []

        for raw_line in io.StringIO(content):
            line = raw_line.rstrip('\n\r')
            stripped = line.strip()
            if not stripped:
                current_chapter.append(line)
                continue

            is_title = cls.is_chapter_title(stripped)

            if is_title and current_chapter:
                current_text = '\n'.join(current_chapter).strip()
                if current_text == stripped:
                    current_chapter = [line]
                    continue
                if current_text:
                    chapters.append(current_text)
                current_chapter = [line]
            else:
                current_chapter.append(line)

        if current_chapter:
            chapter_text = '\n'.join(current_chapter).strip()
            if chapter_text:
                chapters.append(chapter_text)

        if not chapters:
            return [content.strip()]
        
        filtered_chapters = []
        for chapter in chapters:
            stripped = chapter.strip()
            if len(stripped) < 3 and len(filtered_chapters) > 0:
                filtered_chapters[-1] += '\n\n' + chapter
            else:
                filtered_chapters.append(chapter)
        
        return filtered_chapters if filtered_chapters else [content.strip()]

    @classmethod
    def is_chapter_title(cls, line: str) -> bool:
        """判断一行文本是否是章节标题

        Args:
            line: 文本行（应已strip）

        Returns:
            是否是章节标题
        """
        if not line or len(line) > 50:
            return False
        if line[0] not in cls._CHAPTER_START_CHARS:
            return False
        return any(p.match(line) for p in cls.CHAPTER_PATTERNS)

    @classmethod
    def get_chapter_title(cls, chapter_content: str, max_length: int = 50) -> str:
        """从章节内容中提取标题

        Args:
            chapter_content: 章节内容
            max_length: 标题最大长度

        Returns:
            章节标题
        """
        if not chapter_content:
            return "未知章节"

        lines = chapter_content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped:
                return stripped[:max_length]
        return "未知章节"

    @classmethod
    def get_chapter_preview(cls, chapter_content: str, max_length: int = 80) -> str:
        """获取章节内容预览（跳过标题行）

        Args:
            chapter_content: 章节内容
            max_length: 预览最大长度

        Returns:
            章节内容预览
        """
        if not chapter_content:
            return ""

        lines = chapter_content.split('\n')
        # 跳过标题行，找正文内容
        preview_lines = []
        found_title = False
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            if not found_title:
                # 第一个非空行可能是标题，跳过
                if cls.is_chapter_title(stripped):
                    found_title = True
                    continue
                else:
                    found_title = True
            
            preview_lines.append(stripped)
            # 收集足够的预览文本
            if len(''.join(preview_lines)) >= max_length:
                break
        
        preview = ''.join(preview_lines)
        if len(preview) > max_length:
            preview = preview[:max_length] + '...'
        return preview

    @staticmethod
    def count_characters(text: str, exclude_whitespace: bool = True) -> int:
        """统计字符数

        Args:
            text: 文本内容
            exclude_whitespace: 是否排除空白字符

        Returns:
            字符数
        """
        if not text:
            return 0
        if exclude_whitespace:
            # 单趟遍历，避免 8 次 str.count 全串扫描
            return sum(1 for c in text if not c.isspace() and c != '\u3000' and c != '\xa0')
        return len(text)
