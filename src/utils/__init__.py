"""工具函数模块

提供文件操作、编码检测、文本解析等通用工具功能。
"""

from .encoding import EncodingDetector
from .file_utils import (
    get_resource_dirs,
    ensure_dirs_exist,
)
from .text_parser import TextParser

__all__ = [
    # file_utils
    'get_resource_dirs',
    'ensure_dirs_exist',
    # encoding
    'EncodingDetector',
    # text_parser
    'TextParser',
]
