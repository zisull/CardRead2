"""pytest 配置文件

提供通用的测试夹具和配置。
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 添加项目根目录到 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_text_file(temp_dir):
    """创建示例文本文件"""
    file_path = os.path.join(temp_dir, "sample.txt")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("第一章 测试章节\n\n这是测试内容。\n\n第二章 另一个章节\n\n更多测试内容。")
    return file_path


@pytest.fixture
def sample_markdown_file(temp_dir):
    """创建示例 Markdown 文件"""
    file_path = os.path.join(temp_dir, "sample.md")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("# 第一章\n\n这是测试内容。\n\n## 第一节\n\n子章节内容。\n\n# 第二章\n\n更多测试内容。")
    return file_path
