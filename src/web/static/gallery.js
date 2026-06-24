var _viewMode = localStorage.getItem('sd_view') || 'grid';
var _virtualScroller = null;
const VIRTUAL_SCROLL_THRESHOLD = 20;

function toggleView() { setView(_viewMode === 'grid' ? 'list' : 'grid'); }
function setView(mode) {
    _viewMode = mode;
    localStorage.setItem('sd_view', mode);
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
        el.className = 'sd-grid';
        el.innerHTML = '<div class="sd-empty"><div class="sd-empty-icon">📡</div><div class="sd-empty-text">书架为空，请添加书籍</div></div>';
        return;
    }
    if (filtered.length === 0) {
        _destroyVirtualScroller();
        el.className = 'sd-grid';
        el.innerHTML = '<div class="sd-empty"><div class="sd-empty-icon">🔍</div><div class="sd-empty-text">未找到匹配的书籍</div></div>';
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
    el.className = 'sd-grid';
    el.innerHTML = filtered.map(function(b) {
        var pctNum = parseInt(b.progress) || 0;
        var [c1, c2] = getBookColor(b.name);
        var ch = b.cover_char || '?';
        var pctStr = b.progress || '未读';
        var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
        var meta = (b.word_count_text || '') + ' · ' + (b.chapters || 0) + '章';
        var status = pctNum >= 100 ? 'COMPLETE' : pctNum === 0 ? 'PENDING' : 'ACTIVE';
        var statusColor = pctNum >= 100 ? 'var(--success)' : pctNum === 0 ? 'var(--warning)' : 'var(--accent)';

        return '<div class="sd-card" data-book-name="' + escapeAttr(b.name) + '">' +
            '<div class="sd-card-top">' +
            '<div class="sd-card-hex" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div>' +
            '<div class="sd-card-name">' + escapeHtml(b.display_name || b.name) + '</div>' +
            '<div class="sd-card-pct" style="color:' + pColor + '">' + pctStr + '</div>' +
            '</div>' +
            '<div class="sd-card-meta">' + escapeHtml(meta) + '</div>' +
            '<div class="sd-card-bar"><div class="sd-card-bar-fill" style="width:' + pctNum + '%;background:linear-gradient(90deg,var(--accent),var(--accent2))"></div></div>' +
            '<div class="sd-card-data">' +
            '<div class="sd-card-datum">WORDS: <span>' + escapeHtml(b.word_count_text || '') + '</span></div>' +
            '<div class="sd-card-datum">CHAPTERS: <span>' + (b.chapters || 0) + '</span></div>' +
            '<div class="sd-card-datum">STATUS: <span style="color:' + statusColor + '">' + status + '</span></div>' +
            '</div></div>';
    }).join('');

    el.querySelectorAll('.sd-card').forEach(function(card) {
        var name = card.dataset.bookName;
        if (name === lastOpenedBook) card.classList.add('reading');
        card.addEventListener('dblclick', function() { openBook(name); });
        card.addEventListener('contextmenu', function(e) { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.sd-card');
}

function _renderListView(el, filtered) {
    el.className = 'sd-list';
    el.innerHTML = '<div class="sd-list-header">' +
        '<div class="sd-list-col sd-col-icon"></div>' +
        '<div class="sd-list-col sd-col-name">名称</div>' +
        '<div class="sd-list-col sd-col-progress">进度</div>' +
        '</div>' +
        filtered.map(function(b) {
            var pctNum = parseInt(b.progress) || 0;
            var [c1, c2] = getBookColor(b.name);
            var ch = b.cover_char || '?';
            var pctStr = b.progress || '未读';
            var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
            var status = pctNum >= 100 ? 'DONE' : pctNum === 0 ? 'NEW' : 'ING';
            var statusBg = pctNum >= 100 ? 'rgba(0,184,148,0.15)' : pctNum === 0 ? 'rgba(253,203,110,0.15)' : 'rgba(var(--accent-rgb,100,150,255),0.15)';
            var statusColor = pctNum >= 100 ? 'var(--success)' : pctNum === 0 ? 'var(--warning)' : 'var(--accent)';

            return '<div class="sd-row" data-book-name="' + escapeAttr(b.name) + '">' +
                '<div class="sd-row-hex" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div>' +
                '<div class="sd-row-info">' +
                    '<div class="sd-row-name">' + escapeHtml(b.display_name || b.name) + '</div>' +
                    '<div class="sd-row-meta">' + escapeHtml(b.word_count_text || '') + '字 · ' + (b.chapters || 0) + '章 · ' + escapeHtml(b.format || 'TXT') +
                    '<span class="sd-row-tag" style="background:' + statusBg + ';color:' + statusColor + '">' + status + '</span></div>' +
                '</div>' +
                '<div class="sd-row-progress">' +
                    '<div class="sd-row-bar"><div class="fill" style="width:' + pctNum + '%;background:' + pColor + '"></div></div>' +
                    '<span class="sd-row-pct" style="color:' + pColor + '">' + pctStr + '</span>' +
                '</div>' +
                '</div>';
        }).join('');

    el.querySelectorAll('.sd-row').forEach(function(row) {
        var name = row.dataset.bookName;
        if (name === lastOpenedBook) row.classList.add('reading');
        row.addEventListener('dblclick', function() { openBook(name); });
        row.addEventListener('contextmenu', function(e) { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.sd-row');
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
    var itemsPerRow = isGrid ? Math.floor(el.clientWidth / 200) || 4 : 1;

    _virtualScroller = new VirtualScroller(el, {
        itemHeight: itemHeight,
        itemsPerRow: itemsPerRow,
        bufferSize: 5,
        renderItem: function(book) {
            return isGrid ? _createSdCard(book) : _createSdRow(book);
        },
        onItemClick: openBook,
        onItemContextMenu: showContextMenu,
    });
    _virtualScroller.setItems(filtered, isGrid);
}

function _createSdCard(book) {
    var pctNum = parseInt(book.progress) || 0;
    var colors = getBookColor(book.name);
    var c1 = colors[0], c2 = colors[1];
    var ch = book.cover_char || '?';
    var pctStr = book.progress || '未读';
    var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
    var meta = (book.word_count_text || '') + ' · ' + (book.chapters || 0) + '章';
    var status = pctNum >= 100 ? 'COMPLETE' : pctNum === 0 ? 'PENDING' : 'ACTIVE';
    var statusColor = pctNum >= 100 ? 'var(--success)' : pctNum === 0 ? 'var(--warning)' : 'var(--accent)';
    var div = document.createElement('div');
    div.className = 'sd-card' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML =
        '<div class="sd-card-top">' +
        '<div class="sd-card-hex" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + escapeHtml(ch) + '</div>' +
        '<div class="sd-card-name">' + escapeHtml(book.display_name || book.name) + '</div>' +
        '<div class="sd-card-pct" style="color:' + pColor + '">' + escapeHtml(pctStr) + '</div>' +
        '</div>' +
        '<div class="sd-card-meta">' + escapeHtml(meta) + '</div>' +
        '<div class="sd-card-bar"><div class="sd-card-bar-fill" style="width:' + pctNum + '%;background:linear-gradient(90deg,var(--accent),var(--accent2))"></div></div>' +
        '<div class="sd-card-data">' +
        '<div class="sd-card-datum">WORDS: <span>' + escapeHtml(book.word_count_text || '') + '</span></div>' +
        '<div class="sd-card-datum">CHAPTERS: <span>' + (book.chapters || 0) + '</span></div>' +
        '<div class="sd-card-datum">STATUS: <span style="color:' + statusColor + '">' + status + '</span></div>' +
        '</div>';
    return div;
}

function _createSdRow(book) {
    var pctNum = parseInt(book.progress) || 0;
    var colors = getBookColor(book.name);
    var c1 = colors[0], c2 = colors[1];
    var ch = book.cover_char || '?';
    var pctStr = book.progress || '未读';
    var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
    var status = pctNum >= 100 ? 'DONE' : pctNum === 0 ? 'NEW' : 'ING';
    var statusBg = pctNum >= 100 ? 'rgba(0,184,148,0.15)' : pctNum === 0 ? 'rgba(253,203,110,0.15)' : 'rgba(var(--accent-rgb,100,150,255),0.15)';
    var statusColor = pctNum >= 100 ? 'var(--success)' : pctNum === 0 ? 'var(--warning)' : 'var(--accent)';
    var div = document.createElement('div');
    div.className = 'sd-row' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML =
        '<div class="sd-row-hex" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + escapeHtml(ch) + '</div>' +
        '<div class="sd-row-info">' +
            '<div class="sd-row-name">' + escapeHtml(book.display_name || book.name) + '</div>' +
            '<div class="sd-row-meta">' + escapeHtml(book.word_count_text || '') + '字 · ' + (book.chapters || 0) + '章 · ' + escapeHtml(book.format || 'TXT') +
            '<span class="sd-row-tag" style="background:' + statusBg + ';color:' + statusColor + '">' + status + '</span></div>' +
        '</div>' +
        '<div class="sd-row-progress">' +
            '<div class="sd-row-bar"><div class="fill" style="width:' + pctNum + '%;background:' + pColor + '"></div></div>' +
            '<span class="sd-row-pct" style="color:' + pColor + '">' + escapeHtml(pctStr) + '</span>' +
        '</div>';
    return div;
}

function _buildRing(pct, color, size) {
    var r = size / 2 - 3;
    var circ = 2 * Math.PI * r;
    var offset = circ * (1 - pct / 100);
    return '<svg width="' + size + '" height="' + size + '"><circle cx="' + size/2 + '" cy="' + size/2 + '" r="' + r + '" fill="none" stroke="var(--card-border)" stroke-width="3"/>' +
        '<circle cx="' + size/2 + '" cy="' + size/2 + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="3" stroke-dasharray="' + circ + '" stroke-dashoffset="' + offset + '" stroke-linecap="round"/></svg>';
}

function updateHero(lastRead) {
    var hero = document.getElementById('sdHero');
    if (!hero) return;
    if (lastRead) {
        var book = books.find(function(b) { return b.name === lastRead; });
        if (book) {
            var pctNum = parseInt(book.progress) || 0;
            var [c1, c2] = getBookColor(book.name);
            var pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
            hero.style.display = '';

            var ringEl = document.getElementById('sdHeroRing');
            if (ringEl) {
                ringEl.innerHTML = _buildRing(pctNum, pColor, 68) +
                    '<div class="sd-hero-ring-text"><div class="sd-hero-ring-pct" style="color:' + pColor + '">' + (pctNum || 0) + '%</div><div class="sd-hero-ring-label">PROGRESS</div></div>';
            }

            var titleEl = document.getElementById('sdHeroTitle');
            if (titleEl) titleEl.textContent = book.display_name || book.name;
            var metaEl = document.getElementById('sdHeroMeta');
            if (metaEl) metaEl.textContent = (book.word_count_text || '') + ' · ' + (book.chapters || 0) + '章';

            var totalWords = 0;
            books.forEach(function(b) { totalWords += parseInt(b.word_count) || 0; });
            var wordsStr = totalWords > 10000 ? (totalWords / 10000).toFixed(1) + '万' : totalWords;
            var svBooks = document.getElementById('sdStatBooks');
            if (svBooks) svBooks.textContent = _cachedStats ? _cachedStats.total_books : books.length;
            var svCh = document.getElementById('sdStatCh');
            if (svCh) svCh.textContent = _cachedStats ? _cachedStats.total_chapters : books.reduce(function(s, b) { return s + (parseInt(b.chapters) || 0); }, 0);
            var svWords = document.getElementById('sdStatWords');
            if (svWords) svWords.textContent = wordsStr;

            var btn = document.getElementById('sdHeroBtn');
            if (btn) btn.dataset.book = book.name;
            return;
        }
    }
    hero.style.display = 'none';
}

function heroClick() {
    var btn = document.getElementById('sdHeroBtn');
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
