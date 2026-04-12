"""
第三层：SessionCache（会话缓存）
================================

核心设计原则：
- 会话中的临时信息，不跨会话持久化
- 自动压缩：当缓存超过阈值时触发蒸馏
- 蒸馏算法：提炼精华到 MEMORY.md（第一层）
- 支持多轮对话的上下文保持

功能：
1. 缓存会话中的关键交互
2. 基于重要性评分的自动压缩
3. 蒸馏到第一层索引
4. 滑动窗口管理

生命周期：
- 创建于会话开始
- 随着对话增长
- 达到阈值后压缩/蒸馏
- 关键内容提升至 L1（MEMORY.md）
- 临时内容在会话结束后丢弃
"""

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import OrderedDict


CST = timezone(timedelta(hours=8))

# 缓存约束
DEFAULT_MAX_CACHE_ENTRIES = 500       # 最大条目数
DEFAULT_MAX_CACHE_BYTES = 2 * 1024 * 1024  # 2MB
COMPRESSION_THRESHOLD_RATIO = 0.8     # 80% 容量时触发压缩
DISTILL_MIN_IMPORTANCE = 0.6          # 最低蒸馏分数


@dataclass
class CacheEntry:
    """会话缓存条目"""
    entry_id: str = ""
    role: str = ""            # user | assistant | system | tool | reflection
    content: str = ""
    summary: str = ""         # 压缩后的摘要
    importance_score: float = 0.5   # 重要性评分 [0.0, 1.0]
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    token_estimate: int = 0   # 预估 token 数
    compressed: bool = False  # 是否已压缩
    distilled: bool = False   # 是否已蒸馏到 L1
    
    def to_dict(self) -> Dict:
        return {
            "entry_id": self.entry_id,
            "role": self.role,
            "content": self.content[:500],  # 截断长内容
            "summary": self.summary,
            "importance_score": self.importance_score,
            "tags": self.tags,
            "timestamp": self.timestamp,
            "token_estimate": self.token_estimate,
            "compressed": self.compressed,
            "distilled": self.distilled,
        }


class ImportanceScorer:
    """
    重要性评分器
    
    基于启发式规则评估一条缓存条目的重要性。
    
    评分维度：
    - 用户显式标记的关键信息（+高权重）
    - 包含决策、修复、错误等关键词（+中权重）
    - 工具调用和结果（+低权重，除非出错）
    - 反思/总结类内容（+高权重）
    - 重复或闲聊（-权重）
    """
    
    # 高价值关键词
    HIGH_VALUE_PATTERNS = [
        r"(?i)(决定|decision|选择|choose|确定|confirm)",
        r"(?i)(修复|fix|bug|error|错误|失败|fail)",
        r"(?i)(重要|important|关键|critical|核心)",
        r"(?i)(学|learned|洞察|insight|经验|lesson)",
        r"(?i)(架构|architecture|设计|design|重构|refactor)",
        r"(?i)(用户偏好|preference|习惯|convention)",
    ]
    
    # 低价值关键词（降权）
    LOW_VALUE_PATTERNS = [
        r"^(好的|ok|嗯|是的|yes|no|thanks?)\s*[.!]*$",
        r"^(\[.*?\]\s*){3,}$",  # 纯工具输出
        r"^(正在处理|processing|working on it)\s*[.!]*$",
    ]
    
    @classmethod
    def score(cls, role: str, content: str, tags: List[str] = None) -> float:
        """
        计算条目重要性分数
        
        Args:
            role: 角色 (user|assistant|system|tool|reflection)
            content: 内容文本
            tags: 标签列表
            
        Returns:
            重要性评分 [0.0, 1.0]
        """
        import re
        
        score = 0.5  # 基础分
        
        # 角色基础分调整
        role_weights = {
            "user": 0.55,
            "assistant": 0.45,
            "system": 0.30,
            "tool": 0.35,
            "reflection": 0.80,  # 反思类最高优先
        }
        score += role_weights.get(role, 0.4) * 0.15
        
        # 高价值模式匹配
        import re as _re
        for pattern in cls.HIGH_VALUE_PATTERNS:
            if _re.search(pattern, content):
                score += 0.12
        
        # 低价值模式匹配（降权）
        for pattern in cls.LOW_VALUE_PATTERNS:
            if _re.match(pattern, content.strip()):
                score -= 0.20
        
        # 标签加权
        if tags:
            high_value_tags = {"decision", "bug-fix", "preference", "insight", "critical"}
            for tag in tags:
                if tag.lower() in high_value_tags:
                    score += 0.10
        
        # 内容长度因素（适中的长度通常更有价值）
        content_len = len(content)
        if 50 <= content_len <= 1000:
            score += 0.05  # 中等长度加分
        elif content_len > 3000:
            score -= 0.05  # 过长的可能是日志
        
        # 最终裁剪到 [0.0, 1.0]
        return max(0.0, min(1.0, score))
    
    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """粗略估算 token 数（中文约 1.5 字符/token，英文约 4 字符/token）"""
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)


class DistillationEngine:
    """
    蒸馏引擎
    
    从会话缓存中提炼精华内容，生成适合写入 MEMORY.md 的格式。
    
    蒸馏策略：
    1. 选择重要性 > threshold 的未蒸馏条目
    2. 合并相似主题的条目
    3. 提取结构化记忆（决策、偏好、教训等）
    4. 输出为 MEMORY.md 兼容格式
    """
    
    @staticmethod
    def distill(
        entries: List[CacheEntry],
        min_importance: float = DISTILL_MIN_IMPORTANCE,
    ) -> List[Dict]:
        """
        执行蒸馏操作
        
        Args:
            entries: 待蒸馏的缓存条目列表
            min_importance: 最低重要性阈值
            
        Returns:
            蒸馏后的记忆字典列表（可直接写入 MEMORY.md）
        """
        candidates = [
            e for e in entries
            if not e.distilled and e.importance_score >= min_importance
        ]
        
        if not candidates:
            return []
        
        # 按主题分组
        groups = DistillationEngine._group_by_topic(candidates)
        
        memories = []
        
        for topic, group_entries in groups.items():
            # 取该组最重要的条目作为代表
            primary = max(group_entries, key=lambda x: x.importance_score)
            
            # 判断类别
            category = DistillationEngine._categorize(primary.role, primary.tags)
            
            # 生成摘要
            summary = DistillationEngine._generate_summary(group_entries)
            
            memory = {
                "category": category,
                "title": topic[:80],
                "content": summary,
                "tags": list(set(
                    t for e in group_entries for t in e.tags
                )) or ["auto-distilled"],
                "source_entries": [e.entry_id for e in group_entries],
                "distilled_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M"),
                "original_scores": [e.importance_score for e in group_entries],
            }
            
            memories.append(memory)
        
        return memories
    
    @staticmethod
    def _group_by_topic(entries: List[CacheEntry]) -> Dict[str, List[CacheEntry]]:
        """按主题分组（基于标签和内容关键词）"""
        import re
        
        groups = OrderedDict()
        
        for entry in entries:
            # 尝试从标签提取主题
            if entry.tags:
                topic = entry.tags[0]
            else:
                # 从内容提取前几个词作为主题
                words = re.findall(r'[\u4e00-\u9fff\w]{2,6}', entry.content)[:3]
                topic = " ".join(words) if words else "misc"
            
            if topic not in groups:
                groups[topic] = []
            groups[topic].append(entry)
        
        return groups
    
    @staticmethod
    def _categorize(role: str, tags: List[str]) -> str:
        """判断记忆类别"""
        tag_set = set(t.lower() for t in tags) if tags else set()
        
        if "decision" in tag_set or "决定" in tag_set:
            return "项目决策"
        if "preference" in tag_set or "偏好" in tag_set or "习惯" in tag_set:
            return "用户偏好"
        if "bug-fix" in tag_set or "修复" in tag_set or "错误" in tag_set:
            return "技术修复"
        if "insight" in tag_set or "洞察" in tag_set or "经验" in tag_set:
            return "深度学习"
        if role == "reflection":
            return "反思记录"
        
        return "工作笔记"
    
    @staticmethod
    def _generate_summary(entries: List[CacheEntry]) -> str:
        """从一组相关条目生成综合摘要"""
        # 按时间排序
        sorted_entries = sorted(entries, key=lambda x: x.timestamp)
        
        parts = []
        seen_content = set()
        
        for entry in sorted_entries:
            # 使用摘要（如果已压缩），否则截取内容
            text = entry.summary if entry.compressed else entry.content
            
            # 去重
            content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                
                if len(text) > 300:
                    text = text[:300] + "..."
                
                parts.append("- {}: {}".format(entry.role, text))
        
        return "\n".join(parts)


class SessionCache:
    """
    第三层：会话缓存
    
    职责：
    - 存储当前会话的所有关键交互
    - 管理缓存容量
    - 触发自动压缩和蒸馏
    - 与第一层（MemoryIndex）对接进行蒸馏
    """
    
    def __init__(
        self,
        session_id: str = None,
        max_entries: int = DEFAULT_MAX_CACHE_ENTRIES,
        max_bytes: int = DEFAULT_MAX_CACHE_BYTES,
    ):
        """
        初始化会话缓存
        
        Args:
            session_id: 会话唯一 ID
            max_entries: 最大条目数
            max_bytes: 最大字节数
        """
        self.session_id = session_id or SessionCache._generate_session_id()
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        
        # 有序存储（插入顺序 = 时间顺序）
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        
        # 统计
        self._total_tokens = 0
        self._compression_count = 0
        self._distillation_count = 0
        
        print("[SessionCache] Initialized: {} (max={}, {}KB)".format(
            self.session_id, max_entries, max_bytes // 1024
        ))
    
    @staticmethod
    def _generate_session_id() -> str:
        return "SESSION-{}".format(datetime.now(CST).strftime("%Y%m%d%H%M%S"))
    
    def add(
        self,
        role: str,
        content: str,
        tags: List[str] = None,
        metadata: Dict = None,
    ) -> CacheEntry:
        """
        添加新的缓存条目
        
        当容量接近阈值时自动触发压缩。
        
        Args:
            role: 角色类型
            content: 内容文本
            tags: 标签列表
            metadata: 额外元数据
            
        Returns:
            创建的 CacheEntry
        """
        entry_id = "CE-{}-{}".format(
            self.session_id,
            len(self._entries) + 1
        )
        
        now = datetime.now(CST).isoformat()
        
        # 计算重要性分数
        importance = ImportanceScorer.score(role, content, tags)
        
        # 估算 token 数
        token_estimate = ImportanceScorer.estimate_tokens(content)
        
        entry = CacheEntry(
            entry_id=entry_id,
            role=role,
            content=content,
            importance_score=importance,
            tags=tags or [],
            metadata=metadata or {},
            timestamp=now,
            token_estimate=token_estimate,
        )
        
        self._entries[entry_id] = entry
        self._total_tokens += token_estimate
        
        # 检查容量并自动压缩
        self._check_capacity()
        
        return entry
    
    def get(self, entry_id: str) -> Optional[CacheEntry]:
        """获取指定缓存条目"""
        return self._entries.get(entry_id)
    
    def get_recent(self, count: int = 10) -> List[CacheEntry]:
        """获取最近的 N 条缓存"""
        items = list(self._entries.values())
        return items[-count:] if count > 0 else items[-count:]
    
    def query(self, keywords: List[str], limit: int = 10) -> List[CacheEntry]:
        """
        在当前会话缓存中查询
        
        Args:
            keywords: 关键词列表
            limit: 返回上限
            
        Returns:
            匹配的缓存条目
        """
        scored = []
        
        for entry in self._values():
            searchable = "{} {} {}".format(
                entry.role, entry.content, " ".join(entry.tags)
            ).lower()
            
            score = 0.0
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in searchable:
                    score += 1.0
                if kw_lower in (entry.summary or "").lower():
                    score += 0.5
            
            if score > 0:
                scored.append((score, entry))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]
    
    def compress(self, target_ratio: float = 0.5):
        """
        压缩缓存（保留重要条目，压缩低优先级条目）
        
        Args:
            target_ratio: 目标压缩比例（保留比例）
        """
        entries_list = list(self._entries.values())
        
        if len(entries_list) < 10:
            return  # 太少不需要压缩
        
        # 按重要性排序
        entries_list.sort(key=lambda x: x.importance_score, reverse=True)
        
        # 保留 top target_ratio 的完整内容
        keep_count = max(int(len(entries_list) * target_ratio), 10)
        keep_ids = {e.entry_id for e in entries_list[:keep_count]}
        
        compressed_count = 0
        
        for entry in entries_list[keep_count:]:
            if not entry.compressed:
                # 压缩：用摘要替换原始内容
                entry.summary = entry.content[:200].replace("\n", " ")
                if len(entry.content) > 200:
                    entry.summary += "..."
                entry.compressed = True
                compressed_count += 1
        
        self._compression_count += compressed_count
        
        print("[SessionCache] Compressed {} entries (kept {} full)".format(
            compressed_count, keep_count
        ))
    
    def distill(self) -> List[Dict]:
        """
        执行蒸馏：将高价值内容提炼为长期记忆格式
        
        Returns:
            可写入 MEMORY.md 的记忆字典列表
        """
        all_entries = list(self._entries.values())
        
        memories = DistillationEngine.distill(all_entries)
        
        # 标记已蒸馏
        for memory in memories:
            for eid in memory.get("source_entries", []):
                if eid in self._entries:
                    self._entries[eid].distilled = True
        
        self._distillation_count += len(memories)
        
        print("[SessionCache] Distilled {} memories from {} cache entries".format(
            len(memories), len(all_entries)
        ))
        
        return memories
    
    def _check_capacity(self):
        """检查容量并自动触发压缩"""
        current_size = sum(
            len(e.content.encode("utf-8")) for e in self._entries.values()
        )
        
        # 条件1：条目数超限
        entry_ratio = len(self._entries) / self.max_entries
        # 条件2：字节大小超限
        byte_ratio = current_size / self.max_bytes
        
        if max(entry_ratio, byte_ratio) >= COMPRESSION_THRESHOLD_RATIO:
            self.compress(target_ratio=0.6)
    
    def get_context_window(self, max_tokens: int = 4000) -> str:
        """
        获取适合放入上下文窗口的缓存摘要
        
        策略：优先展示高重要性、最近的条目
        
        Args:
            max_tokens: 最大 token 数限制
            
        Returns:
            格式化的摘要文本
        """
        entries = list(self._entries.values())
        
        # 按重要性 + 时间排序（最近的高重要性优先）
        entries.sort(key=lambda x: (
            x.importance_score,
            x.timestamp
        ), reverse=True)
        
        lines = ["# Session Cache ({})".format(self.session_id)]
        lines.append("")
        
        total_tokens = 0
        
        for entry in entries:
            # 已蒸馏的跳过（已经进入长期记忆）
            if entry.distilled:
                continue
            
            # 选择显示内容
            display_text = entry.summary if entry.compressed else entry.content
            
            if len(display_text) > 400:
                display_text = display_text[:400] + "..."
            
            entry_tokens = ImportanceScorer.estimate_tokens(
                "[{}] {}: {}".format(entry.role, entry.entry_id, display_text)
            )
            
            if total_tokens + entry_tokens > max_tokens:
                lines.append("\n... ({} more entries truncated)".format(
                    len(entries) - len(lines) + 2
                ))
                break
            
            freshness = "✅" if entry.importance_score > 0.6 else "📝"
            lines.append("{} **[{}]** {}: {}".format(
                freshness, entry.role.upper(), 
                entry.timestamp[11:19],  # 只要时分秒
                display_text
            ))
            
            total_tokens += entry_tokens
        
        return "\n".join(lines)
    
    def clear(self):
        """清空缓存"""
        self._entries.clear()
        self._total_tokens = 0
        print("[SessionCache] Cleared")
    
    def _values(self):
        return self._entries.values()
    
    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total_size = sum(len(e.content.encode("utf-8")) for e in self._values())
        compressed = sum(1 for e in self._values() if e.compressed)
        distilled = sum(1 for e in self._values() if e.distilled)
        
        return {
            "session_id": self.session_id,
            "total_entries": len(self._entries),
            "total_tokens": self._total_tokens,
            "total_bytes": total_size,
            "compressed_entries": compressed,
            "distilled_entries": distilled,
            "compression_count": self._compression_count,
            "distillation_count": self._distillation_count,
            "capacity_ratio": len(self._entries) / self.max_entries if self.max_entries else 0,
        }
