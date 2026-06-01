"""检测器模块"""
from app.detectors.base import BaseDetector, DetectionResult
from app.detectors.registry import DetectorRegistry, register_detector
from app.detectors.manager import DetectorManager
