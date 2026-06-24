"""LRU 缓存实现

提供线程安全的 LRU 缓存，用于限制缓存大小，防止内存泄漏。
"""
from collections import OrderedDict
from threading import RLock
from typing import Any, Optional, TypeVar, Generic

T = TypeVar('T')

# 哨兵对象，用于区分"不存在"和"值为 None"
_MISSING = object()


class LRUCache(Generic[T]):
    """线程安全的 LRU 缓存
    
    当缓存达到容量上限时，自动淘汰最久未使用的项。
    
    Attributes:
        capacity: 缓存容量
    """
    
    def __init__(self, capacity: int = 1000):
        """初始化 LRU 缓存
        
        Args:
            capacity: 缓存容量，默认 1000
        """
        self._cache: OrderedDict[str, T] = OrderedDict()
        self._capacity = capacity
        self._lock = RLock()
    
    @property
    def capacity(self) -> int:
        """获取缓存容量"""
        return self._capacity
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值
        
        Args:
            key: 缓存键
            default: 键不存在时的默认返回值
            
        Returns:
            缓存值，不存在返回 default
        """
        with self._lock:
            if key in self._cache:
                # 移动到末尾（最近使用）
                self._cache.move_to_end(key)
                return self._cache[key]
            return default
    
    def put(self, key: str, value: T) -> None:
        """设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        with self._lock:
            if key in self._cache:
                # 更新现有值并移动到末尾
                self._cache.move_to_end(key)
            self._cache[key] = value
            # 超出容量时淘汰最久未使用的项
            while len(self._cache) > self._capacity:
                self._cache.popitem(last=False)
    
    def remove(self, key: str) -> Optional[T]:
        """移除缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            被移除的值，不存在返回 None
        """
        with self._lock:
            return self._cache.pop(key, None)
    
    def pop(self, key: str, default: Any = None) -> Optional[T]:
        """移除并返回缓存项
        
        兼容 dict.pop() 接口。
        
        Args:
            key: 缓存键
            default: 键不存在时的默认返回值
            
        Returns:
            被移除的值，不存在返回 default
        """
        with self._lock:
            return self._cache.pop(key, default)
    
    def contains(self, key: str) -> bool:
        """检查键是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在
        """
        with self._lock:
            if key in self._cache:
                # 更新访问顺序，将键移动到末尾（最近使用）
                self._cache.move_to_end(key)
                return True
            return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def size(self) -> int:
        """获取当前缓存大小
        
        Returns:
            缓存项数量
        """
        with self._lock:
            return len(self._cache)
    
    def keys(self) -> list:
        """获取所有键（按最近使用排序）
        
        Returns:
            键列表
        """
        with self._lock:
            return list(reversed(self._cache.keys()))
    
    def values(self) -> list:
        """获取所有值（按最近使用排序）
        
        Returns:
            值列表
        """
        with self._lock:
            return list(reversed(self._cache.values()))
    
    def items(self) -> list:
        """获取所有键值对（按最近使用排序）
        
        Returns:
            键值对列表
        """
        with self._lock:
            return list(reversed(self._cache.items()))
    
    def __len__(self) -> int:
        """获取缓存大小"""
        return self.size()
    
    def __contains__(self, key: str) -> bool:
        """支持 in 操作符"""
        return self.contains(key)
    
    def __getitem__(self, key: str) -> T:
        """支持 [] 访问"""
        value = self.get(key, _MISSING)
        if value is _MISSING:
            raise KeyError(key)
        return value
    
    def __setitem__(self, key: str, value: T) -> None:
        """支持 [] 赋值"""
        self.put(key, value)
    
    def __delitem__(self, key: str) -> None:
        """支持 del 操作"""
        if self.remove(key) is None:
            raise KeyError(key)
