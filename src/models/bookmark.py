"""书签数据模型

定义书签（Bookmark）和书签管理器（BookmarkManager）的数据结构。
支持从字典序列化/反序列化，便于数据持久化。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional, Iterator


@dataclass(slots=True)
class Bookmark:
    """书签数据模型

    Attributes:
        chapter: 章节索引
        position: 文本位置（字符偏移量）
        description: 书签描述
        time: 创建时间（ISO格式）
    """

    chapter: int
    position: int
    description: str
    time: Optional[str] = None

    def __post_init__(self):
        if self.time is None:
            self.time = datetime.now().isoformat()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Bookmark':
        """从字典创建书签对象

        Args:
            data: 书签数据字典

        Returns:
            Bookmark 对象
        """
        chapter = data.get('chapter', 0)
        if not isinstance(chapter, int) or chapter < 0:
            chapter = 0
        
        position = data.get('position', 0)
        if not isinstance(position, int) or position < 0:
            position = 0
        
        description = data.get('description', '')
        if not isinstance(description, str):
            description = ''
        
        time = data.get('time')
        if time is not None and not isinstance(time, str):
            time = None
        
        return cls(
            chapter=chapter,
            position=position,
            description=description,
            time=time
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            书签数据字典
        """
        return {
            'chapter': self.chapter,
            'position': self.position,
            'description': self.description,
            'time': self.time
        }

    def __repr__(self) -> str:
        desc = self.description[:20] + '...' if len(self.description) > 20 else self.description
        return f"Bookmark(chapter={self.chapter}, pos={self.position}, desc='{desc}')"


class BookmarkManager:
    """书签管理器

    管理所有书籍的书签，支持增删改查和序列化/反序列化。
    """

    __slots__ = ('_bookmarks',)

    def __init__(self):
        """初始化书签管理器"""
        self._bookmarks: Dict[str, List[Bookmark]] = {}

    def add_bookmark(self, book_name: str, bookmark: Bookmark) -> None:
        """添加书签

        Args:
            book_name: 书籍名称
            bookmark: Bookmark 对象
        """
        if book_name not in self._bookmarks:
            self._bookmarks[book_name] = []
        self._bookmarks[book_name].append(bookmark)

    def update_bookmark(self, book_name: str, index: int, description: str) -> bool:
        bookmarks = self._bookmarks.get(book_name, [])
        if 0 <= index < len(bookmarks):
            bookmarks[index].description = description
            return True
        return False

    def remove_bookmark(self, book_name: str, index: int) -> bool:
        """移除书签

        Args:
            book_name: 书籍名称
            index: 书签索引

        Returns:
            是否移除成功
        """
        bookmarks = self._bookmarks.get(book_name, [])
        if 0 <= index < len(bookmarks):
            del bookmarks[index]
            return True
        return False

    def remove_book_bookmarks(self, book_name: str) -> bool:
        """移除书籍的所有书签

        Args:
            book_name: 书籍名称

        Returns:
            是否移除成功
        """
        if book_name in self._bookmarks:
            del self._bookmarks[book_name]
            return True
        return False

    def get_bookmarks(self, book_name: str) -> List[Bookmark]:
        """获取书籍的所有书签

        Args:
            book_name: 书籍名称

        Returns:
            书签列表
        """
        return self._bookmarks.get(book_name, [])

    def get_bookmark(self, book_name: str, index: int) -> Optional[Bookmark]:
        """获取指定书签

        Args:
            book_name: 书籍名称
            index: 书签索引

        Returns:
            Bookmark 对象，不存在返回 None
        """
        bookmarks = self.get_bookmarks(book_name)
        if 0 <= index < len(bookmarks):
            return bookmarks[index]
        return None

    def has_bookmarks(self, book_name: str) -> bool:
        """检查书籍是否有书签

        Args:
            book_name: 书籍名称

        Returns:
            是否有书签
        """
        return len(self.get_bookmarks(book_name)) > 0

    def count_bookmarks(self, book_name: Optional[str] = None) -> int:
        """统计书签数量

        Args:
            book_name: 书籍名称，为 None 时返回所有书籍的书签总数

        Returns:
            书签数量
        """
        if book_name is not None:
            return len(self.get_bookmarks(book_name))
        return sum(len(bms) for bms in self._bookmarks.values())

    def get_book_names(self) -> List[str]:
        """获取所有有书签的书籍名称

        Returns:
            书籍名称列表
        """
        return [name for name, bms in self._bookmarks.items() if bms]

    def to_dict(self) -> Dict[str, List[Dict[str, Any]]]:
        """转换为字典

        Returns:
            书签数据字典
        """
        return {
            name: [bm.to_dict() for bm in bookmarks]
            for name, bookmarks in self._bookmarks.items()
        }

    def load_from_dict(self, data: Dict[str, List[Dict[str, Any]]]) -> None:
        """从字典加载

        Args:
            data: 书签数据字典
        """
        self._bookmarks.clear()
        for book_name, bookmarks_data in data.items():
            self._bookmarks[book_name] = [
                Bookmark.from_dict(bm_data) for bm_data in bookmarks_data
            ]

    def __len__(self) -> int:
        """返回总书签数"""
        return self.count_bookmarks()

    def __iter__(self) -> Iterator[str]:
        """迭代有书签的书籍名称"""
        return iter(self.get_book_names())

    def clear(self) -> None:
        """清空所有书签"""
        self._bookmarks.clear()

    def __contains__(self, book_name: str) -> bool:
        """支持 in 操作符"""
        return self.has_bookmarks(book_name)
