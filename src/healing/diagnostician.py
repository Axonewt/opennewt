"""
诊断引擎 - 分析错误根因
========================

两层诊断策略：
1. 规则引擎（快速、确定性强）- 基于模式匹配和启发式规则
2. LLM 增强（深度、不确定场景）- 调用 AI 进行根因分析

输出标准化 DiagnosticResult，供下游 Healer 执行修复。
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .detector import ErrorReport, ErrorType


@dataclass
class DiagnosticResult:
    """
    诊断结果

    包含根因分析、修复建议和置信度。
    confidence 范围 0.0 - 1.0：
    - >= 0.8: 高置信度，建议自动修复
    - 0.5 - 0.8: 中等置信度，Dry Run 验证后修复
    - < 0.5: 低置信度，建议人工介入
    """
    root_cause: str
    fix_suggestion: str
    confidence: float
    fix_type: str = "manual"          # auto_restart, auto_install, auto_config, auto_patch, manual
    affected_files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_auto_fixable(self) -> bool:
        """是否可以自动修复"""
        return self.confidence >= 0.7 and self.fix_type != "manual"

    @property
    def risk_level(self) -> str:
        """风险等级"""
        if self.confidence >= 0.8:
            return "low"
        elif self.confidence >= 0.5:
            return "medium"
        return "high"


# 语法错误诊断规则
_SYNTAX_RULES = [
    {
        "pattern": r"unexpected indent",
        "root_cause": "缩进错误 - 可能混用了 Tab 和 Space",
        "fix_suggestion": "将 Tab 替换为 4 个空格，确保缩进一致",
        "confidence": 0.95,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"expected an indented block",
        "root_cause": "缺少缩进块 - if/for/while/def/class 后需要缩进",
        "fix_suggestion": "在冒号后添加缩进代码块",
        "confidence": 0.95,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"invalid syntax",
        "root_cause": "Python 语法错误",
        "fix_suggestion": "检查该行的语法，常见原因：缺少冒号、括号不匹配、关键字拼写错误",
        "confidence": 0.8,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"EOL while scanning string",
        "root_cause": "字符串未闭合 - 缺少引号",
        "fix_suggestion": "检查字符串引号是否配对",
        "confidence": 0.9,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"unterminated string literal",
        "root_cause": "字符串字面量未终止",
        "fix_suggestion": "确保所有字符串都有闭合引号",
        "confidence": 0.9,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"non-default argument follows default argument",
        "root_cause": "函数定义中非默认参数跟在默认参数后面",
        "fix_suggestion": "将所有默认参数移到非默认参数之后",
        "confidence": 0.95,
        "fix_type": "auto_patch",
    },
]

# API 错误诊断规则
_API_RULES = [
    {
        "pattern": r"Connection refused",
        "root_cause": "服务未启动或端口拒绝连接",
        "fix_suggestion": "检查目标服务是否运行（如 Ollama、数据库）",
        "confidence": 0.95,
        "fix_type": "auto_restart",
    },
    {
        "pattern": r"Connection reset",
        "root_cause": "连接被远程端重置",
        "fix_suggestion": "检查网络稳定性，可能是服务重启导致",
        "confidence": 0.8,
        "fix_type": "auto_restart",
    },
    {
        "pattern": r"timed? ?out",
        "root_cause": "请求超时",
        "fix_suggestion": "增加超时时间或检查服务响应速度",
        "confidence": 0.75,
        "fix_type": "auto_config",
    },
    {
        "pattern": r"401|Unauthorized",
        "root_cause": "认证失败 - API Key 无效或过期",
        "fix_suggestion": "检查 API Key 配置，必要时重新生成",
        "confidence": 0.9,
        "fix_type": "auto_config",
    },
    {
        "pattern": r"403|Forbidden",
        "root_cause": "权限不足 - 无权访问该资源",
        "fix_suggestion": "检查账户权限和访问控制配置",
        "confidence": 0.85,
        "fix_type": "manual",
    },
    {
        "pattern": r"429|Too Many Requests|rate limit",
        "root_cause": "请求频率超限 - 触发 API 限流",
        "fix_suggestion": "降低请求频率，添加重试退避逻辑",
        "confidence": 0.9,
        "fix_type": "auto_config",
    },
    {
        "pattern": r"500|Internal Server Error",
        "root_cause": "服务端内部错误",
        "fix_suggestion": "检查服务端日志，可能是服务端 Bug 或资源不足",
        "confidence": 0.6,
        "fix_type": "manual",
    },
    {
        "pattern": r"502|Bad Gateway",
        "root_cause": "网关错误 - 上游服务不可用",
        "fix_suggestion": "等待上游服务恢复，检查反向代理配置",
        "confidence": 0.7,
        "fix_type": "auto_restart",
    },
    {
        "pattern": r"503|Service Unavailable",
        "root_cause": "服务不可用 - 可能是维护或过载",
        "fix_suggestion": "等待服务恢复或检查服务健康状态",
        "confidence": 0.7,
        "fix_type": "auto_restart",
    },
]

# 导入错误诊断规则
_IMPORT_RULES = [
    {
        "pattern": r"No module named '(.+)'",
        "root_cause": "缺少 Python 模块",
        "fix_suggestion": "运行 pip install {module} 安装缺失模块",
        "confidence": 0.95,
        "fix_type": "auto_install",
        "extract_module": True,
    },
    {
        "pattern": r"cannot import name '(.+)' from '(.+)'",
        "root_cause": "模块中不存在指定的名称",
        "fix_suggestion": "检查模块版本，可能已重命名或移除",
        "confidence": 0.75,
        "fix_type": "auto_install",
    },
    {
        "pattern": r"DLL load failed",
        "root_cause": "动态链接库加载失败",
        "fix_suggestion": "检查依赖库是否安装（如 Visual C++ Redistributable）",
        "confidence": 0.7,
        "fix_type": "manual",
    },
]

# 资源错误诊断规则
_RESOURCE_RULES = [
    {
        "pattern": r"MemoryError|out of memory",
        "root_cause": "内存不足",
        "fix_suggestion": "减少批处理大小、释放缓存、增加 swap 空间",
        "confidence": 0.85,
        "fix_type": "auto_config",
    },
    {
        "pattern": r"RecursionError|maximum recursion depth",
        "root_cause": "递归深度超限",
        "fix_suggestion": "检查递归终止条件，或使用 sys.setrecursionlimit() 增加限制",
        "confidence": 0.9,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"Permission denied",
        "root_cause": "文件权限不足",
        "fix_suggestion": "检查文件权限，可能需要管理员权限",
        "confidence": 0.9,
        "fix_type": "manual",
    },
    {
        "pattern": r"No space left on device",
        "root_cause": "磁盘空间不足",
        "fix_suggestion": "清理磁盘空间，删除临时文件和缓存",
        "confidence": 0.95,
        "fix_type": "manual",
    },
]

# 运行时错误诊断规则
_RUNTIME_RULES = [
    {
        "pattern": r"NameError: name '(.+)' is not defined",
        "root_cause": "变量未定义",
        "fix_suggestion": "检查变量拼写、作用域和导入",
        "confidence": 0.85,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"KeyError: '(.+)'",
        "root_cause": "字典中不存在指定的键",
        "fix_suggestion": "使用 dict.get(key, default) 或先检查键是否存在",
        "confidence": 0.85,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"IndexError: (?:list index out of range|tuple index out of range)",
        "root_cause": "索引越界",
        "fix_suggestion": "访问前检查列表/元组长度",
        "confidence": 0.9,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"AttributeError: '(.+)' object has no attribute '(.+)'",
        "root_cause": "对象没有指定的属性/方法",
        "fix_suggestion": "检查对象类型和属性名称拼写",
        "confidence": 0.8,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"TypeError: (.+)",
        "root_cause": "类型不匹配",
        "fix_suggestion": "检查传入参数的类型是否正确",
        "confidence": 0.7,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"ValueError: (.+)",
        "root_cause": "值不合法",
        "fix_suggestion": "检查传入值的格式和范围",
        "confidence": 0.7,
        "fix_type": "auto_patch",
    },
    {
        "pattern": r"NotImplementedError",
        "root_cause": "调用了未实现的方法",
        "fix_suggestion": "实现该方法或使用已实现的替代方案",
        "confidence": 0.9,
        "fix_type": "manual",
    },
]


class Diagnostician:
    """
    诊断引擎

    分析错误报告，找出根因并生成修复建议。
    采用两层策略：规则引擎（快速）+ LLM 增强（深度）。
    """

    def __init__(self):
        # 按错误类型组织的规则
        self._rules = {
            ErrorType.SYNTAX: _SYNTAX_RULES,
            ErrorType.API: _API_RULES,
            ErrorType.IMPORT: _IMPORT_RULES,
            ErrorType.RESOURCE: _RESOURCE_RULES,
            ErrorType.RUNTIME: _RUNTIME_RULES,
            ErrorType.TIMEOUT: _API_RULES,  # 共用 API 规则中的超时部分
            ErrorType.CONFIG: [],
            ErrorType.DEPENDENCY: [],
            ErrorType.TYPE: _RUNTIME_RULES,
            ErrorType.VALUE: _RUNTIME_RULES,
            ErrorType.PERMISSION: _RESOURCE_RULES,
            ErrorType.UNKNOWN: [],
        }

    def diagnose(self, error_report: ErrorReport) -> DiagnosticResult:
        """
        诊断错误

        Args:
            error_report: 检测器生成的错误报告

        Returns:
            标准化的诊断结果
        """
        # 1. 基于错误类型选择规则集
        rules = self._rules.get(error_report.error_type, [])

        # 2. 尝试规则匹配
        result = self._match_rules(error_report, rules)

        # 3. 如果规则匹配失败，尝试跨类型全局匹配
        if result.confidence < 0.5:
            result = self._global_match(error_report)

        # 4. 提取受影响的文件
        if error_report.location:
            result.affected_files.append(error_report.location)

        return result

    def _match_rules(
        self,
        error_report: ErrorReport,
        rules: List[Dict[str, Any]],
    ) -> DiagnosticResult:
        """
        匹配规则引擎

        遍历规则列表，返回第一个匹配且置信度最高的结果。
        """
        # 合并 message 和 stack_trace 用于匹配
        search_text = f"{error_report.message}\n{error_report.stack_trace}"

        best_result = DiagnosticResult(
            root_cause="未知原因",
            fix_suggestion="需要进一步分析或人工介入",
            confidence=0.3,
            fix_type="manual",
        )

        for rule in rules:
            pattern = rule["pattern"]
            match = re.search(pattern, search_text, re.IGNORECASE)

            if match:
                confidence = rule["confidence"]

                # 如果规则能提取模块名，动态生成修复建议
                fix_suggestion = rule["fix_suggestion"]
                if rule.get("extract_module") and match.lastindex:
                    module_name = match.group(1)
                    fix_suggestion = f"运行 pip install {module_name}"

                # 优先选择高置信度匹配
                if confidence > best_result.confidence:
                    best_result = DiagnosticResult(
                        root_cause=rule["root_cause"],
                        fix_suggestion=fix_suggestion,
                        confidence=confidence,
                        fix_type=rule.get("fix_type", "manual"),
                        metadata={"matched_pattern": pattern},
                    )

        return best_result

    def _global_match(self, error_report: ErrorReport) -> DiagnosticResult:
        """
        全局规则匹配

        当类型规则匹配失败时，在所有规则中搜索。
        """
        all_rules = []
        for rules in self._rules.values():
            all_rules.extend(rules)

        return self._match_rules(error_report, all_rules)

    def diagnose_batch(self, error_reports: List[ErrorReport]) -> List[DiagnosticResult]:
        """
        批量诊断

        Args:
            error_reports: 错误报告列表

        Returns:
            诊断结果列表
        """
        return [self.diagnose(report) for report in error_reports]
