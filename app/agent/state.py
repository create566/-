"""Agent 状态定义"""

from typing import TypedDict, Annotated, Sequence, Optional, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Plan-Execute-Replan Agent 的状态"""

    # 系统信息
    system_id: str
    system_name: str
    system_type: str
    endpoint: str
    auth: Optional[dict]

    # 检测器配置 [{name, thresholds, config}]
    detectors: list[dict]

    # 历史数据（趋势分析用）
    history: list[dict]

    # 当前执行计划
    plan: list[dict]          # [{step, action, params, reason, status}]
    current_step: int

    # 执行结果
    results: list[dict]       # [{step, metric, value, severity, message, ...}]

    # 异常收集
    anomalies: list[dict]

    # 阶段控制: checking → (diagnosing) → done
    phase: str                # "checking" | "diagnosing" | "done"
    diagnosis_rounds: int

    # 知识库检索结果
    knowledge: str

    # LLM 消息
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # 最终输出
    severity: str             # normal | warning | critical
    root_cause: str
    report: str
