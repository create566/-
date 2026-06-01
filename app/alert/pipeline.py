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
            "detector_name": r.get("detector", ""),
            "metric_name": r.get("metric", ""),
            "metric_value": r.get("value", 0),
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
            "report_markdown": report,
            "anomalies": [{
                "detector": a.get("detector", ""), "metric": a.get("metric", ""),
                "value": a.get("value", 0), "severity": a.get("severity", ""),
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
    """构建飞书推送内容 = 机器状态摘要 + 诊断报告"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_lines = [f"**系统名称**: {system_name}", f"**检测时间**: {now_str}", "", "**📊 当前机器状态**", ""]
    status_lines.append("| 检测器 | 指标值 | 状态 |")
    status_lines.append("|--------|--------|------|")
    for m in metrics:
        name = m.get("detector", "?")
        val = m.get("value", "?")
        sev = m.get("severity", "normal")
        icon = {"critical": "🔴", "warning": "🟡", "normal": "🟢", "error": "⚠️"}.get(sev, "⚪")
        status_lines.append(f"| {name} | {val} | {icon} {sev} |")
    status_text = "\n".join(status_lines)

    # 截断报告以适应飞书卡片限制
    max_report_len = 3000 - len(status_text) - 20
    truncated_report = report[:max_report_len] if len(report) > max_report_len else report

    return status_text + "\n\n---\n\n" + truncated_report


# 全局单例
alert_pipeline = AlertPipeline()
