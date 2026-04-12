"""
火蜥蜴自愈引擎 - 整合所有组件
===============================

SelfHealingEngine 是 Phase 4 的核心入口。
整合检测、诊断、修复、验证、学习五个阶段形成完整闭环。

自愈闭环：
    检测（感知）→ 诊断（分析）→ 修复（执行）→ 验证（测试）→ 学习（进化）
                        ↑                          ↓
                        └──────── 免疫记忆 ←───────┘

集成点：
- 上游：Soma Nociceptor (perception.nociceptor.PainSignal)
- 通信：OACP 协议 (protocol.oacp)
- 内部：detector → diagnostician → healer → validator → immune
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .detector import ErrorDetector, ErrorReport
from .diagnostician import Diagnostician, DiagnosticResult
from .healer import Healer, HealResult
from .validator import Validator, ValidationResult
from .immune import ImmuneMemory, ImmuneRecord

logger = logging.getLogger(__name__)


@dataclass
class HealingReport:
    """
    自愈报告

    一次完整的自愈流程记录，包含所有阶段的结果。
    """
    session_id: str
    status: str                     # immune, healed, healed_validated, failed, escalated
    started_at: str
    completed_at: str = ""
    error_report: Optional[ErrorReport] = None
    immune_record: Optional[Dict[str, Any]] = None
    diagnostic: Optional[DiagnosticResult] = None
    heal_result: Optional[HealResult] = None
    validation: Optional[ValidationResult] = None
    dry_run: bool = False
    phase: str = "unknown"          # detect, diagnose, heal, validate, learn
    error: str = ""

    @property
    def duration_ms(self) -> int:
        """自愈耗时（毫秒）"""
        try:
            start = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.completed_at.replace("Z", "+00:00"))
            return int((end - start).total_seconds() * 1000)
        except Exception:
            return -1

    @property
    def summary(self) -> str:
        """人类可读的摘要"""
        status_map = {
            "immune": "已免疫 - 直接应用已知修复方案",
            "healed": "已修复 - 修复成功（未验证）",
            "healed_validated": "已修复 - 修复成功且验证通过",
            "failed": "修复失败",
            "escalated": "已升级 - 需要人工介入",
            "skipped": "已跳过 - Dry Run 模式",
        }
        return status_map.get(self.status, self.status)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        result = {
            "session_id": self.session_id,
            "status": self.status,
            "summary": self.summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "dry_run": self.dry_run,
            "phase": self.phase,
        }

        if self.error_report:
            result["error"] = self.error_report.to_dict()

        if self.immune_record:
            result["immune"] = self.immune_record

        if self.diagnostic:
            result["diagnostic"] = {
                "root_cause": self.diagnostic.root_cause,
                "fix_suggestion": self.diagnostic.fix_suggestion,
                "confidence": self.diagnostic.confidence,
                "fix_type": self.diagnostic.fix_type,
                "is_auto_fixable": self.diagnostic.is_auto_fixable,
            }

        if self.heal_result:
            result["heal"] = self.heal_result.to_dict()

        if self.validation:
            result["validation"] = self.validation.to_dict()

        if self.error:
            result["error"] = self.error

        return result


class SelfHealingEngine:
    """
    火蜥蜴自愈引擎

    完整闭环：检测 → 诊断 → 修复 → 验证 → 学习

    使用示例:
        >>> engine = SelfHealingEngine(dry_run=True)
        >>> report = engine.process_exception(some_exception)
        >>> print(report.summary)
    """

    def __init__(
        self,
        dry_run: bool = True,
        project_path: str = "",
        db_path: Optional[str] = None,
        immunity_threshold: int = 3,
    ):
        """
        Args:
            dry_run: 默认 Dry Run 模式（安全第一）
            project_path: 项目根路径
            db_path: 免疫记忆数据库路径
            immunity_threshold: 免疫阈值（成功修复次数）
        """
        self.dry_run = dry_run
        self.project_path = project_path

        # 初始化所有组件
        self.detector = ErrorDetector()
        self.diagnostician = Diagnostician()
        self.healer = Healer(dry_run=dry_run, project_path=project_path)
        self.validator = Validator(project_path=project_path)
        self.immune = ImmuneMemory(
            db_path=db_path,
            immunity_threshold=immunity_threshold,
        )

        # 会话统计
        self._session_counter = 0
        self._history: List[HealingReport] = []

    def process_exception(
        self,
        exc: Exception,
        dry_run: Optional[bool] = None,
    ) -> HealingReport:
        """
        处理 Python 异常的完整自愈流程

        Args:
            exc: Python 异常对象
            dry_run: 覆盖默认 dry_run 设置

        Returns:
            自愈报告
        """
        report = self._create_report()

        try:
            # Phase 1: 检测
            report.phase = "detect"
            error_report = self.detector.detect_from_exception(exc)
            report.error_report = error_report

            return self._process_report(error_report, report, dry_run)

        except Exception as e:
            report.status = "failed"
            report.phase = "detect"
            report.error = f"检测阶段异常: {str(e)}"
            logger.error(f"[SelfHealing] 检测失败: {e}", exc_info=True)

        self._finalize_report(report)
        return report

    def process_pain_signal(
        self,
        signal,
        dry_run: Optional[bool] = None,
    ) -> HealingReport:
        """
        处理 Soma PainSignal 的完整自愈流程

        Args:
            signal: perception.nociceptor.PainSignal
            dry_run: 覆盖默认 dry_run 设置

        Returns:
            自愈报告
        """
        report = self._create_report()

        try:
            # Phase 1: 检测
            report.phase = "detect"
            error_report = self.detector.detect_from_pain_signal(signal)
            report.error_report = error_report

            return self._process_report(error_report, report, dry_run)

        except Exception as e:
            report.status = "failed"
            report.phase = "detect"
            report.error = f"PainSignal 处理异常: {str(e)}"
            logger.error(f"[SelfHealing] PainSignal 处理失败: {e}", exc_info=True)

        self._finalize_report(report)
        return report

    def process_error_report(
        self,
        error_report: ErrorReport,
        dry_run: Optional[bool] = None,
    ) -> HealingReport:
        """
        处理已有的 ErrorReport

        当外部已有 ErrorReport 时直接进入自愈流程。

        Args:
            error_report: 错误报告
            dry_run: 覆盖默认 dry_run 设置

        Returns:
            自愈报告
        """
        report = self._create_report()
        report.error_report = error_report

        try:
            return self._process_report(error_report, report, dry_run)
        except Exception as e:
            report.status = "failed"
            report.error = f"自愈流程异常: {str(e)}"
            logger.error(f"[SelfHealing] 自愈失败: {e}", exc_info=True)

        self._finalize_report(report)
        return report

    def _process_report(
        self,
        error_report: ErrorReport,
        report: HealingReport,
        dry_run: Optional[bool],
    ) -> HealingReport:
        """
        核心自愈流程

        免疫检查 → 诊断 → 修复 → 验证 → 学习
        """
        effective_dry_run = dry_run if dry_run is not None else self.dry_run
        report.dry_run = effective_dry_run

        # Phase 2: 免疫检查
        immune_record = self.immune.get_immunity(error_report)
        if immune_record and immune_record.is_immune:
            report.status = "immune"
            report.phase = "learn"  # 直接跳到学习（已免疫）
            report.immune_record = immune_record.to_dict()

            # 已免疫：仍记录一次成功
            self.immune.learn(
                error_report,
                DiagnosticResult(
                    root_cause=immune_record.root_cause,
                    fix_suggestion=immune_record.fix_pattern,
                    confidence=immune_record.confidence,
                    fix_type=immune_record.fix_type,
                ),
                success=True,
            )

            logger.info(
                f"[SelfHealing] 已免疫: {error_report.error_type.value} - "
                f"{error_report.message[:50]}"
            )
            self._finalize_report(report)
            return report

        # Phase 3: 诊断
        report.phase = "diagnose"
        diagnostic = self.diagnostician.diagnose(error_report)
        report.diagnostic = diagnostic

        if not diagnostic.is_auto_fixable:
            report.status = "escalated"
            report.phase = "diagnose"
            logger.info(
                f"[SelfHealing] 无法自动修复: {diagnostic.root_cause} "
                f"(confidence={diagnostic.confidence})"
            )
            self._finalize_report(report)
            return report

        # Phase 4: 修复
        report.phase = "heal"
        heal_result = self.healer.heal(diagnostic, dry_run=effective_dry_run)
        report.heal_result = heal_result

        if not heal_result.success:
            report.status = "failed"
            report.phase = "heal"
            logger.warning(f"[SelfHealing] 修复失败: {heal_result.message}")
            self._finalize_report(report)
            return report

        # Phase 5: 验证
        report.phase = "validate"
        validation = self.validator.validate(error_report, heal_result)
        report.validation = validation

        if not validation.passed:
            report.status = "healed"  # 修复了但验证未通过
            logger.warning(f"[SelfHealing] 验证未通过: {validation.message}")
        else:
            report.status = "healed_validated"
            logger.info(f"[SelfHealing] 修复成功且验证通过: {diagnostic.root_cause}")

        # Phase 6: 学习
        report.phase = "learn"
        self.immune.learn(error_report, diagnostic, success=heal_result.success)

        self._finalize_report(report)
        return report

    def scan_and_heal(
        self,
        project_path: Optional[str] = None,
        dry_run: Optional[bool] = None,
    ) -> List[HealingReport]:
        """
        扫描项目并自动修复

        集成 Soma Nociceptor 进行项目扫描，
        对发现的每个问题执行自愈流程。

        Args:
            project_path: 项目路径（默认使用引擎初始化时的路径）
            dry_run: 覆盖默认 dry_run 设置

        Returns:
            所有自愈报告列表
        """
        path = project_path or self.project_path
        if not path:
            logger.error("[SelfHealing] 未指定项目路径")
            return []

        reports = []

        try:
            # 尝试集成 Soma Nociceptor
            from src.perception.nociceptor import NociceptorArray

            nociceptors = NociceptorArray()
            signals = nociceptors.scan(path)

            logger.info(
                f"[SelfHealing] 扫描发现 {len(signals)} 个疼痛信号"
            )

            for signal in signals:
                report = self.process_pain_signal(signal, dry_run=dry_run)
                reports.append(report)

        except ImportError:
            logger.warning(
                "[SelfHealing] Soma Nociceptor 不可用，跳过扫描"
            )
        except Exception as e:
            logger.error(f"[SelfHealing] 扫描失败: {e}", exc_info=True)

        return reports

    def get_stats(self) -> Dict[str, Any]:
        """
        获取引擎和免疫记忆统计

        Returns:
            统计信息字典
        """
        immune_stats = self.immune.get_stats()

        return {
            "engine": {
                "dry_run": self.dry_run,
                "project_path": self.project_path,
                "total_sessions": self._session_counter,
                "history_size": len(self._history),
            },
            "immune": immune_stats,
        }

    def _create_report(self) -> HealingReport:
        """创建新的自愈报告"""
        self._session_counter += 1
        return HealingReport(
            session_id=f"HEAL-{self._session_counter:04d}",
            status="pending",
            started_at=datetime.utcnow().isoformat() + "Z",
        )

    def _finalize_report(self, report: HealingReport):
        """完成报告并归档"""
        report.completed_at = datetime.utcnow().isoformat() + "Z"
        self._history.append(report)
        logger.info(
            f"[SelfHealing] Session {report.session_id}: "
            f"{report.status} ({report.phase}) "
            f"[{report.duration_ms}ms]"
        )
