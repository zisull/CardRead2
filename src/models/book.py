"""书籍数据模型

定义书籍（Book）和书架（Bookshelf）的数据结构。
支持从字典序列化/反序列化，便于数据持久化。
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Iterator, Tuple


@dataclass(slots=True)
class Book:
    """书籍数据模型

    Attributes:
        name: 书籍名称（通常为文件名去掉扩展名）
        file_path: 文件路径
        original_encoding: 原始编码
        total_chapters: 总章节数
        file_size: 文件大小（字节）
        added_time: 添加时间（ISO格式）
        last_modified: 最后修改时间（ISO格式）
        current_encoding: 当前使用的编码（可能与原始编码不同）
    """

    name: str
    file_path: str
    original_encoding: str = 'utf-8'
    total_chapters: int = 0
    file_size: int = 0
    word_count: int = 0
    added_time: Optional[str] = None
    last_modified: Optional[str] = None
    current_encoding: Optional[str] = None
    display_name: Optional[str] = None

    def __post_init__(self):
        if self.added_time is None:
            self.added_time = datetime.now().isoformat()

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> 'Book':
        """从字典创建书籍对象

        Args:
            name: 书籍名称
            data: 书籍数据字典

        Returns:
            Book 对象
        """
        book = cls(
            name=name,
            file_path=data.get('file_path', ''),
            original_encoding=data.get('original_encoding', 'utf-8'),
            total_chapters=data.get('total_chapters', 0),
            file_size=data.get('file_size', 0),
            word_count=data.get('word_count', 0),
            added_time=data.get('added_time'),
            last_modified=data.get('last_modified'),
            display_name=data.get('display_name')
        )
        book.current_encoding = data.get('current_encoding')
        return book

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            书籍数据字典
        """
        result = {
            'file_path': self.file_path,
            'original_encoding': self.original_encoding,
            'total_chapters': self.total_chapters,
            'file_size': self.file_size,
            'word_count': self.word_count,
            'added_time': self.added_time,
            'last_modified': self.last_modified,
        }
        if self.current_encoding:
            result['current_encoding'] = self.current_encoding
        if self.display_name is not None:
            result['display_name'] = self.display_name
        return result

    def file_exists(self) -> bool:
        """检查文件是否存在

        Returns:
            文件是否存在
        """
        return Path(self.file_path).is_file()

    def get_display_name(self) -> str:
        if self.display_name:
            return self.display_name
        return self.name

    def get_display_size(self) -> str:
        """获取显示用的文件大小

        Returns:
            格式化的文件大小字符串（如 "1.5MB"）
        """
        if self.file_size > 1024 * 1024:
            return f"{self.file_size / (1024 * 1024):.1f}MB"
        elif self.file_size > 1024:
            return f"{self.file_size / 1024:.1f}KB"
        return f"{self.file_size}B"

    def __repr__(self) -> str:
        return (f"Book(name='{self.name}', chapters={self.total_chapters}, "
                f"size={self.get_display_size()})")


class Bookshelf:
    """书架管理类

    管理书籍的增删改查，支持序列化/反序列化。
    """

    __slots__ = ('_books',)

    def __init__(self):
        """初始化书架"""
        self._books: Dict[str, Book] = {}

    def add_book(self, book: Book) -> None:
        """添加书籍

        Args:
            book: Book 对象
        """
        self._books[book.name] = book

    def remove_book(self, name: str) -> bool:
        """移除书籍

        Args:
            name: 书籍名称

        Returns:
            是否移除成功
        """
        if name in self._books:
            del self._books[name]
            return True
        return False

    def get_book(self, name: str) -> Optional[Book]:
        """获取书籍

        Args:
            name: 书籍名称

        Returns:
            Book 对象，不存在返回 None
        """
        return self._books.get(name)

    def has_book(self, name: str) -> bool:
        """检查书籍是否存在

        Args:
            name: 书籍名称

        Returns:
            是否存在
        """
        return name in self._books

    def get_book_names(self) -> list:
        """获取所有书籍名称

        Returns:
            书籍名称列表
        """
        return list(self._books.keys())

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """转换为字典

        Returns:
            书架数据字典
        """
        return {name: book.to_dict() for name, book in self._books.items()}

    def load_from_dict(self, data: Dict[str, Dict[str, Any]]) -> None:
        """从字典加载

        Args:
            data: 书架数据字典
        """
        self._books.clear()
        for name, book_data in data.items():
            self._books[name] = Book.from_dict(name, book_data)

    def __len__(self) -> int:
        """获取书籍数量"""
        return len(self._books)

    def __iter__(self) -> Iterator[Tuple[str, Book]]:
        """迭代器"""
        return iter(self._books.items())

    def clear(self) -> None:
        """清空所有书籍"""
        self._books.clear()

    def __contains__(self, name: str) -> bool:
        """支持 in 操作符"""
        return name in self._books
