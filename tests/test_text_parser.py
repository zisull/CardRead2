"""TextParser 模块测试"""
import pytest

from src.utils.text_parser import TextParser


class TestTextParser:
    """TextParser 测试类"""
    
    def test_parse_chapters_empty(self):
        """测试空内容"""
        result = TextParser.parse_chapters("")
        assert result == [""]
    
    def test_parse_chapters_single(self):
        """测试单个章节"""
        content = "这是第一章的内容"
        result = TextParser.parse_chapters(content)
        assert len(result) == 1
        assert result[0] == content
    
    def test_parse_chapters_multiple(self):
        """测试多个章节"""
        content = "第一章 开始\n\n内容1\n\n第二章 继续\n\n内容2"
        result = TextParser.parse_chapters(content)
        assert len(result) == 2
        assert "第一章" in result[0]
        assert "第二章" in result[1]
    
    def test_is_chapter_title_chinese(self):
        """测试中文章节标题识别"""
        assert TextParser.is_chapter_title("第一章 开始") is True
        assert TextParser.is_chapter_title("第1章 开始") is True
        assert TextParser.is_chapter_title("序章") is True
        assert TextParser.is_chapter_title("终章") is True
    
    def test_is_chapter_title_english(self):
        """测试英文章节标题识别"""
        assert TextParser.is_chapter_title("Chapter 1") is True
        assert TextParser.is_chapter_title("CHAPTER 1") is True
    
    def test_is_chapter_title_invalid(self):
        """测试无效章节标题"""
        assert TextParser.is_chapter_title("") is False
        assert TextParser.is_chapter_title("普通文本") is False
        assert TextParser.is_chapter_title("a" * 100) is False
    
    def test_get_chapter_title(self):
        """测试获取章节标题"""
        content = "第一章 开始\n\n这是内容"
        title = TextParser.get_chapter_title(content)
        assert title == "第一章 开始"
    
    def test_get_chapter_title_long(self):
        """测试长标题截断"""
        content = "a" * 100
        title = TextParser.get_chapter_title(content, max_length=20)
        assert len(title) == 20
    
    def test_count_characters(self):
        """测试字符统计"""
        assert TextParser.count_characters("hello") == 5
        assert TextParser.count_characters("hello world") == 10  # 不排除空格
        assert TextParser.count_characters("hello world", exclude_whitespace=True) == 10
    
    def test_count_characters_empty(self):
        """测试空字符串统计"""
        assert TextParser.count_characters("") == 0
        assert TextParser.count_characters(None) == 0
