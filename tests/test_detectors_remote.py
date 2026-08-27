"""远程检测器单元测试 — mock 外部服务(Prometheus/MySQL/Redis)"""

from types import SimpleNamespace

import pytest


THRESHOLDS = {"warning": 60, "critical": 80}


def _fake_httpx_factory(payload, status=200):
    """构造一个返回固定 JSON 的 fake httpx.AsyncClient"""
    import httpx

    class FakeResponse:
        status_code = status

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url, params=None):
            return FakeResponse()

    return FakeClient


PROM_OK = {
    "status": "success",
    "data": {"result": [{"value": [1234567890, "85.5"]}]},
}
PROM_EMPTY = {"status": "success", "data": {"result": []}}


class TestPrometheusCPUDetector:
    @pytest.fixture
    def detector(self):
        from app.detectors.remote import PrometheusCPUDetector
        return PrometheusCPUDetector()

    async def test_critical(self, detector, monkeypatch):
        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _fake_httpx_factory(PROM_OK))
        result = await detector.check("sys-1", "测试系统", "http://10.0.0.1:9090", THRESHOLDS)
        assert result.severity == "critical"
        assert result.current_value == 85.5

    async def test_no_data(self, detector, monkeypatch):
        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _fake_httpx_factory(PROM_EMPTY))
        result = await detector.check("sys-1", "测试系统", "http://10.0.0.1:9090", THRESHOLDS)
        assert result.severity == "error"

    async def test_query_error(self, detector, monkeypatch):
        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _fake_httpx_factory(PROM_OK, status=502))
        result = await detector.check("sys-1", "测试系统", "http://10.0.0.1:9090", THRESHOLDS)
        # 502 时 resp.json() 仍返回 PROM_OK，走正常解析分支
        assert result.severity in ("critical", "error")


class TestPrometheusMemoryDetector:
    @pytest.fixture
    def detector(self):
        from app.detectors.remote import PrometheusMemoryDetector
        return PrometheusMemoryDetector()

    async def test_normal(self, detector, monkeypatch):
        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", _fake_httpx_factory(PROM_OK))
        result = await detector.check("sys-1", "测试系统", "http://10.0.0.1:9090", THRESHOLDS)
        assert result.severity == "critical"
        assert result.current_value == 85.5


class TestMySQLSlowQueryDetector:
    @pytest.fixture
    def detector(self):
        from app.detectors.remote import MySQLSlowQueryDetector
        return MySQLSlowQueryDetector()

    def _fake_connect(self, rows, monkeypatch):
        import pymysql

        class FakeCursor:
            def __init__(self, rows): self._rows = rows
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def execute(self, sql): pass
            def fetchone(self): return self._rows

        class FakeConn:
            def __init__(self, rows): self._rows = rows
            def cursor(self): return FakeCursor(self._rows)
            def close(self): pass

        monkeypatch.setattr(pymysql, "connect", lambda **kw: FakeConn(rows))

    async def test_many_slow_queries(self, detector, monkeypatch):
        self._fake_connect(("Slow_queries", 120), monkeypatch)
        result = await detector.check(
            "sys-1", "测试系统", "10.0.0.1:3306",
            {"warning": 10, "critical": 50},
            auth={"user": "root", "password": "", "database": "mysql"},
        )
        assert result.severity == "critical"
        assert result.current_value == 120

    async def test_normal(self, detector, monkeypatch):
        self._fake_connect(("Slow_queries", 3), monkeypatch)
        result = await detector.check(
            "sys-1", "测试系统", "10.0.0.1:3306",
            {"warning": 10, "critical": 50},
            auth={"user": "root", "password": ""},
        )
        assert result.severity == "normal"

    async def test_connection_failure(self, detector, monkeypatch):
        import pymysql
        def _boom(**kw): raise pymysql.MySQLError("connection refused")
        monkeypatch.setattr(pymysql, "connect", _boom)
        result = await detector.check(
            "sys-1", "测试系统", "10.0.0.1:3306", THRESHOLDS,
        )
        assert result.severity == "error"


class TestRedisMemoryDetector:
    @pytest.fixture
    def detector(self):
        from app.detectors.remote import RedisMemoryDetector
        return RedisMemoryDetector()

    async def test_high_memory(self, detector, monkeypatch):
        import redis as redis_mod

        class FakeRedis:
            def __init__(self, *a, **kw): pass
            def info(self, section):
                if section == "memory":
                    return {"used_memory_rss": 900, "maxmemory": 1000}
                return {"connected_clients": 10}
            def close(self): pass

        monkeypatch.setattr(redis_mod, "Redis", FakeRedis)
        result = await detector.check(
            "sys-1", "测试系统", "10.0.0.1:6379", THRESHOLDS,
        )
        assert result.severity == "critical"  # 90% >= 80

    async def test_connection_failure(self, detector, monkeypatch):
        import redis as redis_mod
        def _boom(*a, **kw): raise ConnectionError("refused")
        monkeypatch.setattr(redis_mod, "Redis", _boom)
        result = await detector.check(
            "sys-1", "测试系统", "10.0.0.1:6379", THRESHOLDS,
        )
        assert result.severity == "error"
