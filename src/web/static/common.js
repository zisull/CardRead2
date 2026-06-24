let books = [];
let currentTheme = {};
let settings = {};
let contextMenuBook = null;
let lastOpenedBook = null;
let confirmCallback = null;
let allThemeData = [];
let customThemesList = [];
let customThemeColors = null;
let heroBookName = null;
let _cachedStats = null;
let _shelfDirty = true;
let _bookmarkDirty = true;
let _notesDirty = true;

// 搜索历史（最近 10 条）
let _searchHistory = [];
try { _searchHistory = JSON.parse(localStorage.getItem('cardread_search_history') || '[]'); } catch(e) { _searchHistory = []; }

document.addEventListener('DOMContentLoaded', function() {
    document.body.style.opacity = '0';
    document.body.style.transition = 'opacity 0.3s ease';
    requestAnimationFrame(function() {
        document.body.style.opacity = '1';
    });
    // 注入公共页面模板（设置页/日志页/说明页），消除 5 个 layout 的重复 HTML
    renderPartials();
});

// 书名哈希 → HSL 动态生成颜色，永不重复（取代 12 组硬编码 NEON_COLORS）
function getBookColor(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) | 0;
    h = Math.abs(h) % 360;
    const s1 = 55 + (h % 25);  // 55%-80% 饱和度
    const l1 = 55 + (h % 15);  // 55%-70% 亮度
    const h2 = (h + 30) % 360; // 第二色偏移 30 度
    const s2 = s1 + 5;
    const l2 = l1 + 8;
    function hslToHex(h, s, l) {
        s /= 100; l /= 100;
        const c = (1 - Math.abs(2 * l - 1)) * s;
        const x = c * (1 - Math.abs((h / 60) % 2 - 1));
        const m = l - c / 2;
        let r, g, b;
        if (h < 60) { r = c; g = x; b = 0; }
        else if (h < 120) { r = x; g = c; b = 0; }
        else if (h < 180) { r = 0; g = c; b = x; }
        else if (h < 240) { r = 0; g = x; b = c; }
        else if (h < 300) { r = x; g = 0; b = c; }
        else { r = c; g = 0; b = x; }
        const toHex = v => Math.round((v + m) * 255).toString(16).padStart(2, '0');
        return '#' + toHex(r) + toHex(g) + toHex(b);
    }
    return [hslToHex(h, s1, l1), hslToHex(h2, s2, l2)];
}
function getStatusColor(pctNum) {
    if (pctNum >= 100) return ['#00b894','#55efc4'];
    if (pctNum > 0) return ['#5b86e5','#36d1dc'];
    return ['#666','#888'];
}
function getBookChar(name) {
    if (!name) return '?';
    for (var i = 0; i < name.length; i++) {
        var ch = name.charAt(i);
        if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(ch)) return ch;
        if (/[a-zA-Z]/.test(ch)) return ch.toUpperCase();
        if (/[0-9]/.test(ch)) return ch;
    }
    return name.charAt(0) || '?';
}
function _fmtTimeDetail(iso) {
    if (!iso) return '';
    var s = String(iso).replace('T', ' ');
    var dot = s.indexOf('.');
    return dot > 0 ? s.substring(0, dot) : s;
}
function highlightMatch(text, query) {
    if (!query) return escapeHtml(text);
    var escaped = escapeHtml(text);
    var q = escapeHtml(query);
    var re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    return escaped.replace(re, '<mark class="search-hl">$1</mark>');
}
function getProgressColor(pct) {
    var p = Math.max(0, Math.min(100, pct));
    var hue = Math.round(180 + p * 1.5);
    return 'hsl(' + hue + ',60%,55%)';
}
function getProgressTextColor(pct) {
    var accent = (typeof currentTheme !== 'undefined' && currentTheme.accent) ? currentTheme.accent : '#2878b8';
    var hsl = hexToHsl(accent);
    var p = Math.max(0, Math.min(100, pct));
    var sat = Math.round(Math.min(hsl.s, 60));
    var lightness = 55 - p * 0.10;
    return 'hsl(' + Math.round(hsl.h) + ',' + sat + '%,' + lightness + '%)';
}

// 主题应用节流标记
let _themeApplyPending = false;
let _themeApplyArgs = null;

function _applyThemeVars(bg, fg, accent, tip, secondary) {
    // 使用 requestAnimationFrame 节流，避免频繁 DOM 操作
    _themeApplyArgs = { bg, fg, accent, tip, secondary };
    if (!_themeApplyPending) {
        _themeApplyPending = true;
        requestAnimationFrame(() => {
            _themeApplyPending = false;
            if (_themeApplyArgs) {
                _doApplyThemeVars(_themeApplyArgs.bg, _themeApplyArgs.fg, _themeApplyArgs.accent, _themeApplyArgs.tip, _themeApplyArgs.secondary);
                _themeApplyArgs = null;
            }
        });
    }
}

function _doApplyThemeVars(bg, fg, accent, tip, secondary) {
    const r = document.documentElement.style;
    const dark = isDarkColor(bg);
    const cardAlpha = dark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)';
    const cardBorderAlpha = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.08)';
    const cardHoverAlpha = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)';
    const fg3 = dark ? lightenColor(tip, 0.3) : darkenColor(tip, 0.2);
    const accent2 = dark ? lightenColor(accent, 0.3) : darkenColor(accent, 0.2);
    const cardBg = dark ? lightenColor(bg, 0.03) : darkenColor(bg, 0.02);
    const borderColor = dark ? lightenColor(bg, 0.08) : darkenColor(bg, 0.06);
    const shadowColor = dark ? 'rgba(0,0,0,0.4)' : 'rgba(0,0,0,0.08)';
    const inputBg = dark ? lightenColor(bg, 0.05) : darkenColor(bg, 0.02);

    r.setProperty('--bg', bg);
    r.setProperty('--bg2', secondary);
    r.setProperty('--fg', fg);
    r.setProperty('--fg2', tip);
    r.setProperty('--tip', tip);
    r.setProperty('--fg3', fg3);
    r.setProperty('--accent', accent);
    r.setProperty('--accent2', accent2);
    r.setProperty('--card', cardAlpha);
    r.setProperty('--card-border', cardBorderAlpha);
    r.setProperty('--card-hover', cardHoverAlpha);
    r.setProperty('--card-bg', cardBg);
    r.setProperty('--border', borderColor);
    r.setProperty('--shadow', shadowColor);
    r.setProperty('--input-bg', inputBg);
    r.setProperty('--secondary', secondary);
    r.setProperty('--font-color', fg);
    r.setProperty('--success', '#00b894');
    r.setProperty('--warning', '#fdcb6e');
    r.setProperty('--danger', '#e74c3c');
    r.setProperty('--danger-rgb', '231,76,60');
    r.setProperty('--warning-rgb', '243,156,18');

    const glowR = parseInt(accent.slice(1,3),16);
    const glowG = parseInt(accent.slice(3,5),16);
    const glowB = parseInt(accent.slice(5,7),16);
    r.setProperty('--accent-rgb', glowR+','+glowG+','+glowB);
    r.setProperty('--highlight', 'rgba('+glowR+','+glowG+','+glowB+',0.12)');
    r.setProperty('--code-bg', dark ? lightenColor(bg, 0.08) : darkenColor(bg, 0.04));
    r.setProperty('--code-color', dark ? lightenColor(fg, 0.1) : darkenColor(fg, 0.1));
    r.setProperty('--glow-color', 'rgba('+glowR+','+glowG+','+glowB+',0.3)');
    const appEl = document.querySelector('.app');
    if (appEl) {
        appEl.style.setProperty('--glow',
            'radial-gradient(circle, rgba('+glowR+','+glowG+','+glowB+',0.06), transparent 70%)');
    }

    const heroSection = document.querySelector('.hero-section');
    if (heroSection) {
        heroSection.style.background = dark
            ? 'linear-gradient(135deg, rgba('+glowR+','+glowG+','+glowB+',0.1), rgba('+glowR+','+glowG+','+glowB+',0.05))'
            : 'linear-gradient(135deg, rgba('+glowR+','+glowG+','+glowB+',0.06), rgba('+glowR+','+glowG+','+glowB+',0.03))';
        heroSection.style.borderColor = 'rgba('+glowR+','+glowG+','+glowB+',0.15)';
    }

    if (typeof homeBgPath !== 'undefined' && homeBgPath && homeBgDataUrl) {
        const opacityEl = document.getElementById('homeBgOpacity');
        const opacity = opacityEl ? parseInt(opacityEl.value) / 100 : 0.5;
        document.body.style.background = bg + ' url(' + homeBgDataUrl + ') center/cover no-repeat fixed';
        const app = document.getElementById('appRoot');
        if (app) {
            const r2 = parseInt(bg.slice(1,3),16) || 12;
            const g2 = parseInt(bg.slice(3,5),16) || 12;
            const b2 = parseInt(bg.slice(5,7),16) || 20;
            app.style.background = 'rgba(' + r2 + ',' + g2 + ',' + b2 + ',' + (1 - opacity) + ')';
        }
    } else {
        document.body.style.background = '';
        const app = document.getElementById('appRoot');
        if (app) app.style.background = '';
    }
}

async function loadTheme() {
    try {
        currentTheme = await api().get_current_theme();
        const bg = currentTheme.bg || '#0c0c14';
        const fg = currentTheme.fg || '#e0d8f0';
        const accent = currentTheme.accent || '#ff6ec7';
        const tip = currentTheme.tip || '#8880a0';
        const secondary = currentTheme.secondary || '#161620';
        _applyThemeVars(bg, fg, accent, tip, secondary);
    } catch (e) { showToast('加载主题失败'); }
}
function previewThemeColors(colors) {
    const bg = colors.bg;
    const fg = colors.fg;
    const accent = colors.accent;
    const tip = colors.tip || mixHex(fg, bg, 0.5);
    const dark = isDarkColor(bg);
    const secondary = dark ? lightenColor(bg, 0.06) : darkenColor(bg, 0.03);
    _applyThemeVars(bg, fg, accent, tip, secondary);
}

async function loadBooks() {
    try {
        books = await api().get_books();
        renderBookList();
    } catch (e) {
        showToast('加载书籍列表失败');
    }
}

async function loadDashboard() {
    try {
        const data = await api().get_dashboard_data();
        if (data && Array.isArray(data.books)) {
            books = data.books;
            renderBookList();
        } else {
            await loadBooks();
        }
        if (data && data.stats) {
            _cachedStats = data.stats;
            applyStats(data.stats);
        } else {
            await loadStats(true);
        }
    } catch (e) {
        try { await loadBooks(); } catch (e2) { showToast('加载书籍列表失败'); }
        try { await loadStats(true); } catch (e2) { /* ignore */ }
    }
}

function getFilteredBooks() {
    const searchEl = document.getElementById('searchInput');
    const formatEl = document.getElementById('filterFormat');
    const progressEl = document.getElementById('filterProgress');
    const sortEl = document.getElementById('sortBy');
    const query = (searchEl ? searchEl.value : '').toLowerCase();
    const formatFilter = (formatEl ? formatEl.value : '').toUpperCase();
    const progressFilter = progressEl ? progressEl.value : '';
    const sortBy = (sortEl ? sortEl.value : '') || 'recent';

    const filtered = books.filter(b => {
        if (query) {
            // 匹配 name/display_name（原逻辑，不分大小写）
            const nameMatch = b.name.toLowerCase().includes(query) || (b.display_name || '').toLowerCase().includes(query);
            // 匹配拼音首字母（如「射雕英雄传」→ SDYXZ，输入 sdyxz 可命中）
            const initials = (b.pinyin_initials || '').toLowerCase();
            const initialsMatch = initials && initials.includes(query);
            // 匹配全拼音（如「射雕英雄传」→ shediaoyingxiongzhuan，输入 shediao 可命中）
            const fullPinyin = (b.pinyin_full || '').toLowerCase();
            const fullPinyinMatch = fullPinyin && fullPinyin.includes(query);
            if (!nameMatch && !initialsMatch && !fullPinyinMatch) return false;
        }
        if (formatFilter && (b.format || 'TXT').toUpperCase() !== formatFilter) return false;
        if (progressFilter) {
            const pctStr = b.progress || '未读';
            const pctNum = parseInt(pctStr) || 0;
            if (progressFilter === 'unread' && pctNum > 0) return false;
            if (progressFilter === 'reading' && (pctNum <= 0 || pctNum >= 100)) return false;
            if (progressFilter === 'done' && pctNum < 100) return false;
        }
        return true;
    });

    filtered.sort((a, b) => {
        if (sortBy === 'name') {
            return (a.display_name || a.name).localeCompare(b.display_name || b.name, 'zh-CN');
        } else if (sortBy === 'progress') {
            return (parseInt(a.progress) || 0) - (parseInt(b.progress) || 0);
        } else if (sortBy === 'added') {
            return a.name.localeCompare(b.name, 'zh-CN');
        } else {
            const ta = a.last_read || '';
            const tb = b.last_read || '';
            if (ta && tb) return tb.localeCompare(ta);
            if (ta) return -1;
            if (tb) return 1;
            return (parseInt(b.progress) || 0) - (parseInt(a.progress) || 0);
        }
    });

    return filtered;
}

async function addBooks() {
    try {
        const paths = await api().open_file_dialog();
        if (paths && paths.length > 0) await importBooks(paths);
    } catch (e) { showToast('打开文件对话框失败'); }
}

async function importBooks(paths) {
    try {
        setStatus('正在导入 ' + paths.length + ' 本书籍...');
        var r = await api().import_books(paths);
        var added = (r && r.added) || 0;
        var errors = (r && r.errors) || [];
        var skipped = (r && r.skipped) || [];
        if (added > 0) {
            showToast('成功添加 ' + added + ' 本书籍' + (skipped.length > 0 ? '（跳过 ' + skipped.length + ' 本）' : ''));
            _cachedStats = null; _shelfDirty = true; _bookmarkDirty = true;
            await loadDashboard();
        } else if (errors.length > 0) {
            showToast('导入失败: ' + errors[0]);
        } else {
            showToast('未添加任何书籍');
        }
        setStatus('就绪');
    } catch (e) { showToast('导入异常'); setStatus('就绪'); }
}

async function openBook(name) {
    try {
        setStatus('正在打开书籍...');
        lastOpenedBook = name;
        const [, r] = await Promise.all([
            api().open_reader_window(name),
            api().open_book(name)
        ]);
        if (!r.success) showToast(r.error || '打开失败');
        else showToast('已打开：' + name);
        setStatus('就绪');
        renderBookList();
    } catch (e) { showToast('打开失败: ' + (e.message || e)); setStatus('就绪'); }
}

async function deleteBook(name) {
    showConfirm('确认删除', '确定要删除「' + name + '」吗？\n\n注意：此操作将删除书籍文件和相关数据。', async () => {
        try {
            const r = await api().delete_book(name);
            if (r) { showToast('已删除：' + name); _cachedStats = null; _shelfDirty = true; _bookmarkDirty = true; await loadDashboard(); }
            else showToast('删除失败（可能正在阅读中）');
        } catch (e) { showToast('删除失败'); }
    });
}

async function resetApp() {
    showConfirm('确认重置', '确定要重置应用吗？\n\n此操作将清除以下所有数据：\n• 所有阅读进度\n• 所有书签\n• 所有个性化设置\n\n书籍文件将保留，重启后自动加载。\n\n此操作不可撤销！', async () => {
        try {
            showToast('正在重置并重启...');
            await api().reset_app();
        } catch (e) { }
    });
}

async function openDataFolder() { try { await api().open_data_folder(); } catch (e) { showToast('打开存档目录失败'); } }

var _logAutoTimer = null;
var _logData = [];
async function loadLogs() {
    try {
        var level = document.getElementById('logLevelFilter').value;
        var search = document.getElementById('logSearch').value || '';
        var data = await api().get_logs(level, 500, search);
        _logData = data.logs || [];
        renderLogs(_logData);
        var el = document.getElementById('logCount');
        if (el) el.textContent = _logData.length + ' 条' + (data.total >= 500 ? '（最近500条）' : '');
    } catch (e) { showToast('加载日志失败: ' + (e.message || e)); }
}
// 日志多选状态
var _selectedLogRows = new Set();
var _lastClickedLogIndex = -1;
var _lastRenderedLogCount = 0;
var _lastRenderedLogMsg = '';

function _buildLogRowHtml(log, index) {
    var lvl = log.level || 'INFO';
    var color = lvl === 'ERROR' || lvl === 'CRITICAL' ? 'var(--danger)' : lvl === 'WARNING' ? 'var(--warning)' : lvl === 'DEBUG' ? 'var(--fg3)' : 'var(--accent)';
    var bg = lvl === 'ERROR' || lvl === 'CRITICAL' ? 'rgba(var(--danger-rgb),0.08)' : lvl === 'WARNING' ? 'rgba(var(--warning-rgb),0.06)' : 'transparent';
    var time = log.time ? log.time.split(' ')[1] || log.time : '';
    var logText = time + ' [' + lvl + '] ' + log.message;
    var isSelected = _selectedLogRows.has(index);
    var selectedBg = isSelected ? 'rgba(var(--accent-rgb), 0.15)' : bg;
    var selectedBorder = isSelected ? '1px solid rgba(var(--accent-rgb), 0.4)' : '1px solid transparent';
    return '<div class="log-row" data-log-index="' + index + '" data-log-text="' + escapeAttr(logText) + '" style="padding:2px 6px;border-radius:4px;background:' + selectedBg + ';border:' + selectedBorder + ';margin-bottom:1px;display:flex;gap:8px;align-items:flex-start;cursor:text;transition:background 0.15s;user-select:text;-webkit-user-select:text;">' +
        '<span style="color:var(--fg3);flex-shrink:0;min-width:80px;">' + escapeHtml(time) + '</span>' +
        '<span style="color:' + color + ';flex-shrink:0;min-width:56px;font-weight:600;">' + escapeHtml(lvl) + '</span>' +
        '<span style="color:var(--fg);word-break:break-all;white-space:pre-wrap;flex:1;">' + escapeHtml(log.message) + '</span>' +
        '</div>';
}

function renderLogs(logs, forceFull) {
    var el = document.getElementById('logContainer');
    if (!el) return;
    if (!logs || logs.length === 0) {
        el.innerHTML = '<div style="text-align:center;color:var(--fg3);padding:40px;">暂无日志</div>';
        _lastRenderedLogCount = 0;
        _lastRenderedLogMsg = '';
        return;
    }

    var appended = false;
    if (!forceFull && logs.length > _lastRenderedLogCount && _lastRenderedLogCount > 0) {
        var boundary = _lastRenderedLogCount - 1;
        if (logs[boundary].message === _lastRenderedLogMsg) {
            var frag = document.createDocumentFragment();
            for (var i = _lastRenderedLogCount; i < logs.length; i++) {
                var div = document.createElement('div');
                div.innerHTML = _buildLogRowHtml(logs[i], i);
                frag.appendChild(div.firstChild);
            }
            el.appendChild(frag);
            appended = true;
        }
    }

    if (!appended) {
        var html = '';
        for (var i = 0; i < logs.length; i++) {
            html += _buildLogRowHtml(logs[i], i);
        }
        el.innerHTML = html;
    }

    _lastRenderedLogCount = logs.length;
    _lastRenderedLogMsg = logs[logs.length - 1].message;
    if (appended) el.scrollTop = el.scrollHeight;

    setupLogMultiSelect();
}

function setupLogMultiSelect() {
    var el = document.getElementById('logContainer');
    if (!el || el._multiSelectReady) return;
    el._multiSelectReady = true;

    el.addEventListener('mousedown', function(e) {
        var row = e.target.closest('.log-row');
        if (!row) return;
        if (e.ctrlKey || e.metaKey || e.shiftKey) e.preventDefault();
    });

    el.addEventListener('click', function(e) {
        var row = e.target.closest('.log-row');
        if (!row) return;
        var index = parseInt(row.dataset.logIndex);

        if (e.ctrlKey || e.metaKey) {
            if (_selectedLogRows.has(index)) {
                _selectedLogRows.delete(index);
                row.style.background = '';
                row.style.border = '1px solid transparent';
            } else {
                _selectedLogRows.add(index);
                row.style.background = 'rgba(var(--accent-rgb), 0.15)';
                row.style.border = '1px solid rgba(var(--accent-rgb), 0.4)';
            }
        } else if (e.shiftKey && _lastClickedLogIndex >= 0) {
            var start = Math.min(_lastClickedLogIndex, index);
            var end = Math.max(_lastClickedLogIndex, index);
            _selectedLogRows.clear();
            el.querySelectorAll('.log-row').forEach(function(r) {
                r.style.background = '';
                r.style.border = '1px solid transparent';
            });
            for (var i = start; i <= end; i++) {
                _selectedLogRows.add(i);
                var targetRow = el.querySelector('[data-log-index="' + i + '"]');
                if (targetRow) {
                    targetRow.style.background = 'rgba(var(--accent-rgb), 0.15)';
                    targetRow.style.border = '1px solid rgba(var(--accent-rgb), 0.4)';
                }
            }
        } else {
            _selectedLogRows.clear();
            el.querySelectorAll('.log-row').forEach(function(r) {
                r.style.background = '';
                r.style.border = '1px solid transparent';
            });
            _selectedLogRows.add(index);
            row.style.background = 'rgba(var(--accent-rgb), 0.15)';
            row.style.border = '1px solid rgba(var(--accent-rgb), 0.4)';
        }

        _lastClickedLogIndex = index;
        updateLogSelectionInfo();
    });
}

function updateLogSelectionInfo() {
    var countEl = document.getElementById('logSelectionCount');
    if (countEl) {
        if (_selectedLogRows.size > 0) {
            countEl.textContent = '已选中 ' + _selectedLogRows.size + ' 条';
            countEl.style.display = '';
        } else {
            countEl.style.display = 'none';
        }
    }
}

function copySelectedLogs() {
    if (_selectedLogRows.size === 0) {
        showToast('请先选中日志行');
        return;
    }
    
    var el = document.getElementById('logContainer');
    if (!el) return;
    
    var texts = [];
    _selectedLogRows.forEach(function(index) {
        var row = el.querySelector('[data-log-index="' + index + '"]');
        if (row) {
            texts.push(row.dataset.logText);
        }
    });
    
    if (texts.length > 0) {
        navigator.clipboard.writeText(texts.join('\n')).then(function() {
            showToast('已复制 ' + texts.length + ' 条日志');
        }).catch(function() {
            showToast('复制失败');
        });
    }
}

function selectAllLogs() {
    var el = document.getElementById('logContainer');
    if (!el) return;
    
    _selectedLogRows.clear();
    el.querySelectorAll('.log-row').forEach(function(row) {
        var index = parseInt(row.dataset.logIndex);
        _selectedLogRows.add(index);
        row.style.background = 'rgba(var(--accent-rgb), 0.15)';
        row.style.border = '1px solid rgba(var(--accent-rgb), 0.4)';
    });
    
    updateLogSelectionInfo();
}

function clearLogSelection() {
    var el = document.getElementById('logContainer');
    if (!el) return;
    
    _selectedLogRows.clear();
    el.querySelectorAll('.log-row').forEach(function(row) {
        row.style.background = '';
        row.style.border = '1px solid transparent';
    });
    
    updateLogSelectionInfo();
}
function filterLogs() {
    var search = (document.getElementById('logSearch').value || '').toLowerCase();
    var level = document.getElementById('logLevelFilter').value;
    var filtered = _logData.filter(function(l) {
        if (level !== 'ALL' && l.level !== level) return false;
        if (search && (l.message || '').toLowerCase().indexOf(search) === -1 && (l.source || '').toLowerCase().indexOf(search) === -1) return false;
        return true;
    });
    renderLogs(filtered, true);
    var el = document.getElementById('logCount');
    if (el) el.textContent = filtered.length + ' / ' + _logData.length + ' 条';
}
function toggleLogAutoRefresh() {
    var checked = document.getElementById('logAutoRefresh').checked;
    if (checked) {
        _logAutoTimer = setInterval(loadLogs, 5000);
    } else {
        if (_logAutoTimer) { clearInterval(_logAutoTimer); _logAutoTimer = null; }
    }
}
function clearLogs() {
    showConfirm('清空日志', '确定要清空所有日志吗？\n\n此操作不可撤销。', async function() {
        try {
            var r = await api().clear_logs();
            if (r && r.success) { showToast('日志已清空'); loadLogs(); }
            else showToast('清空失败');
        } catch (e) { showToast('清空失败'); }
    });
}
function setupLogContextMenu() {
    var container = document.getElementById('logContainer');
    if (!container || container._ctxReady) return;
    container._ctxReady = true;
    var menu = document.createElement('div');
    menu.id = 'logContextMenu';
    menu.style.cssText = 'position:fixed;z-index:9999;background:var(--card-bg,#232336);border:1px solid var(--card-border);border-radius:8px;padding:4px 0;box-shadow:0 4px 20px rgba(0,0,0,.3);display:none;min-width:140px;';
    menu.innerHTML = '<div class="log-ctx-item" data-act="selectall" style="padding:6px 16px;cursor:pointer;font-size:13px;color:var(--fg);border-radius:4px;margin:0 4px;">' + ICONS.selectAll + ' 全选</div>' +
        '<div class="log-ctx-item" data-act="copy" style="padding:6px 16px;cursor:pointer;font-size:13px;color:var(--fg);border-radius:4px;margin:0 4px;">' + ICONS.copy + ' 复制选中</div>';
    document.body.appendChild(menu);
    menu.addEventListener('mouseover', function(e) { if (e.target.classList.contains('log-ctx-item')) e.target.style.background = 'var(--hover-bg,rgba(255,255,255,.08))'; });
    menu.addEventListener('mouseout', function(e) { if (e.target.classList.contains('log-ctx-item')) e.target.style.background = ''; });
    menu.addEventListener('click', function(e) {
        var act = e.target.dataset.act;
        if (act === 'selectall') {
            var range = document.createRange();
            range.selectNodeContents(container);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
        } else if (act === 'copy') {
            var text = window.getSelection().toString();
            if (!text) {
                var range2 = document.createRange();
                range2.selectNodeContents(container);
                var sel2 = window.getSelection();
                sel2.removeAllRanges();
                sel2.addRange(range2);
                text = sel2.toString();
            }
            if (text) {
                navigator.clipboard.writeText(text).then(function() { showToast('已复制到剪贴板'); }).catch(function() {
                    document.execCommand('copy');
                    showToast('已复制到剪贴板');
                });
            } else {
                showToast('没有可复制的内容');
            }
        }
        menu.style.display = 'none';
    });
    document.addEventListener('click', function() { menu.style.display = 'none'; });
    container.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
        menu.style.display = 'block';
    });
}

function showConfirm(title, msg, cb) {
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmMessage').innerHTML = escapeHtml(msg).replace(/\n/g, '<br>');
    confirmCallback = cb;
    document.getElementById('confirmModal').classList.add('active');
}
function closeConfirm() { document.getElementById('confirmModal').classList.remove('active'); confirmCallback = null; }
function confirmAction() { if (confirmCallback) confirmCallback(); closeConfirm(); }

let promptCallback = null;
function showPrompt(title, label, defaultValue, cb) {
    document.getElementById('promptTitle').textContent = title;
    document.getElementById('promptLabel').textContent = label;
    const input = document.getElementById('promptInput');
    input.value = defaultValue || '';
    promptCallback = cb;
    document.getElementById('promptModal').classList.add('active');
    setTimeout(() => { input.focus(); input.select(); }, 50);
}
function closePrompt() { document.getElementById('promptModal').classList.remove('active'); promptCallback = null; }
function promptConfirmAction() {
    const val = document.getElementById('promptInput').value;
    if (promptCallback) promptCallback(val);
    closePrompt();
}

function navTo(page) {
    document.querySelectorAll('.nav-links a').forEach(a => a.classList.remove('active'));
    document.querySelectorAll('.page-panel').forEach(p => p.classList.remove('active'));
    const sb = document.getElementById('sidebar');
    if (sb) sb.style.display = page === 'shelf' ? '' : 'none';
    var themeBox = document.getElementById('themePhysics');
    if (page !== 'settings' && themeBox && themeBox._physicsPause) themeBox._physicsPause();
    var link = document.querySelector('.nav-links a[data-page="' + page + '"]');
    var panel = document.getElementById('page' + page.charAt(0).toUpperCase() + page.slice(1));
    if (link && panel) {
        link.classList.add('active');
        panel.classList.add('active');
        if (page === 'shelf' && _shelfDirty) { _shelfDirty = false; loadBooks(); }
        if (page === 'settings') {
            renderThemeGrid();
            renderLayoutSelector();
            if (typeof loadFontList === 'function') loadFontList();
            var tb = document.getElementById('themePhysics');
            if (tb && tb._physicsResume) tb._physicsResume();
        }
        if (page === 'bookmark' && _bookmarkDirty) { _bookmarkDirty = false; loadBookmarks(); }
        if (page === 'notes' && _notesDirty) { _notesDirty = false; loadNotes(); }
        if (page === 'stats') loadStatsPage();
        if (page === 'log') { loadLogs(); toggleLogAutoRefresh(); setupLogContextMenu(); }
    }
}

function showContextMenu(e, name) {
    e.preventDefault();
    contextMenuBook = name;
    const m = document.getElementById('contextMenu');
    
    // 计算菜单位置，确保不超出屏幕
    var x = e.clientX;
    var y = e.clientY;
    var menuWidth = 180;
    var menuHeight = 300;
    
    if (x + menuWidth > window.innerWidth) {
        x = window.innerWidth - menuWidth - 10;
    }
    if (y + menuHeight > window.innerHeight) {
        y = window.innerHeight - menuHeight - 10;
    }
    
    m.style.left = x + 'px';
    m.style.top = y + 'px';
    m.classList.add('active');
    
    // 更新菜单项状态
    var book = books.find(b => b.name === name);
    if (book) {
        var progressItem = m.querySelector('[data-action="progress"]');
        if (progressItem) {
            progressItem.style.display = book.progress === '100%' ? 'none' : '';
        }
    }
}
function hideContextMenu() { document.getElementById('contextMenu').classList.remove('active'); contextMenuBook = null; }
function openBookFromContext() { if (contextMenuBook) openBook(contextMenuBook); hideContextMenu(); }
function openBookDirFromContext() { if (contextMenuBook) { api().open_book_directory(contextMenuBook).catch(() => {}); } hideContextMenu(); }
function copyBookName() {
    if (contextMenuBook) {
        try { navigator.clipboard.writeText(contextMenuBook); showToast('已复制：' + contextMenuBook); }
        catch (e) { showToast('复制失败'); }
    }
    hideContextMenu();
}
function copyBookPath() {
    if (contextMenuBook) {
        var book = books.find(b => b.name === contextMenuBook);
        if (book && book.file_path) {
            try { navigator.clipboard.writeText(book.file_path); showToast('已复制文件路径'); }
            catch (e) { showToast('复制失败'); }
        }
    }
    hideContextMenu();
}
function deleteBookFromContext() { if (contextMenuBook) deleteBook(contextMenuBook); hideContextMenu(); }
function renameBookFromContext() {
    if (!contextMenuBook) { hideContextMenu(); return; }
    const bookName = contextMenuBook;
    hideContextMenu();
    const book = books.find(b => b.name === bookName);
    const currentDisplay = book ? (book.display_name || book.name) : bookName;
    showPrompt('重命名', '请输入新的显示名称：', currentDisplay, async function(newName) {
        if (newName === null || newName === undefined) return;
        if (!newName.trim()) { showToast('名称不能为空'); return; }
        try {
            const r = await api().set_display_name(bookName, newName.trim());
            if (r.success) {
                const book = books.find(b => b.name === bookName);
                if (book) { book.display_name = newName.trim(); }
                _booksDirty = true;
                await loadDashboard();
            } else {
                showToast(r.error || '重命名失败');
            }
        } catch (e) { showToast('重命名失败'); }
    });
}

function showBookDetailFromContext() {
    if (!contextMenuBook) { hideContextMenu(); return; }
    const bookName = contextMenuBook;
    hideContextMenu();
    const book = books.find(b => b.name === bookName);
    if (!book) { showToast('未找到书籍'); return; }
    const displayName = escapeHtml(book.display_name || book.name);
    const fileName = escapeHtml(book.name + '.' + (book.format || 'txt').toLowerCase());
    const fileSize = escapeHtml(book.size || '未知');
    const format = escapeHtml(book.format || 'TXT');
    const chapters = escapeHtml(String(book.chapters || 0));
    const wordCount = escapeHtml(book.word_count_text || '0');
    const lastRead = escapeHtml(book.last_read ? _fmtTimeDetail(book.last_read) : '尚未阅读');
    const progress = escapeHtml(book.progress || '未读');
    const body = document.getElementById('detailBody');
    body.innerHTML =
        '<div style="display:flex;justify-content:space-between;"><span style="color:var(--fg2);">文件名</span><span>' + fileName + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;"><span style="color:var(--fg2);">文件大小</span><span>' + fileSize + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;"><span style="color:var(--fg2);">格式</span><span>' + format + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;"><span style="color:var(--fg2);">章节数</span><span>' + chapters + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;"><span style="color:var(--fg2);">总字数</span><span>' + wordCount + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;"><span style="color:var(--fg2);">最后阅读</span><span>' + lastRead + '</span></div>' +
        '<div style="display:flex;justify-content:space-between;"><span style="color:var(--fg2);">阅读进度</span><span>' + progress + '</span></div>';
    document.getElementById('detailTitle').textContent = displayName + ' — 详情';
    document.getElementById('detailModal').classList.add('active');
}
function closeDetailModal() { document.getElementById('detailModal').classList.remove('active'); }

function setStatus(text) { document.getElementById('statusText').textContent = text; }

async function loadSettings() {
    try {
        settings = await api().get_settings();
        document.getElementById('fontFamily').value = settings.font_family || 'Microsoft YaHei';
        var _ffLabel = document.getElementById('fontFamilyLabel');
        if (_ffLabel) { var _ffOpt = document.querySelector('#fontFamilyPanel .font-dd-opt[data-val="' + (settings.font_family || 'Microsoft YaHei') + '"]'); if (_ffOpt) _ffLabel.textContent = _ffOpt.querySelector('.font-dd-name').textContent; }
        var el;
        el = document.getElementById('fontSize'); if (el) el.value = settings.font_size || 18;
        el = document.getElementById('fontSizeValue'); if (el) el.textContent = settings.font_size || 18;
        const ls = Math.round((settings.line_spacing || 1.8) * 10);
        document.getElementById('lineSpacing').value = ls;
        document.getElementById('lineSpacingValue').textContent = (ls / 10).toFixed(1);
        document.getElementById('paragraphSpacing').value = settings.paragraph_spacing != null ? settings.paragraph_spacing : 20;
        document.getElementById('paragraphSpacingValue').textContent = settings.paragraph_spacing != null ? settings.paragraph_spacing : 20;
        document.getElementById('textIndent').value = settings.text_indent != null ? settings.text_indent : 2;
        document.getElementById('textIndentValue').textContent = settings.text_indent != null ? settings.text_indent : 2;
        if (window.updateClickBar) { updateClickBar('lineSpacing'); updateClickBar('paragraphSpacing'); updateClickBar('textIndent'); }
        const homeBg = settings.home_bg_image || '';
        const homeBgOp = Math.round((settings.home_bg_opacity || 0.10) * 100);
        document.getElementById('homeBgOpacity').value = homeBgOp;
        document.getElementById('homeBgOpacityValue').textContent = homeBgOp + '%';
        if (window.updateClickBar) updateClickBar('homeBgOpacity');
        if (homeBg) {
            homeBgPath = homeBg;
            document.getElementById('homeBgStatus').textContent = '✓';
            document.getElementById('homeBgStatus').style.color = 'var(--accent)';
            try {
                const dataUrl = await api().get_image_data_url(homeBg);
                if (dataUrl) homeBgDataUrl = dataUrl;
            } catch (e) {}
        }

        const readerBg = settings.reader_bg_image || settings.background_image || '';
        const readerBgOp = Math.round((settings.reader_bg_opacity || settings.background_opacity || 0.08) * 100);
        document.getElementById('readerBgOpacity').value = readerBgOp;
        document.getElementById('readerBgOpacityValue').textContent = readerBgOp + '%';
        if (window.updateClickBar) updateClickBar('readerBgOpacity');
        if (readerBg) {
            readerBgPath = readerBg;
            document.getElementById('readerBgStatus').textContent = '✓';
            document.getElementById('readerBgStatus').style.color = 'var(--accent)';
        }

        const notesBg = settings.notes_bg_image || '';
        const notesBgOp = Math.round((settings.notes_bg_opacity || 0.08) * 100);
        if (document.getElementById('notesBgOpacity')) {
            document.getElementById('notesBgOpacity').value = notesBgOp;
            document.getElementById('notesBgOpacityValue').textContent = notesBgOp + '%';
            if (window.updateClickBar) updateClickBar('notesBgOpacity');
        }
        if (notesBg) {
            notesBgPath = notesBg;
            if (document.getElementById('notesBgStatus')) {
                document.getElementById('notesBgStatus').textContent = '✓';
                document.getElementById('notesBgStatus').style.color = 'var(--accent)';
            }
            try {
                const dataUrl = await api().get_image_data_url(notesBg);
                if (dataUrl) notesBgDataUrl = dataUrl;
            } catch (e) {}
        }
    } catch (e) { showToast('加载设置失败'); }
}

async function loadBookmarks() {
    try {
        const bookmarks = await api().get_all_bookmarks();
        renderBookmarks(bookmarks);
    } catch (e) { showToast('加载书签失败'); }
}

function renderBookmarks(bookmarks) {
    const el = document.getElementById('bookmarkList');
    if (!bookmarks || bookmarks.length === 0) {
        el.innerHTML = '<div class="empty-state"><div class="icon">' + ICONS.bookmark + '</div><p>暂无书签</p></div>';
        return;
    }

    const groups = {};
    bookmarks.forEach(bm => {
        if (!groups[bm.book_name]) groups[bm.book_name] = [];
        groups[bm.book_name].push(bm);
    });

    // 使用数组和 join 优化字符串拼接
    const htmlParts = [];
    for (const bookName of Object.keys(groups)) {
        const items = groups[bookName];
        const [c1, c2] = getBookColor(bookName);
        const escapedBookName = escapeHtml(bookName);
        const escapedBookNameAttr = escapeAttr(bookName);
        
        htmlParts.push(`<div class="bookmark-group">`);
        htmlParts.push(`<div class="bookmark-group-title">`);
        htmlParts.push(`<span style="display:inline-block;width:14px;height:14px;border-radius:4px;background:linear-gradient(135deg,${c1},${c2});vertical-align:middle;"></span> `);
        htmlParts.push(`${escapedBookName}`);
        htmlParts.push(`<span class="bookmark-group-count">${items.length}</span>`);
        htmlParts.push(`</div>`);
        
        items.forEach(bm => {
            const timeStr = escapeHtml(bm.time || '');
            const desc = escapeHtml(bm.description || '无描述');
            const chapter = escapeHtml(bm.chapter || '未知章节');
            
            htmlParts.push(`<div class="bookmark-item" data-book-name="${escapedBookNameAttr}" data-bm-index="${bm.index}">`);
            htmlParts.push(`<div class="bookmark-icon">${ICONS.pin}</div>`);
            htmlParts.push(`<div class="bookmark-info">`);
            htmlParts.push(`<div class="bookmark-chapter">${chapter}</div>`);
            htmlParts.push(`<div class="bookmark-desc">${desc}</div>`);
            htmlParts.push(`</div>`);
            htmlParts.push(`<span class="bookmark-time">${timeStr}</span>`);
            htmlParts.push(`<button class="bookmark-del" data-book-name="${escapedBookNameAttr}" data-bm-index="${bm.index}" title="删除书签">✕</button>`);
            htmlParts.push(`</div>`);
        });
        htmlParts.push(`</div>`);
    }
    
    el.innerHTML = htmlParts.join('');
    el.querySelectorAll('.bookmark-item').forEach(item => {
        const name = item.dataset.bookName;
        const index = parseInt(item.dataset.bmIndex);
        item.addEventListener('click', () => gotoBookmark(name, index));
    });
    el.querySelectorAll('.bookmark-del').forEach(btn => {
        const name = btn.dataset.bookName;
        const index = parseInt(btn.dataset.bmIndex);
        btn.addEventListener('click', (e) => { e.stopPropagation(); removeBookmark(name, index); });
    });
}

async function gotoBookmark(bookName, index) {
    try {
        const loaded = await api().open_book(bookName);
        if (!loaded || !loaded.success) {
            showToast('打开书籍失败');
            return;
        }
        const r = await api().goto_bookmark(bookName, index);
        if (r && r.success) {
            await api().open_reader_window(bookName);
            showToast('已跳转到书签');
        } else {
            showToast('跳转书签失败');
        }
    } catch (e) { showToast('跳转书签失败'); }
}

async function removeBookmark(bookName, index) {
    showConfirm('删除书签', '确定要删除此书签吗？', async () => {
        try {
            const r = await api().remove_bookmark(bookName, index);
            if (r) {
                showToast('书签已删除');
                await loadBookmarks();
            } else {
                showToast('删除书签失败');
            }
        } catch (e) { showToast('删除书签失败'); }
    });
}

async function loadStatsPage() {
    try {
        const [s, allBooks] = await Promise.all([api().get_stats(), api().get_books()]);
        const container = document.getElementById('statsPage');

        let html = '<div class="timeline-wrap">';

        html += '<div class="tl-overview">';
        html += '<div class="tl-overview-card"><div class="tl-overview-val">' + escapeHtml(s.total_books) + '</div><div class="tl-overview-label">总藏书</div></div>';
        html += '<div class="tl-overview-card"><div class="tl-overview-val">' + escapeHtml(s.total_chapters) + '</div><div class="tl-overview-label">总章节</div></div>';
        html += '<div class="tl-overview-card"><div class="tl-overview-val">' + escapeHtml(s.reading_time) + '</div><div class="tl-overview-label">阅读时长</div></div>';
        html += '<div class="tl-overview-card"><div class="tl-overview-val">' + escapeHtml(s.progress_percent) + '%</div><div class="tl-overview-label">平均进度</div></div>';
        html += '</div>';

        if (allBooks && allBooks.length > 0) {
            const sorted = [...allBooks].sort((a, b) => {
                const ta = a.last_read || '';
                const tb = b.last_read || '';
                if (ta && tb) return tb.localeCompare(ta);
                if (ta) return -1;
                if (tb) return 1;
                return 0;
            });

            const now = new Date();
            const today = now.toISOString().slice(0, 10);
            const yesterday = new Date(now - 86400000).toISOString().slice(0, 10);

            let lastGroup = '';
            sorted.forEach(b => {
                const readDate = b.last_read ? b.last_read.slice(0, 10) : '';
                let group = '';
                if (readDate === today) group = '今天';
                else if (readDate === yesterday) group = '昨天';
                else if (readDate) {
                    const d = new Date(readDate);
                    const diff = Math.floor((now - d) / 86400000);
                    if (diff <= 7) group = '本周';
                    else if (diff <= 30) group = '本月';
                    else group = '更早';
                } else {
                    group = '未阅读';
                }

                if (group !== lastGroup) {
                    html += '<div class="tl-section-label">' + escapeHtml(group) + '</div>';
                    lastGroup = group;
                }

                const displayName = escapeHtml(b.display_name || b.name);
                const [c1, c2] = getBookColor(b.name);
                const ch = escapeHtml(b.cover_char || '?');
                const pctNum = parseInt(b.progress) || 0;
                const pctStr = b.progress || '未读';
                const pColor = 'hsl(' + (180 + pctNum * 1.5) + ',88%,55%)';
                const timeStr = b.last_read ? new Date(b.last_read).toLocaleString('zh-CN', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : '';

                html += '<div class="tl-item" data-book-name="' + escapeAttr(b.name) + '">';
                if (timeStr) html += '<div class="tl-item-date">' + escapeHtml(timeStr) + '</div>';
                html += '<div class="tl-item-head">';
                html += '<div class="tl-item-icon" style="background:linear-gradient(135deg,' + c1 + ',' + c2 + ')">' + ch + '</div>';
                html += '<div class="tl-item-name">' + displayName + '</div>';
                html += '<div class="tl-item-pct" style="color:' + pColor + '">' + escapeHtml(pctStr) + '</div>';
                html += '</div>';
                html += '<div class="tl-item-meta">' + escapeHtml(b.word_count_text) + '字 · ' + escapeHtml(b.chapters) + '章 · ' + escapeHtml(b.format || 'TXT') + '</div>';
                html += '</div>';
            });
        }

        html += '</div>';
        container.innerHTML = html;
        container.querySelectorAll('.tl-item[data-book-name]').forEach(item => {
            item.addEventListener('click', () => openBook(item.dataset.bookName));
        });
    } catch (e) { showToast('加载统计页面失败'); }
}

async function loadStats(force) {
    try {
        if (!force && _cachedStats) {
            applyStats(_cachedStats);
            return;
        }
        const s = await api().get_stats();
        _cachedStats = s;
        applyStats(s);
    } catch (e) { showToast('加载统计数据失败'); }
}
function applyStats(s) {
    if (!s) return;
    var el;
    el = document.getElementById('booksCount'); if (el) el.textContent = s.total_books || 0;
    el = document.getElementById('chaptersCount'); if (el) el.textContent = s.total_chapters || 0;
    el = document.getElementById('progressPercent'); if (el) el.textContent = (s.progress_percent || 0) + '%';
    el = document.getElementById('readingTime');
    if (el) {
        var t = s.reading_time || '0秒';
        if (typeof t === 'string' && t.includes('小时')) el.textContent = t.split('小时')[0] + 'h';
        else if (typeof t === 'string' && t.includes('分钟')) el.textContent = t.split('分钟')[0] + 'm';
        else el.textContent = (typeof t === 'string' ? t.split('秒')[0] : '0') + 's';
    }
    el = document.getElementById('readingTimeUnit'); if (el) el.textContent = '阅读时长';
    if (typeof updateHero === 'function') updateHero(s.last_read_book);
}

async function renderLayoutSelector() {
    try {
        const layouts = await api().get_available_layouts();
        const settingsEl = document.querySelector('.inline-settings');
        if (!settingsEl) return;
        let existing = document.getElementById('layoutSelectorCard');
        if (existing) existing.remove();
        const card = document.createElement('div');
        card.className = 'is-card';
        card.id = 'layoutSelectorCard';
        const currentLayout = settings.home_layout || 'nautical';
        card.innerHTML = '<div class="is-card-title">' + ICONS.layout + ' 主页布局</div>' +
            '<div style="display:flex;gap:5px;flex-wrap:wrap;">' +
            layouts.map(l => {
                const active = l.id === currentLayout;
                return '<div class="layout-option" data-layout="' + l.id + '" style="' +
                    'flex:1;min-width:70px;padding:6px 8px;border-radius:5px;cursor:pointer;' +
                    'border:1.5px solid ' + (active ? 'var(--accent)' : 'var(--card-border)') + ';' +
                    'background:' + (active ? 'rgba(255,110,199,0.08)' : 'var(--card)') + ';' +
                    'transition:all 0.2s;text-align:center;">' +
                    '<div style="font-size:11px;font-weight:600;color:var(--fg);">' + escapeHtml(l.name) + '</div>' +
                    (active ? '<div style="font-size:8px;color:var(--accent);margin-top:1px;">✓</div>' : '') +
                    '</div>';
            }).join('') +
            '</div>';
        const firstChild = settingsEl.firstChild;
        settingsEl.insertBefore(card, firstChild);
        card.querySelectorAll('.layout-option').forEach(opt => {
            opt.addEventListener('click', async function() {
                const layout = this.dataset.layout;
                if (layout === currentLayout) return;
                try {
                    await api().set_home_layout(layout);
                } catch (e) {}
            });
        });
    } catch (e) {}
}

async function renderThemeGrid() {
    try {
        if (allThemeData.length === 0) {
            const themes = await api().get_all_themes();
            allThemeData = themes;
        }
        customThemesList = await api().get_custom_themes();
        const current = settings.current_theme || '深渊';
        const grid = document.getElementById('themeGrid');
        const darkOrder = ['深渊','子夜','幽林','靛蓝','暮烟','紫夜','酒红','琥珀','柿饼','冰川'];
        const lightOrder = ['珍珠','月白','雾蓝','丁香','裸粉','鹅黄','银灰','青碧','云白','桃夭'];
        const byName = {};
        allThemeData.forEach(t => { byName[t.name] = t; });
        const ordered = [];
        darkOrder.forEach(n => { if (byName[n]) ordered.push(byName[n]); });
        lightOrder.forEach(n => { if (byName[n]) ordered.push(byName[n]); });

        var oldBox = document.getElementById('themePhysics');
        if (oldBox && oldBox._physicsCleanup) { oldBox._physicsCleanup(); }
        grid.className = '';
        grid.innerHTML = '<div class="theme-search-bar"><input type="text" class="theme-search-input" id="themeSearchInput" placeholder="搜索主题..." oninput="filterThemeBalls(this.value)"></div><div class="theme-physics" id="themePhysics"></div>';
        const box = document.getElementById('themePhysics');
        _initThemePhysics(box, ordered, customThemesList, current);
        loadColorPalette(current);
    } catch (e) { showToast('加载主题列表失败'); }
}

function _initThemePhysics(box, themes, customThemes, currentTheme) {
    var allThemes = themes.concat(customThemes || []);
    var W = box.offsetWidth || 420;
    var H = Math.max(144, Math.min(208, Math.floor((120 + allThemes.length * 4) * 0.8)));
    box.style.height = H + 'px';
    var R = Math.max(10, Math.min(18, Math.floor(W / (allThemes.length * 1.6 + 4))));
    if (allThemes.length <= 12) R = Math.min(18, Math.floor(W / 16));
    var N = allThemes.length;
    var balls = [];
    var dragBall = null;
    var dragOffX = 0, dragOffY = 0;
    var dragMoved = 0;
    var animId = null;
    var presetCount = themes.length;

    for (var i = 0; i < N; i++) {
        var t = allThemes[i];
        var isCustom = !!t.custom;
        var el = document.createElement('div');
        el.className = 'theme-ball' + (isCustom ? ' theme-ball-custom' : '') + (t.name === currentTheme ? ' active' : '');
        el.style.width = el.style.height = R * 2 + 'px';
        el.dataset.themeName = t.name;
        if (isCustom) {
            el.dataset.uid = t.name;
        }
        var numLabel = isCustom ? 'C' + (i - presetCount + 1) : String(i + 1);
        var ballLabel = isCustom ? escapeHtml(t.display_name || ('自定义' + (i - presetCount + 1))) : escapeHtml(t.name);
        el.innerHTML = '<div class="theme-ball-inner" style="background:' + t.bg + '">' +
            '<div class="theme-ball-num" style="color:' + t.tip + ';font-size:' + (R < 14 ? '9' : '11') + 'px">' + numLabel + '</div>' +
            '<div class="theme-ball-shade"></div><div class="theme-ball-rim"></div></div>' +
            '<div class="theme-ball-label" style="color:' + t.fg + '">' + ballLabel + '</div>' +
            (isCustom ? '<div class="ball-del-btn" data-uid="' + escapeAttr(t.name) + '">✕</div>' : '');
        box.appendChild(el);

        var cols = Math.max(1, Math.floor((W - R * 2) / (R * 2.4)));
        var row = Math.floor(i / cols);
        var col = i % cols;
        var x = R + col * (R * 2.4) + (row % 2 ? R * 0.6 : 0);
        var y = R + row * (R * 2.4);
        x = Math.max(R, Math.min(W - R, x));
        y = Math.max(R, Math.min(H - R, y));

        balls.push({
            el: el, name: t.name, x: x, y: y,
            vx: (Math.random() - 0.5) * 2,
            vy: (Math.random() - 0.5) * 2,
            r: R, m: 1, isCustom: isCustom
        });
        el.style.transform = 'translate(' + (x - R) + 'px,' + (y - R) + 'px)';
    }

    function getPos(e) {
        var rect = box.getBoundingClientRect();
        var ct = e.touches ? e.touches[0] : e;
        return { x: ct.clientX - rect.left, y: ct.clientY - rect.top };
    }

    function findBallAt(px, py) {
        for (var i = balls.length - 1; i >= 0; i--) {
            var b = balls[i];
            var dx = px - b.x, dy = py - b.y;
            if (dx * dx + dy * dy <= b.r * b.r * 1.2) return b;
        }
        return null;
    }

    function onDown(e) {
        var target = e.target;
        if (target.classList.contains('ball-del-btn')) {
            e.preventDefault();
            e.stopPropagation();
            var uid = target.dataset.uid;
            if (uid) _deleteCustomTheme(uid);
            return;
        }
        e.preventDefault();
        var p = getPos(e);
        var b = findBallAt(p.x, p.y);
        if (!b) return;
        dragBall = b;
        dragOffX = p.x - b.x;
        dragOffY = p.y - b.y;
        dragMoved = 0;
        b.vx = 0; b.vy = 0;
        b.el.classList.add('dragging');
        b.el.style.cursor = 'grabbing';
        b.el.style.zIndex = 10;
    }

    function onMove(e) {
        if (!dragBall) return;
        e.preventDefault();
        var p = getPos(e);
        var nx = p.x - dragOffX;
        var ny = p.y - dragOffY;
        dragMoved += Math.abs(nx - dragBall.x) + Math.abs(ny - dragBall.y);
        dragBall.vx = (nx - dragBall.x) * 0.4;
        dragBall.vy = (ny - dragBall.y) * 0.4;
        dragBall.x = Math.max(dragBall.r, Math.min(W - dragBall.r, nx));
        dragBall.y = Math.max(dragBall.r, Math.min(H - dragBall.r, ny));
        dragBall.el.style.transform = 'translate(' + (dragBall.x - dragBall.r) + 'px,' + (dragBall.y - dragBall.r) + 'px)';
    }

    function onUp(e) {
        if (!dragBall) return;
        dragBall.el.classList.remove('dragging');
        dragBall.el.style.cursor = 'grab';
        dragBall.el.style.zIndex = '';
        if (dragMoved < 4) {
            selectTheme(dragBall.name, dragBall.el);
            document.querySelectorAll('.theme-ball').forEach(function(b) { b.classList.remove('active'); });
            dragBall.el.classList.add('active');
        }
        dragBall = null;
    }

    box.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    box.addEventListener('touchstart', onDown, { passive: false });
    window.addEventListener('touchmove', onMove, { passive: false });
    window.addEventListener('touchend', onUp);

    var friction = 0.985;
    var bounce = 0.6;
    var prevSX = 0, prevSY = 0;
    try { prevSX = window.screenX || 0; prevSY = window.screenY || 0; } catch(e) {}
    var frameCount = 0;
    var paused = false;
    var _rafStopped = false;
    var _idleFrames = 0;
    var _IDLE_THRESHOLD = 60;
    var _animating = false;

    function wakeUp() {
        if (!_animating && !paused) {
            _animating = true;
            _idleFrames = 0;
            animId = requestAnimationFrame(step);
        }
    }

    function step() {
        if (paused) { _rafStopped = true; _animating = false; return; }
        if (++frameCount % 3 === 0) {
            try {
                var curSX = window.screenX || 0;
                var curSY = window.screenY || 0;
                var sdx = curSX - prevSX;
                var sdy = curSY - prevSY;
                if (Math.abs(sdx) + Math.abs(sdy) > 1) {
                    _idleFrames = 0;
                    var force = 0.04;
                    for (var i = 0; i < balls.length; i++) {
                        if (balls[i] === dragBall) continue;
                        balls[i].vx += sdx * force * (0.5 + Math.random() * 0.5);
                        balls[i].vy += sdy * force * (0.5 + Math.random() * 0.5);
                    }
                }
                prevSX = curSX;
                prevSY = curSY;
            } catch(e) {}
        }
        var allIdle = true;
        for (var i = 0; i < balls.length; i++) {
            var a = balls[i];
            if (a === dragBall) continue;
            a.vy += 0.03;
            a.vx *= friction;
            a.vy *= friction;
            a.x += a.vx;
            a.y += a.vy;
            if (a.x - a.r < 0) { a.x = a.r; a.vx = Math.abs(a.vx) * bounce; }
            if (a.x + a.r > W) { a.x = W - a.r; a.vx = -Math.abs(a.vx) * bounce; }
            if (a.y - a.r < 0) { a.y = a.r; a.vy = Math.abs(a.vy) * bounce; }
            if (a.y + a.r > H) { a.y = H - a.r; a.vy = -Math.abs(a.vy) * bounce; }
            if (Math.abs(a.vx) > 0.01 || Math.abs(a.vy) > 0.01) allIdle = false;
        }
        if (!allIdle || dragBall) {
            _idleFrames = 0;
            for (var i = 0; i < balls.length; i++) {
                for (var j = i + 1; j < balls.length; j++) {
                    var a = balls[i], b = balls[j];
                    var dx = b.x - a.x, dy = b.y - a.y;
                    var distSq = dx * dx + dy * dy;
                    var minD = a.r + b.r;
                    if (distSq < minD * minD && distSq > 0.0001) {
                        var dist = Math.sqrt(distSq);
                        var nx = dx / dist, ny = dy / dist;
                        var overlap = (minD - dist) * 0.5;
                        if (a !== dragBall) { a.x -= nx * overlap; a.y -= ny * overlap; }
                        if (b !== dragBall) { b.x += nx * overlap; b.y += ny * overlap; }
                        var dvx = a.vx - b.vx, dvy = a.vy - b.vy;
                        var dot = dvx * nx + dvy * ny;
                        if (dot > 0) {
                            var imp = dot * 0.9;
                            if (a !== dragBall) { a.vx -= imp * nx; a.vy -= imp * ny; }
                            if (b !== dragBall) { b.vx += imp * nx; b.vy += imp * ny; }
                        }
                    }
                }
            }
        } else {
            _idleFrames++;
        }
        if (_idleFrames < _IDLE_THRESHOLD) {
            for (var i = 0; i < balls.length; i++) {
                var b = balls[i];
                b.el.style.transform = 'translate(' + (b.x - b.r) + 'px,' + (b.y - b.r) + 'px)';
            }
            animId = requestAnimationFrame(step);
        } else {
            _animating = false;
        }
    }
    wakeUp();

    function _resume() {
        if (paused) { paused = false; _idleFrames = 0; }
        if (_rafStopped) { _rafStopped = false; animId = requestAnimationFrame(step); }
    }
    box._physicsResume = _resume;

    var ro = new ResizeObserver(function() {
        W = box.offsetWidth || 420;
    });
    ro.observe(box);

    box._physicsBalls = balls;
    box._physicsPause = function() { paused = true; };
    box._physicsCleanup = function() {
        cancelAnimationFrame(animId);
        ro.disconnect();
        box.removeEventListener('mousedown', onDown);
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
        box.removeEventListener('touchstart', onDown);
        window.removeEventListener('touchmove', onMove);
        window.removeEventListener('touchend', onUp);
    };
}

function filterThemeBalls(query) {
    var q = (query || '').toLowerCase().trim();
    var balls = document.querySelectorAll('#themePhysics .theme-ball');
    balls.forEach(function(b) {
        if (!q) {
            b.style.opacity = '';
            b.style.pointerEvents = '';
            return;
        }
        var name = (b.dataset.themeName || '').toLowerCase();
        var label = (b.querySelector('.theme-ball-label') || {}).textContent || '';
        label = label.toLowerCase();
        var match = name.indexOf(q) >= 0 || label.indexOf(q) >= 0;
        b.style.opacity = match ? '' : '0.15';
        b.style.pointerEvents = match ? '' : 'none';
    });
}

function selectTheme(name, el) {
    document.querySelectorAll('.theme-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.theme-ball').forEach(i => i.classList.remove('active'));
    if (el) el.classList.add('active');
    settings.current_theme = name;
    var t = allThemeData.find(x => x.name === name);
    if (!t && customThemesList) {
        t = customThemesList.find(x => x.name === name);
    }
    if (t) {
        if (t.custom) {
            customThemeColors = { name: 'custom', bg: t.bg, fg: t.fg, accent: t.accent, tip: t.tip, font_color: t.font_color };
            setStatus('主题：' + (t.display_name || '自定义') + '  ' + t.bg + ' / ' + t.fg + ' / ' + t.accent);
        } else {
            customThemeColors = null;
            setStatus('主题：' + t.name + '  ' + t.bg + ' / ' + t.fg + ' / ' + t.accent);
        }
        setColorPicker('capBg', t.bg);
        setColorPicker('capFg', t.fg);
        setColorPicker('capAccent', t.accent);
        setColorPicker('capTip', t.tip || mixHex(t.fg, t.bg, 0.5));
        setColorPicker('capFontColor', t.font_color || t.fg);
        previewThemeColors(t);
        try { api().preview_reader_theme(t); } catch(e) {}
    } else {
        customThemeColors = null;
    }
    autoSaveSettings();
}
function loadColorPalette(name) {
    let t = allThemeData.find(x => x.name === name);
    if (!t && customThemesList) { t = customThemesList.find(x => x.name === name); }
    if (!t && customThemeColors) { t = customThemeColors; }
    if (!t) return;
    setColorPicker('capAccent', t.accent);
    setColorPicker('capBg', t.bg);
    setColorPicker('capFg', t.fg);
    setColorPicker('capTip', t.tip || mixHex(t.fg, t.bg, 0.5));
    setColorPicker('capFontColor', t.font_color || t.fg);
}
function setColorPicker(id, color) {
    const picker = document.getElementById(id);
    const hex = document.getElementById(id + 'Hex');
    if (picker) picker.value = color;
    if (hex) hex.textContent = color;
}
function getColorPicker(id) {
    return document.getElementById(id).value;
}
function setupColorPaletteListeners() {
    const accentEl = document.getElementById('capAccent');
    if (accentEl) accentEl.addEventListener('input', function() {
        document.getElementById('capAccentHex').textContent = this.value;
        const accent = this.value;
        const bg = getColorPicker('capBg');
        const isLight = !isDarkColor(bg);
        const derived = deriveThemeFromAccent(accent, isLight, 30);
        setColorPicker('capBg', derived.bg);
        setColorPicker('capFg', derived.fg);
        setColorPicker('capTip', derived.tip);
        setColorPicker('capFontColor', derived.font_color);
        customThemeColors = {name:'custom', ...derived};
        previewThemeColors(customThemeColors);
        try { api().preview_reader_theme(customThemeColors); } catch(e) {}
        autoSaveSettings();
    });
    ['capBg', 'capFg', 'capTip', 'capFontColor'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', function() {
            document.getElementById(id + 'Hex').textContent = this.value;
            customThemeColors = {
                name: 'custom',
                bg: getColorPicker('capBg'),
                fg: getColorPicker('capFg'),
                accent: getColorPicker('capAccent'),
                tip: getColorPicker('capTip'),
                font_color: getColorPicker('capFontColor')
            };
            previewThemeColors(customThemeColors);
            try { api().preview_reader_theme(customThemeColors); } catch(e) {}
            if (id === 'capFontColor') { previewTypography(); }
            autoSaveSettings();
        });
    });
}
function hslToHex(h, s, l) {
    h = ((h % 360) + 360) % 360;
    s = Math.max(0, Math.min(1, s));
    l = Math.max(0, Math.min(1, l));
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs((h / 60) % 2 - 1));
    const m = l - c / 2;
    let r, g, b;
    if (h < 60) { r = c; g = x; b = 0; }
    else if (h < 120) { r = x; g = c; b = 0; }
    else if (h < 180) { r = 0; g = c; b = x; }
    else if (h < 240) { r = 0; g = x; b = c; }
    else if (h < 300) { r = x; g = 0; b = c; }
    else { r = c; g = 0; b = x; }
    const toHex = v => Math.round((v + m) * 255).toString(16).padStart(2, '0');
    return '#' + toHex(r) + toHex(g) + toHex(b);
}
function randomThemeColors() {
    const h = Math.random() * 360;
    const s = 0.50 + Math.random() * 0.40;
    const l = 0.40 + Math.random() * 0.25;
    const accent = hslToHex(h, s, l);
    const isLight = Math.random() > 0.5;
    const sat = 10 + Math.floor(Math.random() * 50);
    const derived = deriveThemeFromAccent(accent, isLight, sat);
    customThemeColors = { name: 'custom', ...derived };
    setColorPicker('capBg', derived.bg);
    setColorPicker('capFg', derived.fg);
    setColorPicker('capAccent', accent);
    setColorPicker('capTip', derived.tip);
    setColorPicker('capFontColor', derived.font_color);
    const preview = { bg: derived.bg, fg: derived.fg, accent: derived.accent, tip: derived.tip };
    previewThemeColors(preview);
    try { api().preview_reader_theme(preview); } catch(e) {}
    autoSaveSettings();
}

async function exportThemeColors() {
    try {
        const path = await api().export_theme_color();
        if (path) {
            showToast('配色已导出');
        } else {
            showToast('导出已取消');
        }
    } catch (e) { showToast('导出配色失败'); }
}

async function importThemeColors() {
    try {
        const colors = await api().import_theme_color();
        if (colors) {
            allThemeData = [];
            await loadTheme();
            if (document.getElementById('pageSettings').classList.contains('active')) {
                await renderThemeGrid();
            }
            showToast('配色已导入');
        } else {
            showToast('导入已取消');
        }
    } catch (e) { showToast('导入配色失败'); }
}

async function addCustomTheme() {
    const colors = customThemeColors || {
        bg: getColorPicker('capBg'),
        fg: getColorPicker('capFg'),
        accent: getColorPicker('capAccent'),
        tip: getColorPicker('capTip'),
        font_color: getColorPicker('capFontColor'),
    };
    if (!colors.bg || !colors.fg || !colors.accent) {
        showToast('请先选择或随机生成配色');
        return;
    }
    showPrompt('保存配色', '为此配色命名（可留空）：', '', async function(name) {
        if (name === null) return;
        await _doSaveCustomTheme(colors, name || '');
    });
}
async function _doSaveCustomTheme(colors, name) {
    try {
        const r = await api().save_custom_theme(colors, name);
        if (r && r.success) {
            showToast('配色已保存（共 ' + r.count + ' 个自定义）');
            customThemesList = [];
            allThemeData = [];
            if (document.getElementById('pageSettings').classList.contains('active')) {
                await renderThemeGrid();
                var box = document.getElementById('themePhysics');
                if (box && box._physicsBalls) {
                    var lastBall = box._physicsBalls[box._physicsBalls.length - 1];
                    if (lastBall) {
                        lastBall.el.classList.add('pop-in');
                        lastBall.vx = (Math.random() - 0.5) * 6;
                        lastBall.vy = -3 - Math.random() * 2;
                    }
                }
            }
        } else {
            showToast(r ? r.error : '保存失败');
        }
    } catch (e) { showToast('保存配色失败'); }
}

async function _deleteCustomTheme(uid) {
    showConfirm('删除自定义配色', '确定要删除这个自定义配色吗？', async () => {
        try {
            const r = await api().delete_custom_theme(uid);
            if (r && r.success) {
                showToast('已删除（剩余 ' + r.count + ' 个自定义）');
                customThemesList = [];
                allThemeData = [];
                if (document.getElementById('pageSettings').classList.contains('active')) {
                    await renderThemeGrid();
                }
            } else {
                showToast(r ? r.error : '删除失败');
            }
        } catch (e) { showToast('删除失败'); }
    });
}

async function exportAllThemes() {
    try {
        const path = await api().export_all_themes();
        if (path) {
            showToast('自定义配色已导出');
        } else {
            showToast('导出已取消');
        }
    } catch (e) { showToast('导出失败'); }
}

async function importAllThemes() {
    try {
        const r = await api().import_all_themes();
        if (r && r.success) {
            showToast(r.message || ('已导入 ' + r.imported + ' 个配色'));
            customThemesList = [];
            allThemeData = [];
            if (document.getElementById('pageSettings').classList.contains('active')) {
                await renderThemeGrid();
            }
        } else {
            showToast(r ? r.error : '导入失败');
        }
    } catch (e) { showToast('导入失败'); }
}

async function resetCurrentTheme() {
    const current = settings.current_theme || '';
    if (!current || current.startsWith('ct_')) {
        showToast('自定义配色无需重置');
        return;
    }
    try {
        const r = await api().reset_theme_colors(current);
        if (r && r.success) {
            showToast('已恢复「' + current + '」默认配色');
            allThemeData = [];
            await loadTheme();
            if (document.getElementById('pageSettings').classList.contains('active')) {
                await renderThemeGrid();
                loadColorPalette(current);
            }
        } else {
            showToast(r ? r.error : '重置失败');
        }
    } catch (e) { showToast('重置失败'); }
}

async function applySettings() {
    try {
        settings.font_family = document.getElementById('fontFamily').value;
        settings.font_size = parseInt((document.getElementById('fontSize') || {}).value || settings.font_size || 18);
        settings.line_spacing = parseFloat((document.getElementById('lineSpacing').value / 10).toFixed(1));
        settings.paragraph_spacing = parseInt(document.getElementById('paragraphSpacing').value);
        settings.text_indent = parseInt(document.getElementById('textIndent').value);
        settings.font_color = getColorPicker('capFontColor');
        settings.home_bg_image = homeBgPath || '';
        settings.home_bg_opacity = parseInt(document.getElementById('homeBgOpacity').value) / 100;
        settings.reader_bg_image = readerBgPath || '';
        settings.reader_bg_opacity = parseInt(document.getElementById('readerBgOpacity').value) / 100;
        settings.background_image = settings.reader_bg_image;
        settings.background_opacity = settings.reader_bg_opacity;
        settings.notes_bg_image = notesBgPath || '';
        settings.notes_bg_opacity = parseInt(document.getElementById('notesBgOpacity')?.value || '8') / 100;
        if (customThemeColors) {
            settings.theme_colors = {
                bg: getColorPicker('capBg'),
                fg: getColorPicker('capFg'),
                accent: getColorPicker('capAccent'),
                tip: getColorPicker('capTip'),
                font_color: getColorPicker('capFontColor')
            };
        } else {
            delete settings.theme_colors;
        }
        await Promise.all([
            api().update_settings(settings),
            api().refresh_reader_settings().catch(() => {})
        ]);
        await loadTheme();
    } catch (e) {}
}

function resetTypography() {
    const fs = document.getElementById('lineSpacing'), fv = document.getElementById('lineSpacingValue');
    const ps = document.getElementById('paragraphSpacing'), pd = document.getElementById('paragraphSpacingValue');
    const ti = document.getElementById('textIndent'), td = document.getElementById('textIndentValue');
    const ff = document.getElementById('fontFamily');
    const fl = document.getElementById('fontFamilyLabel');
    if (fs) { fs.value = 18; if (fv) fv.textContent = '1.8'; }
    if (ps) { ps.value = 20; if (pd) pd.textContent = '20'; }
    if (ti) { ti.value = 2; if (td) td.textContent = '2'; }
    if (ff) ff.value = 'Microsoft YaHei';
    if (fl) fl.textContent = '微软雅黑';
    if (window.updateClickBar) { updateClickBar('lineSpacing'); updateClickBar('paragraphSpacing'); updateClickBar('textIndent'); }
    previewTypography();
    showToast('已恢复默认排版');
}

async function loadFontList() {
    const wrap = document.getElementById('fontFamilyWrap');
    const panel = document.getElementById('fontFamilyPanel');
    const hidden = document.getElementById('fontFamily');
    const label = document.getElementById('fontFamilyLabel');
    if (!wrap || !panel || !hidden) return;
    const current = hidden.value || 'Microsoft YaHei';
    const builtIn = [
        {name:'微软雅黑', value:'Microsoft YaHei'},
        {name:'宋体', value:'SimSun'},
        {name:'楷体', value:'KaiTi'},
        {name:'仿宋', value:'FangSong'},
        {name:'苹方', value:'PingFang SC'},
        {name:'思源黑体', value:'Noto Sans CJK SC'},
    ];
    let customs = [];
    try { customs = await api().get_custom_fonts(); } catch(e) {}
    if (customs.length > 0) {
        let styleEl = document.getElementById('customFontStyles');
        if (!styleEl) {
            styleEl = document.createElement('style');
            styleEl.id = 'customFontStyles';
            document.head.appendChild(styleEl);
        }
        let css = '';
        for (const f of customs) {
            const fontName = String(f.name).replace(/"/g, '\\"');
            const fontPath = String(f.path).replace(/\\/g, '/').replace(/"/g, '%22');
            css += '@font-face{font-family:"' + fontName + '";src:url("file:///' + fontPath + '");}\n';
        }
        styleEl.textContent = css;
    }
    panel.replaceChildren();
    for (const f of builtIn) panel.appendChild(createFontOption(f.name, f.value, f.value === current));
    if (customs.length > 0) {
        const groupLabel = document.createElement('div');
        groupLabel.className = 'font-dd-grp-label';
        groupLabel.textContent = '自定义字体';
        panel.appendChild(groupLabel);
        for (const f of customs) panel.appendChild(createFontOption(f.name, f.name, f.name === current, true));
    }
    const activeOpt = panel.querySelector('.font-dd-opt.active');
    if (label) label.textContent = activeOpt ? activeOpt.querySelector('.font-dd-name').textContent : '微软雅黑';
}

function createFontOption(name, value, active, removable) {
    const opt = document.createElement('div');
    opt.className = 'font-dd-opt' + (active ? ' active' : '');
    opt.dataset.val = value;
    opt.onclick = function() { pickFont(opt); };
    const text = document.createElement('span');
    text.className = 'font-dd-name';
    text.textContent = name;
    opt.appendChild(text);
    if (removable) {
        const rm = document.createElement('span');
        rm.className = 'font-dd-rm';
        rm.title = '移除并删除';
        rm.textContent = '✕';
        rm.onclick = function(e) { removeFontItem(e, value); };
        opt.appendChild(rm);
    }
    return opt;
}

function toggleFontDropdown() {
    const wrap = document.getElementById('fontFamilyWrap');
    if (!wrap) return;
    const isOpen = wrap.classList.contains('open');
    closeFontDropdown();
    if (!isOpen) wrap.classList.add('open');
}

function closeFontDropdown() {
    const wrap = document.getElementById('fontFamilyWrap');
    if (wrap) wrap.classList.remove('open');
}

function pickFont(el) {
    const hidden = document.getElementById('fontFamily');
    const label = document.getElementById('fontFamilyLabel');
    if (hidden) hidden.value = el.dataset.val;
    if (label) label.textContent = el.querySelector('.font-dd-name').textContent;
    document.querySelectorAll('#fontFamilyPanel .font-dd-opt').forEach(o => o.classList.remove('active'));
    el.classList.add('active');
    closeFontDropdown();
    previewTypography();
}

async function removeFontItem(e, name) {
    e.stopPropagation();
    try {
        const ok = await api().remove_custom_font(name);
        if (ok) {
            const hidden = document.getElementById('fontFamily');
            if (hidden && hidden.value === name) {
                hidden.value = 'Microsoft YaHei';
                const label = document.getElementById('fontFamilyLabel');
                if (label) label.textContent = '微软雅黑';
            }
            await loadFontList();
            previewTypography();
            showToast('已移除: ' + name);
        }
    } catch (e) { showToast('移除失败'); }
}

document.addEventListener('click', function(e) {
    const wrap = document.getElementById('fontFamilyWrap');
    if (wrap && !wrap.contains(e.target)) closeFontDropdown();
});

async function addCustomFont() {
    try {
        const result = await api().import_font();
        if (result && result.count > 0) {
            await loadFontList();
            const hidden = document.getElementById('fontFamily');
            const label = document.getElementById('fontFamilyLabel');
            if (hidden && result.names && result.names.length > 0) {
                hidden.value = result.names[0];
                if (label) label.textContent = result.names[0];
                previewTypography();
            }
            showToast('已导入 ' + result.count + ' 个字体');
        }
    } catch (e) { showToast('导入字体失败'); }
}

async function openFontsFolder() {
    try { await api().open_fonts_folder(); } catch (e) { showToast('打开文件夹失败'); }
}

let _autoSaveTimer = null;
function autoSaveSettings() {
    clearTimeout(_autoSaveTimer);
    _autoSaveTimer = setTimeout(() => { applySettings(); }, 500);
}

let homeBgPath = null;
let homeBgDataUrl = null;
let readerBgPath = null;

async function selectHomeBg() {
    try {
        const path = await api().open_image_dialog();
        if (path) {
            homeBgPath = path;
            settings.home_bg_image = path;
            const dataUrl = await api().get_image_data_url(path);
            if (dataUrl) {
                homeBgDataUrl = dataUrl;
                document.getElementById('homeBgStatus').textContent = '✓';
                document.getElementById('homeBgStatus').style.color = 'var(--accent)';
                applyHomeBg(dataUrl);
            }
            autoSaveSettings();
            showToast('已设置主页背景');
        }
    } catch (e) { showToast('选择图片失败'); }
}

function clearHomeBg() {
    homeBgPath = null;
    homeBgDataUrl = null;
    settings.home_bg_image = '';
    document.getElementById('homeBgStatus').textContent = '-';
    document.getElementById('homeBgStatus').style.color = '';
    removeHomeBg();
    autoSaveSettings();
    showToast('已清除主页背景');
}

async function selectReaderBg() {
    try {
        const path = await api().open_image_dialog();
        if (path) {
            readerBgPath = path;
            settings.reader_bg_image = path;
            settings.background_image = path;
            document.getElementById('readerBgStatus').textContent = '✓';
            document.getElementById('readerBgStatus').style.color = 'var(--accent)';
            const dataUrl = await api().get_image_data_url(path);
            if (dataUrl) {
                previewTypography();
            }
            autoSaveSettings();
            showToast('已设置阅读背景');
        }
    } catch (e) { showToast('选择图片失败'); }
}

function clearReaderBg() {
    readerBgPath = null;
    settings.reader_bg_image = '';
    settings.background_image = '';
    document.getElementById('readerBgStatus').textContent = '-';
    document.getElementById('readerBgStatus').style.color = '';
    previewTypography();
    autoSaveSettings();
    showToast('已清除阅读背景');
}

let notesBgPath = null;
let notesBgDataUrl = null;
async function selectNotesBg() {
    try {
        const path = await api().open_image_dialog();
        if (path) {
            notesBgPath = path;
            settings.notes_bg_image = path;
            const dataUrl = await api().get_image_data_url(path);
            if (dataUrl) {
                notesBgDataUrl = dataUrl;
                document.getElementById('notesBgStatus').textContent = '✓';
                document.getElementById('notesBgStatus').style.color = 'var(--accent)';
            }
            autoSaveSettings();
            showToast('已设置便签背景');
        }
    } catch (e) { showToast('选择图片失败'); }
}
function clearNotesBg() {
    notesBgPath = null;
    notesBgDataUrl = null;
    settings.notes_bg_image = '';
    document.getElementById('notesBgStatus').textContent = '-';
    document.getElementById('notesBgStatus').style.color = '';
    autoSaveSettings();
    showToast('已清除便签背景');
}

function applyHomeBg(dataUrl) {
    if (homeBgPath) {
        const opacity = parseInt(document.getElementById('homeBgOpacity').value) / 100;
        const url = dataUrl || homeBgDataUrl;
        if (!url) return;
        homeBgDataUrl = url;
        const cs = getComputedStyle(document.documentElement);
        const bgHex = cs.getPropertyValue('--bg').trim();
        document.body.style.background = bgHex + ' url(' + url + ') center/cover no-repeat fixed';
        const app = document.getElementById('appRoot');
        const r = parseInt(bgHex.replace('#','').substring(0,2), 16) || 12;
        const g = parseInt(bgHex.replace('#','').substring(2,4), 16) || 12;
        const b = parseInt(bgHex.replace('#','').substring(4,6), 16) || 20;
        app.style.background = 'rgba(' + r + ',' + g + ',' + b + ',' + (1 - opacity) + ')';
    }
}

function removeHomeBg() {
    document.body.style.background = '';
    const app = document.getElementById('appRoot');
    app.style.background = '';
}

function setupFontSizeSlider() {
    const s = document.getElementById('fontSize'), d = document.getElementById('fontSizeValue');
    if (s && d) s.addEventListener('input', () => { d.textContent = s.value; previewTypography(); });
    window._onHomeBgChange = function() { applyHomeBg(); autoSaveSettings(); };
}
function setupLineSpacingSlider() {
    document.querySelectorAll('.click-bar[data-input]').forEach(initClickBar);
    document.getElementById('fontFamily').addEventListener('change', () => previewTypography());
}

function initClickBar(bar) {
    const inputId = bar.dataset.input;
    const input = document.getElementById(inputId);
    if (!input) return;
    const min = parseFloat(bar.dataset.min);
    const max = parseFloat(bar.dataset.max);
    const step = parseFloat(bar.dataset.step) || 1;
    const divVal = bar.dataset.displayDiv ? parseFloat(bar.dataset.displayDiv) : 0;
    const suffix = bar.dataset.suffix || '';
    const cbName = bar.dataset.callback || '';
    const fill = bar.querySelector('.click-bar-fill');
    const dot = bar.querySelector('.click-bar-dot');
    const tip = bar.querySelector('.click-bar-tooltip');

    function updateBar(val) {
        const pct = ((val - min) / (max - min)) * 100;
        fill.style.width = pct + '%';
        dot.style.left = pct + '%';
        const display = (divVal ? (val / divVal).toFixed(1) : val) + suffix;
        if (tip) tip.textContent = display;
        const svEl = bar.parentElement.querySelector('.sv');
        if (svEl) svEl.textContent = display;
    }

    function setFromX(clientX) {
        const rect = bar.getBoundingClientRect();
        let pct = (clientX - rect.left) / rect.width;
        pct = Math.max(0, Math.min(1, pct));
        let val = min + pct * (max - min);
        val = Math.round(val / step) * step;
        val = Math.max(min, Math.min(max, val));
        input.value = val;
        updateBar(val);
        if (cbName && window[cbName]) { try { window[cbName](); } catch(e) {} }
        else { previewTypography(); }
    }

    updateBar(parseFloat(input.value));

    bar.addEventListener('mousedown', function(e) {
        e.preventDefault();
        setFromX(e.clientX);
        function onMove(ev) { setFromX(ev.clientX); }
        function onUp() { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });

    bar.addEventListener('touchstart', function(e) {
        e.preventDefault();
        setFromX(e.touches[0].clientX);
        function onMove(ev) { ev.preventDefault(); setFromX(ev.touches[0].clientX); }
        function onUp() { document.removeEventListener('touchmove', onMove); document.removeEventListener('touchend', onUp); }
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('touchend', onUp);
    }, { passive: false });
}

window.updateClickBar = function(inputId) {
    const bar = document.querySelector('.click-bar[data-input="' + inputId + '"]');
    if (!bar) return;
    const input = document.getElementById(inputId);
    if (!input) return;
    const min = parseFloat(bar.dataset.min);
    const max = parseFloat(bar.dataset.max);
    const divVal = bar.dataset.displayDiv ? parseFloat(bar.dataset.displayDiv) : 0;
    const suffix = bar.dataset.suffix || '';
    const fill = bar.querySelector('.click-bar-fill');
    const dot = bar.querySelector('.click-bar-dot');
    const tip = bar.querySelector('.click-bar-tooltip');
    const val = parseFloat(input.value);
    const pct = ((val - min) / (max - min)) * 100;
    fill.style.width = pct + '%';
    dot.style.left = pct + '%';
    const display = (divVal ? (val / divVal).toFixed(1) : val) + suffix;
    if (tip) tip.textContent = display;
    const svEl = bar.parentElement.querySelector('.sv');
    if (svEl) svEl.textContent = display;
};

function previewTypography() {
    const payload = {
        font_family: document.getElementById('fontFamily').value,
        font_size: parseInt((document.getElementById('fontSize') || {}).value || settings.font_size || 18),
        line_spacing: parseFloat((document.getElementById('lineSpacing').value / 10).toFixed(1)),
        paragraph_spacing: parseInt(document.getElementById('paragraphSpacing').value),
        text_indent: parseInt(document.getElementById('textIndent').value),
        font_color: getColorPicker('capFontColor'),
        background_opacity: parseInt(document.getElementById('readerBgOpacity').value) / 100,
        reader_bg_image: readerBgPath || '',
    };
    try { api().preview_typography(payload); } catch (e) {}
    autoSaveSettings();
}

async function minimizeWindow() { try { await api().minimize_window(); } catch (e) { showToast('最小化失败'); } }
async function toggleMaximize() {
    try {
        const m = await api().toggle_maximize();
        document.getElementById('maxBtn').textContent = m ? '❐' : '□';
    } catch (e) { showToast('最大化切换失败'); }
}
async function closeWindow() { try { await api().close_window(); } catch (e) { showToast('关闭窗口失败'); } }

function setupDragDrop() {
    const appRoot = document.getElementById('appRoot');
    const overlay = document.getElementById('dragOverlay');
    let dragCounter = 0;

    appRoot.addEventListener('dragenter', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dragCounter++;
        overlay.classList.add('active');
    });

    appRoot.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
    });

    appRoot.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dragCounter--;
        if (dragCounter <= 0) {
            dragCounter = 0;
            overlay.classList.remove('active');
        }
    });

    appRoot.addEventListener('drop', async function(e) {
        e.preventDefault();
        e.stopPropagation();
        dragCounter = 0;
        overlay.classList.remove('active');

        const files = e.dataTransfer.files;
        if (!files || files.length === 0) return;

        const paths = [];
        for (let i = 0; i < files.length; i++) {
            if (files[i].path) paths.push(files[i].path);
        }
        if (paths.length > 0) {
            await importBooks(paths);
            return;
        }

        var added = 0, errors = [], skipped = [];
        var total = files.length;
        for (var i = 0; i < total; i++) {
            var file = files[i];
            setStatus('导入中 (' + (i + 1) + '/' + total + ')：' + file.name);
            try {
                var base64 = await _readFileAsBase64(file);
                var r = await api().import_book_from_content(file.name, base64);
                if (r && r.added > 0) added += r.added;
                if (r && r.skipped) skipped = skipped.concat(r.skipped);
                if (r && r.errors) errors = errors.concat(r.errors);
            } catch (err) {
                errors.push(file.name + ': ' + (err.message || err));
            }
        }
        if (added > 0) {
            showToast('成功添加 ' + added + ' 本书籍' + (skipped.length > 0 ? '（跳过 ' + skipped.length + ' 本）' : ''));
            _cachedStats = null; _shelfDirty = true; _bookmarkDirty = true;
            await loadDashboard();
        } else if (errors.length > 0) {
            showToast('导入失败: ' + errors[0]);
        } else {
            showToast('未添加任何书籍');
        }
        setStatus('就绪');
    });
}

function _readFileAsBase64(file) {
    return new Promise(function(resolve, reject) {
        var reader = new FileReader();
        reader.onload = function() {
            var arr = new Uint8Array(reader.result);
            var CHUNK = 8192;
            var parts = [];
            for (var i = 0; i < arr.length; i += CHUNK) {
                parts.push(String.fromCharCode.apply(null, arr.subarray(i, i + CHUNK)));
            }
            resolve(btoa(parts.join('')));
        };
        reader.onerror = function() { reject(new Error('读取文件失败')); };
        reader.readAsArrayBuffer(file);
    });
}

async function loadAppInfo() {
    try {
        const info = await api().get_app_info();
        const el = document.getElementById('copyrightText');
        if (el) {
            el.textContent = info.copyright;
            el.style.cursor = 'pointer';
            el.title = '双击访问主页';
            el.addEventListener('dblclick', function() {
                api().open_url_in_browser(info.author_homepage_url || 'https://space.bilibili.com/210900168');
            });
        }
        document.getElementById('versionText').textContent = info.version_text;

        const authorCard = document.getElementById('guideAuthorCard');
        if (authorCard && info.author_info) {
            authorCard.innerHTML = info.author_info.map(function(item) {
                if (item.url) {
                    return '<div>▪ ' + escapeHtml(item.label) + '：<span onclick="api().open_url_in_browser(\'' + item.url.replace(/'/g, "\\'") + '\')" style="color:var(--accent);cursor:pointer;text-decoration:underline;">' + escapeHtml(item.value) + '</span></div>';
                }
                return '<div>▪ ' + escapeHtml(item.label) + '：' + escapeHtml(item.value) + '</div>';
            }).join('');
        }
    } catch (e) { showToast('加载应用信息失败'); }
}

document.addEventListener('click', e => { if (!e.target.closest('.context-menu')) hideContextMenu(); });
document.addEventListener('click', function(e) {
    var menu = document.getElementById('capMoreMenu');
    if (menu && !e.target.closest('.cap-more-btn')) menu.classList.remove('show');
});

function toggleCapMore(e) {
    e.stopPropagation();
    var menu = document.getElementById('capMoreMenu');
    if (menu) menu.classList.toggle('show');
}

(function setupDrag() {
    const titleBar = document.getElementById('titleBar');
    let dragging = false, lastX = 0, lastY = 0;
    let _dragRAF = null, dx = 0, dy = 0;
    titleBar.addEventListener('mousedown', e => {
        if (e.target.closest('.win-btn') || e.target.closest('input')) return;
        dragging = true; lastX = e.screenX; lastY = e.screenY;
        dx = 0; dy = 0;
    });
    document.addEventListener('mousemove', e => {
        if (!dragging) return;
        dx += e.screenX - lastX; dy += e.screenY - lastY;
        lastX = e.screenX; lastY = e.screenY;
        if (!_dragRAF) {
            _dragRAF = requestAnimationFrame(() => {
                if (dx || dy) { try { api().move_main_window(dx, dy); } catch (e2) {} }
                dx = 0; dy = 0; _dragRAF = null;
            });
        }
    });
    document.addEventListener('mouseup', () => { dragging = false; });
})();

document.addEventListener('visibilitychange', () => {
    if (!document.hidden) _shelfDirty = true;
});

function applyStaggerDelays(selector) {
    document.querySelectorAll(selector || '.book-row').forEach(function(row, i) {
        row.style.animationDelay = (i * 30) + 'ms';
    });
}

var _noteListData = [];
var _noteSelectedIds = new Set();
var _noteFilterGroup = '';
var _noteSearchQuery = '';

async function loadNotes() {
    try {
        if (_noteSearchQuery) {
            _noteListData = await api().search_notes(_noteSearchQuery);
        } else {
            _noteListData = await api().get_notes();
        }
        await loadNoteGroups();
        renderNotes();
    } catch (e) { showToast('加载便签失败'); }
}

async function loadNoteGroups() {
    try {
        var groups = await api().get_note_groups();
        var sel = document.getElementById('noteGroupFilter');
        if (!sel) return;
        var current = sel.value;
        var html = '<option value="">全部分组</option>';
        for (var i = 0; i < groups.length; i++) {
            html += '<option value="' + escapeHtml(groups[i]) + '">' + escapeHtml(groups[i]) + '</option>';
        }
        sel.innerHTML = html;
        sel.value = current;
    } catch (e) {}
}

function filterNotesByGroup() {
    var sel = document.getElementById('noteGroupFilter');
    _noteFilterGroup = sel ? sel.value : '';
    renderNotes();
}

function searchNotes() {
    var input = document.getElementById('noteSearchInput');
    _noteSearchQuery = input ? input.value : '';
    loadNotes();
}

function searchNotesKeydown(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        searchNotes();
    } else if (e.key === 'Escape') {
        var input = document.getElementById('noteSearchInput');
        if (input) { input.value = ''; }
        _noteSearchQuery = '';
        loadNotes();
    }
}

async function createNote() {
    try {
        var note = await api().create_note('');
        if (note && note.id) {
            _notesDirty = true;
            await api().open_note_editor(note.id);
            await loadNotes();
        }
    } catch (e) { showToast('创建便签失败'); }
}

async function addSampleNote() {
    try {
        await api().create_sample_note();
        _notesDirty = true;
        await loadNotes();
        showToast('示例便签已添加');
    } catch (e) { showToast('添加失败'); }
}

function toggleNoteSelectionByDrag(noteId, enabled) {
    if (enabled) {
        _noteSelectedIds.add(noteId);
    } else {
        _noteSelectedIds.delete(noteId);
    }
}

function initNoteDragSelect() {
    var list = document.getElementById('noteList');
    if (!list || list._dragSelectBound) {
        return;
    }
    list._dragSelectBound = true;
    var dragging = false;
    var dragMode = true;
    var lastTouchedId = null;
    list.addEventListener('pointerdown', function(e) {
        var row = e.target.closest('.note-row');
        if (!row || e.button !== 0) {
            return;
        }
        dragging = true;
        dragMode = !_noteSelectedIds.has(row.dataset.noteId);
        lastTouchedId = row.dataset.noteId;
        _noteSelectedIds[dragMode ? 'add' : 'delete'](row.dataset.noteId);
        row.setPointerCapture && row.setPointerCapture(e.pointerId);
        renderNotes();
        e.preventDefault();
    });
    list.addEventListener('pointermove', function(e) {
        if (!dragging) {
            return;
        }
        var row = e.target.closest('.note-row');
        if (!row || row.dataset.noteId === lastTouchedId) {
            return;
        }
        lastTouchedId = row.dataset.noteId;
        toggleNoteSelectionByDrag(row.dataset.noteId, dragMode);
        renderNotes();
    });
    var stopDrag = function() {
        dragging = false;
        lastTouchedId = null;
    };
    list.addEventListener('pointerup', stopDrag);
    list.addEventListener('pointercancel', stopDrag);
    list.addEventListener('pointerleave', stopDrag);
}

function selectAllNotes() {
    return;
}

async function deleteSelectedNotes() {
    return;
}

async function deleteAllNotes() {
    return;
}

async function deleteNote(noteId) {
    showConfirm('删除便签', '确定要删除这个便签吗？\n此操作不可撤销。', async function() {
        try {
            var ok = await api().delete_note(noteId);
            if (ok) {
                _noteSelectedIds.delete(noteId);
                showToast('便签已删除');
                await loadNotes();
            } else {
                showToast('删除失败');
            }
        } catch (e) { showToast('删除失败'); }
    });
}

async function openNoteEditor(noteId) {
    try {
        await api().open_note_editor(noteId);
    } catch (e) { showToast('打开编辑器失败'); }
}

async function openNoteViewer(noteId) {
    try {
        await api().open_note_viewer(noteId);
    } catch (e) { showToast('打开展示窗口失败'); }
}

async function duplicateNote(noteId) {
    try {
        var result = await api().duplicate_note(noteId);
        if (result && result.success !== false) {
            await loadNotes();
            showToast('已复制便签');
        } else {
            showToast(result && result.error ? result.error : '复制失败');
        }
    } catch (e) { showToast('复制便签失败'); }
}

async function exportNoteMd(noteId) {
    try {
        var result = await api().export_note_md(noteId);
        if (result && result.success) {
            showToast('已导出: ' + (result.path || ''));
        } else if (result && result.error && result.error !== '用户取消') {
            showToast(result.error);
        }
    } catch (e) { showToast('导出失败'); }
}

async function updateNoteGroup(noteId, group) {
    try {
        await api().update_note(noteId, null, null, null, group);
        await loadNotes();
    } catch (e) { showToast('更新分组失败'); }
}

function startEditNoteGroup(noteId, currentGroup) {
    var groupEl = document.getElementById('noteGroup_' + noteId);
    if (!groupEl) return;
    var renamed = false;
    var input = document.createElement('input');
    input.type = 'text';
    input.value = currentGroup || '';
    input.placeholder = '分组';
    input.style.cssText = 'font-size:10px;color:var(--fg);background:var(--input-bg);border:1px solid var(--accent);border-radius:4px;padding:1px 5px;outline:none;width:60px;box-sizing:border-box;';
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (!renamed) { renamed = true; updateNoteGroup(noteId, input.value); }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            renamed = true;
            renderNotes();
        }
    });
    input.addEventListener('blur', function() {
        if (!renamed) { renamed = true; updateNoteGroup(noteId, input.value); }
    });
    groupEl.innerHTML = '';
    groupEl.appendChild(input);
    input.focus();
    input.select();
}

function getFilteredNotes() {
    var list = _noteListData;
    if (_noteFilterGroup) {
        list = list.filter(function(n) { return (n.group || '') === _noteFilterGroup; });
    }
    var sortSel = document.getElementById('noteSortBy');
    var sortBy = sortSel ? sortSel.value : 'updated';
    if (sortBy === 'title') {
        list = list.slice().sort(function(a, b) {
            var ta = (a.title || '空白便签').toLowerCase();
            var tb = (b.title || '空白便签').toLowerCase();
            return ta < tb ? -1 : (ta > tb ? 1 : 0);
        });
    } else if (sortBy === 'created') {
        list = list.slice().sort(function(a, b) {
            var ca = a.created_at || '';
            var cb = b.created_at || '';
            return ca < cb ? 1 : (ca > cb ? -1 : 0);
        });
    }
    // 默认 updated 已由后端按 updated_at 倒序返回
    return list;
}

function renderNotes() {
    var el = document.getElementById('noteList');
    var countEl = document.getElementById('noteCount');
    if (!el) return;

    var filtered = getFilteredNotes();
    var suffix = '';
    if (_noteSearchQuery) suffix += ' 搜索:' + _noteSearchQuery;
    if (_noteFilterGroup) suffix += ' [' + _noteFilterGroup + ']';
    if (countEl) countEl.textContent = filtered.length + ' 条' + suffix;

    if (filtered.length === 0) {
        el.innerHTML = '<div style="text-align:center;padding:60px 20px;color:var(--fg3);"><div style="font-size:40px;margin-bottom:12px;opacity:0.5;">' + ICONS.note + '</div><div style="font-size:13px;">' + (_noteSearchQuery ? '未找到匹配的便签' : '暂无便签') + '</div><div style="font-size:11px;margin-top:6px;opacity:0.6;">' + (_noteSearchQuery ? '换个关键词试试' : '点击「新建」或「示例」开始') + '</div></div>';
        return;
    }

    var parts = [];
    for (var i = 0; i < filtered.length; i++) {
        var note = filtered[i];
        var group = note.group || '';
        var selected = _noteSelectedIds.has(note.id);
        var title = escapeHtml(note.title || '空白便签');
        var preview = escapeHtml((note.content || '').substring(0, 200).replace(/^#+\s*/gm, '').replace(/[*_`~\[\]()]/g, '').substring(0, 80));
        var time = note.updated_at ? note.updated_at.replace('T', ' ').substring(0, 16) : '';

        parts.push('<div class="note-row' + (selected ? ' selected' : '') + '" data-note-id="' + note.id + '">');
        parts.push('<input type="checkbox" ' + (selected ? 'checked' : '') + ' onclick="event.stopPropagation();toggleNoteSelect(\'' + note.id + '\')" style="accent-color:var(--accent);flex-shrink:0;cursor:pointer;">');
        parts.push('<div style="flex:1;min-width:0;overflow:hidden;" onclick="openNoteEditor(\'' + note.id + '\')">');
        parts.push('<div class="note-row-title" id="noteTitle_' + note.id + '" ondblclick="event.stopPropagation();startEditNoteTitle(\'' + note.id + '\',\'' + escapeAttr(note.title || '空白便签') + '\')" title="双击编辑标题">' + title + '</div>');
        parts.push('<div class="note-row-preview">' + preview + '</div>');
        parts.push('</div>');
        parts.push('<div class="note-row-group" id="noteGroup_' + note.id + '" ondblclick="event.stopPropagation();startEditNoteGroup(\'' + note.id + '\',\'' + escapeAttr(group) + '\')" title="双击编辑分组">');
        if (group) {
            parts.push('<span class="note-row-group-tag">' + escapeHtml(group) + '</span>');
        } else {
            parts.push('<span style="font-size:10px;color:var(--fg3);opacity:0.3;">分组</span>');
        }
        parts.push('</div>');
        parts.push('<span class="note-row-time">' + escapeHtml(time) + '</span>');
        parts.push('<div style="display:flex;gap:4px;flex-shrink:0;">');
        parts.push('<button class="note-action-btn" onclick="event.stopPropagation();openNoteViewer(\'' + note.id + '\')" title="桌面展示">📌</button>');
        parts.push('<button class="note-action-btn" onclick="event.stopPropagation();duplicateNote(\'' + note.id + '\')" title="复制便签">📋</button>');
        parts.push('<button class="note-action-btn" onclick="event.stopPropagation();exportNoteMd(\'' + note.id + '\')" title="导出为 .md">💾</button>');
        parts.push('<button class="note-action-btn-danger" onclick="event.stopPropagation();deleteNote(\'' + note.id + '\')" title="删除">🗑️</button>');
        parts.push('</div>');
        parts.push('</div>');
    }
    el.innerHTML = parts.join('');
}

function toggleNoteSelect(noteId) {
    var row = document.querySelector('[data-note-id="' + noteId + '"]');
    if (!row) {
        if (_noteSelectedIds.has(noteId)) {
            _noteSelectedIds.delete(noteId);
        } else {
            _noteSelectedIds.add(noteId);
        }
        renderNotes();
        return;
    }
    var cb = row.querySelector('input[type="checkbox"]');
    if (_noteSelectedIds.has(noteId)) {
        _noteSelectedIds.delete(noteId);
        row.classList.remove('selected');
        if (cb) cb.checked = false;
    } else {
        _noteSelectedIds.add(noteId);
        row.classList.add('selected');
        if (cb) cb.checked = true;
    }
}

async function renameNote(noteId, newTitle) {
    try {
        var result = await api().update_note(noteId, null, null, newTitle);
        if (result && result.success) {
            await loadNotes();
        }
    } catch (e) { showToast('重命名失败'); }
}

function startEditNoteTitle(noteId, currentTitle) {
    var titleEl = document.getElementById('noteTitle_' + noteId);
    if (!titleEl) return;
    var renamed = false;
    var input = document.createElement('input');
    input.type = 'text';
    input.value = currentTitle;
    input.style.cssText = 'font-size:13px;font-weight:500;color:var(--fg);background:var(--input-bg);border:1px solid var(--accent);border-radius:4px;padding:1px 5px;outline:none;width:100%;box-sizing:border-box;';
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (!renamed) { renamed = true; renameNote(noteId, input.value); }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            renamed = true;
            renderNotes();
        }
    });
    input.addEventListener('blur', function() {
        if (!renamed) { renamed = true; renameNote(noteId, input.value); }
    });
    titleEl.innerHTML = '';
    titleEl.appendChild(input);
    input.focus();
    input.select();
}

// 公共页面模板（设置页/日志页/说明页），由 renderPartials() 在 DOMContentLoaded 时注入
// pywebview file:// 不支持父路径回溯，故 HTML 内联于此而非 fetch
const _PARTIAL_SETTINGS = '<div class="inline-settings"><div class="is-card"><div class="is-card-title">§palette 主题配色</div><div class="theme-grid" id="themeGrid"></div><div class="is-divider"></div><div class="is-label">自定义颜色</div><div class="cap-row" id="colorPalette"><div class="cap-col"><input type="color" class="cap-dot" id="capBg" data-key="bg" value="#f5eed8"><span class="cap-label">背景</span><span class="cap-hex" id="capBgHex">#f5eed8</span></div><div class="cap-col"><input type="color" class="cap-dot" id="capFg" data-key="fg" value="#4a4030"><span class="cap-label">文字</span><span class="cap-hex" id="capFgHex">#4a4030</span></div><div class="cap-col"><input type="color" class="cap-dot" id="capAccent" data-key="accent" value="#b89858"><span class="cap-label">强调</span><span class="cap-hex" id="capAccentHex">#b89858</span></div><div class="cap-col"><input type="color" class="cap-dot" id="capTip" data-key="tip" value="#a09070"><span class="cap-label">提示</span><span class="cap-hex" id="capTipHex">#a09070</span></div><div class="cap-col"><input type="color" class="cap-dot" id="capFontColor" data-key="font_color" value="#574c3c"><span class="cap-label">阅读色</span><span class="cap-hex" id="capFontColorHex">#574c3c</span></div><div class="cap-btns"><button class="btn btn-accent" onclick="randomThemeColors()">🎲 随机</button><button class="btn btn-ghost" onclick="addCustomTheme()">＋ 增加</button><button class="btn btn-ghost" onclick="resetCurrentTheme()">↩ 恢复默认</button><div class="cap-more-btn"><button class="btn btn-ghost" onclick="toggleCapMore(event)">⋯</button><div class="cap-more-menu" id="capMoreMenu"><div class="cap-more-item" onclick="importAllThemes()">📥 导入</div><div class="cap-more-item" onclick="exportAllThemes()">📤 导出</div><div class="cap-more-item" onclick="resetApp()" style="color:var(--danger);">🔄 重置应用</div></div></div></div></div></div><div class="is-card"><div class="is-card-title">§book 阅读排版 <span style="margin-left:auto;cursor:pointer;font-size:9px;color:var(--fg3);font-weight:400;" onclick="resetTypography()">↩ 恢复默认</span></div><div style="display:flex;flex-direction:column;gap:8px;"><div style="display:flex;align-items:center;gap:8px;"><span style="font-size:10px;color:var(--fg2);width:32px;flex-shrink:0;">字体</span><div id="fontFamilyWrap" class="font-dd-wrap" style="flex:1;position:relative;"><div id="fontFamilyTrigger" class="font-dd-trigger" onclick="toggleFontDropdown()"><span id="fontFamilyLabel">微软雅黑</span><span class="font-dd-arrow">▾</span></div><div id="fontFamilyPanel" class="font-dd-panel"></div></div><input type="hidden" id="fontFamily" value="Microsoft YaHei"><button class="btn btn-ghost" onclick="addCustomFont()" style="padding:3px 8px;font-size:10px;flex-shrink:0;" title="添加字体文件">＋</button><button class="btn btn-ghost" onclick="openFontsFolder()" style="padding:3px 6px;font-size:10px;color:var(--fg3);flex-shrink:0;" title="打开字体文件夹">📂</button></div><div style="display:flex;align-items:center;gap:8px;"><span style="font-size:10px;color:var(--fg2);width:32px;flex-shrink:0;">行距</span><input type="range" id="lineSpacing" class="is-range" min="8" max="30" step="1" value="18" style="display:none;"><div class="click-bar" data-input="lineSpacing" data-min="8" data-max="30" data-step="1" data-display-div="10"><div class="click-bar-fill"></div><div class="click-bar-dot"></div><div class="click-bar-tooltip"></div></div><span class="sv" style="font-size:10px;width:28px;text-align:right;" id="lineSpacingValue">1.8</span></div><div style="display:flex;align-items:center;gap:8px;"><span style="font-size:10px;color:var(--fg2);width:32px;flex-shrink:0;">段距</span><input type="range" id="paragraphSpacing" class="is-range" min="-50" max="50" value="20" style="display:none;"><div class="click-bar" data-input="paragraphSpacing" data-min="-50" data-max="50" data-step="1"><div class="click-bar-fill"></div><div class="click-bar-dot"></div><div class="click-bar-tooltip"></div></div><span class="sv" style="font-size:10px;width:28px;text-align:right;" id="paragraphSpacingValue">20</span></div><div style="display:flex;align-items:center;gap:8px;"><span style="font-size:10px;color:var(--fg2);width:32px;flex-shrink:0;">缩进</span><input type="range" id="textIndent" class="is-range" min="0" max="10" step="1" value="2" style="display:none;"><div class="click-bar" data-input="textIndent" data-min="0" data-max="10" data-step="1"><div class="click-bar-fill"></div><div class="click-bar-dot"></div><div class="click-bar-tooltip"></div></div><span class="sv" style="font-size:10px;width:28px;text-align:right;" id="textIndentValue">2</span></div></div></div><div class="is-card"><div class="is-card-title">§image 背景</div><div style="display:flex;flex-direction:column;gap:6px;"><div style="display:flex;align-items:center;gap:8px;"><span style="font-size:10px;color:var(--fg3);width:52px;flex-shrink:0;">主页背景</span><span style="font-size:10px;color:var(--fg2);width:18px;flex-shrink:0;" id="homeBgStatus">-</span><input type="range" id="homeBgOpacity" class="is-range" min="1" max="50" value="10" style="display:none;"><div class="click-bar" data-input="homeBgOpacity" data-min="1" data-max="50" data-step="1" data-suffix="%" data-callback="_onHomeBgChange"><div class="click-bar-fill"></div><div class="click-bar-dot"></div><div class="click-bar-tooltip"></div></div><span class="sv" style="font-size:10px;width:28px;text-align:right;" id="homeBgOpacityValue">10%</span><button class="btn btn-ghost" onclick="selectHomeBg()" style="padding:3px 8px;font-size:10px;flex-shrink:0;">选择</button><button class="btn btn-ghost" onclick="clearHomeBg()" style="padding:3px 6px;font-size:10px;color:var(--fg3);flex-shrink:0;">✕</button></div><div style="display:flex;align-items:center;gap:8px;"><span style="font-size:10px;color:var(--fg3);width:52px;flex-shrink:0;">阅读背景</span><span style="font-size:10px;color:var(--fg2);width:18px;flex-shrink:0;" id="readerBgStatus">-</span><input type="range" id="readerBgOpacity" class="is-range" min="1" max="50" value="8" style="display:none;"><div class="click-bar" data-input="readerBgOpacity" data-min="1" data-max="50" data-step="1" data-suffix="%"><div class="click-bar-fill"></div><div class="click-bar-dot"></div><div class="click-bar-tooltip"></div></div><span class="sv" style="font-size:10px;width:28px;text-align:right;" id="readerBgOpacityValue">8%</span><button class="btn btn-ghost" onclick="selectReaderBg()" style="padding:3px 8px;font-size:10px;flex-shrink:0;">选择</button><button class="btn btn-ghost" onclick="clearReaderBg()" style="padding:3px 6px;font-size:10px;color:var(--fg3);flex-shrink:0;">✕</button></div><div style="display:flex;align-items:center;gap:8px;"><span style="font-size:10px;color:var(--fg3);width:52px;flex-shrink:0;">便签背景</span><span style="font-size:10px;color:var(--fg2);width:18px;flex-shrink:0;" id="notesBgStatus">-</span><input type="range" id="notesBgOpacity" class="is-range" min="1" max="50" value="8" style="display:none;"><div class="click-bar" data-input="notesBgOpacity" data-min="1" data-max="50" data-step="1" data-suffix="%"><div class="click-bar-fill"></div><div class="click-bar-dot"></div><div class="click-bar-tooltip"></div></div><span class="sv" style="font-size:10px;width:28px;text-align:right;" id="notesBgOpacityValue">8%</span><button class="btn btn-ghost" onclick="selectNotesBg()" style="padding:3px 8px;font-size:10px;flex-shrink:0;">选择</button><button class="btn btn-ghost" onclick="clearNotesBg()" style="padding:3px 6px;font-size:10px;color:var(--fg3);flex-shrink:0;">✕</button></div></div></div></div>';

const _PARTIAL_LOG = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-shrink:0;"><span style="font-size:15px;font-weight:700;">§log 应用日志</span><span id="logCount" style="font-size:11px;color:var(--fg3);"></span><span id="logSelectionCount" style="font-size:11px;color:var(--accent);display:none;"></span><div style="flex:1;"></div><input id="logSearch" type="text" placeholder="搜索日志..." style="width:200px;padding:4px 10px;border-radius:6px;border:1px solid var(--card-border);background:var(--input-bg);color:var(--fg);font-size:12px;outline:none;" oninput="filterLogs()"><select id="logLevelFilter" style="padding:4px 8px;border-radius:6px;border:1px solid var(--card-border);background:var(--input-bg);color:var(--fg);font-size:12px;outline:none;" onchange="filterLogs()"><option value="ALL">全部级别</option><option value="DEBUG">DEBUG</option><option value="INFO">INFO</option><option value="WARNING">WARNING</option><option value="ERROR">ERROR</option></select><button class="btn btn-ghost" style="padding:4px 10px;font-size:11px;" onclick="loadLogs()">§refresh 刷新</button><button class="btn btn-ghost" style="padding:4px 10px;font-size:11px;" onclick="selectAllLogs()">§check 全选</button><button class="btn btn-ghost" style="padding:4px 10px;font-size:11px;" onclick="copySelectedLogs()">§copy 复制选中</button><button class="btn btn-ghost" style="padding:4px 10px;font-size:11px;color:var(--danger);" onclick="clearLogs()">§trash 清空</button><label style="display:flex;align-items:center;gap:4px;font-size:11px;color:var(--fg3);cursor:pointer;"><input type="checkbox" id="logAutoRefresh" checked onchange="toggleLogAutoRefresh()" style="accent-color:var(--accent);"> 自动刷新</label></div><div style="display:flex;gap:8px;margin-bottom:8px;font-size:11px;color:var(--fg3);"><span>§lightbulb 提示：点击选中单行，Ctrl+点击多选，Shift+点击范围选择，选中后可右键复制</span></div><div id="logContainer" style="flex:1;overflow-y:auto;background:rgba(0,0,0,0.3);border-radius:8px;padding:10px;font-family:\'Cascadia Code\',\'Fira Code\',\'Consolas\',monospace;font-size:12px;line-height:1.8;"></div>';

const _PARTIAL_GUIDE = '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;"><div class="is-card"><div class="is-card-title">§book 阅读操作</div><div style="font-size:13px;color:var(--fg);line-height:2.2;"><div>▪ 左侧点击 / ← / PageUp：上一页</div><div>▪ 右侧点击 / → / PageDown / 空格：下一页</div><div>▪ ↑ / ↓ 方向键：逐行滚动</div><div>▪ 章节首尾自动切换上下章</div><div>▪ Ctrl + ↓：加速向下阅读（+0.25）</div><div>▪ Ctrl + ↑：减速 / 反向向上（-0.25）</div><div>▪ Ctrl + 滚轮：同上调节速度</div><div>▪ Ctrl + F：全文搜索当前书籍</div><div>▪ Ctrl + Alt + 滚轮：调节阅读字体大小</div><div>▪ Esc：停止自动 / 关闭面板</div></div></div><div class="is-card"><div class="is-card-title">§bookmark 书签与目录</div><div style="font-size:13px;color:var(--fg);line-height:2.2;"><div>▪ 点击底部章节名打开目录，支持搜索和章节预览</div><div>▪ 顶部工具栏 🔖 按钮打开书签面板</div><div>▪ 书签支持添加、编辑描述、点击跳转、单条删除</div><div>▪ 书签支持按添加时间/章节顺序排序</div><div>▪ 书签支持勾选全选后批量删除</div><div>▪ 右键菜单：复制、目录、书签、检索、打开书架、自动阅读</div></div></div><div class="is-card"><div class="is-card-title">§palette 主题与设置</div><div style="font-size:13px;color:var(--fg);line-height:2.2;"><div>▪ 🌙/☀ 图标切换深浅主题</div><div>▪ 20种内置配色 + 自定义保存</div><div>▪ 5种主页布局可切换</div><div>▪ 自定义字体、字号、行距</div><div>▪ 设置页 ＋ 按钮添加自定义字体</div><div>▪ 支持导入/导出/随机配色</div><div>▪ 可设置主页/阅读背景图片</div></div></div><div class="is-card"><div class="is-card-title">§folder 支持格式</div><div style="font-size:13px;color:var(--fg);line-height:2.2;"><div>▪ <b>TXT</b> — 纯文本（自动识别编码）</div><div>▪ <b>Markdown</b> — .md 文件（支持图片）</div><div>▪ <b>EPUB</b> — 电子书（支持内链封面）</div><div>▪ <b>MOBI</b> — Kindle 格式（自动解析）</div></div></div><div class="is-card"><div class="is-card-title">§lightbulb 小技巧</div><div style="font-size:13px;color:var(--fg);line-height:2.2;"><div>▪ 拖放文件到窗口快速导入书籍</div><div>▪ 标题栏拖拽移动窗口</div><div>▪ 右下角拖拽调整窗口大小</div><div>▪ 阅读进度自动保存恢复</div><div>▪ 代码块语法高亮与一键复制</div><div>▪ 右键菜单：重命名、查看详情</div></div></div><div class="is-card"><div class="is-card-title">§user 作者</div><div id="guideAuthorCard" style="font-size:13px;color:var(--fg);line-height:2.2;"></div></div></div>';

const _PARTIAL_NOTES = '<div style="padding:16px 20px;height:100%;display:flex;flex-direction:column;box-sizing:border-box;"><div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;flex-shrink:0;flex-wrap:wrap;"><span style="font-size:16px;font-weight:700;color:var(--fg);letter-spacing:0.5px;">§note 便签</span><span id="noteCount" style="font-size:10px;color:var(--fg3);background:var(--card);padding:2px 8px;border-radius:10px;"></span><div style="flex:1;"></div><input id="noteSearchInput" type="text" placeholder="搜索便签..." onkeydown="searchNotesKeydown(event)" style="width:160px;padding:4px 10px;border-radius:6px;border:1px solid var(--card-border);background:var(--input-bg);color:var(--fg);font-size:11px;outline:none;" onfocus="this.style.borderColor=\'var(--accent)\'" onblur="this.style.borderColor=\'var(--card-border)\'"><button class="btn btn-ghost" onclick="searchNotes()" style="padding:4px 8px;font-size:11px;display:inline-flex;align-items:center;gap:4px;"><span style="font-size:12px;line-height:1;">🔍</span><span>搜索</span></button><select id="noteGroupFilter" onchange="filterNotesByGroup()" style="padding:4px 8px;border-radius:6px;border:1px solid var(--card-border);background:var(--input-bg);color:var(--fg);font-size:11px;outline:none;"><option value="">全部分组</option></select><select id="noteSortBy" onchange="renderNotes()" style="padding:4px 8px;border-radius:6px;border:1px solid var(--card-border);background:var(--input-bg);color:var(--fg);font-size:11px;outline:none;"><option value="updated">按更新时间</option><option value="created">按创建时间</option><option value="title">按标题</option></select><button class="btn btn-ghost" onclick="addSampleNote()" style="padding:4px 10px;font-size:11px;display:inline-flex;align-items:center;gap:4px;"><span style="font-size:12px;line-height:1;">📄</span><span>示例</span></button><button class="btn btn-accent" onclick="createNote()" style="padding:5px 14px;font-size:11px;border-radius:6px;display:inline-flex;align-items:center;gap:4px;"><span style="font-size:12px;line-height:1;">➕</span><span>新建</span></button></div><div id="noteList" style="flex:1;overflow-y:auto;"></div></div>';

function _resolveIcons(html) {
    return html.replace(/§(\w+)/g, function(_, key) { return ICONS[key] || ''; });
}

function renderPartials() {
    const map = { pageSettings: _PARTIAL_SETTINGS, pageLog: _PARTIAL_LOG, pageGuide: _PARTIAL_GUIDE, pageNotes: _PARTIAL_NOTES };
    for (const [id, html] of Object.entries(map)) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = _resolveIcons(html);
    }
    // 注入后初始化 click-bar 等交互组件
    if (typeof setupFontSizeSlider === 'function') setupFontSizeSlider();
    if (typeof setupLineSpacingSlider === 'function') setupLineSpacingSlider();
    if (typeof loadFontList === 'function') loadFontList();
    if (typeof initNoteDragSelect === 'function') initNoteDragSelect();
}
