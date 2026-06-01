"""LLM 工厂类

支持多种 LLM Provider：
- vLLM: 高吞吐量，本地推理
- Ollama: 本地模型推理
- OpenAI: 云端模型（DeepSeek 等）
"""

from langchain_openai import ChatOpenAI
from app.config import config
from loguru import logger


class LLMFactory:
    """LLM 工厂类 — 支持 vLLM / Ollama / OpenAI"""

    PROVIDER_DEFAULTS = {
        "vllm": {"base_url": "http://localhost:8000/v1", "model": "Qwen2.5-7B-Instruct"},
        "ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b"},
        "openai": {"base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash"},
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
        """创建 LLM 实例

        Args:
            model: 模型名称，默认使用配置
            temperature: 温度参数
            streaming: 是否启用流式
            base_url: API 地址，默认使用配置
            api_key: API Key，默认使用配置
            timeout: 超时时间（秒）
            max_tokens: 最大 token 数
            provider: 提供商（vllm/ollama/openai），默认使用配置
        """
        provider = provider or config.llm_provider
        defaults = LLMFactory.PROVIDER_DEFAULTS.get(provider, {})

        # 解析模型名称：Ollama 使用 ollama_model，其他使用 llm_model
        if provider == "ollama":
            model = model or config.ollama_model or defaults.get("model", "qwen2.5:7b")
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
        logger.info(f"LLM 已创建: provider={provider}, model={model}, base_url={base_url}, timeout={timeout}s")
        return llm


llm_factory = LLMFactory()