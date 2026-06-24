"""LRUCache 模块测试"""
import pytest

from src.utils.lru_cache import LRUCache


class TestLRUCache:
    """LRUCache 测试类"""
    
    def test_init(self):
        """测试初始化"""
        cache = LRUCache(capacity=10)
        assert cache.capacity == 10
        assert len(cache) == 0
    
    def test_put_and_get(self):
        """测试放入和获取"""
        cache = LRUCache(capacity=10)
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"
    
    def test_get_nonexistent(self):
        """测试获取不存在的键"""
        cache = LRUCache(capacity=10)
        assert cache.get("nonexistent") is None
    
    def test_update_existing(self):
        """测试更新现有键"""
        cache = LRUCache(capacity=10)
        cache.put("key1", "value1")
        cache.put("key1", "value2")
        assert cache.get("key1") == "value2"
    
    def test_capacity_limit(self):
        """测试容量限制"""
        cache = LRUCache(capacity=2)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.put("key3", "value3")  # 应该淘汰 key1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
    
    def test_lru_order(self):
        """测试 LRU 顺序"""
        cache = LRUCache(capacity=2)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.get("key1")  # 访问 key1，使其成为最近使用
        cache.put("key3", "value3")  # 应该淘汰 key2
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None
        assert cache.get("key3") == "value3"
    
    def test_remove(self):
        """测试删除"""
        cache = LRUCache(capacity=10)
        cache.put("key1", "value1")
        assert cache.remove("key1") == "value1"
        assert cache.get("key1") is None
    
    def test_remove_nonexistent(self):
        """测试删除不存在的键"""
        cache = LRUCache(capacity=10)
        assert cache.remove("nonexistent") is None
    
    def test_contains(self):
        """测试包含检查"""
        cache = LRUCache(capacity=10)
        cache.put("key1", "value1")
        assert cache.contains("key1") is True
        assert cache.contains("nonexistent") is False
    
    def test_clear(self):
        """测试清空"""
        cache = LRUCache(capacity=10)
        cache.put("key1", "value1")
        cache.put("key2", "value2")
        cache.clear()
        assert len(cache) == 0
        assert cache.get("key1") is None
    
    def test_size(self):
        """测试大小"""
        cache = LRUCache(capacity=10)
        assert cache.size() == 0
        cache.put("key1", "value1")
        assert cache.size() == 1
        cache.put("key2", "value2")
        assert cache.size() == 2
    
    def test_len(self):
        """测试 len 函数"""
        cache = LRUCache(capacity=10)
        assert len(cache) == 0
        cache.put("key1", "value1")
        assert len(cache) == 1
    
    def test_contains_operator(self):
        """测试 in 操作符"""
        cache = LRUCache(capacity=10)
        cache.put("key1", "value1")
        assert "key1" in cache
        assert "nonexistent" not in cache
    
    def test_getitem(self):
        """测试 [] 访问"""
        cache = LRUCache(capacity=10)
        cache.put("key1", "value1")
        assert cache["key1"] == "value1"
    
    def test_setitem(self):
        """测试 [] 赋值"""
        cache = LRUCache(capacity=10)
        cache["key1"] = "value1"
        assert cache.get("key1") == "value1"
    
    def test_delitem(self):
        """测试 del 操作"""
        cache = LRUCache(capacity=10)
        cache.put("key1", "value1")
        del cache["key1"]
        assert cache.get("key1") is None
