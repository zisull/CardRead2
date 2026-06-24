"""MOBI 格式解析器

基于 mobi 库（KindleUnpack 封装版）解析 MOBI 电子书。
mobi.extract() 将 MOBI 解包为 EPUB 格式，然后复用 EpubParser 进行解析。
支持封面图片、章节分割、内嵌图片等完整功能。
"""
import os
import shutil
from pathlib import Path
from typing import List, Optional

from loguru import logger

from .base_parser import BaseParser, ParseResult
from .epub_parser import EpubParser
from .registry import register_parser


@register_parser
class MobiParser(BaseParser):
    """MOBI 格式解析器，基于 mobi 库"""

    def __init__(self):
        self._epub_parser = EpubParser()

    @property
    def extensions(self) -> List[str]:
        return ['.mobi', '.pdb']

    def supports(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in self.extensions

    def parse(self, file_path: str, colors: dict = None) -> ParseResult:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        logger.debug(f"解析 MOBI: {file_path}")

        import mobi

        tempdir = None
        try:
            tempdir, extracted_path = mobi.extract(file_path)
            ext = Path(extracted_path).suffix.lower()
            logger.debug(f"MOBI 解包结果: {extracted_path} (格式: {ext})")

            if ext == '.epub':
                result = self._epub_parser.parse(extracted_path, colors)
                # 使用文件名作为标题（避免 MOBI 元数据中文乱码）
                result.title = Path(file_path).stem
                return result
            elif ext in ('.html', '.htm'):
                return self._parse_html(extracted_path, tempdir, file_path)
            else:
                raise ValueError(f"不支持的 MOBI 解包格式: {ext}")

        except Exception as e:
            logger.error(f"解析 MOBI 失败: {e}")
            raise
        finally:
            if tempdir and os.path.exists(tempdir):
                try:
                    shutil.rmtree(tempdir)
                except Exception as e:
                    logger.warning(f"清理临时目录失败: {e}")

    def _parse_html(self, html_path: str, tempdir: str, original_path: str) -> ParseResult:
        """解析解包后的 HTML 文件"""
        from bs4 import BeautifulSoup
        import base64
        import re

        with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')

        for tag in soup.find_all(['script', 'style']):
            tag.decompose()

        # 处理图片：将相对路径转为 base64
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if not src or src.startswith('data:'):
                continue
            img_path = os.path.join(os.path.dirname(html_path), src)
            if os.path.isfile(img_path):
                with open(img_path, 'rb') as f:
                    img_data = f.read()
                if len(img_data) < 5 * 1024 * 1024:
                    ext = Path(img_path).suffix.lower()
                    mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                            '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
                    b64 = base64.b64encode(img_data).decode('ascii')
                    img['src'] = f'data:{mime};base64,{b64}'

        # 提取封面
        cover_data = ''
        cover_img = soup.find('img')
        if cover_img and cover_img.get('src', '').startswith('data:'):
            cover_data = cover_img['src']

        # 章节分割
        body = soup.find('body') or soup
        headings = body.find_all(['h1', 'h2', 'h3'])

        from collections import Counter
        level_counts = Counter(h.name for h in headings)
        best_level = None
        for level in ['h1', 'h2', 'h3']:
            if level_counts.get(level, 0) >= 2:
                best_level = level
                break

        from .base_parser import ChapterData

        chapters = []
        if best_level and level_counts[best_level] >= 2:
            split_headings = [h for h in headings if h.name == best_level]
            for i, heading in enumerate(split_headings):
                title = heading.get_text(strip=True) or f"第{i+1}章"
                content_elements = [str(heading)]
                for sibling in heading.next_siblings:
                    if hasattr(sibling, 'name') and sibling.name == best_level:
                        break
                    if sibling in split_headings:
                        break
                    content_elements.append(str(sibling))

                section_html = ''.join(content_elements).strip()
                section_soup = BeautifulSoup(section_html, 'html.parser')
                section_text = section_soup.get_text(separator='\n').strip()
                section_text = re.sub(r'\n{3,}', '\n\n', section_text)

                if section_text or section_html:
                    chapters.append(ChapterData(
                        title=title,
                        content=section_text,
                        html_content=section_html
                    ))
        else:
            full_text = body.get_text(separator='\n').strip()
            full_text = re.sub(r'\n{3,}', '\n\n', full_text)
            chapters.append(ChapterData(
                title='正文',
                content=full_text,
                html_content=str(body).strip()
            ))

        if not chapters:
            raise ValueError("MOBI 文件中没有找到可读内容")

        return ParseResult(
            title=Path(original_path).stem,
            chapters=chapters,
            encoding='utf-8',
            cover_data=cover_data
        )

    def get_cover_image(self, file_path: str) -> Optional[str]:
        """快速提取封面图片"""
        if not os.path.isfile(file_path):
            return None

        import mobi

        tempdir = None
        try:
            tempdir, extracted_path = mobi.extract(file_path)
            ext = Path(extracted_path).suffix.lower()

            if ext == '.epub':
                return self._epub_parser.get_cover_image(extracted_path)
            elif ext in ('.html', '.htm'):
                from bs4 import BeautifulSoup
                with open(extracted_path, 'r', encoding='utf-8', errors='replace') as f:
                    html_content = f.read()
                soup = BeautifulSoup(html_content, 'html.parser')
                cover_img = soup.find('img')
                if cover_img:
                    src = cover_img.get('src', '')
                    if src.startswith('data:'):
                        return src
                    img_path = os.path.join(os.path.dirname(extracted_path), src)
                    if os.path.isfile(img_path):
                        import base64
                        with open(img_path, 'rb') as f:
                            img_data = f.read()
                        ext2 = Path(img_path).suffix.lower()
                        mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                                '.gif': 'image/gif', '.bmp': 'image/bmp'}.get(ext2, 'image/jpeg')
                        b64 = base64.b64encode(img_data).decode('ascii')
                        return f'data:{mime};base64,{b64}'
        except Exception as e:
            logger.debug(f"获取 MOBI 封面失败: {e}")
        finally:
            if tempdir and os.path.exists(tempdir):
                try:
                    shutil.rmtree(tempdir)
                except Exception:
                    pass

        return None
