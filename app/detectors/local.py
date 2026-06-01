"""本地检测器 — 开箱即用，不需要外部服务"""

from typing import Dict, Any, Optional
import asyncio
from loguru import logger

from app.detectors.base import BaseDetector, DetectionResult
from app.detectors.registry import register_detector


@register_detector("http_health")
class HTTPHealthDetector(BaseDetector):
    """HTTP健康端点检测 — 检查目标服务 /health 是否返回 2xx"""

    name = "http_health"
    description = "检测 HTTP 服务的 /health 端点，判断服务是否存活"
    metric_name = "http_status"

    async def check(
        self, system_id: str, system_name: str, endpoint: str,
        thresholds: Dict[str, Any], auth: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                url = endpoint.rstrip("/") + "/health"
                resp = await client.get(url)
                ok = 200 <= resp.status_code < 300
                severity, msg = ("normal", f"HTTP {resp.status_code} OK") if ok else ("critical", f"HTTP {resp.status_code} 异常")
                return DetectionResult(
                    detector_name=self.name, system_id=system_id, system_name=system_name,
                    metric_name=self.metric_name, current_value=resp.status_code,
                    threshold_warning=thresholds.get("warning", 200),
                    threshold_critical=thresholds.get("critical", 200),
                    severity=severity, message=msg,
                    raw_data={"status_code": resp.status_code, "url": url},
                )
        except Exception as e:
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=0, severity="critical",
                message=f"HTTP检测失败: {e}",
                raw_data={"error": str(e), "endpoint": endpoint},
            )


@register_detector("local_cpu")
class LocalCPUDetector(BaseDetector):
    """本机CPU使用率检测 — 使用 psutil"""

    name = "local_cpu"
    description = "检测本机 CPU 使用率 %（psutil）"
    metric_name = "cpu_usage_percent"

    async def check(
        self, system_id: str, system_name: str, endpoint: str,
        thresholds: Dict[str, Any], auth: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        try:
            import psutil
            value = round(psutil.cpu_percent(interval=1), 1)
            severity, msg = self._evaluate(value, thresholds)
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=value,
                threshold_warning=thresholds.get("warning", 60),
                threshold_critical=thresholds.get("critical", 80),
                severity=severity, message=msg,
                raw_data={"cpu_percent": value, "cpu_count": psutil.cpu_count()},
            )
        except Exception as e:
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=0, severity="error",
                message=f"CPU检测失败: {e}",
            )


@register_detector("local_memory")
class LocalMemoryDetector(BaseDetector):
    """本机内存使用率检测 — 使用 psutil"""

    name = "local_memory"
    description = "检测本机内存使用率 %（psutil）"
    metric_name = "memory_usage_percent"

    async def check(
        self, system_id: str, system_name: str, endpoint: str,
        thresholds: Dict[str, Any], auth: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        try:
            import psutil
            mem = psutil.virtual_memory()
            value = round(mem.percent, 1)
            severity, msg = self._evaluate(value, thresholds)
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=value,
                threshold_warning=thresholds.get("warning", 70),
                threshold_critical=thresholds.get("critical", 85),
                severity=severity, message=msg,
                raw_data={
                    "percent": value, "total_gb": round(mem.total / (1024**3), 1),
                    "available_gb": round(mem.available / (1024**3), 1),
                },
            )
        except Exception as e:
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=0, severity="error",
                message=f"内存检测失败: {e}",
            )


@register_detector("local_disk")
class LocalDiskDetector(BaseDetector):
    """本机磁盘使用率检测 — 使用 shutil"""

    name = "local_disk"
    description = "检测本机磁盘使用率 %（shutil）"
    metric_name = "disk_usage_percent"

    async def check(
        self, system_id: str, system_name: str, endpoint: str,
        thresholds: Dict[str, Any], auth: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        try:
            import shutil
            # 智能判断路径：endpoint 为空或 "localhost" 时用当前工作目录的根路径
            path = endpoint.strip() if endpoint and endpoint.strip() not in ("localhost", "127.0.0.1") else "C:\\"
            if not path or path == ".":
                path = "C:\\"
            usage = await asyncio.to_thread(shutil.disk_usage, path)
            value = round(usage.used / usage.total * 100, 1)
            severity, msg = self._evaluate(value, thresholds)
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=value,
                threshold_warning=thresholds.get("warning", 75),
                threshold_critical=thresholds.get("critical", 90),
                severity=severity, message=msg,
                raw_data={
                    "percent": value, "total_gb": round(usage.total / (1024**3), 1),
                    "used_gb": round(usage.used / (1024**3), 1), "path": path,
                },
            )
        except Exception as e:
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=0, severity="error",
                message=f"磁盘检测失败: {e}",
            )
