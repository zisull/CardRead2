"""全局配置

集中管理软件名称、版本号等常量。
"""
from typing import Dict, Any

# 应用信息
APP_NAME = "Cardread Pro"
APP_DISPLAY_NAME = "Cardread Pro"
APP_AUTHOR = "zisull"
APP_VERSION = "0.0.1"
COPYRIGHT = "zisull@qq.com"

# 作者信息（说明页"作者"卡片内容，完全自定义）
# label: 显示标签，value: 内容，url: 可选链接（点击打开）
AUTHOR_INFO = [
    {"label": "作者", "value": "紫苏i @zisull"},
    {"label": "蓝奏云 下载", "value": "密码：cz4a", "url": "https://zisull.lanzoub.com/b02xfay1ah?pwd=cz4a"},
    {"label": "GitHub 下载", "value": "https://github.com/zisull/CardRead2",
     "url": "https://github.com/zisull/CardRead2/releases"},
    #    {"label": "主页", "value": "space.bilibili.com/210900168", "url": "https://space.bilibili.com/210900168"},
]

# 窗口配置
MAIN_WINDOW_HEIGHT = 800
MAIN_WINDOW_WIDTH = 1200
MIN_WINDOW_SIZE = (900, 650)

# 文件大小限制（字节）
MAX_IMPORT_SIZE = 200 * 1024 * 1024  # 200MB，导入文件大小限制
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB，单张图片大小限制（封面、内嵌图片通用）
MAX_IMAGE_DATA_URL_SIZE = 10 * 1024 * 1024  # 10MB，图片转 data URL 的大小限制
MAX_COVER_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB，封面图片大小限制
MAX_EPUB_SINGLE_IMAGE = 2 * 1024 * 1024  # 2MB，EPUB 单张内嵌图片上限（超过则跳过）
MAX_CHAPTER_IMAGE_TOTAL = 8 * 1024 * 1024  # 8MB，单章节图片总量上限（超过则跳过后续）

# 缓存配置
BOOKS_CACHE_CAPACITY = 500  # 书籍缓存容量
COVER_CACHE_CAPACITY = 500  # 封面缓存容量
PREVIEW_CACHE_CAPACITY = 500  # 预览缓存容量
ENCODING_CACHE_SIZE = 100  # 编码检测缓存大小

# 搜索配置
SEARCH_MAX_RESULTS_DEFAULT = 200  # search_in_book 默认最大结果数
SEARCH_MAX_RESULTS_LIMIT = 5000  # search_in_book 最大结果数上限
FTS5_MAX_RESULTS_DEFAULT = 100  # FTS5 搜索默认最大结果数

# 扫描配置
SCAN_SAMPLE_SIZE = 50 * 1024  # 扫描书籍时读取的样本大小（50KB）

# 延迟保存配置
SAVE_DELAY_SECONDS = 5.0  # 延迟保存时间（秒）

# 支持的文件格式
SUPPORTED_EXTENSIONS = {'.txt', '.text', '.log', '.md', '.markdown', '.epub', '.mobi', '.pdb'}

# 默认主题
DEFAULT_THEME = '深渊'

# 默认设置
DEFAULT_SETTINGS: Dict[str, Any] = {
    'current_theme': DEFAULT_THEME,
    'font_family': 'Microsoft YaHei',
    'font_size': 18,
    'font_color': '#2c3e50',
    'line_spacing': 1.8,
    'paragraph_spacing': 20,
    'text_indent': 2,
    'brightness': 1.0,
    'auto_next_chapter_enabled': True,
    'page_turn_mode': 'none',
    'page_turn_speed': 200,
    'nav_auto_hide': False,
    'background_image_opacity': 0.3,
    'background_image_scale_mode': 'cover',
    'reading_mode': 'scroll',
    'long_text_mode': True,
}


def get_version_text() -> str:
    """获取版本文本"""
    return f"v{APP_VERSION}"
