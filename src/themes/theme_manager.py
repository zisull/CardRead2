"""主题管理器

负责主题的加载、保存和切换。
主题只存储核心色（bg/fg/accent/tip/font_color），展开由 expand_theme 完成。
"""
import json
from pathlib import Path
from typing import Dict, Optional, List

from .theme_styles import expand_theme


class ThemeManager:
    """主题管理器"""

    def __init__(self, theme_dir: str):
        self.theme_dir = Path(theme_dir)
        self.theme_dir.mkdir(parents=True, exist_ok=True)

        self._core_themes: Dict[str, dict] = {}
        self.current_theme: str = "珍珠"

        self._load_builtin_themes()
        self._load_user_themes()

    def _load_builtin_themes(self) -> None:
        from .theme_styles import CORE_THEMES
        self._core_themes.update(CORE_THEMES)

    def _load_user_themes(self) -> None:
        for theme_file in self.theme_dir.glob("*.json"):
            try:
                with open(theme_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                name = theme_file.stem
                if 'bg' in data and 'fg' in data and 'accent' in data:
                    self._core_themes[name] = data
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                continue

    def get_theme(self, name: str) -> Optional[dict]:
        core = self._core_themes.get(name)
        if core:
            return expand_theme(core)
        return None

    def get_current_theme(self) -> dict:
        fallback = {"bg": "#f5eed8", "fg": "#4a4030", "accent": "#b09050"}
        return self.get_theme(self.current_theme) or expand_theme(self._core_themes.get("深渊", fallback))

    def get_theme_names(self) -> List[str]:
        return list(self._core_themes.keys())

    def get_theme_core(self, name: str) -> Optional[dict]:
        return self._core_themes.get(name)

    def set_theme(self, name: str, save: bool = True) -> bool:
        if name not in self._core_themes:
            return False
        self.current_theme = name
        if save:
            self.save_current_theme()
        return True

    def has_core_theme(self, name: str) -> bool:
        return name in self._core_themes

    def set_core_theme(self, name: str, colors: dict) -> None:
        self._core_themes[name] = {
            'bg': colors.get('bg', '#f5eed8'),
            'fg': colors.get('fg', '#4a4030'),
            'accent': colors.get('accent', '#b09050'),
            'tip': colors.get('tip', '#888070'),
            'font_color': colors.get('font_color', colors.get('fg', '#4a4030')),
        }

    def remove_core_theme(self, name: str) -> bool:
        if name in self._core_themes:
            del self._core_themes[name]
            return True
        return False

    def update_theme_colors(self, name: str, bg: str, fg: str, accent: str, tip: str = None, font_color: str = None) -> None:
        if name in self._core_themes:
            existing = self._core_themes[name]
            core = {'bg': bg, 'fg': fg, 'accent': accent}
            core['tip'] = tip if tip is not None else existing.get('tip', '#8b8070')
            if font_color is not None:
                core['font_color'] = font_color
            elif 'font_color' in existing:
                core['font_color'] = existing['font_color']
            self._core_themes[name] = core

    def save_current_theme(self) -> None:
        if self.current_theme.startswith('ct_'):
            return
        core = self._core_themes.get(self.current_theme)
        if not core:
            return
        theme_file = self.theme_dir / f"{self.current_theme}.json"
        try:
            with open(theme_file, 'w', encoding='utf-8') as f:
                json.dump(core, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
