"""知识库检索 — TAG_INDEX 字符串匹配 + Milvus 向量检索双模式"""

import asyncio
from typing import List, Dict, Optional
from loguru import logger

from app.config import config

# ==================== TAG_INDEX 模式（原始，保留作为兜底）====================

# 标签索引: 关键词 → 文档列表
TAG_INDEX = {
    "cpu":          ["cpu_high_usage.md", "slow_response.md"],
    "内存":          ["memory_high_usage.md", "redis_memory_high.md"],
    "memory":       ["memory_high_usage.md", "redis_memory_high.md"],
    "磁盘":          ["disk_high_usage.md"],
    "disk":         ["disk_high_usage.md"],
    "http":         ["service_unavailable.md", "slow_response.md"],
    "服务不可用":      ["service_unavailable.md"],
    "service_unavailable": ["service_unavailable.md"],
    "慢响应":         ["slow_response.md"],
    "slow_response": ["slow_response.md"],
    "mysql":        ["mysql_slow_query.md", "slow_response.md", "cpu_high_usage.md"],
    "慢查询":         ["mysql_slow_query.md", "slow_response.md"],
    "slow_query":   ["mysql_slow_query.md", "slow_response.md"],
    "redis":        ["redis_memory_high.md"],
    "超时":          ["slow_response.md", "service_unavailable.md"],
    "timeout":      ["slow_response.md", "service_unavailable.md"],
    "连接数":         ["redis_memory_high.md", "mysql_slow_query.md"],
    "错误率":         ["service_unavailable.md", "slow_response.md"],
}

# 知识库目录
KNOWLEDGE_DIR = None


def _get_knowledge_dir():
    global KNOWLEDGE_DIR
    if KNOWLEDGE_DIR is None:
        from pathlib import Path
        KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
    return KNOWLEDGE_DIR


def _load_doc(filename: str) -> str:
    """加载一篇知识库文档"""
    filepath = _get_knowledge_dir() / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


def search_knowledge(anomalies: list[dict], diagnosis_hint: str = "") -> str:
    """基于 TAG_INDEX 的知识库检索（兜底方案）

    Args:
        anomalies: 异常列表 [{detector, metric_name, severity, message, ...}]
        diagnosis_hint: 诊断方向的提示文字

    Returns:
        格式化的知识库文本
    """
    if not anomalies and not diagnosis_hint:
        return ""

    # ① 从异常指标中提取关键词
    keywords = set()
    for a in anomalies:
        name = a.get("detector_name", "") + " " + a.get("metric_name", "")
        msg = a.get("message", "")
        combined = (name + " " + msg).lower()
        for tag in TAG_INDEX:
            if tag in combined:
                keywords.add(tag)

    # ② 从诊断提示中提取关键词
    if diagnosis_hint:
        hint_lower = diagnosis_hint.lower()
        for tag in TAG_INDEX:
            if tag in hint_lower:
                keywords.add(tag)

    if not keywords:
        return ""

    # ③ 匹配文档（去重）
    matched_docs = set()
    for kw in keywords:
        for doc in TAG_INDEX.get(kw, []):
            matched_docs.add(doc)

    # ④ 加载并拼接
    parts = []
    for doc in sorted(matched_docs):
        content = _load_doc(doc)
        if content:
            parts.append(f"## 📚 知识库参考: {doc.replace('.md', '')}\n\n{content}\n")

    result = "\n---\n".join(parts)
    if result:
        logger.info(f"TAG_INDEX 检索: 关键词={keywords}, 命中{len(matched_docs)}篇文档")
    return result


# ==================== 向量检索模式 ====================

# 全局单例
_milvus_client = None
_embedding_model = None


def _get_milvus_client():
    """获取 Milvus 客户端（延迟初始化）"""
    global _milvus_client
    if _milvus_client is None:
        try:
            from app.utils.milvus_client import MilvusKnowledgeBase
            _milvus_client = MilvusKnowledgeBase(
                host=config.milvus_host,
                port=config.milvus_port,
                collection=config.milvus_collection,
                user=config.milvus_user,
                password=config.milvus_password,
            )
            logger.info("Milvus 客户端初始化成功")
        except Exception as e:
            logger.warning(f"Milvus 初始化失败: {e}")
            return None
    return _milvus_client


def _get_embedding_model():
    """获取 Embedding 模型（支持 local/openai/azure 三种模式）"""
    global _embedding_model
    if _embedding_model is None:
        try:
            from langchain_openai import OpenAIEmbeddings

            provider = getattr(config, 'embedding_provider', 'local')

            if provider == "openai":
                # 云端 OpenAI API
                _embedding_model = OpenAIEmbeddings(
                    model=config.embedding_cloud_model,
                    api_key=config.embedding_api_key,
                )
                logger.info(f"Embedding 模型: OpenAI {config.embedding_cloud_model}")
            elif provider == "azure":
                # Azure OpenAI
                _embedding_model = OpenAIEmbeddings(
                    model=config.embedding_model,
                    api_key=config.embedding_api_key,
                    base_url=config.embedding_api_base,  # Azure endpoint
                )
                logger.info(f"Embedding 模型: Azure {config.embedding_model}")
            else:
                # 本地服务（Ollama/LMA-Factory）
                _embedding_model = OpenAIEmbeddings(
                    model=config.embedding_model,
                    api_key=config.embedding_api_key,
                    base_url=config.embedding_api_base,
                )
                logger.info(f"Embedding 模型: 本地 {config.embedding_model} @ {config.embedding_api_base}")

        except Exception as e:
            logger.warning(f"Embedding 模型初始化失败: {e}")
            return None
    return _embedding_model


async def search_knowledge_vector(
    anomalies: list[dict],
    top_k: int = 5,
    max_chars: int = 3000,
) -> str:
    """基于向量检索的知识库搜索

    Args:
        anomalies: 异常列表 [{detector, metric_name, severity, message, ...}]
        top_k: 返回最相关的 top_k 个段落
        max_chars: 最大返回字符数

    Returns:
        格式化的知识库文本
    """
    if not anomalies:
        return ""

    # ① 构建查询文本
    query_parts = []
    for a in anomalies:
        detector = a.get("detector_name", "")
        metric = a.get("metric_name", "")
        message = a.get("message", "")
        severity = a.get("severity", "")

        # 构造描述性查询
        query = f"{detector} {metric} {message}".strip()
        if severity:
            query = f"{severity} {query}"
        query_parts.append(query)

    query_text = "，".join(query_parts)

    # ② 向量化查询
    embeddings = _get_embedding_model()
    if embeddings is None:
        logger.warning("Embedding 模型不可用，降级到 TAG_INDEX")
        return search_knowledge(anomalies)

    try:
        query_vector = await embeddings.aembed_query(query_text)
    except Exception as e:
        logger.error(f"查询向量化失败: {e}，降级到 TAG_INDEX")
        return search_knowledge(anomalies)

    # ③ Milvus 检索
    milvus = _get_milvus_client()
    if milvus is None:
        logger.warning("Milvus 不可用，降级到 TAG_INDEX")
        return search_knowledge(anomalies)

    try:
        results = milvus.search(query_vector, top_k=top_k)
    except Exception as e:
        logger.warning(f"Milvus 检索失败，降级到 TAG_INDEX: {e}")
        return search_knowledge(anomalies)

    # ④ 格式化输出
    if not results:
        logger.info(f"向量检索无结果，降级到 TAG_INDEX")
        return search_knowledge(anomalies)

    parts = []
    for hit in results:
        doc_title = hit.get("doc_title", "")
        p_type = hit.get("paragraph_type", "")
        content = hit.get("content", "")
        distance = hit.get("distance", 0)

        # 类型友好显示
        type_display = {
            "alert_info": "📋 告警信息",
            "problem_description": "🔍 问题描述",
            "troubleshooting_step": "🔧 排查步骤",
            "root_cause": "⚠️ 根因分析",
            "solution": "💡 处理方案",
            "emergency_action": "🚨 紧急处理",
            "verification": "✅ 验证步骤",
        }.get(p_type, p_type)

        parts.append(f"### {type_display}: {doc_title}\n\n{content}\n")

    result = "\n---\n".join(parts)

    # 按字符数截断
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n... (知识库内容已截断，已省略 {len(result) - max_chars} 字符)"

    logger.info(f"向量检索: query='{query_text[:50]}...', 命中 {len(results)} 个段落")
    return result


# ==================== 智能选择入口 ====================

async def search(anomalies: list[dict], diagnosis_hint: str = "") -> str:
    """智能知识库检索 — 优先向量检索，失败降级到 TAG_INDEX

    Args:
        anomalies: 异常列表
        diagnosis_hint: 诊断提示（传递给 TAG_INDEX 备用）

    Returns:
        格式化的知识库文本
    """
    try:
        return await search_knowledge_vector(anomalies, top_k=5)
    except Exception as e:
        logger.warning(f"向量检索异常，降级到 TAG_INDEX: {e}")
        return search_knowledge(anomalies, diagnosis_hint)


# ==================== 向量检索测试 ====================

async def test_vector_search():
    """测试向量检索"""
    test_anomalies = [
        {
            "detector": "local_cpu",
            "metric_name": "cpu_usage",
            "message": "CPU使用率过高，达到 85%",
            "severity": "critical",
        },
        {
            "detector": "mysql_slow_queries",
            "metric_name": "slow_query_count",
            "message": "慢查询数量激增",
            "severity": "warning",
        },
    ]

    print("=" * 60)
    print("测试向量检索")
    print("=" * 60)

    result = await search(test_anomalies)
    print(f"\n检索结果 ({len(result)} 字符):\n")
    print(result[:1500] if result else "无结果")
    print("...")


if __name__ == "__main__":
    asyncio.run(test_vector_search())