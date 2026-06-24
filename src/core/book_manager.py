"""书籍管理模块

负责书籍的导入、删除、验证和书架管理。
"""
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any

from loguru import logger

from src.models.book import Book
from src.parsers.parser_factory import get_parser_for_file
from src.utils.text_parser import TextParser
from src.utils.encoding import EncodingDetector
from src.config import SCAN_SAMPLE_SIZE


class BookManager:
    """书籍管理器

    负责书籍的增删改查和文件验证。
    使用 DataStore（数据库）存储书籍数据。

    Attributes:
        books_dir: 书籍存放目录
        data_store: 数据存储管理器
    """

    def __init__(self, books_dir: str, data_store=None):
        """初始化书籍管理器

        Args:
            books_dir: 书籍存放目录
            data_store: DataStore 实例，用于数据库操作
        """
        self.books_dir = books_dir
        self.data_store = data_store
        self._encoding_detector = EncodingDetector()

    def import_book(self, file_path: str) -> Optional[Book]:
        """导入书籍

        根据文件格式采用不同策略：
        - TXT 等文本格式：转码为 UTF-8 TXT 存档
        - EPUB/MD 等格式：保留原格式文件存档

        Args:
            file_path: 文件路径

        Returns:
            Book 对象，失败返回 None
        """
        if not Path(file_path).is_file():
            logger.warning(f"[导入] 文件不存在: {file_path}")
            return None

        # 规范化源文件路径
        abs_file_path = str(Path(file_path).resolve())

        book_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(file_path).stem).strip('. ')
        ext = Path(file_path).suffix.lower()

        if self.has_book(book_name):
            logger.debug(f"[导入] 书籍已存在: {book_name}")
            return self.get_book(book_name)

        parser = get_parser_for_file(file_path)
        if not parser:
            logger.warning(f"[导入] 无匹配解析器: {file_path}")
            return None

        try:
            result = parser.parse(file_path)

            # 统一使用文件名作为书名，不使用解析器标题覆盖
            noise = {'未知', 'unknown', 'untitled', 'null', 'none', '正文', '内容'}
            parsed_title = (result.title or '').strip()
            if parsed_title and parsed_title.lower() in noise:
                logger.debug(f"[导入] 忽略解析器噪声标题: {parsed_title}")

            # 计算目标路径
            if ext in ('.epub', '.md', '.markdown', '.mobi', '.pdb'):
                dest_path = str(Path(self.books_dir) / (book_name + ext))
            else:
                dest_path = str(Path(self.books_dir) / (book_name + ".txt"))

            # 规范化路径并验证
            dest_path = str(Path(dest_path).resolve())
            abs_books_dir = str(Path(self.books_dir).resolve())

            # 验证目标路径在允许的目录范围内
            if not dest_path.startswith(abs_books_dir + os.sep):
                logger.warning(f"[导入] 目标路径超出允许范围: {dest_path}")
                return None

            # 处理文件名冲突
            if Path(dest_path).exists():
                stem = Path(dest_path).stem
                suffix = Path(dest_path).suffix
                parent = Path(dest_path).parent
                counter = 1
                while Path(parent / f"{stem}_{counter}{suffix}").exists():
                    counter += 1
                dest_path = str(parent / f"{stem}_{counter}{suffix}")

            # 复制或写入文件
            if ext in ('.epub', '.md', '.markdown', '.mobi', '.pdb'):
                shutil.copy2(abs_file_path, dest_path)
            else:
                with open(dest_path, 'w', encoding='utf-8') as f:
                    f.write(result.all_content)

            file_size = Path(dest_path).stat().st_size

            from datetime import datetime
            book_data = {
                'name': book_name,
                'file_path': str(Path(dest_path).resolve()),
                'original_encoding': result.encoding,
                'total_chapters': result.chapter_count,
                'file_size': file_size,
                'word_count': result.total_word_count,
                'added_time': datetime.now().isoformat(),
            }

            if self.data_store:
                self.data_store.add_book(book_data)

            book = Book.from_dict(book_name, book_data)
            logger.info(f"导入成功: {book_name}")
            return book

        except Exception as e:
            if 'dest_path' in locals() and Path(dest_path).exists():
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
            logger.error(f"导入失败: {book_name}: {type(e).__name__}: {e}")
            return None

    def rename_book(self, old_name: str, new_name: str) -> bool:
        book = self.get_book(old_name)
        if not book or old_name == new_name:
            return False
        clean_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', new_name).strip('. ')
        if not clean_name or self.has_book(clean_name):
            return False
        old_path = book.file_path
        ext = Path(old_path).suffix
        new_path = str(Path(self.books_dir) / (clean_name + ext))
        if Path(new_path).exists():
            return False
        try:
            os.rename(old_path, new_path)
        except OSError:
            return False

        if self.data_store:
            self.data_store.remove_book(old_name)
            book_data = book.to_dict()
            book_data['name'] = clean_name
            book_data['file_path'] = new_path
            self.data_store.add_book(book_data)
        return True

    def remove_book(self, name: str, delete_file: bool = False) -> bool:
        """移除书籍

        Args:
            name: 书籍名称
            delete_file: 是否删除文件

        Returns:
            是否移除成功
        """
        book = self.get_book(name)
        if not book:
            return False

        if delete_file and book.file_exists():
            try:
                os.remove(book.file_path)
            except OSError:
                pass

        if self.data_store:
            return self.data_store.remove_book(name)
        return False

    def get_book(self, name: str) -> Optional[Book]:
        """获取书籍

        Args:
            name: 书籍名称

        Returns:
            Book 对象，不存在返回 None
        """
        if self.data_store:
            data = self.data_store.get_book(name)
            if data:
                return Book.from_dict(name, data)
        return None

    def get_all_books_list(self) -> List[Book]:
        """获取所有书籍列表

        Returns:
            书籍列表
        """
        if self.data_store:
            books_data = self.data_store.get_books()
            return [Book.from_dict(d['name'], d) for d in books_data]
        return []

    def get_book_names(self) -> List[str]:
        """获取所有书籍名称

        Returns:
            书籍名称列表
        """
        if self.data_store:
            books_data = self.data_store.get_books()
            return [d['name'] for d in books_data]
        return []

    def has_book(self, name: str) -> bool:
        """检查书籍是否存在

        Args:
            name: 书籍名称

        Returns:
            是否存在
        """
        if self.data_store:
            return self.data_store.has_book(name)
        return False

    def update_book(self, name: str, updates: Dict[str, Any]) -> bool:
        """更新书籍信息

        Args:
            name: 书籍名称
            updates: 要更新的字段

        Returns:
            是否更新成功
        """
        if self.data_store:
            return self.data_store.update_book(name, updates)
        return False

    _SCAN_SAMPLE_SIZE = SCAN_SAMPLE_SIZE
    _SCAN_EPUB_SAMPLE_ITEMS = 5

    def _lightweight_scan_file(self, filepath: str, ext: str) -> dict:
        file_size = os.path.getsize(filepath)
        if ext == '.epub':
            return self._lightweight_scan_epub(filepath)
        if ext in ('.mobi', '.pdb'):
            return self._lightweight_scan_mobi(filepath)
        return self._lightweight_scan_text(filepath, file_size, ext)

    def _lightweight_scan_mobi(self, filepath: str) -> dict:
        """轻量扫描 MOBI 文件元数据"""
        file_size = os.path.getsize(filepath)
        try:
            import mobi
            tempdir, extracted_path = mobi.extract(filepath)
            ext = Path(extracted_path).suffix.lower()
            try:
                if ext == '.epub':
                    return self._lightweight_scan_epub(extracted_path)
                else:
                    # HTML 格式，按文件大小估算
                    with open(extracted_path, 'r', encoding='utf-8', errors='ignore') as f:
                        text = f.read()
                    word_count = len([c for c in text if not c.isspace()])
                    # 按 h1/h2/h3 估算章节数
                    import re
                    headings = re.findall(r'<h[123][^>]*>', text, re.IGNORECASE)
                    chapter_count = max(1, len(headings))
                    return {'word_count': word_count, 'chapter_count': chapter_count}
            finally:
                import shutil
                if tempdir and os.path.exists(tempdir):
                    shutil.rmtree(tempdir, ignore_errors=True)
        except Exception as e:
            logger.debug(f"MOBI 轻量扫描失败: {e}")
            return {'word_count': 0, 'chapter_count': 1}

    def _lightweight_scan_epub(self, filepath: str) -> dict:
        import zipfile
        with zipfile.ZipFile(filepath, 'r') as zf:
            doc_names = [
                n for n in zf.namelist()
                if n.lower().endswith(('.xhtml', '.html', '.htm'))
            ]
            chapter_count = max(1, len(doc_names))

            word_count = 0
            sampled = 0
            for name in doc_names[:self._SCAN_EPUB_SAMPLE_ITEMS]:
                try:
                    data = zf.read(name)
                    text = data.decode('utf-8', errors='ignore')
                    text = re.sub(r'<[^>]+>', ' ', text)
                    word_count += len([c for c in text if not c.isspace()])
                    sampled += 1
                except Exception:
                    continue

        if sampled > 0 and len(doc_names) > sampled:
            word_count = int(word_count / sampled * len(doc_names))

        return {'encoding': 'utf-8', 'chapter_count': chapter_count, 'word_count': word_count}

    def _lightweight_scan_text(self, filepath: str, file_size: int, ext: str) -> dict:
        sample_size = min(file_size, self._SCAN_SAMPLE_SIZE)

        with open(filepath, 'rb') as f:
            raw = f.read(sample_size)

        if not raw:
            return {'encoding': 'utf-8', 'chapter_count': 1, 'word_count': 0}

        # 复用已读的 raw bytes 检测编码，避免二次打开文件
        encoding = self._encoding_detector.detect_from_bytes(raw)

        try:
            sample_text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            sample_text = raw.decode('utf-8', errors='ignore')
            encoding = 'utf-8'

        if ext in ('.md', '.markdown'):
            chapter_count = sum(
                1 for line in sample_text.split('\n')
                if re.match(r'^#{1,6}\s+\S', line.strip())
            )
        else:
            chapter_count = sum(
                1 for line in sample_text.split('\n')
                if TextParser.is_chapter_title(line.strip())
            )

        sample_word_count = len([c for c in sample_text if not c.isspace()])

        if sample_size < file_size:
            ratio = file_size / sample_size
            word_count = int(sample_word_count * ratio)
            if chapter_count > 0:
                chapter_count = max(1, int(chapter_count * ratio))
        else:
            word_count = sample_word_count

        if chapter_count < 1:
            chapter_count = 1

        return {'encoding': encoding, 'chapter_count': chapter_count, 'word_count': word_count}

    def scan_books_directory(self) -> int:
        """扫描 books 目录，自动发现并注册目录中已有但书架中没有的书籍

        Returns:
            新发现并注册的书籍数量
        """
        if not Path(self.books_dir).is_dir():
            logger.warning(f"[扫描] 目录不存在: {self.books_dir}")
            return 0

        supported_exts = {'.txt', '.text', '.log', '.md', '.markdown', '.epub', '.mobi', '.pdb'}
        existing_paths = set()
        if self.data_store:
            for book_data in self.data_store.get_books():
                existing_paths.add(book_data.get('file_path', ''))
        
        new_count = 0

        for filename in os.listdir(self.books_dir):
            filepath = str(Path(self.books_dir) / filename)
            if not Path(filepath).is_file():
                continue
            ext = Path(filename).suffix.lower()
            if ext not in supported_exts:
                continue
            abs_filepath = str(Path(filepath).resolve())
            if abs_filepath in existing_paths:
                continue

            try:
                meta = self._lightweight_scan_file(filepath, ext)

                book_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(filepath).stem).strip('. ')

                if self.has_book(book_name):
                    continue

                file_size = Path(filepath).stat().st_size
                from datetime import datetime
                book_data = {
                    'name': book_name,
                    'file_path': abs_filepath,
                    'original_encoding': meta['encoding'],
                    'total_chapters': meta['chapter_count'],
                    'file_size': file_size,
                    'word_count': meta['word_count'],
                    'added_time': datetime.now().isoformat(),
                }
                
                if self.data_store:
                    self.data_store.add_book(book_data)
                new_count += 1
            except Exception as e:
                logger.warning(f"[扫描] 解析失败 {filename}: {e}")

        if new_count > 0:
            logger.info(f"扫描完成: 新增 {new_count} 本")
        return new_count
