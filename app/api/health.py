"""健康检查接口"""

from fastapi import APIRouter
from app.config import config
from app.models.response import UnifiedResponse

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查 — API + LLM"""
    services = {
        "api": {"available": True, "message": "API 服务正常"},
        "llm": {"available": True, "message": "待首次调用验证"},
    }

    # 检查 LLM
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
        test_llm = ChatOpenAI(
            model=config.llm_model,
            api_key=config.llm_api_key,
            base_url=config.llm_api_base,
            max_tokens=5,
            streaming=False,
            timeout=30,
            max_retries=1,
        )
        test_llm.invoke([HumanMessage(content="ping")])
        services["llm"] = {"available": True, "message": "LLM 连接正常"}
    except Exception as e:
        services["llm"] = {"available": False, "message": f"LLM 不可用: {e}"}

    overall = "healthy" if services["llm"]["available"] else "degraded"

    return UnifiedResponse.success(result={
        "service": config.app_name,
        "version": config.app_version,
        "status": overall,
        "services": services,
    }).model_dump()
