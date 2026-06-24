"""EPUB 格式解析器

使用 ebooklib 和 BeautifulSoup 解析 EPUB 电子书文件。
ebooklib 自动处理 EPUB2/3 规范、路径解析和编码问题。
"""
import base64
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from ebooklib import epub, ITEM_DOCUMENT, ITEM_IMAGE
from loguru import logger

from src.config import MAX_IMAGE_SIZE, MAX_EPUB_SINGLE_IMAGE, MAX_CHAPTER_IMAGE_TOTAL

from .base_parser import BaseParser, ParseResult, ChapterData
from .registry import register_parser


@register_parser
class EpubParser(BaseParser):
    """EPUB 格式解析器"""

    NOISE_WORDS = {'未知', 'unknown', 'untitled', 'null', 'none', '正文', '内容', '...', '…',
                   'cover', 'table of contents', 'contents', 'toc', '目录', '封面', '版权页',
                   '前言', '序言', '序', '后记', '附录', '索引'}

    def __init__(self):
        """初始化 EPUB 解析器"""
        pass  # 无需实例状态，图片缓存在 parse 周期内局部持有（避免单例累积）

    @property
    def extensions(self) -> List[str]:
        return ['.epub']

    def supports(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in self.extensions

    def parse(self, file_path: str, colors: dict = None) -> ParseResult:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        logger.debug(f"解析 EPUB: {file_path}")

        try:
            book = epub.read_epub(file_path)
        except Exception as e:
            logger.error(f"读取 EPUB 失败: {e}")
            raise ValueError(f"无法读取 EPUB 文件: {e}")
        
        title = self._get_title(book)
        chapters = self._extract_chapters(book, colors)

        if not chapters:
            raise ValueError("EPUB 文件中没有找到可读内容")

        cover_data = self._extract_cover(book)

        return ParseResult(
            title=title or Path(file_path).stem,
            chapters=chapters,
            encoding='utf-8',
            cover_data=cover_data
        )

    def _get_title(self, book: epub.EpubBook) -> str:
        """获取书籍标题"""
        try:
            title = book.get_metadata('DC', 'title')
            if title:
                val = title[0][0] if isinstance(title[0], (tuple, list)) else title[0]
                if val and isinstance(val, str) and val.strip():
                    return val.strip()
        except Exception as e:
            logger.warning(f"获取标题失败: {e}")
        return ''

    def _extract_cover(self, book: epub.EpubBook) -> str:
        try:
            meta = book.get_metadata('meta', 'cover')
            if meta:
                cover_id = meta[0][0] if isinstance(meta[0], (tuple, list)) else meta[0]
                if cover_id:
                    cover_item = book.get_item_with_id(str(cover_id))
                    if cover_item:
                        img_data = cover_item.content
                        if img_data and len(img_data) < MAX_IMAGE_SIZE:
                            mime = self._guess_mime(cover_item.get_name() or '')
                            b64 = base64.b64encode(img_data).decode('ascii')
                            return f'data:{mime};base64,{b64}'
        except Exception as e:
            logger.debug(f"从元数据获取封面失败: {e}")

        for item in book.get_items_of_type(ITEM_IMAGE):
            name = item.get_name().lower()
            if 'cover' in name:
                img_data = item.content
                if img_data and len(img_data) < MAX_IMAGE_SIZE:
                    mime = self._guess_mime(item.get_name() or '')
                    b64 = base64.b64encode(img_data).decode('ascii')
                    return f'data:{mime};base64,{b64}'

        return ""

    def _extract_chapters(self, book: epub.EpubBook, colors: dict = None) -> List[ChapterData]:
        """提取所有章节内容
        
        注意：image_index 和 image_cache 在单本书 parse 周期内使用，
        不应在多线程场景下并发访问。当前实现为串行处理，但若未来改为并行解析，
        需确保每个 parse 周期有独立的索引和缓存副本。
        """
        book_title = self._get_title(book)
        image_index = self._build_image_index(book)
        # 图片缓存在单本书的 parse 周期内局部持有，parse 结束自动释放，避免单例累积
        image_cache: Dict[str, str] = {}
        items = list(book.get_items_of_type(ITEM_DOCUMENT))
        logger.debug(f"文档项: {len(items)}")

        parsed = []
        for item in items:
            soup = None
            try:
                content = item.content
                if not content:
                    continue
                html_str = content.decode('utf-8', errors='ignore')
                soup = BeautifulSoup(html_str, 'html.parser')
                text = self._extract_text(soup)
                text = re.sub(r'\n{3,}', '\n\n', text).strip()
                has_images = bool(soup.find('img'))
                if not text or len(text) < 10:
                    if not has_images:
                        soup.decompose()
                        soup = None
                        continue
                    text = "[图片内容]"
                parsed.append((item, soup, text))
            except Exception as e:
                logger.warning(f"预处理文档 {item.get_name()} 失败: {e}")
                if soup is not None:
                    soup.decompose()
                    soup = None

        name_to_chapter = {}
        for idx, (item, _, _) in enumerate(parsed):
            name = item.get_name()
            if name:
                name_to_chapter[name.removeprefix('./')] = idx
                bn = os.path.basename(name)
                if bn:
                    name_to_chapter[bn] = idx

        chapters = []
        for item, soup, text in parsed:
            try:
                self._process_images(soup, image_index, image_cache)
                title = self._extract_title(soup, item, chapters, book_title)
                body_html = self._get_body_html(soup, name_to_chapter)
                chapters.append(ChapterData(title=title, content=text, html_content=body_html))
                logger.debug(f"添加章节: {title}")
            except Exception as e:
                logger.warning(f"处理文档 {item.get_name()} 失败: {e}")
            finally:
                soup.decompose()

        return chapters

    def _process_images(self, soup: BeautifulSoup, image_index: dict, image_cache: Dict[str, str]):
        """处理 HTML 中的图片，转换为 base64

        串行处理（base64.b64encode 是 CPU 密集型，GIL 下多线程无并行收益反有调度开销）。
        image_cache 由调用方传入，在单本书 parse 周期内复用，避免重复转换同一图片。
        """
        total_size = 0
        max_total = MAX_CHAPTER_IMAGE_TOTAL

        for img in soup.find_all('img'):
            src = img.get('src', '')
            if not src or src.startswith('data:'):
                continue
            if total_size >= max_total:
                img.decompose()
                continue

            # 检查缓存（同一本书内多章节可能引用同一图片）
            if src in image_cache:
                img['src'] = image_cache[src]
                continue

            image_item = self._find_image_from_index(src, image_index)
            if image_item:
                img_data = image_item.content
                if img_data and len(img_data) > MAX_EPUB_SINGLE_IMAGE:
                    logger.warning(f"图片过大({len(img_data)}字节)，跳过: {src}")
                    img.decompose()
                    continue
                if img_data:
                    if total_size + len(img_data) > max_total:
                        logger.warning(f"章节图片总量超过限制，跳过: {src}")
                        continue
                    total_size += len(img_data)
                    # 串行转 base64
                    try:
                        img_name = image_item.get_name()
                        mime = self._guess_mime(img_name or src)
                        b64 = base64.b64encode(img_data).decode('ascii')
                        data_url = f'data:{mime};base64,{b64}'
                        image_cache[src] = data_url
                        img['src'] = data_url
                    except Exception as e:
                        logger.warning(f"处理图片 {src} 失败: {e}")
                else:
                    logger.warning(f"图片内容为空: {src}")
            else:
                logger.warning(f"未找到图片资源: {src}")

    def _build_image_index(self, book: epub.EpubBook) -> dict:
        """构建图片索引，支持多种路径匹配
        
        注意：返回的字典在单本书 parse 周期内使用，不应在多线程场景下并发访问。
        当前实现为串行处理，但若未来改为并行解析，需确保每个 parse 周期有独立的索引副本。
        """
        index = {}
        
        # 收集所有可能的图片资源
        for item in book.get_items():
            item_name = item.get_name()
            if not item_name:
                continue
            
            # 检查是否为图片类型
            item_type = item.get_type()
            is_image = (item_type == ITEM_IMAGE or 
                       'image' in str(item_type) or
                       item_name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp')))
            
            if is_image:
                # 存储多种路径形式
                clean_name = item_name.removeprefix('./')
                basename = os.path.basename(item_name)
                
                # 原始路径
                index[clean_name] = item
                # 小写路径
                index[clean_name.lower()] = item
                # 仅文件名
                if basename:
                    index[basename] = item
                    index[basename.lower()] = item
                # 去掉目录的路径
                if '/' in clean_name:
                    index[clean_name.split('/')[-1]] = item
        
        logger.debug(f"图片索引: {len(index)} 条")
        return index

    def _find_image_from_index(self, src: str, index: dict) -> Optional[epub.EpubItem]:
        """从索引中查找图片资源"""
        # 清理路径
        src_clean = src.removeprefix('./').removeprefix('/')
        src_basename = os.path.basename(src_clean)
        
        # 尝试多种匹配方式
        for key in [src_clean, src_basename, src_clean.lower(), src_basename.lower()]:
            if key in index:
                return index[key]
        
        # 模糊匹配：检查索引键是否以源路径结尾
        src_lower = src_clean.lower()
        for key, item in index.items():
            if key.endswith(src_lower) or src_lower.endswith(key):
                return item
        
        return None

    def _guess_mime(self, src: str) -> str:
        """根据文件扩展名猜测 MIME 类型"""
        ext = os.path.splitext(src)[1].lower()
        mime_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.webp': 'image/webp'
        }
        return mime_map.get(ext, 'image/png')

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """从 HTML 提取纯文本"""
        # 移除脚本和样式
        for tag in soup.find_all(['script', 'style']):
            tag.decompose()
        
        # 获取文本
        text = soup.get_text(separator='\n')
        
        # 清理文本
        lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
            elif lines and lines[-1] != '':
                lines.append('')
        
        return '\n'.join(lines).strip()

    def _extract_title(self, soup: BeautifulSoup, item: epub.EpubItem, chapters: List[ChapterData], book_title: str = '') -> str:
        """从 HTML 提取标题"""
        book_title_lower = book_title.strip().lower()
        
        # 尝试从标题标签提取（跳过与书名相同的标题）
        for tag_name in ['h1', 'h2', 'h3']:
            for heading in soup.find_all(tag_name):
                title = heading.get_text().strip()
                if not title or len(title) >= 80:
                    continue
                title_lower = title.lower()
                # 跳过噪声词和书名
                if title_lower in ('', 'contents', 'toc', '目录') or title in self.NOISE_WORDS:
                    continue
                if book_title_lower and title_lower == book_title_lower:
                    continue
                return title
        
        # 尝试从 <title> 标签提取
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            if title and len(title) < 80:
                title_lower = title.lower()
                if title_lower not in ('', 'contents', 'toc', '目录') and title not in self.NOISE_WORDS:
                    if not book_title_lower or title_lower != book_title_lower:
                        return title
        
        # 尝试从特定 class 提取
        for cls in ['chapter-title', 'ct', 'title', 'chapter', 'heading', 'chapterName', 'chapter-title']:
            elem = soup.find(class_=re.compile(cls, re.I))
            if elem:
                title = elem.get_text().strip()
                if title and len(title) < 80:
                    title_lower = title.lower()
                    if title_lower not in ('', 'contents', 'toc', '目录') and title not in self.NOISE_WORDS:
                        if not book_title_lower or title_lower != book_title_lower:
                            return title
        
        # 尝试从文件名提取
        name = item.get_name()
        if name:
            basename = os.path.splitext(os.path.basename(name))[0]
            # 移除数字前缀和常见前缀
            clean_name = re.sub(r'^\d+[-_]?', '', basename).strip()
            # 移除常见无意义前缀
            clean_name = re.sub(r'^(chapter|ch|part|pt)[-\s_]?\d*\s*', '', clean_name, flags=re.I).strip()
            if clean_name and clean_name.lower() not in ('index', 'content', 'toc', 'chapter', 'text', 'page'):
                return clean_name
            # 如果清理后为空，尝试用原始文件名
            if not clean_name and basename:
                clean_name = re.sub(r'^\d+[-_]?', '', basename).strip()
                if clean_name:
                    return clean_name
        
        # 生成默认标题
        img_count = len([c for c in chapters if c.content.startswith('[图片')])
        if soup.find('img'):
            return f"插图 {img_count + 1}"
        
        return f"第{len(chapters) + 1}章"

    _BLOCK_TAGS = frozenset({
        'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'table', 'pre', 'blockquote',
        'section', 'article', 'header', 'footer', 'nav',
        'aside', 'figure', 'figcaption', 'details', 'summary',
        'hr', 'dl', 'dt', 'dd',
    })

    def _get_body_html(self, soup: BeautifulSoup, name_to_chapter: dict = None) -> str:
        """获取处理后的 body HTML"""
        body = soup.find('body')
        if not body:
            body = soup

        for tag in body.find_all(['script', 'style', 'link']):
            tag.decompose()

        for tag in body.find_all(True):
            if tag.get('style'):
                del tag['style']
            if tag.get('class'):
                del tag['class']

        if name_to_chapter:
            for a in body.find_all('a'):
                href = a.get('href', '').strip()
                if not href or href.startswith(('http://', 'https://', '#', 'mailto:')):
                    continue
                parts = href.split('#', 1)
                file_part = parts[0]
                anchor_part = parts[1] if len(parts) > 1 else ''
                clean = file_part.removeprefix('./')
                idx = name_to_chapter.get(clean)
                if idx is None:
                    idx = name_to_chapter.get(os.path.basename(clean))
                if idx is not None:
                    a['href'] = f'#ch-{idx}' + (f'#{anchor_part}' if anchor_part else '')

        for div in body.find_all('div'):
            has_block = any(
                child.name in self._BLOCK_TAGS
                for child in div.children
                if hasattr(child, 'name') and child.name
            )
            if not has_block:
                div.name = 'p'

        self._clean_paragraphs(body)

        return str(body).strip()

    def _clean_paragraphs(self, body):
        for p in body.find_all('p'):
            text = p.get_text(strip=True)
            if not text:
                has_img = p.find('img')
                if not has_img:
                    p.decompose()

        for br in body.find_all('br'):
            prev = br.previous_sibling
            nxt = br.next_sibling
            if self._is_block_sibling(prev) or self._is_block_sibling(nxt):
                br.decompose()
                continue
            if self._is_br(prev) or self._is_br(nxt):
                br.decompose()

        for p in body.find_all('p'):
            children = list(p.children)
            if len(children) == 1 and self._is_br(children[0]):
                p.decompose()

    @staticmethod
    def _is_block_sibling(node):
        if node is None:
            return True
        if hasattr(node, 'name') and node.name in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'table', 'pre', 'blockquote', 'section', 'hr'):
            return True
        return False

    @staticmethod
    def _is_br(node):
        return hasattr(node, 'name') and node.name == 'br'

    def get_cover_image(self, file_path: str) -> Optional[str]:
        try:
            book = epub.read_epub(file_path)
            for item in book.get_items():
                if item.get_type() == ITEM_IMAGE:
                    name = item.get_name().lower()
                    if 'cover' in name or name.endswith(('.jpg', '.jpeg', '.png')):
                        img_data = item.content
                        if img_data and len(img_data) < MAX_IMAGE_SIZE:
                            import base64
                            mime = self._guess_mime(item.get_name())
                            return f'data:{mime};base64,{base64.b64encode(img_data).decode("ascii")}'
        except Exception:
            pass
        return None
