"""对话服务 — 编排会话、记忆、LLM 调用"""

from typing import List, Dict
from loguru import logger

from app.dao import store
from app.core.llm_factory import LLMFactory
from app.chat.session_manager import SessionManager
from app.chat.memory_extractor import MemoryExtractor
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

SYSTEM_PROMPT_TEMPLATE = """你是智能监控平台的 AI 助手。你可以帮助用户查看监控状态、分析故障、提供建议。请用简洁、友好的语气回答。

当前已知监控系统：
{sys_info}

--- 知识库参考（有则参考，无则忽略）---
{knowledge_section}

--- 对话记忆 ---
{facts_section}
---

请基于以上信息回答用户问题。"""


class ChatService:

    @staticmethod
    async def chat(chat_source: str, source_id: str,
                   user_message: str) -> str:
        sess = await SessionManager.get_or_create_session(chat_source, source_id)
        session_id = sess["id"]

        history = await SessionManager.get_context_messages(session_id)
        facts = await SessionManager.get_facts(session_id)
        sys_info = ChatService._build_sys_info()

        # 检索知识库
        from app.agent.knowledge_search import search_by_text
        knowledge_section = await search_by_text(user_message)
        if not knowledge_section:
            knowledge_section = "暂无相关知识库内容"

        messages = ChatService._build_message_list(history, facts, user_message, sys_info, knowledge_section)

        try:
            llm = LLMFactory.create_chat_model(max_tokens=500, timeout=60)
            response = await llm.ainvoke(messages)
            answer = response.content.strip()
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            answer = "抱歉，AI 助手暂时无法回答这个问题。"

        await SessionManager.save_message(session_id, "user", user_message)
        await SessionManager.save_message(session_id, "assistant", answer)

        await MemoryExtractor.maybe_extract(
            session_id,
            [{"role": "user", "content": user_message}, {"role": "assistant", "content": answer}],
        )

        if len(answer) > 600:
            answer = answer[:600] + "..."
        return answer

    @staticmethod
    async def get_session_info(session_id: str) -> Dict:
        sess = store.get_chat_session(session_id)
        if not sess:
            return None
        messages = await SessionManager.get_context_messages(session_id)
        facts = await SessionManager.get_facts(session_id)
        return {
            "session_id": session_id,
            "chat_source": sess["chat_source"],
            "source_id": sess["source_id"],
            "title": sess.get("title", ""),
            "message_count": len(messages),
            "history": messages,
            "facts": facts,
            "created_at": sess.get("created_at"),
            "updated_at": sess.get("updated_at"),
        }

    @staticmethod
    def _build_message_list(history: List[Dict], facts: List[Dict],
                            user_message: str, sys_info: str,
                            knowledge_section: str = "暂无相关知识库内容") -> List:
        facts_section = ChatService._format_facts(facts)
        system_content = SYSTEM_PROMPT_TEMPLATE.format(
            sys_info=sys_info,
            facts_section=facts_section,
            knowledge_section=knowledge_section,
        )

        msg_list = [SystemMessage(content=system_content)]
        for h in history:
            if h["role"] == "user":
                msg_list.append(HumanMessage(content=h["content"]))
            elif h["role"] == "assistant":
                msg_list.append(AIMessage(content=h["content"]))

        msg_list.append(HumanMessage(content=user_message))
        return msg_list

    @staticmethod
    def _build_sys_info() -> str:
        systems = store.list_systems()
        if not systems:
            return "暂无注册系统"
        return "\n".join([
            f"- {s.get('name', '?')} (状态:{s.get('status', '?')}, 健康分:{s.get('health_score', 100)})"
            for s in systems
        ])

    @staticmethod
    def _format_facts(facts: List[Dict]) -> str:
        if not facts:
            return "暂无对话记忆"

        by_category: Dict[str, List[Dict]] = {}
        for f in facts:
            cat = f.get("category", "general")
            by_category.setdefault(cat, []).append(f)

        cat_labels = {
            "preference": "用户偏好",
            "monitored_system": "关注系统",
            "action_history": "操作记录",
            "user_info": "用户信息",
            "general": "一般信息",
        }

        lines = []
        for cat in cat_labels:
            items = by_category.get(cat, [])
            if not items:
                continue
            lines.append(f"[{cat_labels[cat]}]")
            for item in items:
                lines.append(f"- {item['key']}: {item['value']}")

        # 处理不在已知类别中的事实
        for cat, items in by_category.items():
            if cat not in cat_labels:
                if not lines or not lines[-1].startswith("["):
                    lines.append(f"[{cat}]")
                for item in items:
                    lines.append(f"- {item['key']}: {item['value']}")

        return "\n".join(lines)
