"""飞书机器人 — WebSocket 长连接接收 @机器人 消息（使用 lark-oapi SDK）"""

import sys
import os
import json
import time
import asyncio
import requests as http_requests
from loguru import logger

_vendor = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "vendor")
if os.path.exists(os.path.join(_vendor, "lark_oapi")):
    sys.path.insert(0, _vendor)

from lark_oapi.ws import Client
from lark_oapi.event.dispatcher_handler import EventDispatcherHandlerBuilder
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
from lark_oapi.core.enum import LogLevel


# 全局 loop，供外部 stop 使用
_ws_loop: asyncio.AbstractEventLoop = None
_ws_client: Client = None


async def _run_websocket(app_id: str, app_secret: str, handler) -> None:
    """在 FastAPI 主事件循环中运行 WebSocket"""
    global _ws_loop, _ws_client

    _ws_loop = asyncio.get_running_loop()
    _ws_client = Client(
        app_id=app_id,
        app_secret=app_secret,
        event_handler=handler,
        log_level=LogLevel.INFO,
    )

    logger.info("飞书 WebSocket 正在连接...")
    try:
        await _ws_client.start()
    except Exception as e:
        logger.error(f"飞书 WebSocket 连接异常: {e}")


def start_feishu_ws_bot(app_id: str, app_secret: str, message_handler) -> "FeishuWebSocketBot":
    """在 FastAPI 启动时调用，挂载到主事件循环"""
    global _feishu_ws_bot
    if _feishu_ws_bot is not None:
        return _feishu_ws_bot

    handler = (
        EventDispatcherHandlerBuilder("", "")
        .register_p2_im_message_receive_v1(lambda e: _on_message(e, message_handler))
        .build()
    )

    # 把 WebSocket 任务注册到 FastAPI 主事件循环
    loop = asyncio.get_running_loop()
    task = loop.create_task(_run_websocket(app_id, app_secret, handler))
    logger.info(f"飞书 WebSocket 任务已注册到主事件循环")

    _feishu_ws_bot = FeishuWebSocketBot(app_id, app_secret, message_handler)
    return _feishu_ws_bot


def _on_message(event: P2ImMessageReceiveV1, message_handler) -> None:
    """收到消息事件的回调"""
    try:
        msg = event.event.message
        if msg is None:
            return

        chat_id = msg.chat_id or ""
        msg_id = msg.message_id or ""
        msg_type = msg.message_type or ""
        text = ""

        if msg_type == "text":
            try:
                content = json.loads(msg.content or "{}")
                text = content.get("text", "").strip()
            except Exception:
                pass

        mentions = msg.mentions or []
        mention_keys = [m.key for m in mentions] if mentions else []
        is_mentioned = "bot" in mention_keys or any(k.startswith("@") for k in mention_keys)

        logger.info(f"飞书 WS msg_id={msg_id[:8] if msg_id else '?'} chat={chat_id} type={msg_type} text={text[:60]} mentions={mention_keys}")

        if not text and not is_mentioned:
            return

        if message_handler:
            try:
                loop = asyncio.get_running_loop()
                # 在主循环中异步运行 handler
                future = asyncio.run_coroutine_threadsafe(message_handler("", text), loop)
                reply = future.result(timeout=30)
                if reply:
                    _send_reply_sync(chat_id, reply,
                        app_id=os.getenv("FEISHU_APP_ID", ""),
                        app_secret=os.getenv("FEISHU_APP_SECRET", ""))
            except Exception as e:
                logger.error(f"处理飞书消息异常: {e}")

    except Exception as e:
        logger.error(f"处理飞书消息异常: {e}")


def _send_reply_sync(chat_id: str, text: str, app_id: str, app_secret: str):
    """同步发送回复（供线程中调用）"""
    try:
        resp = http_requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        token = resp.json().get("tenant_access_token", "")
        if not token:
            return

        resp2 = http_requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": text})},
            timeout=10,
        )
        if resp2.status_code == 200:
            logger.info("飞书 WS 回复成功")
        else:
            logger.error(f"飞书 WS 回复失败: HTTP {resp2.status_code} {resp2.text[:200]}")
    except Exception as e:
        logger.error(f"飞书 WS 回复异常: {e}")


class FeishuWebSocketBot:
    """占位类，保持 API 兼容"""

    def __init__(self, app_id: str, app_secret: str, message_handler=None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.message_handler = message_handler
        logger.info(f"FeishuWebSocketBot 已创建 (app_id={app_id[:8]}...)")

    def stop(self):
        global _ws_client
        if _ws_client:
            _ws_client._running = False
            logger.info("飞书 WebSocket 已停止")


_feishu_ws_bot = None