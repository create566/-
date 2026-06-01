"""远程检测器 — 连接外部服务（Prometheus / MySQL / Redis）"""

from typing import Dict, Any, Optional
import asyncio
from loguru import logger

from app.detectors.base import BaseDetector, DetectionResult
from app.detectors.registry import register_detector


@register_detector("prometheus_cpu")
class PrometheusCPUDetector(BaseDetector):
    """Prometheus CPU使用率检测"""

    name = "prometheus_cpu"
    description = "通过 Prometheus 查询目标服务器 CPU 使用率 %"
    metric_name = "cpu_usage_percent"

    async def check(
        self, system_id: str, system_name: str, endpoint: str,
        thresholds: Dict[str, Any], auth: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        try:
            import httpx
            # endpoint = Prometheus 地址，如 http://10.0.1.100:9090
            promql = self.config.get("query") or '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
            url = endpoint.rstrip("/") + "/api/v1/query"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params={"query": promql})
                data = resp.json()
                if data.get("status") == "success" and data["data"]["result"]:
                    value = round(float(data["data"]["result"][0]["value"][1]), 1)
                else:
                    return DetectionResult(
                        detector_name=self.name, system_id=system_id, system_name=system_name,
                        metric_name=self.metric_name, current_value=0, severity="error",
                        message=f"Prometheus 无数据: {data}",
                    )
            severity, msg = self._evaluate(value, thresholds)
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=value,
                threshold_warning=thresholds.get("warning", 60),
                threshold_critical=thresholds.get("critical", 80),
                severity=severity, message=msg,
                raw_data={"cpu_percent": value, "promql": promql, "prometheus": endpoint},
            )
        except Exception as e:
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=0, severity="error",
                message=f"Prometheus查询失败: {e}",
            )


@register_detector("prometheus_memory")
class PrometheusMemoryDetector(BaseDetector):
    """Prometheus 内存使用率检测"""

    name = "prometheus_memory"
    description = "通过 Prometheus 查询目标服务器内存使用率 %"
    metric_name = "memory_usage_percent"

    async def check(
        self, system_id: str, system_name: str, endpoint: str,
        thresholds: Dict[str, Any], auth: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        try:
            import httpx
            promql = (
                self.config.get("query")
                or '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100'
            )
            url = endpoint.rstrip("/") + "/api/v1/query"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params={"query": promql})
                data = resp.json()
                if data.get("status") == "success" and data["data"]["result"]:
                    value = round(float(data["data"]["result"][0]["value"][1]), 1)
                else:
                    return DetectionResult(
                        detector_name=self.name, system_id=system_id, system_name=system_name,
                        metric_name=self.metric_name, current_value=0, severity="error",
                        message=f"Prometheus 无数据: {data}",
                    )
            severity, msg = self._evaluate(value, thresholds)
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=value,
                threshold_warning=thresholds.get("warning", 70),
                threshold_critical=thresholds.get("critical", 85),
                severity=severity, message=msg,
                raw_data={"memory_percent": value, "promql": promql, "prometheus": endpoint},
            )
        except Exception as e:
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=0, severity="error",
                message=f"Prometheus查询失败: {e}",
            )


@register_detector("mysql_slow_queries")
class MySQLSlowQueryDetector(BaseDetector):
    """MySQL 慢查询数量检测"""

    name = "mysql_slow_queries"
    description = "连接 MySQL 查询慢查询数量"
    metric_name = "slow_queries_count"

    async def check(
        self, system_id: str, system_name: str, endpoint: str,
        thresholds: Dict[str, Any], auth: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        try:
            import pymysql

            def _query():
                host = endpoint or "localhost"
                port = 3306
                if ":" in host:
                    parts = host.rsplit(":", 1)
                    host, port = parts[0], int(parts[1])

                conn = pymysql.connect(
                    host=host, port=port,
                    user=auth.get("user", "root") if auth else "root",
                    password=auth.get("password", "") if auth else "",
                    database=auth.get("database", "mysql") if auth else "mysql",
                    connect_timeout=5,
                )
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SHOW GLOBAL STATUS LIKE 'Slow_queries'")
                        row = cursor.fetchone()
                        return int(row[1]) if row else 0
                finally:
                    conn.close()

            value = await asyncio.to_thread(_query)
            severity, msg = self._evaluate(value, thresholds)
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=value,
                threshold_warning=thresholds.get("warning", 10),
                threshold_critical=thresholds.get("critical", 50),
                severity=severity, message=msg,
                raw_data={"slow_queries": value},
            )
        except Exception as e:
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=0, severity="error",
                message=f"MySQL查询失败: {e}",
            )


@register_detector("redis_memory")
class RedisMemoryDetector(BaseDetector):
    """Redis 内存使用率检测"""

    name = "redis_memory"
    description = "连接 Redis 查询内存使用率和连接数"
    metric_name = "redis_memory_percent"

    async def check(
        self, system_id: str, system_name: str, endpoint: str,
        thresholds: Dict[str, Any], auth: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        try:
            import redis

            def _query():
                host = endpoint or "localhost"
                port = 6379
                if ":" in host:
                    parts = host.rsplit(":", 1)
                    host, port = parts[0], int(parts[1])

                password = auth.get("password") if auth else None
                db = int(auth.get("db", 0)) if auth else 0

                r = redis.Redis(host=host, port=port, password=password, db=db,
                                socket_connect_timeout=5, decode_responses=True)
                try:
                    info = r.info("memory")
                    used_memory = info.get("used_memory_rss", 0)
                    maxmemory = info.get("maxmemory", 0)
                    if maxmemory > 0:
                        percent = round(used_memory / maxmemory * 100, 1)
                    else:
                        # 没有设置 maxmemory，使用系统内存估算
                        import psutil
                        total_mem = psutil.virtual_memory().total
                        percent = round(used_memory / total_mem * 100, 1)

                    # 也查一下连接数
                    clients_info = r.info("clients")
                    connected_clients = clients_info.get("connected_clients", 0)

                    return percent, connected_clients, used_memory, maxmemory
                finally:
                    r.close()

            percent, clients, used_mem, max_mem = await asyncio.to_thread(_query)
            severity, msg = self._evaluate(percent, thresholds)

            # 连接数也加入判断
            if severity != "critical" and clients > 1000:
                severity = "warning"
                msg += f" | 连接数偏高: {clients}"

            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=percent,
                threshold_warning=thresholds.get("warning", 70),
                threshold_critical=thresholds.get("critical", 85),
                severity=severity, message=msg,
                raw_data={
                    "memory_percent": percent, "connected_clients": clients,
                    "used_memory_mb": round(used_mem / (1024**2), 1),
                    "maxmemory_mb": round(max_mem / (1024**2), 1) if max_mem > 0 else "无限制",
                },
            )
        except Exception as e:
            return DetectionResult(
                detector_name=self.name, system_id=system_id, system_name=system_name,
                metric_name=self.metric_name, current_value=0, severity="error",
                message=f"Redis查询失败: {e}",
            )
