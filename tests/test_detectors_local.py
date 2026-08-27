"""本地检测器单元测试 — mock 外部依赖(psutil/shutil/httpx)"""

from types import SimpleNamespace

import pytest


THRESHOLDS = {"warning": 60, "critical": 80}


class TestHTTPHealthDetector:
    """HTTP 健康检测器测试"""

    @pytest.fixture
    def detector(self):
        from app.detectors.local import HTTPHealthDetector
        return HTTPHealthDetector()

    async def test_healthy_2xx(self, detector, monkeypatch):
        """2xx 响应 → normal"""
        import httpx

        class FakeResponse:
            status_code = 200

        class FakeClient:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def get(self, url):
                assert url.endswith("/health")
                return FakeResponse()

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        result = await detector.check("sys-1", "测试系统", "http://10.0.0.1:8080", THRESHOLDS)
        assert result.severity == "normal"
        assert result.current_value == 200
        assert result.is_anomalous is False

    async def test_unhealthy_5xx(self, detector, monkeypatch):
        """5xx 响应 → critical"""
        import httpx

        class FakeResponse:
            status_code = 500

        class FakeClient:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def get(self, url): return FakeResponse()

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        result = await detector.check("sys-1", "测试系统", "http://10.0.0.1:8080", THRESHOLDS)
        assert result.severity == "critical"
        assert result.is_anomalous is True

    async def test_connection_error(self, detector, monkeypatch):
        """连接异常 → critical（服务不可达视为严重）"""
        import httpx

        class FakeClient:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def get(self, url):
                raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        result = await detector.check("sys-1", "测试系统", "http://10.0.0.1:8080", THRESHOLDS)
        assert result.severity == "critical"
        assert "失败" in result.message


class TestLocalCPUDetector:
    """本机 CPU 检测器测试"""

    @pytest.fixture
    def detector(self):
        from app.detectors.local import LocalCPUDetector
        return LocalCPUDetector()

    async def test_critical(self, detector, monkeypatch):
        import psutil
        monkeypatch.setattr(psutil, "cpu_percent", lambda interval=1: 95.0)
        monkeypatch.setattr(psutil, "cpu_count", lambda: 8)
        result = await detector.check("sys-1", "测试系统", "localhost", THRESHOLDS)
        assert result.severity == "critical"

    async def test_warning(self, detector, monkeypatch):
        import psutil
        monkeypatch.setattr(psutil, "cpu_percent", lambda interval=1: 70.0)
        monkeypatch.setattr(psutil, "cpu_count", lambda: 8)
        result = await detector.check("sys-1", "测试系统", "localhost", THRESHOLDS)
        assert result.severity == "warning"

    async def test_normal(self, detector, monkeypatch):
        import psutil
        monkeypatch.setattr(psutil, "cpu_percent", lambda interval=1: 30.0)
        monkeypatch.setattr(psutil, "cpu_count", lambda: 8)
        result = await detector.check("sys-1", "测试系统", "localhost", THRESHOLDS)
        assert result.severity == "normal"

    async def test_psutil_error(self, detector, monkeypatch):
        import psutil
        def _boom(interval=1): raise OSError("psutil error")
        monkeypatch.setattr(psutil, "cpu_percent", _boom)
        result = await detector.check("sys-1", "测试系统", "localhost", THRESHOLDS)
        assert result.severity == "error"


class TestLocalMemoryDetector:
    """本机内存检测器测试"""

    @pytest.fixture
    def detector(self):
        from app.detectors.local import LocalMemoryDetector
        return LocalMemoryDetector()

    async def test_critical(self, detector, monkeypatch):
        import psutil
        mem = SimpleNamespace(
            percent=92.5, total=16 * 1024**3, available=1 * 1024**3,
        )
        monkeypatch.setattr(psutil, "virtual_memory", lambda: mem)
        result = await detector.check("sys-1", "测试系统", "localhost", THRESHOLDS)
        assert result.severity == "critical"

    async def test_normal(self, detector, monkeypatch):
        import psutil
        mem = SimpleNamespace(
            percent=45.2, total=16 * 1024**3, available=8 * 1024**3,
        )
        monkeypatch.setattr(psutil, "virtual_memory", lambda: mem)
        result = await detector.check("sys-1", "测试系统", "localhost", THRESHOLDS)
        assert result.severity == "normal"


class TestLocalDiskDetector:
    """本机磁盘检测器测试"""

    @pytest.fixture
    def detector(self):
        from app.detectors.local import LocalDiskDetector
        return LocalDiskDetector()

    async def test_critical(self, detector, monkeypatch):
        import shutil
        # used/total = 95%
        usage = SimpleNamespace(total=100 * 1024**3, used=95 * 1024**3, free=5 * 1024**3)
        monkeypatch.setattr(shutil, "disk_usage", lambda path: usage)
        result = await detector.check("sys-1", "测试系统", "localhost", THRESHOLDS)
        assert result.severity == "critical"

    async def test_normal(self, detector, monkeypatch):
        import shutil
        usage = SimpleNamespace(total=100 * 1024**3, used=40 * 1024**3, free=60 * 1024**3)
        monkeypatch.setattr(shutil, "disk_usage", lambda path: usage)
        result = await detector.check("sys-1", "测试系统", "localhost", THRESHOLDS)
        assert result.severity == "normal"

    async def test_threshold_evaluate(self, detector):
        """直接验证阈值评估逻辑(纯逻辑)"""
        severity, _ = detector._evaluate(80, THRESHOLDS)
        assert severity == "critical"
        severity, _ = detector._evaluate(60, THRESHOLDS)
        assert severity == "warning"
        severity, _ = detector._evaluate(30, THRESHOLDS)
        assert severity == "normal"
