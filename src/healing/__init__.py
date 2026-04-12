"""
火蜥蜴自愈引擎 (Salamander Self-Healing Engine)
================================================

Phase 4 核心模块 - 主动自愈闭环

自愈闭环流程：
    检测（感知）→ 诊断（分析）→ 修复（执行）→ 验证（测试）→ 学习（进化）
                        ↑                          ↓
                        └──────── 免疫记忆 ←───────┘

差异化优势：
    Hermes Agent 只有 Skill 自进化（被动学习）
    Axonewt 有主动自愈（检测 → 修复 → 学习 → 免疫）

集成点：
    - 上游：Soma 感知层 (perception.nociceptor.PainSignal)
    - 通信：OACP 协议 (protocol.oacp)
    - 下游：免疫记忆 (healing.immune.ImmuneMemory)
"""

from .detector import ErrorType, ErrorReport, ErrorDetector
from .diagnostician import DiagnosticResult, Diagnostician
from .healer import HealAction, HealResult, Healer
from .validator import ValidationResult, Validator
from .immune import ImmuneMemory, ImmuneRecord
from .engine import SelfHealingEngine, HealingReport

__all__ = [
    # 检测
    "ErrorType",
    "ErrorReport",
    "ErrorDetector",
    # 诊断
    "DiagnosticResult",
    "Diagnostician",
    # 修复
    "HealAction",
    "HealResult",
    "Healer",
    # 验证
    "ValidationResult",
    "Validator",
    # 免疫
    "ImmuneMemory",
    "ImmuneRecord",
    # 主引擎
    "SelfHealingEngine",
    "HealingReport",
]
