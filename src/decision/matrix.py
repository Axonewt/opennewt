"""
PlasticityMatrix - 决策矩阵
============================

基于四象限分类和可塑性评估，做出最优决策。

决策流程：
1. 输入：感知结果（PainSignal + SystemState）
2. 分类：使用 QuadrantClassifier 确定象限
3. 评估：使用 PlasticityEvaluator 对可选方案评分
4. 决策：根据象限和评估结果做出决策
5. 输出：Decision（包含行动方案和执行建议）

决策类型：
- IMMEDIATE: 立即执行（第一象限）
- SCHEDULED: 规划执行（第二象限）
- DELEGATED: 委托执行（第三象限）
- DEFERRED: 延迟或删除（第四象限）
- ESCALATED: 升级人工（所有象限都可能出现）
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.protocol.oacp import BlueprintMessage, DamageType, Priority, SignalMessage
from src.models.plasticity import PlasticityEvaluator, RepairPlan, ScoredPlan
from .quadrant import Quadrant, QuadrantClassification, QuadrantClassifier


class DecisionType(Enum):
    """决策类型"""
    IMMEDIATE = "immediate"           # 立即执行
    SCHEDULED = "scheduled"           # 规划执行
    DELEGATED = "delegated"           # 委托执行
    DEFERRED = "deferred"             # 延迟处理
    ELIMINATED = "eliminated"         # 删除/忽略
    ESCALATED = "escalated"           # 升级人工
    MONITOR = "monitor"               # 持续监控


@dataclass
class Decision:
    """
    决策结果
    
    包含决策类型、选择的方案、执行建议等。
    """
    decision_id: str
    decision_type: DecisionType
    quadrant: Quadrant
    priority: Priority
    reasoning: str
    
    # 选择的方案（如果有多个可选方案）
    selected_plan: Optional[RepairPlan] = None
    alternative_plans: List[RepairPlan] = field(default_factory=list)
    plan_score: float = 0.0
    
    # 执行建议
    recommended_actions: List[str] = field(default_factory=list)
    estimated_duration: str = "unknown"
    resource_requirements: Dict[str, str] = field(default_factory=dict)
    
    # 元数据
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    confidence: float = 0.0
    requires_human_approval: bool = False
    escalation_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "decision_id": self.decision_id,
            "decision_type": self.decision_type.value,
            "quadrant": self.quadrant.value,
            "quadrant_label": self.quadrant.label,
            "priority": self.priority.value,
            "reasoning": self.reasoning,
            "selected_plan": self.selected_plan.name if self.selected_plan else None,
            "plan_score": self.plan_score,
            "recommended_actions": self.recommended_actions,
            "estimated_duration": self.estimated_duration,
            "confidence": self.confidence,
            "requires_human_approval": self.requires_human_approval,
            "escalation_reason": self.escalation_reason,
        }


class PlasticityMatrix:
    """
    可塑性决策矩阵
    
    整合四象限分类和可塑性评估，做出最优决策。
    这是 Plasticus（可塑性）的核心决策组件。
    
    工作流程：
    1. 接收感知结果或损伤信号
    2. 使用 QuadrantClassifier 分类
    3. 根据象限决定决策策略
    4. 如果需要修复，生成/评估方案
    5. 输出决策结果
    
    使用：
        matrix = PlasticityMatrix()
        
        # 从感知结果决策
        decision = matrix.decide_from_perception(perception_result)
        
        # 从信号决策
        decision = matrix.decide_from_signal(signal_message)
    """
    
    def __init__(
        self,
        quadrant_classifier: Optional[QuadrantClassifier] = None,
        plasticity_evaluator: Optional[PlasticityEvaluator] = None,
        auto_escalate_threshold: float = 0.5,
    ):
        """
        Args:
            quadrant_classifier: 四象限分类器
            plasticity_evaluator: 可塑性评估器
            auto_escalate_threshold: 自动升级人工的阈值（方案最高分低于此值时升级）
        """
        self.classifier = quadrant_classifier or QuadrantClassifier()
        self.evaluator = plasticity_evaluator or PlasticityEvaluator()
        self.auto_escalate_threshold = auto_escalate_threshold
        self._decision_counter = 0
    
    def _next_decision_id(self) -> str:
        """生成下一个决策 ID"""
        self._decision_counter += 1
        return f"DEC-{self._decision_counter:04d}"
    
    def assess(
        self,
        health_score: float = 1.0,
        pain_level: int = 0,
        damage_type: str = "",
        has_data_loss_risk: bool = False,
        has_security_risk: bool = False,
    ) -> QuadrantClassification:
        """
        评估任务的象限分类
        
        Args:
            health_score: 健康度
            pain_level: 疼痛等级
            damage_type: 损伤类型
            has_data_loss_risk: 数据丢失风险
            has_security_risk: 安全风险
            
        Returns:
            象限分类结果
        """
        return self.classifier.classify(
            health_score=health_score,
            pain_level=pain_level,
            damage_type=damage_type,
            has_data_loss_risk=has_data_loss_risk,
            has_security_risk=has_security_risk,
        )
    
    def decide_from_classification(
        self,
        classification: QuadrantClassification,
        available_plans: Optional[List[RepairPlan]] = None,
    ) -> Decision:
        """
        根据象限分类做出决策
        
        Args:
            classification: 象限分类结果
            available_plans: 可选的修复方案列表
            
        Returns:
            决策结果
        """
        quadrant = classification.quadrant
        
        # 根据象限决定决策类型
        decision_type, reasoning = self._quadrant_decision(quadrant)
        
        # 选择方案（如果有）
        selected_plan = None
        plan_score = 0.0
        alternatives = []
        
        if available_plans and decision_type in (
            DecisionType.IMMEDIATE, DecisionType.SCHEDULED, DecisionType.DELEGATED
        ):
            scored = self.evaluator.evaluate_plans(available_plans)
            
            if scored:
                selected_plan = scored[0].plan
                plan_score = scored[0].score
                alternatives = [sp.plan for sp in scored[1:]]
                
                # 检查是否需要升级
                if plan_score < self.auto_escalate_threshold:
                    decision_type = DecisionType.ESCALATED
                    reasoning += f"; 最高方案得分 {plan_score:.2f} < {self.auto_escalate_threshold}，升级人工"
        
        # 生成推荐行动
        recommended_actions = self._generate_actions(
            decision_type, quadrant, selected_plan
        )
        
        # 估算持续时间
        estimated_duration = self._estimate_duration(decision_type, selected_plan)
        
        # 是否需要人工审批
        requires_approval = (
            decision_type == DecisionType.ESCALATED or
            quadrant == Quadrant.Q1_IMPORTANT_URGENT
        )
        
        return Decision(
            decision_id=self._next_decision_id(),
            decision_type=decision_type,
            quadrant=quadrant,
            priority=quadrant.to_priority(),
            reasoning=reasoning,
            selected_plan=selected_plan,
            alternative_plans=alternatives,
            plan_score=plan_score,
            recommended_actions=recommended_actions,
            estimated_duration=estimated_duration,
            confidence=classification.confidence,
            requires_human_approval=requires_approval,
        )
    
    def decide(
        self,
        health_score: float = 1.0,
        pain_level: int = 0,
        damage_type: str = "",
        available_plans: Optional[List[RepairPlan]] = None,
        has_data_loss_risk: bool = False,
        has_security_risk: bool = False,
    ) -> Decision:
        """
        便捷方法：评估 + 决策（一步完成）
        
        Args:
            health_score: 健康度
            pain_level: 疼痛等级
            damage_type: 损伤类型
            available_plans: 可选的修复方案
            has_data_loss_risk: 数据丢失风险
            has_security_risk: 安全风险
            
        Returns:
            决策结果
        """
        classification = self.assess(
            health_score=health_score,
            pain_level=pain_level,
            damage_type=damage_type,
            has_data_loss_risk=has_data_loss_risk,
            has_security_risk=has_security_risk,
        )
        
        return self.decide_from_classification(classification, available_plans)
    
    def _quadrant_decision(self, quadrant: Quadrant) -> tuple:
        """根据象限确定决策类型和理由"""
        decisions = {
            Quadrant.Q1_IMPORTANT_URGENT: (
                DecisionType.IMMEDIATE,
                f"第一象限（{quadrant.label}）：{quadrant.description}"
            ),
            Quadrant.Q2_IMPORTANT_NOT_URGENT: (
                DecisionType.SCHEDULED,
                f"第二象限（{quadrant.label}）：{quadrant.description}"
            ),
            Quadrant.Q3_NOT_IMPORTANT_URGENT: (
                DecisionType.DELEGATED,
                f"第三象限（{quadrant.label}）：{quadrant.description}"
            ),
            Quadrant.Q4_NOT_IMPORTANT_NOT_URGENT: (
                DecisionType.DEFERRED,
                f"第四象限（{quadrant.label}）：{quadrant.description}"
            ),
        }
        return decisions[quadrant]
    
    def _generate_actions(
        self,
        decision_type: DecisionType,
        quadrant: Quadrant,
        plan: Optional[RepairPlan],
    ) -> List[str]:
        """生成推荐行动"""
        actions = []
        
        # 基于决策类型
        type_actions = {
            DecisionType.IMMEDIATE: [
                "立即启动修复流程",
                "通知相关团队成员",
                "设置监控和回滚机制",
            ],
            DecisionType.SCHEDULED: [
                "添加到修复计划队列",
                "分配适当的资源和时间",
                "设定里程碑和检查点",
            ],
            DecisionType.DELEGATED: [
                "评估是否可以自动化处理",
                "批量处理类似问题",
                "考虑委托给合适的工具/Agent",
            ],
            DecisionType.DEFERRED: [
                "记录问题但暂不处理",
                "定期重新评估优先级",
                "如果长期无价值则考虑删除",
            ],
            DecisionType.ELIMINATED: [
                "标记为非必要",
                "从待办列表中移除",
            ],
            DecisionType.ESCALATED: [
                "创建人工审核请求",
                "准备详细的问题报告",
                "等待人工决策",
            ],
            DecisionType.MONITOR: [
                "设置监控指标",
                "设定告警阈值",
                "定期检查趋势",
            ],
        }
        
        actions.extend(type_actions.get(decision_type, []))
        
        # 如果有方案，添加方案相关行动
        if plan:
            for step in plan.steps:
                actions.append(f"执行: {step.get('action', step)}")
        
        return actions
    
    def _estimate_duration(
        self,
        decision_type: DecisionType,
        plan: Optional[RepairPlan],
    ) -> str:
        """估算持续时间"""
        if plan and plan.steps:
            step_count = len(plan.steps)
            if decision_type == DecisionType.IMMEDIATE:
                return f"~{step_count * 2}-{step_count * 5} 分钟"
            elif decision_type == DecisionType.SCHEDULED:
                return f"~{step_count * 15}-{step_count * 30} 分钟"
            else:
                return f"~{step_count * 10}-{step_count * 20} 分钟"
        
        durations = {
            DecisionType.IMMEDIATE: "~5-15 分钟",
            DecisionType.SCHEDULED: "~1-4 小时",
            DecisionType.DELEGATED: "~30 分钟-1 小时",
            DecisionType.DEFERRED: "下次迭代",
            DecisionType.ELIMINATED: "N/A",
            DecisionType.ESCALATED: "等待人工响应（通常 1-24 小时）",
            DecisionType.MONITOR: "持续监控",
        }
        return durations.get(decision_type, "unknown")
