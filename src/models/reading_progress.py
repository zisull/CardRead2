"""阅读进度数据模型

定义阅读进度（ReadingProgress）和进度管理器（ProgressManager）的数据结构。
支持从字典序列化/反序列化，便于数据持久化。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, Iterator, Tuple


@dataclass(slots=True)
class ReadingProgress:
    """阅读进度数据模型

    Attributes:
        chapter: 当前章节索引
        scroll_percent: 滚动位置精度值（0-100000，万分比，用于精确定位）
        last_read: 最后阅读时间（ISO格式）
    """

    chapter: int = 0
    scroll_percent: int = 0
    last_read: Optional[str] = None

    def __post_init__(self):
        if self.last_read is None:
            self.last_read = datetime.now().isoformat()

    @property
    def position(self) -> int:
        """兼容旧代码的属性访问"""
        return self.scroll_percent

    @position.setter
    def position(self, value: int) -> None:
        """兼容旧代码的属性设置"""
        self.scroll_percent = value

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReadingProgress':
        """从字典创建阅读进度对象

        Args:
            data: 阅读进度数据字典

        Returns:
            ReadingProgress 对象
        """
        chapter = data.get('chapter', 0)
        if not isinstance(chapter, int) or chapter < 0:
            chapter = 0
        
        scroll_percent = data.get('scroll_percent', data.get('position', 0))
        if not isinstance(scroll_percent, int) or scroll_percent < 0 or scroll_percent > 100000:
            scroll_percent = 0
        
        last_read = data.get('last_read')
        if last_read is not None and not isinstance(last_read, str):
            last_read = None
        
        return cls(
            chapter=chapter,
            scroll_percent=scroll_percent,
            last_read=last_read
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            阅读进度数据字典
        """
        return {
            'chapter': self.chapter,
            'scroll_percent': self.scroll_percent,
            'last_read': self.last_read
        }

    def update(self, chapter: int, scroll_percent: int) -> None:
        """更新阅读进度

        Args:
            chapter: 章节索引
            scroll_percent: 滚动位置精度值（0-100000，万分比）
        """
        self.chapter = chapter
        self.scroll_percent = scroll_percent
        self.last_read = datetime.now().isoformat()

    def __repr__(self) -> str:
        return f"ReadingProgress(chapter={self.chapter}, pos={self.position})"


class ProgressManager:
    """阅读进度管理器

    管理所有书籍的阅读进度，支持进度的保存、恢复和查询。
    """

    __slots__ = ('_progress',)

    def __init__(self):
        """初始化进度管理器"""
        self._progress: Dict[str, ReadingProgress] = {}

    def get_progress(self, book_name: str) -> ReadingProgress:
        """获取书籍的阅读进度，不存在则创建

        Args:
            book_name: 书籍名称

        Returns:
            ReadingProgress 对象
        """
        if book_name not in self._progress:
            self._progress[book_name] = ReadingProgress()
        return self._progress[book_name]

    def has_progress(self, book_name: str) -> bool:
        """检查书籍是否有阅读进度

        Args:
            book_name: 书籍名称

        Returns:
            是否有进度记录
        """
        return book_name in self._progress

    def update_progress(self, book_name: str, chapter: int, position: int) -> None:
        """更新阅读进度

        Args:
            book_name: 书籍名称
            chapter: 章节索引
            position: 文本位置
        """
        if chapter < 0:
            chapter = 0
        if position < 0:
            position = 0
        progress = self.get_progress(book_name)
        progress.update(chapter, position)

    def remove_progress(self, book_name: str) -> bool:
        """移除阅读进度

        Args:
            book_name: 书籍名称

        Returns:
            是否移除成功
        """
        if book_name in self._progress:
            del self._progress[book_name]
            return True
        return False

    def get_last_read_book(self) -> Optional[str]:
        """获取最近阅读的书籍

        Returns:
            书籍名称，没有阅读记录返回 None
        """
        if not self._progress:
            return None

        last_book = None
        last_time = None

        for book_name, progress in self._progress.items():
            try:
                read_time = datetime.fromisoformat(progress.last_read)
                if last_time is None or read_time > last_time:
                    last_time = read_time
                    last_book = book_name
            except (ValueError, TypeError):
                continue

        return last_book

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        """转换为字典

        Returns:
            阅读进度数据字典
        """
        return {
            name: progress.to_dict()
            for name, progress in self._progress.items()
        }

    def load_from_dict(self, data: Dict[str, Dict[str, Any]]) -> None:
        """从字典加载

        Args:
            data: 阅读进度数据字典
        """
        self._progress.clear()
        for book_name, progress_data in data.items():
            self._progress[book_name] = ReadingProgress.from_dict(progress_data)

    def __len__(self) -> int:
        """返回有进度记录的书籍数量"""
        return len(self._progress)

    def __iter__(self) -> Iterator[Tuple[str, ReadingProgress]]:
        """迭代器"""
        return iter(self._progress.items())

    def clear(self) -> None:
        """清空所有阅读进度"""
        self._progress.clear()

    def __contains__(self, book_name: str) -> bool:
        """支持 in 操作符"""
        return book_name in self._progress
