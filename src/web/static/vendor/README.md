# highlight.js 本地化文件

本目录存放 highlight.js v11.9.0 的本地副本，替代外部 CDN 引用。

## 需要下载的文件

从 https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/ 下载以下文件：

### 主文件
- `highlight.min.js` → 放在本目录下

### 主题样式（Atom One Dark，匹配深色代码块背景 #282c34）
- `styles/atom-one-dark.min.css` → 保存为 `highlight.styles/default.min.css`

### 语言支持
以下文件放在 `languages/` 子目录下：
- `languages/python.min.js`
- `languages/javascript.min.js`
- `languages/bash.min.js`
- `languages/json.min.js`
- `languages/html.min.js`（实际为 cdnjs 上的 `xml.min.js`）
- `languages/css.min.js`
- `languages/markdown.min.js`

## 目录结构

```
vendor/
├── README.md
├── highlight.min.js
├── highlight.styles/
│   └── default.min.css
└── languages/
    ├── python.min.js
    ├── javascript.min.js
    ├── bash.min.js
    ├── json.min.js
    ├── html.min.js
    ├── css.min.js
    └── markdown.min.js
```

## 下载方式

可以使用以下 PowerShell 命令批量下载：

```powershell
$base = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0"
$vendorDir = "src/web/static/vendor"

Invoke-WebRequest -Uri "$base/highlight.min.js" -OutFile "$vendorDir/highlight.min.js"
Invoke-WebRequest -Uri "$base/styles/atom-one-dark.min.css" -OutFile "$vendorDir/highlight.styles/default.min.css"

$langs = @("python", "javascript", "bash", "json", "html", "css", "markdown")
foreach ($lang in $langs) {
    Invoke-WebRequest -Uri "$base/languages/$lang.min.js" -OutFile "$vendorDir/languages/$lang.min.js"
}
```
