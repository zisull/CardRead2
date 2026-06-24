"""主题样式定义

内置主题配色与展开逻辑。
"""
import colorsys
from functools import lru_cache
from typing import Dict, List, Tuple


CORE_THEMES: Dict[str, Dict[str, str]] = {
    # ══ 10 个深色主题 ══
    # 海蓝（最深，接近纯黑的深海蓝）
    "深渊":   {"bg": "#060c16", "fg": "#b0d0f0", "accent": "#40c8ff", "tip": "#4870a0", "font_color": "#a0c0e0"},
    # 钢蓝灰（冷调中性，不偏紫不偏绿）
    "子夜":   {"bg": "#0e1118", "fg": "#b8c0d0", "accent": "#6078c0", "tip": "#506078", "font_color": "#a8b0c0"},
    # 纯正森林绿
    "幽林":   {"bg": "#0a1610", "fg": "#b0e0c0", "accent": "#30d880", "tip": "#489068", "font_color": "#a0d0b0"},
    # 深靛蓝（纯蓝，不偏紫不偏绿）
    "靛蓝":   {"bg": "#0a0e1e", "fg": "#b0c0e8", "accent": "#4080ff", "tip": "#4858a0", "font_color": "#a0b0d8"},
    # 暖灰（纯中性灰偏暖，不带蓝不带紫）
    "暮烟":   {"bg": "#141210", "fg": "#d0c8c0", "accent": "#b08080", "tip": "#706860", "font_color": "#c0b8b0"},
    # 深紫（纯正紫色，与靛蓝的蓝色系拉开）
    "紫夜":   {"bg": "#12081c", "fg": "#c8b8e0", "accent": "#9850e8", "tip": "#6848a0", "font_color": "#b8a8d0"},
    # 酒红（暖调深红，与紫夜的冷紫拉开）
    "酒红":   {"bg": "#180a0e", "fg": "#e0c0c8", "accent": "#d04060", "tip": "#985868", "font_color": "#d0b0b8"},
    # 金棕（暖调金色，最暖的深色主题）
    "琥珀":   {"bg": "#1a1408", "fg": "#e8d8b0", "accent": "#e8a028", "tip": "#a09050", "font_color": "#dcd0a0"},
    # 暗铜（暖调红棕，比琥珀更偏红）
    "柿饼":   {"bg": "#1a0e08", "fg": "#e0c8b0", "accent": "#c87040", "tip": "#a07050", "font_color": "#d8bca0"},
    # 冰蓝（冷调浅灰蓝，最亮的深色主题）
    "冰川":   {"bg": "#141a22", "fg": "#c0d0e0", "accent": "#50b8e0", "tip": "#587890", "font_color": "#b0c0d0"},
    # ══ 10 个浅色主题 ══
    # 暖白（最浅，微微偏暖的米白）
    "珍珠":   {"bg": "#f2f0ec", "fg": "#383430", "accent": "#2868b0", "tip": "#808888", "font_color": "#484440"},
    # 蓝灰（冷调浅灰，微微偏蓝）
    "月白":   {"bg": "#e8ecf0", "fg": "#2a3040", "accent": "#3080d0", "tip": "#707888", "font_color": "#3a4050"},
    # 淡蓝紫（冷调蓝紫，比月白更偏紫）
    "雾蓝":   {"bg": "#e8eaf4", "fg": "#282848", "accent": "#6070d0", "tip": "#707898", "font_color": "#383858"},
    # 薰衣草（纯正淡紫，与雾蓝的蓝紫拉开）
    "丁香":   {"bg": "#ece4f0", "fg": "#382040", "accent": "#9050c8", "tip": "#887898", "font_color": "#483050"},
    # 暖粉（偏桃色的粉，不偏紫）
    "裸粉":   {"bg": "#f4e8e4", "fg": "#482828", "accent": "#d85060", "tip": "#a88888", "font_color": "#583838"},
    # 暖黄（纯正浅黄，最暖的浅色主题）
    "鹅黄":   {"bg": "#f8f2e0", "fg": "#403818", "accent": "#c88820", "tip": "#a09060", "font_color": "#504828"},
    # 冷银灰（纯中性灰，不偏蓝不偏暖）
    "银灰":   {"bg": "#e8e8e8", "fg": "#303030", "accent": "#6088a0", "tip": "#787878", "font_color": "#404040"},
    # 绿松石（冷调浅绿，独特色系）
    "青碧":   {"bg": "#e4f0ec", "fg": "#183830", "accent": "#20a078", "tip": "#608880", "font_color": "#284840"},
    # 奶白（暖调极浅，比珍珠更暖更亮）
    "云白":   {"bg": "#f6f2ea", "fg": "#403828", "accent": "#a88040", "tip": "#989080", "font_color": "#504838"},
    # 紫粉（暖调偏紫的粉，与裸粉的桃色拉开）
    "桃夭":   {"bg": "#f2e8ee", "fg": "#402038", "accent": "#c04888", "tip": "#a07898", "font_color": "#503048"},
}

THEME_CYCLE: List[str] = [
    "深渊", "珍珠", "子夜", "月白", "幽林", "雾蓝",
    "靛蓝", "丁香", "暮烟", "裸粉", "紫夜", "鹅黄",
    "酒红", "银灰", "琥珀", "青碧", "柿饼", "云白",
    "冰川", "桃夭",
]


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _mix_color(c1: str, c2: str, ratio: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        int(r1 + (r2 - r1) * ratio),
        int(g1 + (g2 - g1) * ratio),
        int(b1 + (b2 - b1) * ratio),
    )


def _lighten(hex_color: str, factor: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(
        int(r + (255 - r) * factor),
        int(g + (255 - g) * factor),
        int(b + (255 - b) * factor),
    )


def _is_light(hex_color: str) -> bool:
    r, g, b = _hex_to_rgb(hex_color)
    return (r * 299 + g * 587 + b * 114) / 1000 > 160


def _shift_hue(hex_color: str, degrees: float) -> str:
    """将颜色色相旋转指定角度（度），保持明度与饱和度不变。"""
    r, g, b = _hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    h = (h + degrees / 360.0) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return _rgb_to_hex(int(r * 255), int(g * 255), int(b * 255))


@lru_cache(maxsize=64)
def _expand_theme_cached(
    bg: str,
    fg: str,
    accent: str,
    tip: str = None,
    font_color: str = None,
) -> Dict[str, str]:
    """从核心色展开完整主题配色（缓存版本）。"""
    if _is_light(bg):
        secondary = _lighten(bg, 0.03)
        text_bg = _lighten(bg, 0.04)
        card_bg = _lighten(bg, 0.02)
        border = _mix_color(bg, fg, 0.15)
        shadow_alpha = 0.06
    else:
        secondary = _lighten(bg, 0.06)
        text_bg = _lighten(bg, 0.04)
        card_bg = _lighten(bg, 0.05)
        border = _lighten(bg, 0.18)
        shadow_alpha = 0.3

    accent_light = _lighten(accent, 0.2)
    accent2 = _shift_hue(accent, 25)
    resolved_tip = tip or _mix_color(fg, bg, 0.5)
    resolved_font_color = font_color or fg

    is_dark = not _is_light(bg)
    if is_dark:
        code_bg = _lighten(bg, 0.08)
        code_color = _lighten(fg, 0.1)
    else:
        code_bg = _lighten(bg, -0.04)
        code_color = _lighten(fg, -0.1)

    ar, ag, ab = _hex_to_rgb(accent)
    highlight = f"rgba({ar},{ag},{ab},0.12)"

    return {
        'bg': bg,
        'fg': fg,
        'accent': accent,
        'accent2': accent2,
        'accent_light': accent_light,
        'secondary': secondary,
        'text_bg': text_bg,
        'card_bg': card_bg,
        'border': border,
        'tip': resolved_tip,
        'font_color': resolved_font_color,
        'shadow': f"0 2px 4px rgba(0, 0, 0, {shadow_alpha})",
        'highlight': highlight,
        'code_bg': code_bg,
        'code_color': code_color,
    }


def expand_theme(core: Dict[str, str]) -> Dict[str, str]:
    """从核心色展开完整主题配色。"""
    return dict(_expand_theme_cached(
        bg=core['bg'],
        fg=core['fg'],
        accent=core['accent'],
        tip=core.get('tip'),
        font_color=core.get('font_color'),
    ))
