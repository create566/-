"""限流中间件单元测试"""

import time

import pytest


class TestSlidingWindowLimiter:
    """滑动窗口限流器核心逻辑"""

    def test_allows_within_limit(self):
        from app.middleware.rate_limit import SlidingWindowLimiter
        limiter = SlidingWindowLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            allowed, _ = limiter.allow("client1:/api/x")
            assert allowed is True

    def test_blocks_over_limit(self):
        from app.middleware.rate_limit import SlidingWindowLimiter
        limiter = SlidingWindowLimiter(max_requests=2, window_seconds=60)
        assert limiter.allow("k")[0] is True
        assert limiter.allow("k")[0] is True
        allowed, retry_after = limiter.allow("k")
        assert allowed is False
        assert retry_after >= 1
        assert retry_after <= 61

    def test_window_slides_forward(self):
        """窗口滑过后恢复放行"""
        from app.middleware.rate_limit import SlidingWindowLimiter
        limiter = SlidingWindowLimiter(max_requests=1, window_seconds=1)
        assert limiter.allow("k")[0] is True
        assert limiter.allow("k")[0] is False
        time.sleep(1.1)
        assert limiter.allow("k")[0] is True

    def test_keys_are_isolated(self):
        """不同 IP/路径互不影响"""
        from app.middleware.rate_limit import SlidingWindowLimiter
        limiter = SlidingWindowLimiter(max_requests=1, window_seconds=60)
        assert limiter.allow("ip1:/api/a")[0] is True
        assert limiter.allow("ip2:/api/a")[0] is True
        assert limiter.allow("ip1:/api/b")[0] is True
        assert limiter.allow("ip1:/api/a")[0] is False

    def test_cleanup_removes_idle_keys(self):
        from app.middleware.rate_limit import SlidingWindowLimiter
        limiter = SlidingWindowLimiter(max_requests=10, window_seconds=60)
        limiter.allow("idle_key")
        limiter.allow("active_key")
        # 手动把 idle_key 的最后访问时间拨回过去
        limiter._hits["idle_key"][0] -= 1000
        removed = limiter.cleanup(max_idle_seconds=300)
        assert removed == 1
        assert "idle_key" not in limiter._hits
        assert "active_key" in limiter._hits


class TestRateLimitMiddleware:
    """限流中间件集成行为（挂在真实 ASGI app 上）"""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from starlette.testclient import TestClient
        from app.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=2, window_seconds=60)

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.get("/")
        async def root():
            return {"status": "ok"}

        @app.get("/api/data")
        async def data():
            return {"status": "ok"}

        return TestClient(app)

    def test_health_not_rate_limited(self, client):
        for _ in range(10):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_non_api_path_not_rate_limited(self, client):
        for _ in range(10):
            resp = client.get("/")
            assert resp.status_code == 200

    def test_api_blocked_after_threshold(self, client):
        assert client.get("/api/data").status_code == 200
        assert client.get("/api/data").status_code == 200
        resp = client.get("/api/data")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        body = resp.json()
        assert body["error"] == "Too Many Requests"
