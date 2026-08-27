"""
测试 Planner — _make_check_plan 逻辑
≤3 个检测器时不需要 LLM，走纯逻辑分支，可直接测试
"""
import pytest
from app.agent.planner import _make_check_plan
from unittest.mock import MagicMock, AsyncMock


class TestMakeCheckPlan:
    """制定检测计划"""

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.invoke = MagicMock()
        return llm

    @pytest.fixture
    def base_state(self):
        return {
            "system_name": "test-system",
            "system_type": "web",
            "detectors": [],
            "history": [],
        }

    def test_empty_detectors_returns_noop(self, mock_llm):
        state = {
            "system_name": "test",
            "system_type": "web",
            "detectors": [],
            "history": [],
        }
        import asyncio
        result = asyncio.run(_make_check_plan(state, mock_llm))
        assert len(result["plan"]) == 1
        assert result["plan"][0]["action"] == "noop"

    def test_single_detector_returns_one_step(self, mock_llm):
        state = {
            "system_name": "test",
            "system_type": "web",
            "detectors": [
                {"name": "local_cpu", "thresholds": {"warning": 60, "critical": 80}}
            ],
            "history": [],
        }
        import asyncio
        result = asyncio.run(_make_check_plan(state, mock_llm))
        assert len(result["plan"]) == 1
        assert result["plan"][0]["action"] == "local_cpu"
        assert result["plan"][0]["status"] == "pending"

    def test_two_detectors_returns_two_steps(self, mock_llm):
        state = {
            "system_name": "test",
            "system_type": "web",
            "detectors": [
                {"name": "local_cpu", "thresholds": {"warning": 60, "critical": 80}},
                {"name": "local_memory", "thresholds": {"warning": 70, "critical": 85}},
            ],
            "history": [],
        }
        import asyncio
        result = asyncio.run(_make_check_plan(state, mock_llm))
        assert len(result["plan"]) == 2
        assert result["plan"][0]["step"] == 1
        assert result["plan"][1]["step"] == 2

    def test_three_detectors_returns_three_steps(self, mock_llm):
        state = {
            "system_name": "test",
            "system_type": "web",
            "detectors": [
                {"name": "local_cpu", "thresholds": {"warning": 60, "critical": 80}},
                {"name": "local_memory", "thresholds": {"warning": 70, "critical": 85}},
                {"name": "local_disk", "thresholds": {"warning": 75, "critical": 90}},
            ],
            "history": [],
        }
        import asyncio
        result = asyncio.run(_make_check_plan(state, mock_llm))
        assert len(result["plan"]) == 3

    def test_steps_have_required_fields(self, mock_llm):
        state = {
            "system_name": "test",
            "system_type": "web",
            "detectors": [
                {"name": "local_cpu", "thresholds": {"warning": 60, "critical": 80}}
            ],
            "history": [],
        }
        import asyncio
        result = asyncio.run(_make_check_plan(state, mock_llm))
        for step in result["plan"]:
            assert "step" in step
            assert "action" in step
            assert "params" in step
            assert "reason" in step
            assert "status" in step
