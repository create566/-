"""知识库向量化索引脚本 — 将结构化段落存入 Milvus"""

import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

try:
    from langchain_openai import OpenAIEmbeddings
    _embedding_available = True
except ImportError:
    _embedding_available = False

from app.knowledge.convert import parse_all_knowledge_docs
from app.utils.milvus_client import MilvusKnowledgeBase, get_milvus_client


class KnowledgeIndexer:
    """知识库索引器"""

    def __init__(self, config):
        """
        Args:
            config: 应用配置对象（包含 Milvus/Embedding 配置）
        """
        self.config = config
        self.milvus: Optional[MilvusKnowledgeBase] = None
        self.embeddings = None
        self.embedding_api_base = config.embedding_api_base
        self.embedding_model = config.embedding_model
        self.dim = config.embedding_dim

    async def init(self):
        """初始化 Milvus 和 Embedding 模型"""
        # 初始化 Milvus
        try:
            self.milvus = MilvusKnowledgeBase(
                host=self.config.milvus_host,
                port=self.config.milvus_port,
                collection=self.config.milvus_collection,
                user=self.config.milvus_user,
                password=self.config.milvus_password,
            )
            logger.info("Milvus 客户端初始化成功")
        except Exception as e:
            logger.error(f"Milvus 初始化失败: {e}")
            raise

        # 初始化 Embedding 模型（支持 local/openai/azure）
        if not _embedding_available:
            raise ImportError("langchain-openai 未安装")

        try:
            provider = getattr(self.config, 'embedding_provider', 'local')

            if provider == "openai":
                self.embeddings = OpenAIEmbeddings(
                    model=self.config.embedding_cloud_model,
                    api_key=self.config.embedding_api_key,
                )
                logger.info(f"Embedding 模型: OpenAI {self.config.embedding_cloud_model}")
            elif provider == "azure":
                self.embeddings = OpenAIEmbeddings(
                    model=self.config.embedding_model,
                    api_key=self.config.embedding_api_key,
                    base_url=self.config.embedding_api_base,
                )
                logger.info(f"Embedding 模型: Azure {self.config.embedding_model}")
            else:
                # 本地服务
                self.embeddings = OpenAIEmbeddings(
                    model=self.config.embedding_model,
                    api_key=self.config.embedding_api_key,
                    base_url=self.config.embedding_api_base,
                )
                logger.info(f"Embedding 模型: 本地 {self.config.embedding_model}")

        except Exception as e:
            logger.error(f"Embedding 初始化失败: {e}")
            raise

    async def index_knowledge_base(
        self,
        knowledge_dir: Path,
        drop_existing: bool = False,
        batch_size: int = 10,
    ) -> int:
        """索引知识库

        Args:
            knowledge_dir: 知识库目录
            drop_existing: 是否删除已存在的 collection
            batch_size: 批处理大小

        Returns:
            索引的段落总数
        """
        # 初始化 collection（向量维度根据实际 embedding 模型确定）
        provider = getattr(self.config, 'embedding_provider', 'local')
        if provider == "openai":
            dim = self.config.embedding_cloud_dim  # 1536 for OpenAI
        elif provider == "azure":
            dim = self.config.embedding_cloud_dim
        else:
            dim = self.config.embedding_dim  # 本地模型维度

        self.milvus.init_collection(
            dim=dim,
            drop_existing=drop_existing,
        )

        # 解析所有文档为段落
        paragraphs = parse_all_knowledge_docs(knowledge_dir)
        if not paragraphs:
            logger.warning("没有找到知识库段落")
            return 0

        total_indexed = 0

        # 分批处理
        for i in range(0, len(paragraphs), batch_size):
            batch = paragraphs[i:i + batch_size]
            await self._index_batch(batch)
            total_indexed += len(batch)
            logger.info(f"索引进度: {total_indexed}/{len(paragraphs)}")

        return total_indexed

    async def _index_batch(self, batch: List[Dict[str, Any]]):
        """索引一批段落"""
        # 提取文本内容，截断到 ~250 字符避免超出 embedding 模型的 512 token 限制
        texts = [p["content"][:250] for p in batch]

        # 向量化 — 优先直调 vLLM API（绕过 LangChain tokenizer 兼容问题）
        vectors = []
        import aiohttp
        for text in texts:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.embedding_api_base}/embeddings",
                        json={"input": text, "model": self.embedding_model},
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as resp:
                        data = await resp.json()
                        vectors.append(data["data"][0]["embedding"])
            except Exception as e:
                logger.error(f"向量化失败: {e}")
                vectors.append([0.0] * self.dim)

        # 组装插入数据
        for p, v in zip(batch, vectors):
            p["content_vector"] = v

        # 插入 Milvus
        self.milvus.insert(batch)

    async def index_single_doc(self, md_file: Path) -> int:
        """索引单个文档

        Args:
            md_file: .md 文件路径

        Returns:
            索引的段落数
        """
        from app.knowledge.convert import parse_md_to_paragraphs

        paragraphs = parse_md_to_paragraphs(md_file)
        if not paragraphs:
            return 0

        await self._index_batch(paragraphs)
        return len(paragraphs)


async def index_all(
    knowledge_dir: str = "app/knowledge",
    milvus_host: str = "localhost",
    milvus_port: int = 19530,
    collection: str = "knowledge_base",
    embedding_api_base: str = "http://localhost:11434/v1",
    embedding_model: str = "bge-large-zh-v1.5",
    embedding_dim: int = 1024,
    drop_existing: bool = False,
):
    """命令行索引入口"""
    # 创建配置对象
    class Config:
        pass

    config = Config()
    config.milvus_host = milvus_host
    config.milvus_port = milvus_port
    config.milvus_collection = collection
    config.milvus_user = ""
    config.milvus_password = ""
    config.embedding_api_key = "local"
    config.embedding_api_base = embedding_api_base
    config.embedding_model = embedding_model
    config.embedding_dim = embedding_dim

    indexer = KnowledgeIndexer(config)
    await indexer.init()

    knowledge_path = Path(knowledge_dir)
    total = await indexer.index_knowledge_base(knowledge_path, drop_existing=drop_existing)

    logger.info(f"✅ 知识库索引完成，共 {total} 个段落")
    return total


# ==================== 命令行入口 ====================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="知识库向量化索引工具")
    parser.add_argument(
        "--input", "-i",
        type=str,
        default="app/knowledge",
        help="知识库目录路径",
    )
    parser.add_argument(
        "--milvus-host",
        type=str,
        default="localhost",
        help="Milvus 主机地址",
    )
    parser.add_argument(
        "--milvus-port",
        type=int,
        default=19530,
        help="Milvus 端口",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="knowledge_base",
        help="Collection 名称",
    )
    parser.add_argument(
        "--embedding-api-base",
        type=str,
        default="http://localhost:11434/v1",
        help="Embedding API 地址",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default="bge-large-zh-v1.5",
        help="Embedding 模型名称",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=1024,
        help="Embedding 向量维度",
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="删除已存在的 Collection 后重新索引",
    )

    args = parser.parse_args()

    asyncio.run(index_all(
        knowledge_dir=args.input,
        milvus_host=args.milvus_host,
        milvus_port=args.milvus_port,
        collection=args.collection,
        embedding_api_base=args.embedding_api_base,
        embedding_model=args.embedding_model,
        embedding_dim=args.embedding_dim,
        drop_existing=args.drop,
    ))


if __name__ == "__main__":
    main()