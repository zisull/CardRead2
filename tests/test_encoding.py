"""编码检测工具测试

测试 EncodingDetector 的编码检测、字节检测和别名处理。
"""
import os
import tempfile
import pytest

from src.utils.encoding import EncodingDetector


@pytest.fixture
def detector():
    return EncodingDetector()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _write_file(tmp_dir, name, content_bytes):
    path = os.path.join(tmp_dir, name)
    with open(path, 'wb') as f:
        f.write(content_bytes)
    return path


class TestEncodingDetector:
    def test_detect_utf8(self, detector, tmp_dir):
        path = _write_file(tmp_dir, 'test.txt', '你好世界'.encode('utf-8'))
        enc = detector.detect(path)
        assert enc in ('utf-8', 'utf-8-sig')

    def test_detect_gbk(self, detector, tmp_dir):
        path = _write_file(tmp_dir, 'test.txt', '你好世界'.encode('gbk'))
        enc = detector.detect(path)
        assert enc in ('gbk', 'gb18030', 'gb2312')

    def test_detect_ascii(self, detector, tmp_dir):
        path = _write_file(tmp_dir, 'test.txt', b'hello world')
        enc = detector.detect(path)
        assert enc in ('ascii', 'utf-8')

    def test_detect_empty_file(self, detector, tmp_dir):
        path = _write_file(tmp_dir, 'empty.txt', b'')
        enc = detector.detect(path)
        assert enc == 'utf-8'

    def test_detect_from_bytes_utf8(self, detector):
        raw = '你好世界'.encode('utf-8')
        enc = detector.detect_from_bytes(raw)
        assert enc in ('utf-8', 'utf-8-sig')

    def test_detect_from_bytes_gbk(self, detector):
        raw = '你好世界'.encode('gbk')
        enc = detector.detect_from_bytes(raw)
        assert enc in ('gbk', 'gb18030', 'gb2312')

    def test_detect_from_bytes_empty(self, detector):
        enc = detector.detect_from_bytes(b'')
        assert enc == 'utf-8'

    def test_detect_from_bytes_ascii(self, detector):
        enc = detector.detect_from_bytes(b'hello world')
        assert enc in ('ascii', 'utf-8')

    def test_detect_nonexistent_file(self, detector):
        with pytest.raises(FileNotFoundError):
            detector.detect('/nonexistent/path.txt')

    def test_read_file_utf8(self, detector, tmp_dir):
        path = _write_file(tmp_dir, 'test.txt', '你好'.encode('utf-8'))
        content, enc = detector.read_file(path)
        assert content == '你好'
        assert enc in ('utf-8', 'utf-8-sig')

    def test_read_file_gbk(self, detector, tmp_dir):
        path = _write_file(tmp_dir, 'test.txt', '你好'.encode('gbk'))
        content, enc = detector.read_file(path)
        assert content == '你好'

    def test_detect_bom_utf8(self, detector, tmp_dir):
        path = _write_file(tmp_dir, 'test.txt', b'\xef\xbb\xbfhello')
        enc = detector.detect(path)
        assert enc == 'utf-8-sig'

    def test_detect_bom_utf16_le(self, detector, tmp_dir):
        path = _write_file(tmp_dir, 'test.txt', b'\xff\xfehello')
        enc = detector.detect(path)
        assert enc == 'utf-16-le'

    def test_detect_bom_utf16_be(self, detector, tmp_dir):
        path = _write_file(tmp_dir, 'test.txt', b'\xfe\xffhello')
        enc = detector.detect(path)
        assert enc == 'utf-16-be'

    def test_normalize_encoding_windows_1252(self, detector):
        """Windows-1252 别名应正确映射到 cp1252"""
        # chardet 可能返回 'Windows-1252'，_normalize_encoding 处理后应为 'cp1252'
        enc = detector._normalize_encoding('windows-1252')
        assert enc == 'cp1252'

    def test_normalize_encoding_windows_1251(self, detector):
        enc = detector._normalize_encoding('windows-1251')
        assert enc == 'cp1251'

    def test_normalize_encoding_windows_1250(self, detector):
        enc = detector._normalize_encoding('windows-1250')
        assert enc == 'cp1250'

    def test_normalize_encoding_common(self, detector):
        assert detector._normalize_encoding('utf-8') == 'utf-8'
        assert detector._normalize_encoding('gbk') == 'gbk'
        assert detector._normalize_encoding('ascii') == 'utf-8'
        assert detector._normalize_encoding('latin1') == 'latin1'

    def test_cache_hit(self, detector, tmp_dir):
        """第二次检测同一文件应命中缓存"""
        path = _write_file(tmp_dir, 'test.txt', '你好'.encode('utf-8'))
        enc1 = detector.detect(path)
        enc2 = detector.detect(path)
        assert enc1 == enc2
        assert path in [k for k in detector._encoding_cache.keys()] or \
               os.path.abspath(path) in detector._encoding_cache

    def test_detect_from_bytes_does_not_cache(self, detector):
        """detect_from_bytes 不做缓存（无文件路径）"""
        raw = 'hello'.encode('utf-8')
        detector.detect_from_bytes(raw)
        assert len(detector._encoding_cache) == 0
