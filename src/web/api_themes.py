"""主题与设置 Mixin

提供主题管理、自定义配色、布局切换、设置读写等接口。
"""
import json
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.web.api_helpers import _COLOR_RE, AVAILABLE_LAYOUTS, LAYOUTS_META


class ThemesMixin:
    """主题与设置操作"""

    # ── 主题 ──

    def _invalidate_themes_cache(self) -> None:
        self._all_themes_cache = None

    def get_themes(self) -> List[str]:
        return self._theme_manager.get_theme_names()

    def get_all_themes(self) -> List[Dict[str, Any]]:
        if self._all_themes_cache is not None:
            return self._all_themes_cache
        names = self._theme_manager.get_theme_names()
        result = []
        for name in names:
            core = self._theme_manager.get_theme_core(name)
            if core:
                fg = core.get('fg', '#4a4030')
                result.append({
                    'name': name,
                    'bg': core.get('bg', '#f5eed8'),
                    'fg': fg,
                    'accent': core.get('accent', '#b09050'),
                    'tip': core.get('tip', '#888070'),
                    'font_color': core.get('font_color', fg),
                })
        self._all_themes_cache = result
        return result

    def get_current_theme(self) -> Dict[str, Any]:
        return self._theme_manager.get_current_theme()

    def set_theme(self, theme_name: str) -> Dict[str, Any]:
        try:
            if theme_name.startswith('ct_'):
                self._ensure_custom_theme_in_core(theme_name)
                if self._theme_manager.has_core_theme(theme_name):
                    self._theme_manager.current_theme = theme_name
                    self._data_store.set_setting('current_theme', theme_name)
                    self._save_deferred()
                    return self._theme_manager.get_current_theme()
                return {}
            self._theme_manager.set_theme(theme_name)
            self._data_store.set_setting('current_theme', theme_name)
            self._save_deferred()
            self._invalidate_themes_cache()
            return self._theme_manager.get_current_theme()
        except Exception as e:
            logger.error(f"设置主题失败: {e}")
            return {}

    def get_next_theme_name(self) -> str:
        from src.themes.theme_styles import THEME_CYCLE
        current = self._theme_manager.current_theme
        if current in THEME_CYCLE:
            idx = THEME_CYCLE.index(current)
            return THEME_CYCLE[(idx + 1) % len(THEME_CYCLE)]
        return THEME_CYCLE[0]

    def export_theme_color(self) -> Optional[str]:
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename='theme.color',
                file_types=('配色文件 (*.color)',),
            )
            if not result:
                return None
            save_path = result if isinstance(result, str) else result[0]
            if not save_path.endswith('.color'):
                save_path += '.color'
            cur = self._theme_manager.get_current_theme()
            colors = {
                'bg': cur.get('bg', '#f5eed8'),
                'fg': cur.get('fg', '#4a4030'),
                'accent': cur.get('accent', '#b09050'),
                'tip': cur.get('tip', '#888070'),
                'font_color': cur.get('font_color', '#4a4030'),
            }
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(colors, f, ensure_ascii=False, indent=2)
            return save_path
        except Exception as e:
            logger.error(f"导出配色失败: {e}")
            return None

    def import_theme_color(self) -> Optional[Dict[str, str]]:
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=('配色文件 (*.color)',),
            )
            if not result:
                return None
            file_path = result if isinstance(result, str) else result[0]
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not all(k in data for k in ('bg', 'fg', 'accent')):
                return None
            if not all(_COLOR_RE.match(str(data.get(k, ''))) for k in ('bg', 'fg', 'accent')):
                return None
            theme_name = self._theme_manager.current_theme
            self._theme_manager.update_theme_colors(
                theme_name, data.get('bg', '#f5eed8'), data.get('fg', '#4a4030'),
                data.get('accent', '#b09050'), data.get('tip'), data.get('font_color')
            )
            self._theme_manager.save_current_theme()
            # 自定义主题（ct_前缀）：同步更新 _settings['custom_themes'] 列表对应条目，
            # 否则重启后从列表加载旧颜色覆盖内存新颜色
            if theme_name.startswith('ct_'):
                self._sync_custom_theme_colors(theme_name, data)
            self._save_immediate()
            self._invalidate_themes_cache()
            return data
        except Exception as e:
            logger.error(f"导入配色失败: {e}")
            return None

    def _sync_custom_theme_colors(self, uid: str, colors: Dict[str, str]) -> None:
        """同步更新 _settings['custom_themes'] 列表中指定自定义主题的颜色。

        用于 import_theme_color / update_settings 修改已有自定义主题颜色后，
        确保持久化层与内存 _core_themes 一致，避免重启后颜色回退。
        """
        custom = self._get_custom_themes_list()
        for c in custom:
            if c.get('uid') == uid:
                c['bg'] = colors.get('bg', c.get('bg', '#f5eed8'))
                c['fg'] = colors.get('fg', c.get('fg', '#4a4030'))
                c['accent'] = colors.get('accent', c.get('accent', '#b09050'))
                if 'tip' in colors:
                    c['tip'] = colors['tip']
                if 'font_color' in colors:
                    c['font_color'] = colors['font_color']
                break
        self._data_store.set_setting('custom_themes', custom)

    # ── 自定义配色 ──

    @staticmethod
    def _gen_uid() -> str:
        return 'ct_' + uuid.uuid4().hex[:12]

    def _get_custom_themes_list(self) -> List[Dict[str, str]]:
        val = self._data_store.get_setting('custom_themes', [])
        return val if isinstance(val, list) else []

    def _find_custom_by_uid(self, uid: str) -> tuple:
        custom = self._get_custom_themes_list()
        for i, c in enumerate(custom):
            if c.get('uid') == uid:
                return i, c
        return -1, None

    def _ensure_custom_theme_in_core(self, uid: str) -> bool:
        if self._theme_manager.has_core_theme(uid):
            return True
        _, theme = self._find_custom_by_uid(uid)
        if theme:
            self._theme_manager.set_core_theme(uid, theme)
            return True
        return False

    def save_custom_theme(self, colors: Dict[str, str], name: str = '') -> Dict[str, Any]:
        try:
            bg = colors.get('bg', '')
            fg = colors.get('fg', '')
            accent = colors.get('accent', '')
            if not (_COLOR_RE.match(bg) and _COLOR_RE.match(fg) and _COLOR_RE.match(accent)):
                return {'success': False, 'error': '无效的颜色格式'}
            tip = colors.get('tip') or '#888070'
            font_color = colors.get('font_color') or fg
            uid = self._gen_uid()
            theme = {'uid': uid, 'name': name.strip()[:20], 'bg': bg, 'fg': fg, 'accent': accent, 'tip': tip, 'font_color': font_color}
            custom = self._get_custom_themes_list()
            custom.append(theme)
            self._data_store.set_setting('custom_themes', custom)
            self._save_immediate()
            self._invalidate_themes_cache()
            return {'success': True, 'uid': uid, 'count': len(custom)}
        except Exception as e:
            logger.error(f"保存自定义配色失败: {e}")
            return {'success': False, 'error': str(e)}

    def get_custom_themes(self) -> List[Dict[str, Any]]:
        custom = self._get_custom_themes_list()
        result = []
        for idx, c in enumerate(custom):
            fg = c.get('fg', '#4a4030')
            uid = c.get('uid', '')
            display_name = c.get('name', '').strip() or ('自定义' + str(idx + 1))
            result.append({
                'name': uid, 'display_name': display_name,
                'bg': c.get('bg', '#f5eed8'), 'fg': fg,
                'accent': c.get('accent', '#b09050'), 'tip': c.get('tip', '#888070'),
                'font_color': c.get('font_color', fg), 'custom': True,
            })
        return result

    def delete_custom_theme(self, uid: str) -> Dict[str, Any]:
        try:
            custom = self._get_custom_themes_list()
            idx = next((i for i, c in enumerate(custom) if c.get('uid') == uid), -1)
            if idx < 0:
                return {'success': False, 'error': '未找到该配色'}
            del custom[idx]
            self._data_store.set_setting('custom_themes', custom)
            self._theme_manager.remove_core_theme(uid)
            if self._data_store.get_setting('current_theme') == uid:
                self._theme_manager.current_theme = '深渊'
                self._data_store.set_setting('current_theme', '深渊')
            self._save_immediate()
            self._invalidate_themes_cache()
            return {'success': True, 'count': len(custom)}
        except Exception as e:
            logger.error(f"删除自定义配色失败: {e}")
            return {'success': False, 'error': str(e)}

    def export_all_themes(self) -> Optional[str]:
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename='my_themes.themes.json',
                file_types=('主题文件 (*.themes.json)',),
            )
            if not result:
                return None
            save_path = result if isinstance(result, str) else result[0]
            if not save_path.endswith('.themes.json'):
                save_path += '.themes.json'
            custom = self._get_custom_themes_list()
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(custom, f, ensure_ascii=False, indent=2)
            return save_path
        except Exception as e:
            logger.error(f"导出主题失败: {e}")
            return None

    def reset_theme_colors(self, theme_name: str) -> Dict[str, Any]:
        try:
            from src.themes.theme_styles import CORE_THEMES
            if theme_name not in CORE_THEMES:
                return {'success': False, 'error': '只能重置内置主题'}
            original = CORE_THEMES[theme_name]
            self._theme_manager.set_core_theme(theme_name, original)
            theme_file = self._theme_manager.theme_dir / f"{theme_name}.json"
            if theme_file.exists():
                theme_file.unlink()
            self._save_immediate()
            self._invalidate_themes_cache()
            return {'success': True}
        except Exception as e:
            logger.error(f"重置主题失败: {e}")
            return {'success': False, 'error': str(e)}

    def import_all_themes(self) -> Dict[str, Any]:
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=('主题文件 (*.themes.json;*.color)', '所有文件 (*.*)'),
            )
            if not result:
                return {'success': False, 'error': '已取消'}
            file_path = result if isinstance(result, str) else result[0]
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            themes_to_add = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and all(k in item for k in ('bg', 'fg', 'accent')):
                        if _COLOR_RE.match(item['bg']) and _COLOR_RE.match(item['fg']) and _COLOR_RE.match(item['accent']):
                            themes_to_add.append({
                                'name': item.get('name', ''), 'bg': item['bg'], 'fg': item['fg'], 'accent': item['accent'],
                                'tip': item.get('tip', '#888070'), 'font_color': item.get('font_color', item['fg']),
                            })
            elif isinstance(data, dict) and all(k in data for k in ('bg', 'fg', 'accent')):
                if _COLOR_RE.match(data['bg']) and _COLOR_RE.match(data['fg']) and _COLOR_RE.match(data['accent']):
                    themes_to_add.append({
                        'name': data.get('name', ''), 'bg': data['bg'], 'fg': data['fg'], 'accent': data['accent'],
                        'tip': data.get('tip', '#888070'), 'font_color': data.get('font_color', data['fg']),
                    })
            if not themes_to_add:
                return {'success': False, 'error': '文件中没有有效配色'}
            custom = self._get_custom_themes_list()
            existing_keys = {(c.get('bg', ''), c.get('fg', ''), c.get('accent', '')) for c in custom}
            added = skipped = 0
            for t in themes_to_add:
                key = (t['bg'], t['fg'], t['accent'])
                if key in existing_keys:
                    skipped += 1
                    continue
                existing_keys.add(key)
                t['uid'] = self._gen_uid()
                custom.append(t)
                added += 1
            self._data_store.set_setting('custom_themes', custom)
            self._save_immediate()
            self._invalidate_themes_cache()
            msg = '已导入 ' + str(added) + ' 个配色'
            if skipped > 0:
                msg += '（跳过 ' + str(skipped) + ' 个重复）'
            return {'success': True, 'imported': added, 'skipped': skipped, 'total': len(custom), 'message': msg}
        except Exception as e:
            logger.error(f"导入主题失败: {e}")
            return {'success': False, 'error': str(e)}

    # ── 布局 ──

    def get_home_layout(self) -> str:
        layout = self._data_store.get_setting('home_layout', 'nautical')
        if layout not in AVAILABLE_LAYOUTS:
            layout = 'nautical'
            self._data_store.set_setting('home_layout', layout)
        return layout

    def set_home_layout(self, layout: str) -> Dict[str, Any]:
        if layout not in AVAILABLE_LAYOUTS:
            return {'success': False, 'error': f'无效布局: {layout}'}
        self._data_store.set_setting('home_layout', layout)
        self._save_immediate()
        try:
            from src.utils.file_utils import get_bundle_base_path
            base = get_bundle_base_path(__file__)
            html_path = os.path.join(base, 'static', f'{layout}.html')
            if not os.path.isfile(html_path):
                html_path = os.path.join(base, 'static', 'nautical.html')
            abs_path = os.path.abspath(html_path)
            url = 'file:///' + abs_path.replace('\\', '/')
            if self._window:
                def _do_load():
                    try:
                        import time
                        time.sleep(0.3)
                        self._window.load_url(url)
                    except Exception:
                        pass
                threading.Thread(target=_do_load, daemon=True).start()
        except Exception as e:
            logger.error(f"切换布局失败: {e}")
            return {'success': False, 'error': str(e)}
        return None

    def get_available_layouts(self) -> List[Dict[str, str]]:
        layouts = [dict(m) for m in LAYOUTS_META]
        current = self.get_home_layout()
        for l in layouts:
            l['current'] = l['id'] == current
        return layouts

    # ── 设置 ──

    def get_settings(self) -> Dict[str, Any]:
        return self._data_store.get_all_settings()

    def update_settings(self, settings: Dict[str, Any]) -> bool:
        try:
            font_size = settings.get('font_size')
            if font_size is not None:
                font_size = int(font_size)
                if not (10 <= font_size <= 40):
                    return False
                settings['font_size'] = font_size
            line_spacing = settings.get('line_spacing')
            if line_spacing is not None:
                line_spacing = float(line_spacing)
                if not (1.0 <= line_spacing <= 3.0):
                    return False
                settings['line_spacing'] = line_spacing
            for color_key in ('font_color', 'bg', 'fg', 'accent', 'tip'):
                val = settings.get(color_key)
                if val is not None and not _COLOR_RE.match(str(val)):
                    return False
            theme_name = settings.get('current_theme')
            theme_colors = settings.get('theme_colors')
            if theme_name:
                is_custom = theme_name.startswith('ct_')
                if is_custom and theme_colors:
                    self._theme_manager.set_core_theme(theme_name, theme_colors)
                    self._theme_manager.current_theme = theme_name
                    self._data_store.set_setting('current_theme', theme_name)
                    # 同步更新 _settings['custom_themes'] 列表，避免重启后颜色回退
                    self._sync_custom_theme_colors(theme_name, theme_colors)
                elif is_custom:
                    self._ensure_custom_theme_in_core(theme_name)
                    if self._theme_manager.has_core_theme(theme_name):
                        self._theme_manager.current_theme = theme_name
                        self._data_store.set_setting('current_theme', theme_name)
                else:
                    self._theme_manager.set_theme(theme_name)
                    self._data_store.set_setting('current_theme', theme_name)
                    if theme_colors:
                        self._theme_manager.update_theme_colors(
                            theme_name, theme_colors.get('bg', '#f5eed8'), theme_colors.get('fg', '#4a4030'),
                            theme_colors.get('accent', '#b09050'), theme_colors.get('tip'), theme_colors.get('font_color')
                        )
                        self._theme_manager.save_current_theme()
            clean = {k: v for k, v in settings.items() if k not in ('current_theme', 'theme_colors')}
            self._data_store.update_settings(clean)
            self._save_deferred()
            if theme_name or theme_colors:
                self._invalidate_themes_cache()
            return True
        except Exception as e:
            logger.error(f"更新设置失败: {e}")
            return False

    # ── 快捷键 ──

    def get_shortcut_settings(self) -> Dict[str, Any]:
        return self._data_store.get_shortcut_settings()

    def update_shortcuts(self, shortcuts: Dict[str, Any]) -> bool:
        try:
            self._data_store.set_shortcut_settings(shortcuts)
            self._save_immediate()
            return True
        except Exception as e:
            logger.error(f"更新快捷键失败: {e}")
            return False

    # ── 自定义字体 ──

    _FONT_EXTS = {'.ttf', '.otf', '.woff', '.woff2', '.ttc'}

    def get_custom_fonts(self) -> List[Dict[str, str]]:
        fonts_dir = self._dirs.get('fonts', '')
        if not fonts_dir or not os.path.isdir(fonts_dir):
            return []
        result = []
        for f in sorted(os.listdir(fonts_dir)):
            ext = Path(f).suffix.lower()
            if ext in self._FONT_EXTS:
                name = Path(f).stem
                full_path = os.path.join(fonts_dir, f)
                result.append({'name': name, 'file': f, 'path': full_path})
        return result

    def import_font(self) -> Optional[Dict[str, str]]:
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=(
                    '字体文件 (*.ttf;*.otf;*.woff;*.woff2;*.ttc)',
                    '所有文件 (*.*)',
                ),
            )
            if not result:
                return None
            paths = list(result) if isinstance(result, (list, tuple)) else [result]
            fonts_dir = self._dirs.get('fonts', '')
            os.makedirs(fonts_dir, exist_ok=True)
            imported = []
            for p in paths:
                if not os.path.isfile(p):
                    continue
                ext = Path(p).suffix.lower()
                if ext not in self._FONT_EXTS:
                    continue
                dest = os.path.join(fonts_dir, Path(p).name)
                if os.path.exists(dest):
                    continue
                shutil.copy2(p, dest)
                imported.append(Path(p).stem)
            if not imported:
                return None
            logger.info(f"导入字体: {imported}")
            return {'count': len(imported), 'names': imported}
        except Exception as e:
            logger.error(f"导入字体失败: {e}")
            return None

    def remove_custom_font(self, font_name: str) -> bool:
        try:
            fonts_dir = self._dirs.get('fonts', '')
            if not fonts_dir or not os.path.isdir(fonts_dir):
                return False
            for f in os.listdir(fonts_dir):
                if Path(f).stem == font_name:
                    ext = Path(f).suffix.lower()
                    if ext in self._FONT_EXTS:
                        os.remove(os.path.join(fonts_dir, f))
                        logger.info(f"删除字体: {font_name}")
                        return True
            return False
        except Exception as e:
            logger.error(f"删除字体失败: {e}")
            return False

    def open_fonts_folder(self) -> bool:
        try:
            fonts_dir = self._dirs.get('fonts', '')
            os.makedirs(fonts_dir, exist_ok=True)
            if not os.path.isdir(fonts_dir):
                return False
            import sys
            if sys.platform == 'win32':
                os.startfile(fonts_dir)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.run(['open', fonts_dir])
            else:
                import subprocess
                subprocess.run(['xdg-open', fonts_dir])
            return True
        except Exception as e:
            logger.error(f"打开字体文件夹失败: {e}")
            return False
