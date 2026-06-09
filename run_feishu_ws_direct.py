#!/usr/bin/env python3
"""飞书 WebSocket — 直接用代码内凭证，不依赖环境变量"""

import sys
import os

# 先把 vendor 加到 path
_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if os.path.exists(os.path.join(_vendor, "lark_oapi")):
    sys.path.insert(0, _vendor)

from run_feishu_ws import FeishuWsProcess
import time
import signal

APP_ID = "cli_aa9475644e385cc2"
APP_SECRET = "rLgezJJ57bOoIcfDdH4nFbNHAlby4YLk"
API_BASE = "http://127.0.0.1:9900"

ws = FeishuWsProcess(APP_ID, APP_SECRET, api_base=API_BASE)
ws.run()

def signal_handler(sig, frame):
    ws.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

while ws._running:
    time.sleep(1)
