"""装饰器工具模块

提供通用的装饰器，用于统一处理异常、日志等。
"""
import functools
from typing import Any, Callable, TypeVar

from loguru import logger

F = TypeVar('F', bound=Callable[..., Any])


def handle_api_error(default_return: Any = None, error_message: str = "操作失败") -> Callable[[F], F]:
    """API 错误处理装饰器
    
    统一处理 API 方法中的异常，记录日志并返回默认值。
    
    Args:
        default_return: 异常时的默认返回值
        error_message: 错误日志消息前缀
        
    Returns:
        装饰器函数
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                method_name = func.__name__
                logger.error(f"{error_message} [{method_name}]: {type(e).__name__}: {e}")
                if isinstance(default_return, dict):
                    return {**default_return, 'error': str(e)}
                return default_return
        return wrapper
    return decorator


def log_method_call(level: str = "DEBUG") -> Callable[[F], F]:
    """方法调用日志装饰器
    
    记录方法的调用和返回。
    
    Args:
        level: 日志级别
        
    Returns:
        装饰器函数
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            method_name = func.__name__
            logger.log(level, f"调用 {method_name}")
            result = func(*args, **kwargs)
            logger.log(level, f"{method_name} 完成")
            return result
        return wrapper
    return decorator


def require_window(func: F) -> F:
    """要求窗口已初始化的装饰器
    
    检查 self._window 是否已初始化。
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self._window:
            logger.warning(f"窗口未初始化，无法执行 {func.__name__}")
            return None
        return func(self, *args, **kwargs)
    return wrapper
