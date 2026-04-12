"""
错误检测器 - 主动发现问题的 Nocireceptor
==========================================

集成 Soma 感知层，将 PainSignal 转换为可处理的 ErrorReport。
同时支持直接从异常和控制台日志检测错误。

双向集成：
    PainSignal (perception) → ErrorReport (healing)
    Exception / Log         → ErrorReport (healing)
"""

import asyncio
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ErrorType(Enum):
    """错误类型分类"""
    SYNTAX = "syntax"           # 语法错误
    RUNTIME = "runtime"         # 运行时错误
    API = "api"                 # API 调用失败
    TIMEOUT = "timeout"         # 超时
    RESOURCE = "resource"       # 资源不足
    DEPENDENCY = "dependency"   # 依赖问题
    CONFIG = "config"           # 配置错误
    IMPORT = "import"           # 导入错误
    TYPE = "type"               # 类型错误
    VALUE = "value"             # 值错误
    PERMISSION = "permission"   # 权限错误
    UNKNOWN = "unknown"         # 未知错误


# 异常类型 → 错误类型映射
_EXCEPTION_TYPE_MAP = {
    SyntaxError: ErrorType.SYNTAX,
    IndentationError: ErrorType.SYNTAX,
    TabError: ErrorType.SYNTAX,
    TimeoutError: ErrorType.TIMEOUT,
    asyncio.TimeoutError: ErrorType.TIMEOUT,
    ConnectionError: ErrorType.API,
    ConnectionRefusedError: ErrorType.API,
    ConnectionResetError: ErrorType.API,
    ConnectionAbortedError: ErrorType.API,
    MemoryError: ErrorType.RESOURCE,
    OSError: ErrorType.RESOURCE,
    FileNotFoundError: ErrorType.RESOURCE,
    PermissionError: ErrorType.PERMISSION,
    ModuleNotFoundError: ErrorType.IMPORT,
    ImportError: ErrorType.IMPORT,
    TypeError: ErrorType.TYPE,
    ValueError: ErrorType.VALUE,
    AttributeError: ErrorType.RUNTIME,
    NameError: ErrorType.RUNTIME,
    KeyError: ErrorType.RUNTIME,
    IndexError: ErrorType.RUNTIME,
    ZeroDivisionError: ErrorType.RUNTIME,
    NotImplementedError: ErrorType.RUNTIME,
    RecursionError: ErrorType.RESOURCE,
}


# 日志错误模式
_LOG_ERROR_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r"\bError\b.*(?:occurred|raised|failed)", re.IGNORECASE),
    re.compile(r"\bException\b:", re.IGNORECASE),
    re.compile(r"\bFATAL\b", re.IGNORECASE),
    re.compile(r"\bCRITICAL\b", re.IGNORECASE),
]

_LOG_WARNING_PATTERNS = [
    re.compile(r"\bWARNING\b", re.IGNORECASE),
    re.compile(r"\bDeprecationWarning\b"),
    re.compile(r"\bResourceWarning\b"),
    re.compile(r"\bUserWarning\b"),
]


@dataclass
class ErrorReport:
    """
    错误报告

    检测器输出的标准化错误描述，供下游诊断引擎消费。
    可从 Exception、PainSignal、控制台日志生成。
    """
    error_type: ErrorType
    message: str
    stack_trace: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    location: str = ""
    error_class: str = ""
    immune_memory_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_critical(self) -> bool:
        """是否为严重错误（需要立即处理）"""
        return self.error_type in (
            ErrorType.SYNTAX,
            ErrorType.RESOURCE,
            ErrorType.PERMISSION,
        )

    @property
    def is_recoverable(self) -> bool:
        """是否可自动修复"""
        return self.error_type not in (
            ErrorType.PERMISSION,
            ErrorType.UNKNOWN,
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "stack_trace": self.stack_trace,
            "timestamp": self.timestamp,
            "location": self.location,
            "error_class": self.error_class,
            "immune_memory_id": self.immune_memory_id,
            "metadata": self.metadata,
        }

    def get_signature(self) -> str:
        """
        生成错误签名

        用于免疫记忆匹配。签名 = 错误类型:错误类:消息前100字符
        """
        msg_key = self.message.replace(" ", "")[:100].lower()
        return f"{self.error_type.value}:{self.error_class}:{msg_key}"


class ErrorDetector:
    """
    错误检测器

    三种检测入口：
    1. detect_from_exception(exc) - 从 Python 异常检测
    2. detect_from_pain_signal(signal) - 从 Soma PainSignal 转换
    3. detect_from_console(log_line) - 从控制台日志检测
    """

    def __init__(self):
        self._report_counter = 0

    def detect_from_exception(self, exc: Exception) -> ErrorReport:
        """
        从异常中检测错误类型

        Args:
            exc: Python 异常对象

        Returns:
            标准化的 ErrorReport
        """
        exc_type = type(exc)
        error_type = _EXCEPTION_TYPE_MAP.get(exc_type, ErrorType.RUNTIME)

        # 对于某些 RuntimeError 子类，尝试从消息进一步分类
        if error_type == ErrorType.RUNTIME:
            msg_lower = str(exc).lower()
            if "connection" in msg_lower or "network" in msg_lower:
                error_type = ErrorType.API
            elif "timeout" in msg_lower:
                error_type = ErrorType.TIMEOUT
            elif "config" in msg_lower or "setting" in msg_lower:
                error_type = ErrorType.CONFIG
            elif "module" in msg_lower or "import" in msg_lower:
                error_type = ErrorType.IMPORT

        trace = traceback.format_exc()

        # 尝试从 traceback 提取文件位置
        location = self._extract_location_from_trace(trace)

        self._report_counter += 1

        return ErrorReport(
            error_type=error_type,
            message=str(exc),
            stack_trace=trace,
            location=location,
            error_class=exc_type.__name__,
            metadata={
                "source": "exception",
                "report_id": f"DET-{self._report_counter:04d}",
            },
        )

    def detect_from_pain_signal(self, signal) -> ErrorReport:
        """
        从 Soma PainSignal 转换为 ErrorReport

        Args:
            signal: perception.nociceptor.PainSignal

        Returns:
            标准化的 ErrorReport
        """
        # PainSignal.pain_type → ErrorType 映射
        pain_to_error = {
            "syntax_error": ErrorType.SYNTAX,
            "runtime_error": ErrorType.RUNTIME,
            "api_failure": ErrorType.API,
            "warning": ErrorType.UNKNOWN,
            "performance": ErrorType.RESOURCE,
            "behavior_drift": ErrorType.RUNTIME,
            "code_decay": ErrorType.RUNTIME,
            "dependency_vulnerability": ErrorType.DEPENDENCY,
            "resource_leak": ErrorType.RESOURCE,
        }

        error_type = pain_to_error.get(
            getattr(signal, "pain_type", "unknown"),
            ErrorType.UNKNOWN,
        )

        self._report_counter += 1

        return ErrorReport(
            error_type=error_type,
            message=getattr(signal, "description", "Unknown pain signal"),
            stack_trace="\n".join(getattr(signal, "evidence", [])),
            location=getattr(signal, "location", ""),
            error_class=f"PainSignal.{getattr(signal, 'pain_type', 'unknown')}",
            timestamp=getattr(signal, "timestamp", datetime.utcnow().isoformat() + "Z"),
            metadata={
                "source": "pain_signal",
                "signal_id": getattr(signal, "signal_id", ""),
                "pain_level": getattr(signal, "pain_level", 0),
                "report_id": f"DET-{self._report_counter:04d}",
            },
        )

    def detect_from_console(self, log_line: str) -> Optional[ErrorReport]:
        """
        从控制台日志检测错误/警告

        Args:
            log_line: 单行日志文本

        Returns:
            ErrorReport（如果检测到错误），否则 None
        """
        error_type = None
        severity = "error"

        # 检查错误模式
        for pattern in _LOG_ERROR_PATTERNS:
            if pattern.search(log_line):
                error_type = ErrorType.UNKNOWN
                severity = "error"
                break

        # 检查警告模式（优先级较低）
        if error_type is None:
            for pattern in _LOG_WARNING_PATTERNS:
                if pattern.search(log_line):
                    error_type = ErrorType.UNKNOWN
                    severity = "warning"
                    break

        if error_type is None:
            return None

        # 尝试从日志推断更具体的错误类型
        msg_lower = log_line.lower()
        if "syntaxerror" in msg_lower:
            error_type = ErrorType.SYNTAX
        elif "timeout" in msg_lower:
            error_type = ErrorType.TIMEOUT
        elif "connection" in msg_lower or "refused" in msg_lower:
            error_type = ErrorType.API
        elif "memory" in msg_lower or "resource" in msg_lower:
            error_type = ErrorType.RESOURCE
        elif "import" in msg_lower or "module" in msg_lower:
            error_type = ErrorType.IMPORT

        self._report_counter += 1

        return ErrorReport(
            error_type=error_type,
            message=log_line.strip(),
            stack_trace="",
            error_class=f"ConsoleLog.{severity}",
            metadata={
                "source": "console",
                "severity": severity,
                "report_id": f"DET-{self._report_counter:04d}",
            },
        )

    def detect_from_test_output(self, test_output: str) -> List[ErrorReport]:
        """
        从测试输出中提取所有失败

        Args:
            test_output: pytest/unittest 输出文本

        Returns:
            检测到的所有 ErrorReport
        """
        reports = []

        # pytest FAILED 模式
        failed_pattern = re.compile(r"FAILED (.+?) - (.+?)(?:\n|$)")
        for match in failed_pattern.finditer(test_output):
            location = match.group(1)
            message = match.group(2)
            reports.append(ErrorReport(
                error_type=ErrorType.RUNTIME,
                message=f"Test failed: {message}",
                stack_trace="",
                location=location,
                error_class="TestFailure",
                metadata={"source": "test_output", "test_framework": "pytest"},
            ))

        # ERROR 模式
        error_pattern = re.compile(r"ERROR (.+?)(?:\n|$)")
        for match in error_pattern.finditer(test_output):
            location = match.group(1)
            reports.append(ErrorReport(
                error_type=ErrorType.RUNTIME,
                message=f"Test error: {location}",
                stack_trace="",
                location=location,
                error_class="TestError",
                metadata={"source": "test_output"},
            ))

        return reports

    def _extract_location_from_trace(self, trace: str) -> str:
        """从 traceback 中提取最相关的文件位置"""
        lines = trace.strip().split("\n")
        # 查找最后一个 "File " 行（通常是实际错误位置）
        last_file_line = ""
        for line in lines:
            if 'File "' in line or "File '" in line:
                last_file_line = line.strip()

        if last_file_line:
            # 提取文件路径
            match = re.search(r'File "([^"]+)", line (\d+)', last_file_line)
            if match:
                return f"{match.group(1)}:{match.group(2)}"

        return ""
