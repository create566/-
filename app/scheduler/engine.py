"""监控调度引擎 — 定时触发系统检测"""

import asyncio
from typing import Dict, Callable, Optional
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger


class MonitorScheduler:
    """管理所有系统的定时检测任务

    使用内存 job store（简单可靠），FastAPI lifespan 中启停。
    """

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._check_fn: Optional[Callable] = None  # 检测回调函数
        self._system_ids: Dict[str, int] = {}       # system_id → interval

    def set_handler(self, check_fn: Callable):
        """设置检测回调: async def check_fn(system_id: str)"""
        self._check_fn = check_fn

    def start(self):
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("MonitorScheduler 已启动")

    def shutdown(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("MonitorScheduler 已关闭")

    def schedule(self, system_id: str, interval_seconds: int = 60):
        """为系统添加定时检测"""
        job_id = f"check_{system_id}"
        self._scheduler.add_job(
            func=self._run_check,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            args=[system_id],
            replace_existing=True,
            max_instances=1,  # 防止堆积
        )
        self._system_ids[system_id] = interval_seconds
        logger.info(f"已调度: {system_id}, 每 {interval_seconds}s 检测一次")

    def unschedule(self, system_id: str):
        """取消系统的定时检测"""
        job_id = f"check_{system_id}"
        try:
            self._scheduler.remove_job(job_id)
            self._system_ids.pop(system_id, None)
            logger.info(f"已取消调度: {system_id}")
        except Exception:
            pass

    def is_scheduled(self, system_id: str) -> bool:
        return system_id in self._system_ids

    def get_scheduled(self) -> list:
        """返回所有已调度的系统"""
        return [{"system_id": sid, "interval_seconds": iv} for sid, iv in self._system_ids.items()]

    async def _run_check(self, system_id: str):
        """包装检测调用，异常不中断调度"""
        if self._check_fn is None:
            logger.warning("检测回调未设置")
            return
        try:
            await self._check_fn(system_id)
        except Exception as e:
            logger.error(f"定时检测失败 [{system_id}]: {e}")


# 全局单例
monitor_scheduler = MonitorScheduler()
