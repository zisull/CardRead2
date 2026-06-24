var _viewMode = localStorage.getItem('elegant_view') || 'list';
var _virtualScroller = null;
const VIRTUAL_SCROLL_THRESHOLD = 20;

function toggleView() { setView(_viewMode === 'grid' ? 'list' : 'grid'); }
function setView(mode) {
    _viewMode = mode;
    localStorage.setItem('elegant_view', mode);
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

    if (badge) badge.textContent = filtered.length + ' book' + (filtered.length !== 1 ? 's' : '') + ' · ' + books.reduce((s,b) => s + (b.chapters||0), 0) + ' chapters';

    if (books.length === 0) {
        _destroyVirtualScroller();
        el.className = _viewMode === 'grid' ? 's3-grid' : 's3-list';
        el.innerHTML = '<div class="empty-state"><div class="icon">📚</div><p>书架为空，请添加书籍</p></div>';
        return;
    }
    if (filtered.length === 0) {
        _destroyVirtualScroller();
        el.className = _viewMode === 'grid' ? 's3-grid' : 's3-list';
        el.innerHTML = '<div class="empty-state"><div class="icon">🔍</div><p>未找到匹配的书籍</p></div>';
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
    el.className = 's3-grid';
    el.innerHTML = filtered.map(function(b, i) {
        var pColor = 'hsl(' + (180 + (parseInt(b.progress)||0) * 1.5) + ',88%,55%)';
        var [c1, c2] = getBookColor(b.name);
        var ch = b.cover_char || '?';
        var pctNum = parseInt(b.progress) || 0;

        return '<div class="s3-card" data-book-name="' + escapeAttr(b.name) + '">' +
            '<div class="s3-card-num">' + String(i + 1).padStart(2, '0') + '</div>' +
            '<div class="s3-card-seal" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div>' +
            '<div class="s3-card-name">' + escapeHtml(b.display_name || b.name) + '</div>' +
            '<div class="s3-card-meta">' + escapeHtml(b.word_count_text) + ' · ' + escapeHtml(b.chapters) + '章</div>' +
            '<div class="s3-card-bar"><div class="s3-card-bar-fill" style="width:' + pctNum + '%;background:' + pColor + '"></div></div>' +
            '<div class="s3-card-pct" style="color:' + pColor + '">' + (b.progress || '—') + '</div></div>';
    }).join('');

    el.querySelectorAll('.s3-card').forEach(function(card) {
        var name = card.dataset.bookName;
        if (name === lastOpenedBook) card.classList.add('reading');
        card.addEventListener('dblclick', function() { openBook(name); });
        card.addEventListener('contextmenu', function(e) { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.s3-card');
}

function _renderListView(el, filtered) {
    el.className = 's3-list';
    el.innerHTML = filtered.map(function(b, i) {
        var pColor = 'hsl(' + (180 + (parseInt(b.progress)||0) * 1.5) + ',88%,55%)';
        var [c1, c2] = getBookColor(b.name);
        return '<div class="s3-item" data-book-name="' + escapeAttr(b.name) + '">' +
            '<div class="s3-item-num">' + String(i + 1).padStart(2, '0') + '</div>' +
            '<div class="s3-item-bar" style="background:linear-gradient(180deg,' + c1 + ',' + c2 + ')"></div>' +
            '<div class="s3-item-info"><div class="s3-item-name">' + escapeHtml(b.display_name || b.name) + '</div>' +
            '<div class="s3-item-meta">' + escapeHtml(b.word_count_text) + ' · ' + escapeHtml(b.chapters) + '章<span class="format-tag">' + escapeHtml(b.format || 'TXT') + '</span></div></div>' +
            '<div class="s3-item-pct" style="color:' + pColor + '">' + (b.progress || '—') + '</div></div>';
    }).join('');

    el.querySelectorAll('.s3-item').forEach(function(item) {
        var name = item.dataset.bookName;
        if (name === lastOpenedBook) item.classList.add('reading');
        item.addEventListener('dblclick', function() { openBook(name); });
        item.addEventListener('contextmenu', function(e) { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.s3-item');
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
    var itemHeight = isGrid ? 180 : 70;
    var itemsPerRow = isGrid ? Math.floor(el.clientWidth / 200) || 4 : 1;

    _virtualScroller = new VirtualScroller(el, {
        itemHeight: itemHeight,
        itemsPerRow: itemsPerRow,
        bufferSize: 5,
        renderItem: function(book) {
            return isGrid ? _createS3Card(book) : _createS3Item(book);
        },
        onItemClick: openBook,
        onItemContextMenu: showContextMenu,
    });
    _virtualScroller.setItems(filtered, isGrid);
}

function _createS3Card(book) {
    var pctNum = parseInt(book.progress) || 0;
    var colors = getBookColor(book.name);
    var c1 = colors[0], c2 = colors[1];
    var ch = book.cover_char || '?';
    var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
    var div = document.createElement('div');
    div.className = 's3-card' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML =
        '<div class="s3-card-num">00</div>' +
        '<div class="s3-card-seal" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + escapeHtml(ch) + '</div>' +
        '<div class="s3-card-name">' + escapeHtml(book.display_name || book.name) + '</div>' +
        '<div class="s3-card-meta">' + escapeHtml(book.word_count_text) + ' · ' + escapeHtml(book.chapters) + '章</div>' +
        '<div class="s3-card-bar"><div class="s3-card-bar-fill" style="width:' + pctNum + '%;background:' + pColor + '"></div></div>' +
        '<div class="s3-card-pct" style="color:' + pColor + '">' + escapeHtml(book.progress || '—') + '</div>';
    return div;
}

function _createS3Item(book) {
    var pctNum = parseInt(book.progress) || 0;
    var colors = getBookColor(book.name);
    var c1 = colors[0], c2 = colors[1];
    var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
    var div = document.createElement('div');
    div.className = 's3-item' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML =
        '<div class="s3-item-num">00</div>' +
        '<div class="s3-item-bar" style="background:linear-gradient(180deg,' + c1 + ',' + c2 + ')"></div>' +
        '<div class="s3-item-info"><div class="s3-item-name">' + escapeHtml(book.display_name || book.name) + '</div>' +
        '<div class="s3-item-meta">' + escapeHtml(book.word_count_text) + ' · ' + escapeHtml(book.chapters) + '章<span class="format-tag">' + escapeHtml(book.format || 'TXT') + '</span></div></div>' +
        '<div class="s3-item-pct" style="color:' + pColor + '">' + escapeHtml(book.progress || '—') + '</div>';
    return div;
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
