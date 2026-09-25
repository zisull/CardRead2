"""loguru 日志配置（单一来源）

启动时与「清空日志」后重建 handler 都走这里，避免两处配置漂移。
"""
import os
import sys

from loguru import logger

LOG_ROTATION_SIZE = "1 MB"
ERROR_LOG_ROTATION_SIZE = "512 KB"
LOG_FILE_NAME = "cardread_web.log"
ERROR_LOG_FILE_NAME = "cardread_error.log"


def configure_logging(log_dir: str) -> None:
    """按统一配置重建全部 loguru handler（幂等，可重复调用）

    Args:
        log_dir: 日志目录，不存在时会创建
    """
    logger.remove()
    try:
        os.makedirs(log_dir, exist_ok=True)
        logger.add(os.path.join(log_dir, LOG_FILE_NAME),
                   rotation=LOG_ROTATION_SIZE, retention="7 days",
                   encoding="utf-8", level="DEBUG")
        logger.add(os.path.join(log_dir, ERROR_LOG_FILE_NAME),
                   rotation=ERROR_LOG_ROTATION_SIZE, retention="30 days",
                   encoding="utf-8", level="ERROR")
    except Exception:
        pass
    if sys.stderr is not None:
        logger.add(sys.stderr, level="INFO")
