"""会话管理器 — 会话、消息、事实的 CRUD + Redis 缓存"""

import uuid
import json
from typing import List, Dict, Optional
from loguru import logger

from app.dao import store
from app.chat.redis_client import get_redis

MAX_CONTEXT_MESSAGES = 20
EXTRACT_EVERY_N = 5
REDIS_TTL = 3600


class SessionManager:

    @staticmethod
    async def get_or_create_session(chat_source: str, source_id: str,
                                     title: str = "") -> Dict:
        existing = store.get_session_by_source(chat_source, source_id)
        if existing:
            store.update_session_timestamp(existing["id"])
            return existing

        session_id = str(uuid.uuid4())
        sess = store.create_session({
            "id": session_id,
            "chat_source": chat_source,
            "source_id": source_id,
            "title": title,
        })
        logger.info(f"新会话: {session_id[:8]} ({chat_source}/{source_id[:20]})")
        return sess

    @staticmethod
    async def save_message(session_id: str, role: str, content: str) -> Dict:
        msg = store.save_message({
            "session_id": session_id,
            "role": role,
            "content": content,
        })
        store.update_session_timestamp(session_id)

        r = await get_redis()
        if r:
            try:
                key = f"sm:{session_id}:messages"
                await r.rpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
                await r.ltrim(key, -50, -1)
                await r.expire(key, REDIS_TTL)
            except Exception:
                pass

        return msg

    @staticmethod
    async def get_context_messages(session_id: str, max_count: int = MAX_CONTEXT_MESSAGES) -> List[Dict]:
        r = await get_redis()
        if r:
            try:
                key = f"sm:{session_id}:messages"
                raw = await r.lrange(key, -max_count, -1)
                if raw:
                    return [json.loads(item) for item in raw]
            except Exception:
                pass

        messages = store.get_recent_messages(session_id, max_count)
        if r:
            try:
                key = f"sm:{session_id}:messages"
                pipe = r.pipeline()
                pipe.delete(key)
                for m in messages:
                    pipe.rpush(key, json.dumps({"role": m["role"], "content": m["content"]}, ensure_ascii=False))
                pipe.expire(key, REDIS_TTL)
                await pipe.execute()
            except Exception:
                pass

        return [{"role": m["role"], "content": m["content"]} for m in messages]

    @staticmethod
    async def get_message_count(session_id: str) -> int:
        return store.get_message_count(session_id)

    @staticmethod
    async def upsert_fact(session_id: str, key: str, value: str,
                          category: str = "general") -> Dict:
        fact = store.save_fact({
            "session_id": session_id,
            "key": key,
            "value": value,
            "category": category,
        })

        r = await get_redis()
        if r:
            try:
                hash_key = f"sm:{session_id}:facts"
                await r.hset(hash_key, key, json.dumps(fact, ensure_ascii=False))
                await r.expire(hash_key, REDIS_TTL)
            except Exception:
                pass

        return fact

    @staticmethod
    async def get_facts(session_id: str) -> List[Dict]:
        r = await get_redis()
        if r:
            try:
                hash_key = f"sm:{session_id}:facts"
                raw = await r.hgetall(hash_key)
                if raw:
                    facts = []
                    for key_bytes, val_bytes in raw.items():
                        try:
                            facts.append(json.loads(val_bytes))
                        except Exception:
                            pass
                    return facts
            except Exception:
                pass

        facts = store.get_facts(session_id)
        if r and facts:
            try:
                hash_key = f"sm:{session_id}:facts"
                mapping = {f["key"]: json.dumps(f, ensure_ascii=False) for f in facts}
                pipe = r.pipeline()
                pipe.delete(hash_key)
                if mapping:
                    pipe.hset(hash_key, mapping=mapping)
                pipe.expire(hash_key, REDIS_TTL)
                await pipe.execute()
            except Exception:
                pass

        return facts

    @staticmethod
    async def list_sessions(limit: int = 50) -> List[Dict]:
        return store.list_sessions(limit)

    @staticmethod
    async def delete_session(session_id: str) -> bool:
        r = await get_redis()
        if r:
            try:
                pipe = r.pipeline()
                pipe.delete(f"sm:{session_id}:messages")
                pipe.delete(f"sm:{session_id}:facts")
                pipe.delete(f"sm:{session_id}:meta")
                await pipe.execute()
            except Exception:
                pass

        return store.delete_session(session_id)

    @staticmethod
    async def acquire_extraction_lock(session_id: str) -> bool:
        r = await get_redis()
        if r:
            try:
                return await r.set(f"sm:{session_id}:lock", "1", nx=True, ex=30)
            except Exception:
                pass
        return True  # Redis 不可用时默认允许执行

    @staticmethod
    async def release_extraction_lock(session_id: str):
        r = await get_redis()
        if r:
            try:
                await r.delete(f"sm:{session_id}:lock")
            except Exception:
                pass
