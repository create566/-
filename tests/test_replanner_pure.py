"""
测试 Replanner 纯逻辑函数
_quick_judge, _should_diagnose, decide_next, _extract_root_cause, _format_history_trend
无需外部依赖，可直接运行
"""
import pytest
from app.agent.replanner import (
    _quick_judge,
    _should_diagnose,
    decide_next,
    _extract_root_cause,
    _format_history_trend,
)


class TestQuickJudge:
    """毛刺过滤逻辑"""

    def test_empty_anomalies_returns_normal(self):
        assert _quick_judge([], []) == "normal"

    def test_single_anomaly_no_history_returns_anomaly(self):
        anomalies = [{"detector_name": "local_cpu", "metric_value": 90, "severity": "critical"}]
        assert _quick_judge(anomalies, []) == "anomaly"

    def test_single_spike_filtered_as_noise(self):
        """前4次正常（<50），突然飙到90，且只有这一个异常 → 毛刺过滤"""
        anomalies = [{"detector_name": "local_cpu", "metric_value": 90}]
        history = [
            {"detector_name": "local_cpu", "metric_value": 30},
            {"detector_name": "local_cpu", "metric_value": 35},
            {"detector_name": "local_cpu", "metric_value": 28},
            {"detector_name": "local_cpu", "metric_value": 40},
        ]
        assert _quick_judge(anomalies, history) == "normal"

    def test_multiple_anomalies_not_filtered(self):
        """多个指标同时异常 → 不可能是毛刺"""
        anomalies = [
            {"detector_name": "local_cpu", "metric_value": 90},
            {"detector_name": "local_memory", "metric_value": 85},
        ]
        history = [
            {"detector_name": "local_cpu", "metric_value": 30},
            {"detector_name": "local_cpu", "metric_value": 35},
            {"detector_name": "local_cpu", "metric_value": 28},
            {"detector_name": "local_cpu", "metric_value": 40},
        ]
        # 两个异常 → 不过滤
        assert _quick_judge(anomalies, history) == "anomaly"

    def test_normal_trend_not_filtered(self):
        """前4次均值不低 → 不是毛刺，如实报告"""
        anomalies = [{"detector_name": "local_cpu", "metric_value": 90}]
        history = [
            {"detector_name": "local_cpu", "metric_value": 70},
            {"detector_name": "local_cpu", "metric_value": 65},
            {"detector_name": "local_cpu", "metric_value": 72},
            {"detector_name": "local_cpu", "metric_value": 68},
        ]
        # 历史均值>50 → 不过滤
        assert _quick_judge(anomalies, history) == "anomaly"


class TestShouldDiagnose:
    """是否触发深度诊断"""

    def test_multi_anomaly_triggers_diagnosis(self):
        assert _should_diagnose(
            [{"detector_name": "cpu"}, {"detector_name": "memory"}],
            []
        ) is True

    def test_critical_triggers_diagnosis(self):
        assert _should_diagnose(
            [{"detector_name": "cpu", "severity": "critical"}],
            []
        ) is True

    def test_single_warning_no_trend_skips(self):
        assert _should_diagnose(
            [{"detector_name": "cpu", "severity": "warning"}],
            []
        ) is False

    def test_rising_trend_triggers_diagnosis(self):
        """连续3次上升 → 需要诊断"""
        anomalies = [{"detector_name": "local_cpu", "metric_value": 85}]
        history = [
            {"detector_name": "local_cpu", "metric_value": 60},
            {"detector_name": "local_cpu", "metric_value": 70},
            {"detector_name": "local_cpu", "metric_value": 80},
        ]
        assert _should_diagnose(anomalies, history) is True


class TestDecideNext:
    """状态路由"""

    def test_done_returns_done(self):
        assert decide_next({"phase": "done"}) == "done"

    def test_checking_returns_done(self):
        """checking 阶段默认结束（由 replanner 设为 done）"""
        assert decide_next({"phase": "checking"}) == "done"

    def test_diagnosing_returns_continue(self):
        """diagnosing 阶段 → 回到 planner 继续排查"""
        assert decide_next({"phase": "diagnosing"}) == "continue"

    def test_empty_state_defaults_to_done(self):
        assert decide_next({}) == "done"


class TestExtractRootCause:
    """根因提取"""

    def test_extract_from_chinese(self):
        report = "## 告警摘要\n系统CPU过高\n\n## 根因分析：缓存失效导致数据库压力增大\n\n## 处理建议"
        assert "缓存失效" in _extract_root_cause(report)

    def test_extract_from_english_colon(self):
        report = "## Root Cause Analysis: Database connection pool exhausted\n\n## Action Items"
        assert "Database" in _extract_root_cause(report)

    def test_fallback_to_first_100_chars(self):
        report = "# 故障报告\n系统出现未知异常，需要进一步排查。"
        result = _extract_root_cause(report)
        assert len(result) <= 100
        assert "故障报告" in result


class TestFormatHistoryTrend:
    """历史趋势格式化"""

    def test_empty_history(self):
        assert _format_history_trend([]) == "无历史数据"

    def test_rising_trend(self):
        history = [
            {"detector_name": "cpu", "metric_value": 30},
            {"detector_name": "cpu", "metric_value": 50},
            {"detector_name": "cpu", "metric_value": 80},
        ]
        result = _format_history_trend(history)
        assert "持续上升" in result
        assert "cpu" in result

    def test_multi_detector(self):
        history = [
            {"detector_name": "cpu", "metric_value": 30},
            {"detector_name": "memory", "metric_value": 60},
        ]
        result = _format_history_trend(history)
        assert "cpu" in result
        assert "memory" in result
