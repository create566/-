"""配置管理模块 — 全部配置从 .env 读取，不自带任何密钥"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ──────────── 应用 ────────────
    app_name: str = "SmartMonitor"
    app_version: str = "1.2.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 9900

    # ──────────── 数据库 ────────────
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "smart_monitor"

    # ──────────── Redis ────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # ──────────── LLM ────────────
    # provider: vllm / ollama / openai / dashscope
    # vLLM:       base_url=http://localhost:8000/v1
    # Ollama:     base_url=http://localhost:11434/v1
    # DashScope:  base_url=https://dashscope.aliyuncs.com/compatible-mode/v1
    # DeepSeek:   base_url=https://api.deepseek.com
    llm_provider: str = "vllm"
    llm_api_key: str = ""
    llm_api_base: str = "http://localhost:8000/v1"
    llm_model: str = "Qwen2.5-7B-Instruct"

    # Ollama 专用（llm_provider=ollama 时覆盖 llm_model）
    ollama_model: str = "qwen2.5:7b"

    # DashScope 专用（llm_provider=dashscope 时覆盖 llm_model）
    dashscope_model: str = "qwen-plus"

    # ──────────── Embedding ────────────
    embedding_provider: str = "local"
    embedding_api_key: str = ""
    embedding_api_base: str = "http://localhost:11434/v1"
    embedding_model: str = "bge-large-zh-v1.5"
    embedding_dim: int = 1024
    embedding_cloud_model: str = "text-embedding-3-small"
    embedding_cloud_dim: int = 1536

    # ──────────── Milvus ────────────
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_collection: str = "knowledge_base"

    # ──────────── 飞书 ────────────
    feishu_webhook_url: str = ""
    feishu_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""

    # ──────────── Prometheus ────────────
    prometheus_url: str = "http://localhost:9090"

    # ──────────── 报告保存 ────────────
    report_dir: str = "./reports"

    # ──────────── API 认证 ────────────
    api_key: str = "change-me-in-production"


# 全局配置实例
config = Settings()