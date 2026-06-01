"""配置管理模块 — 支持 MySQL + Redis 生产配置"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    app_name: str = "SmartMonitor"
    app_version: str = "1.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 9900

    # 数据库
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "smart_monitor"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # LLM（OpenAI 兼容模式，支持本地/云端）
    # 使用说明：
    #   vLLM: llm_provider="vllm", llm_api_base="http://localhost:8000/v1"
    #   Ollama: llm_provider="ollama", llm_api_base="http://localhost:11434/v1"
    #   云端: llm_provider="openai", llm_api_base="https://api.deepseek.com"
    llm_provider: str = "vllm"  # vllm / ollama / openai
    llm_api_key: str = "local"
    llm_api_base: str = "http://localhost:8000/v1"  # vLLM 默认端口
    llm_model: str = "Qwen2.5-7B-Instruct"  # 根据实际模型名称修改

    # Ollama 特定配置（llm_provider="ollama" 时使用）
    ollama_model: str = "qwen2.5:7b"  # Ollama 模型名称（与 llm_model 不同）

    # Milvus 向量数据库配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_collection: str = "knowledge_base"

    # Embedding 模型配置（用于向量检索）
    # 使用说明：
    #   embedding_provider="local": 使用本地服务（Ollama/LMA-Factory）
    #   embedding_provider="openai": 使用 OpenAI API（text-embedding-3-small）
    #   embedding_provider="azure": 使用 Azure OpenAI
    embedding_provider: str = "local"  # local / openai / azure
    embedding_api_key: str = "local"
    embedding_api_base: str = "http://localhost:11434/v1"  # 本地服务地址
    embedding_model: str = "bge-large-zh-v1.5"  # 本地模型名
    embedding_dim: int = 1024

    # 云端 Embedding 备选配置（embedding_provider="openai" 或 "azure" 时使用）
    embedding_cloud_model: str = "text-embedding-3-small"  # OpenAI 模型
    embedding_cloud_dim: int = 1536  # OpenAI 维度

    # 飞书告警通知
    feishu_webhook_url: str = ""
    feishu_enabled: bool = True

    # 飞书机器人（接收消息 / @机器人查询状态）
    feishu_app_id: str = "cli_aa93d9202afa5bd9"
    feishu_app_secret: str = "4muhsqpI7Rno2YOdofE3tbx0rtMiHOhO"

    # Prometheus 默认地址（远程检测器使用）
    prometheus_url: str = "http://localhost:9090"

    # 报告保存目录
    report_dir: str = "D:\桌面\智能仓库\reports"

    # API 认证
    api_key: str = "sm_monitor_2024_secret_key_change_in_production"


# 全局配置实例
config = Settings()