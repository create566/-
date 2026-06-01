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
    logger.info("🔑 验证 LLM 连接...")
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
        test_llm = ChatOpenAI(
            model=config.llm_model, api_key=config.llm_api_key,
            base_url=config.llm_api_base, max_tokens=5, streaming=False,
            timeout=30, max_retries=2,
        )
        test_llm.invoke([HumanMessage(content="hi")])
        logger.info("✅ LLM 连接正常")
    except Exception as e:
        logger.error(f"❌ LLM 不可用: {e}")

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

    # ⑥ 启动飞书机器人（@机器人 状态 → 实时回复指标）
    if config.feishu_app_id and config.feishu_app_secret:
        from app.tools.feishu_ws_bot import FeishuBotListener

        async def handle_feishu_status(open_id, text):
            t = text.strip().lower()
            if "状态" in t or "status" in t or "查询" in t:
                return await _get_status_reply()
            return None

        async def _get_status_reply():
            from app.detectors.manager import DetectorManager
            dm = DetectorManager()
            lines = [f"📊 机器状态 {time.strftime('%H:%M:%S')}", ""]
            for s in store.list_systems():
                if s.get("status") != "active":
                    continue
                lines.append(f"【{s['name']}】 健康分:{s.get('health_score', 100)}")
                try:
                    results = await dm.run_checks(s)
                    for r in results:
                        icon = {"critical":"🔴","warning":"🟡","normal":"🟢","error":"⚠️"}.get(r.severity,"⚪")
                        lines.append(f"  {icon} {r.metric_name}: {r.current_value}")
                except Exception as e:
                    lines.append(f"  ⚠️ 检测失败: {e}")
                lines.append("")
            if len(lines) <= 2:
                return "暂无活跃监控系统"
            return "\n".join(lines)

        feishu_bot = FeishuBotListener(handle_feishu_status)
        feishu_bot.start_websocket()
        logger.info("🤖 飞书机器人已启动，@机器人发送「状态」查询")

    # ⑦ 确保检测器已注册
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