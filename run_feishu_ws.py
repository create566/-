#!/usr/bin/env python3
"""飞书 WebSocket 独立进程 — 避免与 FastAPI 主服务事件循环冲突"""

import sys
import os
import json
import time
import asyncio
import subprocess
import requests as http_requests
import threading
import signal

_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if os.path.exists(os.path.join(_vendor, "lark_oapi")):
    sys.path.insert(0, _vendor)

from lark_oapi.ws import Client
from lark_oapi.event.dispatcher_handler import EventDispatcherHandlerBuilder
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
from lark_oapi.core.enum import LogLevel
from loguru import logger
import loguru

# 日志输出到 stdout，让父进程能看到（仅独立运行时配置）
if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:HH:mm:ss} | {level} | {message}", level="INFO")


class FeishuWsProcess:
    def __init__(self, app_id: str, app_secret: str, api_base: str = "http://127.0.0.1:9901"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_base = api_base
        self._client = None
        self._token = None
        self._token_expire = 0
        self._running = False

    def _get_token(self):
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        try:
            resp = http_requests.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10,
            )
            data = resp.json()
            self._token = data.get("tenant_access_token", "")
            self._token_expire = time.time() + data.get("expire", 7200)
            return self._token
        except Exception as e:
            logger.error(f"获取飞书token失败: {e}")
            return ""

    def _on_message(self, event: P2ImMessageReceiveV1) -> None:
        print(f"【收到事件】type={type(event).__name__} event={event}")
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

            if not text and not is_mentioned:
                return

            # 清洗 @标签，提取纯文本命令（如 "<at user_id=\"xxx\">@机器人</at> 状态" → "状态"）
            import re as _re
            clean_text = _re.sub(r"<at[^>]*>[^<]*</at>", "", text).strip()

            logger.info(f"收到 msg_id={msg_id[:8] if msg_id else '?'} chat={chat_id} text={text[:60]} clean={clean_text[:60]}")

            # 调用主服务 API 获取回复
            reply_text = self._get_reply_from_api(clean_text)
            if reply_text:
                self._send_reply(chat_id, reply_text)

        except Exception as e:
            logger.error(f"处理消息异常: {e}")

    def _get_reply_from_api(self, text: str) -> str:
        """调用主服务的飞书状态 API 获取回复内容"""
        try:
            # 告诉主服务这是什么消息，它返回回复内容
            resp = http_requests.post(
                f"{self.api_base}/api/feishu/handle",
                json={"text": text},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("reply", "")
            logger.warning(f"主服务 API 返回: {resp.status_code}")
        except Exception as e:
            logger.error(f"调用主服务 API 失败: {e}")
        return ""

    def _send_reply(self, chat_id: str, text: str):
        try:
            token = self._get_token()
            if not token:
                return
            resp = http_requests.post(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": text})},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("回复成功")
            else:
                logger.error(f"回复失败: HTTP {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"回复异常: {e}")

    def run(self):
        """在新线程的事件循环中运行 WebSocket"""
        def _thread_target():
            self._running = True
            handler = (
                EventDispatcherHandlerBuilder("", "")
                .register_p2_im_message_receive_v1(self._on_message)
                .build()
            )

            self._client = Client(
                app_id=self.app_id,
                app_secret=self.app_secret,
                event_handler=handler,
                log_level=LogLevel.INFO,
            )

            while self._running:
                try:
                    # 每次重连都创建新的独立 event loop
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._client.start())
                except Exception as e:
                    logger.error(f"WS 连接异常: {e}")
                finally:
                    try:
                        loop.close()
                    except Exception:
                        pass
                if self._running:
                    logger.info("5秒后重连...")
                    time.sleep(5)

        t = threading.Thread(target=_thread_target, daemon=True, name="feishu-ws")
        t.start()
        logger.info(f"飞书 WS 进程启动 (app_id={self.app_id[:8]}...)")

    def stop(self):
        self._running = False
        if self._client:
            self._client._running = False
        logger.info("飞书 WS 进程已停止")


if __name__ == "__main__":
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        print("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET 环境变量")
        sys.exit(1)

    api_base = os.environ.get("FEISHU_API_BASE", "http://127.0.0.1:9901")
    ws = FeishuWsProcess(app_id, app_secret, api_base=api_base)
    ws.run()

    # 优雅退出
    def signal_handler(sig, frame):
        ws.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 保持进程运行
    while ws._running:
        time.sleep(1)