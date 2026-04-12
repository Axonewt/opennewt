"""
Decision Engine - 决策引擎
===========================

整合感知层和决策层，提供端到端的决策流程。

工作流程：
    感知（Perception） → 分类（Quadrant） → 评估（Plasticity） → 决策（Decision） → 执行（Blueprint）

这是 Plasticus 的核心引擎，将感知信号转化为可执行的修复蓝图。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.protocol.oacp import (
    BlueprintMessage,
    DamageType,
    Priority,
    SignalMessage,
)
from src.models.plasticity import BlueprintGenerator, RepairPlan
from .quadrant import Quadrant, QuadrantClassification, QuadrantClassifier
from .matrix import Decision, DecisionType, PlasticityMatrix


@dataclass
class TaskAssessment:
    """
    任务评估结果
    
    包含从感知到决策的完整评估链。
    """
    assessment_id: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    # 输入
    health_score: float = 1.0
    pain_level: int = 0
    damage_type: str = ""
    
    # 分类
    classification: Optional[QuadrantClassification] = None
    
    # 决策
    decision: Optional[Decision] = None
    
    # 蓝图
    blueprint: Optional[BlueprintMessage] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "assessment_id": self.assessment_id,
            "timestamp": self.timestamp,
            "health_score": self.health_score,
            "pain_level": self.pain_level,
            "damage_type": self.damage_type,
        }
        
        if self.classification:
            result["classification"] = {
                "quadrant": self.classification.quadrant.value,
                "label": self.classification.quadrant.label,
                "importance": self.classification.importance.value,
                "urgency": self.classification.urgency.value,
                "importance_score": self.classification.importance_score,
                "urgency_score": self.classification.urgency_score,
                "confidence": self.classification.confidence,
                "reasoning": self.classification.reasoning,
            }
        
        if self.decision:
            result["decision"] = self.decision.to_dict()
        
        if self.blueprint:
            result["blueprint"] = {
                "plan_id": self.blueprint.payload.get("plan_id"),
                "strategy": self.blueprint.payload.get("strategy"),
                "estimated_downtime": self.blueprint.payload.get("estimated_downtime"),
                "success_rate_prediction": self.blueprint.payload.get("success_rate_prediction"),
            }
        
        return result


class DecisionEngine:
    """
    决策引擎
    
    整合感知层和决策层，提供端到端的决策流程。
    这是 Plasticus（可塑性）的"大脑皮层"。
    
    工作流程：
    1. 接收感知结果 → 评估和分类
    2. 接收损伤信号 → 评估和分类
    3. 做出决策 → 选择方案
    4. 生成蓝图 → 发送给 Effector
    
    使用：
        engine = DecisionEngine()
        
        # 从感知结果
        assessment = engine.assess_perception(perception_result)
        
        # 从信号
        assessment = engine.assess_signal(signal_message)
        
        # 获取蓝图
        if assessment.blueprint:
            # 发送给 Effector-Dev
            pass
    """
    
    def __init__(
        self,
        quadrant_classifier: Optional[QuadrantClassifier] = None,
        plasticity_matrix: Optional[PlasticityMatrix] = None,
        blueprint_generator: Optional[BlueprintGenerator] = None,
    ):
        """
        Args:
            quadrant_classifier: 四象限分类器
            plasticity_matrix: 决策矩阵
            blueprint_generator: 蓝图生成器
        """
        self.classifier = quadrant_classifier or QuadrantClassifier()
        self.matrix = plasticity_matrix or PlasticityMatrix()
        self.generator = blueprint_generator or BlueprintGenerator()
        self._assessment_counter = 0
    
    def _next_assessment_id(self) -> str:
        """生成下一个评估 ID"""
        self._assessment_counter += 1
        return f"ASM-{self._assessment_counter:04d}"
    
    def assess_perception(self, perception_result) -> TaskAssessment:
        """
        从感知结果进行评估
        
        Args:
            perception_result: PerceptionResult（来自 SomaPerception）
            
        Returns:
            任务评估结果
        """
        assessment = TaskAssessment(
            assessment_id=self._next_assessment_id(),
            health_score=perception_result.overall_health,
            pain_level=perception_result.max_pain_level.value,
        )
        
        # 获取最严重的疼痛信号的损伤类型
        if perception_result.pain_signals:
            worst = perception_result.pain_signals[0]
            assessment.damage_type = worst.pain_type
        
        # 分类
        assessment.classification = self.classifier.classify(
            health_score=perception_result.overall_health,
            pain_level=perception_result.max_pain_level.value,
            damage_type=assessment.damage_type,
        )
        
        # 生成修复方案
        available_plans = []
        if assessment.damage_type:
            available_plans = self.generator.generate_plans_from_signal(
                damage_type=assessment.damage_type,
                location="detected_by_perception",
                symptoms=[s.description for s in perception_result.pain_signals[:3]],
                health_score=perception_result.overall_health,
            )
        
        # 决策
        assessment.decision = self.matrix.decide_from_classification(
            assessment.classification,
            available_plans=available_plans,
        )
        
        # 生成蓝图（如果需要执行）
        if assessment.decision and assessment.decision.selected_plan:
            plan = assessment.decision.selected_plan
            assessment.blueprint = BlueprintMessage.create(
                plan_id=plan.plan_id,
                strategy=plan.name,
                steps=plan.steps,
                estimated_downtime=f"{plan.downtime_seconds}s",
                success_rate_prediction=plan.historical_success_rate,
                rollback_plan="git revert + 重启服务",
            )
        
        return assessment
    
    def assess_signal(self, signal: SignalMessage) -> TaskAssessment:
        """
        从 OACP 信号进行评估
        
        Args:
            signal: SignalMessage（来自 Soma-Dev）
            
        Returns:
            任务评估结果
        """
        payload = signal.payload
        
        # 解析优先级
        severity = payload.get("severity", "P2")
        pain_level_map = {"P0": 4, "P1": 3, "P2": 2}
        pain_level = pain_level_map.get(severity, 1)
        
        assessment = TaskAssessment(
            assessment_id=self._next_assessment_id(),
            health_score=payload.get("health_score", 1.0),
            pain_level=pain_level,
            damage_type=payload.get("damage_type", ""),
        )
        
        # 分类
        assessment.classification = self.classifier.classify(
            health_score=payload.get("health_score", 1.0),
            pain_level=pain_level,
            damage_type=payload.get("damage_type", ""),
            has_security_risk=payload.get("damage_type") == "依赖腐化",
        )
        
        # 生成修复方案
        available_plans = self.generator.generate_plans_from_signal(
            damage_type=payload.get("damage_type", ""),
            location=payload.get("location", ""),
            symptoms=payload.get("symptoms", []),
            health_score=payload.get("health_score", 1.0),
        )
        
        # 决策
        assessment.decision = self.matrix.decide_from_classification(
            assessment.classification,
            available_plans=available_plans,
        )
        
        # 生成蓝图
        if assessment.decision and assessment.decision.selected_plan:
            plan = assessment.decision.selected_plan
            assessment.blueprint = BlueprintMessage.create(
                plan_id=plan.plan_id,
                strategy=plan.name,
                steps=plan.steps,
                estimated_downtime=f"{plan.downtime_seconds}s",
                success_rate_prediction=plan.historical_success_rate,
                rollback_plan="git revert + 重启服务",
            )
        
        return assessment
    
    def batch_assess(
        self,
        signals: List[SignalMessage]
    ) -> List[TaskAssessment]:
        """
        批量评估多个信号
        
        Args:
            signals: 信号列表
            
        Returns:
            评估结果列表（按优先级降序）
        """
        assessments = [self.assess_signal(s) for s in signals]
        
        # 按优先级排序（Q1 > Q2 > Q3 > Q4）
        quadrant_order = {
            Quadrant.Q1_IMPORTANT_URGENT: 0,
            Quadrant.Q2_IMPORTANT_NOT_URGENT: 1,
            Quadrant.Q3_NOT_IMPORTANT_URGENT: 2,
            Quadrant.Q4_NOT_IMPORTANT_NOT_URGENT: 3,
        }
        
        assessments.sort(
            key=lambda a: quadrant_order.get(
                a.classification.quadrant if a.classification else Quadrant.Q4, 4
            )
        )
        
        return assessments
    
    def get_decision_summary(self, assessment: TaskAssessment) -> str:
        """
        生成决策摘要（用于日志和报告）
        
        Args:
            assessment: 任务评估结果
            
        Returns:
            决策摘要文本
        """
        lines = [
            "=" * 60,
            "[Plasticus] Decision Summary",
            "=" * 60,
            f"Assessment ID: {assessment.assessment_id}",
            f"Health Score: {assessment.health_score:.2f}",
            f"Damage Type: {assessment.damage_type}",
        ]
        
        if assessment.classification:
            c = assessment.classification
            lines.extend([
                "",
                f"Classification: {c.quadrant.value} ({c.quadrant.label})",
                f"  Importance: {c.importance_score:.2f} ({c.importance.value})",
                f"  Urgency: {c.urgency_score:.2f} ({c.urgency.value})",
                f"  Confidence: {c.confidence:.2f}",
                f"  Reasoning: {c.reasoning}",
            ])
        
        if assessment.decision:
            d = assessment.decision
            lines.extend([
                "",
                f"Decision: {d.decision_type.value}",
                f"  Priority: {d.priority.value}",
                f"  Reasoning: {d.reasoning}",
            ])
            
            if d.selected_plan:
                lines.extend([
                    f"  Selected Plan: {d.selected_plan.name}",
                    f"  Plan Score: {d.plan_score:.3f}",
                    f"  Est. Duration: {d.estimated_duration}",
                ])
            
            if d.recommended_actions:
                lines.append("  Recommended Actions:")
                for action in d.recommended_actions:
                    lines.append(f"    - {action}")
            
            if d.requires_human_approval:
                lines.append("  [!] Requires Human Approval")
        
        if assessment.blueprint:
            lines.extend([
                "",
                f"Blueprint Generated: {assessment.blueprint.payload.get('plan_id')}",
                f"  Strategy: {assessment.blueprint.payload.get('strategy')}",
            ])
        else:
            lines.extend(["", "No Blueprint Generated (monitoring/deferred)"])
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
