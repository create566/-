"""LangGraph 图组装 — Plan-Execute-Replan Agent"""

from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.planner import planner
from app.agent.executor import executor, should_continue_execution
from app.agent.replanner import replanner, decide_next

try:
    from langgraph.checkpoint.redis import RedisSaver
    import redis as redis_lib
    _redis_checkpointer_available = True
except ImportError:
    _redis_checkpointer_available = False


def build_agent_graph(config=None):
    """构建 Plan-Execute-Replan Agent 图

    流程图:
      START → planner → executor ⟲ (循环执行计划中的每一步)
                  ↓ (全部执行完)
               replanner
               ↓        ↘
            [continue]  [done]
               ↓          ↓
            planner      END

    Args:
        config: 应用配置对象，用于获取 Redis 连接参数
    """
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("planner", planner)
    workflow.add_node("executor", executor)
    workflow.add_node("replanner", replanner)

    # 设置入口
    workflow.set_entry_point("planner")

    # Planner → Executor
    workflow.add_edge("planner", "executor")

    # Executor 条件: 继续执行 or 交给 Replanner
    workflow.add_conditional_edges(
        "executor",
        should_continue_execution,
        {
            "continue": "executor",   # 还有步骤未执行
            "review": "replanner",    # 计划全部执行完
        }
    )

    # Replanner 条件: 需要继续排查 or 结束
    workflow.add_conditional_edges(
        "replanner",
        decide_next,
        {
            "continue": "planner",    # 需要进一步排查 → 重新定计划
            "done": END,              # 有结论了 → 结束
        }
    )

    # 选择 checkpointer：Redis > MemorySaver
    if _redis_checkpointer_available and config:
        try:
            redis_client = redis_lib.Redis(
                host=config.redis_host,
                port=config.redis_port,
                db=config.redis_db,
                password=config.redis_password or None,
                decode_responses=True,
            )
            redis_client.ping()
            checkpointer = RedisSaver(redis_client)
            checkpointer = checkpointer  # 赋值给局部变量以避免 Unused import warning
            # 使用 Redis checkpointer
            return workflow.compile(checkpointer=RedisSaver(redis_client))
        except Exception:
            # Redis 不可用，降级到 MemorySaver
            from langgraph.checkpoint.memory import MemorySaver
            return workflow.compile(checkpointer=MemorySaver())

    # 默认使用 MemorySaver（内存持久化，重启丢失）
    from langgraph.checkpoint.memory import MemorySaver
    return workflow.compile(checkpointer=MemorySaver())


# 全局单例（延迟初始化）
_agent_graph = None


def get_agent_graph(config=None):
    """获取 Agent Graph 单例"""
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph(config)
    return _agent_graph


# 兼容旧代码：如果其他地方直接导入 agent_graph，使用默认配置初始化
try:
    from app.config import config as _config
    agent_graph = get_agent_graph(_config)
except Exception:
    # 配置未加载时使用 MemorySaver
    from langgraph.checkpoint.memory import MemorySaver
    _workflow = StateGraph(AgentState)
    _workflow.add_node("planner", planner)
    _workflow.add_node("executor", executor)
    _workflow.add_node("replanner", replanner)
    _workflow.set_entry_point("planner")
    _workflow.add_edge("planner", "executor")
    _workflow.add_conditional_edges("executor", should_continue_execution, {"continue": "executor", "review": "replanner"})
    _workflow.add_conditional_edges("replanner", decide_next, {"continue": "planner", "done": END})
    agent_graph = _workflow.compile(checkpointer=MemorySaver())