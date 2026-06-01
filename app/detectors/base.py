"""检测器基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class DetectionResult:
    """单次检测结果"""
    detector_name: str
    system_id: str
    system_name: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metric_name: str = ""
    current_value: float = 0.0
    threshold_warning: float = 0.0
    threshold_critical: float = 0.0
    severity: str = "normal"  # normal / warning / critical / error
    message: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_anomalous(self) -> bool:
        return self.severity in ("warning", "critical")


class BaseDetector(ABC):
    """检测器抽象基类

    所有检测器继承此类，实现 check() 方法。
    子类只需关心"拿到什么数据"，框架负责"何时调用、如何告警"。
    """

    name: str = "base"
    description: str = "基础检测器"
    metric_name: str = "unknown"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @abstractmethod
    async def check(
        self,
        system_id: str,
        system_name: str,
        endpoint: str,
        thresholds: Dict[str, Any],
        auth: Optional[Dict[str, Any]] = None,
    ) -> DetectionResult:
        """执行一次检测

        Args:
            system_id: 系统ID
            system_name: 系统名称
            endpoint: 目标地址 (URL / host:port / connection_string)
            thresholds: {"warning": 60, "critical": 80}
            auth: 认证信息 {"type": "api_key", "key": "..."}

        Returns:
            DetectionResult: 检测结果（含是否异常、严重程度）
        """
        ...

    def _evaluate(self, value: float, thresholds: Dict[str, Any]) -> tuple[str, str]:
        """根据阈值判断严重程度"""
        critical = thresholds.get("critical")
        warning = thresholds.get("warning")

        if critical is not None and value >= critical:
            return "critical", f"{self.metric_name}: {value} >= 严重阈值 {critical}"
        if warning is not None and value >= warning:
            return "warning", f"{self.metric_name}: {value} >= 警告阈值 {warning}"
        return "normal", f"{self.metric_name}: {value} (正常)"
