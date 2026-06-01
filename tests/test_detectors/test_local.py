"""本地检测器单元测试"""

import pytest
from app.detectors.local import LocalCPUDetector, LocalMemoryDetector, LocalDiskDetector, HTTPHealthDetector


class TestLocalCPUDetector:
    """CPU 检测器测试"""

    def test_detector_name(self):
        detector = LocalCPUDetector(config={})
        assert detector.name == "local_cpu"

    def test_run_sync(self):
        detector = LocalCPUDetector(config={})
        result = detector.run_sync()
        assert result is not None
        assert result.metric_name == "cpu_usage"
        assert result.severity in ["normal", "warning", "critical", "error"]

    def test_thresholds(self):
        detector = LocalCPUDetector(config={"thresholds": {"warning": 50, "critical": 80}})
        result = detector.run_sync()
        assert result.severity in ["normal", "warning", "critical", "error"]


class TestLocalMemoryDetector:
    """内存检测器测试"""

    def test_detector_name(self):
        detector = LocalMemoryDetector(config={})
        assert detector.name == "local_memory"

    def test_run_sync(self):
        detector = LocalMemoryDetector(config={})
        result = detector.run_sync()
        assert result is not None
        assert result.metric_name == "memory_usage"
        assert result.severity in ["normal", "warning", "critical", "error"]


class TestLocalDiskDetector:
    """磁盘检测器测试"""

    def test_detector_name(self):
        detector = LocalDiskDetector(config={})
        assert detector.name == "local_disk"

    def test_run_sync(self):
        detector = LocalDiskDetector(config={})
        result = detector.run_sync()
        assert result is not None
        assert result.metric_name == "disk_usage"
        assert result.severity in ["normal", "warning", "critical", "error"]


class TestHTTPHealthDetector:
    """HTTP 健康检测器测试"""

    def test_detector_name(self):
        detector = HTTPHealthDetector(config={"endpoint": "http://localhost:9900/health"})
        assert detector.name == "http_health"

    def test_run_sync(self):
        detector = HTTPHealthDetector(config={"endpoint": "http://localhost:9900/health"})
        result = detector.run_sync()
        assert result is not None
        assert result.metric_name == "http_status"

    def test_invalid_url(self):
        detector = HTTPHealthDetector(config={"endpoint": "http://invalid.local:9999/health"})
        result = detector.run_sync()
        assert result.severity == "error"