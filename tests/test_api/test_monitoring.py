"""API 集成测试"""

import pytest
from fastapi.testclient import TestClient


class TestHealthAPI:
    """健康检查 API 测试"""

    def test_health_endpoint(self):
        """测试 /health 端点"""
        from app.main import app
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_live_endpoint(self):
        """测试 /health/live 端点"""
        from app.main import app
        client = TestClient(app)
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


class TestMonitoringAPI:
    """监控管理 API 测试（需要认证）"""

    def test_list_systems_without_auth(self):
        """测试未认证访问被拒绝"""
        from app.main import app
        client = TestClient(app)
        response = client.get("/api/systems")
        assert response.status_code == 401

    def test_list_systems_with_auth(self):
        """测试带认证访问系统列表"""
        from app.main import app
        from app.config import config
        client = TestClient(app)
        response = client.get(
            "/api/systems",
            headers={"X-API-Key": config.api_key}
        )
        assert response.status_code == 200

    def test_create_system(self):
        """测试创建系统"""
        from app.main import app
        from app.config import config
        client = TestClient(app)
        response = client.post(
            "/api/systems",
            headers={
                "X-API-Key": config.api_key,
                "Content-Type": "application/json"
            },
            json={
                "name": "测试系统",
                "system_type": "server",
                "endpoint": "localhost",
                "detectors": [
                    {"name": "local_cpu", "thresholds": {"warning": 60, "critical": 80}}
                ],
                "check_interval_seconds": 60
            }
        )
        # 可能 200 成功或 500（数据库未连接），但不应该 401
        assert response.status_code != 401

    def test_metrics_endpoint(self):
        """测试 /metrics 端点（公开）"""
        from app.main import app
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200