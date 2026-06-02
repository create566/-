"""Replanner — 智能判断：去毛刺、看趋势、关联分析、决定下一步"""

import json
from langchain_core.messages import HumanMessage
from app.core.llm_factory import llm_factory
from app.agent.state import AgentState
from app.agent.knowledge_search import search, search_knowledge_vector
from loguru import logger


async def replanner(state: AgentState) -> dict:
    """综合判断：是否需要告警？是否需要深度诊断？还是出报告？"""
    # 用更快的模型生成报告，避免超时
    llm = llm_factory.create_chat_model(temperature=0.3, streaming=False, timeout=45, max_tokens=2000)

    phase = state.get("phase", "checking")
    results = state.get("results", [])
    anomalies = state.get("anomalies", [])
    history = state.get("history", [])
    diagnosis_rounds = state.get("diagnosis_rounds", 0)

    # 没有异常 → 正常
    if not anomalies:
        logger.info(f"Replanner: [{state.get('system_name')}] 一切正常")
        return {
            "severity": "normal",
            "root_cause": "",
            "report": "",
            "phase": "done",
            "anomalies": [],
        }

    # ① 先做本地规则判断（快速过滤明显毛刺）
    quick_judgment = _quick_judge(anomalies, history)
    if quick_judgment == "normal":
        logger.info(f"Replanner: 毛刺过滤，不告警")
        return {
            "severity": "normal",
            "root_cause": "",
            "report": "",
            "phase": "done",
            "anomalies": [],
        }

    # ② LLM 深度判断
    results_text = "\n".join(
        f"- {r.get('detector_name','')}: {r.get('metric_name','')}={r.get('metric_value','')} ({r.get('severity','')}) — {r.get('message','')}"
        for r in results
    )
    anomalies_text = "\n".join(
        f"- {a.get('detector_name','')}: {a.get('metric_name','')}={a.get('metric_value','')} ({a.get('severity','')})"
        for a in anomalies
    )
    history_text = _format_history_trend(history)

    # 检测完成 → 直接出报告（诊断在一次LLM分析中完成）
    return await _generate_report(state, llm, anomalies, results, history_text)

    # 默认出报告
    return await _generate_report(state, llm, anomalies, results, history_text)


async def _generate_report(state: AgentState, llm, anomalies, results, history_text) -> dict:
    """生成最终诊断报告 — 使用知识库增强专业术语"""
    system_name = state.get("system_name", "")
    results_text = "\n".join(
        f"| {r.get('detector_name','')} | {r.get('metric_name','')} | {r.get('metric_value','')} | {r.get('severity','')} | {r.get('message','')} |"
        for r in results
    )

    # ★ 知识库检索（优先向量检索，失败降级 TAG_INDEX）
    knowledge = await search(anomalies)
    knowledge_text = knowledge[:2000] if knowledge else "（暂无相关知识库参考）"

    severity = max(
        (a.get("severity", "warning") for a in anomalies),
        key=lambda s: {"critical": 3, "warning": 2, "normal": 1, "error": 2}.get(s, 0)
    )

    prompt = f"""你是资深运维专家，需要生成一份专业的故障诊断报告。

## 系统信息
- 名称: {system_name}
- 类型: {state.get('system_type', '')}
- 地址: {state.get('endpoint', '')}

## 检测结果
| 检测器 | 指标 | 当前值 | 严重程度 | 说明 |
|--------|------|--------|----------|------|
{results_text}

## 历史趋势
{history_text}

## 专业知识库参考
{knowledge_text}

请生成一份完整的 Markdown 格式故障诊断报告，使用专业知识库中的专业术语和排查框架。报告必须包含：

### 1. 机器当前状态
- 用表格列出所有检测指标及其当前值、阈值、状态（正常/警告/严重）
- 标注异常指标

### 2. 告警摘要
- 什么系统、什么指标异常、严重程度

### 3. 现象描述
- 当前值、历史趋势、关联指标分析
- 使用趋势数据判断是否是真正的故障（而非毛刺）

### 4. 根因分析
- 结合专业知识库中的常见原因，分析最可能的根因
- 使用关联分析法（如: CPU高 + 慢查询暴增 → MySQL可能是根因）
- 引用具体数据作为证据

### 5. 处理建议
- 结合专业知识库中的排查步骤，给出具体可执行的操作
- 按优先级排列（立即操作 / 短期措施 / 长期优化）

### 6. 风险评估
- 如果不处理会导致什么后果
- 引用专业知识库中的影响分析

直接输出完整 Markdown，不要 JSON 包装。语言专业、具体、可执行。"""
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        report = resp.content if hasattr(resp, 'content') else str(resp)
        root_cause = _extract_root_cause(report)

        logger.info(f"Replanner: 报告已生成 ({len(report)} 字符)")
        return {
            "severity": severity,
            "root_cause": root_cause,
            "report": report,
            "phase": "done",
            "anomalies": anomalies,
            "knowledge": knowledge_text,
        }
    except Exception as e:
        logger.error(f"报告生成失败: {e}")
        return {
            "severity": severity,
            "root_cause": f"报告生成失败: {e}",
            "report": f"# 故障报告\n\n## 异常指标\n\n{results_text}\n\n生成失败: {e}",
            "phase": "done",
            "anomalies": anomalies,
        }


def _quick_judge(anomalies: list, history: list) -> str:
    """本地快速判断：过滤明显的单次毛刺"""
    if not anomalies:
        return "normal"

    for a in anomalies:
        detector = a.get("detector_name", "")
        value = a.get("metric_value", 0)

        # 找历史中这个检测器的最近值
        hist_values = []
        for h in history:
            if h.get("detector_name") == detector:
                hist_values.append(h.get("metric_value", 0))

        if len(hist_values) >= 4:
            # 检查是否是毛刺：前4次都正常，只有这次高
            recent = hist_values[-4:]
            avg_recent = sum(recent) / len(recent)
            if avg_recent < 50 and value > 80:
                # 可能毛刺，但不绝对——如果有其他指标也异常则保留
                if len(anomalies) == 1:
                    logger.info(f"快速判断: {detector} 可能是毛刺 (前4次均值{avg_recent:.1f}, 当前{value})")
                    return "normal"
    return "anomaly"


def _should_diagnose(anomalies: list, history: list) -> bool:
    """判断是否需要深度诊断"""
    # 规则1: 多指标异常 → 需要诊断（可能是关联故障）
    if len(anomalies) >= 2:
        return True

    # 规则2: critical 级别 → 需要诊断
    if any(a.get("severity") == "critical" for a in anomalies):
        return True

    # 规则3: 趋势持续恶化 → 需要诊断
    for a in anomalies:
        detector = a.get("detector_name", "")
        hist_values = []
        for h in history:
            if h.get("detector_name") == detector:
                hist_values.append(h.get("metric_value", 0))
        if len(hist_values) >= 3:
            recent = hist_values[-3:]
            if all(recent[i] < recent[i + 1] for i in range(len(recent) - 1)):
                return True  # 连续上涨

    return False


def _format_history_trend(history: list) -> str:
    """格式化历史趋势"""
    if not history:
        return "无历史数据"
    by_detector = {}
    for h in history[-60:]:
        name = h.get("detector_name", "unknown")
        if name not in by_detector:
            by_detector[name] = []
        by_detector[name].append(h.get("metric_value", 0))

    lines = []
    for name, values in by_detector.items():
        if len(values) >= 2:
            trend = "持续上升" if values[-1] > values[0] else "持续下降" if values[-1] < values[0] else "平稳"
            lines.append(f"- {name}: {trend}，最近值: {' → '.join(str(v) for v in values[-5:])}")
        else:
            lines.append(f"- {name}: 当前值 {values[0] if values else 'N/A'}")
    return "\n".join(lines)


def _extract_root_cause(report: str) -> str:
    """从报告中提取根因摘要"""
    for line in report.split("\n"):
        line = line.strip()
        if "根因" in line and ("：" in line or ":" in line):
            return line.strip("# ").strip()
    # 取报告前100字作为摘要
    return report[:100].replace("#", "").replace("\n", " ").strip()


def _extract_json(text: str) -> str:
    """从 LLM 输出中提取 JSON"""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()


def decide_next(state: AgentState) -> str:
    """决定下一步：检测完直接结束"""
    phase = state.get("phase", "done")
    return "done" if phase == "done" else "done"
