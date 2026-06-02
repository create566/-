"""飞书机器人 — HTTP 轮询接收消息（不用任何 SDK）

流程: 获取群列表 → 轮询每个群的最新消息 → 匹配「状态」→ 回复
"""

import time
import json
import requests
from loguru import logger
from app.config import config


class FeishuBotListener:
    def __init__(self, message_handler=None):
        self.message_handler = message_handler
        self.app_id = config.feishu_app_id
        self.app_secret = config.feishu_app_secret
        self._token = None
        self._token_expire = 0
        self._running = False
        self._seen_msgs = set()  # 已处理的消息ID，避免重复回复
        logger.info("FeishuBotListener 已初始化")

    def _get_token(self):
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        try:
            resp = requests.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10,
            )
            data = resp.json()
            self._token = data.get("tenant_access_token", "")
            self._token_expire = time.time() + data.get("expire", 7200)
            logger.debug(f"飞书 token 已刷新")
            return self._token
        except Exception as e:
            logger.error(f"获取飞书token失败: {e}")
            return ""

    def start_websocket(self):
        import threading
        def _run():
            self._running = True
            logger.info("飞书消息轮询已启动（每5秒一次）")
            while self._running:
                try:
                    self._poll()
                except Exception as e:
                    logger.error(f"轮询异常: {e}")
                time.sleep(5)
        t = threading.Thread(target=_run, daemon=True, name="feishu-poll")
        t.start()

    def _poll(self):
        token = self._get_token()
        if not token:
            return
        headers = {"Authorization": f"Bearer {token}"}

        # 1. 获取群列表
        try:
            resp = requests.get(
                "https://open.feishu.cn/open-apis/im/v1/chats",
                headers=headers,
                params={"page_size": 20},
                timeout=10,
            )
            if resp.status_code != 200:
                return
            chats = resp.json().get("data", {}).get("items", [])
        except Exception:
            return

        # 2. 查每个群的最新消息
        for chat in chats:
            chat_id = chat.get("chat_id", "")
            chat_name = chat.get("name", "?")
            if not chat_id:
                continue
            try:
                resp2 = requests.get(
                    "https://open.feishu.cn/open-apis/im/v1/messages",
                    headers=headers,
                    params={
                        "receive_id_type": "chat_id",
                        "receive_id": chat_id,
                        "page_size": 5,
                        "sort_type": "ByCreateTimeDesc",
                    },
                    timeout=10,
                )
                if resp2.status_code != 200:
                    continue
                items = resp2.json().get("data", {}).get("items", [])
            except Exception:
                continue

            # 3. 检查消息
            for item in items:
                msg_id = item.get("message_id", "")
                if msg_id in self._seen_msgs:
                    continue
                self._seen_msgs.add(msg_id)

                msg_type = item.get("msg_type", "")
                if msg_type != "text":
                    continue

                try:
                    body = item.get("body", {})
                    content_str = body.get("content", "{}")
                    content_obj = json.loads(content_str)
                    text = content_obj.get("text", "").strip()
                except Exception:
                    continue

                if not text:
                    continue

                # 解析 @ 机器人 的 user_id
                mentions = item.get("mentions", []) or []
                mention_keys = [m.get("key", "") for m in mentions]
                mention_ids = [m.get("id", "") for m in mentions]

                # 检查是否 @了机器人（text 内容含 <at></at> 标签 或 mentions 含 bot key）
                is_mentioned = (
                    "<at" in text or
                    "bot" in mention_keys or
                    any(k.startswith("@") for k in mention_keys)
                )
                t = text.lower()
                is_status_query = any(k in t for k in ["状态", "status", "在线", "check", "查询", "监控"])

                logger.info(f"飞书[{chat_name}] msg_id={msg_id[:8]} text={text[:60]} mentions={mention_keys} is_mentioned={is_mentioned} is_status={is_status_query}")

                # 只要 @了机器人 或包含上述关键词之一，就回复
                if is_mentioned or is_status_query:
                    if self.message_handler:
                        import asyncio
                        try:
                            reply = asyncio.run(self.message_handler("", text))
                            if reply:
                                self._reply(token, msg_id, reply)
                        except Exception as e:
                            logger.error(f"处理消息异常: {e}")

        # 限制缓存大小
        if len(self._seen_msgs) > 500:
            self._seen_msgs = set(list(self._seen_msgs)[-200:])

    def _reply(self, token, message_id, text):
        try:
            resp = requests.post(
                f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"content": json.dumps({"text": text}), "msg_type": "text"},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"飞书回复成功")
            else:
                logger.error(f"飞书回复失败: HTTP {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"飞书回复异常: {e}")
