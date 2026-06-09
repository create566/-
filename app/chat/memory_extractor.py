"""记忆抽取器 — 使用 LLM 从对话中提取结构化事实"""

import json
from typing import List, Dict
from loguru import logger

from app.core.llm_factory import LLMFactory
from app.chat.session_manager import SessionManager
from langchain_core.messages import HumanMessage

EXTRACTION_PROMPT = """你是一个信息提取助手。根据以下对话，提取关键的结构化信息。

对话内容：
{conversation}

请提取所有值得记忆的关键事实，按以下 JSON 格式输出（只输出 JSON，不要其他内容）：
[
  {{"key": "事实的简短标识", "value": "事实的具体内容", "category": "preference|monitored_system|action_history|user_info|general"}}
]

提取规则：
1. 只提取明确陈述的事实，不要推测
2. 如果用户提到偏好的系统名称或检测对象，记录下来
3. 如果用户要求执行了某个操作，记录下来
4. 如果没有值得提取的信息，返回空数组 []
5. key 使用中文简短描述，不超过 50 字"""


class MemoryExtractor:

    @staticmethod
    async def extract_facts(session_id: str,
                            recent_messages: List[Dict],
                            existing_facts: List[Dict]) -> List[Dict]:
        conversation = "\n".join([
            f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}"
            for m in recent_messages
        ])

        existing_str = ""
        if existing_facts:
            items = [f"- [{f['category']}] {f['key']}: {f['value']}" for f in existing_facts]
            existing_str = "\n现有记忆：\n" + "\n".join(items)

        prompt = EXTRACTION_PROMPT.format(conversation=conversation)
        if existing_str:
            prompt += f"\n{existing_str}\n请更新/补充上述记忆，只输出新增或更新的条目。"

        try:
            llm = LLMFactory.create_chat_model(max_tokens=500, timeout=30, temperature=0.3)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            facts = MemoryExtractor._parse_response(response.content)
            logger.info(f"事实抽取完成: session={session_id[:8]}, 抽取{len(facts)}条")
            return facts
        except Exception as e:
            logger.error(f"事实抽取失败: {e}")
            return []

    @staticmethod
    def _parse_response(text: str) -> List[Dict]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]
        try:
            result = json.loads(text)
            if isinstance(result, list):
                valid = []
                for item in result:
                    if isinstance(item, dict) and "key" in item and "value" in item:
                        valid.append({
                            "key": str(item["key"])[:256],
                            "value": str(item["value"]),
                            "category": str(item.get("category", "general"))[:64],
                        })
                return valid
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"事实抽取 JSON 解析失败，尝试逐条恢复: {e}")

        # 容错：用正则逐条提取 JSON 对象，即使数组不完整
        import re
        valid = []
        pattern = r'\{\s*"key"\s*:\s*"([^"]*)"\s*,\s*"value"\s*:\s*"([^"]*)"\s*(?:,\s*"category"\s*:\s*"([^"]*)")?\s*\}'
        for m in re.finditer(pattern, text):
            valid.append({
                "key": m.group(1)[:256],
                "value": m.group(2),
                "category": m.group(3)[:64] if m.group(3) else "general",
            })
        if valid:
            logger.info(f"容错解析: 从残缺 JSON 中恢复 {len(valid)} 条事实")
        return valid

    @staticmethod
    async def maybe_extract(session_id: str, new_messages: List[Dict]) -> int:
        count = await SessionManager.get_message_count(session_id)
        if count < 1 or count % 5 != 0:
            return 0

        locked = await SessionManager.acquire_extraction_lock(session_id)
        if not locked:
            return 0

        try:
            existing = await SessionManager.get_facts(session_id)
            # 拉取最近 10 条消息作为抽取上下文，而非仅当前轮的 2 条
            context_messages = await SessionManager.get_context_messages(session_id, max_count=10)
            facts = await MemoryExtractor.extract_facts(session_id, context_messages, existing)
            saved = 0
            for f in facts:
                await SessionManager.upsert_fact(session_id, f["key"], f["value"], f.get("category", "general"))
                saved += 1
            if saved:
                logger.info(f"会话 {session_id[:8]} 新增 {saved} 条记忆事实")
            return saved
        finally:
            await SessionManager.release_extraction_lock(session_id)
