        let bookName = '';
        let currentChapter = 0;
        let chapterCount = 0;
        let chapters = [];
        let autoReadSpeed = 0;
        let autoReadTimer = null;
        let autoReadBadgeTimer = null;
        let savedPosition = 0;
        let readerSettings = {};
        let isDragging = false;
        let shortcutSettings = { scroll_up: 'ArrowUp', scroll_down: 'ArrowDown', scroll_lines: 5, prev_chapter: '', next_chapter: '' };
        let loadedStart = 0;
        let loadedEnd = 0;
        let isLoadingMore = false;
        let _lastReadPos = null;
        // 每次加载的章节数量（向下滚动时加载更多章节的批次大小）
        const CHUNK_SIZE = 20;
        // 自动阅读速度范围
        const MIN_AUTO_READ_SPEED = -20;
        const MAX_AUTO_READ_SPEED = 20;
        // 时间更新间隔（毫秒）
        const TIME_UPDATE_INTERVAL = 60000;

        const $el = {
            content: null,
            readerContent: null,
            bookTitle: null,
            progressInfo: null,
            chapterInfo: null,
            timeInfo: null,
            tocPanel: null,
            bmPanel: null,
            autoReadBadge: null,
            prevBtn: null,
            nextBtn: null,
            bgOverlay: null
        };

        function openLightbox(src) {
            document.getElementById('lbImg').src = src;
            document.getElementById('imgLightbox').classList.add('active');
        }
        function closeLightbox() {
            document.getElementById('imgLightbox').classList.remove('active');
            document.getElementById('lbImg').src = '';
        }

        async function init() {
            $el.content = document.getElementById('contentArea');
            $el.readerContent = document.getElementById('readerContent');
            $el.bookTitle = document.getElementById('bookTitle');
            $el.progressInfo = document.getElementById('progressInfo');
            $el.chapterInfo = document.getElementById('chapterInfo');
            $el.timeInfo = document.getElementById('timeInfo');
            $el.tocPanel = document.getElementById('tocPanel');
            $el.bmPanel = document.getElementById('bmPanel');
            $el.autoReadBadge = document.getElementById('autoReadBadge');
            $el.prevBtn = document.getElementById('prevBtn');
            $el.nextBtn = document.getElementById('nextBtn');
            $el.bgOverlay = document.getElementById('bgOverlay');

            try { bookName = await api().get_current_book_name(); } catch (e) {}
            if (!bookName) { $el.content.textContent = '未指定书籍'; return; }

            await Promise.all([loadTheme(), loadShortcutSettings(), loadBookData()]);
            loadCustomFonts();
            setupScrollTracking();
            setupKeyboard();
            setupContextMenu();
            setupLinkHandler();
            setupDrag();
            setupResize();
            updateTime();
            setInterval(updateTime, TIME_UPDATE_INTERVAL);
            loadAlwaysOnTopState();
            document.addEventListener('visibilitychange', function() {
                if (!document.hidden) refreshFromMain();
            });
        }

        function _applyThemeVars(theme) {
            const result = applyThemeVars(theme);
            const r = document.documentElement.style;
            const dark = result.dark;

            const btnNormal = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
            const btnHover = dark ? 'rgba(255,255,255,0.14)' : 'rgba(0,0,0,0.12)';
            r.setProperty('--btn-normal', btnNormal);
            r.setProperty('--btn-hover', btnHover);
            r.setProperty('--scroll-thumb', dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.15)');
            r.setProperty('--panel-shadow', dark ? 'rgba(0,0,0,0.5)' : 'rgba(0,0,0,0.15)');

            if (typeof readerSettings !== 'undefined' && readerSettings) {
                applyBackgroundImage(readerSettings);
            } else {
                document.body.style.background = '';
                var card = document.querySelector('.card');
                if (card) card.style.background = '';
            }
        }

        async function loadTheme() {
            try {
                const theme = await api().get_current_theme();
                _applyThemeVars(theme);
                updateThemeToggleIcon();
            } catch (e) {}
        }


        function applyThemeDirect(colors) {
            const bg = colors.bg || '#0c0c14';
            const fg = colors.fg || '#e0d8f0';
            const accent = colors.accent || '#ff6ec7';
            const tip = colors.tip || '#8880a0';
            const font_color = colors.font_color || fg;
            const dark = isDarkColor(bg);
            const secondary = dark ? lightenColor(bg, 0.06) : darkenColor(bg, 0.03);
            _applyThemeVars({
                bg, fg, accent, tip, font_color, secondary,
                card_bg: dark ? lightenColor(bg, 0.04) : darkenColor(bg, 0.01),
                border: dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.1)',
            });
        }

        function updateThemeToggleIcon() {
            const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
            const el = document.getElementById('themeToggle');
            if (!el) return;
            if (isDarkColor(bg)) {
                el.innerHTML = '<svg viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 0 1 11.21 3a7 7 0 1 0 9.79 9.79z"/></svg>';
            } else {
                el.innerHTML = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3" stroke-width="2" stroke-linecap="round"/><line x1="12" y1="21" x2="12" y2="23" stroke-width="2" stroke-linecap="round"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" stroke-width="2" stroke-linecap="round"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" stroke-width="2" stroke-linecap="round"/><line x1="1" y1="12" x2="3" y2="12" stroke-width="2" stroke-linecap="round"/><line x1="21" y1="12" x2="23" y2="12" stroke-width="2" stroke-linecap="round"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" stroke-width="2" stroke-linecap="round"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" stroke-width="2" stroke-linecap="round"/></svg>';
            }
        }

        async function toggleDarkLight() {
            try {
                const next = await api().get_next_theme_name();
                const theme = await api().set_theme(next);
                if (theme && theme.bg) {
                    _applyThemeVars(theme);
                    updateThemeToggleIcon();
                    applyBackgroundImage(readerSettings);
                }
            } catch (e) {}
        }

        let _cachedAnchors = null;
        let _cachedLineHeight = 0;

        function invalidateCache() {
            _cachedAnchors = null;
            _cachedLineHeight = 0;
            _tocPreviewsLoaded = false;
        }

        function appendAnchorsFrom(container) {
            if (_cachedAnchors) {
                const newAnchors = container.querySelectorAll('.ch-anchor');
                newAnchors.forEach(a => _cachedAnchors.push(a));
            }
        }

        function getAnchors() {
            if (!_cachedAnchors) {
                _cachedAnchors = Array.from($el.content.querySelectorAll('.ch-anchor'));
            }
            return _cachedAnchors;
        }

        function getCachedLineHeight() {
            if (!_cachedLineHeight) {
                _cachedLineHeight = parseFloat(getComputedStyle($el.content).lineHeight) || 24;
            }
            return _cachedLineHeight;
        }

        let isResizing = false;

        function addCopyBtn(pre, codeEl) {
            if (pre.querySelector('.code-copy-btn')) return;
            const btn = document.createElement('button');
            btn.className = 'code-copy-btn';
            btn.textContent = '复制';
            btn.onclick = function(e) {
                e.stopPropagation();
                copyToClipboard(codeEl.textContent);
                btn.textContent = '已复制';
                btn.classList.add('copied');
                setTimeout(() => { btn.textContent = '复制'; btn.classList.remove('copied'); }, 1500);
            };
            pre.appendChild(btn);
        }

        function highlightBlock(block) {
            if (block.classList.contains('hljs') || typeof hljs === 'undefined') return;
            try {
                if (block.className && block.className.includes('language-')) {
                    hljs.highlightElement(block);
                } else {
                    block.classList.add('language-python');
                    hljs.highlightElement(block);
                }
            } catch (e) {}
        }

        function processCodeBlocks() {
            const blocks = $el.content.querySelectorAll('pre code');
            blocks.forEach(block => {
                const pre = block.parentElement;
                if (pre && pre.tagName === 'PRE') {
                    addCopyBtn(pre, block);
                    highlightBlock(block);
                }
            });
        }

        function forceOpenDetails() {
            $el.content.querySelectorAll('details').forEach(function(d) {
                d.setAttribute('open', '');
            });
        }

        function applyBackgroundImage(settings) {
            const img = (settings && (settings.reader_bg_image || settings.background_image)) || '';
            const opacity = settings ? (settings.reader_bg_opacity ?? settings.background_opacity) : null;
            if (img) {
                api().get_image_data_url(img).then(function(dataUrl) {
                    if (dataUrl) {
                        const cs = getComputedStyle(document.documentElement);
                        const bgHex = cs.getPropertyValue('--bg').trim();
                        document.body.style.background = bgHex + ' url(' + dataUrl + ') center/cover no-repeat fixed';
                        const card = document.querySelector('.card');
                        if (card) {
                            const r = parseInt(bgHex.replace('#','').substring(0,2), 16) || 12;
                            const g = parseInt(bgHex.replace('#','').substring(2,4), 16) || 12;
                            const b = parseInt(bgHex.replace('#','').substring(4,6), 16) || 20;
                            const op = (opacity != null) ? (1 - opacity) : 0.85;
                            card.style.background = 'rgba(' + r + ',' + g + ',' + b + ',' + op + ')';
                        }
                    }
                }).catch(function() {});
            } else {
                document.body.style.background = '';
                const card = document.querySelector('.card');
                if (card) card.style.background = '';
            }
        }

        function showLoading() {
            const el = document.getElementById('loadingOverlay');
            if (el) el.classList.remove('hidden');
        }
        function hideLoading() {
            const el = document.getElementById('loadingOverlay');
            if (el) el.classList.add('hidden');
        }
        function updateLoadingProgress(text, pct) {
            const t = document.getElementById('loadingText');
            const b = document.getElementById('loadingBar');
            if (t) t.textContent = text;
            if (b) b.style.width = (pct || 0) + '%';
        }

        async function loadBookData() {
            showLoading();
            updateLoadingProgress('正在获取书籍信息...', 5);
            try {
                let displayData = null;
                let pollDelay = 200;
                for (let i = 0; i < 10; i++) {
                    displayData = await api().get_book_display_data(bookName);
                    if (displayData.success) break;
                    updateLoadingProgress('正在解析书籍...', 5 + Math.min(i * 4, 30));
                    await new Promise(r => setTimeout(r, pollDelay));
                    pollDelay = Math.min(pollDelay * 1.4, 1000);
                }
                if (!displayData || !displayData.success) { $el.content.textContent = (displayData && displayData.error) || '打开失败'; hideLoading(); return; }
                $el.bookTitle.textContent = '📖 ' + (bookName.length > 10 ? bookName.slice(0,10)+'…' : bookName);
                currentChapter = displayData.current_chapter;
                chapterCount = displayData.chapter_count;
                chapters = displayData.chapters;
                savedPosition = displayData.scroll_percent || 0;
                if (displayData.settings) readerSettings = displayData.settings;
                _lastAppliedSettings = {};
                renderToc();
                updateNavButtons();
                applyBackgroundImage(readerSettings);
                updateLoadingProgress('正在生成全文...', 10);
                await initChunkedLoad();
            } catch (e) {
                $el.content.textContent = '加载失败';
                hideLoading();
            }
        }

        function getChapterRatio() {
            const anchor = document.getElementById('ch-' + currentChapter);
            if (!anchor) return 0;
            const c = $el.readerContent;
            const nextAnchor = document.getElementById('ch-' + (currentChapter + 1));
            const chapterBottom = nextAnchor ? nextAnchor.offsetTop : c.scrollHeight;
            const chapterHeight = chapterBottom - anchor.offsetTop;
            const scrollInChapter = Math.max(0, c.scrollTop - anchor.offsetTop);
            return chapterHeight > 0 ? Math.min(1, scrollInChapter / chapterHeight) : 0;
        }

        async function initChunkedLoad() {
            const savedChapter = currentChapter;
            const savedRatio = (savedPosition > 0 && savedPosition <= 100000) ? savedPosition / 100000 : 0;
            const start = Math.max(0, savedChapter - Math.floor(CHUNK_SIZE / 2));
            const count = CHUNK_SIZE;
            updateLoadingProgress('正在加载章节...', 20);
            try {
                const r = await api().get_chapters_range(bookName, start, count);
                if (!r.success) { $el.content.textContent = r.error || '加载失败'; hideLoading(); return; }
                updateLoadingProgress('正在渲染页面...', 90);
                const fragment = document.createRange().createContextualFragment('<div class="full-text">' + r.html + '</div>');
                $el.content.innerHTML = '';
                $el.content.appendChild(fragment);
                $el.content.classList.remove('chapter-fade');
                void $el.content.offsetWidth;
                $el.content.classList.add('chapter-fade');
                loadedStart = r.start;
                loadedEnd = r.end;
                chapterCount = r.total;
                invalidateCache();
                forceOpenDetails();
                applyReaderSettings();
                processCodeBlocks();
                updateChapterInfo();
                if (savedChapter > 0 || savedRatio > 0) {
                    updateLoadingProgress('正在恢复阅读位置...', 96);
                    setTimeout(() => {
                        const anchor = document.getElementById('ch-' + savedChapter);
                        if (anchor) {
                            currentChapter = savedChapter;
                            const nextAnchor = document.getElementById('ch-' + (savedChapter + 1));
                            const chapterBottom = nextAnchor ? nextAnchor.offsetTop : $el.readerContent.scrollHeight;
                            const chapterHeight = chapterBottom - anchor.offsetTop;
                            $el.readerContent.scrollTop = anchor.offsetTop + savedRatio * chapterHeight;
                            renderToc();
                            updateChapterInfo();
                        }
                        savedPosition = 0;
                        updateProgress();
                        hideLoading();
                    }, 200);
                } else {
                    hideLoading();
                }
            } catch (e) {
                $el.content.textContent = '加载失败';
                hideLoading();
            }
        }

        async function loadMoreDown() {
            if (isLoadingMore || loadedEnd >= chapterCount) return;
            isLoadingMore = true;
            const start = loadedEnd;
            const count = Math.min(CHUNK_SIZE, chapterCount - start);
            try {
                const r = await api().get_chapters_range(bookName, start, count);
                if (r.success && r.html) {
                    const ft = $el.content.querySelector('.full-text');
                    if (ft) {
                        const wrapper = document.createElement('div');
                        wrapper.innerHTML = '<hr class="ch-sep">' + r.html;
                        appendAnchorsFrom(wrapper);
                        ft.appendChild(wrapper);
                    }
                    loadedEnd = r.end;
                    forceOpenDetails();
                    applyReaderSettings();
                    processCodeBlocks();
                }
            } catch (e) {}
            isLoadingMore = false;
        }

        async function loadMoreUp() {
            if (isLoadingMore || loadedStart <= 0) return;
            isLoadingMore = true;
            const c = $el.readerContent;
            const oldHeight = c.scrollHeight;
            const start = Math.max(0, loadedStart - CHUNK_SIZE);
            const count = loadedStart - start;
            try {
                const r = await api().get_chapters_range(bookName, start, count);
                if (r.success && r.html) {
                    const ft = $el.content.querySelector('.full-text');
                    if (ft) {
                        const fragment = document.createRange().createContextualFragment(r.html + '<hr class="ch-sep">');
                        const wrapper = document.createElement('div');
                        wrapper.appendChild(fragment);
                        appendAnchorsFrom(wrapper);
                        ft.prepend(wrapper);
                    }
                    loadedStart = r.start;
                    forceOpenDetails();
                    applyReaderSettings();
                    processCodeBlocks();
                    requestAnimationFrame(() => {
                        c.scrollTop += c.scrollHeight - oldHeight;
                    });
                }
            } catch (e) {}
            isLoadingMore = false;
        }

        function checkLoadMore() {
            if (isLoadingMore) return;
            const c = $el.readerContent;
            if (c.scrollTop + c.clientHeight > c.scrollHeight - 1000 && loadedEnd < chapterCount) {
                loadMoreDown();
            }
            if (c.scrollTop < 1000 && loadedStart > 0) {
                loadMoreUp();
            }
        }

        async function scrollToChapter(ch) {
            const anchor = document.getElementById('ch-' + ch);
            if (anchor) {
                $el.readerContent.scrollTop = anchor.offsetTop - 10;
                currentChapter = ch;
                renderToc();
                updateChapterInfo();
            } else if (!isLoadingMore) {
                isLoadingMore = true;
                const start = Math.max(0, ch - Math.floor(CHUNK_SIZE / 2));
                const count = CHUNK_SIZE;
                try {
                    const r = await api().get_chapters_range(bookName, start, count);
                    if (r.success && r.html) {
                        $el.content.innerHTML = '<div class="full-text">' + r.html + '</div>';
                        loadedStart = r.start;
                        loadedEnd = r.end;
                        invalidateCache();
                        forceOpenDetails();
                        applyReaderSettings();
                        processCodeBlocks();
                        const a = document.getElementById('ch-' + ch);
                        if (a) {
                            $el.readerContent.scrollTop = a.offsetTop - 10;
                            currentChapter = ch;
                            renderToc();
                            updateChapterInfo();
                        }
                    }
                } catch (e) {}
                isLoadingMore = false;
            }
        }

        function saveLastReadPos() {
            if (chapterCount <= 0) return;
            const ratio = getChapterRatio();
            _lastReadPos = {
                chapter: currentChapter,
                scrollTop: $el.readerContent.scrollTop,
                ratio: ratio,
                title: chapters[currentChapter] ? chapters[currentChapter].title : ('第' + (currentChapter + 1) + '章')
            };
            updateLastReadBtn();
        }

        async function restoreLastReadPos() {
            if (!_lastReadPos) return;
            const target = _lastReadPos;
            _lastReadPos = null;
            updateLastReadBtn();
            await scrollToChapter(target.chapter);
            const anchor = document.getElementById('ch-' + target.chapter);
            if (anchor) {
                const nextAnchor = document.getElementById('ch-' + (target.chapter + 1));
                const chapterBottom = nextAnchor ? nextAnchor.offsetTop : $el.readerContent.scrollHeight;
                const chapterHeight = chapterBottom - anchor.offsetTop;
                $el.readerContent.scrollTop = anchor.offsetTop + target.ratio * chapterHeight;
                currentChapter = target.chapter;
                renderToc();
                updateChapterInfo();
                updateProgress();
            }
            showToast('已返回: ' + target.title);
        }

        function updateLastReadBtn() {
            const btn = document.getElementById('lastReadBtn');
            if (!btn) return;
            if (_lastReadPos) {
                btn.classList.add('visible');
                const textSpan = btn.querySelector('span:first-child');
                if (textSpan) textSpan.title = '返回: ' + _lastReadPos.title;
            } else {
                btn.classList.remove('visible');
            }
        }

        function dismissLastReadBtn(e) {
            e.stopPropagation();
            _lastReadPos = null;
            updateLastReadBtn();
        }

        function detectCurrentChapter() {
            const anchors = getAnchors();
            if (anchors.length === 0) return;
            const scrollTop = $el.readerContent.scrollTop + 80;
            let lo = 0, hi = anchors.length - 1;
            let detected = 0;
            while (lo <= hi) {
                const mid = (lo + hi) >>> 1;
                if (anchors[mid].offsetTop <= scrollTop) {
                    detected = parseInt(anchors[mid].dataset.chapter);
                    lo = mid + 1;
                } else {
                    hi = mid - 1;
                }
            }
            if (detected !== currentChapter) {
                currentChapter = detected;
                renderToc();
                updateChapterInfo();
            }
        }

        async function loadShortcutSettings() {
            try {
                const sc = await api().get_shortcut_settings();
                if (sc) {
                    shortcutSettings.scroll_up = sc.scroll_up || 'ArrowUp';
                    shortcutSettings.scroll_down = sc.scroll_down || 'ArrowDown';
                    shortcutSettings.scroll_lines = sc.scroll_lines != null ? sc.scroll_lines : 5;
                    shortcutSettings.prev_chapter = sc.prev_chapter || '';
                    shortcutSettings.next_chapter = sc.next_chapter || '';
                }
            } catch (e) {}
        }

        function matchShortcut(e, pattern) {
            if (!pattern) return false;
            const parts = pattern.split('+').map(s => s.trim().toLowerCase());
            const key = e.key.length === 1 ? e.key.toUpperCase().toLowerCase() : e.key.toLowerCase();
            const hasCtrl = parts.includes('ctrl');
            const hasAlt = parts.includes('alt');
            const hasShift = parts.includes('shift');
            const hasMeta = parts.includes('meta');
            const mainKey = parts.find(p => !['ctrl','alt','shift','meta'].includes(p));
            if (hasCtrl !== e.ctrlKey) return false;
            if (hasAlt !== e.altKey) return false;
            if (hasShift !== e.shiftKey) return false;
            if (hasMeta !== e.metaKey) return false;
            if (mainKey && mainKey !== key) return false;
            return true;
        }

        let _lastAppliedSettings = {};
        function applyReaderSettings() {
            const el = $el.content;
            const r = document.documentElement.style;
            const s = readerSettings;
            let needInvalidate = false;
            if (s.font_family && s.font_family !== _lastAppliedSettings.font_family) { el.style.fontFamily = s.font_family; _lastAppliedSettings.font_family = s.font_family; }
            if (s.font_size && s.font_size !== _lastAppliedSettings.font_size) { el.style.fontSize = s.font_size + 'px'; _lastAppliedSettings.font_size = s.font_size; needInvalidate = true; }
            if (s.line_spacing && s.line_spacing !== _lastAppliedSettings.line_spacing) { el.style.lineHeight = s.line_spacing; _lastAppliedSettings.line_spacing = s.line_spacing; needInvalidate = true; }
            if (s.font_color && s.font_color !== _lastAppliedSettings.font_color) {
                el.style.color = s.font_color;
                r.setProperty('--font-color', s.font_color);
                _lastAppliedSettings.font_color = s.font_color;
            }
            const ps = s.paragraph_spacing;
            if (ps != null && ps !== _lastAppliedSettings.paragraph_spacing) { r.setProperty('--p-margin', ps + 'px'); _lastAppliedSettings.paragraph_spacing = ps; }
            const ti = s.text_indent;
            if (ti != null && ti !== _lastAppliedSettings.text_indent) { r.setProperty('--p-indent', ti > 0 ? ti + 'em' : '0'); _lastAppliedSettings.text_indent = ti; }
            if (needInvalidate) invalidateCache();
        }

        function applyTypographyPreview(s) {
            const el = $el.content;
            const r = document.documentElement.style;
            if (s.font_size || s.line_spacing) invalidateCache();
            if (s.font_family) { el.style.fontFamily = s.font_family; readerSettings.font_family = s.font_family; }
            if (s.font_size) { el.style.fontSize = s.font_size + 'px'; readerSettings.font_size = s.font_size; }
            if (s.line_spacing) { el.style.lineHeight = s.line_spacing; readerSettings.line_spacing = s.line_spacing; }
            if (s.font_color) {
                el.style.color = s.font_color;
                r.setProperty('--font-color', s.font_color);
                readerSettings.font_color = s.font_color;
            }
            if (s.paragraph_spacing != null) { r.setProperty('--p-margin', s.paragraph_spacing + 'px'); readerSettings.paragraph_spacing = s.paragraph_spacing; }
            if (s.text_indent != null) { r.setProperty('--p-indent', s.text_indent > 0 ? s.text_indent + 'em' : '0'); readerSettings.text_indent = s.text_indent; }
            if (s.reader_bg_image !== undefined) {
                readerSettings.reader_bg_image = s.reader_bg_image;
            }
            if (s.background_opacity != null || s.reader_bg_opacity != null) {
                readerSettings.reader_bg_opacity = s.reader_bg_opacity ?? s.background_opacity;
            }
            if (s.reader_bg_image !== undefined || s.background_opacity != null || s.reader_bg_opacity != null) {
                applyBackgroundImage(readerSettings);
            }
        }

        function refreshFromMain() {
            api().get_current_theme().then(function(theme) {
                _applyThemeVars(theme);
                updateThemeToggleIcon();
                if (bookName && chapterCount > 0) {
                    return api().get_book_display_data(bookName);
                }
                return null;
            }).then(function(data) {
                if (data && data.settings) {
                    readerSettings = data.settings;
                    applyReaderSettings();
                    applyBackgroundImage(readerSettings);
                }
            }).catch(function() {});
        }

        function loadCustomFonts() {
            api().get_custom_fonts().then(function(fonts) {
                if (!fonts || fonts.length === 0) return;
                let styleEl = document.getElementById('customFontStyles');
                if (!styleEl) {
                    styleEl = document.createElement('style');
                    styleEl.id = 'customFontStyles';
                    document.head.appendChild(styleEl);
                }
                let css = '';
                for (const f of fonts) {
                    css += '@font-face{font-family:"' + f.name + '";src:url("file:///' + f.path.replace(/\\/g, '/') + '");}\n';
                }
                styleEl.textContent = css;
            }).catch(function() {});
        }

        function filterToc() {
            const query = (document.getElementById('tocSearch').value || '').toLowerCase();
            const items = document.getElementById('tocList').children;
            let visibleCount = 0;
            for (let i = 0; i < items.length; i++) {
                const title = items[i].querySelector('.toc-ch-title');
                const text = title ? title.textContent.toLowerCase() : '';
                const match = !query || text.includes(query);
                items[i].style.display = match ? '' : 'none';
                if (match) visibleCount++;
            }
            document.getElementById('tocCount').textContent = visibleCount + '章';
        }

        function renderToc() {
            const el = document.getElementById('tocList');
            document.getElementById('tocCount').textContent = chapters.length + '章';
            const items = el.children;
            if (items.length === chapters.length) {
                for (let i = 0; i < items.length; i++) {
                    const item = items[i];
                    const isActive = i === currentChapter;
                    if (isActive && !item.classList.contains('active')) {
                        item.classList.add('active');
                        if (!item.querySelector('.toc-indicator')) {
                            const ind = document.createElement('div');
                            ind.className = 'toc-indicator';
                            item.prepend(ind);
                        }
                        item.querySelector('.toc-ch-title').style.color = '#fff';
                    } else if (!isActive && item.classList.contains('active')) {
                        item.classList.remove('active');
                        const ind = item.querySelector('.toc-indicator');
                        if (ind) ind.remove();
                        item.querySelector('.toc-ch-title').style.color = '';
                    }
                }
            } else {
                el.innerHTML = chapters.map((ch, i) => {
                    const lvl = (ch.level && ch.level > 1) ? ' toc-level-' + ch.level : '';
                    return '<div class="toc-item' + lvl + ' ' + (i === currentChapter ? 'active' : '') + '" onclick="gotoChapter(' + i + ')">' +
                    (i === currentChapter ? '<div class="toc-indicator"></div>' : '') +
                    '<div class="toc-ch-title">' + escapeHtml(ch.title) + '</div>' +
                    '<div class="toc-ch-preview">' + escapeHtml(ch.preview) + '</div></div>';
                }).join('');
            }
        }

        function updateChapterInfo() {
            const el = $el.chapterInfo;
            const title = chapters[currentChapter] ? chapters[currentChapter].title : '';
            const text = title || ('第' + (currentChapter + 1) + '章');
            el.textContent = text;
        }
        function updateTime() {
            $el.timeInfo.textContent = new Date().toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
        }
        let _progressSaveTimer = null;
        function updateProgress() {
            if (chapterCount <= 0) { $el.progressInfo.textContent = '0%'; return; }
            const ratio = getChapterRatio();
            const pct = Math.min(100, Math.round(((currentChapter + ratio) / chapterCount) * 100));
            $el.progressInfo.textContent = (currentChapter + 1) + '/' + chapterCount + '章 ' + pct + '%';
            if (bookName) {
                clearTimeout(_progressSaveTimer);
                _progressSaveTimer = setTimeout(() => {
                    api().update_reading_progress(bookName, currentChapter, Math.round(ratio * 100000)).catch(() => {});
                }, 500);
            }
        }

        function updateNavButtons() {
            if ($el.prevBtn) $el.prevBtn.disabled = currentChapter <= 0;
            if ($el.nextBtn) $el.nextBtn.disabled = currentChapter >= chapterCount - 1;
        }

        let _isFlipping = false;

        function showPageFlip(direction) {
            if (_isFlipping) return false;

            const container = $el.readerContent;
            const content = $el.content;
            const pageHeight = container.clientHeight - 40;
            const originScrollTop = container.scrollTop;
            const targetScrollTop = direction === 'down'
                ? originScrollTop + pageHeight
                : originScrollTop - pageHeight;

            if (direction === 'down') {
                if (originScrollTop + container.clientHeight >= container.scrollHeight - 5) return false;
            } else {
                if (originScrollTop <= 5) return false;
            }

            _isFlipping = true;
            const outY = direction === 'down' ? '-14px' : '14px';
            const inY = direction === 'down' ? '14px' : '-14px';

            content.style.transition = 'transform 0.12s cubic-bezier(0.4,0,1,1), opacity 0.12s ease-in';
            content.style.transform = 'translateY(' + outY + ')';
            content.style.opacity = '0.3';

            function onOutEnd(e) {
                if (e.propertyName !== 'transform') return;
                content.removeEventListener('transitionend', onOutEnd);
                container.scrollTop = targetScrollTop;
                content.style.transition = 'none';
                content.style.transform = 'translateY(' + inY + ')';
                content.offsetHeight;
                content.style.transition = 'transform 0.14s cubic-bezier(0,0,0.2,1), opacity 0.14s ease-out';
                content.style.transform = 'translateY(0)';
                content.style.opacity = '1';
                content.addEventListener('transitionend', onInEnd);
            }

            function onInEnd(e) {
                if (e.propertyName !== 'transform') return;
                content.removeEventListener('transitionend', onInEnd);
                content.style.transition = '';
                content.style.transform = '';
                content.style.opacity = '';
                _isFlipping = false;
                detectCurrentChapter();
                updateProgress();
                checkLoadMore();
            }

            content.addEventListener('transitionend', onOutEnd);

            return true;
        }


        function setupScrollTracking() {
            const c = $el.readerContent;
            let ticking = false;
            let _mouseDownX = -1;
            let _mouseDownY = -1;
            c.addEventListener('scroll', () => {
                if (ticking) return;
                ticking = true;
                requestAnimationFrame(() => {
                    ticking = false;
                    if (!_isFlipping) {
                        detectCurrentChapter();
                        updateProgress();
                        checkLoadMore();
                        if (_lastReadPos && _lastReadPos.chapter === currentChapter) {
                            const anchor = document.getElementById('ch-' + currentChapter);
                            if (anchor) {
                                const nextAnchor = document.getElementById('ch-' + (currentChapter + 1));
                                const chapterBottom = nextAnchor ? nextAnchor.offsetTop : c.scrollHeight;
                                const chapterHeight = chapterBottom - anchor.offsetTop;
                                const curRatio = chapterHeight > 0 ? (c.scrollTop - anchor.offsetTop) / chapterHeight : 0;
                                if (Math.abs(curRatio - _lastReadPos.ratio) < 0.05) {
                                    _lastReadPos = null;
                                    updateLastReadBtn();
                                }
                            }
                        }
                    }
                });
            });
            c.addEventListener('wheel', e => {
                if (isDragging || _isFlipping) { e.preventDefault(); return; }
                if (e.ctrlKey && e.altKey) {
                    e.preventDefault();
                    const delta = e.deltaY > 0 ? -1 : 1;
                    const cur = readerSettings.font_size || 14;
                    const next = Math.max(10, Math.min(30, cur + delta));
                    if (next !== cur) {
                        readerSettings.font_size = next;
                        $el.content.style.fontSize = next + 'px';
                        invalidateCache();
                        showToast('字体: ' + next + 'px');
                        try { api().update_settings({ font_size: next }); } catch (ex) {}
                    }
                    return;
                }
                if (e.ctrlKey) {
                    e.preventDefault();
                    adjustAutoReadSpeed(e.deltaY > 0 ? 0.25 : -0.25);
                    return;
                }
            }, {passive: false});
            c.addEventListener('mousedown', e => {
                if (e.button !== 0) return;
                _mouseDownX = e.clientX;
                _mouseDownY = e.clientY;
            });
            c.addEventListener('click', e => {
                if (e.target.closest('button') || e.target.closest('.ctx-menu') || e.target.closest('.side-panel')) return;
                if (_mouseDownX < 0) return;
                const dx = Math.abs(e.clientX - _mouseDownX);
                const dy = Math.abs(e.clientY - _mouseDownY);
                _mouseDownX = -1;
                _mouseDownY = -1;
                if (dx > 5 || dy > 5) return;
                const rect = c.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const w = rect.width;
                const isLeft = x < w * 0.15;
                const isRight = x > w * 0.85;
                if (!isLeft && !isRight) return;
                if (_isFlipping) return;
                e.preventDefault();
                e.stopPropagation();
                if (isLeft) {
                    if (c.scrollTop <= 5) prevChapter();
                    else showPageFlip('up');
                } else {
                    if (c.scrollTop + c.clientHeight >= c.scrollHeight - 5) nextChapter();
                    else showPageFlip('down');
                }
            });
        }

        function setupKeyboard() {
            document.addEventListener('keydown', e => {
                if (!bookName) return;
                if (e.key === 'Escape') {
                    closeLightbox();
                    stopAutoReading();
                    $el.tocPanel.classList.remove('active');
                    $el.bmPanel.classList.remove('active');
                    document.getElementById('ctxMenu').classList.remove('active');
                    if (document.getElementById('searchBar').classList.contains('active')) {
                        closeSearch();
                    }
                    return;
                }
                if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
                    e.preventDefault();
                    toggleSearch();
                    return;
                }

                const sc = shortcutSettings;
                const lines = sc.scroll_lines || 5;

                if (matchShortcut(e, sc.prev_chapter)) { e.preventDefault(); prevChapter(); return; }
                if (matchShortcut(e, sc.next_chapter)) { e.preventDefault(); nextChapter(); return; }

                if (e.key === 'PageUp' || e.key === 'ArrowLeft') {
                    e.preventDefault();
                    const c = $el.readerContent;
                    if (c.scrollTop <= 5) { prevChapter(); }
                    else { showPageFlip('up'); }
                    return;
                }
                if (e.key === 'PageDown' || e.key === 'ArrowRight' || e.key === ' ') {
                    e.preventDefault();
                    const c = $el.readerContent;
                    if (c.scrollTop + c.clientHeight >= c.scrollHeight - 5) { nextChapter(); }
                    else { showPageFlip('down'); }
                    return;
                }

                if (matchShortcut(e, sc.scroll_up)) {
                    e.preventDefault();
                    const c = $el.readerContent;
                    if (c.scrollTop <= 5) { prevChapter(); }
                    else { scrollLines(-lines); }
                    return;
                }
                if (matchShortcut(e, sc.scroll_down)) {
                    e.preventDefault();
                    const c = $el.readerContent;
                    if (c.scrollTop + c.clientHeight >= c.scrollHeight - 5) { nextChapter(); }
                    else { scrollLines(lines); }
                    return;
                }

                if (e.key === 'ArrowUp' && e.ctrlKey) {
                    e.preventDefault();
                    adjustAutoReadSpeed(-0.25);
                    return;
                }
                if (e.key === 'ArrowDown' && e.ctrlKey) {
                    e.preventDefault();
                    adjustAutoReadSpeed(0.25);
                    return;
                }

                if (e.key === 'ArrowUp' && !matchShortcut(e, sc.scroll_up)) {
                    e.preventDefault();
                    const c = $el.readerContent;
                    if (c.scrollTop <= 5) { prevChapter(); }
                    else { scrollLines(-5); }
                    return;
                }
                if (e.key === 'ArrowDown' && !matchShortcut(e, sc.scroll_down)) {
                    e.preventDefault();
                    const c = $el.readerContent;
                    if (c.scrollTop + c.clientHeight >= c.scrollHeight - 5) { nextChapter(); }
                    else { scrollLines(5); }
                    return;
                }
            });
        }

        function setupLinkHandler() {
            $el.content.addEventListener('click', e => {
                if (e.target.tagName === 'IMG' && e.target.closest('.text')) {
                    e.preventDefault();
                    openLightbox(e.target.src);
                    return;
                }
                const link = e.target.closest('a');
                if (link && link.href) {
                    e.preventDefault();
                    e.stopPropagation();
                    const href = link.getAttribute('href') || '';
                    if (href.startsWith('#')) {
                        saveLastReadPos();
                        const parts = href.slice(1).split('#');
                        const chId = parts[0];
                        const subAnchor = parts[1] || '';
                        const target = document.getElementById(chId);
                        if (target) {
                            $el.readerContent.scrollTop = target.offsetTop - 10;
                            if (subAnchor) {
                                const sub = document.getElementById(subAnchor) || document.querySelector('[name="' + subAnchor + '"]');
                                if (sub) $el.readerContent.scrollTop = sub.offsetTop - 10;
                            }
                        } else {
                            const m = chId.match(/^ch-(\d+)$/);
                            if (m) scrollToChapter(parseInt(m[1]));
                        }
                    } else if (/\.x?html/i.test(href)) {
                        showToast('内部链接暂不支持跳转');
                    } else {
                        api().open_url_in_browser(link.href);
                    }
                }
            });
        }

        function scrollLines(n) {
            $el.readerContent.scrollTop += n * getCachedLineHeight();
        }

        function prevChapter() {
            if (currentChapter > 0) scrollToChapter(currentChapter - 1);
        }
        function nextChapter() {
            if (currentChapter < chapterCount - 1) scrollToChapter(currentChapter + 1);
        }
        function gotoChapter(i) {
            saveLastReadPos();
            scrollToChapter(i);
            toggleToc();
        }

        function showChapterTip(msg) {
            showToast(msg);
        }

        let _tocPreviewsLoaded = false;
        async function toggleToc() {
            $el.bmPanel.classList.remove('active');
            $el.tocPanel.classList.toggle('active');
            if (!$el.tocPanel.classList.contains('active')) {
                const searchInput = document.getElementById('tocSearch');
                if (searchInput) { searchInput.value = ''; filterToc(); }
            }
            if ($el.tocPanel.classList.contains('active') && !_tocPreviewsLoaded) {
                _tocPreviewsLoaded = true;
                try {
                    const previews = await api().get_chapter_previews(bookName);
                    if (previews && previews.length === chapters.length) {
                        for (let i = 0; i < chapters.length; i++) {
                            chapters[i].preview = previews[i].preview || '';
                            if (previews[i].level) chapters[i].level = previews[i].level;
                        }
                        document.getElementById('tocList').innerHTML = '';
                        renderToc();
                    }
                } catch (e) {}
            }
        }

        let _bmSortOrder = 'time-desc';
        let _bmRawData = [];

        function toggleBookmarks() {
            $el.tocPanel.classList.remove('active');
            $el.bmPanel.classList.toggle('active');
            if ($el.bmPanel.classList.contains('active')) {
                renderBookmarks();
            }
        }

        function sortBookmarks() {
            _bmSortOrder = document.getElementById('bmSortSelect').value;
            _renderSortedBookmarks();
        }

        function _renderSortedBookmarks() {
            const list = document.getElementById('bmList');
            const count = document.getElementById('bmCount');
            if (!_bmRawData || _bmRawData.length === 0) {
                count.textContent = '0个';
                document.getElementById('bmToolbar').style.display = 'none';
                list.innerHTML = '<div class="bm-empty"><span class="bm-empty-icon">🔖</span>暂无书签<br>点击上方按钮添加</div>';
                return;
            }
            document.getElementById('bmToolbar').style.display = '';
            count.textContent = _bmRawData.length + '个';

            let sorted = _bmRawData.slice();
            if (_bmSortOrder === 'time-asc') {
                sorted.sort((a, b) => (a.time || '').localeCompare(b.time || ''));
            } else if (_bmSortOrder === 'chapter-asc') {
                sorted.sort((a, b) => a.chapter - b.chapter || a.position - b.position);
            } else {
                sorted.sort((a, b) => (b.time || '').localeCompare(a.time || ''));
            }

            list.innerHTML = sorted.map(bm => {
                const ratio = bm.position != null ? bm.position : 0;
                const pct = Math.round(ratio / 100000 * 100);
                const time = bm.time || '';
                const title = bm.description || ('第' + (bm.chapter + 1) + '章');
                return '<div class="bm-item" data-bm-idx="' + bm._origIdx + '" onclick="jumpToBookmark(' + bm.chapter + ',' + ratio + ')">' +
                    '<input type="checkbox" class="bm-cb" onclick="event.stopPropagation()" data-bm-idx="' + bm._origIdx + '">' +
                    '<div class="bm-title" style="padding-left:18px;">' + escapeHtml(title) + '</div>' +
                    '<div class="bm-meta" style="padding-left:18px;">' +
                    '<span class="bm-pos">📍 ' + pct + '%</span>' +
                    '<span class="bm-time">' + escapeHtml(time) + '</span>' +
                    '</div>' +
                    '<button class="bm-edit" onclick="event.stopPropagation();startEditBookmark(' + bm._origIdx + ',this)" title="编辑">✎</button>' +
                    '<button class="bm-del" onclick="event.stopPropagation();deleteBookmark(' + bm._origIdx + ')" title="删除">✕</button>' +
                    '</div>';
            }).join('');
        }

        async function renderBookmarks() {
            const list = document.getElementById('bmList');
            const count = document.getElementById('bmCount');
            try {
                const marks = await api().get_bookmarks(bookName);
                if (!marks || marks.length === 0) {
                    _bmRawData = [];
                    count.textContent = '0个';
                    document.getElementById('bmToolbar').style.display = 'none';
                    list.innerHTML = '<div class="bm-empty"><span class="bm-empty-icon">🔖</span>暂无书签<br>点击上方按钮添加</div>';
                    return;
                }
                _bmRawData = marks.map((bm, i) => ({ ...bm, _origIdx: i }));
                _renderSortedBookmarks();
            } catch (e) {
                count.textContent = '0个';
                document.getElementById('bmToolbar').style.display = 'none';
                list.innerHTML = '<div class="bm-empty"><span class="bm-empty-icon">⚠</span>加载失败</div>';
            }
        }

        function startEditBookmark(index, btnEl) {
            const item = btnEl.closest('.bm-item');
            const titleEl = item.querySelector('.bm-title');
            const currentText = _bmRawData.find(b => b._origIdx === index);
            const desc = currentText ? (currentText.description || '') : '';
            titleEl.innerHTML = '<input type="text" class="bm-edit-input" value="' + escapeHtml(desc) + '">';
            const input = titleEl.querySelector('input');
            input.focus();
            input.select();
            const save = async () => {
                const newDesc = input.value.trim();
                if (newDesc && newDesc !== desc) {
                    try {
                        const ok = await api().update_bookmark(bookName, index, newDesc);
                        if (ok) {
                            showToast('已更新书签');
                            await renderBookmarks();
                        } else {
                            showToast('更新失败');
                            titleEl.textContent = desc;
                        }
                    } catch (e) { showToast('更新失败'); titleEl.textContent = desc; }
                } else {
                    titleEl.textContent = desc;
                }
            };
            input.addEventListener('blur', save);
            input.addEventListener('keydown', e => {
                if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
                if (e.key === 'Escape') { input.value = desc; input.blur(); }
            });
        }

        function toggleSelectAllBookmarks() {
            const cbs = document.querySelectorAll('#bmList .bm-cb');
            if (!cbs.length) return;
            const allChecked = Array.from(cbs).every(cb => cb.checked);
            cbs.forEach(cb => { cb.checked = !allChecked; cb.style.opacity = '1'; });
        }

        async function batchDeleteBookmarks() {
            const cbs = document.querySelectorAll('#bmList .bm-cb:checked');
            if (!cbs.length) { showToast('请先选择书签'); return; }
            const indices = Array.from(cbs).map(cb => parseInt(cb.dataset.bmIdx)).sort((a, b) => b - a);
            try {
                const ok = await api().remove_bookmarks(bookName, indices);
                if (ok) {
                    showToast('已删除 ' + indices.length + ' 个书签');
                    await renderBookmarks();
                } else {
                    showToast('删除失败');
                }
            } catch (e) { showToast('删除失败'); }
        }

        async function jumpToBookmark(chapter, ratio) {
            saveLastReadPos();
            toggleBookmarks();
            await scrollToChapter(chapter);
            const anchor = document.getElementById('ch-' + chapter);
            if (anchor) {
                // 使用更精确的定位方法
                const nextAnchor = document.getElementById('ch-' + (chapter + 1));
                const chapterBottom = nextAnchor ? nextAnchor.offsetTop : $el.readerContent.scrollHeight;
                const chapterHeight = chapterBottom - anchor.offsetTop;
                
                // 计算目标滚动位置
                const targetScrollTop = anchor.offsetTop + (ratio / 100000) * chapterHeight;
                
                // 使用平滑滚动到目标位置
                $el.readerContent.scrollTo({
                    top: targetScrollTop,
                    behavior: 'instant' // 使用 instant 而不是 smooth，避免动画延迟
                });
                
                currentChapter = chapter;
                renderToc();
                updateChapterInfo();
                updateProgress();
            }
        }

        async function deleteBookmark(index) {
            try {
                const ok = await api().remove_bookmark(bookName, index);
                if (ok) {
                    showToast('已删除书签');
                    renderBookmarks();
                } else {
                    showToast('删除失败');
                }
            } catch (e) { showToast('删除失败'); }
        }

        async function addBookmark() {
            try {
                const ratio = Math.round(getChapterRatio() * 100000);
                const desc = chapters[currentChapter] ? chapters[currentChapter].title : '第' + (currentChapter + 1) + '章';
                const r = await api().add_bookmark(bookName, currentChapter, ratio, desc);
                showToast(r ? '已添加书签' : '添加失败');
                if ($el.bmPanel.classList.contains('active')) {
                    renderBookmarks();
                }
            } catch (e) { showToast('添加失败'); }
        }

        function adjustAutoReadSpeed(delta) {
            let newSpeed;
            if (autoReadSpeed === 0 && delta > 0) {
                newSpeed = 1;
            } else if (autoReadSpeed === 0 && delta < 0) {
                newSpeed = -1;
            } else {
                newSpeed = Math.round((autoReadSpeed + delta) * 100) / 100;
                newSpeed = Math.max(MIN_AUTO_READ_SPEED, Math.min(MAX_AUTO_READ_SPEED, newSpeed));
            }
            if (newSpeed === autoReadSpeed) return;
            autoReadSpeed = newSpeed;
            if (autoReadSpeed === 0) {
                stopAutoReading();
                return;
            }
            const b = $el.autoReadBadge;
            b.classList.add('active');
            const dir = autoReadSpeed > 0 ? '↓' : '↑';
            b.textContent = '🤖 速度:' + autoReadSpeed + ' ' + dir + ' | Esc停止';
            if (autoReadBadgeTimer) clearTimeout(autoReadBadgeTimer);
            autoReadBadgeTimer = setTimeout(() => { b.classList.remove('active'); }, 5000);
            if (!autoReadTimer) {
                let lastTime = 0;
                function tick(now) {
                    if (autoReadSpeed === 0) { autoReadTimer = null; return; }
                    if (now - lastTime >= 25) {
                        lastTime = now;
                        const c = $el.readerContent;
                        const step = autoReadSpeed * 2;
                        if (step < 0) {
                            if (c.scrollTop <= -step) { stopAutoReading(); prevChapter(); return; }
                            c.scrollTop += step;
                        } else {
                            if (c.scrollTop >= c.scrollHeight - c.clientHeight - step) { stopAutoReading(); nextChapter(); return; }
                            c.scrollTop += step;
                        }
                        detectCurrentChapter();
                        updateProgress();
                        checkLoadMore();
                    }
                    autoReadTimer = requestAnimationFrame(tick);
                }
                autoReadTimer = requestAnimationFrame(tick);
            }
        }
        function stopAutoReading() {
            autoReadSpeed = 0;
            if (autoReadBadgeTimer) { clearTimeout(autoReadBadgeTimer); autoReadBadgeTimer = null; }
            $el.autoReadBadge.classList.remove('active');
            if (autoReadTimer) { cancelAnimationFrame(autoReadTimer); autoReadTimer = null; }
        }

        async function minimizeWindow() { try { await api().minimize_window(); } catch (e) {} }
        async function toggleMaximize() {
            try {
                const m = await api().toggle_maximize();
                const btn = document.getElementById('maxBtn');
                if (btn) btn.textContent = m ? '❐' : '□';
            } catch (e) {}
        }
        async function closeReader() {
            if (bookName) { try { await api().close_reader_window(bookName); } catch (e) {} }
        }

        async function toggleAlwaysOnTop() {
            if (!bookName) return;
            try {
                const newState = await api().toggle_reader_always_on_top(bookName);
                const btn = document.getElementById('topBtn');
                if (btn) {
                    if (newState) {
                        btn.classList.add('active');
                        btn.title = '取消置顶';
                        showToast('窗口已置顶');
                    } else {
                        btn.classList.remove('active');
                        btn.title = '置顶窗口';
                        showToast('已取消置顶');
                    }
                }
            } catch (e) {
                showToast('切换置顶失败');
            }
        }

        async function loadAlwaysOnTopState() {
            if (!bookName) return;
            try {
                const isOnTop = await api().get_reader_always_on_top(bookName);
                const btn = document.getElementById('topBtn');
                if (btn && isOnTop) {
                    btn.classList.add('active');
                    btn.title = '取消置顶';
                }
            } catch (e) {}
        }


        window.addEventListener('beforeunload', () => {
            if (bookName) {
                api().save_reader_window_geometry(bookName).catch(() => {});
            }
        });

        function setupDrag() {
            const titleBar = document.getElementById('titleBar');
            let dragging = false, lastX = 0, lastY = 0;
            let _dragThrottle = null, dx = 0, dy = 0;
            titleBar.addEventListener('mousedown', e => {
                if (e.target.closest('.win-btn')) return;
                dragging = true; isDragging = true;
                lastX = e.screenX; lastY = e.screenY;
                dx = 0; dy = 0;
                e.preventDefault();
            });
            document.addEventListener('mousemove', e => {
                if (!dragging) return;
                dx += e.screenX - lastX; dy += e.screenY - lastY;
                lastX = e.screenX; lastY = e.screenY;
                if (!_dragThrottle) {
                    _dragThrottle = requestAnimationFrame(() => {
                        if (bookName && (dx || dy)) api().move_reader_window(bookName, dx, dy);
                        dx = 0; dy = 0;
                        _dragThrottle = null;
                    });
                }
            });
            document.addEventListener('mouseup', () => {
                if (dragging) {
                    dragging = false;
                    isDragging = false;
                    if (bookName) api().save_reader_window_geometry(bookName).catch(() => {});
                }
            });
        }

        function setupResize() {
            const handle = document.getElementById('resizeHandle');
            let resizing = false, startX = 0, startY = 0, startW = 0, startH = 0;
            let _resizeThrottle = null;
            handle.addEventListener('mousedown', async e => {
                e.preventDefault(); e.stopPropagation();
                resizing = true; isResizing = true;
                startX = e.screenX; startY = e.screenY;
                const size = await api().get_reader_window_size(bookName);
                startW = size.width; startH = size.height;
            });
            document.addEventListener('mousemove', e => {
                if (!resizing) return;
                const w = Math.max(300, startW + (e.screenX - startX));
                const h = Math.max(400, startH + (e.screenY - startY));
                clearTimeout(_resizeThrottle);
                _resizeThrottle = setTimeout(() => {
                    api().resize_reader_window(bookName, w, h);
                }, 30);
            });
            document.addEventListener('mouseup', () => {
                if (resizing) {
                    resizing = false;
                    isResizing = false;
                    if (bookName) api().save_reader_window_geometry(bookName).catch(() => {});
                }
            });
        }

        let _ctxSelectedText = '';

        function setupContextMenu() {
            const menu = document.getElementById('ctxMenu');
            const content = $el.readerContent;
            content.addEventListener('contextmenu', e => {
                e.preventDefault();
                _ctxSelectedText = window.getSelection().toString().trim();
                const copyItem = document.getElementById('ctxCopy');
                const copySep = document.getElementById('ctxCopySep');
                if (_ctxSelectedText) {
                    copyItem.style.display = '';
                    copySep.style.display = '';
                } else {
                    copyItem.style.display = 'none';
                    copySep.style.display = 'none';
                }
                menu.style.left = Math.min(e.clientX, window.innerWidth - 180) + 'px';
                menu.style.top = Math.min(e.clientY, window.innerHeight - 200) + 'px';
                menu.classList.add('active');
            });
            document.addEventListener('click', e => {
                if (!menu.contains(e.target)) menu.classList.remove('active');
            });
        }

        function ctxAction(action) {
            document.getElementById('ctxMenu').classList.remove('active');
            switch (action) {
                case 'copy':
                    if (_ctxSelectedText) {
                        copyToClipboard(_ctxSelectedText);
                        _ctxSelectedText = '';
                    }
                    break;
                case 'toc': toggleToc(); break;
                case 'bm': toggleBookmarks(); break;
                case 'search': toggleSearch(); break;
                case 'autoread': adjustAutoReadSpeed(0.25); break;
                case 'bookshelf': api().show_bookshelf(); break;
                case 'reset': resetWindowSize(); break;
            }
        }

        function copyToClipboard(text) {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    showToast('已复制到剪贴板');
                }).catch(() => {
                    fallbackCopy(text);
                });
            } else {
                fallbackCopy(text);
            }
        }

        function fallbackCopy(text) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                showToast('已复制到剪贴板');
            } catch (e) {
                showToast('复制失败');
            }
            document.body.removeChild(textarea);
        }

        async function resetWindowSize() {
            try {
                await api().reset_reader_window_geometry(bookName);
                showToast('已重置窗口大小');
            } catch (e) {}
        }

        let _searchMatches = [];
        let _searchIndex = -1;
        let _fullTextResults = [];
        let _searchDebounce = null;

        function toggleSearch() {
            const bar = document.getElementById('searchBar');
            if (bar.classList.contains('active')) {
                closeSearch();
            } else {
                bar.classList.add('active');
                const input = document.getElementById('searchInput');
                input.focus();
                input.select();
            }
        }

        function closeSearch() {
            const bar = document.getElementById('searchBar');
            bar.classList.remove('active');
            clearSearchHighlights();
            document.getElementById('searchInput').value = '';
            document.getElementById('searchCount').textContent = '';
            document.getElementById('searchHint').textContent = '';
            document.getElementById('searchResults').classList.remove('active');
            document.getElementById('searchResults').innerHTML = '';
            _searchMatches = [];
            _searchIndex = -1;
            _fullTextResults = [];
        }

        function clearSearchHighlights() {
            const container = $el.content;
            container.querySelectorAll('.search-highlight').forEach(el => {
                const parent = el.parentNode;
                if (parent) {
                    while (el.firstChild) {
                        parent.insertBefore(el.firstChild, el);
                    }
                    parent.removeChild(el);
                    parent.normalize();
                }
            });
        }

        function doSearch() {
            clearTimeout(_searchDebounce);
            clearSearchHighlights();
            _searchMatches = [];
            _searchIndex = -1;
            _fullTextResults = [];

            const query = document.getElementById('searchInput').value;
            const resultsEl = document.getElementById('searchResults');
            const hintEl = document.getElementById('searchHint');

            if (!query) {
                document.getElementById('searchCount').textContent = '';
                hintEl.textContent = '';
                resultsEl.classList.remove('active');
                resultsEl.innerHTML = '';
                return;
            }

            const isFullText = document.getElementById('searchFullText').checked;
            if (isFullText) {
                hintEl.textContent = '搜索中...';
                document.getElementById('searchCount').textContent = '';
                resultsEl.classList.remove('active');
                resultsEl.innerHTML = '';
                _searchDebounce = setTimeout(() => doFullTextSearch(query), 300);
            } else {
                hintEl.textContent = '';
                resultsEl.classList.remove('active');
                resultsEl.innerHTML = '';
                doLocalSearch(query);
            }
        }

        function doLocalSearch(query) {
            const container = $el.content;
            const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
            const textNodes = [];
            while (walker.nextNode()) {
                textNodes.push(walker.currentNode);
            }

            const lowerQuery = query.toLowerCase();
            textNodes.forEach(node => {
                const text = node.textContent;
                const lowerText = text.toLowerCase();
                let pos = 0;
                const matches = [];
                while (pos < lowerText.length) {
                    const idx = lowerText.indexOf(lowerQuery, pos);
                    if (idx === -1) break;
                    matches.push(idx);
                    pos = idx + 1;
                }
                if (matches.length === 0) return;

                const parent = node.parentNode;
                const frag = document.createDocumentFragment();
                let lastEnd = 0;
                matches.forEach(start => {
                    if (start > lastEnd) {
                        frag.appendChild(document.createTextNode(text.slice(lastEnd, start)));
                    }
                    const mark = document.createElement('span');
                    mark.className = 'search-highlight';
                    mark.textContent = text.slice(start, start + query.length);
                    frag.appendChild(mark);
                    _searchMatches.push(mark);
                    lastEnd = start + query.length;
                });
                if (lastEnd < text.length) {
                    frag.appendChild(document.createTextNode(text.slice(lastEnd)));
                }
                parent.replaceChild(frag, node);
            });

            if (_searchMatches.length > 0) {
                _searchIndex = 0;
                _searchMatches[0].classList.add('current');
                scrollToSearchMatch(0);
            }
            updateSearchCount();
        }

        async function doFullTextSearch(query) {
            const resultsEl = document.getElementById('searchResults');
            const hintEl = document.getElementById('searchHint');
            const countEl = document.getElementById('searchCount');

            try {
                const result = await api().search_in_book(bookName, query, 200);
                if (!result.success) {
                    hintEl.textContent = '搜索失败';
                    return;
                }

                _fullTextResults = result.results || [];
                const total = result.total || 0;

                if (_fullTextResults.length === 0) {
                    hintEl.textContent = '无匹配';
                    countEl.textContent = '';
                    resultsEl.classList.remove('active');
                    resultsEl.innerHTML = '';
                    return;
                }

                const displayCount = _fullTextResults.length;
                const limitedText = total > displayCount ? ` (显示前${displayCount}条)` : '';
                hintEl.textContent = `共${total}处匹配${limitedText}`;
                countEl.textContent = '';

                const escapedQuery = query.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
                resultsEl.innerHTML = _fullTextResults.map((r, i) => {
                    const ctx = r.context.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
                    const highlighted = ctx.replace(new RegExp(escapedQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), m => '<mark>' + m + '</mark>');
                    const chTitle = chapters[r.chapter] ? chapters[r.chapter].title : '第' + (r.chapter + 1) + '章';
                    return '<div class="search-result-item" onclick="goToSearchResult(' + i + ')">' +
                        '<div class="search-result-chapter">' + escapeHtml(chTitle) + '</div>' +
                        '<div class="search-result-context">' + highlighted + '</div></div>';
                }).join('');
                resultsEl.classList.add('active');
            } catch (e) {
                hintEl.textContent = '搜索失败';
            }
        }

        async function goToSearchResult(index) {
            if (index < 0 || index >= _fullTextResults.length) return;
            saveLastReadPos();
            const r = _fullTextResults[index];
            const ch = r.chapter;
            const pos = r.position;

            document.getElementById('searchResults').classList.remove('active');

            await scrollToChapter(ch);
            const content = $el.content;
            const text = content.textContent;
            const query = document.getElementById('searchInput').value;

            if (query) {
                doLocalSearch(query);
                if (_searchMatches.length > 0) {
                    let bestIndex = 0;
                    let bestDist = Infinity;
                    _searchMatches.forEach((el, i) => {
                        const dist = Math.abs(el.offsetTop - 0);
                        if (dist < bestDist) {
                            bestDist = dist;
                            bestIndex = i;
                        }
                    });
                    _searchMatches.forEach(el => el.classList.remove('current'));
                    _searchIndex = bestIndex;
                    _searchMatches[_searchIndex].classList.add('current');
                    scrollToSearchMatch(_searchIndex);
                    updateSearchCount();
                }
            }
        }

        function updateSearchCount() {
            const el = document.getElementById('searchCount');
            const isFullText = document.getElementById('searchFullText').checked;
            if (isFullText) return;
            if (_searchMatches.length === 0) {
                el.textContent = document.getElementById('searchInput').value ? '无匹配' : '';
            } else {
                el.textContent = (_searchIndex + 1) + '/' + _searchMatches.length;
            }
        }

        function scrollToSearchMatch(index) {
            if (index < 0 || index >= _searchMatches.length) return;
            const el = _searchMatches[index];
            const container = $el.readerContent;
            const elTop = el.offsetTop;
            const elBottom = elTop + el.offsetHeight;
            if (elTop < container.scrollTop || elBottom > container.scrollTop + container.clientHeight) {
                container.scrollTop = elTop - container.clientHeight / 3;
            }
        }

        function searchNext() {
            if (_searchMatches.length === 0) return;
            _searchMatches[_searchIndex].classList.remove('current');
            _searchIndex = (_searchIndex + 1) % _searchMatches.length;
            _searchMatches[_searchIndex].classList.add('current');
            scrollToSearchMatch(_searchIndex);
            updateSearchCount();
        }

        function searchPrev() {
            if (_searchMatches.length === 0) return;
            _searchMatches[_searchIndex].classList.remove('current');
            _searchIndex = (_searchIndex - 1 + _searchMatches.length) % _searchMatches.length;
            _searchMatches[_searchIndex].classList.add('current');
            scrollToSearchMatch(_searchIndex);
            updateSearchCount();
        }

        // 暴露给后端 goto_bookmark 调用（后端不再拼接 JS，逻辑留在前端维护）
        window.gotoBookmark = function(chapter, position) {
            setTimeout(function() {
                scrollToChapter(chapter).then(function() {
                    jumpToBookmark(chapter, position);
                });
            }, 100);
        };

        window.addEventListener('pywebviewready', init);
