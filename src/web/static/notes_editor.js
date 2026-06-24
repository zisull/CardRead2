

(function() {
    let noteId = null;
    let previewTimer = null;
    let saveTimer = null;
    let lastSavedContent = '';
    let _savedBgDataUrl = '';
    let _savedBgOpacity = 0.08;

    const editor = document.getElementById('editor');
    const preview = document.getElementById('preview');
    const charCount = document.getElementById('charCount');
    const saveTimeEl = document.getElementById('saveTime');
    const titleBar = document.getElementById('titleBar');
    const editorTitle = document.getElementById('editorTitle');
    const closeBtn = document.getElementById('closeBtn');
    const divider = document.getElementById('divider');
    const editorPane = document.getElementById('editorPane');
    const previewPane = document.getElementById('previewPane');
    const resizeHandle = document.getElementById('resizeHandle');
    const toolbar = document.getElementById('toolbar');

    function _applyThemeVars(theme) {
        const result = applyThemeVars(theme);
        document.documentElement.style.setProperty('--note-color', result.accent);
    }

    window.initNoteEditor = function(note, theme) {
        noteId = note.id;
        editor.value = note.content || '';
        editorTitle.textContent = note.title || '便签';
        lastSavedContent = editor.value;

        if (theme) {
            _savedBgDataUrl = theme.notes_bg_data_url || '';
            _savedBgOpacity = theme.notes_bg_opacity != null ? theme.notes_bg_opacity : 0.08;
            _applyThemeVars(theme);
            _applyNotesBg(theme);
        }

        updateCharCount();
        updatePreview();
    };

    function _applyNotesBg(theme) {
        var dataUrl = (theme && theme.notes_bg_data_url) || _savedBgDataUrl || '';
        if (dataUrl) {
            var cs = getComputedStyle(document.documentElement);
            var bgHex = cs.getPropertyValue('--bg').trim();
            document.body.style.background = bgHex + ' url(' + dataUrl + ') center/cover no-repeat fixed';
            var opacity = (theme && theme.notes_bg_opacity != null) ? theme.notes_bg_opacity : _savedBgOpacity;
            var card = document.querySelector('.editor-card');
            if (card) {
                var r = parseInt(bgHex.replace('#','').substring(0,2), 16) || 12;
                var g = parseInt(bgHex.replace('#','').substring(2,4), 16) || 12;
                var b = parseInt(bgHex.replace('#','').substring(4,6), 16) || 20;
                card.style.background = 'rgba(' + r + ',' + g + ',' + b + ',' + (1 - opacity) + ')';
            }
        }
    }

    window.applyNoteTheme = function(theme) {
        if (!theme) return;
        _applyThemeVars(theme);
        _applyNotesBg(theme);
    };

    function hexToRgba(hex, alpha) {
        var h = hex.replace('#', '');
        var r = parseInt(h.substring(0, 2), 16);
        var g = parseInt(h.substring(2, 4), 16);
        var b = parseInt(h.substring(4, 6), 16);
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

    function debounce(fn, delay) {
        var timer = null;
        return function() {
            clearTimeout(timer);
            var args = arguments;
            var self = this;
            timer = setTimeout(function() { fn.apply(self, args); }, delay);
        };
    }

    var _lastPreviewText = '';
    function updatePreview() {
        var text = editor.value;
        if (text === _lastPreviewText) return;
        _lastPreviewText = text;
        if (!text.trim()) {
            preview.innerHTML = '';
            return;
        }
        if (typeof api().render_markdown === 'function') {
            api().render_markdown(text).then(function(html) {
                preview.innerHTML = html || '';
            }).catch(function() {
                preview.innerHTML = '<p style="color:var(--tip);opacity:0.5;">预览加载失败</p>';
            });
        }
    }

    var debouncedPreview = debounce(updatePreview, 300);

    function updateCharCount() {
        var text = editor.value;
        var count = text.replace(/\s/g, '').length;
        charCount.textContent = count + ' 字';
    }

    function scheduleSave() {
        if (editor.value === lastSavedContent) return;
        saveTimeEl.textContent = '保存中...';
        saveTimeEl.classList.add('saving');
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function() {
            var content = editor.value;
            if (typeof api().save_note_from_editor === 'function') {
                api().save_note_from_editor(noteId, content).then(function() {
                    lastSavedContent = content;
                    var now = new Date();
                    var h = String(now.getHours()).padStart(2, '0');
                    var m = String(now.getMinutes()).padStart(2, '0');
                    var s = String(now.getSeconds()).padStart(2, '0');
                    saveTimeEl.textContent = '已保存 ' + h + ':' + m + ':' + s;
                    saveTimeEl.classList.remove('saving');
                }).catch(function() {
                    saveTimeEl.textContent = '保存失败';
                    saveTimeEl.classList.remove('saving');
                });
            }
        }, 1000);
    }

    editor.addEventListener('input', function() {
        updateCharCount();
        debouncedPreview();
        scheduleSave();
    });

    editor.addEventListener('keydown', function(e) {
        // Tab 缩进
        if (e.key === 'Tab' && !e.ctrlKey && !e.altKey) {
            e.preventDefault();
            var start = editor.selectionStart;
            var end = editor.selectionEnd;
            editor.value = editor.value.substring(0, start) + '    ' + editor.value.substring(end);
            editor.selectionStart = editor.selectionEnd = start + 4;
            editor.dispatchEvent(new Event('input'));
            return;
        }
        // Ctrl+S 立即保存
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            clearTimeout(saveTimer);
            var content = editor.value;
            if (typeof api().save_note_from_editor === 'function' && content !== lastSavedContent) {
                api().save_note_from_editor(noteId, content).then(function() {
                    lastSavedContent = content;
                    var now = new Date();
                    saveTimeEl.textContent = '已保存 ' + String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0') + ':' + String(now.getSeconds()).padStart(2,'0');
                }).catch(function() {});
            }
            return;
        }
        // Ctrl+B 加粗 / Ctrl+I 斜体
        if ((e.ctrlKey || e.metaKey) && (e.key === 'b' || e.key === 'B')) {
            e.preventDefault();
            var s = editor.selectionStart, en = editor.selectionEnd;
            var sel = editor.value.substring(s, en) || '粗体';
            editor.value = editor.value.substring(0, s) + '**' + sel + '**' + editor.value.substring(en);
            editor.selectionStart = s + 2;
            editor.selectionEnd = s + 2 + sel.length;
            editor.dispatchEvent(new Event('input'));
            return;
        }
        if ((e.ctrlKey || e.metaKey) && (e.key === 'i' || e.key === 'I')) {
            e.preventDefault();
            var s2 = editor.selectionStart, en2 = editor.selectionEnd;
            var sel2 = editor.value.substring(s2, en2) || '斜体';
            editor.value = editor.value.substring(0, s2) + '*' + sel2 + '*' + editor.value.substring(en2);
            editor.selectionStart = s2 + 1;
            editor.selectionEnd = s2 + 1 + sel2.length;
            editor.dispatchEvent(new Event('input'));
            return;
        }
    });

    // Esc 关闭编辑器（未保存内容会强制保存）
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && !e.ctrlKey && !e.altKey && !e.shiftKey) {
            if (document.activeElement === editor || document.activeElement === document.body) {
                e.preventDefault();
                closeBtn.click();
            }
        }
    });

    closeBtn.addEventListener('click', async function() {
        if (editor.value !== lastSavedContent) {
            clearTimeout(saveTimer);
            if (typeof api().save_note_from_editor === 'function') {
                await api().save_note_from_editor(noteId, editor.value).catch(function() {});
            }
        }
        if (typeof api().close_note_editor === 'function') {
            api().close_note_editor(noteId);
        }
    });

    function setupDrag() {
        var dragging = false, lastX = 0, lastY = 0;
        var _dragThrottle = null, dx = 0, dy = 0;
        titleBar.addEventListener('mousedown', function(e) {
            if (e.target.closest('.win-btn')) return;
            dragging = true;
            lastX = e.screenX;
            lastY = e.screenY;
            dx = 0;
            dy = 0;
            e.preventDefault();
        });
        document.addEventListener('mousemove', function(e) {
            if (!dragging) return;
            dx += e.screenX - lastX;
            dy += e.screenY - lastY;
            lastX = e.screenX;
            lastY = e.screenY;
            if (!_dragThrottle) {
                _dragThrottle = requestAnimationFrame(function() {
                    if (noteId && (dx || dy)) api().move_note_window(noteId, dx, dy);
                    dx = 0;
                    dy = 0;
                    _dragThrottle = null;
                });
            }
        });
        document.addEventListener('mouseup', function() {
            dragging = false;
        });
    }

    function setupResize() {
        var resizing = false, startX = 0, startY = 0, startW = 0, startH = 0;
        var _resizeThrottle = null;
        resizeHandle.addEventListener('mousedown', function(e) {
            e.preventDefault();
            e.stopPropagation();
            resizing = true;
            startX = e.screenX;
            startY = e.screenY;
            startW = window.innerWidth;
            startH = window.innerHeight;
        });
        document.addEventListener('mousemove', function(e) {
            if (!resizing) return;
            var w = Math.max(400, startW + (e.screenX - startX));
            var h = Math.max(300, startH + (e.screenY - startY));
            clearTimeout(_resizeThrottle);
            _resizeThrottle = setTimeout(function() {
                api().resize_note_window(noteId, w, h);
            }, 30);
        });
        document.addEventListener('mouseup', function() {
            resizing = false;
        });
    }

    function setupDivider() {
        var dragging = false, startX = 0;
        var editorBody = document.getElementById('editorBody');
        divider.addEventListener('mousedown', function(e) {
            e.preventDefault();
            dragging = true;
            startX = e.clientX;
            divider.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });
        document.addEventListener('mousemove', function(e) {
            if (!dragging) return;
            var bodyRect = editorBody.getBoundingClientRect();
            var x = e.clientX - bodyRect.left;
            var total = bodyRect.width;
            var ratio = Math.max(0.2, Math.min(0.8, x / total));
            editorPane.style.flex = ratio + ' ' + ratio + ' 0%';
            previewPane.style.flex = (1 - ratio) + ' ' + (1 - ratio) + ' 0%';
        });
        document.addEventListener('mouseup', function() {
            if (dragging) {
                dragging = false;
                divider.classList.remove('dragging');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    }

    toolbar.addEventListener('click', function(e) {
        var btn = e.target.closest('.tb-btn');
        if (!btn || !btn.dataset.action) return;
        var action = btn.dataset.action;
        var start = editor.selectionStart;
        var end = editor.selectionEnd;
        var selected = editor.value.substring(start, end);
        var before = editor.value.substring(0, start);
        var after = editor.value.substring(end);
        var insert = '';
        var cursorOffset = 0;

        switch (action) {
            case 'bold':
                insert = '**' + (selected || '粗体') + '**';
                cursorOffset = selected ? insert.length : 2;
                break;
            case 'italic':
                insert = '*' + (selected || '斜体') + '*';
                cursorOffset = selected ? insert.length : 1;
                break;
            case 'h1':
                insert = '# ' + (selected || '标题');
                cursorOffset = selected ? insert.length : 2;
                break;
            case 'h2':
                insert = '## ' + (selected || '标题');
                cursorOffset = selected ? insert.length : 3;
                break;
            case 'ul':
                insert = '- ' + (selected || '列表项');
                cursorOffset = selected ? insert.length : 2;
                break;
            case 'ol':
                insert = '1. ' + (selected || '列表项');
                cursorOffset = selected ? insert.length : 3;
                break;
            case 'task':
                insert = '- [ ] ' + (selected || '待办');
                cursorOffset = selected ? insert.length : 6;
                break;
            case 'code':
                if (selected.indexOf('\n') >= 0 || selected.length > 40) {
                    insert = '```\n' + selected + '\n```';
                    cursorOffset = 4;
                } else {
                    insert = '`' + (selected || '代码') + '`';
                    cursorOffset = selected ? insert.length : 1;
                }
                break;
            case 'link':
                insert = '[' + (selected || '文本') + '](URL)';
                cursorOffset = selected ? insert.length - 4 : 1;
                break;
        }

        editor.value = before + insert + after;
        var newPos = start + cursorOffset;
        editor.selectionStart = selected ? newPos : newPos;
        editor.selectionEnd = selected ? newPos : newPos + insert.length - cursorOffset;
        editor.focus();
        editor.dispatchEvent(new Event('input'));
    });

    setupDrag();
    setupResize();
    setupDivider();
})();
