"""日志配置模块

使用 loguru 实现结构化日志
"""

import sys
from pathlib import Path

from loguru import logger

# 日志目录
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 移除默认 handler
logger.remove()

# 控制台输出（INFO 及以上）
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True,
)

# 文件输出（DEBUG 及以上）
logger.add(
    LOG_DIR / "app_{time:YYYY-MM-DD}.log",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="00:00",  # 每天零点轮转
    retention="30 days",  # 保留 30 天
    compression="zip",  # 压缩旧日志
    encoding="utf-8",
)

# 错误日志单独输出
logger.add(
    LOG_DIR / "error_{time:YYYY-MM-DD}.log",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="00:00",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
)

__all__ = ["logger"]