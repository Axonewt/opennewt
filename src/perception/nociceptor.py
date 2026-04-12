"""
Nociceptor - 疼痛感受器
========================

检测代码库的"疼痛"信号：
- 语法错误（SyntaxError）
- 运行时异常（RuntimeError, NameError 等）
- API 失败（HTTP 5xx, 超时）
- 控制台警告（deprecation, resource warning）
- 性能下降（响应时间增加、资源增长）
- 行为偏离（测试通过率下降、输出漂移）

疼痛等级：
- PAIN_NONE (0): 无痛
- PAIN_MILD (1): 轻微不适（警告、低优先级问题）
- PAIN_MODERATE (2): 中等疼痛（性能下降、测试偶尔失败）
- PAIN_SEVERE (3): 严重疼痛（运行时错误、API 持续失败）
- PAIN_CRITICAL (4): 危及生命（系统崩溃、数据丢失风险）
"""

import ast
import os
import re
import glob
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Dict, List, Optional, Tuple, Any

from src.protocol.oacp import Priority, DamageType


class PainLevel(IntEnum):
    """疼痛等级（从无痛到危及生命）"""
    PAIN_NONE = 0       # 无异常
    PAIN_MILD = 1       # 轻微：警告、低优先级
    PAIN_MODERATE = 2   # 中等：性能下降、测试偶尔失败
    PAIN_SEVERE = 3     # 严重：运行时错误、API 失败
    PAIN_CRITICAL = 4   # 危及生命：崩溃、数据丢失


@dataclass
class PainSignal:
    """
    疼痛信号
    
    一个疼痛信号代表感知器检测到的一次异常。
    类似于生物神经系统的伤害性刺激信号。
    """
    signal_id: str
    pain_level: PainLevel
    pain_type: str              # 疼痛类型：syntax_error, runtime_error, api_failure, warning, performance, behavior_drift
    location: str               # 位置：文件路径或模块名
    description: str            # 描述
    evidence: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_damage_type(self) -> DamageType:
        """将疼痛信号映射为损伤类型"""
        mapping = {
            "syntax_error": DamageType.CODE_DECAY,
            "runtime_error": DamageType.CODE_DECAY,
            "api_failure": DamageType.LATENCY_ANOMALY,
            "warning": DamageType.CODE_DECAY,
            "performance": DamageType.RESOURCE_LEAK,
            "behavior_drift": DamageType.BEHAVIOR_DRIFT,
            "dependency_vulnerability": DamageType.DEPENDENCY_DECAY,
            "resource_leak": DamageType.RESOURCE_LEAK,
        }
        return mapping.get(self.pain_type, DamageType.CODE_DECAY)
    
    def to_priority(self) -> Priority:
        """将疼痛等级映射为优先级"""
        if self.pain_level >= PainLevel.PAIN_CRITICAL:
            return Priority.P0
        elif self.pain_level >= PainLevel.PAIN_SEVERE:
            return Priority.P0
        elif self.pain_level >= PainLevel.PAIN_MODERATE:
            return Priority.P1
        else:
            return Priority.P2


class Nociceptor:
    """
    疼痛感受器（单个）
    
    每个感受器专注于一种类型的"疼痛"检测。
    类似于皮肤上的伤害性感受器，检测特定类型的刺激。
    """
    
    def __init__(self, name: str, pain_type: str, threshold: PainLevel = PainLevel.PAIN_MILD):
        """
        Args:
            name: 感受器名称
            pain_type: 感知的疼痛类型
            threshold: 触发阈值（低于此等级的信号会被过滤）
        """
        self.name = name
        self.pain_type = pain_type
        self.threshold = threshold
        self.signals: List[PainSignal] = []
        self._signal_counter = 0
    
    def _next_signal_id(self) -> str:
        """生成下一个信号 ID"""
        self._signal_counter += 1
        return f"NOC-{self.name}-{self._signal_counter:04d}"
    
    def detect(self, project_path: str) -> List[PainSignal]:
        """
        检测疼痛信号
        
        Args:
            project_path: 项目路径
            
        Returns:
            检测到的疼痛信号列表
        """
        raise NotImplementedError("子类必须实现 detect 方法")
    
    def _emit_signal(
        self,
        pain_level: PainLevel,
        location: str,
        description: str,
        evidence: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[PainSignal]:
        """
        发射疼痛信号
        
        如果疼痛等级低于阈值，则不发射。
        
        Args:
            pain_level: 疼痛等级
            location: 位置
            description: 描述
            evidence: 证据
            metadata: 元数据
            
        Returns:
            疼痛信号（如果高于阈值），否则 None
        """
        if pain_level < self.threshold:
            return None
        
        signal = PainSignal(
            signal_id=self._next_signal_id(),
            pain_level=pain_level,
            pain_type=self.pain_type,
            location=location,
            description=description,
            evidence=evidence or [],
            metadata=metadata or {}
        )
        
        self.signals.append(signal)
        return signal


class SyntaxErrorNociceptor(Nociceptor):
    """
    语法错误感受器
    
    通过 AST 解析检测 Python 文件中的语法错误。
    疼痛等级：PAIN_SEVERE（语法错误直接阻止代码执行）
    """
    
    def __init__(self):
        super().__init__(
            name="syntax",
            pain_type="syntax_error",
            threshold=PainLevel.PAIN_MILD
        )
    
    def detect(self, project_path: str) -> List[PainSignal]:
        """扫描 Python 文件语法错误"""
        signals = []
        py_files = self._find_files(project_path, "*.py")
        
        # 排除虚拟环境和缓存目录
        exclude_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git", ".mypy_cache"}
        
        for filepath in py_files:
            # 检查是否在排除目录中
            parts = os.path.normpath(filepath).split(os.sep)
            if any(d in parts for d in exclude_dirs):
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    source = f.read()
                
                if not source.strip():
                    continue
                
                ast.parse(source, filename=filepath)
                
            except SyntaxError as e:
                signal = self._emit_signal(
                    pain_level=PainLevel.PAIN_SEVERE,
                    location=filepath,
                    description=f"语法错误: {e.msg} (line {e.lineno})",
                    evidence=[
                        f"File: {os.path.relpath(filepath, project_path)}",
                        f"Line: {e.lineno}",
                        f"Error: {e.msg}"
                    ],
                    metadata={"line": e.lineno, "offset": e.offset, "text": e.text}
                )
                if signal:
                    signals.append(signal)
        
        return signals
    
    def _find_files(self, base_path: str, pattern: str) -> List[str]:
        """查找文件"""
        search_path = os.path.join(base_path, "**", pattern)
        return glob.glob(search_path, recursive=True)


class RuntimeErrorNociceptor(Nociceptor):
    """
    运行时错误感受器
    
    通过静态模式匹配检测潜在的运行时错误：
    - 未处理的异常捕获（bare except）
    - 变量使用前未定义
    - 导入模块不存在
    
    疼痛等级：PAIN_MODERATE ~ PAIN_SEVERE
    """
    
    def __init__(self):
        super().__init__(
            name="runtime",
            pain_type="runtime_error",
            threshold=PainLevel.PAIN_MILD
        )
    
    def detect(self, project_path: str) -> List[PainSignal]:
        """扫描潜在运行时错误"""
        signals = []
        py_files = self._find_files(project_path, "*.py")
        exclude_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git", ".mypy_cache"}
        
        for filepath in py_files:
            parts = os.path.normpath(filepath).split(os.sep)
            if any(d in parts for d in exclude_dirs):
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    source = f.read()
                
                if not source.strip():
                    continue
                
                # 检测 bare except
                bare_excepts = re.findall(r'except\s*:', source)
                if bare_excepts:
                    signal = self._emit_signal(
                        pain_level=PainLevel.PAIN_MODERATE,
                        location=filepath,
                        description=f"发现 {len(bare_excepts)} 处 bare except（会掩盖所有异常）",
                        evidence=[f"bare except count: {len(bare_excepts)}"],
                        metadata={"pattern": "bare_except", "count": len(bare_excepts)}
                    )
                    if signal:
                        signals.append(signal)
                
                # 检测 pass 占位符（可能表示未实现的错误处理）
                # except ... pass 模式
                pass_in_except = re.findall(r'except[^:]*:\s*pass', source)
                if pass_in_except:
                    signal = self._emit_signal(
                        pain_level=PainLevel.PAIN_MILD,
                        location=filepath,
                        description=f"发现 {len(pass_in_except)} 处空异常处理（except: pass）",
                        evidence=[f"empty except count: {len(pass_in_except)}"],
                        metadata={"pattern": "empty_except", "count": len(pass_in_except)}
                    )
                    if signal:
                        signals.append(signal)
                
            except Exception:
                pass
        
        return signals
    
    def _find_files(self, base_path: str, pattern: str) -> List[str]:
        """查找文件"""
        search_path = os.path.join(base_path, "**", pattern)
        return glob.glob(search_path, recursive=True)


class WarningNociceptor(Nociceptor):
    """
    警告感受器
    
    通过外部工具（pylint）或静态分析检测警告：
    - DeprecationWarning
    - ResourceWarning
    - 代码质量问题
    
    疼痛等级：PAIN_MILD ~ PAIN_MODERATE
    """
    
    def __init__(self):
        super().__init__(
            name="warning",
            pain_type="warning",
            threshold=PainLevel.PAIN_MILD
        )
    
    def detect(self, project_path: str) -> List[PainSignal]:
        """扫描警告"""
        signals = []
        
        # 1. 尝试运行 pylint
        pylint_signals = self._run_pylint(project_path)
        signals.extend(pylint_signals)
        
        # 2. 静态检测 TODO/FIXME 标记
        todo_signals = self._detect_todos(project_path)
        signals.extend(todo_signals)
        
        return signals
    
    def _run_pylint(self, project_path: str) -> List[PainSignal]:
        """运行 pylint 获取警告"""
        signals = []
        
        try:
            result = subprocess.run(
                ["pylint", "--output-format=json", project_path],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.stdout.strip():
                import json
                warnings = json.loads(result.stdout)
                
                # 按类型分组统计
                type_counts: Dict[str, int] = {}
                for w in warnings:
                    msg_type = w.get("type", "unknown")
                    type_counts[msg_type] = type_counts.get(msg_type, 0) + 1
                
                # 总警告数
                total = len(warnings)
                if total > 20:
                    signal = self._emit_signal(
                        pain_level=PainLevel.PAIN_MODERATE,
                        location=project_path,
                        description=f"Pylint 发现 {total} 个问题（{dict(type_counts)}）",
                        evidence=[f"Total: {total}"] + [f"{k}: {v}" for k, v in type_counts.items()],
                        metadata={"tool": "pylint", "counts": type_counts}
                    )
                    if signal:
                        signals.append(signal)
                elif total > 5:
                    signal = self._emit_signal(
                        pain_level=PainLevel.PAIN_MILD,
                        location=project_path,
                        description=f"Pylint 发现 {total} 个问题",
                        evidence=[f"Total: {total}"],
                        metadata={"tool": "pylint", "total": total}
                    )
                    if signal:
                        signals.append(signal)
        
        except FileNotFoundError:
            # pylint 未安装，跳过
            pass
        except (subprocess.TimeoutExpired, Exception):
            pass
        
        return signals
    
    def _detect_todos(self, project_path: str) -> List[PainSignal]:
        """检测 TODO/FIXME 标记"""
        signals = []
        py_files = self._find_files(project_path, "*.py")
        exclude_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git", ".mypy_cache"}
        
        todo_count = 0
        fixme_count = 0
        hack_count = 0
        
        for filepath in py_files:
            parts = os.path.normpath(filepath).split(os.sep)
            if any(d in parts for d in exclude_dirs):
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        line_lower = line.lower().strip()
                        if '# todo' in line_lower or '# todo:' in line_lower:
                            todo_count += 1
                        elif '# fixme' in line_lower or '# fixme:' in line_lower:
                            fixme_count += 1
                        elif '# hack' in line_lower or '# xxx' in line_lower:
                            hack_count += 1
            except Exception:
                pass
        
        total_todos = todo_count + fixme_count + hack_count
        if total_todos > 0:
            signal = self._emit_signal(
                pain_level=PainLevel.PAIN_MILD,
                location=project_path,
                description=f"发现 {total_todos} 个待办标记（TODO:{todo_count}, FIXME:{fixme_count}, HACK:{hack_count}）",
                evidence=[f"TODO: {todo_count}", f"FIXME: {fixme_count}", f"HACK: {hack_count}"],
                metadata={"todos": todo_count, "fixmes": fixme_count, "hacks": hack_count}
            )
            if signal:
                signals.append(signal)
        
        return signals
    
    def _find_files(self, base_path: str, pattern: str) -> List[str]:
        """查找文件"""
        search_path = os.path.join(base_path, "**", pattern)
        return glob.glob(search_path, recursive=True)


class ComplexityNociceptor(Nociceptor):
    """
    代码复杂度感受器
    
    通过 AST 分析检测代码复杂度问题：
    - 函数/方法过长（>50 行）
    - 圈复杂度过高（>10）
    - 嵌套深度过大（>4 层）
    - 类过大（>300 行）
    
    疼痛等级：PAIN_MILD ~ PAIN_MODERATE
    """
    
    # 复杂度阈值
    MAX_FUNCTION_LINES = 50
    MAX_CYCLOMATIC = 10
    MAX_NESTING = 4
    MAX_CLASS_LINES = 300
    
    def __init__(self):
        super().__init__(
            name="complexity",
            pain_type="code_decay",
            threshold=PainLevel.PAIN_MILD
        )
    
    def detect(self, project_path: str) -> List[PainSignal]:
        """扫描代码复杂度"""
        signals = []
        py_files = self._find_files(project_path, "*.py")
        exclude_dirs = {"venv", ".venv", "node_modules", "__pycache__", ".git", ".mypy_cache"}
        
        long_functions = []
        high_complexity = []
        deep_nesting = []
        large_classes = []
        
        for filepath in py_files:
            parts = os.path.normpath(filepath).split(os.sep)
            if any(d in parts for d in exclude_dirs):
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    source = f.read()
                
                if not source.strip():
                    continue
                
                tree = ast.parse(source, filename=filepath)
                rel_path = os.path.relpath(filepath, project_path)
                
                for node in ast.walk(tree):
                    # 检测函数长度
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if hasattr(node, 'end_lineno') and node.end_lineno:
                            lines = node.end_lineno - node.lineno + 1
                            if lines > self.MAX_FUNCTION_LINES:
                                long_functions.append(
                                    f"{rel_path}::{node.name} ({lines} lines)"
                                )
                            
                            # 检测圈复杂度
                            complexity = self._calculate_cyclomatic(node)
                            if complexity > self.MAX_CYCLOMATIC:
                                high_complexity.append(
                                    f"{rel_path}::{node.name} (complexity: {complexity})"
                                )
                    
                    # 检测类大小
                    elif isinstance(node, ast.ClassDef):
                        if hasattr(node, 'end_lineno') and node.end_lineno:
                            lines = node.end_lineno - node.lineno + 1
                            if lines > self.MAX_CLASS_LINES:
                                large_classes.append(
                                    f"{rel_path}::{node.name} ({lines} lines)"
                                )
                
                # 检测嵌套深度
                max_depth = self._max_nesting_depth(tree)
                if max_depth > self.MAX_NESTING:
                    deep_nesting.append(
                        f"{rel_path} (max depth: {max_depth})"
                    )
                
            except (SyntaxError, Exception):
                continue
        
        # 发射信号
        if long_functions:
            signal = self._emit_signal(
                pain_level=PainLevel.PAIN_MODERATE,
                location=project_path,
                description=f"发现 {len(long_functions)} 个过长函数（>{self.MAX_FUNCTION_LINES} 行）",
                evidence=long_functions[:5],
                metadata={"type": "long_functions", "count": len(long_functions)}
            )
            if signal:
                signals.append(signal)
        
        if high_complexity:
            signal = self._emit_signal(
                pain_level=PainLevel.PAIN_MODERATE,
                location=project_path,
                description=f"发现 {len(high_complexity)} 个高复杂度函数（>{self.MAX_CYCLOMATIC}）",
                evidence=high_complexity[:5],
                metadata={"type": "high_complexity", "count": len(high_complexity)}
            )
            if signal:
                signals.append(signal)
        
        if deep_nesting:
            signal = self._emit_signal(
                pain_level=PainLevel.PAIN_MILD,
                location=project_path,
                description=f"发现 {len(deep_nesting)} 个文件嵌套过深（>{self.MAX_NESTING} 层）",
                evidence=deep_nesting[:5],
                metadata={"type": "deep_nesting", "count": len(deep_nesting)}
            )
            if signal:
                signals.append(signal)
        
        if large_classes:
            signal = self._emit_signal(
                pain_level=PainLevel.PAIN_MILD,
                location=project_path,
                description=f"发现 {len(large_classes)} 个过大类（>{self.MAX_CLASS_LINES} 行）",
                evidence=large_classes[:5],
                metadata={"type": "large_classes", "count": len(large_classes)}
            )
            if signal:
                signals.append(signal)
        
        return signals
    
    def _calculate_cyclomatic(self, node: ast.AST) -> int:
        """计算圈复杂度"""
        complexity = 1  # 基础复杂度
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, (ast.And, ast.Or)):
                complexity += 1
            elif isinstance(child, ast.comprehension):
                complexity += 1
            elif isinstance(child, (ast.Assert, ast.With)):
                complexity += 1
        return complexity
    
    def _max_nesting_depth(self, tree: ast.AST) -> int:
        """计算最大嵌套深度"""
        max_depth = 0
        
        def _walk(node, depth):
            nonlocal max_depth
            nesting_nodes = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)
            if isinstance(node, nesting_nodes):
                depth += 1
                max_depth = max(max_depth, depth)
            for child in ast.iter_child_nodes(node):
                _walk(child, depth)
        
        _walk(tree, 0)
        return max_depth
    
    def _find_files(self, base_path: str, pattern: str) -> List[str]:
        """查找文件"""
        search_path = os.path.join(base_path, "**", pattern)
        return glob.glob(search_path, recursive=True)


class NociceptorArray:
    """
    疼痛感受器阵列
    
    管理所有疼痛感受器，提供统一的感知接口。
    类似于皮肤上的伤害性感受器网络，全面感知"疼痛"。
    
    默认包含的感受器：
    - SyntaxErrorNociceptor: 语法错误
    - RuntimeErrorNociceptor: 运行时错误模式
    - WarningNociceptor: 警告
    - ComplexityNociceptor: 代码复杂度
    """
    
    def __init__(self, custom_nociceptors: Optional[List[Nociceptor]] = None):
        """
        Args:
            custom_nociceptors: 自定义感受器列表（会替换默认感受器）
        """
        if custom_nociceptors:
            self.nociceptors = custom_nociceptors
        else:
            self.nociceptors = [
                SyntaxErrorNociceptor(),
                RuntimeErrorNociceptor(),
                WarningNociceptor(),
                ComplexityNociceptor(),
            ]
    
    def scan(self, project_path: str) -> List[PainSignal]:
        """
        全面扫描疼痛信号
        
        Args:
            project_path: 项目路径
            
        Returns:
            所有感受器检测到的疼痛信号（按疼痛等级降序）
        """
        all_signals: List[PainSignal] = []
        
        for nociceptor in self.nociceptors:
            try:
                signals = nociceptor.detect(project_path)
                all_signals.extend(signals)
            except Exception as e:
                # 单个感受器失败不影响整体
                print(f"[Nociceptor] {nociceptor.name} 扫描失败: {e}")
        
        # 按疼痛等级降序排序
        all_signals.sort(key=lambda s: s.pain_level, reverse=True)
        
        return all_signals
    
    def get_max_pain_level(self, signals: List[PainSignal]) -> PainLevel:
        """获取最高疼痛等级"""
        if not signals:
            return PainLevel.PAIN_NONE
        return max(s.pain_level for s in signals)
    
    def get_pain_summary(self, signals: List[PainSignal]) -> Dict[str, Any]:
        """获取疼痛信号摘要"""
        if not signals:
            return {
                "total_signals": 0,
                "max_pain_level": PainLevel.PAIN_NONE.name,
                "by_type": {},
                "by_level": {}
            }
        
        by_type: Dict[str, int] = {}
        by_level: Dict[str, int] = {}
        
        for signal in signals:
            by_type[signal.pain_type] = by_type.get(signal.pain_type, 0) + 1
            level_name = signal.pain_level.name
            by_level[level_name] = by_level.get(level_name, 0) + 1
        
        return {
            "total_signals": len(signals),
            "max_pain_level": self.get_max_pain_level(signals).name,
            "by_type": by_type,
            "by_level": by_level,
            "critical_count": sum(1 for s in signals if s.pain_level >= PainLevel.PAIN_SEVERE),
            "moderate_count": sum(1 for s in signals if s.pain_level == PainLevel.PAIN_MODERATE),
            "mild_count": sum(1 for s in signals if s.pain_level == PainLevel.PAIN_MILD),
        }
