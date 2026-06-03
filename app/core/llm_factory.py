"""LLM 工厂类

支持多种 LLM Provider：
- vLLM: 本地高性能推理
- Ollama: 本地模型推理
- DashScope: 阿里云灵积（qwen-plus/max）
- OpenAI: 兼容所有 OpenAI API（DeepSeek 等）
"""

from langchain_openai import ChatOpenAI
from app.config import config
from loguru import logger


class LLMFactory:
    """LLM 工厂类 — 支持 vLLM / Ollama / DashScope / OpenAI"""

    PROVIDER_DEFAULTS = {
        "vllm": {"base_url": "http://localhost:8000/v1", "model": "Qwen2.5-7B-Instruct"},
        "ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b"},
        "dashscope": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
        "openai": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    }

    @staticmethod
    def create_chat_model(
        model: str | None = None,
        temperature: float = 0.7,
        streaming: bool = False,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 120,
        max_tokens: int = 4096,
        provider: str | None = None,
    ) -> ChatOpenAI:
        """创建 LLM 实例"""
        provider = provider or config.llm_provider
        defaults = LLMFactory.PROVIDER_DEFAULTS.get(provider, {})

        if provider == "ollama":
            model = model or config.ollama_model or defaults.get("model", "qwen2.5:7b")
        elif provider == "dashscope":
            model = model or config.dashscope_model or defaults.get("model", "qwen-plus")
        else:
            model = model or config.llm_model or defaults.get("model", "Qwen2.5-7B-Instruct")

        base_url = base_url or config.llm_api_base or defaults.get("base_url", "")
        api_key = api_key or config.llm_api_key or "local"

        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=api_key,
            request_timeout=timeout,
            max_tokens=max_tokens,
        )
        logger.info(f"LLM 已创建: provider={provider}, model={model}, base_url={base_url}")
        return llm


llm_factory = LLMFactory()