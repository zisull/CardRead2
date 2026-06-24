"""pywebview 入口文件

使用 pywebview 启动 CardRead 阅读器。
"""
import atexit
import os
import shutil
import sys
import tempfile
import time

# 进程状态常量
PROCESS_QUERY_LIMITED_INFORMATION = 0x0400
STILL_ACTIVE = 259

# 日志 rotation 大小
LOG_ROTATION_SIZE = "1 MB"
ERROR_LOG_ROTATION_SIZE = "512 KB"


def _get_file_this():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def _detect_nuitka():
    return '__compiled__' in globals()


def _setup_dll_paths():
    base = _get_file_this()
    dll_dirs = []
    for candidate in (
        os.path.join(base, 'pythonnet', 'runtime'),
        os.path.join(base, 'pythonnet'),
        base,
    ):
        if os.path.isfile(os.path.join(candidate, 'Python.Runtime.dll')):
            dll_dirs.append(candidate)
    for candidate in (
        os.path.join(base, 'clr_loader', 'ffi', 'dlls'),
        os.path.join(base, 'clr_loader', 'ffi', 'dlls', 'amd64'),
    ):
        if os.path.isdir(candidate):
            dll_dirs.append(candidate)
    for d in dll_dirs:
        os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(d)


_is_nuitka = _detect_nuitka()
_setup_dll_paths()

import webview
from loguru import logger

from src.config import APP_DISPLAY_NAME, APP_VERSION, MAIN_WINDOW_HEIGHT
from src.utils.file_utils import get_appdata_dir, get_bundle_base_path
from src.web.api import Api, AVAILABLE_LAYOUTS


_BASE_PATH = get_bundle_base_path(__file__)
_LOCK_FILE = os.path.join(tempfile.gettempdir(), 'cardread2.lock')
_lock_file_descriptor = None  # 用于存储文件描述符，以便在进程退出时关闭


def _is_process_running(pid: int) -> bool:
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)  # type: ignore[attr-defined]
            if handle:
                exit_code = ctypes.c_ulong()
                kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))  # type: ignore[attr-defined]
                kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                return exit_code.value == STILL_ACTIVE
        except Exception:
            pass
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def _check_single_instance() -> bool:
    """检查是否已有实例运行，使用文件锁确保原子性。
    
    Returns:
        True 如果是第一个实例，False 如果已有实例运行
    """
    try:
        # 使用文件锁确保原子性
        if sys.platform == 'win32':
            return _check_single_instance_windows()
        else:
            return _check_single_instance_unix()
    except Exception as e:
        # 如果文件锁失败，回退到简单的 PID 检查
        logger.warning(f"文件锁失败，回退到PID检查: {e}")
        return _check_single_instance_fallback()


def _check_single_instance_windows() -> bool:
    """Windows 平台单实例检测，使用 msvcrt.locking()"""
    import msvcrt
    
    global _lock_file_descriptor
    lock_file = _LOCK_FILE + '.lock'
    try:
        # 尝试创建或打开锁文件
        fd = os.open(lock_file, os.O_CREAT | os.O_RDWR)
        try:
            # 尝试获取排他锁
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            # 锁获取成功，检查 PID 文件
            result = _check_pid_file()
            if result:
                # 将当前 PID 写入锁文件（用于调试）
                os.write(fd, str(os.getpid()).encode())
                # 保持文件描述符打开，以便锁一直持有
                _lock_file_descriptor = fd
            else:
                # 如果检查失败，关闭文件描述符
                os.close(fd)
            return result
        except OSError:
            # 无法获取锁，已有实例运行
            os.close(fd)
            return False
    except OSError:
        return False


def _check_single_instance_unix() -> bool:
    """Unix 平台单实例检测，使用 fcntl.flock()"""
    import fcntl
    
    global _lock_file_descriptor
    lock_file = _LOCK_FILE + '.lock'
    try:
        fd = open(lock_file, 'w')
        try:
            # 尝试获取排他锁（非阻塞）
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # 锁获取成功，检查 PID 文件
            result = _check_pid_file()
            if result:
                # 将当前 PID 写入锁文件（用于调试）
                fd.write(str(os.getpid()))
                fd.flush()
                # 保持文件描述符打开，以便锁一直持有
                _lock_file_descriptor = fd
            else:
                # 如果检查失败，关闭文件描述符
                fd.close()
            return result
        except (IOError, OSError):
            # 无法获取锁，已有实例运行
            fd.close()
            return False
    except OSError:
        return False


def _check_pid_file() -> bool:
    """检查 PID 文件，判断是否有实例运行"""
    try:
        if os.path.exists(_LOCK_FILE):
            with open(_LOCK_FILE, 'r') as f:
                old_pid = f.read().strip()
            if old_pid.isdigit() and _is_process_running(int(old_pid)):
                return False
            os.remove(_LOCK_FILE)
        with open(_LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except OSError:
        try:
            os.remove(_LOCK_FILE)
        except OSError:
            return False
        try:
            with open(_LOCK_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except OSError:
            return False
        return True


def _check_single_instance_fallback() -> bool:
    """回退方案：简单的 PID 检查（存在竞态条件）"""
    try:
        if os.path.exists(_LOCK_FILE):
            with open(_LOCK_FILE, 'r') as f:
                old_pid = f.read().strip()
            if old_pid.isdigit() and _is_process_running(int(old_pid)):
                return False
            os.remove(_LOCK_FILE)
        with open(_LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except OSError:
        try:
            os.remove(_LOCK_FILE)
        except OSError:
            return False
        try:
            with open(_LOCK_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except OSError:
            return False
        return True


def _release_lock():
    """释放单实例锁文件。

    删除前校验锁文件内记录的 PID 是否等于当前进程 PID，
    避免 reset_app 启动新进程后，旧进程退出时误删新进程的锁文件。
    同时释放文件锁。
    """
    # 释放文件锁
    _release_file_lock()
    
    # 释放 PID 文件
    try:
        if not os.path.exists(_LOCK_FILE):
            return
        with open(_LOCK_FILE, 'r') as f:
            lock_pid_str = f.read().strip()
        # 仅当锁文件内 PID == 当前 PID 时才删除
        if lock_pid_str.isdigit() and int(lock_pid_str) == os.getpid():
            os.remove(_LOCK_FILE)
    except OSError:
        pass


def _release_file_lock():
    """释放文件锁"""
    global _lock_file_descriptor
    try:
        # 关闭文件描述符（如果存在）
        if _lock_file_descriptor is not None:
            try:
                os.close(_lock_file_descriptor)
            except OSError:
                pass
            _lock_file_descriptor = None
        
        # 删除锁文件
        lock_file = _LOCK_FILE + '.lock'
        if os.path.exists(lock_file):
            os.remove(lock_file)
    except OSError:
        pass


def setup_logging():
    log_dir = get_appdata_dir()
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'cardread_web.log')
        error_log_file = os.path.join(log_dir, 'cardread_error.log')

        logger.remove()
        logger.add(log_file, rotation=LOG_ROTATION_SIZE, retention="7 days", encoding="utf-8", level="DEBUG")
        logger.add(error_log_file, rotation=ERROR_LOG_ROTATION_SIZE, retention="30 days", encoding="utf-8", level="ERROR")
        if sys.stderr is not None:
            logger.add(sys.stderr, level="INFO")
    except Exception:
        logger.remove()
        if sys.stderr is not None:
            logger.add(sys.stderr, level="INFO")


_SHARED_FILES = ['common.css', 'common.js', 'utils.js']


def _distribute_shared_files():
    """保留向后兼容，扁平化结构后实际为空操作"""
    pass


def get_html_path(layout: str = 'nautical'):
    if layout not in AVAILABLE_LAYOUTS:
        layout = 'nautical'
    # 扁平化结构：所有文件在 static/ 目录，layout 独特文件命名为 layout.html/css/js
    path = os.path.join(_BASE_PATH, 'static', f'{layout}.html')
    if not os.path.isfile(path):
        path = os.path.join(_BASE_PATH, 'static', 'nautical.html')
    if not os.path.isfile(path):
        path = os.path.join(_BASE_PATH, 'static', 'index.html')
    return path


def _cleanup_temp_files():
    """清理残留的临时文件"""
    try:
        from src.utils.file_utils import get_appdata_dir
        books_dir = os.path.join(get_appdata_dir(), 'books')
        if not os.path.isdir(books_dir):
            return
        
        # 清理以 _drag_tmp_ 开头的临时文件
        for filename in os.listdir(books_dir):
            if filename.startswith('_drag_tmp_'):
                filepath = os.path.join(books_dir, filename)
                try:
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                        logger.debug(f"清理临时文件: {filepath}")
                except OSError as e:
                    logger.warning(f"清理临时文件失败: {filepath}, {e}")
    except Exception as e:
        logger.warning(f"清理临时文件时出错: {e}")


def main():
    if not _check_single_instance():
        logger.warning("检测到已有实例运行，退出")
        return

    # 注册清理函数，确保进程退出时释放文件锁
    atexit.register(_release_file_lock)

    setup_logging()
    
    # 清理残留的临时文件
    _cleanup_temp_files()
    # 扁平化结构后不再需要分发共享文件，所有文件已在 static/ 同一目录
    _is_pyinstaller = getattr(sys, 'frozen', False)
    _mode = 'Nuitka' if _is_nuitka else ('PyInstaller' if _is_pyinstaller else '源码')
    logger.info(f"启动 | v{APP_VERSION} | {_mode}")
    
    api = Api()

    layout = api.get_home_layout()
    html_path = get_html_path(layout)
    logger.info(f"布局: {layout}")
    
    if not os.path.isfile(html_path):
        logger.error(f"HTML文件不存在: {html_path}")
    
    window = webview.create_window(
        title=f'{APP_DISPLAY_NAME} v{APP_VERSION}',
        url=html_path,
        js_api=api,
        width=1200,
        height=MAIN_WINDOW_HEIGHT,
        min_size=(900, 650),
        resizable=True,
        text_select=True,
        frameless=True,
        easy_drag=False,
        background_color='#0c0c14'
    )
    
    api._window = window

    try:
        webview.start(debug=False)
    except Exception as e:
        logger.error(f"webview启动失败: {e}")
        raise
    finally:
        api.close_all_note_windows()
        for name in list(api._data_store.get_active_sessions().keys()):
            api._data_store.stop_reading_session(name)
        api._save_immediate()
        # 关闭搜索索引连接，防止资源泄漏
        if hasattr(api, '_search_index') and api._search_index:
            api._search_index.close()
        _release_lock()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        _crash_log = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Cardread Pro', 'crash.log')
        try:
            os.makedirs(os.path.dirname(_crash_log), exist_ok=True)
            with open(_crash_log, 'w', encoding='utf-8') as f:
                traceback.print_exc(file=f)
        except OSError:
            pass
        raise


