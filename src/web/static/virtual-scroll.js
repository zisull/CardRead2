/**
 * 虚拟滚动工具类
 * 
 * 仅渲染可见区域的元素，提升大量数据时的渲染性能。
 * 支持列表和网格两种布局模式。
 */
class VirtualScroller {
    /**
     * 创建虚拟滚动实例
     * 
     * @param {HTMLElement} container - 容器元素
     * @param {Object} options - 配置选项
     * @param {number} options.itemHeight - 每项高度（列表模式）
     * @param {number} options.itemWidth - 每项宽度（网格模式）
     * @param {number} options.itemsPerRow - 每行项目数（网格模式）
     * @param {number} options.bufferSize - 缓冲区大小（额外渲染的项目数）
     * @param {Function} options.renderItem - 渲染单个项目的函数
     * @param {Function} options.onItemClick - 点击项目的回调
     * @param {Function} options.onItemContextMenu - 右键点击项目的回调
     */
    constructor(container, options = {}) {
        this.container = container;
        this.options = {
            itemHeight: options.itemHeight || 70,
            itemWidth: options.itemWidth || 200,
            itemsPerRow: options.itemsPerRow || 1,
            bufferSize: options.bufferSize || 5,
            renderItem: options.renderItem || (() => ''),
            onItemClick: options.onItemClick || null,
            onItemContextMenu: options.onItemContextMenu || null,
        };
        
        this.items = [];
        this.visibleItems = [];
        this.startIndex = 0;
        this.endIndex = 0;
        this.scrollTop = 0;
        this.containerHeight = 0;
        this.isGrid = false;
        
        // 创建内部结构
        this._setupDOM();
        
        // 绑定事件
        this._bindEvents();
        
        // 初始化
        this._update();
    }
    
    /**
     * 设置 DOM 结构
     */
    _setupDOM() {
        // 设置容器样式
        this.container.style.overflow = 'auto';
        this.container.style.position = 'relative';
        
        // 创建滚动占位元素
        this.spacer = document.createElement('div');
        this.spacer.style.position = 'absolute';
        this.spacer.style.top = '0';
        this.spacer.style.left = '0';
        this.spacer.style.width = '1px';
        this.spacer.style.pointerEvents = 'none';
        this.container.appendChild(this.spacer);
        
        // 创建内容容器
        this.content = document.createElement('div');
        this.content.style.position = 'relative';
        this.content.style.width = '100%';
        this.container.appendChild(this.content);
    }
    
    /**
     * 绑定事件
     */
    _bindEvents() {
        // 使用 requestAnimationFrame 节流滚动事件
        let ticking = false;
        this.container.addEventListener('scroll', () => {
            if (!ticking) {
                requestAnimationFrame(() => {
                    this._onScroll();
                    ticking = false;
                });
                ticking = true;
            }
        });
        
        // 监听容器大小变化
        if (typeof ResizeObserver !== 'undefined') {
            this.resizeObserver = new ResizeObserver(() => {
                this._update();
            });
            this.resizeObserver.observe(this.container);
        }
    }
    
    /**
     * 滚动事件处理
     */
    _onScroll() {
        this.scrollTop = this.container.scrollTop;
        this._updateVisibleItems();
    }
    
    /**
     * 设置数据
     * 
     * @param {Array} items - 数据数组
     * @param {boolean} isGrid - 是否为网格模式
     */
    setItems(items, isGrid = false) {
        this.items = items || [];
        this.isGrid = isGrid;
        this._update();
    }
    
    /**
     * 更新布局
     */
    _update() {
        this.containerHeight = this.container.clientHeight;
        this._updateTotalHeight();
        this._updateVisibleItems();
    }
    
    /**
     * 更新总高度
     */
    _updateTotalHeight() {
        if (this.isGrid) {
            const rows = Math.ceil(this.items.length / this.options.itemsPerRow);
            this.totalHeight = rows * this.options.itemHeight;
        } else {
            this.totalHeight = this.items.length * this.options.itemHeight;
        }
        this.spacer.style.height = this.totalHeight + 'px';
    }
    
    /**
     * 更新可见项目
     */
    _updateVisibleItems() {
        const { itemHeight, itemsPerRow, bufferSize } = this.options;
        
        let startIndex, endIndex;
        
        if (this.isGrid) {
            const rowHeight = itemHeight;
            const startRow = Math.floor(this.scrollTop / rowHeight);
            const visibleRows = Math.ceil(this.containerHeight / rowHeight);
            const startRowWithBuffer = Math.max(0, startRow - bufferSize);
            const endRowWithBuffer = Math.min(
                Math.ceil(this.items.length / itemsPerRow),
                startRow + visibleRows + bufferSize
            );
            
            startIndex = startRowWithBuffer * itemsPerRow;
            endIndex = Math.min(this.items.length, endRowWithBuffer * itemsPerRow);
        } else {
            startIndex = Math.max(0, Math.floor(this.scrollTop / itemHeight) - bufferSize);
            endIndex = Math.min(
                this.items.length,
                Math.ceil((this.scrollTop + this.containerHeight) / itemHeight) + bufferSize
            );
        }
        
        // 只在范围变化时更新
        if (startIndex !== this.startIndex || endIndex !== this.endIndex) {
            this.startIndex = startIndex;
            this.endIndex = endIndex;
            this._render();
        }
    }
    
    /**
     * 渲染可见项目
     */
    _render() {
        const { itemHeight, itemsPerRow, renderItem, onItemClick, onItemContextMenu } = this.options;
        const fragment = document.createDocumentFragment();
        
        for (let i = this.startIndex; i < this.endIndex; i++) {
            const item = this.items[i];
            if (!item) continue;
            
            const el = renderItem(item, i);
            if (typeof el === 'string') {
                const div = document.createElement('div');
                div.innerHTML = el;
                if (!div.firstChild) continue;
                div.firstChild.style.position = 'absolute';
                
                if (this.isGrid) {
                    const row = Math.floor(i / itemsPerRow);
                    const col = i % itemsPerRow;
                    const colWidth = this.container.clientWidth / itemsPerRow;
                    div.firstChild.style.top = (row * itemHeight) + 'px';
                    div.firstChild.style.left = (col * colWidth) + 'px';
                    div.firstChild.style.width = colWidth + 'px';
                } else {
                    div.firstChild.style.top = (i * itemHeight) + 'px';
                    div.firstChild.style.left = '0';
                    div.firstChild.style.width = '100%';
                }
                
                fragment.appendChild(div.firstChild);
            } else if (el instanceof HTMLElement) {
                el.style.position = 'absolute';
                
                if (this.isGrid) {
                    const row = Math.floor(i / itemsPerRow);
                    const col = i % itemsPerRow;
                    const colWidth = this.container.clientWidth / itemsPerRow;
                    el.style.top = (row * itemHeight) + 'px';
                    el.style.left = (col * colWidth) + 'px';
                    el.style.width = colWidth + 'px';
                } else {
                    el.style.top = (i * itemHeight) + 'px';
                    el.style.left = '0';
                    el.style.width = '100%';
                }
                
                fragment.appendChild(el);
            }
        }
        
        // 清空内容容器
        this.content.innerHTML = '';
        this.content.appendChild(fragment);
        
        // 绑定事件
        this._bindItemEvents();
    }
    
    /**
     * 绑定项目事件
     */
    _bindItemEvents() {
        const { onItemClick, onItemContextMenu } = this.options;
        
        if (onItemClick) {
            this.content.querySelectorAll('[data-book-name]').forEach(el => {
                const name = el.dataset.bookName;
                el.addEventListener('dblclick', () => onItemClick(name));
            });
        }
        
        if (onItemContextMenu) {
            this.content.querySelectorAll('[data-book-name]').forEach(el => {
                const name = el.dataset.bookName;
                el.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    onItemContextMenu(e, name);
                });
            });
        }
    }
    
    /**
     * 滚动到指定项目
     * 
     * @param {number} index - 项目索引
     */
    scrollToIndex(index) {
        const { itemHeight, itemsPerRow } = this.options;
        
        if (this.isGrid) {
            const row = Math.floor(index / itemsPerRow);
            this.container.scrollTop = row * itemHeight;
        } else {
            this.container.scrollTop = index * itemHeight;
        }
    }
    
    /**
     * 刷新显示
     */
    refresh() {
        this._update();
    }
    
    /**
     * 销毁实例
     */
    destroy() {
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
        }
        this.container.innerHTML = '';
    }
}

// 导出到全局
window.VirtualScroller = VirtualScroller;
