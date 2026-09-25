"""EPUB 正文净化测试

_get_body_html 负责去掉外来样式/事件处理器并把书内链接改写成章内锚点。
"""
import pytest
from bs4 import BeautifulSoup

from src.parsers.epub_parser import EpubParser

SAMPLE = '''<html><body>
<p style="color:red" class="a b" onclick="alert(1)" onerror="x">正文<img src="a.png" onload="evil()"/></p>
<script>alert(2)</script>
<iframe src="http://evil"></iframe>
<object data="x"></object>
<div><span>只有内联</span></div>
<p><a href="javascript:alert(3)">点我</a> <a href="chap2.xhtml#s">下一章</a></p>
<p>   </p>
</body></html>'''


@pytest.fixture
def body_html():
    parser = EpubParser()
    soup = BeautifulSoup(SAMPLE, 'html.parser')
    return parser._get_body_html(soup, {'chap2.xhtml': 1})


class TestGetBodyHtml:
    def test_strips_event_handlers_and_inline_style(self, body_html):
        for token in ('onclick', 'onerror', 'onload', 'style=', 'class='):
            assert token not in body_html

    def test_strips_active_tags(self, body_html):
        for token in ('<script', '<iframe', '<object'):
            assert token not in body_html

    def test_keeps_text_and_images(self, body_html):
        assert '正文' in body_html
        assert '<img src="a.png"' in body_html
        assert '只有内联' in body_html

    def test_unwraps_javascript_link_but_keeps_label(self, body_html):
        assert 'javascript:' not in body_html
        assert '点我' in body_html

    def test_rewrites_internal_link_to_anchor(self, body_html):
        assert 'href="#ch-1#s"' in body_html

    def test_drops_empty_paragraphs(self, body_html):
        assert body_html.count('<p>') == body_html.count('</p>')
        assert '<p> </p>' not in body_html
