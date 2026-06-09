"""Redis 异步客户端 — 可选，不可用时降级为纯 DB 模式"""

import redis.asyncio as aioredis
from app.config import config
from loguru import logger

_redis_pool = None
_redis_available = None


async def get_redis():
    """获取 Redis 连接，不可用时返回 None"""
    global _redis_pool, _redis_available

    if _redis_available is False:
        return None

    if _redis_pool is None:
        try:
            url = f"redis://{config.redis_host}:{config.redis_port}/{config.redis_db}"
            _redis_pool = aioredis.ConnectionPool.from_url(
                url,
                password=config.redis_password or None,
                max_connections=20,
            )
            r = aioredis.Redis(connection_pool=_redis_pool)
            await r.ping()
            _redis_available = True
            logger.info("Redis 连接成功")
        except Exception as e:
            _redis_available = False
            _redis_pool = None
            logger.warning(f"Redis 不可用，会话缓存将仅使用数据库: {e}")
            return None

    try:
        return aioredis.Redis(connection_pool=_redis_pool)
    except Exception:
        return None


def is_redis_available() -> bool:
    return _redis_available is True
