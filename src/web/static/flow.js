var _viewMode = localStorage.getItem('flow_view') || 'list';
var _virtualScroller = null;
const VIRTUAL_SCROLL_THRESHOLD = 20;

function toggleView() { setView(_viewMode === 'grid' ? 'list' : 'grid'); }
function setView(mode) {
    _viewMode = mode;
    localStorage.setItem('flow_view', mode);
    var btn = document.getElementById('viewToggle');
    if (btn) btn.textContent = mode === 'grid' ? '▦' : '☰';
    renderBookList();
}

function renderBookList() {
    try {
    var el = document.getElementById('bookList');
    var badge = document.getElementById('bookCountBadge');
    if (!el) return;
    var filtered = getFilteredBooks();
    if (badge) badge.textContent = filtered.length;

    if (books.length === 0) {
        _destroyVirtualScroller();
        el.className = _viewMode === 'grid' ? 'oi-grid' : 'oi-list';
        el.innerHTML = '<div class="oi-empty"><div class="oi-empty-icon">📜</div><div class="oi-empty-text">书架为空，请添加书籍</div></div>';
        return;
    }
    if (filtered.length === 0) {
        _destroyVirtualScroller();
        el.className = _viewMode === 'grid' ? 'oi-grid' : 'oi-list';
        el.innerHTML = '<div class="oi-empty"><div class="oi-empty-icon">🔍</div><div class="oi-empty-text">未找到匹配的书籍</div></div>';
        return;
    }

    if (filtered.length > VIRTUAL_SCROLL_THRESHOLD) {
        _renderWithVirtualScroll(el, filtered);
    } else {
        _destroyVirtualScroller();
        if (_viewMode === 'list') {
            _renderListView(el, filtered);
        } else {
            _renderGridView(el, filtered);
        }
    }
    } catch (e) { console.error('[renderBookList] 异常:', e); }
}

function _renderGridView(el, filtered) {
    el.className = 'oi-grid';
    el.innerHTML = filtered.map(function(b, i) {
        var pctNum = parseInt(b.progress) || 0;
        var [c1, c2] = getBookColor(b.name);
        var ch = b.cover_char || '?';
        var pctStr = b.progress || '—';
        var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
        var meta = (b.word_count_text || '') + ' · ' + (b.chapters || 0) + '章';

        return '<div class="oi-card" data-book-name="' + escapeAttr(b.name) + '">' +
            '<div class="oi-card-seal" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div>' +
            '<div class="oi-card-name">' + escapeHtml(b.display_name || b.name) + '</div>' +
            '<div class="oi-card-meta">' + escapeHtml(meta) + '</div>' +
            '<div class="oi-card-bar"><div class="oi-card-bar-fill" style="width:' + pctNum + '%;background:' + pColor + '"></div></div>' +
            '<div class="oi-card-pct" style="color:' + pColor + '">' + pctStr + '</div>' +
            '</div>';
    }).join('');

    el.querySelectorAll('.oi-card').forEach(function(card) {
        var name = card.dataset.bookName;
        if (name === lastOpenedBook) card.classList.add('reading');
        card.addEventListener('dblclick', function() { openBook(name); });
        card.addEventListener('contextmenu', function(e) { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.oi-card');
}

function _renderListView(el, filtered) {
    el.className = 'oi-list';
    el.innerHTML = filtered.map(function(b, i) {
        var pctNum = parseInt(b.progress) || 0;
        var [c1, c2] = getBookColor(b.name);
        var ch = b.cover_char || '?';
        var pctStr = b.progress || '—';
        var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
        var meta = (b.word_count_text || '') + ' · ' + (b.chapters || 0) + '章';

        return '<li class="oi-item" data-book-name="' + escapeAttr(b.name) + '">' +
            '<div class="oi-item-num">' + String(i + 1).padStart(2, '0') + '</div>' +
            '<div class="oi-item-seal" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div>' +
            '<div class="oi-item-info"><div class="oi-item-name">' + escapeHtml(b.display_name || b.name) + '</div><div class="oi-item-meta">' + escapeHtml(meta) + '<span class="format-tag">' + escapeHtml(b.format || 'TXT') + '</span></div></div>' +
            '<div class="oi-item-pct" style="color:' + pColor + '">' + pctStr + '</div>' +
            '</li>';
    }).join('');

    el.querySelectorAll('.oi-item').forEach(function(item) {
        var name = item.dataset.bookName;
        if (name === lastOpenedBook) item.classList.add('reading');
        item.addEventListener('dblclick', function() { openBook(name); });
        item.addEventListener('contextmenu', function(e) { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.oi-item');
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
    var itemHeight = isGrid ? 200 : 70;
    var itemsPerRow = isGrid ? Math.floor(el.clientWidth / 180) || 4 : 1;

    _virtualScroller = new VirtualScroller(el, {
        itemHeight: itemHeight,
        itemsPerRow: itemsPerRow,
        bufferSize: 5,
        renderItem: function(book) {
            return isGrid ? _createOiCard(book) : _createOiItem(book);
        },
        onItemClick: openBook,
        onItemContextMenu: showContextMenu,
    });
    _virtualScroller.setItems(filtered, isGrid);
}

function _createOiCard(book) {
    var pctNum = parseInt(book.progress) || 0;
    var colors = getBookColor(book.name);
    var c1 = colors[0], c2 = colors[1];
    var ch = book.cover_char || '?';
    var pctStr = book.progress || '—';
    var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
    var meta = (book.word_count_text || '') + ' · ' + (book.chapters || 0) + '章';
    var div = document.createElement('div');
    div.className = 'oi-card' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML =
        '<div class="oi-card-seal" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + escapeHtml(ch) + '</div>' +
        '<div class="oi-card-name">' + escapeHtml(book.display_name || book.name) + '</div>' +
        '<div class="oi-card-meta">' + escapeHtml(meta) + '</div>' +
        '<div class="oi-card-bar"><div class="oi-card-bar-fill" style="width:' + pctNum + '%;background:' + pColor + '"></div></div>' +
        '<div class="oi-card-pct" style="color:' + pColor + '">' + escapeHtml(pctStr) + '</div>';
    return div;
}

function _createOiItem(book) {
    var pctNum = parseInt(book.progress) || 0;
    var colors = getBookColor(book.name);
    var c1 = colors[0], c2 = colors[1];
    var ch = book.cover_char || '?';
    var pctStr = book.progress || '—';
    var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
    var meta = (book.word_count_text || '') + ' · ' + (book.chapters || 0) + '章';
    var div = document.createElement('div');
    div.className = 'oi-item' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML =
        '<div class="oi-item-num">00</div>' +
        '<div class="oi-item-seal" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + escapeHtml(ch) + '</div>' +
        '<div class="oi-item-info"><div class="oi-item-name">' + escapeHtml(book.display_name || book.name) + '</div><div class="oi-item-meta">' + escapeHtml(meta) + '<span class="format-tag">' + escapeHtml(book.format || 'TXT') + '</span></div></div>' +
        '<div class="oi-item-pct" style="color:' + pColor + '">' + escapeHtml(pctStr) + '</div>';
    return div;
}

function updateHero(lastRead) {
    var hero = document.getElementById('oiHero');
    if (!hero) return;
    if (lastRead) {
        var book = books.find(function(b) { return b.name === lastRead; });
        if (book) {
            heroBookName = book.name;
            var [c1, c2] = getBookColor(book.name);
            hero.style.display = '';
            hero.setAttribute('data-glyph', book.cover_char || '?');

            var titleEl = document.getElementById('oiHeroTitle');
            if (titleEl) titleEl.textContent = book.display_name || book.name;
            var metaEl = document.getElementById('oiHeroMeta');
            if (metaEl) metaEl.textContent = (book.word_count_text || '') + ' · ' + (book.chapters || 0) + '章 · 已读 ' + (book.progress || '0%');

            var btn = document.getElementById('oiHeroBtn');
            if (btn) btn.dataset.book = book.name;
            return;
        }
    }
    hero.style.display = 'none';
}

function heroClick() {
    var btn = document.getElementById('oiHeroBtn');
    if (btn && btn.dataset.book) openBook(btn.dataset.book);
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
    setView(_viewMode);
    setupColorPaletteListeners();
    setupDragDrop();
}
window.removeEventListener('pywebviewready', init);
window.addEventListener('pywebviewready', init);
