"""api.py 的辅助常量、函数和枚举类。

从 api.py 中提取的模块级定义，供 Api 类方法内部使用。
"""
import re
from enum import Enum
from typing import Any, Optional

from src.config import MAX_IMPORT_SIZE, MAX_IMAGE_SIZE, MAX_IMAGE_DATA_URL_SIZE

# 文件大小限制（从 config.py 导入）
_MAX_IMPORT_SIZE = MAX_IMPORT_SIZE
_MAX_IMAGE_SIZE = MAX_IMAGE_SIZE
_MAX_IMAGE_DATA_URL_SIZE = MAX_IMAGE_DATA_URL_SIZE

# 正则表达式
_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

_CH_LEVEL1_RE = re.compile(r'^#{1}\s+|^第.{1,4}[章回卷部集篇]|^Chapter\s*\d+|^Part\s*\d+|^\d+[\.\s]', re.I)
_CH_LEVEL2_RE = re.compile(r'^#{2}\s+|^第.{1,4}[节]|^\d+\.\d+[\.\s]', re.I)
_CH_LEVEL3_RE = re.compile(r'^#{3}\s+|^第.{1,4}[小]节|^\d+\.\d+\.\d+', re.I)

AVAILABLE_LAYOUTS = {'elegant', 'gallery', 'flow', 'vinyl', 'nautical'}

LAYOUTS_META = [
    {'id': 'nautical', 'name': '航海志', 'desc': '航海风格，船舵/锚元素，深蓝配色，罗盘装饰，大航海时代的阅读冒险'},
    {'id': 'vinyl', 'name': '黑胶片', 'desc': '唱片机界面风格，旋转唱片动画，黑红经典配色，复古音乐质感'},
    {'id': 'elegant', 'name': '极简风', 'desc': '优雅编号列表，留白多、专注阅读'},
    {'id': 'gallery', 'name': '仪表盘', 'desc': 'HUD 风格控制台，六边形图标 + 环形图表 + 冷蓝配色'},
    {'id': 'flow', 'name': '国风韵', 'desc': '中式水墨风格，印章装饰 + 楷体排版 + 文房意境'},
]


def _detect_chapter_level(title: str) -> int:
    if not title:
        return 1
    t = title.strip()
    if _CH_LEVEL3_RE.match(t):
        return 3
    if _CH_LEVEL2_RE.match(t):
        return 2
    if _CH_LEVEL1_RE.match(t):
        return 1
    return 1


def _get_cover_char(name: str) -> str:
    if not name:
        return '?'
    for ch in name:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            try:
                from pypinyin import lazy_pinyin
                result = lazy_pinyin(ch)
                if result and result[0]:
                    return result[0][0].upper()
            except Exception:
                pass
            return ch
        if ch.isalpha():
            return ch.upper()
        if ch.isdigit():
            return ch
    return name[0].upper() if name else '?'


def _get_pinyin_initials(name: str) -> str:
    """将名称转换为拼音首字母串（用于首字母搜索）。

    中文字符取拼音首字母（大写）；英文字母保留原样大写；数字保留；其他字符跳过。
    例：「射雕英雄传」→「SDYXZ」，「三体3体」→「ST3T」，「Harry Potter」→「HARRYPOTTER」

    Args:
        name: 书名或显示名

    Returns:
        大写首字母串，空名返回空串
    """
    if not name:
        return ''
    try:
        from pypinyin import lazy_pinyin
    except Exception:
        return ''
    parts = []
    # 把字符串按字符切，lazy_pinyin 接受字符串，逐字处理以确保非中文字符不被吞
    for ch in name:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            try:
                pys = lazy_pinyin(ch)
                if pys and pys[0]:
                    parts.append(pys[0][0].upper())
                else:
                    parts.append(ch.upper())
            except Exception:
                parts.append(ch.upper())
        elif ch.isalpha():
            parts.append(ch.upper())
        elif ch.isdigit():
            parts.append(ch)
        # 其他字符（标点、空格等）跳过，保持首字母串紧凑
    return ''.join(parts)


def _get_pinyin_full(name: str) -> str:
    """将名称转换为全拼音串（用于全拼音搜索）。

    中文字符转拼音，英文字母保留，数字保留，其他字符跳过。
    例：「射雕英雄传」→「shediaoyingxiongzhuan」，「三体3体」→「santi3ti」

    Args:
        name: 书名或显示名

    Returns:
        小写全拼音串，空名返回空串
    """
    if not name:
        return ''
    try:
        from pypinyin import lazy_pinyin
    except Exception:
        return ''
    # lazy_pinyin 对整个字符串批量处理，内部有优化
    pys = lazy_pinyin(name)
    parts = []
    for py in pys:
        # 拼音部分保留，非拼音（数字/英文/标点）只保留字母数字
        cleaned = ''.join(c for c in py if c.isalnum())
        if cleaned:
            parts.append(cleaned.lower())
    return ''.join(parts)


def _validate_book_name(book_name: str) -> bool:
    if not book_name or not book_name.strip():
        return False
    if '..' in book_name or '/' in book_name or '\\' in book_name:
        return False
    if any(c in book_name for c in '<>:"|?*\x00'):
        return False
    return True


class ErrorCode(str, Enum):
    BOOK_NOT_FOUND = 'BOOK_NOT_FOUND'
    FILE_NOT_FOUND = 'FILE_NOT_FOUND'
    PARSE_ERROR = 'PARSE_ERROR'
    SAVE_ERROR = 'SAVE_ERROR'
    INVALID_INPUT = 'INVALID_INPUT'
    ALREADY_EXISTS = 'ALREADY_EXISTS'
    ENCODING_ERROR = 'ENCODING_ERROR'
