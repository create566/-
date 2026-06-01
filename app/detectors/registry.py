"""检测器注册中心"""

from typing import Dict, Type, Optional
from loguru import logger
from app.detectors.base import BaseDetector


class DetectorRegistry:
    """全局检测器注册中心"""

    _detectors: Dict[str, Type[BaseDetector]] = {}
    _instances: Dict[str, BaseDetector] = {}

    @classmethod
    def register(cls, name: str, detector_cls: Type[BaseDetector]):
        cls._detectors[name] = detector_cls
        logger.debug(f"注册检测器: {name}")

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseDetector]]:
        return cls._detectors.get(name)

    @classmethod
    def get_or_create(cls, name: str, config: Optional[Dict] = None) -> Optional[BaseDetector]:
        """获取或创建检测器实例"""
        cache_key = f"{name}_{hash(str(config))}"
        if cache_key in cls._instances:
            return cls._instances[cache_key]
        detector_cls = cls._detectors.get(name)
        if detector_cls is None:
            return None
        instance = detector_cls(config)
        cls._instances[cache_key] = instance
        return instance

    @classmethod
    def list_all(cls) -> Dict[str, str]:
        return {name: cls.description for name, cls in cls._detectors.items()}

    @classmethod
    def list_details(cls) -> list:
        return [{
            "name": name,
            "description": cls.description,
            "metric_name": cls.metric_name,
        } for name, cls in cls._detectors.items()]


def register_detector(name: str):
    """装饰器：注册检测器"""
    def wrapper(cls):
        DetectorRegistry.register(name, cls)
        return cls
    return wrapper
