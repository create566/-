"""
测试检测器注册中心
"""
import pytest
from app.detectors.registry import DetectorRegistry
from app.detectors.base import BaseDetector, DetectionResult


class DummyDetector(BaseDetector):
    name = "dummy_test"
    description = "测试用假检测器"
    metric_name = "dummy_value"

    async def check(self, system_id, system_name, endpoint, thresholds, auth=None):
        return DetectionResult(
            detector_name=self.name, system_id=system_id,
            metric_name=self.metric_name, current_value=0,
            severity="normal", message="ok"
        )


class TestDetectorRegistry:
    """检测器注册中心测试"""

    def test_register_and_get(self):
        DetectorRegistry.register("my_detector", DummyDetector)
        cls = DetectorRegistry.get("my_detector")
        assert cls is DummyDetector

    def test_get_nonexistent(self):
        assert DetectorRegistry.get("nonexistent_xyz") is None

    def test_list_all(self):
        DetectorRegistry.register("my_detector", DummyDetector)
        result = DetectorRegistry.list_all()
        assert "my_detector" in result
        assert result["my_detector"] == "测试用假检测器"

    def test_list_details(self):
        DetectorRegistry.register("my_detector", DummyDetector)
        details = DetectorRegistry.list_details()
        names = [d["name"] for d in details]
        assert "my_detector" in names

    def test_get_or_create_caches_instance(self):
        DetectorRegistry.register("my_detector", DummyDetector)
        inst1 = DetectorRegistry.get_or_create("my_detector", {"key": "val"})
        inst2 = DetectorRegistry.get_or_create("my_detector", {"key": "val"})
        assert inst1 is inst2  # 同一个实例

    def test_get_or_create_different_configs(self):
        DetectorRegistry.register("my_detector", DummyDetector)
        inst1 = DetectorRegistry.get_or_create("my_detector", {"k": 1})
        inst2 = DetectorRegistry.get_or_create("my_detector", {"k": 2})
        assert inst1 is not inst2  # 不同配置，不同实例

    def test_get_or_create_nonexistent(self):
        assert DetectorRegistry.get_or_create("not_registered") is None
