"""检测器注册中心测试"""

import pytest
from app.detectors.registry import DetectorRegistry, register_detector
from app.detectors.base import BaseDetector


class TestDetectorRegistry:
    """检测器注册中心测试"""

    def test_register(self):
        """测试检测器注册"""
        original = DetectorRegistry._detectors.copy()
        DetectorRegistry._detectors.clear()

        @register_detector("test_detector")
        class TestDetector(BaseDetector):
            name = "test_detector"

            def run_sync(self):
                from app.detectors.base import DetectionResult
                return DetectionResult(
                    detector_name=self.name,
                    metric_name="test_metric",
                    current_value="100",
                    severity="normal",
                    message="test",
                    timestamp="",
                )

        assert "test_detector" in DetectorRegistry.list_all()
        DetectorRegistry._detectors = original

    def test_get_or_create(self):
        """测试检测器实例缓存"""
        DetectorRegistry._instances.clear()
        config = {"thresholds": {"warning": 60, "critical": 80}}

        detector1 = DetectorRegistry.get_or_create("local_cpu", config)
        detector2 = DetectorRegistry.get_or_create("local_cpu", config)

        # 相同配置应该返回相同实例
        assert detector1 is detector2

    def test_list_all(self):
        """测试列出所有检测器"""
        detectors = DetectorRegistry.list_all()
        assert len(detectors) > 0
        assert "local_cpu" in detectors
        assert "local_memory" in detectors