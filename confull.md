# ConfuLL - AI 集成规范文档

[Zh](https://github.com/zisull/confull/blob/main/README.md) / [AI](https://github.com/zisull/confull/blob/main/doc/README-ai-zh.md)

> 本文档为 AI 提供精确、规范的 API 参考，确保正确使用 confull 库。

---

## 1. 快速参考

### 1.1 安装与导入

```bash
pip install confull
```

```python
from confull import Config
```

### 1.2 最小可用示例

```python
from confull import Config

# 创建/加载配置（自动推断格式）
cfg = Config('app.toml')

# 读写配置
cfg.name = 'MyApp'
cfg.set('db.host', 'localhost')

# 获取配置
name = cfg.name                    # 属性方式
host = cfg.get('db.host')         # get 方式
port = cfg('db.port', 3306)       # 调用方式（带默认值）
```

---

## 2. 构造函数

### 2.1 签名

```python
Config(
    data: dict = None,           # 初始数据
    file: str = "config",        # 文件路径（可无扩展名）
    way: str = "",               # 格式：json/toml/yaml/ini/xml（空则自动推断）
    replace: bool = False,       # 是否覆盖已有文件
    auto_save: bool = True,      # 是否自动保存
    pwd: str = None,             # 加密密码（None表示不加密）
    process_safe: bool = False,  # 是否启用进程锁
    debounce_ms: int = 0         # 自动保存去抖延迟（毫秒）
)
```

### 2.2 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `data` | dict/None | None | 初始配置数据，为None时从文件加载或创建空配置 |
| `file` | str | "config" | 配置文件路径，自动创建目录和扩展名 |
| `way` | str | "" | 格式，空字符串时从扩展名推断，无法推断默认toml |
| `replace` | bool | False | True时忽略已有文件，使用data初始化 |
| `auto_save` | bool | True | True时任何修改立即保存到文件 |
| `pwd` | str/None | None | 非空时启用Fernet加密 |
| `process_safe` | bool | False | True时使用portalocker进程锁 |
| `debounce_ms` | int | 0 | >0时延迟保存，减少频繁IO |

### 2.3 格式推断规则

```
1. way 显式指定 → 使用指定格式
2. way 为空 + 扩展名可识别 → 使用扩展名对应格式
3. way 为空 + 扩展名无法识别 → 默认 toml
4. way 为空 + 无扩展名 → 默认 toml，添加 .toml 扩展名
```

### 2.4 常见构造方式

```python
# 空配置（默认文件 config.toml）
cfg = Config()

# 指定文件（自动推断格式）
cfg = Config('app.toml')
cfg = Config('app.json')
cfg = Config('app.yaml')

# 使用 txt 扩展名但 toml 格式
cfg = Config('config.txt', way='toml')

# 带初始数据
cfg = Config({'name': 'app', 'version': '1.0'}, file='app.toml')

# 加密配置
cfg = Config('secure.toml', pwd='my-secret-key')

# 去抖保存（100ms内只保存一次）
cfg = Config('app.toml', debounce_ms=100)
```

---

## 3. 数据访问 API

### 3.1 三种访问方式

```python
cfg = Config({'db': {'host': 'localhost', 'port': 3306}})

# 方式1：属性访问
cfg.db.host              # 'localhost'
cfg.db.port              # 3306

# 方式2：字典访问（支持点路径）
cfg['db']['host']        # 'localhost'
cfg['db.host']           # 'localhost'（点路径）

# 方式3：get/set 方法（推荐用于动态键名）
cfg.get('db.host')       # 'localhost'
cfg.set('db.host', '127.0.0.1')
```

### 3.2 获取值

```python
# get 方法
get(key: str, default: Any = None) -> Any

# 示例
cfg.get('db.host')              # 'localhost'
cfg.get('db.user', 'root')      # 'root'（不存在时返回默认值）
cfg.get('missing')              # None（不存在时返回None）

# 调用方式（等价于get）
cfg('db.host')                  # 'localhost'
cfg('db.user', 'root')          # 'root'
```

### 3.3 设置值

```python
# set 方法
set(key: str, value: Any, overwrite_mode: bool = False) -> Config

# 示例
cfg.set('db.host', 'localhost')           # 设置值
cfg.set('db.host', '127.0.0.1')           # 覆盖值
cfg.set('new.key', 'value')               # 自动创建中间节点

# 链式操作（set返回self）
cfg.set('db.host', 'localhost').set('db.port', 3306).set('db.user', 'root')
```

### 3.4 overwrite_mode 说明

当路径存在但类型冲突时，需要 `overwrite_mode=True`：

```python
cfg = Config()

# 叶子 -> 字典（冲突）
cfg.set('x', 1)
cfg.set('x.y', 2)                           # ❌ KeyError
cfg.set('x.y', 2, overwrite_mode=True)      # ✅ 覆盖

# 字典 -> 叶子（冲突）
cfg.set('a', {'b': 1})
cfg.set('a', 99)                            # ❌ ValueError
cfg.set('a', 99, overwrite_mode=True)       # ✅ 覆盖
```

---

## 4. 便捷方法

### 4.1 setdefault - 设置默认值

```python
setdefault(key: str, value: Any) -> Any

# 仅在键不存在时设置，返回最终值
cfg = Config({'version': '1.0'})

cfg.setdefault('version', '2.0')    # 返回 '1.0'（已存在，不覆盖）
cfg.setdefault('name', 'MyApp')     # 返回 'MyApp'（不存在，设置）
```

### 4.2 first - 获取第一个存在的键

```python
first(*keys, default=None) -> Any

# 按优先级查找，返回第一个存在且非None的值
cfg = Config({'host': 'localhost', 'server_host': '127.0.0.1'})

cfg.first('server_host', 'host')              # '127.0.0.1'
cfg.first('missing', 'host')                  # 'localhost'
cfg.first('a', 'b', 'c', default='none')      # 'none'（都不存在）
```

### 4.3 require - 获取必需配置

```python
require(key: str) -> Any

# 不存在时抛出 KeyError（包含友好错误信息）
cfg = Config({'db_url': 'sqlite:///db.sqlite'})

cfg.require('db_url')       # 'sqlite:///db.sqlite'
cfg.require('api_key')      # ❌ KeyError: "必需的配置项 'api_key' 不存在或值为 None"
```

---

## 5. 批量操作

### 5.1 update - 批量更新

```python
update(data: Dict[str, Any]) -> None

# 支持点路径键名
cfg.update({
    'db.host': 'localhost',
    'db.port': 3306,
    'debug': True
})
```

### 5.2 set_data - 完全替换

```python
set_data(data: Dict[str, Any]) -> None

# 替换所有配置数据
cfg.set_data({'new_key': 'new_value'})
# 旧数据完全丢失
```

### 5.3 merge - 合并配置

```python
merge(other: Union[Dict, Config], strategy: str = "override") -> Config

# 策略说明：
# - 'override': 覆盖已有值（默认）
# - 'keep': 保留已有值
# - 'deep': 深度合并嵌套字典

cfg = Config({'db': {'host': 'localhost', 'port': 3306}})

# override（覆盖）
cfg.merge({'db': {'host': '127.0.0.1'}, 'debug': True})
# 结果: {'db': {'host': '127.0.0.1'}, 'debug': True}

# keep（保留）
cfg.merge({'db': {'host': '127.0.0.1'}, 'debug': True}, strategy='keep')
# 结果: {'db': {'host': 'localhost', 'port': 3306}, 'debug': True}

# deep（深度合并）
cfg.merge({'db': {'user': 'root'}, 'debug': True}, strategy='deep')
# 结果: {'db': {'host': 'localhost', 'port': 3306, 'user': 'root'}, 'debug': True}
```

---

## 6. 删除操作

### 6.1 del_key - 删除指定键

```python
del_key(key: str) -> None

# 支持点路径，自动清理空的父节点
cfg = Config({'a': {'b': {'c': 1, 'd': 2}}, 'e': 3})

cfg.del_key('a.b.c')
# 结果: {'a': {'b': {'d': 2}}, 'e': 3}

cfg.del_key('a.b.d')
# 结果: {'e': 3}（自动清理空的 'a' 和 'b'）
```

### 6.2 del_clean - 清空配置

```python
del_clean() -> bool

# 清空内存数据并删除配置文件
cfg = Config({'x': 1}, file='app.toml')
cfg.del_clean()
# 返回 True，文件被删除
```

---

## 7. 文件操作

### 7.1 save - 保存

```python
save() -> None

# 立即保存（忽略去抖延迟）
cfg = Config('app.toml', auto_save=False)
cfg.name = 'app'
cfg.save()  # 手动保存
```

### 7.2 reload - 重新加载

```python
reload() -> None

# 从磁盘重新加载（丢弃未保存的更改）
cfg = Config('app.toml')
# 外部修改了 app.toml
cfg.reload()
```

### 7.3 to_file - 另存为

```python
to_file(file: str = None, way: str = None) -> None

# 保存到其他文件/格式
cfg = Config('app.toml')
cfg.to_file('backup.json', way='json')
cfg.to_file('backup.yaml', way='yaml')
```

### 7.4 文件监听

```python
enable_watch() -> None
disable_watch() -> None

# 开启监听（外部修改后自动重载）
cfg = Config('config.toml')
cfg.enable_watch()

# 关闭监听（建议在程序退出前调用）
cfg.disable_watch()
```

---

## 8. 导入导出

### 8.1 to_dict - 导出为字典

```python
to_dict() -> Dict[str, Any]

# 返回深拷贝的原生字典
cfg = Config({'db': {'host': 'localhost'}})
data = cfg.to_dict()
# {'db': {'host': 'localhost'}}
```

### 8.2 to_json - 导出为JSON

```python
to_json(indent: int = 2) -> str

# 返回JSON字符串
cfg = Config({'name': 'app'})
cfg.to_json()          # '{\n  "name": "app"\n}'
cfg.to_json(indent=4)  # 更多缩进
```

### 8.3 to_env - 导出为环境变量

```python
to_env(prefix: str = "", uppercase: bool = True) -> Dict[str, str]

# 嵌套键用下划线连接
cfg = Config({'db': {'host': 'localhost', 'port': 3306}})

cfg.to_env()                    # {'DB_HOST': 'localhost', 'DB_PORT': '3306'}
cfg.to_env(prefix='APP')        # {'APP_DB_HOST': 'localhost', 'APP_DB_PORT': '3306'}
cfg.to_env(uppercase=False)     # {'db_host': 'localhost', 'db_port': '3306'}
```

### 8.4 from_env - 从环境变量导入

```python
from_env(prefix: str = "", separator: str = "_") -> Config

import os
os.environ['APP_DB_HOST'] = 'localhost'
os.environ['APP_DB_PORT'] = '3306'

cfg = Config()
cfg.from_env(prefix='APP')
# cfg.db.host = 'localhost'
# cfg.db.port = '3306'
```

---

## 9. 比较操作

### 9.1 diff - 比较差异

```python
diff(other: Union[Dict, Config]) -> Dict[str, Any]

# 返回包含 added/removed/modified 的字典
cfg1 = Config({'a': 1, 'b': 2, 'c': 3})
cfg2 = Config({'a': 1, 'b': 99, 'd': 4})

diff = cfg1.diff(cfg2)
# {
#     'added': {'d': 4},
#     'removed': {'c': 3},
#     'modified': {'b': {'old': 2, 'new': 99}}
# }
```

---

## 10. 安全访问接口

### 10.1 opt 属性

当配置键名与 Config 方法名冲突时，使用 `opt` 访问：

```python
# 保留关键字列表
# to_dict, to_json, save, load, reload, get, set, del_clean, opt

cfg = Config({'save': True, 'path': '/tmp'})

# ❌ 错误：调用的是 save() 方法
# cfg.save

# ✅ 正确：使用 opt 访问
cfg.opt.save        # True
cfg.opt.path        # '/tmp'
cfg.opt.path = '/var'  # 修改
```

---

## 11. 魔法方法

### 11.1 支持的操作

```python
cfg = Config({'a': 1, 'b': {'c': 2}})

# 属性访问
cfg.a               # 1
cfg.b.c             # 2

# 字典访问
cfg['a']            # 1
cfg['b.c']          # 2（支持点路径）

# 删除
del cfg.a
del cfg['b.c']

# 长度
len(cfg)            # 1（删除a后）

# 迭代
for key in cfg:
    print(key)

# 包含判断
'a' in cfg          # False
'b.c' in cfg        # True（支持点路径）

# 布尔值
bool(cfg)           # True（非空）

# 调用方式（等价于get）
cfg('b.c')          # 2
cfg('missing', 0)   # 0（带默认值）
```

### 11.2 上下文管理器

```python
# 退出时自动保存
with Config('app.toml', auto_save=False) as cfg:
    cfg.name = 'app'
    cfg.version = '1.0'
# 退出时自动调用 save()
```

---

## 12. 属性信息

### 12.1 path / path_abs

```python
path() -> str       # 返回相对路径
path_abs() -> str   # 返回绝对路径

cfg = Config('app.toml')
cfg.path()          # 'app.toml'
cfg.path_abs()      # '/absolute/path/to/app.toml'
```

### 12.2 is_auto_save / set_auto_save

```python
is_auto_save() -> bool
set_auto_save(flag: bool) -> None

cfg.is_auto_save()          # True
cfg.set_auto_save(False)    # 关闭自动保存
cfg.is_auto_save()          # False
```

---

## 13. 错误处理

### 13.1 常见异常

| 异常类型 | 原因 | 解决方案 |
|----------|------|----------|
| `KeyError` | 路径不存在 | 检查键名，或使用 `get` 提供默认值 |
| `KeyError` | overwrite_mode=False 时类型冲突 | 设置 `overwrite_mode=True` |
| `ValueError` | 加密文件密码错误 | 使用正确密码 |
| `ValueError` | 加密文件被篡改 | 使用正确密码重新加载 |
| `AttributeError` | 键名与保留关键字冲突 | 使用 `opt` 属性访问 |

### 13.2 错误信息增强

```python
# KeyError 时会提示解决方案
cfg = Config({'a': 1})
cfg['b']
# KeyError: "路径 'b' 不存在。提示：可使用 get('b', default) 提供默认值，或使用 set('b', value) 创建该配置项。"
```

---

## 14. 线程与进程安全

### 14.1 线程安全

- Config 内部使用 RLock，线程安全
- 多线程同时读写是安全的

### 14.2 进程安全

```python
# 启用进程锁（多进程场景）
cfg = Config('shared.toml', process_safe=True)

# 关闭进程锁（单进程高性能场景）
cfg = Config('app.toml', process_safe=False)
```

---

## 15. 最佳实践

### 15.1 批量操作

```python
# ✅ 推荐：关闭自动保存，批量操作后手动保存
with Config('app.toml', auto_save=False) as cfg:
    for i in range(100):
        cfg.set(f'item.{i}', f'value_{i}')
# 退出时自动保存

# ❌ 避免：频繁自动保存
cfg = Config('app.toml')  # auto_save=True 默认
for i in range(100):
    cfg.set(f'item.{i}', f'value_{i}')  # 每次都保存
```

### 15.2 去抖延迟

```python
# 高频写入场景
cfg = Config('app.toml', debounce_ms=100)
# 100ms 内多次写入只保存一次
```

### 15.3 配置合并

```python
# 默认配置 + 用户配置
default = Config('default.toml')
user = Config('user.toml')
default.merge(user, strategy='deep')
```

### 15.4 环境变量覆盖

```python
# 基础配置 + 环境变量覆盖
cfg = Config('app.toml')
cfg.from_env(prefix='APP')
```

### 15.5 安全访问冲突键

```python
# ❌ 错误
cfg = Config({'save': True})
cfg.save  # 调用的是 save() 方法

# ✅ 正确
cfg.opt.save  # 访问 'save' 配置项
```

---

## 16. API 速查表

### 构造

| 方法 | 说明 |
|------|------|
| `Config(data, file, way, ...)` | 创建配置管理器 |

### 读写

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `get(key, default)` | 获取值 | 值或默认值 |
| `set(key, value, overwrite_mode)` | 设置值 | Config（链式） |
| `setdefault(key, value)` | 设置默认值 | 最终值 |
| `first(*keys, default)` | 第一个存在的键 | 值或默认值 |
| `require(key)` | 必需配置 | 值或抛异常 |

### 批量

| 方法 | 说明 |
|------|------|
| `update(dict)` | 批量更新 |
| `set_data(dict)` | 完全替换 |
| `merge(other, strategy)` | 合并配置 |

### 删除

| 方法 | 说明 |
|------|------|
| `del_key(key)` | 删除键（支持点路径） |
| `del_clean()` | 清空并删除文件 |

### 文件

| 方法 | 说明 |
|------|------|
| `save()` | 保存 |
| `reload()` | 重新加载 |
| `to_file(file, way)` | 另存为 |
| `enable_watch()` | 开启监听 |
| `disable_watch()` | 关闭监听 |

### 导入导出

| 方法 | 说明 |
|------|------|
| `to_dict()` | 导出为字典 |
| `to_json(indent)` | 导出为JSON |
| `to_env(prefix, uppercase)` | 导出为环境变量 |
| `from_env(prefix, separator)` | 从环境变量导入 |

### 比较

| 方法 | 说明 |
|------|------|
| `diff(other)` | 比较差异 |

### 状态

| 方法 | 说明 |
|------|------|
| `path()` | 相对路径 |
| `path_abs()` | 绝对路径 |
| `is_auto_save()` | 是否自动保存 |
| `set_auto_save(flag)` | 设置自动保存 |

---

## 17. 注意事项清单

1. **保留关键字**：`to_dict`, `to_json`, `save`, `load`, `reload`, `get`, `set`, `del_clean`, `opt` 不能作为顶层键名
2. **类型冲突**：叶子节点和字典节点冲突时需要 `overwrite_mode=True`
3. **加密不可逆**：忘记密码无法恢复数据
4. **watchdog**：建议在程序退出前调用 `disable_watch()`
5. **自动保存**：默认开启，批量操作建议关闭
6. **点路径**：支持 `a.b.c` 格式的嵌套访问
7. **链式操作**：`set` 方法返回 `self`，支持链式调用
8. **深拷贝**：`to_dict()` 返回深拷贝，修改不影响原配置
