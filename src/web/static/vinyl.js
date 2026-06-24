var _viewMode = localStorage.getItem('vinyl_view') || 'list';
var _virtualScroller = null;
const VIRTUAL_SCROLL_THRESHOLD = 20;

function toggleView() { setView(_viewMode === 'grid' ? 'list' : 'grid'); }
function setView(mode) {
    _viewMode = mode;
    localStorage.setItem('vinyl_view', mode);
    var btn = document.getElementById('viewToggle');
    if (btn) btn.textContent = mode === 'grid' ? '▦' : '☰';
    renderBookList();
}

function renderBookList() {
    try {
    const el = document.getElementById('bookList');
    const badge = document.getElementById('bookCountBadge');
    if (!el) return;
    const filtered = getFilteredBooks();

    if (badge) badge.textContent = (filtered.length !== books.length ? filtered.length + '/' : '') + books.length + ' 张';

    if (books.length === 0) {
        _destroyVirtualScroller();
        el.innerHTML = '<div class="empty-state"><div class="icon">🎵</div><p>唱片架为空，请添加书籍</p></div>';
        return;
    }
    if (filtered.length === 0) {
        _destroyVirtualScroller();
        el.innerHTML = '<div class="empty-state"><div class="icon">🔍</div><p>未找到匹配的唱片</p></div>';
        return;
    }

    if (filtered.length > VIRTUAL_SCROLL_THRESHOLD) {
        _renderWithVirtualScroll(el, filtered);
    } else {
        _destroyVirtualScroller();
        if (_viewMode === 'grid') {
            _renderGridView(el, filtered);
        } else {
            _renderListView(el, filtered);
        }
    }
    } catch (e) { console.error('[renderBookList] 异常:', e); }
}

function _renderGridView(el, filtered) {
    el.className = 'vn-grid';
    el.innerHTML = filtered.map((b, i) => {
        const displayName = escapeHtml(b.display_name || b.name);
        const pctNum = parseInt(b.progress) || 0;
        const [c1, c2] = getBookColor(b.name);
        const ch = escapeHtml(b.cover_char || '?');
        const pctStr = escapeHtml(b.progress || '未读');
        const pctColor = getProgressColor(pctNum);
        const trackNum = String(i + 1).padStart(2, '0');
        const meta = escapeHtml(b.word_count_text) + '字 · ' + escapeHtml(b.chapters) + '章';
        return '<div class="vn-card" data-book-name="' + escapeAttr(b.name) + '">' +
            '<div class="vn-card-vinyl"><div class="vn-card-cover" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div></div>' +
            '<div class="vn-card-track">TRACK ' + trackNum + '</div>' +
            '<div class="vn-card-name">' + displayName + '</div>' +
            '<div class="vn-card-meta">' + meta + '</div>' +
            '<div class="vn-card-pct" style="color:' + pctColor + '">' + pctStr + '</div>' +
            '<div class="vn-card-bar"><div class="vn-card-bar-fill" style="width:' + pctNum + '%;background:' + pctColor + ';"></div></div>' +
            '</div>';
    }).join('');
    el.querySelectorAll('.vn-card').forEach(card => {
        const name = card.dataset.bookName;
        if (name === lastOpenedBook) card.classList.add('reading');
        card.addEventListener('dblclick', () => openBook(name));
        card.addEventListener('contextmenu', (e) => { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.vn-card');
}

function _renderListView(el, filtered) {
    el.className = 'book-list';
    el.innerHTML = filtered.map((b, i) => {
        const displayName = escapeHtml(b.display_name || b.name);
        const pctNum = parseInt(b.progress) || 0;
        const [c1, c2] = getBookColor(b.name);
        const ch = escapeHtml(b.cover_char || '?');
        const pctStr = escapeHtml(b.progress || '未读');
        const pctColor = getProgressColor(pctNum);
        const trackNum = String(i + 1).padStart(2, '0');
        return '<div class="book-row" data-book-name="' + escapeAttr(b.name) + '">' +
            '<div class="book-icon"><div class="vinyl-inner" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div></div>' +
            '<div class="book-info"><div class="book-name">' + displayName + '</div>' +
            '<div class="book-meta">TRACK ' + trackNum + ' · ' + escapeHtml(b.word_count_text) + '字 · ' + escapeHtml(b.chapters) + '章<span class="format-tag">' + escapeHtml(b.format || 'TXT') + '</span></div>' +
            '<div class="book-progress-bar"><div class="fill" style="width:' + pctNum + '%;background:' + pctColor + ';"></div></div></div>' +
            '<div class="book-pct">' + pctStr + '</div></div>';
    }).join('');
    el.querySelectorAll('.book-row').forEach(row => {
        const name = row.dataset.bookName;
        if (name === lastOpenedBook) row.classList.add('reading');
        row.addEventListener('dblclick', () => openBook(name));
        row.addEventListener('contextmenu', (e) => { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.book-row');
}

function _destroyVirtualScroller() {
    if (_virtualScroller) {
        _virtualScroller.destroy();
        _virtualScroller = null;
    }
}

function _renderWithVirtualScroll(el, filtered) {
    _destroyVirtualScroller();
    el.className = '';
    el.innerHTML = '';
    var isGrid = _viewMode === 'grid';
    var itemHeight = isGrid ? 220 : 70;
    var itemsPerRow = isGrid ? Math.floor(el.clientWidth / 200) || 4 : 1;

    _virtualScroller = new VirtualScroller(el, {
        itemHeight: itemHeight,
        itemsPerRow: itemsPerRow,
        bufferSize: 5,
        renderItem: function(book) {
            return isGrid ? _createVnCard(book) : _createVnRow(book);
        },
        onItemClick: openBook,
        onItemContextMenu: showContextMenu,
    });
    _virtualScroller.setItems(filtered, isGrid);
}

function _createVnCard(book) {
    var pctNum = parseInt(book.progress) || 0;
    var colors = getBookColor(book.name);
    var c1 = colors[0], c2 = colors[1];
    var ch = book.cover_char || '?';
    var pctStr = book.progress || '未读';
    var pctColor = getProgressColor(pctNum);
    var meta = escapeHtml(book.word_count_text) + '字 · ' + escapeHtml(book.chapters) + '章';
    var div = document.createElement('div');
    div.className = 'vn-card' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML =
        '<div class="vn-card-vinyl"><div class="vn-card-cover" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + escapeHtml(ch) + '</div></div>' +
        '<div class="vn-card-track">TRACK</div>' +
        '<div class="vn-card-name">' + escapeHtml(book.display_name || book.name) + '</div>' +
        '<div class="vn-card-meta">' + meta + '</div>' +
        '<div class="vn-card-pct" style="color:' + pctColor + '">' + escapeHtml(pctStr) + '</div>' +
        '<div class="vn-card-bar"><div class="vn-card-bar-fill" style="width:' + pctNum + '%;background:' + pctColor + ';"></div></div>';
    return div;
}

function _createVnRow(book) {
    var pctNum = parseInt(book.progress) || 0;
    var colors = getBookColor(book.name);
    var c1 = colors[0], c2 = colors[1];
    var ch = book.cover_char || '?';
    var pctStr = book.progress || '未读';
    var pctColor = getProgressColor(pctNum);
    var div = document.createElement('div');
    div.className = 'book-row' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML =
        '<div class="book-icon"><div class="vinyl-inner" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + escapeHtml(ch) + '</div></div>' +
        '<div class="book-info"><div class="book-name">' + escapeHtml(book.display_name || book.name) + '</div>' +
        '<div class="book-meta">' + escapeHtml(book.word_count_text) + '字 · ' + escapeHtml(book.chapters) + '章<span class="format-tag">' + escapeHtml(book.format || 'TXT') + '</span></div>' +
        '<div class="book-progress-bar"><div class="fill" style="width:' + pctNum + '%;background:' + pctColor + ';"></div></div></div>' +
        '<div class="book-pct">' + escapeHtml(pctStr) + '</div>';
    return div;
}

function updateHero(lastRead) {
    const empty = document.getElementById('heroEmpty');
    const content = document.getElementById('heroContent');

    if (lastRead) {
        const book = books.find(b => b.name === lastRead);
        if (book) {
            empty.style.display = 'none';
            content.style.display = 'flex';
            heroBookName = book.name;
            const displayName = book.display_name || book.name;
            const [c1, c2] = getBookColor(book.name);
            const label = document.querySelector('#heroCover .vinyl-label');
            if (label) {
                label.style.background = 'linear-gradient(135deg,' + c1 + ',' + c2 + ')';
                label.textContent = book.cover_char || '?';
            }
            document.getElementById('heroCover').classList.add('spinning');
            document.getElementById('heroTitle').textContent = displayName;
            document.getElementById('heroCh').textContent = 'TRACK 01 · ' + book.word_count_text + '字 · ' + book.chapters + '章 · ' + book.progress;
            document.getElementById('heroBtn').dataset.book = book.name;
            return;
        }
    }
    heroBookName = null;
    document.getElementById('heroCover').classList.remove('spinning');
    empty.style.display = '';
    content.style.display = 'none';
}

function heroClick() {
    if (heroBookName) {
        openBook(heroBookName);
    }
}

let searchTimer = null;
function filterBooks() {
    clearTimeout(searchTimer);
    const v = document.getElementById('searchInput').value;
    const c = document.getElementById('searchClear');
    if (c) c.style.display = v ? 'flex' : 'none';
    searchTimer = setTimeout(renderBookList, 150);
}

async function init() {
    await Promise.all([loadAppInfo(), loadSettings()]);
    await loadTheme();
    await loadDashboard();
    setupColorPaletteListeners();
    setupDragDrop();
}

window.removeEventListener('pywebviewready', init);
window.addEventListener('pywebviewready', init);
