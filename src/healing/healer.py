"""
修复执行器 - 执行自动修复
==========================

支持 Dry Run 模式：
- Dry Run = True：模拟修复，不修改任何文件或系统状态
- Dry Run = False：实际执行修复

修复动作类型：
- auto_restart: 重启服务
- auto_install: 安装依赖
- auto_config: 修改配置
- auto_patch: 修复代码
- manual: 需要人工介入
"""

import logging
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .diagnostician import DiagnosticResult

logger = logging.getLogger(__name__)


class HealActionType(Enum):
    """修复动作类型"""
    RESTART_SERVICE = "restart_service"
    INSTALL_PACKAGE = "install_package"
    UPDATE_CONFIG = "update_config"
    PATCH_CODE = "patch_code"
    CLEAN_CACHE = "clean_cache"
    ROLLBACK = "rollback"
    ESCALATE = "escalate"          # 升级为人工处理
    NOOP = "noop"                  # 无需修复


@dataclass
class HealAction:
    """
    修复动作

    描述一个具体的修复步骤。
    """
    action_type: HealActionType
    description: str
    command: Optional[str] = None
    target_files: List[str] = field(default_factory=list)
    rollback_command: Optional[str] = None
    estimated_duration: str = "< 1s"
    risk_level: str = "low"         # low, medium, high

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "description": self.description,
            "command": self.command,
            "target_files": self.target_files,
            "rollback_command": self.rollback_command,
            "estimated_duration": self.estimated_duration,
            "risk_level": self.risk_level,
        }


@dataclass
class HealResult:
    """
    修复结果

    包含修复是否成功、执行的动作和详细信息。
    """
    success: bool
    action: str
    message: str
    dry_run: bool = False
    actions_taken: List[HealAction] = field(default_factory=list)
    error_logs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        if self.dry_run:
            return "dry_run" if self.success else "dry_run_failed"
        return "healed" if self.success else "failed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "action": self.action,
            "message": self.message,
            "dry_run": self.dry_run,
            "actions_taken": [a.to_dict() for a in self.actions_taken],
            "error_logs": self.error_logs,
        }


class Healer:
    """
    修复执行器

    根据 DiagnosticResult 生成并执行修复动作。
    默认 Dry Run 模式确保安全。
    """

    def __init__(self, dry_run: bool = True, project_path: str = ""):
        """
        Args:
            dry_run: 是否为 Dry Run 模式（默认 True）
            project_path: 项目根路径（用于定位配置文件等）
        """
        self.dry_run = dry_run
        self.project_path = project_path
        self._action_history: List[HealAction] = []
        self._max_actions_per_heal = 5

    def heal(
        self,
        diagnostic: DiagnosticResult,
        dry_run: Optional[bool] = None,
    ) -> HealResult:
        """
        执行修复

        Args:
            diagnostic: 诊断结果
            dry_run: 覆盖默认的 dry_run 设置

        Returns:
            修复结果
        """
        if dry_run is None:
            dry_run = self.dry_run

        if not diagnostic.is_auto_fixable:
            return HealResult(
                success=False,
                action="escalate",
                message=f"需要人工介入: {diagnostic.root_cause}",
                dry_run=dry_run,
            )

        # 根据诊断结果生成修复动作列表
        actions = self._plan_actions(diagnostic)

        if not actions:
            return HealResult(
                success=False,
                action="none",
                message="无法生成修复动作",
                dry_run=dry_run,
            )

        # 限制动作数量
        actions = actions[: self._max_actions_per_heal]

        # 执行动作
        if dry_run:
            return self._dry_run_heal(actions, diagnostic)
        else:
            return self._apply_heal(actions, diagnostic)

    def _plan_actions(self, diagnostic: DiagnosticResult) -> List[HealAction]:
        """
        根据诊断结果规划修复动作

        Args:
            diagnostic: 诊断结果

        Returns:
            修复动作列表
        """
        actions = []
        suggestion = diagnostic.fix_suggestion.lower()

        if diagnostic.fix_type == "auto_restart":
            actions.append(HealAction(
                action_type=HealActionType.RESTART_SERVICE,
                description=diagnostic.fix_suggestion,
                rollback_command="无需回滚（重启操作）",
                risk_level="low",
            ))

        elif diagnostic.fix_type == "auto_install":
            # 提取包名
            package = self._extract_package_name(diagnostic.fix_suggestion)
            if package:
                actions.append(HealAction(
                    action_type=HealActionType.INSTALL_PACKAGE,
                    description=f"安装缺失包: {package}",
                    command=f"{sys.executable} -m pip install {package}",
                    rollback_command=f"{sys.executable} -m pip uninstall {package} -y",
                    risk_level="medium",
                ))

        elif diagnostic.fix_type == "auto_config":
            actions.append(HealAction(
                action_type=HealActionType.UPDATE_CONFIG,
                description=diagnostic.fix_suggestion,
                target_files=diagnostic.affected_files or [],
                risk_level="medium",
            ))

        elif diagnostic.fix_type == "auto_patch":
            actions.append(HealAction(
                action_type=HealActionType.PATCH_CODE,
                description=diagnostic.fix_suggestion,
                target_files=diagnostic.affected_files or [],
                risk_level="medium",
            ))

        # 如果动作为空但有建议，生成通用动作
        if not actions and diagnostic.fix_suggestion:
            actions.append(HealAction(
                action_type=HealActionType.NOOP,
                description=diagnostic.fix_suggestion,
                risk_level="low",
            ))

        return actions

    def _dry_run_heal(
        self,
        actions: List[HealAction],
        diagnostic: DiagnosticResult,
    ) -> HealResult:
        """
        Dry Run 模式 - 模拟修复

        不修改任何文件或系统状态，仅记录将要执行的动作。
        """
        descriptions = [f"[DRY RUN] {a.description}" for a in actions]

        return HealResult(
            success=True,
            action="; ".join(descriptions),
            message=f"Dry Run: 将执行 {len(actions)} 个修复动作:\n"
                    + "\n".join(f"  - {a.description}" for a in actions),
            dry_run=True,
            actions_taken=actions,
            metadata={
                "total_actions": len(actions),
                "diagnostic_confidence": diagnostic.confidence,
            },
        )

    def _apply_heal(
        self,
        actions: List[HealAction],
        diagnostic: DiagnosticResult,
    ) -> HealResult:
        """
        实际执行修复

        逐个执行修复动作，遇到失败立即停止。
        """
        executed = []
        errors = []

        for action in actions:
            try:
                success, msg = self._execute_action(action)
                executed.append(action)

                if not success:
                    errors.append(f"动作 {action.action_type.value} 失败: {msg}")
                    # 执行失败，尝试回滚已执行的动作
                    self._rollback(executed[:-1])
                    return HealResult(
                        success=False,
                        action=action.action_type.value,
                        message=f"修复失败: {msg}，已回滚",
                        actions_taken=executed,
                        error_logs=errors,
                    )

            except Exception as e:
                errors.append(f"执行异常: {str(e)}")
                self._rollback(executed)
                return HealResult(
                    success=False,
                    action="exception",
                    message=f"执行异常: {str(e)}",
                    actions_taken=executed,
                    error_logs=errors,
                )

        self._action_history.extend(executed)

        return HealResult(
            success=True,
            action="; ".join(a.description for a in executed),
            message=f"成功执行 {len(executed)} 个修复动作:\n"
                    + "\n".join(f"  - {a.description}" for a in executed),
            actions_taken=executed,
            metadata={
                "total_actions": len(executed),
                "diagnostic_confidence": diagnostic.confidence,
            },
        )

    def _execute_action(self, action: HealAction) -> tuple:
        """
        执行单个修复动作

        Returns:
            (success, message)
        """
        if action.action_type == HealActionType.NOOP:
            return True, "无需执行"

        elif action.action_type == HealActionType.INSTALL_PACKAGE:
            if action.command:
                return self._run_command(action.command, timeout=120)

        elif action.action_type == HealActionType.RESTART_SERVICE:
            # 重启服务需要知道具体的服务名
            logger.info(f"[Healer] 建议重启服务: {action.description}")
            return True, f"服务重启建议: {action.description}"

        elif action.action_type == HealActionType.UPDATE_CONFIG:
            logger.info(f"[Healer] 配置更新建议: {action.description}")
            return True, f"配置更新建议: {action.description}"

        elif action.action_type == HealActionType.PATCH_CODE:
            logger.info(f"[Healer] 代码补丁建议: {action.description}")
            return True, f"代码补丁建议: {action.description}"

        elif action.action_type == HealActionType.CLEAN_CACHE:
            if action.command:
                return self._run_command(action.command, timeout=30)
            return True, "缓存清理完成"

        return False, "未知动作类型"

    def _run_command(self, command: str, timeout: int = 60) -> tuple:
        """
        执行 shell 命令

        Returns:
            (success, message)
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0:
                return True, result.stdout.strip() or "命令执行成功"
            else:
                return False, result.stderr.strip() or f"命令返回码: {result.returncode}"

        except subprocess.TimeoutExpired:
            return False, f"命令执行超时（{timeout}s）"
        except Exception as e:
            return False, str(e)

    def _rollback(self, actions: List[HealAction]):
        """
        回滚已执行的动作

        按逆序执行回滚命令。
        """
        for action in reversed(actions):
            if action.rollback_command:
                success, msg = self._run_command(action.rollback_command, timeout=60)
                if not success:
                    logger.warning(f"[Healer] 回滚失败: {msg}")
                else:
                    logger.info(f"[Healer] 回滚成功: {action.description}")

    def _extract_package_name(self, suggestion: str) -> Optional[str]:
        """
        从修复建议中提取包名

        Args:
            suggestion: 修复建议文本

        Returns:
            包名（如果能提取），否则 None
        """
        # 匹配 "pip install <package>" 模式
        match = __import__("re").search(
            r"pip\s+install\s+([a-zA-Z0-9_.-]+)",
            suggestion,
        )
        if match:
            return match.group(1)

        # 匹配 "No module named '<package>'" 模式
        match = __import__("re").search(
            r"No module named '(.+)'",
            suggestion,
        )
        if match:
            return match.group(1)

        return None
