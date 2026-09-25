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


class TestReadFileFallback:
    """回退路径改为「字节只读一次 + 内存逐个试解」，结果需与文本模式等价"""

    def test_fallback_matches_text_mode_read(self, detector, tmp_dir, monkeypatch):
        text = ('第一章 风起\r\n中文与English混排的内容\r\n'
                '第二行用孤立回车\r第三行用普通回车\n结束\r\n') * 4
        path = _write_file(tmp_dir, 'fallback_gbk.txt', text.encode('gbk'))
        # 强制首选编码，使主路径必然解码失败，从而走回退分支
        monkeypatch.setattr(detector, 'detect', lambda p: 'utf-8')

        content, enc = detector.read_file(path)

        assert enc == 'gb18030'
        assert content == open(path, 'r', encoding=enc).read()
        assert '\r' not in content

    @staticmethod
    def _legacy_read(path, forced_encoding):
        """改造前的实现：主编码失败后逐个候选「重新打开并全量读取」，逐字节保留其语义"""
        from src.utils.encoding import COMMON_ENCODINGS
        try:
            with open(path, 'r', encoding=forced_encoding) as f:
                return f.read(), forced_encoding
        except UnicodeDecodeError:
            pass
        for fb in COMMON_ENCODINGS:
            if fb != forced_encoding:
                try:
                    with open(path, 'r', encoding=fb) as f:
                        return f.read(), fb
                except (UnicodeDecodeError, OSError):
                    continue
        with open(path, 'r', encoding='gb18030', errors='ignore') as f:
            return f.read(), 'gb18030 (errors ignored)'

    @pytest.mark.parametrize('forced', ['utf-8', 'gbk', 'big5', 'shift_jis', 'utf-16-le', 'cp1252'])
    @pytest.mark.parametrize('sample', [
        '第一章 风起\r\n中文与English混排\r孤立回车\n普通回车\n',
        'plain ascii text\r\nonly\r\n',
        '日本語テスト\r\n한국어 그리고 ☃  snowman\n',
    ])
    def test_new_read_is_equivalent_to_legacy(self, detector, tmp_dir, monkeypatch, forced, sample):
        path = _write_file(tmp_dir, f'eq_{abs(hash((forced, sample))) % 10**8}.txt',
                           sample.encode('utf-8'))
        # 让主路径读的是「另一份内容」的等价物：统一以 utf-8 落盘，只改变首选解码编码
        monkeypatch.setattr(detector, 'detect', lambda p: forced)
        expected = self._legacy_read(path, forced)
        assert detector.read_file(path) == expected

    def test_translate_newlines(self, detector):
        assert detector._translate_newlines('a\r\nb\rc\n') == 'a\nb\nc\n'
        assert detector._translate_newlines('a\n\n\r\nb') == 'a\n\n\nb'
