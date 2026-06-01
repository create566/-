"""飞书通知工具 — 仅群推送"""

import requests
from loguru import logger
from app.config import config


class FeishuNotifier:
    """飞书群机器人通知器"""

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or config.feishu_webhook_url
        self.enabled = config.feishu_enabled and bool(self.webhook_url)
        if self.enabled:
            logger.info(f"FeishuNotifier 初始化完成，Webhook: {self.webhook_url[:50]}...")

    def send_text(self, text: str) -> bool:
        """发送文本消息"""
        if not self.enabled:
            return False
        try:
            payload = {"msg_type": "text", "content": {"text": text}}
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            result = resp.json()
            if result.get("code") == 0:
                logger.info(f"飞书消息发送成功: {text[:50]}...")
                return True
            logger.error(f"飞书消息发送失败: {result}")
            return False
        except Exception as e:
            logger.error(f"飞书消息发送异常: {e}")
            return False

    def send_markdown(self, title: str, content: str) -> bool:
        """发送 Markdown 卡片消息"""
        if not self.enabled:
            return False
        try:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": title},
                        "template": "red"
                    },
                    "elements": [{"tag": "markdown", "content": content}]
                }
            }
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            result = resp.json()
            if result.get("code") == 0:
                logger.info(f"飞书 Markdown 发送成功: {title}")
                return True
            logger.error(f"飞书 Markdown 发送失败: {result}")
            return False
        except Exception as e:
            logger.error(f"飞书 Markdown 发送异常: {e}")
            return False
