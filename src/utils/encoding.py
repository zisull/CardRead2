"""编码检测工具模块

提供文件编码自动检测和读取功能。
支持多种常见编码格式，包括中文、日文、韩文等。
"""
import os
from collections import OrderedDict
from typing import Tuple, List

try:
    import chardet  # type: ignore
    # 验证 chardet 核心功能可用（Nuitka 打包时子模块可能缺失）
    chardet.detect(b'test')
    _HAS_CHARDET = True
except Exception:
    _HAS_CHARDET = False

COMMON_ENCODINGS: List[str] = [
    'utf-8-sig', 'utf-8',
    'gb18030', 'gbk', 'gb2312',
    'big5', 'big5hkscs',
    'shift_jis', 'cp932',
    'euc-jp', 'euc-kr',
    'cp1252', 'cp1251', 'cp1250',
    'iso-8859-1', 'iso-8859-2', 'iso-8859-5',
    'latin1',
    'ascii',
]


class EncodingDetector:
    """编码检测器 - 自动检测文件编码
    
    Attributes:
        confidence_threshold: 编码检测置信度阈值，低于此值将使用其他方法验证
        MAX_CACHE_SIZE: 编码缓存最大条目数
    """
    
    MAX_CACHE_SIZE = 100

    def __init__(self, confidence_threshold: float = 0.7):
        """初始化编码检测器
        
        Args:
            confidence_threshold: 编码检测置信度阈值，默认 0.7
        """
        self.confidence_threshold = confidence_threshold
        self._encoding_cache: OrderedDict = OrderedDict()

    def detect(self, file_path: str) -> str:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        cache_key = os.path.abspath(file_path)
        if cache_key in self._encoding_cache:
            cached_enc, cached_mtime, cached_size = self._encoding_cache[cache_key]
            try:
                stat = os.stat(file_path)
                if stat.st_mtime == cached_mtime and stat.st_size == cached_size:
                    # 移动到末尾（最近使用）
                    self._encoding_cache.move_to_end(cache_key)
                    return cached_enc
            except OSError:
                pass

        encoding = self._detect_encoding(file_path)
        if len(self._encoding_cache) >= self.MAX_CACHE_SIZE:
            # 移除最久未使用的项（OrderedDict 的第一个项）
            self._encoding_cache.popitem(last=False)
        try:
            stat = os.stat(file_path)
            self._encoding_cache[cache_key] = (encoding, stat.st_mtime, stat.st_size)
        except OSError:
            self._encoding_cache[cache_key] = (encoding, 0, 0)
        return encoding

    def _detect_from_bytes(self, raw: bytes) -> str:
        """从已读取的 bytes 检测编码（核心检测逻辑）。

        Args:
            raw: 文件内容的前 N 字节

        Returns:
            检测到的编码名称
        """
        if not raw:
            return 'utf-8'

        bom_encoding = self._check_bom(raw)
        if bom_encoding:
            return bom_encoding

        if _HAS_CHARDET:
            try:
                result = chardet.detect(raw)
                if result and result.get('encoding'):
                    enc = result['encoding'].lower()
                    confidence = result.get('confidence', 0)
                    normalized = self._normalize_encoding(enc)
                    if normalized:
                        try:
                            raw.decode(normalized)
                            if confidence >= self.confidence_threshold:
                                return normalized
                        except (UnicodeDecodeError, LookupError):
                            pass
            except Exception:
                pass

        has_high_bytes = any(b > 127 for b in raw[:4096])

        if has_high_bytes:
            for encoding in ['gbk', 'big5', 'shift_jis', 'euc-jp', 'euc-kr', 'gb18030']:
                try:
                    raw.decode(encoding)
                    return encoding
                except (UnicodeDecodeError, LookupError):
                    continue

        for encoding in ['utf-8-sig', 'utf-8', 'ascii']:
            try:
                raw.decode(encoding)
                return encoding
            except (UnicodeDecodeError, LookupError):
                continue

        return 'gb18030'

    def detect_from_bytes(self, raw: bytes) -> str:
        """从已读取的 bytes 检测编码（公共接口，无缓存）。

        适用于调用方已读取文件内容，避免二次打开文件。

        Args:
            raw: 文件内容的前 N 字节

        Returns:
            检测到的编码名称
        """
        return self._detect_from_bytes(raw)

    def _detect_encoding(self, file_path: str) -> str:
        with open(file_path, 'rb') as f:
            raw = f.read(65536)
        return self._detect_from_bytes(raw)

    def _check_bom(self, raw: bytes) -> str:
        if raw.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
        if raw.startswith(b'\xff\xfe'):
            return 'utf-16-le'
        if raw.startswith(b'\xfe\xff'):
            return 'utf-16-be'
        return ''

    def _normalize_encoding(self, encoding: str) -> str:
        encoding = encoding.lower().replace('-', '').replace('_', '')
        mapping = {
            'gb2312': 'gbk',
            'gb18030': 'gb18030',
            'gbk': 'gbk',
            'utf8': 'utf-8',
            'utf8sig': 'utf-8-sig',
            'ascii': 'utf-8',
            'big5': 'big5',
            'shiftjis': 'shift_jis',
            'cp932': 'shift_jis',
            'eucjp': 'euc-jp',
            'euckr': 'euc-kr',
            'latin1': 'latin1',
            'iso88591': 'latin1',
            'cp1252': 'cp1252',
            'windows1252': 'cp1252',
            'windows1251': 'cp1251',
            'windows1250': 'cp1250',
        }
        if encoding in mapping:
            return mapping[encoding]
        if encoding.startswith('iso8859'):
            return 'latin1'
        return encoding

    def read_file(self, file_path: str) -> Tuple[str, str]:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        encoding = self.detect(file_path)

        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            return content, encoding
        except UnicodeDecodeError:
            pass

        for fallback in COMMON_ENCODINGS:
            if fallback != encoding:
                try:
                    with open(file_path, 'r', encoding=fallback) as f:
                        content = f.read()
                    return content, fallback
                except (UnicodeDecodeError, OSError):
                    continue

        try:
            with open(file_path, 'r', encoding='gb18030', errors='ignore') as f:
                content = f.read()
            return content, 'gb18030 (errors ignored)'
        except OSError as e:
            raise IOError(f"无法读取文件: {e}")
