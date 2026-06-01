"""Pytest 配置和 fixtures"""

import pytest
import sys
from pathlib import Path

# 将 app 目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_config():
    """模拟配置对象"""
    from app.config import Settings
    config = Settings()
    config.db_host = "localhost"
    config.db_port = 3306
    config.db_user = "root"
    config.db_password = "test"
    config.db_name = "test_db"
    config.redis_host = "localhost"
    config.redis_port = 6379
    config.redis_db = 0
    config.redis_password = ""
    config.api_key = "test_api_key"
    return config


@pytest.fixture
def sample_system():
    """样例系统数据"""
    return {
        "id": "test_system_001",
        "name": "测试系统",
        "system_type": "server",
        "endpoint": "localhost",
        "detectors": [
            {"name": "local_cpu", "thresholds": {"warning": 60, "critical": 80}},
            {"name": "local_memory", "thresholds": {"warning": 70, "critical": 85}},
        ],
        "check_interval_seconds": 60,
        "alert_enabled": True,
    }


@pytest.fixture
def sample_check_results():
    """样例检测结果"""
    from app.detectors.base import DetectionResult
    return [
        DetectionResult(
            detector_name="local_cpu",
            metric_name="cpu_usage",
            current_value="85%",
            severity="critical",
            message="CPU 使用率过高",
            timestamp="2026-06-01T12:00:00Z",
        ),
        DetectionResult(
            detector_name="local_memory",
            metric_name="memory_usage",
            current_value="72%",
            severity="warning",
            message="内存使用率偏高",
            timestamp="2026-06-01T12:00:00Z",
        ),
    ]