(function() {
    let noteId = '';
    let noteContent = '';
    let isEditing = false;
    let isOnTop = false;
    let _savedBgDataUrl = '';
    let _savedBgOpacity = 0.08;

    const contentAreaEl = document.getElementById('contentArea');
    const editAreaEl = document.getElementById('editArea');
    const titleBarEl = document.getElementById('titleBar');
    const noteTitleEl = document.getElementById('noteTitle');

    function _applyThemeVars(theme) {
        applyThemeVars(theme);
    }

    function _applyNotesBg(theme) {
        var dataUrl = (theme && theme.notes_bg_data_url) || _savedBgDataUrl || '';
        if (dataUrl) {
            var cs = getComputedStyle(document.documentElement);
            var bgHex = cs.getPropertyValue('--bg').trim();
            document.body.style.background = bgHex + ' url(' + dataUrl + ') center/cover no-repeat fixed';
            var opacity = (theme && theme.notes_bg_opacity != null) ? theme.notes_bg_opacity : _savedBgOpacity;
            var card = document.querySelector('.viewer-card');
            if (card) {
                var r = parseInt(bgHex.replace('#','').substring(0,2), 16) || 12;
                var g = parseInt(bgHex.replace('#','').substring(2,4), 16) || 12;
                var b = parseInt(bgHex.replace('#','').substring(4,6), 16) || 20;
                card.style.background = 'rgba(' + r + ',' + g + ',' + b + ',' + (1 - opacity) + ')';
            }
        }
    }

    async function renderContent(content) {
        let html = '';
        try {
            html = await api().render_markdown(content || '');
        } catch (e) {
            html = '<pre>' + escapeHtml(content || '') + '</pre>';
        }
        contentAreaEl.innerHTML = html;
        processCodeBlocks();
        processCheckboxes();
    }

    function processCodeBlocks() {
        const blocks = contentAreaEl.querySelectorAll('pre code');
        blocks.forEach(function(block) {
            if (typeof hljs !== 'undefined' && !block.classList.contains('hljs')) {
                try { hljs.highlightElement(block); } catch (e) {}
            }
        });
    }

    function processCheckboxes() {
        const cbs = contentAreaEl.querySelectorAll('input[type="checkbox"]');
        cbs.forEach(function(cb, idx) {
            cb.dataset.cbIndex = idx;
            cb.style.cursor = 'pointer';
            cb.onclick = handleCheckboxClick;
        });
    }

    function handleCheckboxClick(e) {
        const cb = e.target;
        const idx = parseInt(cb.dataset.cbIndex);
        if (isNaN(idx)) return;
        const lines = noteContent.split('\n');
        let count = 0;
        let found = false;
        for (let i = 0; i < lines.length; i++) {
            const match = lines[i].match(/^(\s*[-*+]\s+)\[([ xX])\](.*)/);
            if (match) {
                if (count === idx) {
                    const mark = cb.checked ? 'x' : ' ';
                    lines[i] = match[1] + '[' + mark + ']' + match[3];
                    found = true;
                    break;
                }
                count++;
            }
        }
        if (found) {
            noteContent = lines.join('\n');
            syncContentToBackend();
        }
    }

    let _syncTimer = null;
    let _pendingSavePromise = null;
    let _pendingSaveResolve = null;

    function syncContentToBackend() {
        clearTimeout(_syncTimer);
        if (!_pendingSavePromise) {
            _pendingSavePromise = new Promise(function(resolve) { _pendingSaveResolve = resolve; });
        }
        _syncTimer = setTimeout(function() {
            try {
                api().save_note_from_editor(noteId, noteContent).then(function() {
                    if (_pendingSaveResolve) { _pendingSaveResolve(); }
                    _pendingSavePromise = null;
                    _pendingSaveResolve = null;
                }).catch(function() {
                    if (_pendingSaveResolve) { _pendingSaveResolve(); }
                    _pendingSavePromise = null;
                    _pendingSaveResolve = null;
                });
            } catch (e) {
                if (_pendingSaveResolve) { _pendingSaveResolve(); }
                _pendingSavePromise = null;
                _pendingSaveResolve = null;
            }
        }, 300);
    }

    function toggleEditMode() {
        const editBtn = document.getElementById('editBtn');
        const saveBtn = document.getElementById('saveBtn');

        if (!isEditing) {
            isEditing = true;
            editAreaEl.value = noteContent;
            contentAreaEl.style.display = 'none';
            editAreaEl.style.display = 'block';
            editBtn.style.display = 'none';
            saveBtn.style.display = '';
            editAreaEl.focus();
        }
    }

    async function saveAndPreview() {
        const editBtn = document.getElementById('editBtn');
        const saveBtn = document.getElementById('saveBtn');

        noteContent = editAreaEl.value;
        isEditing = false;
        editAreaEl.style.display = 'none';
        contentAreaEl.style.display = '';
        editBtn.style.display = '';
        saveBtn.style.display = 'none';
        await renderContent(noteContent);
        const note = await api().save_note_from_editor(noteId, noteContent);
        if (note && note.note) {
            noteTitleEl.textContent = note.note.title || '便签';
        }
    }

    function setupDrag() {
        let dragging = false;
        let lastX = 0, lastY = 0, dx = 0, dy = 0;
        let _dragThrottle = null;

        titleBarEl.addEventListener('mousedown', function(e) {
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
        document.addEventListener('mouseup', function() { dragging = false; });
    }

    function setupResize() {
        const handle = document.getElementById('resizeHandle');
        let resizing = false, startX = 0, startY = 0, startW = 0, startH = 0;
        let _resizeThrottle = null;

        handle.addEventListener('mousedown', async function(e) {
            e.preventDefault();
            e.stopPropagation();
            resizing = true;
            startX = e.screenX;
            startY = e.screenY;
            try {
                const size = await api().get_note_window_size(noteId);
                startW = size.width;
                startH = size.height;
            } catch (ex) {
                startW = 320;
                startH = 420;
            }
        });
        document.addEventListener('mousemove', function(e) {
            if (!resizing) return;
            const w = Math.max(200, startW + (e.screenX - startX));
            const h = Math.max(200, startH + (e.screenY - startY));
            clearTimeout(_resizeThrottle);
            _resizeThrottle = setTimeout(function() { api().resize_note_window(noteId, w, h); }, 30);
        });
        document.addEventListener('mouseup', function() { resizing = false; });
    }

    function setupClose() {
        document.getElementById('closeBtn').addEventListener('click', async function() {
            if (isEditing) {
                noteContent = editAreaEl.value;
                await api().save_note_from_editor(noteId, noteContent).catch(function() {});
            } else if (_pendingSavePromise) {
                await _pendingSavePromise;
            }
            try { api().close_note_viewer(noteId); } catch (e) {}
        });
    }

    function setupEdit() {
        document.getElementById('editBtn').addEventListener('click', toggleEditMode);
        document.getElementById('saveBtn').addEventListener('click', saveAndPreview);
    }

    function setupPin() {
        const topBtn = document.getElementById('topBtn');
        topBtn.addEventListener('click', async function() {
            try {
                const newState = await api().toggle_note_always_on_top(noteId);
                isOnTop = newState;
                topBtn.classList.toggle('active', isOnTop);
                topBtn.title = isOnTop ? '取消置顶' : '置顶窗口';
            } catch (e) {}
        });
    }

    function setupLinks() {
        contentAreaEl.addEventListener('click', function(e) {
            const link = e.target.closest('a');
            if (link && link.href) {
                e.preventDefault();
                e.stopPropagation();
                try { api().open_url_in_browser(link.href); } catch (ex) {}
            }
        });
    }

    function setupTabKey() {
        editAreaEl.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = editAreaEl.selectionStart;
                const end = editAreaEl.selectionEnd;
                editAreaEl.value = editAreaEl.value.substring(0, start) + '    ' + editAreaEl.value.substring(end);
                editAreaEl.selectionStart = editAreaEl.selectionEnd = start + 4;
            }
        });
    }

    window.initNoteViewer = function(note, wasOnTop, theme) {
        noteId = note.id || '';
        noteContent = note.content || '';
        isOnTop = wasOnTop || false;

        if (theme) {
            _savedBgDataUrl = theme.notes_bg_data_url || '';
            _savedBgOpacity = theme.notes_bg_opacity != null ? theme.notes_bg_opacity : 0.08;
            _applyThemeVars(theme);
            _applyNotesBg(theme);
        }

        noteTitleEl.textContent = note.title || '便签';

        const topBtn = document.getElementById('topBtn');
        topBtn.classList.toggle('active', isOnTop);
        topBtn.title = isOnTop ? '取消置顶' : '置顶窗口';

        setupDrag();
        setupResize();
        setupClose();
        setupEdit();
        setupPin();
        setupLinks();
        setupTabKey();
        renderContent(noteContent);
    };

    window.applyNoteTheme = function(theme) {
        if (!theme) return;
        _applyThemeVars(theme);
        _applyNotesBg(theme);
        if (!isEditing) renderContent(noteContent);
    };

    window.updateViewerContent = function(note) {
        if (!note) return;
        if (isEditing) return;
        noteContent = note.content || '';
        noteTitleEl.textContent = note.title || '便签';
        renderContent(noteContent);
    };
})();
