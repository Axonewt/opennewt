"""
Quadrant - 四象限分类
=====================

实现四象限决策模型（艾森豪威尔矩阵）：

              紧急程度
           低 ←────────────→ 高
         ┌────────────┬────────────┐
    高   │  第二象限    │  第一象限    │
  重     │  战略投资    │  危机干预    │
  要     │  IMPORTANT_ | IMPORTANT_
    性   │  NOT_URGENT | URGENT     |
         ├────────────┼────────────┤
    低   │  第四象限    │  第三象限    │
         │  研究探索    │  执行优化    │
         │  NOT_IMPORT | NOT_IMPORT
         │  _NOT_URGENT| ANT_URGENT
         └────────────┴────────────┘

与 OACP 协议的映射：
- 第一象限 → Priority.P0（危机干预，立即处理）
- 第二象限 → Priority.P1（战略投资，规划执行）
- 第三象限 → Priority.P2（执行优化，批量处理）
- 第四象限 → Priority.P2（研究探索，闲暇时处理）
"""

from dataclasses import dataclass
from enum import Enum

from src.protocol.oacp import Priority


class Importance(Enum):
    """重要性"""
    HIGH = "high"         # 高重要性
    LOW = "low"           # 低重要性


class Urgency(Enum):
    """紧急程度"""
    HIGH = "high"         # 高紧急度
    LOW = "low"           # 低紧急度


class Quadrant(Enum):
    """四象限"""
    Q1_IMPORTANT_URGENT = "Q1"              # 第一象限：重要+紧急 → 危机干预
    Q2_IMPORTANT_NOT_URGENT = "Q2"          # 第二象限：重要+不紧急 → 战略投资
    Q3_NOT_IMPORTANT_URGENT = "Q3"          # 第三象限：不重要+紧急 → 执行优化
    Q4_NOT_IMPORTANT_NOT_URGENT = "Q4"      # 第四象限：不重要+不紧急 → 研究探索
    
    @property
    def label(self) -> str:
        """象限标签"""
        labels = {
            Quadrant.Q1_IMPORTANT_URGENT: "危机干预",
            Quadrant.Q2_IMPORTANT_NOT_URGENT: "战略投资",
            Quadrant.Q3_NOT_IMPORTANT_URGENT: "执行优化",
            Quadrant.Q4_NOT_IMPORTANT_NOT_URGENT: "研究探索",
        }
        return labels[self]
    
    @property
    def description(self) -> str:
        """象限描述"""
        descriptions = {
            Quadrant.Q1_IMPORTANT_URGENT: "重要且紧急，立即处理（火灾）",
            Quadrant.Q2_IMPORTANT_NOT_URGENT: "重要但不紧急，规划执行（投资）",
            Quadrant.Q3_NOT_IMPORTANT_URGENT: "不重要但紧急，批量处理或委托",
            Quadrant.Q4_NOT_IMPORTANT_NOT_URGENT: "不重要且不紧急，果断删除或研究",
        }
        return descriptions[self]
    
    @property
    def recommended_action(self) -> str:
        """推荐行动"""
        actions = {
            Quadrant.Q1_IMPORTANT_URGENT: "立即处理（DO FIRST）",
            Quadrant.Q2_IMPORTANT_NOT_URGENT: "规划执行（SCHEDULE）",
            Quadrant.Q3_NOT_IMPORTANT_URGENT: "委托或批量处理（DELEGATE）",
            Quadrant.Q4_NOT_IMPORTANT_NOT_URGENT: "删除或研究（ELIMINATE/RESEARCH）",
        }
        return actions[self]
    
    @property
    def color_code(self) -> str:
        """颜色代码（用于 UI 展示）"""
        colors = {
            Quadrant.Q1_IMPORTANT_URGENT: "RED",        # 红色：危险
            Quadrant.Q2_IMPORTANT_NOT_URGENT: "BLUE",    # 蓝色：重要
            Quadrant.Q3_NOT_IMPORTANT_URGENT: "YELLOW",  # 黄色：警告
            Quadrant.Q4_NOT_IMPORTANT_NOT_URGENT: "GRAY", # 灰色：低优先级
        }
        return colors[self]
    
    def to_priority(self) -> Priority:
        """映射到 OACP 优先级"""
        mapping = {
            Quadrant.Q1_IMPORTANT_URGENT: Priority.P0,
            Quadrant.Q2_IMPORTANT_NOT_URGENT: Priority.P1,
            Quadrant.Q3_NOT_IMPORTANT_URGENT: Priority.P2,
            Quadrant.Q4_NOT_IMPORTANT_NOT_URGENT: Priority.P2,
        }
        return mapping[self]
    
    @classmethod
    def from_importance_urgency(
        cls, importance: Importance, urgency: Urgency
    ) -> 'Quadrant':
        """从重要性和紧急度确定象限"""
        if importance == Importance.HIGH and urgency == Urgency.HIGH:
            return cls.Q1_IMPORTANT_URGENT
        elif importance == Importance.HIGH and urgency == Urgency.LOW:
            return cls.Q2_IMPORTANT_NOT_URGENT
        elif importance == Importance.LOW and urgency == Urgency.HIGH:
            return cls.Q3_NOT_IMPORTANT_URGENT
        else:
            return cls.Q4_NOT_IMPORTANT_NOT_URGENT


@dataclass
class QuadrantClassification:
    """
    象限分类结果
    
    包含分类结果和评分依据。
    """
    quadrant: Quadrant
    importance: Importance
    urgency: Urgency
    importance_score: float      # 0-1 重要性评分
    urgency_score: float         # 0-1 紧急度评分
    confidence: float            # 0-1 分类置信度
    reasoning: str               # 分类理由


class QuadrantClassifier:
    """
    四象限分类器
    
    根据任务/信号的特征，自动判断其属于哪个象限。
    
    分类规则：
    - 第一象限（重要+紧急）：
      * 健康度 < 0.5（系统濒临崩溃）
      * P0 级疼痛信号
      * 数据丢失风险
      * 安全漏洞被利用
    
    - 第二象限（重要+不紧急）：
      * 健康度 0.5-0.7（亚健康但有缓冲）
      * P1 级疼痛信号
      * 架构改进需求
      * 性能优化机会
    
    - 第三象限（不重要+紧急）：
      * 依赖版本过时
      * 代码风格问题
      * 文档不完整
      * 警告信息过多
    
    - 第四象限（不重要+不紧急）：
      * 纯研究性探索
      * 可选的代码美化
      * 未来可能需要的功能
    """
    
    # 重要性阈值
    IMPORTANCE_HIGH_THRESHOLD = 0.6
    URGENCY_HIGH_THRESHOLD = 0.6
    
    def classify(
        self,
        health_score: float = 1.0,
        pain_level: int = 0,
        damage_type: str = "",
        has_data_loss_risk: bool = False,
        has_security_risk: bool = False,
        custom_importance: float = None,
        custom_urgency: float = None,
    ) -> QuadrantClassification:
        """
        分类任务到四象限
        
        Args:
            health_score: 健康度（0-1）
            pain_level: 疼痛等级（0-4）
            damage_type: 损伤类型
            has_data_loss_risk: 是否有数据丢失风险
            has_security_risk: 是否有安全风险
            custom_importance: 自定义重要性（如果提供，覆盖自动评估）
            custom_urgency: 自定义紧急度（如果提供，覆盖自动评估）
            
        Returns:
            象限分类结果
        """
        # 计算重要性
        if custom_importance is not None:
            importance_score = custom_importance
        else:
            importance_score = self._assess_importance(
                health_score, pain_level, damage_type,
                has_data_loss_risk, has_security_risk
            )
        
        # 计算紧急度
        if custom_urgency is not None:
            urgency_score = custom_urgency
        else:
            urgency_score = self._assess_urgency(
                health_score, pain_level, damage_type,
                has_data_loss_risk, has_security_risk
            )
        
        # 确定象限
        importance = (
            Importance.HIGH if importance_score >= self.IMPORTANCE_HIGH_THRESHOLD
            else Importance.LOW
        )
        urgency = (
            Urgency.HIGH if urgency_score >= self.URGENCY_HIGH_THRESHOLD
            else Urgency.LOW
        )
        
        quadrant = Quadrant.from_importance_urgency(importance, urgency)
        
        # 生成理由
        reasoning = self._generate_reasoning(
            quadrant, importance_score, urgency_score,
            health_score, pain_level, damage_type
        )
        
        # 置信度
        confidence = self._calculate_confidence(importance_score, urgency_score)
        
        return QuadrantClassification(
            quadrant=quadrant,
            importance=importance,
            urgency=urgency,
            importance_score=round(importance_score, 3),
            urgency_score=round(urgency_score, 3),
            confidence=round(confidence, 3),
            reasoning=reasoning,
        )
    
    def _assess_importance(
        self,
        health_score: float,
        pain_level: int,
        damage_type: str,
        has_data_loss_risk: bool,
        has_security_risk: bool,
    ) -> float:
        """评估重要性（0-1）"""
        score = 0.0
        
        # 健康度影响（越低越重要）
        if health_score < 0.5:
            score += 0.4
        elif health_score < 0.7:
            score += 0.25
        elif health_score < 0.85:
            score += 0.1
        
        # 疼痛等级影响
        if pain_level >= 4:  # CRITICAL
            score += 0.4
        elif pain_level >= 3:  # SEVERE
            score += 0.3
        elif pain_level >= 2:  # MODERATE
            score += 0.15
        elif pain_level >= 1:  # MILD
            score += 0.05
        
        # 损伤类型影响
        critical_types = {"资源泄漏", "延迟异常", "依赖腐化"}
        if damage_type in critical_types:
            score += 0.15
        
        # 特殊风险
        if has_data_loss_risk:
            score += 0.2
        if has_security_risk:
            score += 0.2
        
        return min(1.0, score)
    
    def _assess_urgency(
        self,
        health_score: float,
        pain_level: int,
        damage_type: str,
        has_data_loss_risk: bool,
        has_security_risk: bool,
    ) -> float:
        """评估紧急度（0-1）"""
        score = 0.0
        
        # 健康度紧急度（越低越紧急）
        if health_score < 0.5:
            score += 0.35
        elif health_score < 0.6:
            score += 0.25
        elif health_score < 0.7:
            score += 0.15
        
        # 疼痛等级影响
        if pain_level >= 4:
            score += 0.35
        elif pain_level >= 3:
            score += 0.25
        elif pain_level >= 2:
            score += 0.1
        
        # 损伤类型影响
        urgent_types = {"延迟异常", "资源泄漏", "行为漂移"}
        if damage_type in urgent_types:
            score += 0.2
        
        # 特殊紧急情况
        if has_data_loss_risk:
            score += 0.25
        if has_security_risk:
            score += 0.3
        
        return min(1.0, score)
    
    def _generate_reasoning(
        self,
        quadrant: Quadrant,
        importance_score: float,
        urgency_score: float,
        health_score: float,
        pain_level: int,
        damage_type: str,
    ) -> str:
        """生成分类理由"""
        parts = []
        
        if health_score < 0.7:
            parts.append(f"健康度 {health_score:.2f} 低于阈值 0.7")
        
        if pain_level >= 3:
            parts.append(f"疼痛等级 {pain_level}（严重）")
        
        if damage_type:
            parts.append(f"损伤类型: {damage_type}")
        
        parts.append(f"重要性: {importance_score:.2f}, 紧急度: {urgency_score:.2f}")
        parts.append(f"归入 {quadrant.value}: {quadrant.label}")
        
        return "; ".join(parts)
    
    def _calculate_confidence(self, importance_score: float, urgency_score: float) -> float:
        """计算分类置信度"""
        # 如果重要性和紧急度分数都远离阈值（0.5），则置信度高
        importance_distance = abs(importance_score - 0.5)
        urgency_distance = abs(urgency_score - 0.5)
        
        avg_distance = (importance_distance + urgency_distance) / 2
        # 0 距离 = 0.5 置信度, 0.5 距离 = 1.0 置信度
        return 0.5 + avg_distance
