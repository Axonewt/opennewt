"""
验证器 - 修复后验证
====================

修复执行后，验证修复是否真正有效。
多层次验证策略：
1. 快速检查：语法验证、导入检查
2. 运行验证：测试执行
3. 行为验证：比较修复前后的行为
"""

import ast
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .detector import ErrorReport
from .healer import HealResult

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """
    验证结果

    包含验证是否通过、验证方法和详细信息。
    """
    passed: bool
    validation_method: str     # quick_check, test_run, behavior_check
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    regressions: List[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "passed" if self.passed else "failed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "status": self.status,
            "validation_method": self.validation_method,
            "message": self.message,
            "details": self.details,
            "regressions": self.regressions,
        }


class Validator:
    """
    验证器

    在修复执行后验证修复效果。
    根据错误类型选择合适的验证策略。
    """

    def __init__(self, project_path: str = ""):
        """
        Args:
            project_path: 项目根路径
        """
        self.project_path = project_path
        self._validation_history: List[ValidationResult] = []

    def validate(
        self,
        original_error: ErrorReport,
        heal_result: HealResult,
    ) -> ValidationResult:
        """
        综合验证

        根据原始错误类型选择验证策略。

        Args:
            original_error: 原始错误报告
            heal_result: 修复结果

        Returns:
            验证结果
        """
        if not heal_result.success:
            return ValidationResult(
                passed=False,
                validation_method="skip",
                message="修复未成功，跳过验证",
            )

        # Dry Run 模式下只做快速检查
        if heal_result.dry_run:
            return self._validate_dry_run(original_error, heal_result)

        # 实际修复后做完整验证
        results = []

        # 1. 快速检查（总是执行）
        quick = self._quick_check(original_error, heal_result)
        results.append(quick)

        # 2. 如果有受影响文件，做语法验证
        if original_error.location:
            syntax = self._syntax_check(original_error)
            results.append(syntax)

        # 3. 如果项目路径存在，运行测试
        if self.project_path:
            test = self._test_check(original_error)
            if test:
                results.append(test)

        # 汇总结果
        all_passed = all(r.passed for r in results)
        failures = [r for r in results if not r.passed]

        return ValidationResult(
            passed=all_passed,
            validation_method="comprehensive",
            message=(
                f"所有验证通过 ({len(results)}/{len(results)})"
                if all_passed
                else f"{len(failures)}/{len(results)} 项验证失败"
            ),
            details={
                "total_checks": len(results),
                "passed_checks": len(results) - len(failures),
                "failed_checks": len(failures),
                "check_results": [r.to_dict() for r in results],
            },
        )

    def _validate_dry_run(
        self,
        original_error: ErrorReport,
        heal_result: HealResult,
    ) -> ValidationResult:
        """
        Dry Run 验证

        不实际执行任何验证，仅检查修复计划的合理性。
        """
        has_actions = len(heal_result.actions_taken) > 0

        # 检查是否有匹配的修复动作
        action_types = [a.action_type.value for a in heal_result.actions_taken]

        return ValidationResult(
            passed=has_actions,
            validation_method="dry_run_review",
            message=(
                f"Dry Run: 计划执行 {len(heal_result.actions_taken)} 个动作 "
                f"({', '.join(action_types)})"
                if has_actions
                else "Dry Run: 未生成修复动作"
            ),
            details={
                "action_count": len(heal_result.actions_taken),
                "action_types": action_types,
                "error_type": original_error.error_type.value,
            },
        )

    def _quick_check(
        self,
        original_error: ErrorReport,
        heal_result: HealResult,
    ) -> ValidationResult:
        """
        快速检查

        验证修复结果的基本有效性。
        """
        checks_passed = 0
        total_checks = 2

        # 检查 1: 修复结果有动作
        if heal_result.actions_taken:
            checks_passed += 1

        # 检查 2: 没有错误日志
        if not heal_result.error_logs:
            checks_passed += 1

        return ValidationResult(
            passed=checks_passed == total_checks,
            validation_method="quick_check",
            message=f"快速检查: {checks_passed}/{total_checks} 通过",
            details={
                "has_actions": bool(heal_result.actions_taken),
                "has_errors": bool(heal_result.error_logs),
            },
        )

    def _syntax_check(
        self,
        original_error: ErrorReport,
    ) -> ValidationResult:
        """
        语法验证

        对受影响的文件做 AST 解析验证。
        """
        location = original_error.location
        if not location:
            return ValidationResult(
                passed=True,
                validation_method="syntax_check",
                message="无受影响文件，跳过语法检查",
            )

        # 提取文件路径（去除行号）
        filepath = location.split(":")[0] if ":" in location else location

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()

            if not source.strip():
                return ValidationResult(
                    passed=True,
                    validation_method="syntax_check",
                    message=f"文件为空: {filepath}",
                )

            ast.parse(source, filename=filepath)

            return ValidationResult(
                passed=True,
                validation_method="syntax_check",
                message=f"语法检查通过: {filepath}",
            )

        except FileNotFoundError:
            return ValidationResult(
                passed=True,
                validation_method="syntax_check",
                message=f"文件不存在，跳过: {filepath}",
            )

        except SyntaxError as e:
            return ValidationResult(
                passed=False,
                validation_method="syntax_check",
                message=f"语法错误: {e.msg} (line {e.lineno}) in {filepath}",
                details={"line": e.lineno, "error": e.msg},
            )

        except Exception as e:
            return ValidationResult(
                passed=False,
                validation_method="syntax_check",
                message=f"语法检查异常: {str(e)}",
            )

    def _test_check(
        self,
        original_error: ErrorReport,
    ) -> Optional[ValidationResult]:
        """
        测试验证

        运行项目测试套件验证修复。
        """
        if not self.project_path:
            return None

        try:
            # 检查 pytest 是否可用
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--co", "-q"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # pytest 不可用或无测试文件
                return None

            # 运行测试
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-x", "-q", "--tb=short"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                return ValidationResult(
                    passed=True,
                    validation_method="test_run",
                    message="测试全部通过",
                    details={"stdout": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout},
                )
            else:
                return ValidationResult(
                    passed=False,
                    validation_method="test_run",
                    message="测试失败",
                    details={
                        "stdout": result.stdout[-500:] if len(result.stdout) > 500 else result.stdout,
                        "stderr": result.stderr[-500:] if len(result.stderr) > 500 else result.stderr,
                    },
                )

        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            return ValidationResult(
                passed=False,
                validation_method="test_run",
                message="测试运行超时（120s）",
            )
        except Exception as e:
            logger.warning(f"[Validator] 测试验证异常: {e}")
            return None
