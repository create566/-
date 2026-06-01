"""检测器管理器 — 批量执行检测"""

from typing import List, Dict, Any
from datetime import datetime, timezone
from loguru import logger
from app.detectors.base import DetectionResult
from app.detectors.registry import DetectorRegistry


class DetectorManager:
    """批量运行系统配置的所有检测器"""

    async def run_checks(self, system: Dict[str, Any]) -> List[DetectionResult]:
        """对单个系统执行所有已配置的检测器

        Args:
            system: 系统配置字典:
                {id, name, endpoint, auth, detectors: [{name, thresholds:{warning, critical}}]}

        Returns:
            List[DetectionResult]: 每个检测器一个结果
        """
        results = []
        detectors = system.get("detectors", [])

        for dc in detectors:
            detector_name = dc.get("name", "")
            detector = DetectorRegistry.get_or_create(detector_name)
            if detector is None:
                logger.warning(f"未知检测器: {detector_name}, 跳过")
                continue

            thresholds = dc.get("thresholds", {})
            try:
                result = await detector.check(
                    system_id=system["id"],
                    system_name=system.get("name", ""),
                    endpoint=system.get("endpoint", ""),
                    thresholds=thresholds,
                    auth=system.get("auth"),
                )
                results.append(result)
            except Exception as e:
                logger.error(f"检测器 {detector_name} 执行失败: {e}")
                results.append(DetectionResult(
                    detector_name=detector_name,
                    system_id=system["id"],
                    system_name=system.get("name", ""),
                    severity="error",
                    message=f"检测器异常: {e}",
                ))

        return results
