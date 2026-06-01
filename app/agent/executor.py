"""Executor — 逐步执行检测/诊断计划"""

from loguru import logger
from app.agent.state import AgentState
from app.detectors.registry import DetectorRegistry


async def executor(state: AgentState) -> dict:
    """执行当前步骤，调用对应的检测器工具"""
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    results = list(state.get("results", []))
    messages = list(state.get("messages", []))

    if current_step >= len(plan):
        # 计划执行完毕
        return {"results": results, "messages": messages}

    step = plan[current_step]
    action = step.get("action", "noop")
    params = step.get("params", {})

    if action == "noop":
        step["status"] = "skipped"
        return {
            "results": results,
            "current_step": current_step + 1,
            "messages": messages,
        }

    # ① 从注册中心获取检测器实例
    config = params.get("config", {})
    detector = DetectorRegistry.get_or_create(action, config=config)
    if detector is None:
        logger.warning(f"Executor: 未找到检测器 {action}")
        step["status"] = "error"
        results.append({
            "step": step["step"], "detector": action,
            "metric": "unknown", "value": 0, "severity": "error",
            "message": f"未知检测器: {action}",
        })
        return {
            "results": results,
            "current_step": current_step + 1,
            "messages": messages,
        }

    # ② 执行检测
    try:
        result = await detector.check(
            system_id=state.get("system_id", ""),
            system_name=state.get("system_name", ""),
            endpoint=state.get("endpoint", ""),
            thresholds=params.get("thresholds", {}),
            auth=state.get("auth"),
        )
        step["status"] = "done"

        run_result = {
            "step": step["step"],
            "detector": result.detector_name,
            "metric": result.metric_name,
            "value": result.current_value,
            "severity": result.severity,
            "message": result.message,
            "raw_data": result.raw_data,
            "timestamp": result.timestamp,
        }
        results.append(run_result)

        logger.info(
            f"Executor: [{state.get('system_name', '?')}] {action} → "
            f"{result.metric_name}={result.current_value} ({result.severity})"
        )

        # 如果是异常，记录
        if result.is_anomalous:
            anomalies = list(state.get("anomalies", []))
            anomalies.append(run_result)
            return {
                "results": results,
                "anomalies": anomalies,
                "current_step": current_step + 1,
                "messages": messages,
            }

    except Exception as e:
        logger.error(f"Executor: {action} 执行失败: {e}")
        step["status"] = "error"
        results.append({
            "step": step["step"], "detector": action,
            "metric": detector.metric_name, "value": 0, "severity": "error",
            "message": f"执行失败: {e}",
        })

    return {
        "results": results,
        "current_step": current_step + 1,
        "messages": messages,
    }


def should_continue_execution(state: AgentState) -> str:
    """判断是否继续执行计划中的下一步"""
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    if current_step >= len(plan):
        return "review"   # 全部执行完 → 交给 Replanner
    return "continue"     # 还有步骤 → 继续执行
