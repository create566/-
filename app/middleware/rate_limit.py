"""
滑动窗口限流中间件

基于内存的滑动窗口算法，按「客户端IP + 请求路径」维度限流：
- 窗口内请求数超过阈值 → 返回 429 + Retry-After
- 公开端点（/health、/metrics、/docs 等）不限流
- 过期窗口惰性清理，防止内存泄漏

生产注意：
    本实现为单机内存版（多 worker/多实例部署时需替换为
    集中式存储如 Redis + Lua 脚本实现原子限流），代码结构已
    预留 Limiter 抽象，替换存储层不影响中间件接口。
"""

import threading
import time
from collections import defaultdict, deque
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class SlidingWindowLimiter:
    """滑动窗口限流器 — 线程安全"""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: defaultdict = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        """判断请求是否放行

        Returns:
            (是否放行, 建议重试秒数)。不放行时第二个值为 Retry-After。
        """
        now = time.time()
        with self._lock:
            hits = self._hits[key]
            # 淘汰窗口外的旧记录
            while hits and hits[0] <= now - self.window_seconds:
                hits.popleft()
            if len(hits) < self.max_requests:
                hits.append(now)
                return True, 0
            # 计算最早记录过期还需多久
            retry_after = max(1, int(hits[0] + self.window_seconds - now) + 1)
            return False, retry_after

    def cleanup(self, max_idle_seconds: int = 300) -> int:
        """清理长时间无请求的键（可挂定时任务调用），返回清理数量"""
        now = time.time()
        removed = 0
        with self._lock:
            for key in list(self._hits.keys()):
                hits = self._hits[key]
                if not hits or hits[-1] < now - max_idle_seconds:
                    del self._hits[key]
                    removed += 1
        return removed


def _client_ip(request: Request) -> str:
    """获取客户端真实 IP（优先取反向代理头）"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """API 限流中间件 — 按 IP+路径 限流"""

    # 不限流的公开端点前缀
    EXCLUDED_PREFIXES = (
        "/health", "/metrics", "/docs", "/openapi.json", "/redoc",
    )

    def __init__(
        self,
        app,
        max_requests: int = 100,
        window_seconds: int = 60,
        limiter: Optional[SlidingWindowLimiter] = None,
    ):
        super().__init__(app)
        self.limiter = limiter or SlidingWindowLimiter(max_requests, window_seconds)
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 公开端点直接放行
        for prefix in self.EXCLUDED_PREFIXES:
            if path == prefix or path.startswith(prefix + "/"):
                return await call_next(request)

        # 仅对 API 路径限流
        if not path.startswith("/api"):
            return await call_next(request)

        key = f"{_client_ip(request)}:{path}"
        allowed, retry_after = self.limiter.allow(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "message": "请求过于频繁，请稍后重试",
                    "error": "Too Many Requests",
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        # 透出当前窗口剩余配额，便于客户端和压测观察
        response.headers["X-RateLimit-Window"] = str(self.window_seconds)
        return response
