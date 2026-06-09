"""API Key 认证中间件"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.config import config


class AuthMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件"""

    # 公开端点（不需要认证）
    PUBLIC_PATHS = [
        "/",
        "/health",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/feishu/handle",  # 飞书 WS 进程本地回调，无需认证
        "/api/chat/send",      # Web 聊天无需认证
    ]

    async def dispatch(self, request: Request, call_next):
        # 预检请求放行
        if request.method == "OPTIONS":
            return await call_next(request)

        # 公开端点放行
        path = request.url.path
        for public_path in self.PUBLIC_PATHS:
            if path == public_path or path.startswith(public_path + "/"):
                return await call_next(request)

        # API 端点需要认证
        if path.startswith("/api/"):
            api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
            if not api_key:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Missing X-API-Key header"}
                )
            if api_key != config.api_key:
                return JSONResponse(
                    status_code=403,
                    content={"error": "Invalid API key"}
                )

        return await call_next(request)