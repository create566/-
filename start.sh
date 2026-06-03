#!/bin/bash
echo "Starting SmartMonitor..."
uvicorn app.main:app --host 0.0.0.0 --port 9900 &

sleep 5
if [ -n "$FEISHU_APP_ID" ] && [ -n "$FEISHU_APP_SECRET" ]; then
    echo "Starting Feishu WebSocket..."
    export FEISHU_API_BASE="http://127.0.0.1:9900"
    python run_feishu_ws.py
else
    echo "Feishu not configured, skipping WS"
    wait
fi
