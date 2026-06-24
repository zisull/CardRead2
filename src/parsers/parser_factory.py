"""解析器工厂模块

提供解析器的注册、查找和便捷访问。
使用装饰器注册模式，新增格式只需添加 @register_parser 装饰器即可。
"""
from typing import List, Optional

from .base_parser import BaseParser
from .registry import get_registry

from . import txt_parser, epub_parser, md_parser, mobi_parser


class ParserFactory:
    """解析器工厂 - 管理所有已注册的解析器"""

    def __init__(self):
        self._parsers: List[BaseParser] = get_registry()

    def get_parser(self, file_path: str) -> Optional[BaseParser]:
        for parser in self._parsers:
            if parser.supports(file_path):
                return parser
        return None

    def get_supported_extensions(self) -> List[str]:
        extensions = []
        for parser in self._parsers:
            for ext in parser.extensions:
                if ext not in extensions:
                    extensions.append(ext)
        return extensions

    def is_supported(self, file_path: str) -> bool:
        return self.get_parser(file_path) is not None


_factory: Optional[ParserFactory] = None


def _get_factory() -> ParserFactory:
    global _factory
    if _factory is None:
        _factory = ParserFactory()
    return _factory


def get_parser_for_file(file_path: str) -> Optional[BaseParser]:
    return _get_factory().get_parser(file_path)
