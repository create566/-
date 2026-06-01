"""监控管理 API — 系统注册、仪表盘、故障历史、检测器列表"""

import uuid
from typing import Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from loguru import logger

from app.models.response import UnifiedResponse
from app.dao import store
from app.detectors.registry import DetectorRegistry
from app.scheduler.engine import monitor_scheduler
from app.alert.pipeline import alert_pipeline

router = APIRouter()


# ==================== 请求模型 ====================

class DetectorConfig(BaseModel):
    name: str
    thresholds: dict = Field(default_factory=lambda: {"warning": 60, "critical": 80})
    config: Optional[dict] = Field(default_factory=dict, description="检测器自定义配置，如自定义 PromQL")


class CreateSystemRequest(BaseModel):
    name: str = Field(..., description="系统名称")
    system_type: str = Field(default="web_service")
    endpoint: str = Field(default="")
    auth: Optional[dict] = Field(default=None, description="认证信息，如 {user, password, database}")
    detectors: list[DetectorConfig] = Field(default_factory=list)
    check_interval_seconds: int = Field(default=60, ge=10, le=3600)
    alert_enabled: bool = Field(default=True)


class UpdateSystemRequest(BaseModel):
    name: Optional[str] = None
    system_type: Optional[str] = None
    endpoint: Optional[str] = None
    auth: Optional[dict] = None
    detectors: Optional[list[DetectorConfig]] = None
    check_interval_seconds: Optional[int] = Field(default=None, ge=10, le=3600)
    alert_enabled: Optional[bool] = None
    status: Optional[str] = None


# ==================== 系统管理 ====================

@router.get("/systems")
async def list_systems_api():
    """列出所有注册系统"""
    systems = store.list_systems()
    scheduled = {s["system_id"] for s in monitor_scheduler.get_scheduled()}
    for s in systems:
        s["scheduled"] = s["id"] in scheduled
    return UnifiedResponse.success(result={"systems": systems, "total": len(systems)}).model_dump()


@router.post("/systems")
async def create_system_api(req: CreateSystemRequest):
    """注册新系统并启动定时检测"""
    system = store.create_system({
        "id": str(uuid.uuid4()),
        "name": req.name,
        "system_type": req.system_type,
        "endpoint": req.endpoint,
        "auth": req.auth,
        "detectors": [d.model_dump() for d in req.detectors],
        "check_interval_seconds": req.check_interval_seconds,
        "alert_enabled": req.alert_enabled,
    })
    monitor_scheduler.schedule(system["id"], req.check_interval_seconds)
    logger.info(f"系统注册并调度: {req.name} (间隔{req.check_interval_seconds}s)")
    return UnifiedResponse.success(result=system).model_dump()


@router.get("/systems/{system_id}")
async def get_system_api(system_id: str):
    """获取系统详情"""
    system = store.get_system(system_id)
    if system is None:
        return UnifiedResponse.error(error_message="系统不存在", code=404).model_dump()
    system["scheduled"] = monitor_scheduler.is_scheduled(system_id)
    return UnifiedResponse.success(result=system).model_dump()


@router.put("/systems/{system_id}")
async def update_system_api(system_id: str, req: UpdateSystemRequest):
    """更新系统配置"""
    system = store.get_system(system_id)
    if system is None:
        return UnifiedResponse.error(error_message="系统不存在", code=404).model_dump()

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "detectors" in updates and req.detectors is not None:
        updates["detectors"] = [d if isinstance(d, dict) else d.model_dump() for d in req.detectors]

    new_status = updates.get("status", system["status"])
    if new_status == "active":
        interval = updates.get("check_interval_seconds", system["check_interval_seconds"])
        monitor_scheduler.schedule(system_id, interval)
    else:
        monitor_scheduler.unschedule(system_id)

    updated = store.update_system(system_id, updates)
    return UnifiedResponse.success(result=updated).model_dump()


@router.delete("/systems/{system_id}")
async def delete_system_api(system_id: str):
    """删除系统并取消调度"""
    monitor_scheduler.unschedule(system_id)
    store.delete_system(system_id)
    return UnifiedResponse.success(result={"deleted": True}).model_dump()


@router.post("/systems/{system_id}/pause")
async def pause_system(system_id: str):
    """暂停监控"""
    store.update_system_status(system_id, "paused")
    monitor_scheduler.unschedule(system_id)
    return UnifiedResponse.success(result={"status": "paused"}).model_dump()


@router.post("/systems/{system_id}/resume")
async def resume_system(system_id: str):
    """恢复监控"""
    system = store.update_system_status(system_id, "active")
    if system:
        monitor_scheduler.schedule(system_id, system["check_interval_seconds"])
    return UnifiedResponse.success(result={"status": "active"}).model_dump()


@router.post("/systems/{system_id}/check")
async def manual_check(system_id: str):
    """手动触发一次检测（立即看到结果）"""
    system = store.get_system(system_id)
    if system is None:
        return UnifiedResponse.error(error_message="系统不存在", code=404).model_dump()

    from app.scheduler.engine import monitor_scheduler
    incident = await alert_pipeline.run(system, auto_push=False)
    if incident:
        store.create_incident(incident)
        return UnifiedResponse.success(result={"status": "anomaly", "incident": incident}).model_dump()
    else:
        store.update_health_score(system_id, min(100, system.get("health_score", 100) + 5))
        return UnifiedResponse.success(result={"status": "healthy"}).model_dump()


# ==================== 检测器 ====================

@router.get("/detectors")
async def list_detectors():
    """列出所有可用的检测器类型"""
    return UnifiedResponse.success(result={"detectors": DetectorRegistry.list_details()}).model_dump()


# ==================== 仪表盘 ====================

@router.get("/monitoring/status")
async def dashboard_status():
    """监控仪表盘聚合状态"""
    systems = store.list_systems()
    incidents = store.list_incidents(limit=200)
    open_incidents = [i for i in incidents if i.get("status") == "open"]

    return UnifiedResponse.success(result={
        "systems_total": len(systems),
        "systems_active": len([s for s in systems if s.get("status") == "active"]),
        "systems_healthy": len([s for s in systems if s.get("health_score", 100) >= 80]),
        "active_alerts": len(open_incidents),
        "critical_alerts": len([i for i in open_incidents if i.get("severity") == "critical"]),
        "recent_incidents": open_incidents[:5],
        "systems": [{
            "id": s["id"], "name": s["name"], "status": s.get("status"),
            "health_score": s.get("health_score", 100),
            "last_checked_at": s.get("last_checked_at"),
            "scheduled": monitor_scheduler.is_scheduled(s["id"]),
        } for s in systems],
    }).model_dump()


# ==================== 故障历史 ====================

@router.get("/incidents")
async def list_incidents_api(
    system_id: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """故障列表"""
    incidents = store.list_incidents(system_id=system_id, severity=severity, status=status, limit=limit)
    return UnifiedResponse.success(result={"incidents": incidents, "total": len(incidents)}).model_dump()


@router.get("/incidents/{incident_id}")
async def get_incident_api(incident_id: str):
    """故障详情（含完整诊断报告）"""
    incident = store.get_incident(incident_id)
    if incident is None:
        return UnifiedResponse.error(error_message="故障记录不存在", code=404).model_dump()
    return UnifiedResponse.success(result=incident).model_dump()


@router.put("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str):
    """确认故障"""
    store.update_incident_status(incident_id, "acknowledged")
    return UnifiedResponse.success(result={"status": "acknowledged"}).model_dump()


@router.put("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str):
    """解决故障"""
    store.update_incident_status(incident_id, "resolved")
    return UnifiedResponse.success(result={"status": "resolved"}).model_dump()


@router.post("/incidents/{incident_id}/push")
async def push_incident(incident_id: str):
    """推送故障报告到飞书"""
    incident = store.get_incident(incident_id)
    if incident is None:
        return UnifiedResponse.error(error_message="故障记录不存在", code=404).model_dump()

    # 推送飞书
    from app.alert.pipeline import _build_push_content
    content = _build_push_content(
        incident.get('system_name', ''),
        incident.get('anomalies', []),
        incident.get('report_markdown', '')
    )

    if alert_pipeline.feishu:
        title = f"🔴 {incident['system_name']} 故障告警" if incident['severity'] == 'critical' else f"🟡 {incident['system_name']} 异常通知"
        alert_pipeline.feishu.send_markdown(title, content[:3000])

    store.update_incident_status(incident_id, "open")
    return UnifiedResponse.success(result={"status": "open", "pushed": True}).model_dump()
