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
        incident["status"] = "pending"  # 手动检测，用户可以在故障记录中手动推送
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


# ==================== 飞书机器人交互 ====================

class FeishuHandleRequest(BaseModel):
    text: str = Field(default="", description="用户发送给机器人的文本")


@router.post("/feishu/handle")
async def feishu_handle(req: FeishuHandleRequest):
    """飞书机器人 @消息处理 — 解析命令并返回回复"""
    text = req.text.strip()
    if not text:
        return {"reply": ""}

    t = text.lower()

    # ── 帮助 ──
    if any(kw in t for kw in ["帮助", "help", "功能", "命令", "?", "？"]):
        return {"reply": _build_help()}

    # ── 系统列表 & 总览状态 ──
    if any(kw in t for kw in ["状态", "总览", "概览", "列表", "list", "status", "系统列表", "所有"]):
        return {"reply": _build_status_overview()}

    # ── 故障/告警列表 ──
    if any(kw in t for kw in ["故障", "告警", "incident", "警报", "报警"]):
        return {"reply": _build_incidents_list()}

    # ── 手动检测指定系统 ──
    if any(kw in t for kw in ["检测", "检查", "诊断", "check", "diagnose"]):
        system_name = _extract_name(text, ["检测", "检查", "诊断", "check", "diagnose"])
        if system_name:
            return {"reply": await _trigger_manual_check(system_name)}
        return {"reply": "⚠️ 请指定要检测的系统名称，例如：检测 用户服务"}

    # ── 查询指定系统详情 ──
    if any(kw in t for kw in ["查询", "详情", "detail", "query", "查看", "系统"]):
        system_name = _extract_name(text, ["查询", "详情", "detail", "query", "查看", "系统"])
        if system_name:
            return {"reply": _build_system_detail(system_name)}
        # 没提取到名字，返回总览
        return {"reply": _build_status_overview()}

    # ── 报告 ──
    if any(kw in t for kw in ["报告", "report", "诊断报告"]):
        system_name = _extract_name(text, ["报告", "report", "诊断报告"])
        if system_name:
            return {"reply": _build_report(system_name)}
        return {"reply": "⚠️ 请指定系统名称，例如：报告 用户服务"}

# ── 暂停监控系统 ──
    if any(kw in t for kw in ["暂停", "停止监控", "停止检测", "pause"]):
        system_name = _extract_name(text, ["暂停", "停止监控", "停止检测", "pause"])
        if system_name:
            return {"reply": _pause_system(system_name)}
        return {"reply": "⚠️ 请指定要暂停的系统，例如：暂停 本机监控"}

    # ── 恢复监控系统 ──
    if any(kw in t for kw in ["恢复", "重启监控", "resume", "继续"]):
        system_name = _extract_name(text, ["恢复", "重启监控", "resume", "继续"])
        if system_name:
            return {"reply": _resume_system(system_name)}
        return {"reply": "⚠️ 请指定要恢复的系统，例如：恢复 本机监控"}

    # ── 历史趋势图 ──
    if any(kw in t for kw in ["趋势", "图表", "趋势图", "chart", "trend", "history", "历史"]):
        system_name = _extract_name(text, ["趋势", "图表", "趋势图", "chart", "trend", "history", "历史"])
        if system_name:
            return {"reply": _build_trend_chart(system_name)}
        return {"reply": "⚠️ 请指定系统，例如：趋势 本机监控"}

    # ── 默认：尝试按系统名搜索 ──
    systems = store.list_systems()
    for s in systems:
        if s.get("name", "").lower() in t:
            return {"reply": _build_system_detail(s["name"])}

    # ── 自由对话：交给 LLM 处理 ──
    return {"reply": await _free_chat(text)}


# ──────── 辅助函数 ────────

def _extract_name(text: str, keywords: list[str]) -> str:
    """从文本中提取系统名称，移除关键词和噪音词后返回剩余部分"""
    result = text
    for kw in sorted(keywords, key=len, reverse=True):
        import re
        result = re.sub(kw, "", result, flags=re.IGNORECASE)
    # 移除常见噪音词
    noise_words = ["状态", "详情", "信息", "系统", "的", "一下", "帮我", "请", "给我",
                   "status", "detail", "info", "please", "the", "给我看看", "查一查"]
    for nw in sorted(noise_words, key=len, reverse=True):
        result = re.sub(nw, "", result, flags=re.IGNORECASE)
    result = result.strip().strip("：:：,，.。!！?？、 ")
    return result if result else ""


def _build_help() -> str:
    return """🤖 **智能监控助手 — 机器人命令帮助**

━━━━━━━━━━━━━━━━━━━━
📋 监控命令
━━━━━━━━━━━━━━━━━━━━

▸ **状态 / 列表**
  查看所有系统的监控总览

▸ **查询 <系统名>**
  查看指定系统的详细信息

▸ **检测 <系统名>**
  手动触发一次系统检测

▸ **故障 / 告警**
   查看最近的故障和告警记录

▸ **报告 <系统名>**
  查看最新诊断报告

▸ **趋势 <系统名>**
查看系统指标历史趋势图
 ━━━━━━━━━━━
⚙️ 控制命令
━━━━━━━━━━━━━━━━━━━━

▸ **暂停 <系统名>**
   └ 暂停指定系统的定时检测

▸ **恢复 <系统名>**
   └ 恢复指定系统的定时检测

━━━━━━━━━━━━━━━━━━━━
💬 自由对话
━━━━━━━━━━━━━━━━━━━━

▸ 直接 @机器人 提问
   不匹配命令时，自动调用 LLM 回答

▸ **帮助**
   显示本帮助信息

━━━━━━━━━━━━━━━━━━━━
💡 例：@智能监控助手 状态
━━━━━━━━━━━━━━━━━━━━"""


def _build_status_overview() -> str:
    systems = store.list_systems()
    if not systems:
        return "📭 当前没有注册任何监控系统。\n\n去管理端注册系统后，再来查看吧！"

    lines = ["📊 **系统监控总览**", "━━━━━━━━━━━━━━━━━━━━"]
    healthy = paused = inactive = 0
    for s in systems:
        st = s.get("status", "inactive")
        if st == "active":
            healthy += 1
        elif st == "paused":
            paused += 1
        else:
            inactive += 1

    # 汇总行
    summary_parts = []
    if healthy:
        summary_parts.append(f"🟢 正常 {healthy}")
    if paused:
        summary_parts.append(f"⏸️ 暂停 {paused}")
    if inactive:
        summary_parts.append(f"⚪ 未激活 {inactive}")
    lines.append(" | ".join(summary_parts))
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    for s in systems:
        sid = s.get("id", "")[:8]
        name = s.get("name", "?")
        status = s.get("status", "inactive")
        health = s.get("health_score", 100)
        last_check = s.get("last_checked_at", "从未")

        status_icon = {"active": "🟢", "paused": "⏸️", "inactive": "⚪"}.get(status, "⚪")
        health_icon = "💚" if health >= 90 else "💛" if health >= 70 else "🧡" if health >= 50 else "❤️"
        scheduled = monitor_scheduler.is_scheduled(sid) if sid else False

        if last_check and last_check != "从未" and "T" in str(last_check):
            try:
                last_check = str(last_check)[:19].replace("T", " ")
            except Exception:
                pass

        line = f"{status_icon} **{name}**  {health_icon} {health}分"
        if scheduled:
            line += "  ⏰"
        lines.append(line)
        lines.append(f"   └ {last_check}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"共 **{len(systems)}** 个系统")
    return "\n".join(lines)


def _build_system_detail(name: str) -> str:
    systems = store.list_systems()
    matched = None
    for s in systems:
        if s.get("name", "").lower() == name.lower():
            matched = s
            break
    if not matched:
        for s in systems:
            if name.lower() in s.get("name", "").lower():
                matched = s
                break

    if not matched:
        names = [s.get("name", "?") for s in systems]
        return f"❌ 未找到「{name}」\n\n已注册系统:\n" + "\n".join(f"  • {n}" for n in names) if names else "❌ 未找到「{name}」\n\n暂无已注册系统"

    sid = matched.get("id", "?")[:8]
    system_name = matched.get("name", "?")
    status = matched.get("status", "?")
    health = matched.get("health_score", 100)
    endpoint = matched.get("endpoint", "无")
    interval = matched.get("check_interval_seconds", "?")
    detectors = matched.get("detectors", [])

    health_icon = "💚" if health >= 90 else "💛" if health >= 70 else "🧡" if health >= 50 else "❤️"
    status_icon = {"active": "🟢", "paused": "⏸️", "inactive": "⚪"}.get(status, "⚪")
    status_text = {"active": "运行中", "paused": "已暂停", "inactive": "未激活"}.get(status, status)

    lines = [
        f"📋 **{system_name}** 详情",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{status_icon} 状态: **{status_text}**    {health_icon} 健康分: **{health}**",
        f"🔗 地址: `{endpoint}`",
        f"⏱️ 检测间隔: **{interval}s**",
        f"🔧 检测器: **{len(detectors)}** 个",
    ]

    if detectors:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("**检测器配置**")
        for d in detectors[:5]:
            dname = d.get("name", "?")
            thresholds = d.get("thresholds", {})
            w = thresholds.get("warning", "?")
            c = thresholds.get("critical", "?")
            lines.append(f"  • `{dname}`  告警>{w} | 严重>{c}")

    history = store.get_check_history(sid, limit=3)
    if history:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("**最近检测记录**")
        for h in history[:3]:
            ts = h.get("checked_at", "?")
            if "T" in str(ts):
                ts = str(ts)[:19].replace("T", " ")
            sev = h.get("severity", "normal")
            sev_icon = {"critical": "🔴", "warning": "🟡", "normal": "🟢"}.get(sev, "⚪")
            det = h.get("detector_name", "?")
            metric = h.get("metric_name", "?")
            val = h.get("metric_value", "?")
            lines.append(f"{sev_icon} `{ts}`\n   └ {det}: {metric}={val}")

    return "\n".join(lines)


def _build_incidents_list() -> str:
    incidents = store.list_incidents(limit=10)
    if not incidents:
        return "✅ 暂无故障记录\n\n所有系统运行正常，继续保持！"

    open_incidents = [i for i in incidents if i.get("status") in ("open", "acknowledged", "pending")]
    lines = ["🚨 **故障与告警记录**", "━━━━━━━━━━━━━━━━━━━━"]

    if open_incidents:
        critical = [i for i in open_incidents if i.get("severity") == "critical"]
        warning = [i for i in open_incidents if i.get("severity") != "critical"]
        if critical:
            lines.append(f"🔴 **严重告警 ({len(critical)} 条)**")
            for inc in critical[:5]:
                ts = inc.get("detected_at", "?")
                if "T" in str(ts):
                    ts = str(ts)[:19].replace("T", " ")
                lines.append(f"  • **{inc.get('title', inc.get('system_name', '?'))}**")
                lines.append(f"    └ {ts}")
            lines.append("")
        if warning:
            lines.append(f"🟡 **一般告警 ({len(warning)} 条)**")
            for inc in warning[:5]:
                ts = inc.get("detected_at", "?")
                if "T" in str(ts):
                    ts = str(ts)[:19].replace("T", " ")
                lines.append(f"  • **{inc.get('title', inc.get('system_name', '?'))}**")
                lines.append(f"    └ {ts}")
    else:
        lines.append("✅ 没有进行中的故障")
        resolved = [i for i in incidents if i.get("status") == "resolved"][:3]
        if resolved:
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append("**最近已解决**")
            for inc in resolved:
                ts = inc.get("detected_at", "?")
                if "T" in str(ts):
                    ts = str(ts)[:19].replace("T", " ")
                lines.append(f"  ✅ {inc.get('title', '?')}  {ts}")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"共 **{len(incidents)}** 条记录（{len(open_incidents)} 进行中）")
    return "\n".join(lines)


async def _trigger_manual_check(name: str) -> str:
    """手动触发检测并返回结果摘要"""
    systems = store.list_systems()
    matched = None
    for s in systems:
        if s.get("name", "").lower() == name.lower():
            matched = s
            break
    if not matched:
        for s in systems:
            if name.lower() in s.get("name", "").lower():
                matched = s
                break
    if not matched:
        names = [s.get("name", "?") for s in systems]
        return f"❌ 未找到「{name}」\n\n已注册:\n" + "\n".join(f"  • {n}" for n in names) if names else f"❌ 未找到「{name}」"

    if matched.get("status") != "active":
        return (f"⚠️ 「{matched['name']}」当前状态为 **{matched.get('status', 'inactive')}**\n"
                f"请先恢复监控后再试。")

    lines = [f"🔍 **正在检测「{matched['name']}」...**", ""]

    try:
        incident = await alert_pipeline.run(matched, auto_push=True)
        if incident:
            sev = incident.get("severity", "warning")
            icon = "🔴" if sev == "critical" else "🟡"
            title = incident.get("title", "")
            report = incident.get("report", "")
            summary = (report[:600] + "...") if len(report) > 600 else report
            lines.append(f"{icon} **检测完成 — 发现异常！**")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"**{title}**")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(summary)
        else:
            health = matched.get("health_score", 100)
            health_icon = "💚" if health >= 90 else "💛" if health >= 70 else "🧡" if health >= 50 else "❤️"
            lines.append(f"✅ **检测完成 — 系统正常**")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"{health_icon} 健康分: **{health}**  未发现异常")
    except Exception as e:
        logger.error(f"手动检测失败 [{name}]: {e}")
        lines.append(f"❌ 检测失败: {e}")

    return "\n".join(lines)


def _build_report(name: str) -> str:
    """查询系统最新的诊断报告"""
    systems = store.list_systems()
    matched = None
    for s in systems:
        if s.get("name", "").lower() == name.lower():
            matched = s
            break
    if not matched:
        for s in systems:
            if name.lower() in s.get("name", "").lower():
                matched = s
                break
    if not matched:
        names = [s.get("name", "?") for s in systems]
        return f"❌ 未找到「{name}」\n\n已注册:\n" + "\n".join(f"  • {n}" for n in names) if names else f"❌ 未找到「{name}」"

    sid = matched.get("id", "")
    incidents = store.list_incidents(system_id=sid, limit=5)
    if not incidents:
        return f"📭 「{matched['name']}」暂无诊断报告\n\n先去触发一次检测吧！"

    latest = incidents[0]
    report = latest.get("report", "")
    ts = latest.get("detected_at", "?")
    if "T" in str(ts):
        ts = str(ts)[:19].replace("T", " ")

    sev = latest.get("severity", "warning")
    sev_icon = {"critical": "🔴", "warning": "🟡", "normal": "🟢"}.get(sev, "⚪")

    lines = [
        f"📄 **{matched['name']}** 最新诊断报告",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{sev_icon} 检测时间: `{ts}`",
        f"📌 状态: **{latest.get('status', '?')}**",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if report:
        max_len = 1800
        truncated = report[:max_len] + ("..." if len(report) > max_len else "")
        lines.append(truncated)
    else:
        lines.append("(无诊断报告内容)")
        if latest.get("title"):
            lines.append(f"标题: {latest.get('title')}")

    return "\n".join(lines)


# ──────── 暂停 / 恢复系统 ────────

def _pause_system(name: str) -> str:
    """暂停指定系统的定时检测"""
    systems = store.list_systems()
    matched = None
    for s in systems:
        if s.get("name", "").lower() == name.lower():
            matched = s
            break
    if not matched:
        for s in systems:
            if name.lower() in s.get("name", "").lower():
                matched = s
                break
    if not matched:
        names = [s.get("name", "?") for s in systems]
        return f"❌ 未找到「{name}」\n\n已注册:\n" + "\n".join(f"  • {n}" for n in names) if names else f"❌ 未找到「{name}」"

    sid = matched.get("id", "")
    if matched.get("status") != "active":
        return f"⚠️ 「{matched['name']}」当前状态是 **{matched.get('status', 'inactive')}**，无需暂停。"

    monitor_scheduler.unschedule(sid)
    store.update_system_status(sid, "paused")
    return f"✅ 已暂停「{matched['name']}」的定时检测\n\n系统已进入休眠状态，不会再自动检测。要恢复请说：恢复 {matched['name']}"


def _resume_system(name: str) -> str:
    """恢复指定系统的定时检测"""
    systems = store.list_systems()
    matched = None
    for s in systems:
        if s.get("name", "").lower() == name.lower():
            matched = s
            break
    if not matched:
        for s in systems:
            if name.lower() in s.get("name", "").lower():
                matched = s
                break
    if not matched:
        names = [s.get("name", "?") for s in systems]
        return f"❌ 未找到「{name}」\n\n已注册:\n" + "\n".join(f"  • {n}" for n in names) if names else f"❌ 未找到「{name}」"

    sid = matched.get("id", "")
    interval = matched.get("check_interval_seconds", 60)
    store.update_system_status(sid, "active")
    monitor_scheduler.schedule(sid, interval)
    return (f"✅ 已恢复「{matched['name']}」的定时检测\n\n"
            f"检测间隔: **{interval}s**\n"
            f"系统已恢复正常监控。")


# ──────── 历史趋势图 ────────

def _build_trend_chart(name: str) -> str:
    """生成 ASCII 趋势图，展示系统最近检测指标"""
    systems = store.list_systems()
    matched = None
    for s in systems:
        if s.get("name", "").lower() == name.lower():
            matched = s
            break
    if not matched:
        for s in systems:
            if name.lower() in s.get("name", "").lower():
                matched = s
                break
    if not matched:
        names = [s.get("name", "?") for s in systems]
        return f"❌ 未找到「{name}」\n\n已注册:\n" + "\n".join(f"  • {n}" for n in names) if names else f"❌ 未找到「{name}」"

    sid = matched.get("id", "")
    history = store.get_check_history(sid, limit=20)

    if not history:
        return f"📭 「{matched['name']}」暂无检测历史数据\n\n等待下次定时检测完成后即可查看趋势。"

    from collections import defaultdict
    by_detector = defaultdict(list)
    for h in reversed(history):
        by_detector[h.get("detector_name", "?")].append(h)

    lines = [
        f"📈 **{matched['name']}** 指标趋势（最近 {len(history)} 条）",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for det_name, records in sorted(by_detector.items()):
        if not records:
            continue
        values = [r.get("metric_value", 0) for r in records]
        max_val = max(values) if values else 1
        min_val = min(values) if values else 0
        val_range = max(max_val - min_val, 0.01)

        lines.append(f"\n**{det_name}**")

        chart_len = 7
        step = max(len(values) // chart_len, 1)
        sampled = values[::step][:chart_len]

        bars = []
        for v in sampled:
            ratio = (v - min_val) / val_range
            filled = int(ratio * 8)
            bars.append("▏" * filled + "░" * (8 - filled))

        lines.append("  " + "  ".join(bars))
        lines.append(f"  └ 最新: **{values[-1]:.1f}**  范围: {min_val:.1f}~{max_val:.1f}")

        detectors = matched.get("detectors", [])
        for d in detectors:
            if d.get("name") == det_name:
                thresh = d.get("thresholds", {})
                w = thresh.get("warning")
                c = thresh.get("critical")
                if w:
                    lines.append(f"     告警>{w}")
                if c:
                    lines.append(f"     严重>{c}")
                break

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


# ──────── 自由对话 ────────

async def _free_chat(question: str) -> str:
    """调用 vLLM 做自由对话回答"""
    try:
        from app.core.llm_factory import LLMFactory
        from langchain_core.messages import HumanMessage

        llm = LLMFactory.create_chat_model(max_tokens=500, timeout=30)

        systems = store.list_systems()
        sys_info = "\n".join([
            f"- {s.get('name','?')} (状态:{s.get('status','?')}, 健康分:{s.get('health_score',100)})"
            for s in systems
        ]) or "暂无注册系统"

        prompt = (
            f"你是智能监控平台的 AI 助手。用户通过飞书 @机器人 提问。\n"
            f"已知监控系统列表：\n{sys_info}\n\n"
            f"用户问题：{question}\n\n"
            f"请用简洁、友好的语气回答，简短（不超过 200 字），重点突出。回答内容基于以上监控数据。"
        )

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        answer = response.content.strip()
        if len(answer) > 600:
            answer = answer[:600] + "..."
        return answer

    except Exception as e:
        logger.error(f"自由对话失败: {e}")
        return "🤖 抱歉，LLM 暂时无法回答这个问题。"
