"""知识库文档结构化工具 — 将 .md 文档转换为段落 JSON"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

# 段落类型映射
PARAGRAPH_TYPE_MAP = {
    "告警名称": "alert_info",
    "问题描述": "problem_description",
    "排查步骤": "troubleshooting_step",
    "常见原因": "root_cause",
    "常见原因分析": "root_cause",
    "紧急处理": "emergency_action",
    "紧急处理措施": "emergency_action",
    "处理方案": "solution",
    "短期措施": "solution",
    "长期优化": "solution",
    "验证步骤": "verification",
    "监控指标": "monitoring_metrics",
    "相关告警": "related_alerts",
    "联系方式": "contact_info",
    "参考文档": "reference",
}

# 标签提取关键词
TAG_KEYWORDS = {
    "cpu": ["cpu", "处理器", "负载", "load"],
    "内存": ["内存", "memory", "ram"],
    "磁盘": ["磁盘", "disk", "storage", "硬盘"],
    "mysql": ["mysql", "数据库", "sql", "慢查询"],
    "redis": ["redis", "缓存", "memory"],
    "网络": ["网络", "network", "网卡", "流量"],
    "服务": ["服务", "service", "应用", "进程"],
    "进程": ["进程", "process", "pid"],
    "死循环": ["死循环", "无限递归", "cpu 100"],
    "慢查询": ["慢查询", "slow query", "全表扫描"],
    "锁竞争": ["锁", "lock", "死锁", "阻塞"],
    "流量": ["流量", "qps", "并发", "突增"],
    "扩容": ["扩容", "scale", "自动伸缩"],
    "限流": ["限流", "rate limit", "降级"],
    "重启": ["重启", "restart", "kill"],
    "回滚": ["回滚", "rollback", "版本"],
}


def _infer_paragraph_type(title: str) -> str:
    """根据标题推断段落类型"""
    for key, ptype in PARAGRAPH_TYPE_MAP.items():
        if key in title:
            return ptype
    return "general"


def _extract_tags(content: str) -> List[str]:
    """从内容中提取标签"""
    content_lower = content.lower()
    tags = []

    for tag, keywords in TAG_KEYWORDS.items():
        for kw in keywords:
            if kw in content_lower:
                tags.append(tag)
                break

    # 从 # 标题中提取标签
    headings = re.findall(r'#+\s*([^\n]+)', content)
    for h in headings:
        tags.append(h.strip())

    return list(set(tags))[:10]  # 最多10个标签


def _split_into_paragraphs(md_content: str) -> List[str]:
    """将 .md 文档按二级标题切分为段落"""
    # 标准化：统一换行符
    md_content = md_content.replace('\r\n', '\n')

    # 情况1: 按 ## 二级标题切分
    if '## ' in md_content:
        # 在 ## 前加分隔符，便于split
        parts = re.split(r'\n(?=## )', md_content)
    else:
        # 情况2: 没有二级标题，按一级标题分割
        parts = re.split(r'\n(?=# )', md_content)

    paragraphs = []
    for part in parts:
        part = part.strip()
        if not part or len(part) < 20:  # 过滤太短的内容
            continue
        paragraphs.append(part)

    return paragraphs


def _extract_title_from_paragraph(paragraph: str) -> str:
    """从段落中提取标题"""
    # 去掉一级标题标记
    paragraph = re.sub(r'^#+\s*', '', paragraph)
    # 取第一行作为标题
    lines = paragraph.split('\n')
    return lines[0].strip() if lines else "未命名"


def parse_md_to_paragraphs(md_file: Path) -> List[Dict[str, Any]]:
    """将单个 .md 文档解析为段落列表

    Args:
        md_file: .md 文件路径

    Returns:
        段落列表，每个段落包含:
            - paragraph_id: 段落唯一ID (格式: docid_序号)
            - doc_id: 文档ID (文件名)
            - doc_title: 文档标题
            - paragraph_type: 段落类型
            - content: 段落完整内容
            - tags: 标签列表
    """
    if not md_file.exists():
        logger.error(f"文件不存在: {md_file}")
        return []

    try:
        content = md_file.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"读取文件失败 {md_file}: {e}")
        return []

    doc_id = md_file.stem  # 文件名（无扩展名）
    doc_title = doc_id.replace('_', ' ').replace('-', ' ').title()

    # 按二级标题切分
    raw_paragraphs = _split_into_paragraphs(content)

    paragraphs = []
    for i, para in enumerate(raw_paragraphs):
        if not para.strip():
            continue

        title = _extract_title_from_paragraph(para)
        para_type = _infer_paragraph_type(title)
        tags = _extract_tags(para)

        paragraph = {
            "paragraph_id": f"{doc_id}_{i:03d}",
            "doc_id": doc_id,
            "doc_title": title if title else doc_title,
            "paragraph_type": para_type,
            "content": para.strip(),
            "tags": tags,
        }
        paragraphs.append(paragraph)

    logger.debug(f"解析完成 {md_file.name}: {len(paragraphs)} 个段落")
    return paragraphs


def parse_all_knowledge_docs(knowledge_dir: Path) -> List[Dict[str, Any]]:
    """解析所有知识库文档

    Args:
        knowledge_dir: 知识库目录

    Returns:
        所有段落列表
    """
    all_paragraphs = []

    if not knowledge_dir.exists():
        logger.error(f"知识库目录不存在: {knowledge_dir}")
        return all_paragraphs

    md_files = list(knowledge_dir.glob("*.md"))
    logger.info(f"发现 {len(md_files)} 个知识库文档")

    for md_file in md_files:
        paragraphs = parse_md_to_paragraphs(md_file)
        all_paragraphs.extend(paragraphs)
        logger.info(f"  {md_file.name}: {len(paragraphs)} 个段落")

    return all_paragraphs


def save_structured_knowledge(
    paragraphs: List[Dict[str, Any]],
    output_dir: Path,
    pretty: bool = True,
) -> bool:
    """保存结构化知识库到 JSON 文件

    Args:
        paragraphs: 段落列表
        output_dir: 输出目录
        pretty: 是否格式化 JSON

    Returns:
        是否成功
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 按 doc_id 分组保存
    by_doc = {}
    for p in paragraphs:
        doc_id = p["doc_id"]
        if doc_id not in by_doc:
            by_doc[doc_id] = []
        by_doc[doc_id].append(p)

    for doc_id, paras in by_doc.items():
        output_file = output_dir / f"{doc_id}.json"
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                if pretty:
                    json.dump({"doc_id": doc_id, "paragraphs": paras}, f, ensure_ascii=False, indent=2)
                else:
                    json.dump({"doc_id": doc_id, "paragraphs": paras}, f, ensure_ascii=False)
            logger.info(f"已保存: {output_file}")
        except Exception as e:
            logger.error(f"保存失败 {output_file}: {e}")
            return False

    return True


# ==================== 命令行工具 ====================

def main():
    """命令行入口：解析知识库文档"""
    import argparse

    parser = argparse.ArgumentParser(description="知识库文档结构化工具")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="app/knowledge",
        help="知识库目录路径",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="app/knowledge/structured",
        help="输出目录路径",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="仅预览，不保存",
    )

    args = parser.parse_args()

    knowledge_dir = Path(args.input)
    output_dir = Path(args.output)

    logger.info(f"解析知识库文档: {knowledge_dir}")
    paragraphs = parse_all_knowledge_docs(knowledge_dir)

    logger.info(f"共解析 {len(paragraphs)} 个段落")

    if args.preview:
        # 仅预览：打印前3个段落
        for i, p in enumerate(paragraphs[:3]):
            print(f"\n{'='*60}")
            print(f"段落 {i+1}: {p['paragraph_id']}")
            print(f"类型: {p['paragraph_type']}")
            print(f"标签: {p['tags']}")
            print(f"内容预览: {p['content'][:200]}...")
    else:
        # 保存
        save_structured_knowledge(paragraphs, output_dir)
        logger.info(f"结构化知识库已保存到: {output_dir}")


if __name__ == "__main__":
    main()