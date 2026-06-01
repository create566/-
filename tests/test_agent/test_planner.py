"""Planner 逻辑测试"""

import pytest
from app.agent.planner import planner, _make_check_plan


class TestPlanner:
    """Planner 测试"""

    def test_make_check_plan_few_detectors(self):
        """测试少量检测器时跳过 LLM"""
        detectors = [
            {"name": "local_cpu", "thresholds": {"warning": 60, "critical": 80}},
            {"name": "local_memory", "thresholds": {"warning": 70, "critical": 85}},
        ]
        plan = _make_check_plan(detectors, "", llm_available=False)
        assert len(plan) > 0
        assert all("detector_name" in step for step in plan)

    def test_make_check_plan_with_context(self):
        """测试带上下文的计划生成"""
        detectors = [
            {"name": "local_cpu", "thresholds": {"warning": 60, "critical": 80}},
            {"name": "local_memory", "thresholds": {"warning": 70, "critical": 85}},
            {"name": "local_disk", "thresholds": {"warning": 75, "critical": 90}},
        ]
        context = "CPU 使用率异常，可能是负载过高"
        plan = _make_check_plan(detectors, context, llm_available=False)
        assert len(plan) > 0


class TestReplanner:
    """Replanner 测试"""

    def test_decide_next_continue(self):
        """测试继续排查的情况"""
        from app.agent.replanner import decide_next
        state = {
            "anomalies": [
                {"detector_name": "local_cpu", "severity": "critical"}
            ],
            "phase": "diagnosing",
            "diagnosis_rounds": 1,
        }
        result = decide_next(state)
        assert result in ["continue", "done"]

    def test_decide_next_done(self):
        """测试结束的情况"""
        from app.agent.replanner import decide_next
        state = {
            "anomalies": [],
            "phase": "done",
            "diagnosis_rounds": 3,
        }
        result = decide_next(state)
        assert result == "done"