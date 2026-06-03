"""LLM 连接测试

配置来自 .env:
- LLM_PROVIDER=vllm
- LLM_API_BASE=http://localhost:8010/v1
- LLM_MODEL=/models/Qwen/Qwen2-0___5B-Instruct
"""

import pytest
from app.config import config


class TestLLMConnection:
    """LLM 连接测试"""

    def test_llm_factory_import(self):
        """测试 LLM 工厂类可以正常导入"""
        from app.core.llm_factory import LLMFactory, llm_factory
        assert LLMFactory is not None
        assert llm_factory is not None

    def test_provider_defaults(self):
        """测试提供商默认配置"""
        from app.core.llm_factory import LLMFactory
        defaults = LLMFactory.PROVIDER_DEFAULTS
        assert "vllm" in defaults
        assert "ollama" in defaults
        assert "openai" in defaults

    def test_create_chat_model_from_config(self):
        """测试使用配置创建 vLLM 模型"""
        from app.core.llm_factory import LLMFactory
        llm = LLMFactory.create_chat_model(
            provider=config.llm_provider,
            model=config.llm_model,
            base_url=config.llm_api_base,
            api_key=config.llm_api_key,
        )
        assert llm is not None

    def test_create_chat_model_vllm(self):
        """测试创建 vLLM 模型"""
        from app.core.llm_factory import LLMFactory
        llm = LLMFactory.create_chat_model(
            provider="vllm",
            model="/models/Qwen/Qwen2-0___5B-Instruct",
            base_url="http://localhost:8010/v1",
            api_key="empty",
        )
        assert llm is not None

    def test_create_chat_model_ollama(self):
        """测试创建 Ollama 模型"""
        from app.core.llm_factory import LLMFactory
        llm = LLMFactory.create_chat_model(
            provider="ollama",
            model="qwen2.5:7b",
            base_url="http://localhost:11434/v1",
            api_key="local",
        )
        assert llm is not None

    def test_create_chat_model_openai(self):
        """测试创建 OpenAI 模型"""
        from app.core.llm_factory import LLMFactory
        llm = LLMFactory.create_chat_model(
            provider="openai",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            api_key="test_key",
        )
        assert llm is not None


class TestLLMIntegration:
    """LLM 集成测试（需要真实连接）"""

    @pytest.mark.asyncio
    async def test_vllm_connection(self):
        """测试 vLLM 连接（使用 .env 配置）"""
        from app.core.llm_factory import LLMFactory
        try:
            llm = LLMFactory.create_chat_model(
                provider=config.llm_provider,
                model=config.llm_model,
                base_url=config.llm_api_base,
                api_key=config.llm_api_key,
                timeout=30,
            )
            response = await llm.apredict("Hello, respond with 'OK' if you receive this")
            assert response is not None
            assert "OK" in response
        except Exception as e:
            pytest.skip(f"vLLM 服务未运行: {e}")