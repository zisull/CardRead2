"""文件操作工具模块

提供路径处理、目录管理等通用文件操作功能。
"""
import os
import sys
from pathlib import Path


def get_bundle_base_path(caller_file: str) -> str:
    """获取打包资源的基础路径。

    - PyInstaller onefile: sys._MEIPASS（临时解压目录）
    - Nuitka / 源码运行: 入口模块（__main__）所在目录

    Args:
        caller_file: 调用方模块的 __file__ 值（仅作为最终回退）

    Returns:
        资源基础目录的绝对路径
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    main_module = sys.modules.get('__main__')
    if main_module and getattr(main_module, '__file__', None):
        return str(Path(main_module.__file__).resolve().parent)
    return str(Path(caller_file).resolve().parent)


def get_appdata_dir() -> str:
    """获取AppData目录下的Cardread Pro目录

    Returns:
        Cardread Pro目录路径
    """
    appdata = os.environ.get('APPDATA', str(Path.home()))
    return str(Path(appdata) / 'Cardread Pro')


def get_resource_dirs(base_dir: str) -> dict:
    """获取资源目录结构

    Args:
        base_dir: 基础目录路径

    Returns:
        包含各资源目录路径的字典
    """
    style_dir = str(Path(base_dir) / "style")

    dirs = {
        'base': base_dir,
        'style': style_dir,
        'fonts': str(Path(style_dir) / "fonts"),
        'books': str(Path(style_dir) / "books"),
        'imgs': str(Path(style_dir) / "imgs"),
        'theme': str(Path(style_dir) / "theme"),
    }

    return dirs


def ensure_dirs_exist(dirs: dict) -> None:
    """确保目录存在，不存在则创建

    Args:
        dirs: 目录路径字典
    """
    for dir_path in dirs.values():
        os.makedirs(dir_path, exist_ok=True)
