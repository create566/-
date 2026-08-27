"""智能监控平台 — FastAPI 应用入口"""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import time
import os

from app.config import config
from loguru import logger
from app.api import health, monitoring
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.metrics.exporter import metrics_endpoint


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger.info("=" * 60)
    logger.info(f"🚀 {config.app_name} v{config.app_version} 启动中...")
    logger.info(f"🌐 监听地址: http://{config.host}:{config.port}")

    # ① 初始化数据库
    from app.dao import store
    store.init_database(config)
    logger.info(f"📦 数据库模式: {'MySQL' if not store.is_json_mode() else 'JSON (开发)'}")

    # ② 验证 LLM（本地模型启动慢，超时设长一些）
    import time
    logger.info("🔑 验证 LLM 连接...")
    llm_ready = False
    for attempt in range(1, 6):
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage
            test_llm = ChatOpenAI(
                model=config.llm_model, api_key=config.llm_api_key,
                base_url=config.llm_api_base, max_tokens=5, streaming=False,
                timeout=60, max_retries=1,
            )
            test_llm.invoke([HumanMessage(content="hi")])
            logger.info("✅ LLM 连接正常")
            llm_ready = True
            break
        except Exception as e:
            logger.warning(f"⏳ LLM 不可用(第{attempt}次): {e}")
            if attempt < 5:
                time.sleep(10)

    if not llm_ready:
        logger.error("❌ LLM 连接失败，应用继续启动但 AI 功能可能受影响")

    # ③ 初始化飞书通知器
    if config.feishu_enabled and config.feishu_webhook_url:
        from app.tools.feishu_notifier import FeishuNotifier
        from app.alert.pipeline import alert_pipeline
        alert_pipeline.feishu = FeishuNotifier(config.feishu_webhook_url)
        logger.info("✅ 飞书通知器已就绪")

    # ④ 启动调度器
    from app.scheduler.engine import monitor_scheduler
    from app.alert.pipeline import alert_pipeline

    async def check_system(system_id: str):
        system = store.get_system(system_id)
        if system and system.get("status") == "active":
            incident = await alert_pipeline.run(system)
            if incident:
                store.create_incident(incident)

    monitor_scheduler.set_handler(check_system)
    monitor_scheduler.start()

    # ⑤ 加载所有 active 系统
    for s in store.list_systems():
        if s.get("status") == "active":
            monitor_scheduler.schedule(s["id"], s["check_interval_seconds"])
            logger.info(f"📋 已加载系统: {s['name']} (间隔{s['check_interval_seconds']}s)")

    # ⑥ 初始化 Redis（可选，不可用时仅 warn）
    try:
        from app.chat.redis_client import get_redis as _get_redis
        r = await _get_redis()
        if r:
            await r.ping()
            logger.info("Redis 已连接，会话缓存已启用")
    except Exception as e:
        logger.warning(f"Redis 不可用，会话缓存将仅使用数据库: {e}")

    # ⑧ 飞书 WebSocket 由独立进程 run_feishu_ws.py 管理
    #    新开终端启动: $env:FEISHU_APP_ID="..."; $env:FEISHU_APP_SECRET="..."; python run_feishu_ws.py
    if config.feishu_app_id and config.feishu_app_secret:
        logger.info(f"🤖 飞书 WebSocket 请在新终端独立启动 (app_id={config.feishu_app_id[:8]}...)")

    # ⑨ 确保检测器已注册
    import app.detectors.local    # noqa: F401
    import app.detectors.remote   # noqa: F401
    from app.detectors.registry import DetectorRegistry
    registered = DetectorRegistry.list_all()
    logger.info(f"🔧 已注册检测器: {list(registered.keys())}")

    logger.info("=" * 60)
    logger.info("✅ 智能监控平台启动完成")

    yield

    monitor_scheduler.shutdown()
    logger.info(f"👋 {config.app_name} 关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="智能 OnCall 监控平台 — 自动检测、智能诊断、飞书告警",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 认证中间件
app.add_middleware(AuthMiddleware)

# API 限流中间件（滑动窗口，按 IP+路径）
app.add_middleware(
    RateLimitMiddleware,
    max_requests=config.rate_limit_max_requests,
    window_seconds=config.rate_limit_window_seconds,
)

# 注册路由
app.include_router(health.router, tags=["健康检查"])
app.include_router(monitoring.router, prefix="/api", tags=["监控管理"])

# 挂载管理端静态文件
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """管理端首页"""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {
        "service": config.app_name,
        "version": config.app_version,
        "docs": "/docs",
        "management": "/static/index.html",
    }


@app.get("/chat")
async def chat_page():
    """AI 助手独立页面"""
    chat_path = static_dir / "chat.html"
    if chat_path.exists():
        return FileResponse(str(chat_path))
    return {"error": "chat.html not found"}


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": config.app_name, "version": config.app_version}


@app.get("/health/live")
async def health_live():
    """存活检查"""
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    """就绪检查"""
    # 检查数据库连接
    from app.dao import store
    try:
        if store._engine is not None:
            with store.get_session() as session:
                session.execute("SELECT 1")
            db_status = "connected"
        else:
            db_status = "json_mode"
    except Exception as e:
        db_status = f"error: {e}"

    # 检查 Redis 连接（如果配置了）
    redis_status = "not_configured"
    try:
        import redis
        r = redis.Redis(host=config.redis_host, port=config.redis_port, db=config.redis_db)
        r.ping()
        redis_status = "connected"
    except Exception:
        pass

    return {
        "status": "ready",
        "db": db_status,
        "redis": redis_status,
    }


@app.get("/metrics")
async def metrics(request: Request):
    """Prometheus metrics 端点"""
    return await metrics_endpoint(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="info",
    )