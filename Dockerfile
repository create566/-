# 智能监控平台 - Dockerfile
# 构建: docker build -t smart-monitor .

FROM python:3.11-slim

# 防止 Python 字节码缓存
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 工作目录
WORKDIR /app

# 安装系统依赖（for psutil, pymysql, langchain 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -e .

# 复制应用代码
COPY app/ ./app/
COPY static/ ./static/
COPY data/ ./data/ 2>/dev/null || true

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口
EXPOSE 9900

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9900/health || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9900"]