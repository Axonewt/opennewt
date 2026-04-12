"""
Perception Module - Soma 感知层
================================

Soma = 身体，感知层
负责主动感知环境、发现问题、触发响应

感知器类型：
- Nociceptor（疼痛感受器）：检测错误、警告、异常
- Proprioceptor（位置感知器）：检测系统状态、工具可用性、配置完整性
- Thermoreceptor（温度感知器）：检测性能趋势、资源使用趋势

架构：
    perception/
    ├── __init__.py          # 模块导出
    ├── nociceptor.py        # 疼痛/问题感知
    ├── proprioceptor.py     # 位置/状态感知
    └── engine.py            # 感知引擎（整合所有感知器）
"""

from .nociceptor import Nociceptor, NociceptorArray, PainSignal, PainLevel
from .proprioceptor import Proprioceptor, ProprioceptorArray, SystemState, ToolStatus
from .engine import SomaPerception, PerceptionResult

__all__ = [
    "Nociceptor",
    "NociceptorArray",
    "PainSignal",
    "PainLevel",
    "Proprioceptor",
    "ProprioceptorArray",
    "SystemState",
    "ToolStatus",
    "SomaPerception",
    "PerceptionResult",
]
