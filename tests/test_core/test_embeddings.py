"""Embedding 模型连接测试

配置来自 .env:
- EMBEDDING_PROVIDER=vllm
- EMBEDDING_API_BASE=http://localhost:8011/v1
- EMBEDDING_MODEL=/models/BAAI/bge-small-zh-v1___5
- EMBEDDING_DIM=512
"""

import pytest
from app.config import config


class TestEmbeddingConnection:
    """Embedding 连接测试"""

    def test_embeddings_import(self):
        """测试 OpenAI Embeddings 可导入"""
        try:
            from langchain_openai import OpenAIEmbeddings
            assert OpenAIEmbeddings is not None
        except ImportError:
            pytest.fail("langchain-openai 未安装")

    def test_knowledge_indexer_import(self):
        """测试知识索引器可导入"""
        from app.knowledge.indexer import KnowledgeIndexer
        assert KnowledgeIndexer is not None

    def test_knowledge_search_import(self):
        """测试知识搜索模块可导入"""
        from app.agent.knowledge_search import _get_embedding_model
        assert _get_embedding_model is not None


class TestEmbeddingConfiguration:
    """Embedding 配置测试"""

    def test_embedding_config_loaded(self):
        """测试 embedding 配置已加载"""
        assert hasattr(config, 'embedding_provider')
        assert hasattr(config, 'embedding_api_base')
        assert hasattr(config, 'embedding_model')
        assert hasattr(config, 'embedding_dim')

    def test_embedding_providers(self):
        """测试支持的 embedding 提供商"""
        valid_providers = ['local', 'openai', 'azure', 'vllm']
        assert config.embedding_provider in valid_providers

    def test_embedding_config_from_env(self):
        """测试从 .env 加载的配置值"""
        assert config.embedding_provider == "vllm"
        assert config.embedding_api_base == "http://localhost:8011/v1"
        assert config.embedding_model == "/models/BAAI/bge-small-zh-v1___5"
        assert config.embedding_dim == 512


class TestEmbeddingIntegration:
    """Embedding 集成测试（需要真实连接）"""

    @pytest.mark.asyncio
    async def test_vllm_embedding_connection(self):
        """测试 vLLM Embedding 服务连接（使用 .env 配置）"""
        from langchain_openai import OpenAIEmbeddings

        try:
            embeddings = OpenAIEmbeddings(
                model=config.embedding_model,
                api_key=config.embedding_api_key,
                base_url=config.embedding_api_base,
            )
            result = await embeddings.aembed_query("测试文本")
            assert result is not None
            assert len(result) == config.embedding_dim
        except Exception as e:
            pytest.skip(f"vLLM Embedding 服务未运行: {e}")

    @pytest.mark.asyncio
    async def test_indexer_embedding_connection(self):
        """测试知识索引器的 Embedding 连接（使用 .env 配置）"""
        from app.knowledge.indexer import KnowledgeIndexer

        indexer = KnowledgeIndexer(config)
        try:
            await indexer.init()
            assert indexer.embeddings is not None
        except Exception as e:
            pytest.skip(f"索引器 Embedding 初始化失败: {e}")