var _viewMode = localStorage.getItem('nav_view') || 'list';
var _virtualScroller = null;

// 虚拟滚动阈值：当书籍数量超过此值时启用虚拟滚动优化
const VIRTUAL_SCROLL_THRESHOLD = 20;

function toggleView() { setView(_viewMode === 'grid' ? 'list' : 'grid'); }
function setView(mode) {
    _viewMode = mode;
    localStorage.setItem('nav_view', mode);
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

    if (badge) badge.textContent = (filtered.length !== books.length ? filtered.length + '/' : '') + books.length + ' 港';

    if (books.length === 0) {
        _destroyVirtualScroller();
        el.innerHTML = '<div class="empty-state"><div class="icon">⚓</div><p>航海日志为空，请添加书籍</p></div>';
        return;
    }
    if (filtered.length === 0) {
        _destroyVirtualScroller();
        el.innerHTML = '<div class="empty-state"><div class="icon">🔍</div><p>未找到匹配的港口</p></div>';
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

function _destroyVirtualScroller() {
    if (_virtualScroller) {
        _virtualScroller.destroy();
        _virtualScroller = null;
    }
}

function _renderWithVirtualScroll(el, filtered) {
    _destroyVirtualScroller();
    
    const isGrid = _viewMode === 'grid';
    const itemHeight = isGrid ? 180 : 70;
    const itemsPerRow = isGrid ? Math.floor(el.clientWidth / 200) || 4 : 1;
    
    _virtualScroller = new VirtualScroller(el, {
        itemHeight: itemHeight,
        itemsPerRow: itemsPerRow,
        bufferSize: 5,
        renderItem: (book, index) => {
            if (isGrid) {
                return _createBookCard(book);
            } else {
                return _createBookRow(book);
            }
        },
        onItemClick: openBook,
        onItemContextMenu: showContextMenu,
    });
    
    _virtualScroller.setItems(filtered, isGrid);
}

function _createBookCard(book) {
    const displayName = escapeHtml(book.display_name || book.name);
    const pctNum = parseInt(book.progress) || 0;
    const [c1, c2] = getBookColor(book.name);
    const ch = escapeHtml(book.cover_char || '?');
    const pctStr = escapeHtml(book.progress || '未读');
    const pctTxt = getProgressTextColor(pctNum);
    const meta = escapeHtml(book.word_count_text) + '字 · ' + escapeHtml(book.chapters) + '章';
    
    const div = document.createElement('div');
    div.className = 'nv-card' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML = `
        <div class="nv-card-icon" style="background:linear-gradient(135deg,${c1},${c2})">${ch}</div>
        <div class="nv-card-name">${displayName}</div>
        <div class="nv-card-meta">${meta}</div>
        <div class="nv-card-pct" style="color:${pctTxt}">${pctStr}</div>
        <div class="nv-card-bar"><div class="nv-card-bar-fill" style="width:${pctNum}%;"></div></div>
    `;
    return div;
}

function _createBookRow(book) {
    const displayName = escapeHtml(book.display_name || book.name);
    const pctNum = parseInt(book.progress) || 0;
    const [c1, c2] = getBookColor(book.name);
    const ch = escapeHtml(book.cover_char || '?');
    const pctStr = escapeHtml(book.progress || '未读');
    const pctTxt = getProgressTextColor(pctNum);
    
    const div = document.createElement('div');
    div.className = 'book-row' + (book.name === lastOpenedBook ? ' reading' : '');
    div.dataset.bookName = book.name;
    div.innerHTML = `
        <div class="book-icon" style="background:linear-gradient(135deg,${c1},${c2})">${ch}</div>
        <div class="book-info">
            <div class="book-name">${displayName}</div>
            <div class="book-meta">${escapeHtml(book.word_count_text)}字 · ${escapeHtml(book.chapters)}章 · ${escapeHtml(book.size || '')}<span class="format-tag">${escapeHtml(book.format || 'TXT')}</span></div>
            <div class="book-progress-bar"><div class="fill" style="width:${pctNum}%;"></div></div>
        </div>
        <div class="book-pct" style="color:${pctTxt}">${pctStr}</div>
    `;
    return div;
}

function _renderGridView(el, filtered) {
    el.className = 'nv-grid';
    el.innerHTML = filtered.map(b => {
        const displayName = escapeHtml(b.display_name || b.name);
        const pctNum = parseInt(b.progress) || 0;
        const [c1, c2] = getBookColor(b.name);
        const ch = escapeHtml(b.cover_char || '?');
        const pctStr = escapeHtml(b.progress || '未读');
        const pctTxt = getProgressTextColor(pctNum);
        const meta = escapeHtml(b.word_count_text) + '字 · ' + escapeHtml(b.chapters) + '章';
        return '<div class="nv-card" data-book-name="' + escapeAttr(b.name) + '">' +
            '<div class="nv-card-icon" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div>' +
            '<div class="nv-card-name">' + displayName + '</div>' +
            '<div class="nv-card-meta">' + meta + '</div>' +
            '<div class="nv-card-pct" style="color:' + pctTxt + '">' + pctStr + '</div>' +
            '<div class="nv-card-bar"><div class="nv-card-bar-fill" style="width:' + pctNum + '%;"></div></div>' +
            '</div>';
    }).join('');
    el.querySelectorAll('.nv-card').forEach(card => {
        const name = card.dataset.bookName;
        if (name === lastOpenedBook) card.classList.add('reading');
        card.addEventListener('dblclick', () => openBook(name));
        card.addEventListener('contextmenu', (e) => { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.nv-card');
}

function _renderListView(el, filtered) {
    el.className = 'book-list';
    el.innerHTML = filtered.map(b => {
        const displayName = escapeHtml(b.display_name || b.name);
        const pctNum = parseInt(b.progress) || 0;
        const [c1, c2] = getBookColor(b.name);
        const ch = escapeHtml(b.cover_char || '?');
        const pctStr = escapeHtml(b.progress || '未读');
        const pctTxt = getProgressTextColor(pctNum);
        return '<div class="book-row" data-book-name="' + escapeAttr(b.name) + '">' +
            '<div class="book-icon" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div>' +
            '<div class="book-info"><div class="book-name">' + displayName + '</div>' +
            '<div class="book-meta">' + escapeHtml(b.word_count_text) + '字 · ' + escapeHtml(b.chapters) + '章 · ' + escapeHtml(b.size || '') + '<span class="format-tag">' + escapeHtml(b.format || 'TXT') + '</span></div>' +
            '<div class="book-progress-bar"><div class="fill" style="width:' + pctNum + '%;"></div></div></div>' +
            '<div class="book-pct" style="color:' + pctTxt + '">' + pctStr + '</div></div>';
    }).join('');
    el.querySelectorAll('.book-row').forEach(row => {
        const name = row.dataset.bookName;
        if (name === lastOpenedBook) row.classList.add('reading');
        row.addEventListener('dblclick', () => openBook(name));
        row.addEventListener('contextmenu', (e) => { e.preventDefault(); showContextMenu(e, name); });
    });
    applyStaggerDelays('.book-row');
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
            document.getElementById('heroCover').style.background = 'linear-gradient(135deg,' + c1 + ',' + c2 + ')';
            document.getElementById('heroCover').textContent = book.cover_char || '?';
            document.getElementById('heroTitle').textContent = displayName;
            document.getElementById('heroCh').textContent = book.word_count_text + '字 · ' + book.chapters + '章 · ' + book.progress;
            document.getElementById('heroBtn').dataset.book = book.name;
            return;
        }
    }
    heroBookName = null;
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
