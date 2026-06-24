function api() {
    return window.pywebview ? window.pywebview.api : null;
}
window.api = api;

function isDarkColor(hex) {
    if (!hex || hex.charAt(0) !== '#') return true;
    const h = hex.replace('#', '');
    return (parseInt(h.substring(0,2),16)*299+parseInt(h.substring(2,4),16)*587+parseInt(h.substring(4,6),16)*114)/1000 < 160;
}
function lightenColor(hex, f) {
    const h = hex.replace('#', '');
    const r = Math.min(255, parseInt(h.substring(0,2),16)+Math.round((255-parseInt(h.substring(0,2),16))*f));
    const g = Math.min(255, parseInt(h.substring(2,4),16)+Math.round((255-parseInt(h.substring(2,4),16))*f));
    const b = Math.min(255, parseInt(h.substring(4,6),16)+Math.round((255-parseInt(h.substring(4,6),16))*f));
    return '#'+[r,g,b].map(v=>v.toString(16).padStart(2,'0')).join('');
}
function darkenColor(hex, f) {
    const h = hex.replace('#', '');
    const r = Math.max(0, Math.round(parseInt(h.substring(0,2),16)*(1-f)));
    const g = Math.max(0, Math.round(parseInt(h.substring(2,4),16)*(1-f)));
    const b = Math.max(0, Math.round(parseInt(h.substring(4,6),16)*(1-f)));
    return '#'+[r,g,b].map(v=>v.toString(16).padStart(2,'0')).join('');
}
const _toastQueue = [];
const _TOAST_MAX = 3;
const _TOAST_DURATION = 2500;

function showToast(msg) {
    const container = document.getElementById('toast');
    if (!container) return;

    const item = document.createElement('div');
    item.className = 'toast-item';
    item.textContent = msg;
    container.appendChild(item);
    _toastQueue.push(item);

    requestAnimationFrame(() => { item.classList.add('show'); });

    setTimeout(() => {
        item.classList.remove('show');
        setTimeout(() => {
            if (item.parentNode) item.parentNode.removeChild(item);
            const idx = _toastQueue.indexOf(item);
            if (idx >= 0) _toastQueue.splice(idx, 1);
        }, 300);
    }, _TOAST_DURATION);

    while (_toastQueue.length > _TOAST_MAX) {
        const old = _toastQueue.shift();
        old.classList.remove('show');
        setTimeout(() => { if (old.parentNode) old.parentNode.removeChild(old); }, 300);
    }
}
function mixHex(hex1, hex2, ratio) {
    const h1 = hex1.replace('#', ''), h2 = hex2.replace('#', '');
    const r = Math.round(parseInt(h1.substring(0,2),16)*(1-ratio)+parseInt(h2.substring(0,2),16)*ratio);
    const g = Math.round(parseInt(h1.substring(2,4),16)*(1-ratio)+parseInt(h2.substring(2,4),16)*ratio);
    const b = Math.round(parseInt(h1.substring(4,6),16)*(1-ratio)+parseInt(h2.substring(4,6),16)*ratio);
    return '#'+[r,g,b].map(v=>Math.max(0,Math.min(255,v)).toString(16).padStart(2,'0')).join('');
}
function escapeHtml(str) {
    if (str == null) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}
function escapeAttr(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
window.isDarkColor = isDarkColor;
window.lightenColor = lightenColor;
window.darkenColor = darkenColor;
window.showToast = showToast;
window.mixHex = mixHex;
window.escapeHtml = escapeHtml;
window.escapeAttr = escapeAttr;

function hexToHsl(hex) {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0,2),16)/255;
    const g = parseInt(h.substring(2,4),16)/255;
    const b = parseInt(h.substring(4,6),16)/255;
    const max = Math.max(r,g,b), min = Math.min(r,g,b);
    let hue=0, sat=0, lit=(max+min)/2;
    if (max!==min) {
        const d = max-min;
        sat = lit>0.5 ? d/(2-max-min) : d/(max+min);
        if (max===r) hue=((g-b)/d+(g<b?6:0))/6;
        else if (max===g) hue=((b-r)/d+2)/6;
        else hue=((r-g)/d+4)/6;
    }
    return {h:hue*360, s:sat*100, l:lit*100};
}
window.hexToHsl = hexToHsl;

function deriveThemeFromAccent(accentHex, isLight, satPct) {
    const hsl = hexToHsl(accentHex);
    const h = hsl.h;
    const bgSat = (satPct||30)/100*15;
    const bgLit = isLight ? 93 : 7;
    const bg = hslToHex(h, bgSat/100, bgLit/100);
    const fgSat = bgSat*1.5;
    const fgLit = isLight ? 22 : 78;
    const fg = hslToHex(h, Math.min(fgSat,40)/100, fgLit/100);
    const accent = accentHex;
    const tip = mixHex(fg, bg, 0.5);
    const fontColor = isLight ? darkenColor(fg, 0.05) : lightenColor(fg, 0.05);
    return {bg, fg, accent, tip, font_color: fontColor};
}
window.deriveThemeFromAccent = deriveThemeFromAccent;

function applyThemeVars(theme) {
    const r = document.documentElement.style;
    const bg = theme.bg || '#0c0c14';
    const fg = theme.fg || '#e0d8f0';
    const accent = theme.accent || '#ff6ec7';
    const tip = theme.tip || '#8880a0';
    const font_color = theme.font_color || fg;
    const dark = isDarkColor(bg);
    const secondary = theme.secondary || (dark ? lightenColor(bg, 0.06) : darkenColor(bg, 0.03));
    const border = theme.border || (dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.1)');
    const card_bg = theme.card_bg || (dark ? lightenColor(bg, 0.04) : darkenColor(bg, 0.01));
    const bg2 = dark ? lightenColor(bg, 0.04) : darkenColor(bg, 0.02);
    const fg3 = dark ? lightenColor(tip, 0.3) : darkenColor(tip, 0.2);
    const accent2 = theme.accent2 || lightenColor(accent, 0.3);

    r.setProperty('--bg', bg);
    r.setProperty('--bg2', bg2);
    r.setProperty('--fg', fg);
    r.setProperty('--fg2', tip);
    r.setProperty('--fg3', fg3);
    r.setProperty('--accent', accent);
    r.setProperty('--accent2', accent2);
    r.setProperty('--card', dark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)');
    r.setProperty('--card-border', dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)');
    r.setProperty('--card-bg', card_bg);
    r.setProperty('--border', border);
    r.setProperty('--input-bg', secondary);
    r.setProperty('--tip', tip);
    r.setProperty('--secondary', secondary);
    r.setProperty('--font-color', font_color);

    const accentR = parseInt(accent.slice(1,3),16);
    const accentG = parseInt(accent.slice(3,5),16);
    const accentB = parseInt(accent.slice(5,7),16);
    r.setProperty('--accent-rgb', accentR+','+accentG+','+accentB);
    r.setProperty('--glow', 'rgba(' + accentR + ',' + accentG + ',' + accentB + ',0.06)');
    r.setProperty('--highlight-bg', theme.highlight || 'rgba('+accentR+','+accentG+','+accentB+',0.12)');
    r.setProperty('--code-bg', theme.code_bg || (dark ? '#282c34' : '#f6f8fa'));
    r.setProperty('--code-color', theme.code_color || (dark ? '#abb2bf' : '#24292e'));
    r.setProperty('--danger', '#e74c3c');
    r.setProperty('--danger-rgb', '231,76,60');
    r.setProperty('--success', '#00b894');
    r.setProperty('--warning', '#fdcb6e');

    return { bg, fg, accent, tip, font_color, dark, secondary, border, card_bg, accentR, accentG, accentB };
}
const _svg = (p) => '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + p + '</svg>';
const ICONS = {
    palette: _svg('<circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>'),
    book: _svg('<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>'),
    image: _svg('<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>'),
    bookmark: _svg('<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>'),
    note: _svg('<path d="M16 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8Z"/><path d="M15 3v4a2 2 0 0 0 2 2h4"/>'),
    chart: _svg('<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>'),
    settings: _svg('<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>'),
    log: _svg('<path d="M16 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8Z"/><path d="M15 3v4a2 2 0 0 0 2 2h4"/><path d="M8 13h8"/><path d="M8 17h8"/>'),
    trash: _svg('<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'),
    copy: _svg('<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>'),
    save: _svg('<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>'),
    search: _svg('<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'),
    plus: _svg('<path d="M5 12h14"/><path d="M12 5v14"/>'),
    download: _svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>'),
    upload: _svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>'),
    reset: _svg('<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>'),
    refresh: _svg('<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/>'),
    check: _svg('<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>'),
    close: _svg('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'),
    folder: _svg('<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>'),
    file: _svg('<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 13H8"/><path d="M16 17H8"/><path d="M16 13h-2"/>'),
    edit: _svg('<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/>'),
    pin: _svg('<line x1="12" x2="12" y1="17" y2="22"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"/>'),
    lightbulb: _svg('<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>'),
    user: _svg('<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>'),
    moon: _svg('<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>'),
    sun: _svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>'),
    chevronDown: _svg('<path d="m6 9 6 6 6-6"/>'),
    dice: _svg('<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><path d="M16 8h.01"/><path d="M12 12h.01"/><path d="M8 16h.01"/><path d="M8 8h.01"/><path d="M16 16h.01"/>'),
    layout: _svg('<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/>'),
    selectAll: _svg('<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>'),
};
window.ICONS = ICONS;

window.applyThemeVars = applyThemeVars;
