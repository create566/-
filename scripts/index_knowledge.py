#!/usr/bin/env python3
"""知识库索引脚本 — 将 .md 文档向量化存入 Milvus

用法:
    python scripts/index_knowledge.py                    # 索引全部文档
    python scripts/index_knowledge.py --input app/knowledge  # 指定目录
    python scripts/index_knowledge.py --drop             # 删除后重建
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


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
        default="http://localhost:8011/v1",
        help="Embedding API 地址（OpenAI 兼容）",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default="/models/BAAI/bge-small-zh-v1___5",
        help="Embedding 模型名称",
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=512,
        help="Embedding 向量维度",
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="删除已存在的 Collection 后重新索引",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="仅预览解析结果，不写入 Milvus",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("知识库向量化索引工具")
    print("=" * 60)
    print(f"  知识库目录: {args.input}")
    print(f"  Milvus: {args.milvus_host}:{args.milvus_port}/{args.collection}")
    print(f"  Embedding: {args.embedding_model} @ {args.embedding_api_base}")
    print(f"  向量维度: {args.embedding_dim}")
    print(f"  模式: {'预览' if args.preview else '索引'}")
    print("=" * 60)

    # 预览模式：只解析不写入
    if args.preview:
        from app.knowledge.convert import parse_all_knowledge_docs
        knowledge_dir = Path(args.input)
        paragraphs = parse_all_knowledge_docs(knowledge_dir)
        print(f"\n解析结果: 共 {len(paragraphs)} 个段落\n")
        for i, p in enumerate(paragraphs[:5]):
            print(f"  [{i+1}] {p['paragraph_id']} ({p['paragraph_type']})")
            print(f"       标签: {p['tags'][:5]}")
            print(f"       预览: {p['content'][:100]}...")
            print()
        if len(paragraphs) > 5:
            print(f"  ... 还有 {len(paragraphs) - 5} 个段落")
        return

    # 索引模式
    async def run_index():
        from app.knowledge.indexer import index_all

        total = await index_all(
            knowledge_dir=args.input,
            milvus_host=args.milvus_host,
            milvus_port=args.milvus_port,
            collection=args.collection,
            embedding_api_base=args.embedding_api_base,
            embedding_model=args.embedding_model,
            embedding_dim=args.embedding_dim,
            drop_existing=args.drop,
        )
        print(f"\n✅ 索引完成: {total} 个段落已写入 Milvus")
        return total

    try:
        asyncio.run(run_index())
    except KeyboardInterrupt:
        print("\n\n⚠️ 索引已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 索引失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()