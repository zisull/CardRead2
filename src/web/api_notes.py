"""便签 Mixin

提供便签的增删改查、编辑窗口和桌面展示窗口管理。
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime
from contextlib import suppress
from typing import Any, Dict, List, Optional

from loguru import logger

from src.utils.file_utils import get_bundle_base_path


def _safe_destroy(win):
    with suppress(Exception):
        win.destroy()


class NotesMixin:
    """便签操作"""

    def _init_notes(self):
        self._note_editor_windows: Dict[str, Any] = {}
        self._note_viewer_windows: Dict[str, Any] = {}
        self._notes_cache: Optional[List[Dict[str, Any]]] = None

    def _invalidate_notes_cache(self):
        self._notes_cache = None

    def get_notes(self) -> List[Dict[str, Any]]:
        if self._notes_cache is not None:
            return self._notes_cache
        notes = self._data_store.get_notes()
        if not notes:
            self._create_sample_note()
            notes = self._data_store.get_notes()
        self._notes_cache = notes
        return self._notes_cache

    def search_notes(self, query: str) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return self.get_notes()
        return self._data_store.search_notes(query.strip())

    def create_note(self, content: str = '', group: str = '') -> Dict[str, Any]:
        now = datetime.now().isoformat(timespec='seconds')
        note_id = uuid.uuid4().hex[:8]
        title = self._extract_title(content)
        note = {
            'id': note_id,
            'title': title,
            'content': content,
            'color': '',
            'group': group,
            'created_at': now,
            'updated_at': now,
        }
        self._data_store.add_note(note)
        self._invalidate_notes_cache()
        return note

    def update_note(self, note_id: str, content: str = None, color: str = None, title: str = None, group: str = None) -> Dict[str, Any]:
        updates = {}
        if content is not None:
            updates['content'] = content
            updates['title'] = self._extract_title(content)
        if title is not None:
            updates['title'] = title[:40] if title.strip() else '空白便签'
        if color is not None:
            updates['color'] = color
        if group is not None:
            updates['group'] = group
        
        if self._data_store.update_note(note_id, updates):
            self._invalidate_notes_cache()
            note = self._data_store.get_note(note_id)
            return {'success': True, 'note': note}
        return {'success': False, 'error': '便签不存在'}

    def delete_note(self, note_id: str) -> bool:
        if self._data_store.remove_note(note_id):
            self._invalidate_notes_cache()
            with suppress(Exception):
                self._close_note_editor(note_id)
            with suppress(Exception):
                self._close_note_viewer(note_id)
            return True
        return False

    def delete_notes(self, note_ids: List[str]) -> int:
        deleted_count = self._data_store.remove_notes(note_ids)
        if deleted_count > 0:
            self._invalidate_notes_cache()
            for nid in note_ids:
                with suppress(Exception):
                    self._close_note_editor(nid)
                with suppress(Exception):
                    self._close_note_viewer(nid)
        return deleted_count

    def delete_all_notes(self) -> int:
        notes = self._data_store.get_notes()
        count = len(notes)
        if count > 0:
            self._data_store.clear_notes()
            self._invalidate_notes_cache()
            self.close_all_note_windows()
        return count

    def create_sample_note(self) -> Dict[str, Any]:
        return self._create_sample_note()

    def duplicate_note(self, note_id: str) -> Dict[str, Any]:
        """复制便签（含内容和分组，标题加 (副本) 后缀）。"""
        src = self.get_note(note_id)
        if not src:
            return {'success': False, 'error': '便签不存在'}
        return self.create_note(content=src.get('content', ''), group=src.get('group', ''))

    def export_note_md(self, note_id: str) -> Dict[str, Any]:
        """导出单条便签为 Markdown 文件，返回保存路径。"""
        note = self.get_note(note_id)
        if not note:
            return {'success': False, 'error': '便签不存在'}
        try:
            import os
            from pathlib import Path
            safe_title = ''.join(c for c in (note.get('title') or '便签') if c not in r'\\/:*?"<>|')[:40] or '便签'
            default_name = safe_title + '.md'
            base_dir = Path(os.path.expanduser('~/Downloads'))
            if not base_dir.exists():
                base_dir = Path.home()
            file_path = base_dir / default_name
            if file_path.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                idx = 1
                while file_path.exists():
                    file_path = base_dir / f'{stem}_{idx}{suffix}'
                    idx += 1
            content = note.get('content', '')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {'success': True, 'path': str(file_path)}
        except Exception as e:
            logger.error(f"导出便签失败: {e}")
            return {'success': False, 'error': str(e)}

    def get_note_groups(self) -> List[str]:
        notes = self._data_store.get_notes()
        groups = set()
        for note in notes:
            g = note.get('group', '')
            if g:
                groups.add(g)
        return sorted(groups)

    def get_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        return self._data_store.get_note(note_id)

    def open_note_editor(self, note_id: str) -> bool:
        import webview

        with self._windows_lock:
            if note_id in self._note_editor_windows:
                with suppress(Exception):
                    self._note_editor_windows[note_id].evaluate_js('window.focus()')
                return True

        note = self.get_note(note_id)
        if not note:
            note = self.create_note()

        _base = get_bundle_base_path(__file__)
        html_path = os.path.join(_base, 'static', 'notes_editor.html')
        if not os.path.isfile(html_path):
            logger.error(f"便签编辑器 HTML 不存在: {html_path}")
            return False
        url = 'file:///' + os.path.abspath(html_path).replace('\\', '/')

        theme_vars = self._get_note_theme_raw()

        win_x, win_y = None, None
        if self._window:
            try:
                win_x = self._window.x + max(0, (self._window.width - 720) // 2)
                win_y = self._window.y + max(0, (self._window.height - 520) // 2)
            except Exception:
                pass

        win = webview.create_window(
            title='✏️ 便签',
            url=url,
            js_api=self,
            width=720, height=520,
            min_size=(400, 300),
            resizable=True,
            text_select=True,
            frameless=True,
            easy_drag=False,
            background_color=theme_vars.get('bg', '#0c0c14'),
            x=win_x, y=win_y,
        )
        win._note_id = note_id

        def on_loaded():
            with suppress(Exception):
                win.evaluate_js(
                    f'if(typeof initNoteEditor==="function")'
                    f'initNoteEditor({json.dumps(note)}, {json.dumps(theme_vars)});'
                )

        win.events.loaded += on_loaded

        with self._windows_lock:
            self._note_editor_windows[note_id] = win
        return True

    def open_note_viewer(self, note_id: str) -> bool:
        import webview

        with self._windows_lock:
            if note_id in self._note_viewer_windows:
                with suppress(Exception):
                    self._note_viewer_windows[note_id].evaluate_js('window.focus()')
                return True

        note = self.get_note(note_id)
        if not note:
            return False

        _base = get_bundle_base_path(__file__)
        html_path = os.path.join(_base, 'static', 'notes_viewer.html')
        if not os.path.isfile(html_path):
            logger.error(f"便签展示 HTML 不存在: {html_path}")
            return False
        url = 'file:///' + os.path.abspath(html_path).replace('\\', '/')

        theme = self._theme_manager.get_current_theme()
        theme_vars = self._get_note_theme_raw()

        all_on_top = self._data_store.get_setting('note_always_on_top', {})
        was_on_top = isinstance(all_on_top, dict) and all_on_top.get(note_id, False)

        win_x, win_y = None, None
        if self._window:
            try:
                win_x = self._window.x + max(0, (self._window.width - 320) // 2)
                win_y = self._window.y + max(0, (self._window.height - 420) // 2)
            except Exception:
                pass

        win = webview.create_window(
            title='📌 ' + (note.get('title', '便签')[:20]),
            url=url,
            js_api=self,
            width=320, height=420,
            min_size=(200, 200),
            resizable=True,
            text_select=True,
            frameless=True,
            easy_drag=False,
            background_color=theme_vars.get('bg', '#0c0c14'),
            on_top=was_on_top,
            x=win_x, y=win_y,
        )
        win._note_id = note_id

        def on_loaded():
            with suppress(Exception):
                win.evaluate_js(
                    f'if(typeof initNoteViewer==="function")'
                    f'initNoteViewer({json.dumps(note)}, {json.dumps(was_on_top)}, {json.dumps(theme_vars)});'
                )

        win.events.loaded += on_loaded

        with self._windows_lock:
            self._note_viewer_windows[note_id] = win
        return True

    def save_note_from_editor(self, note_id: str, content: str) -> Dict[str, Any]:
        result = self.update_note(note_id, content=content)
        if result.get('success'):
            self._sync_viewer_content(note_id)
        return result

    def close_note_editor(self, note_id: str) -> bool:
        return self._close_note_editor(note_id)

    def close_note_viewer(self, note_id: str) -> bool:
        return self._close_note_viewer(note_id)

    def close_all_note_windows(self):
        with self._windows_lock:
            wins = list(self._note_editor_windows.values())
            self._note_editor_windows.clear()
            wins += list(self._note_viewer_windows.values())
            self._note_viewer_windows.clear()
        for win in wins:
            win._programmatic_close = True
            threading.Timer(0.15, lambda w=win: _safe_destroy(w)).start()

    def move_note_window(self, note_id: str, dx: int, dy: int) -> bool:
        try:
            with self._windows_lock:
                win = self._note_editor_windows.get(note_id) or self._note_viewer_windows.get(note_id)
            if win:
                win.move(win.x + dx, win.y + dy)
            return True
        except Exception:
            return False

    def resize_note_window(self, note_id: str, width: int, height: int) -> bool:
        try:
            with self._windows_lock:
                win = self._note_editor_windows.get(note_id) or self._note_viewer_windows.get(note_id)
            if win:
                win.resize(width, height)
            return True
        except Exception:
            return False

    def get_note_window_size(self, note_id: str) -> Dict[str, int]:
        try:
            with self._windows_lock:
                win = self._note_editor_windows.get(note_id) or self._note_viewer_windows.get(note_id)
            if win:
                return {'width': win.width, 'height': win.height}
            return {'width': 400, 'height': 400}
        except Exception:
            return {'width': 400, 'height': 400}

    def toggle_note_always_on_top(self, note_id: str) -> bool:
        try:
            with self._windows_lock:
                win = self._note_editor_windows.get(note_id) or self._note_viewer_windows.get(note_id)
            if not win:
                return False
            current_state = self._data_store.get_setting('note_always_on_top', {})
            if not isinstance(current_state, dict):
                current_state = {}
            is_on_top = current_state.get(note_id, False)
            new_state = not is_on_top
            self._set_window_on_top(win, new_state)
            current_state[note_id] = new_state
            self._data_store.set_setting('note_always_on_top', current_state)
            self._save_deferred(delay=0.5)
            return new_state
        except Exception as e:
            logger.error(f"切换便签置顶失败: {e}")
            return False

    def render_markdown(self, md_text: str) -> str:
        try:
            import mistune
            return mistune.html(md_text or '')
        except Exception:
            from html import escape
            return f'<pre>{escape(md_text or "")}</pre>'

    def _get_note_theme_raw(self) -> Dict[str, str]:
        theme = self._theme_manager.get_current_theme()
        settings = self._data_store.get_all_settings()
        font_color = settings.get('font_color', theme.get('fg', '#e0d8f0'))
        notes_bg_image = settings.get('notes_bg_image', '')
        notes_bg_data_url = self.get_image_data_url(notes_bg_image) if notes_bg_image else ''
        return {
            'bg': theme.get('bg', '#0c0c14'),
            'fg': theme.get('fg', '#e0d8f0'),
            'accent': theme.get('accent', '#ff6ec7'),
            'accent2': theme.get('accent2', '#b98dff'),
            'tip': theme.get('tip', '#8880a0'),
            'secondary': theme.get('secondary', '#13131e'),
            'font_color': font_color,
            'notes_bg_image': notes_bg_image,
            'notes_bg_opacity': settings.get('notes_bg_opacity', 0.08),
            'notes_bg_data_url': notes_bg_data_url,
        }

    def _close_note_editor(self, note_id: str) -> bool:
        with self._windows_lock:
            if note_id in self._note_editor_windows:
                win = self._note_editor_windows.pop(note_id)
                win._programmatic_close = True
                threading.Timer(0.15, lambda: _safe_destroy(win)).start()
                return True
        return False

    def _close_note_viewer(self, note_id: str) -> bool:
        with self._windows_lock:
            if note_id in self._note_viewer_windows:
                win = self._note_viewer_windows.pop(note_id)
                win._programmatic_close = True
                threading.Timer(0.15, lambda: _safe_destroy(win)).start()
                return True
        return False

    def _sync_viewer_content(self, note_id: str):
        note = self.get_note(note_id)
        if not note:
            return
        with self._windows_lock:
            win = self._note_viewer_windows.get(note_id)
        if win:
            with suppress(Exception):
                win.evaluate_js(
                    f'if(typeof updateViewerContent==="function")'
                    f'updateViewerContent({json.dumps(note)});'
                )

    @staticmethod
    def _extract_title(content: str) -> str:
        if not content:
            return '空白便签'
        for line in content.split('\n'):
            line = line.strip()
            if line:
                clean = line.lstrip('#').strip()
                if clean:
                    return clean[:40]
        return '空白便签'

    def _create_sample_note(self) -> None:
        now = datetime.now().isoformat(timespec='seconds')
        content = """# 欢迎使用便签

这是一个示例便签，展示了支持的常见格式。

## 文字样式

这是 **粗体文字**，这是 *斜体文字**，这是 `行内代码`。

> 这是一段引用文字，适合用来记录灵感或摘录。

## 待办清单

- [x] 了解便签功能
- [ ] 创建第一个便签
- [ ] 尝试桌面展示

## 有序列表

1. 点击上方 **＋ 新建便签** 创建笔记
2. 使用 Markdown 语法编写内容
3. 点击 **📌 展示** 钉在桌面上

## 代码块

```
function hello() {
    console.log("Hello, Cardread!");
}
```

## 表格

| 功能 | 说明 |
|------|------|
| 编辑 | 左侧编辑，右侧预览 |
| 展示 | 悬浮桌面，随时查看 |
| 颜色 | 6 种颜色标签可选 |

---

💡 **提示**：双击标题可以重命名，关闭窗口会自动保存。"""
        note = {
            'id': uuid.uuid4().hex[:8],
            'title': '欢迎使用便签',
            'content': content,
            'color': '',
            'group': '示例',
            'created_at': now,
            'updated_at': now,
        }
        self._data_store.add_note(note)
        self._invalidate_notes_cache()
        return note
