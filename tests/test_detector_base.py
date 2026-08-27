"""
测试 BaseDetector._evaluate 阈值判断逻辑
纯函数测试，无外部依赖，可直接运行
"""
import pytest
from app.detectors.base import BaseDetector, DetectionResult


class FakeDetector(BaseDetector):
    """用假实现绕过抽象方法"""
    name = "fake"
    metric_name = "test_metric"

    async def check(self, system_id, system_name, endpoint, thresholds, auth=None):
        return DetectionResult(detector_name=self.name, system_id=system_id)


class TestEvaluate:
    """阈值判断逻辑测试"""

    def test_normal_below_thresholds(self):
        detector = FakeDetector({})
        severity, msg = detector._evaluate(30, {"warning": 60, "critical": 80})
        assert severity == "normal"
        assert "正常" in msg

    def test_warning_between_thresholds(self):
        detector = FakeDetector({})
        severity, msg = detector._evaluate(70, {"warning": 60, "critical": 80})
        assert severity == "warning"

    def test_critical_above_critical(self):
        detector = FakeDetector({})
        severity, msg = detector._evaluate(85, {"warning": 60, "critical": 80})
        assert severity == "critical"

    def test_critical_equal_threshold(self):
        detector = FakeDetector({})
        severity, msg = detector._evaluate(80, {"warning": 60, "critical": 80})
        assert severity == "critical"  # >=

    def test_warning_equal_threshold(self):
        detector = FakeDetector({})
        severity, msg = detector._evaluate(60, {"warning": 60, "critical": 80})
        assert severity == "warning"

    def test_only_warning_threshold(self):
        detector = FakeDetector({})
        severity, msg = detector._evaluate(65, {"warning": 50})
        assert severity == "warning"

    def test_no_thresholds(self):
        detector = FakeDetector({})
        severity, msg = detector._evaluate(100, {})
        assert severity == "normal"


class TestDetectionResult:
    """检测结果数据类测试"""

    def test_is_anomalous_warning(self):
        r = DetectionResult(detector_name="test", system_id="1", severity="warning", current_value=75)
        assert r.is_anomalous is True

    def test_is_anomalous_critical(self):
        r = DetectionResult(detector_name="test", system_id="1", severity="critical", current_value=95)
        assert r.is_anomalous is True

    def test_is_not_anomalous_normal(self):
        r = DetectionResult(detector_name="test", system_id="1", severity="normal", current_value=30)
        assert r.is_anomalous is False

    def test_is_not_anomalous_error(self):
        r = DetectionResult(detector_name="test", system_id="1", severity="error", current_value=0)
        assert r.is_anomalous is False
