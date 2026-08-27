# 智能监控平台 - Dockerfile
# 构建: docker build -t smart-monitor .
# 运行: docker compose up -d

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 wheel 包（本地 vendor）
COPY wheel/ ./wheel/
RUN pip install --no-cache-dir wheel/lark_oapi-1.6.7-py3-none-any.whl

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] \
    langgraph langchain-openai langchain-core \
    pydantic pydantic-settings \
    httpx loguru python-dotenv \
    apscheduler psutil \
    pymysql redis sqlalchemy aiomysql \
    pymilvus milvus-lite \
    prometheus-client \
    pytest pytest-asyncio pytest-cov \
    aiohttp lark-oapi

# 复制应用代码
COPY pyproject.toml /app/pyproject.toml
COPY app/ ./app/
COPY configs/ ./configs/
COPY static/ ./static/
COPY scripts/ ./scripts/
COPY vendor/ ./vendor/
COPY run_feishu_ws.py /app/run_feishu_ws.py
COPY run_feishu_ws_direct.py /app/run_feishu_ws_direct.py
COPY init_mysql.sql /app/init_mysql.sql

# 目录
COPY start.sh /app/start.sh
RUN mkdir -p data logs reports && chmod +x /app/start.sh

# 暴露端口
EXPOSE 9900

# 启动（主服务 + 飞书 WS 双进程）
CMD ["/app/start.sh"]
