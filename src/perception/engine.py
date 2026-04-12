"""
Perception Engine - Soma 感知引擎
=================================

整合所有感知器，提供统一的感知接口。

感知引擎是 Soma 的核心，类似大脑的感觉皮层，
整合来自不同感受器的信号，形成统一的环境感知。

架构：
    SomaPerception
    ├── NociceptorArray（疼痛感受器阵列）
    │   ├── SyntaxErrorNociceptor
    │   ├── RuntimeErrorNociceptor
    │   ├── WarningNociceptor
    │   └── ComplexityNociceptor
    └── ProprioceptorArray（位置感知器阵列）
        ├── SystemResourceProprioceptor
        ├── GPUProprioceptor
        ├── ToolchainProprioceptor
        ├── ConfigProprioceptor
        └── DependencyProprioceptor
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.protocol.oacp import DamageType, Priority
from .nociceptor import NociceptorArray, PainSignal, PainLevel
from .proprioceptor import ProprioceptorArray, SystemState


@dataclass
class PerceptionResult:
    """
    感知结果
    
    整合所有感知器的输出，形成统一的环境感知。
    类似于大脑感觉皮层的"感知图"。
    """
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    project_path: str = ""
    
    # 疼痛信号
    pain_signals: List[PainSignal] = field(default_factory=list)
    max_pain_level: PainLevel = PainLevel.PAIN_NONE
    pain_summary: Dict[str, Any] = field(default_factory=dict)
    
    # 系统状态
    system_state: Optional[SystemState] = None
    system_health_score: float = 1.0
    
    # 综合评估
    overall_health: float = 1.0
    should_trigger_signal: bool = False
    recommended_actions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "project_path": self.project_path,
            "max_pain_level": self.max_pain_level.name,
            "pain_summary": self.pain_summary,
            "system_health_score": self.system_health_score,
            "overall_health": self.overall_health,
            "should_trigger_signal": self.should_trigger_signal,
            "recommended_actions": self.recommended_actions,
            "pain_signals": [
                {
                    "signal_id": s.signal_id,
                    "pain_level": s.pain_level.name,
                    "pain_type": s.pain_type,
                    "location": s.location,
                    "description": s.description,
                }
                for s in self.pain_signals
            ],
            "system_state": self.system_state.to_dict() if self.system_state else None,
        }


class SomaPerception:
    """
    Soma 感知引擎
    
    整合所有感知器，提供统一的环境感知和损伤检测。
    这是 Soma（身体）的核心，将外部刺激转化为内部信号。
    
    工作流程：
    1. NociceptorArray 扫描疼痛信号（语法错误、运行时错误、警告、复杂度）
    2. ProprioceptorArray 感知系统状态（资源、工具链、配置、依赖）
    3. 整合所有信号，计算综合健康度
    4. 决定是否触发 SIGNAL 给 Plasticus
    
    使用：
        perception = SomaPerception()
        result = perception.perceive("/path/to/project")
        
        if result.should_trigger_signal:
            signal = perception.create_signal(result)
            # 发送给 Plasticus-Dev
    """
    
    # 健康度阈值
    SIGNAL_THRESHOLD = 0.70      # 低于此值触发 SIGNAL
    WARNING_THRESHOLD = 0.85     # 低于此值触发警告
    
    # 综合评估权重
    PAIN_WEIGHT = 0.60           # 疼痛信号权重
    SYSTEM_WEIGHT = 0.40         # 系统状态权重
    
    def __init__(
        self,
        nociceptor_array: Optional[NociceptorArray] = None,
        proprioceptor_array: Optional[ProprioceptorArray] = None,
        signal_threshold: float = 0.70
    ):
        """
        Args:
            nociceptor_array: 疼痛感受器阵列（默认使用标准配置）
            proprioceptor_array: 位置感知器阵列（默认使用标准配置）
            signal_threshold: 触发信号的阈值
        """
        self.nociceptors = nociceptor_array or NociceptorArray()
        self.proprioceptors = proprioceptor_array or ProprioceptorArray()
        self.signal_threshold = signal_threshold
        
        # 感知历史
        self.perception_history: List[PerceptionResult] = []
    
    def perceive(self, project_path: str) -> PerceptionResult:
        """
        全面感知项目状态
        
        Args:
            project_path: 项目路径
            
        Returns:
            感知结果
        """
        # 1. 疼痛感知
        pain_signals = self.nociceptors.scan(project_path)
        max_pain = self.nociceptors.get_max_pain_level(pain_signals)
        pain_summary = self.nociceptors.get_pain_summary(pain_signals)
        
        # 2. 本体感知
        system_state = self.proprioceptors.sense(project_path)
        system_health = system_state.get_health_score()
        
        # 3. 计算疼痛分数
        pain_score = self._calculate_pain_score(pain_signals)
        
        # 4. 综合健康度
        overall_health = (
            pain_score * self.PAIN_WEIGHT +
            system_health * self.SYSTEM_WEIGHT
        )
        overall_health = round(overall_health, 3)
        
        # 5. 推荐行动
        recommended_actions = self._generate_recommendations(
            pain_signals, system_state, overall_health
        )
        
        # 6. 组装结果
        result = PerceptionResult(
            timestamp=datetime.utcnow().isoformat() + "Z",
            project_path=project_path,
            pain_signals=pain_signals,
            max_pain_level=max_pain,
            pain_summary=pain_summary,
            system_state=system_state,
            system_health_score=system_health,
            overall_health=overall_health,
            should_trigger_signal=overall_health < self.signal_threshold,
            recommended_actions=recommended_actions,
        )
        
        # 记录历史
        self.perception_history.append(result)
        
        return result
    
    def _calculate_pain_score(self, signals: List[PainSignal]) -> float:
        """
        从疼痛信号计算疼痛分数（0-1，1=无痛）
        
        评分规则：
        - 每个信号按疼痛等级扣分
        - PAIN_MILD: -0.02
        - PAIN_MODERATE: -0.05
        - PAIN_SEVERE: -0.10
        - PAIN_CRITICAL: -0.20
        - 最低 0.0
        """
        if not signals:
            return 1.0
        
        penalties = {
            PainLevel.PAIN_MILD: 0.02,
            PainLevel.PAIN_MODERATE: 0.05,
            PainLevel.PAIN_SEVERE: 0.10,
            PainLevel.PAIN_CRITICAL: 0.20,
        }
        
        total_penalty = 0.0
        for signal in signals:
            penalty = penalties.get(signal.pain_level, 0.01)
            total_penalty += penalty
        
        # 最多扣到 0
        return max(0.0, 1.0 - total_penalty)
    
    def _generate_recommendations(
        self,
        pain_signals: List[PainSignal],
        system_state: SystemState,
        health: float
    ) -> List[str]:
        """生成推荐行动"""
        actions = []
        
        # 基于疼痛信号
        severe_signals = [s for s in pain_signals if s.pain_level >= PainLevel.PAIN_SEVERE]
        if severe_signals:
            actions.append(f"[P0] 立即修复 {len(severe_signals)} 个严重问题")
        
        syntax_errors = [s for s in pain_signals if s.pain_type == "syntax_error"]
        if syntax_errors:
            actions.append(f"[P0] 修复 {len(syntax_errors)} 个语法错误")
        
        runtime_errors = [s for s in pain_signals if s.pain_type == "runtime_error"]
        if runtime_errors:
            actions.append(f"[P1] 检查 {len(runtime_errors)} 个潜在运行时错误")
        
        complexity_issues = [s for s in pain_signals if s.pain_type == "code_decay"]
        if complexity_issues:
            actions.append(f"[P2] 降低代码复杂度（{len(complexity_issues)} 个问题）")
        
        # 基于系统状态
        if system_state.memory_percent and system_state.memory_percent > 90:
            actions.append("[P0] 内存使用率过高（>{:.0f}%），检查资源泄漏".format(system_state.memory_percent))
        
        if system_state.vulnerable_count > 0:
            actions.append(f"[P1] 修复 {system_state.vulnerable_count} 个安全漏洞")
        
        missing_configs = [k for k, v in system_state.configs.items() if v.value == "missing"]
        if missing_configs:
            actions.append(f"[P2] 补充缺失配置: {', '.join(missing_configs)}")
        
        if system_state.outdated_count > 5:
            actions.append(f"[P2] 更新 {system_state.outdated_count} 个过时依赖")
        
        # 基于健康度
        if health < self.SIGNAL_THRESHOLD:
            actions.append(f"[SIGNAL] 健康度 {health:.2f} < {self.SIGNAL_THRESHOLD}，建议触发修复流程")
        
        return actions
    
    def detect_damage(
        self, result: PerceptionResult
    ) -> Optional[Dict[str, Any]]:
        """
        从感知结果中检测损伤
        
        Args:
            result: 感知结果
            
        Returns:
            损伤信息（如果检测到），否则 None
        """
        if not result.should_trigger_signal:
            return None
        
        # 找到最严重的疼痛信号
        if result.pain_signals:
            worst = result.pain_signals[0]
            return {
                "symptom_type": worst.pain_type,
                "description": worst.description,
                "location": worst.location,
                "priority": worst.to_priority(),
                "evidence": worst.evidence,
                "health_score": result.overall_health,
            }
        
        # 如果系统健康度低但没有疼痛信号
        if result.system_health_score < self.SIGNAL_THRESHOLD:
            return {
                "symptom_type": "system_degradation",
                "description": f"系统健康度下降至 {result.system_health_score:.2f}",
                "location": "全局",
                "priority": Priority.P1,
                "evidence": [f"系统健康度: {result.system_health_score}"],
                "health_score": result.overall_health,
            }
        
        return None
    
    def create_signal_from_perception(
        self, result: PerceptionResult
    ):
        """
        从感知结果创建 SIGNAL 消息
        
        Args:
            result: 感知结果
            
        Returns:
            SignalMessage（如果应该触发），否则 None
        """
        from src.protocol.oacp import SignalMessage
        
        damage = self.detect_damage(result)
        if not damage:
            return None
        
        damage_type_map = {
            "syntax_error": DamageType.CODE_DECAY,
            "runtime_error": DamageType.CODE_DECAY,
            "api_failure": DamageType.LATENCY_ANOMALY,
            "warning": DamageType.CODE_DECAY,
            "performance": DamageType.RESOURCE_LEAK,
            "behavior_drift": DamageType.BEHAVIOR_DRIFT,
            "dependency_vulnerability": DamageType.DEPENDENCY_DECAY,
            "resource_leak": DamageType.RESOURCE_LEAK,
            "code_decay": DamageType.CODE_DECAY,
            "system_degradation": DamageType.RESOURCE_LEAK,
        }
        
        damage_type = damage_type_map.get(
            damage["symptom_type"], DamageType.CODE_DECAY
        )
        
        signal = SignalMessage.create(
            damage_type=damage_type,
            severity=damage["priority"],
            location=damage["location"],
            symptoms=damage["evidence"],
            health_score=result.overall_health,
            context={
                "description": damage["description"],
                "system_state": result.system_state.to_dict() if result.system_state else {},
                "pain_summary": result.pain_summary,
            }
        )
        
        return signal
    
    def get_trend(self, n_recent: int = 10) -> Dict[str, Any]:
        """
        获取感知趋势
        
        Args:
            n_recent: 最近 N 次感知
            
        Returns:
            趋势数据
        """
        if len(self.perception_history) < 2:
            return {"trend": "insufficient_data"}
        
        recent = self.perception_history[-n_recent:]
        health_scores = [r.overall_health for r in recent]
        
        if health_scores[-1] > health_scores[0]:
            trend = "improving"
        elif health_scores[-1] < health_scores[0]:
            trend = "declining"
        else:
            trend = "stable"
        
        avg_health = sum(health_scores) / len(health_scores)
        min_health = min(health_scores)
        max_health = max(health_scores)
        
        return {
            "trend": trend,
            "average_health": round(avg_health, 3),
            "latest_health": health_scores[-1],
            "min_health": round(min_health, 3),
            "max_health": round(max_health, 3),
            "data_points": len(health_scores),
        }
