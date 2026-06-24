"""解析器注册表模块

提供装饰器注册模式，避免循环导入。
"""
from typing import List

from .base_parser import BaseParser

_PARSER_REGISTRY: List[BaseParser] = []


def register_parser(cls):
    """注册解析器类的装饰器

    装饰器会实例化解析器类并添加到全局注册表中。
    注册顺序影响优先级（后注册的优先级更高）。
    """
    _PARSER_REGISTRY.append(cls())
    return cls


def get_registry() -> List[BaseParser]:
    """获取注册表的副本（反转顺序，后注册的优先级更高）"""
    return list(reversed(_PARSER_REGISTRY))
