#!/usr/bin/env python3
"""飞书 WebSocket — 从环境变量读取凭证，不硬编码"""

import sys
import os

# 先把 vendor 加到 path
_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if os.path.exists(os.path.join(_vendor, "lark_oapi")):
    sys.path.insert(0, _vendor)

from run_feishu_ws import FeishuWsProcess
import time
import signal

# 从环境变量读取（优先），回退到 .env 文件
from dotenv import load_dotenv
load_dotenv()

APP_ID = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:9900")

if not APP_ID or not APP_SECRET:
    print("❌ 请设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
    print("   或在 .env 文件中配置")
    sys.exit(1)

ws = FeishuWsProcess(APP_ID, APP_SECRET, api_base=API_BASE)
ws.run()

def signal_handler(sig, frame):
    ws.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

while ws._running:
    time.sleep(1)
