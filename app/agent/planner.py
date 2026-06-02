"""Planner — LLM 制定检测/诊断计划"""

import json
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.llm_factory import llm_factory
from app.agent.state import AgentState
from loguru import logger


async def planner(state: AgentState) -> dict:
    """根据 phase 制定检测计划或诊断计划"""
    llm = llm_factory.create_chat_model(temperature=0.3, streaming=False, timeout=20)

    phase = state.get("phase", "checking")
    results = state.get("results", [])

    if phase == "checking":
        return await _make_check_plan(state, llm)
    elif phase == "diagnosing":
        return await _make_diagnosis_plan(state, llm)
    else:
        return {"plan": []}


async def _make_check_plan(state: AgentState, llm) -> dict:
    """制定检测计划：按优先级排列要执行的检测器"""
    detectors = state.get("detectors", [])
    history = state.get("history", [])

    if not detectors:
        # 没有配置检测器，用一条空计划
        return {"plan": [{"step": 1, "action": "noop", "params": {}, "reason": "无检测器配置", "status": "pending"}]}

    # 简单情况：检测器 ≤ 3 个，不需要 LLM 规划，直接排好
    if len(detectors) <= 3:
        plan = []
        for i, dc in enumerate(detectors, 1):
            plan.append({
                "step": i, "action": dc["name"],
                "params": {"thresholds": dc.get("thresholds", {}), "config": dc.get("config", {})},
                "reason": f"检测 {dc['name']}", "status": "pending"
            })
        return {"plan": plan}

    # 复杂情况：让 LLM 优化检测顺序（先查轻量、再查重的）
    detector_text = "\n".join(
        f"- {d['name']}: {d.get('thresholds', {})}" for d in detectors
    )
    history_text = _format_history(history)

    prompt = f"""你是运维专家，需要为系统制定检测顺序。

## 系统
- 名称: {state.get('system_name', '')}
- 类型: {state.get('system_type', '')}

## 配置的检测器
{detector_text}

## 最近历史
{history_text if history_text else '无历史数据'}

请制定检测计划，优先检查最可能出问题的指标。输出纯JSON:
{{"plan": [{{"step": 1, "action": "detector_name", "reason": "为什么先查这个"}}]}}
"""
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = _extract_json(resp.content if hasattr(resp, 'content') else str(resp))
        data = json.loads(text)
        # 补充 params
        for item in data.get("plan", []):
            item["status"] = "pending"
            if "params" not in item:
                # 从 detectors 配置中匹配 params
                for dc in detectors:
                    if dc["name"] == item["action"]:
                        item["params"] = {"thresholds": dc.get("thresholds", {}), "config": dc.get("config", {})}
                        break
        logger.info(f"Planner(C): 生成了{len(data.get('plan', []))}步检测计划")
        return {"plan": data.get("plan", [])}
    except Exception as e:
        logger.error(f"Planner(C) 失败: {e}，使用默认顺序")
        plan = []
        for i, dc in enumerate(detectors, 1):
            plan.append({
                "step": i, "action": dc["name"],
                "params": {"thresholds": dc.get("thresholds", {}), "config": dc.get("config", {})},
                "reason": f"检测 {dc['name']}", "status": "pending"
            })
        return {"plan": plan}


async def _make_diagnosis_plan(state: AgentState, llm) -> dict:
    """制定深度诊断计划"""
    anomalies = state.get("anomalies", [])
    results = state.get("results", [])
    diagnosis_rounds = state.get("diagnosis_rounds", 0)

    anomaly_text = "\n".join(
        f"- {a.get('detector_name','')}: {a.get('metric_name','')}={a.get('metric_value','')} ({a.get('severity','')})"
        for a in anomalies
    )
    results_text = "\n".join(
        f"- {r.get('detector_name','')}: {r.get('metric_name','')}={r.get('metric_value','')}" for r in results
    )

    prompt = f"""你是资深运维专家，需要深度排查系统故障。

## 异常指标
{anomaly_text}

## 已有检测数据
{results_text}

## 当前已排查 {diagnosis_rounds} 轮

请制定下一步排查计划。可以查询以下类型的数据:
- prometheus_cpu / prometheus_memory (查更多Prometheus指标)
- mysql_slow_queries (查慢查询详情)
- redis_memory (查Redis内存/连接)
- http_health (验证服务状态)

输出纯JSON:
{{"plan": [{{"step": 1, "action": "detector_name", "params": {{}}, "reason": "为什么要查这个"}}]}}

如果觉得信息够多了不需要再查，输出: {{"plan": []}}
"""
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = _extract_json(resp.content if hasattr(resp, 'content') else str(resp))
        data = json.loads(text)
        for item in data.get("plan", []):
            item["status"] = "pending"
        logger.info(f"Planner(D): 第{diagnosis_rounds + 1}轮诊断，{len(data.get('plan', []))}步")
        return {"plan": data.get("plan", []), "diagnosis_rounds": diagnosis_rounds + 1}
    except Exception as e:
        logger.error(f"Planner(D) 失败: {e}")
        return {"plan": [], "diagnosis_rounds": diagnosis_rounds + 1}


def _format_history(history: list) -> str:
    """格式化历史数据为文本"""
    if not history:
        return ""
    # 按检测器分组取最近值
    by_detector = {}
    for h in history[-50:]:
        name = h.get("detector_name", "unknown")
        if name not in by_detector:
            by_detector[name] = []
        by_detector[name].append(h.get("metric_value", 0))

    lines = []
    for name, values in by_detector.items():
        trend = " → ".join(str(v) for v in values[-5:])
        lines.append(f"- {name}: {trend}")
    return "\n".join(lines)


def _extract_json(text: str) -> str:
    """从 LLM 输出中提取 JSON"""
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()
