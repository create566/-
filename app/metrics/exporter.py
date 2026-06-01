"""Prometheus Metrics 导出器"""

from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
)
from starlette.responses import Response


# ==================== 指标定义 ====================

# 检测指标
monitor_check_total = Counter(
    "monitor_check_total",
    "Total number of monitoring checks",
    ["system_id", "detector_name", "severity"]
)

monitor_check_duration_seconds = Histogram(
    "monitor_check_duration_seconds",
    "Duration of monitoring checks in seconds",
    ["system_id", "detector_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# 告警指标
monitor_alert_total = Counter(
    "monitor_alert_total",
    "Total number of alerts generated",
    ["system_id", "severity"]
)

monitor_system_health_score = Gauge(
    "monitor_system_health_score",
    "Health score of monitored systems",
    ["system_id"]
)

# LLM 指标
llm_call_duration_seconds = Histogram(
    "llm_call_duration_seconds",
    "Duration of LLM calls in seconds",
    ["operation"]  # planner / replanner / diagnosis
)

llm_call_total = Counter(
    "llm_call_total",
    "Total number of LLM calls",
    ["operation", "status"]  # success / failure
)

# 飞书通知指标
feishu_notification_total = Counter(
    "feishu_notification_total",
    "Total number of Feishu notifications",
    ["status"]  # success / failure
)


# ==================== 辅助函数 ====================

def record_check(system_id: str, detector_name: str, severity: str, duration: float):
    """记录一次检测"""
    monitor_check_total.labels(system_id=system_id, detector_name=detector_name, severity=severity).inc()
    monitor_check_duration_seconds.labels(system_id=system_id, detector_name=detector_name).observe(duration)


def record_alert(system_id: str, severity: str):
    """记录一次告警"""
    monitor_alert_total.labels(system_id=system_id, severity=severity).inc()


def update_health_score(system_id: str, score: int):
    """更新健康分"""
    monitor_system_health_score.labels(system_id=system_id).set(score)


def record_llm_call(operation: str, duration: float, success: bool):
    """记录一次 LLM 调用"""
    status = "success" if success else "failure"
    llm_call_total.labels(operation=operation, status=status).inc()
    llm_call_duration_seconds.labels(operation=operation).observe(duration)


def record_feishu_notification(success: bool):
    """记录飞书通知"""
    status = "success" if success else "failure"
    feishu_notification_total.labels(status=status).inc()


# ==================== HTTP 端点 ====================

async def metrics_endpoint(request):
    """Prometheus metrics 端点"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )