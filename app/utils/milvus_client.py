"""Milvus 向量数据库客户端 — 支持 Docker 服务器 & Milvus Lite 本地模式"""

from typing import List, Dict, Optional, Any
from loguru import logger
import os

try:
    from pymilvus import MilvusClient
    _milvus_available = True
except ImportError:
    _milvus_available = False

try:
    import milvus_lite
    _milvus_lite_available = True
except ImportError:
    _milvus_lite_available = False


class MilvusKnowledgeBase:

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection: str = "knowledge_base",
        user: str = "",
        password: str = "",
        use_lite: bool = True,
    ):
        if not _milvus_available:
            raise ImportError("pymilvus 未安装，请运行: pip install pymilvus")

        self.host = host
        self.port = port
        self.collection = collection
        self.user = user
        self.password = password
        self.use_lite = use_lite

        if use_lite:
            if not _milvus_lite_available:
                raise ImportError("milvus-lite 未安装，请运行: pip install milvus-lite")
            # Milvus Lite: URI 是本地文件路径
            lite_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "milvus_lite.db")
            lite_path = os.path.abspath(lite_path)
            logger.info(f"Milvus Lite 模式: {lite_path}")
            self.client = MilvusClient(uri=lite_path)

            # Milvus Lite 需要手动 load collection
            if self.client.has_collection(collection_name=self.collection):
                self.client.load_collection(collection_name=self.collection)
                logger.info(f"Collection '{self.collection}' 已加载")
        else:
            uri = f"http://{host}:{port}"
            logger.info(f"Milvus Docker 模式: {uri}")
            self.client = MilvusClient(uri=uri)

    def has_collection(self) -> bool:
        """检查 collection 是否存在"""
        return self.client.has_collection(collection_name=self.collection)

    def init_collection(self, dim: int = 1024, drop_existing: bool = False):
        """初始化 Collection

        Args:
            dim: 向量维度
            drop_existing: 是否删除已存在的 collection
        """
        if self.client.has_collection(collection_name=self.collection):
            if drop_existing:
                logger.warning(f"删除已存在的 collection: {self.collection}")
                self.client.drop_collection(collection_name=self.collection)
            else:
                logger.info(f"Collection 已存在: {self.collection}")
                return

        self.client.create_collection(
            collection_name=self.collection,
            dimension=dim,
            metric_type="COSINE",
            vector_field_name="content_vector",
            auto_id=True,
        )
        logger.info(f"Collection 创建成功: {self.collection}, dim={dim}")

        # Milvus Lite 需要加载 collection 才能搜索
        if self.use_lite:
            self.client.load_collection(collection_name=self.collection)

        # Milvus Lite 不需要显式创建索引（默认 FLAT 暴力搜索）
        if not self.use_lite:
            try:
                self.client.create_index(
                    collection_name=self.collection,
                    field_name="content_vector",
                    index_type="FLAT",
                    metric_type="COSINE",
                    params={},
                )
                logger.info(f"索引创建成功: content_vector, FLAT, COSINE")
            except Exception as e:
                logger.warning(f"索引创建跳过（Milvus Lite 默认 FLAT）: {e}")

    def insert(self, data: List[Dict[str, Any]]) -> bool:
        """批量插入知识段落

        Args:
            data: 段落列表，每个段落包含:
                - paragraph_id: 段落唯一ID
                - doc_id: 文档ID
                - doc_title: 文档标题
                - paragraph_type: 段落类型（problem_description/root_cause/solution等）
                - content: 段落内容
                - content_vector: 向量（list[float]）
                - tags: 标签列表（可选）

        Returns:
            bool: 插入是否成功
        """
        if not data:
            return True

        try:
            # 确保段落有 ID
            for i, item in enumerate(data):
                if "paragraph_id" not in item:
                    item["paragraph_id"] = f"p_{i}"

            result = self.client.insert(
                collection_name=self.collection,
                data=data,
            )
            logger.info(f"知识段落插入成功: {len(data)} 条")
            return True
        except Exception as e:
            logger.error(f"知识段落插入失败: {e}")
            return False

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filters: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """向量检索

        Args:
            query_vector: 查询向量
            top_k: 返回数量
            filters: 过滤条件（可选）

        Returns:
            检索结果列表
        """
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}

        try:
            results = self.client.search(
                collection_name=self.collection,
                data=[query_vector],
                limit=top_k,
                search_params=search_params,
                output_fields=[
                    "paragraph_id",
                    "doc_id",
                    "doc_title",
                    "paragraph_type",
                    "content",
                    "tags",
                ],
            )

            if not results or len(results) == 0:
                return []

            # 格式化结果
            formatted = []
            for hits in results:
                for hit in hits:
                    entity = hit.get("entity", {}) or {}
                    formatted.append({
                        "paragraph_id": hit.get("paragraph_id") or entity.get("paragraph_id", ""),
                        "doc_id": hit.get("doc_id") or entity.get("doc_id", ""),
                        "doc_title": hit.get("doc_title") or entity.get("doc_title", ""),
                        "paragraph_type": hit.get("paragraph_type") or entity.get("paragraph_type", ""),
                        "content": entity.get("content") or hit.get("content", ""),
                        "tags": entity.get("tags") or hit.get("tags", []),
                        "distance": hit.get("distance", 0),
                    })

            logger.debug(f"向量检索完成: top_k={top_k}, 返回 {len(formatted)} 条")
            return formatted

        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []

    def get_by_doc_id(self, doc_id: str) -> List[Dict[str, Any]]:
        """根据文档ID获取所有段落"""
        try:
            results = self.client.query(
                collection_name=self.collection,
                filter=f'doc_id == "{doc_id}"',
                output_fields=[
                    "paragraph_id",
                    "doc_id",
                    "doc_title",
                    "paragraph_type",
                    "content",
                    "tags",
                ],
            )
            return results
        except Exception as e:
            logger.error(f"根据 doc_id 查询失败: {e}")
            return []

    def delete_by_doc_id(self, doc_id: str) -> bool:
        """根据文档ID删除所有段落"""
        try:
            self.client.delete(
                collection_name=self.collection,
                filter=f'doc_id == "{doc_id}"',
            )
            logger.info(f"文档段落删除成功: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"文档段落删除失败: {e}")
            return False

    def collection_stats(self) -> Dict[str, Any]:
        """获取 Collection 统计信息"""
        try:
            return self.client.get_collection_stats(collection_name=self.collection)
        except Exception as e:
            logger.error(f"获取 Collection 统计失败: {e}")
            return {}


# ==================== 全局单例 ====================

_milvus_client: Optional[MilvusKnowledgeBase] = None


def get_milvus_client(use_lite: bool = True) -> Optional[MilvusKnowledgeBase]:
    """获取 Milvus 全局单例（默认 Milvus Lite 本地模式）"""
    global _milvus_client
    if _milvus_client is None:
        try:
            from app.config import config
            _milvus_client = MilvusKnowledgeBase(
                host=config.milvus_host,
                port=config.milvus_port,
                collection=config.milvus_collection,
                user=config.milvus_user,
                password=config.milvus_password,
                use_lite=use_lite,
            )
        except Exception as e:
            logger.warning(f"Milvus 初始化失败: {e}")
            return None
    return _milvus_client


def is_milvus_available() -> bool:
    """检查 Milvus 是否可用"""
    try:
        client = get_milvus_client()
        if client is None:
            return False
        client.client.ping()
        return True
    except Exception:
        return False