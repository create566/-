"""告警管道 — Agent 智能检测入口"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from app.dao import store


class AlertPipeline:
    """全自动告警处理管道

    流程: 加载历史 → Agent 智能检测+诊断 → 飞书推送 → 存储故障记录

    auto_push=True  (定时器触发): 直接保存+推送飞书
    auto_push=False (手动检测):   保存为pending，前端确认后推送
    """

    def __init__(self, feishu_notifier=None):
        self.feishu = feishu_notifier
        self._last_alert: dict[str, float] = {}
        self._last_normal_push: dict[str, float] = {}  # 正常状态推送节流

    async def run(self, system: dict, auto_push: bool = True) -> Optional[dict]:
        system_id = system["id"]
        system_name = system.get("name", system_id)

        # ① 冷却检查 — 仅自动模式，60秒内同系统不重复
        now = datetime.now().timestamp()
        if auto_push and system_id in self._last_alert:
            if now - self._last_alert[system_id] < 60:
                logger.debug(f"[{system_name}] 冷却中，跳过")
                return None

        # ② 加载历史数据
        history = store.get_check_history(system_id, limit=60)

        # ③ Agent 智能检测
        from app.agent.graph import agent_graph
        try:
            result = await agent_graph.ainvoke({
                "system_id": system_id,
                "system_name": system_name,
                "system_type": system.get("system_type", ""),
                "endpoint": system.get("endpoint", ""),
                "auth": system.get("auth"),
                "detectors": system.get("detectors", []),
                "history": history,
                "phase": "checking",
                "plan": [], "current_step": 0,
                "results": [], "anomalies": [], "diagnosis_rounds": 0,
                "messages": [], "knowledge": "",
                "severity": "normal", "root_cause": "", "report": "",
            }, config={"configurable": {"thread_id": system_id}})
        except Exception as e:
            logger.error(f"Agent 执行失败 [{system_name}]: {e}")
            return None

        # ④ 记录检测历史
        agent_results = result.get("results", [])
        if not agent_results:
            from app.detectors.manager import DetectorManager
            dm = DetectorManager()
            raw_results = await dm.run_checks(system)
            agent_results = [{
                "detector": r.detector_name, "metric": r.metric_name,
                "value": r.current_value, "severity": r.severity,
                "message": r.message, "timestamp": r.timestamp,
            } for r in raw_results]

        store.save_check_history([{
            "system_id": system_id,
            "detector_name": r.get("detector_name", ""),
            "metric_name": r.get("metric_name", ""),
            "metric_value": r.get("current_value", r.get("metric_value", 0)),
            "severity": r.get("severity", "normal"),
            "checked_at": r.get("timestamp", datetime.now(timezone.utc).isoformat()),
        } for r in agent_results])

        # ⑤ 无异常
        if result.get("severity") == "normal":
            store.update_health_score(system_id, min(100, system.get("health_score", 100) + 5))
            return None

        # ⑥ 有异常
        severity = result.get("severity", "warning")
        report = result.get("report", "")
        root_cause = result.get("root_cause", "未知")
        anomalies_list = result.get("anomalies", [])

        self._last_alert[system_id] = now
        logger.warning(f"[{system_name}] 检测到异常! severity={severity} auto_push={auto_push}")

        # ⑦ 飞书推送 — 自动模式直接推，手动模式等确认
        msg_id = None
        if auto_push and self.feishu and system.get("alert_enabled", True):
            try:
                title = f"🔴 {system_name} 故障告警" if severity == "critical" else f"🟡 {system_name} 异常通知"
                push_content = _build_push_content(system_name, agent_results, report)
                self.feishu.send_markdown(title, push_content[:3000])
                msg_id = "sent"
            except Exception as e:
                logger.error(f"飞书推送失败: {e}")

        # ⑧ 保存报告为 Markdown 文件
        incident_id = str(uuid.uuid4())
        if report:
            store.save_report_md(incident_id, report)

        # ⑨ 构建故障记录
        incident = {
            "id": incident_id,
            "system_id": system_id,
            "system_name": system_name,
            "severity": severity,
            "title": f"{system_name} — {root_cause[:100]}" if root_cause else f"{system_name} 异常",
            "description": root_cause,
            "report": report,
            "anomalies": [{
                "detector_name": a.get("detector_name", ""), "metric_name": a.get("metric_name", ""),
                "metric_value": a.get("metric_value", 0), "severity": a.get("severity", ""),
                "message": a.get("message", ""),
            } for a in anomalies_list],
            "feishu_message_id": msg_id,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "status": "open" if auto_push else "pending",
        }

        # ⑨ 扣减健康分
        penalty = 20 if severity == "critical" else 10
        store.update_health_score(system_id, max(0, system.get("health_score", 100) - penalty))

        return incident


def _build_push_content(system_name: str, metrics: list[dict], report: str) -> str:
    """构建飞书推送内容 = 异常指标表格 + 诊断摘要（去重+精简）"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 异常指标表格
    lines = [
        f"**📋 {system_name} — 故障告警**",
        "",
        f"🕐 **{now_str}**",
        "",
        "**📊 异常指标**",
        "| 检测器 | 指标 | 当前值 | 状态 |",
        "|--------|------|--------|------|",
    ]
    for m in metrics:
        name = m.get("detector_name", "unknown")
        metric = m.get("metric_name", "?")
        val = m.get("metric_value", "?")
        sev = m.get("severity", "normal")
        icon = {"critical": "🔴", "warning": "🟡", "normal": "🟢", "error": "⚠️"}.get(sev, "⚪")
        lines.append(f"| {name} | {metric} | **{val}** | {icon} |")

    # 诊断报告去重+精简
    if report:
        clean_report = _deduplicate_report(report)
        # 取报告前半部分（通常有摘要/根因），截断
        lines.append("")
        lines.append("**📝 诊断摘要**")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        max_len = 2500
        truncated = clean_report[:max_len] + ("..." if len(clean_report) > max_len else "")
        lines.append(truncated)

    return "\n".join(lines)


def _deduplicate_report(report: str) -> str:
    """去除报告中的重复段落，保留去重后的内容"""
    if not report:
        return ""
    # 按行处理，去除连续重复的行
    lines = report.split("\n")
    seen_lines = []
    prev_line = None
    repeat_count = 0
    max_repeat = 3  # 同一行连续出现超过3次就截断

    for line in lines:
        stripped = line.strip()
        # 跳过水平线和空行
        if stripped in ("---", "***", "___") or not stripped:
            if prev_line is not None:
                seen_lines.append(line)  # 保留分隔符
                prev_line = line
                repeat_count = 0
            continue
        # 检测重复建议行（如"数据清理：..."这类重复建议）
        if stripped == prev_line:
            repeat_count += 1
            if repeat_count > max_repeat:
                continue  # 跳过重复行
        else:
            repeat_count = 0
        seen_lines.append(line)
        prev_line = stripped

    return "\n".join(seen_lines)


# 全局单例
alert_pipeline = AlertPipeline()
