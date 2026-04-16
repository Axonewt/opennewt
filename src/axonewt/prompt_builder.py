"""
Axonewt Prompt Builder — 升级版
=================================

参考 Claude Code 的三层记忆系统和 Hermes Agent 的 Prompt Builder。

核心能力：
1. SOUL.md 动态加载 — 从文件加载灵魂定义，而非硬编码
2. 记忆新鲜度标签 — >1天的记忆自动加 ⚠️ 过期警告
3. 上下文窗口管理 — Token 计数 + 自动裁剪
4. 技能上下文注入 — 按查询匹配相关技能
5. 工具 Schema 注入 — 按任务类型筛选相关工具
6. 对话历史管理 — 滑动窗口 + 重要消息优先保留
7. 多 Provider 适配 — 适配不同 LLM 的 context window 大小

架构：
┌──────────────────────────────────────────────────┐
│                PromptBuilder                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ SOUL.md  │ │  Memory  │ │ Active Skills    │  │
│  │ (动态)   │ │ (召回)   │ │ (匹配注入)       │  │
│  └──────────┘ └──────────┘ └──────────────────┘  │
│       ↓           ↓              ↓               │
│  ┌──────────────────────────────────────────────┐ │
│  │          Context Window Manager              │ │
│  │  (Token 计数 + 自动裁剪 + 优先级排序)        │ │
│  └──────────────────────────────────────────────┘ │
│                     ↓                             │
│  ┌──────────────────────────────────────────────┐ │
│  │         Final Prompt Assembly                 │ │
│  │  [System] + [Tools] + [Memory] + [History]   │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
"""

import os
import re
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

CST = timezone(timedelta(hours=8))

# ============================================================================
# 常量定义
# ============================================================================

# 各 LLM 的上下文窗口大小（tokens）
CONTEXT_WINDOWS = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16384,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "qwen2.5:7b": 32768,
    "qwen2.5:14b": 32768,
    "qwen2.5:32b": 32768,
    "qwen2.5:72b": 32768,
    "qwen2:72b": 32768,
    "deepseek-chat": 64000,
    "deepseek-coder": 64000,
    "default": 8192,
}

# Token 估算：中文约 1.5 char/token，英文约 4 char/token
CHARS_PER_TOKEN_ZH = 1.5
CHARS_PER_TOKEN_EN = 4.0


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class PromptSection:
    """Prompt 中的一个片段"""
    name: str
    content: str
    priority: int = 5  # 1=最高（不可裁剪），10=最低（优先裁剪）
    token_estimate: int = 0
    stale: bool = False  # 记忆新鲜度标记

    def __post_init__(self):
        if not self.token_estimate:
            self.token_estimate = estimate_tokens(self.content)


@dataclass
class MemoryContext:
    """记忆上下文条目"""
    content: str
    source: str  # "daily", "longterm", "session", "graph"
    timestamp: str = ""
    relevance_score: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(CST).isoformat()


# ============================================================================
# Token 估算
# ============================================================================

def estimate_tokens(text: str) -> int:
    """
    估算文本的 Token 数
    
    不使用 tiktoken（避免额外依赖），用启发式估算。
    """
    if not text:
        return 0
    
    # 统计中文字符数
    zh_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - zh_chars
    
    tokens = int(zh_chars / CHARS_PER_TOKEN_ZH) + int(other_chars / CHARS_PER_TOKEN_EN)
    return max(tokens, 1)


def estimate_tokens_messages(messages: List[Dict]) -> int:
    """估算消息列表的总 Token 数"""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        total += estimate_tokens(content)
        # 每条消息的 overhead（role + formatting）
        total += 4
    return total


# ============================================================================
# 记忆新鲜度
# ============================================================================

def check_memory_freshness(timestamp_str: str) -> Tuple[bool, Optional[str]]:
    """
    检查记忆新鲜度
    
    Returns:
        (is_fresh, warning_label)
        - is_fresh: True=≤1天, False=>1天
        - warning_label: 如 "⚠️ 2天前" 或 None
    """
    try:
        if not timestamp_str:
            return True, None
        
        # 解析时间戳
        ts = timestamp_str.replace("T", " ").replace("+08:00", "")
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            # 尝试其他格式
            for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]:
                try:
                    dt = datetime.strptime(ts.strip(), fmt)
                    break
                except ValueError:
                    continue
            else:
                return True, None

        now = datetime.now(CST)
        # 如果没有时区信息，假设是本地时间
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=CST)

        delta = now - dt
        days = delta.total_seconds() / 86400

        if days <= 1:
            return True, None
        elif days < 7:
            return False, f"⚠️ {int(days)}天前"
        elif days < 30:
            return False, f"⚠️ {int(days)}天前"
        else:
            return False, f"⚠️ {int(days/30)}个月前"
    except Exception:
        return True, None


# ============================================================================
# Prompt Builder — 升级版
# ============================================================================

class PromptBuilder:
    """
    升级版 Prompt 拼接器
    
    核心改进：
    - SOUL.md 从文件动态加载
    - 记忆新鲜度检测
    - Token 计数和上下文窗口管理
    - 技能按相关性注入
    - 对话历史智能裁剪
    """

    def __init__(
        self,
        soul_path: Optional[str] = None,
        memory_engine=None,
        skill_registry=None,
        max_context_tokens: int = 0,
        model_name: str = "default",
    ):
        self.soul_path = Path(soul_path) if soul_path else None
        self.memory = memory_engine
        self.skills = skill_registry
        self.max_context_tokens = max_context_tokens or CONTEXT_WINDOWS.get(model_name, 8192)
        self.model_name = model_name
        
        # 缓存 SOUL.md 内容
        self._soul_content: Optional[str] = None
        self._soul_mtime: float = 0
        self._soul_tokens: int = 0

    # ---------------------------------------------------------------
    # SOUL.md 加载
    # ---------------------------------------------------------------

    def load_soul(self) -> str:
        """加载 SOUL.md 内容（带缓存和热重载）"""
        if not self.soul_path or not self.soul_path.exists():
            return self._default_soul()

        # 检查文件是否被修改
        mtime = self.soul_path.stat().st_mtime
        if self._soul_content is None or mtime > self._soul_mtime:
            try:
                self._soul_content = self.soul_path.read_text(encoding="utf-8")
                self._soul_mtime = mtime
                self._soul_tokens = estimate_tokens(self._soul_content)
            except Exception:
                self._soul_content = self._default_soul()

        return self._soul_content

    def _default_soul(self) -> str:
        """默认 SOUL（当文件不存在时）"""
        return """你叫 Axiom，来自希腊字母 Α/α，是 Axonewt 神经可塑性引擎的核心智能体。

核心信念：
- 真正有用，而不是表演有用
- 有观点，有个性
- 记忆驱动，持续进化
- 直接、精准、有深度

风格：直接、精准、有深度。需要简洁时简洁，需要透彻时透彻。"""

    # ---------------------------------------------------------------
    # 记忆召回
    # ---------------------------------------------------------------

    def recall_memories(self, query: str, limit: int = 5) -> List[MemoryContext]:
        """召回相关记忆（带新鲜度标注）"""
        if not self.memory:
            return []

        results = []
        
        try:
            memories = self.memory.query(query=query, limit=limit)
            for m in memories:
                content = m.get("content", m.get("text", ""))
                if not content:
                    continue
                
                timestamp = m.get("timestamp", m.get("created_at", ""))
                is_fresh, warning = check_memory_freshness(timestamp)
                
                # 组装记忆条目
                display = content
                if warning:
                    display = f"{warning} {content}"
                
                results.append(MemoryContext(
                    content=display,
                    source=m.get("source", "unknown"),
                    timestamp=timestamp,
                    relevance_score=m.get("relevance", m.get("score", 0.5)),
                ))
        except Exception as e:
            # 记忆召回失败不应阻断主流程
            results.append(MemoryContext(
                content=f"[记忆召回错误: {e}]",
                source="error",
            ))

        return results

    # ---------------------------------------------------------------
    # 技能匹配
    # ---------------------------------------------------------------

    def match_skills(self, query: str) -> List[Dict]:
        """匹配相关技能"""
        if not self.skills:
            return []

        matched = self.skills.find(query)
        results = []
        for skill in matched:
            info = {
                "name": skill.name,
                "description": skill.description,
            }
            if hasattr(skill, "examples") and skill.examples:
                info["examples"] = skill.examples
            if hasattr(skill, "metadata") and isinstance(skill.metadata, dict):
                body = skill.metadata.get("body", "")
                if body:
                    # 截断过长的 body
                    if len(body) > 500:
                        body = body[:500] + "..."
                    info["instructions"] = body
            results.append(info)
        return results[:3]  # 最多注入3个技能

    # ---------------------------------------------------------------
    # 核心：构建完整 Prompt
    # ---------------------------------------------------------------

    def build_system_prompt(self, query: str = "") -> str:
        """构建系统 Prompt"""
        sections = []

        # 1. SOUL（最高优先级，不可裁剪）
        soul = self.load_soul()
        sections.append(PromptSection(name="soul", content=soul, priority=1))

        # 2. 当前日期时间（低 token 成本，高实用性）
        now_str = datetime.now(CST).strftime("%Y-%m-%d %H:%M %A")
        sections.append(PromptSection(
            name="datetime",
            content=f"当前时间: {now_str} (CST/UTC+8)",
            priority=1,
        ))

        # 3. 技能上下文（中等优先级）
        skills_info = self.match_skills(query)
        if skills_info:
            skill_text = "## 可用技能\n"
            for s in skills_info:
                skill_text += f"\n### {s['name']}\n{s['description']}"
                if s.get("examples"):
                    skill_text += f"\n示例: {s['examples'][0]}"
                if s.get("instructions"):
                    skill_text += f"\n{s['instructions']}"
            sections.append(PromptSection(name="skills", content=skill_text, priority=3))

        # 4. 记忆召回（中等优先级，可部分裁剪）
        if query:
            memories = self.recall_memories(query, limit=5)
            if memories:
                memory_text = "## 相关记忆\n"
                for m in memories:
                    source_tag = f"[{m.source}] " if m.source != "unknown" else ""
                    memory_text += f"\n- {source_tag}{m.content}"
                sections.append(PromptSection(name="memory", content=memory_text, priority=4))

        # 组装
        return "\n\n".join(s.content for s in sections)

    def build_messages(
        self,
        conversation_history: list,
        user_message: str = "",
        system_instructions: str = "",
        tools_schemas: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        构建发给 LLM 的完整消息列表
        
        自动管理上下文窗口：
        1. System prompt
        2. Tools schema
        3. 对话历史（智能裁剪）
        4. 当前用户消息
        """
        messages = []

        # 1. System prompt
        system_prompt = self.build_system_prompt(user_message)
        if system_instructions:
            system_prompt += f"\n\n## 用户指令\n{system_instructions}"
        messages.append({"role": "system", "content": system_prompt})

        # 计算 system prompt 占用的 token
        system_tokens = estimate_tokens_messages(messages)

        # 2. Tools schema（如果提供）
        if tools_schemas:
            tools_str = "## 可用工具\n"
            for tool in tools_schemas:
                tools_str += f"\n### {tool['name']}\n{tool['description']}"
                if tool.get("inputSchema", {}).get("properties"):
                    params = tool["inputSchema"]["properties"]
                    tools_str += "\n参数: " + ", ".join(params.keys())
            messages.append({"role": "system", "content": tools_str})
            system_tokens += estimate_tokens(tools_str)

        # 3. 对话历史（智能裁剪）
        available_tokens = self.max_context_tokens - system_tokens
        # 预留用户消息和回复空间
        available_tokens -= max(estimate_tokens(user_message) * 4, 1000)

        # 倒序遍历历史，优先保留最近的
        history = list(conversation_history)
        history.reverse()
        selected = []
        used_tokens = 0

        for msg in history:
            msg_dict = msg.to_dict() if hasattr(msg, "to_dict") else msg
            content = msg_dict.get("content", "")
            msg_tokens = estimate_tokens(content) + 8  # overhead

            if used_tokens + msg_tokens > available_tokens:
                break
            
            selected.append(msg_dict)
            used_tokens += msg_tokens

        selected.reverse()

        # 在开头添加裁剪提示（如果历史被裁剪了）
        if len(history) > len(selected) and len(history) > 0:
            messages.append({
                "role": "system",
                "content": f"[注意: 对话历史已裁剪，保留了最近的 {len(selected)}/{len(history)} 条消息]",
            })

        messages.extend(selected)

        # 4. 当前用户消息
        if user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    # ---------------------------------------------------------------
    # Token 统计
    # ---------------------------------------------------------------

    def count_tokens(self, messages: List[Dict]) -> Dict[str, int]:
        """统计消息列表的 Token 使用情况"""
        system_tokens = 0
        user_tokens = 0
        assistant_tokens = 0
        tool_tokens = 0
        total = 0

        for msg in messages:
            content = msg.get("content", "")
            tokens = estimate_tokens(content)
            total += tokens
            role = msg.get("role", "")
            if role == "system":
                system_tokens += tokens
            elif role == "user":
                user_tokens += tokens
            elif role == "assistant":
                assistant_tokens += tokens
            elif role == "tool":
                tool_tokens += tokens

        return {
            "total": total,
            "system": system_tokens,
            "user": user_tokens,
            "assistant": assistant_tokens,
            "tool": tool_tokens,
            "max_context": self.max_context_tokens,
            "utilization": f"{total / self.max_context_tokens * 100:.1f}%" if self.max_context_tokens > 0 else "N/A",
        }
