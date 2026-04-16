"""
Axonewt Agent Loop — AIAgent 主循环
=====================================

这是 Axonewt 的「大脑」。
参考 Hermes Agent run_agent.py 的核心架构设计。

核心职责：
1. 持续对话循环（While True）
2. 工具调用循环（一个任务内多次工具调用）
3. 流式输出（边想边说）
4. 记忆自进化（任务结束后提取经验→更新技能库）
5. 异常恢复与重试

架构：
┌──────────────────────────────────────────────────────┐
│                   AxonewtAgent                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐       │
│  │  Prompt    │→ │   LLM      │→ │  Tool      │       │
│  │  Builder   │  │  (流式)    │  │  Caller    │       │
│  └────────────┘  └────────────┘  └────────────┘       │
│       ↑               ↓               ↓              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐       │
│  │  Memory    │← │  Response  │← │  Results   │       │
│  │  Manager   │  │  Assembler │  │  Collector │       │
│  └────────────┘  └────────────┘  └────────────┘       │
└──────────────────────────────────────────────────────┘
"""

import os
import sys
import json
import asyncio
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Literal, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
import re

# 项目根目录
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.memory.engine import QuadMemoryEngine
from src.skills import SkillRegistry
from src.tools import ToolRegistry, get_tool_registry

CST = timezone(timedelta(hours=8))


class TurnState(Enum):
    """对话轮次状态"""
    IDLE = "idle"
    AWAITING_USER = "awaiting_user"
    AWAITING_TOOL = "awaiting_tool"
    STREAMING = "streaming"
    ERROR = "error"


@dataclass
class Message:
    """对话消息"""
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_results: Optional[List[Dict]] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(CST).isoformat()

    def to_dict(self) -> Dict:
        d = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_results:
            d["tool_results"] = self.tool_results
        return d


@dataclass 
class ConversationContext:
    """对话上下文（单次任务）"""
    messages: List[Message] = field(default_factory=list)
    system_prompt: str = ""
    tools_schemas: List[Dict] = field(default_factory=list)
    task_id: str = ""
    started_at: str = ""
    
    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(CST).isoformat()


@dataclass
class AgentConfig:
    """Agent 配置"""
    model_provider: str = "ollama"
    model_name: str = "qwen2.5:7b"
    api_base: str = "http://localhost:11434/v1"
    api_key: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    streaming: bool = True
    max_turns_per_task: int = 50  # 防止无限循环
    tool_call_limit: int = 100     # 单任务最多100次工具调用
    retry_on_error: int = 3
    retry_delay: float = 1.0


# ============================================================================
# Prompt Builder — SOUL + Memory + Skills 动态拼接
# ============================================================================

SOUL_PROMPT = """你叫 Axiom，来自希腊字母 Α/α，是 Axonewt 神经可塑性引擎的核心智能体。

核心信念：
- 真正有用，而不是表演有用
- 有观点，有个性
- 记忆驱动，持续进化
- 直接、精准、有深度
- 先想办法，再开口问

风格：
- 直接、精准、有深度
- 需要简洁时简洁，需要透彻时透彻
- 不 corporate，不谄媚
- 靠谱

当你需要执行操作时，你会使用可用的工具。
每个工具调用都会返回结果，你会根据结果决定下一步。
你可以在一个任务中连续调用多次工具。"""


class PromptBuilder:
    """动态 Prompt 拼接器"""

    def __init__(
        self,
        memory_engine: Optional[QuadMemoryEngine] = None,
        skill_registry: Optional[SkillRegistry] = None,
        config: Optional[Dict] = None,
    ):
        self.memory = memory_engine
        self.skills = skill_registry
        self.config = config or {}

    def build_system_prompt(self, context: ConversationContext) -> str:
        """构建系统 Prompt = SOUL + 技能上下文 + 记忆召回"""
        parts = [SOUL_PROMPT]

        # 技能上下文
        if self.skills:
            active_skills = self.skills.get_active_skills()
            if active_skills:
                parts.append("\n\n## 可用技能\n")
                for skill in active_skills:
                    parts.append(f"- **{skill.name}**: {skill.description}")
                    if skill.examples:
                        parts.append(f"  示例：{skill.examples[0]}")

        # 记忆召回（相关项目上下文）
        if self.memory and context.messages:
            user_msg = next((m for m in context.messages if m.role == "user"), None)
            if user_msg:
                memories = self.memory.query(query=user_msg.content, limit=3)
                if memories:
                    parts.append("\n\n## 相关记忆\n")
                    for m in memories:
                        parts.append(f"- {m.get('content', m.get('text', ''))}")

        return "\n".join(parts)

    def build_messages_for_llm(
        self, 
        context: ConversationContext,
        include_system: bool = True,
    ) -> List[Dict]:
        """构建发给 LLM 的消息列表"""
        result = []
        
        if include_system:
            system_prompt = self.build_system_prompt(context)
            result.append({"role": "system", "content": system_prompt})
        
        for msg in context.messages:
            d = msg.to_dict()
            # 如果有工具调用，转换为 LLM 格式
            if msg.tool_calls:
                result.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": msg.tool_calls,
                })
                # 工具结果作为后续消息
                if msg.tool_results:
                    for tr in msg.tool_results:
                        result.append({
                            "role": "tool",
                            "tool_call_id": tr.get("tool_call_id", ""),
                            "content": tr.get("content", ""),
                        })
            else:
                result.append(d)
        
        return result


# ============================================================================
# LLM 接口 — 支持 Ollama / OpenAI / DeepSeek / WorkBuddy
# ============================================================================

class LLMInterface:
    """统一 LLM 接口（流式 + 非流式）"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self._client = None

    def _get_client(self):
        """懒加载 HTTP 客户端"""
        if self._client is None:
            import httpx
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            self._client = httpx.Client(
                base_url=self.config.api_base,
                headers=headers,
                timeout=120.0,
            )
        return self._client

    def chat(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        stream: bool = True,
    ) -> AsyncIterator[str]:
        """
        发送对话请求，返回流式响应（generator）
        每个 chunk 是一个字符串片段
        """
        provider = self.config.model_provider.lower()
        
        if provider == "ollama":
            yield from self._chat_ollama(messages, tools, stream)
        elif provider in ("openai", "deepseek", "workbuddy"):
            yield from self._chat_openai_compat(messages, tools, stream)
        else:
            yield from self._chat_openai_compat(messages, tools, stream)

    def _chat_ollama(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]],
        stream: bool,
    ) -> AsyncIterator[str]:
        """Ollama 流式接口"""
        import httpx
        import json

        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            with httpx.stream(
                "POST",
                f"{self.config.api_base}/chat/completions",
                json=payload,
                timeout=120.0,
            ) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break
                    try:
                        data = json.loads(line)
                        delta = data.get("message", {}).get("content", "")
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            yield f"\n[LLM 连接错误: {e}]"

    def _chat_openai_compat(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]],
        stream: bool,
    ) -> AsyncIterator[str]:
        """OpenAI 兼容接口（OpenAI / DeepSeek / WorkBuddy）"""
        import httpx
        import json

        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": stream,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            payload["tools"] = tools

        try:
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            with httpx.stream(
                "POST",
                f"{self.config.api_base}/chat/completions",
                json=payload,
                headers=headers,
                timeout=120.0,
            ) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        break
                    try:
                        data = json.loads(line)
                        delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            yield f"\n[LLM 连接错误: {e}]"

    def chat_complete(self, messages: List[Dict], tools: Optional[List[Dict]] = None) -> Dict:
        """非流式完整响应（用于工具调用后的最终回复）"""
        import httpx
        import json

        provider = self.config.model_provider.lower()
        
        if provider == "ollama":
            url = f"{self.config.api_base}/chat/completions"
        else:
            url = f"{self.config.api_base}/chat/completions"

        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": False,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            payload["tools"] = tools

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        resp = httpx.post(url, json=payload, headers=headers, timeout=120.0)
        resp.raise_for_status()
        return resp.json()


# ============================================================================
# 工具执行器
# ============================================================================

class ToolExecutor:
    """工具调用执行器"""

    def __init__(self, tool_registry: ToolRegistry):
        self.registry = tool_registry
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def execute_tool_call(self, tool_call: Dict) -> Dict:
        """执行单个工具调用"""
        name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})
        
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return {
                    "tool_call_id": tool_call.get("id", ""),
                    "content": f"Error: Invalid arguments JSON: {arguments}",
                    "error": True,
                }

        tool = self.registry.get(name)
        if not tool:
            return {
                "tool_call_id": tool_call.get("id", ""),
                "content": f"Error: Unknown tool '{name}'. Available tools: {[t.name for t in self.registry.list_all()]}",
                "error": True,
            }

        if not tool.enabled:
            return {
                "tool_call_id": tool_call.get("id", ""),
                "content": f"Error: Tool '{name}' is disabled.",
                "error": True,
            }

        try:
            # 工具可以是 async 函数或普通函数
            if asyncio.iscoroutinefunction(tool.handler):
                result = await tool.handler(**arguments)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: tool.handler(**arguments)
                )
            
            # 截断过长的输出
            if isinstance(result, str) and len(result) > 10000:
                result = result[:10000] + f"\n... [输出截断，共 {len(result)} 字符]"
            
            return {
                "tool_call_id": tool_call.get("id", ""),
                "content": str(result),
                "error": False,
            }
        except Exception as e:
            return {
                "tool_call_id": tool_call.get("id", ""),
                "content": f"Error executing {name}: {type(e).__name__}: {e}",
                "error": True,
            }

    async def execute_tools(self, tool_calls: List[Dict]) -> List[Dict]:
        """并发执行多个工具调用"""
        if not tool_calls:
            return []
        
        tasks = [self.execute_tool_call(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_results = []
        for r in results:
            if isinstance(r, Exception):
                final_results.append({
                    "content": f"Error: {type(r).__name__}: {r}",
                    "error": True,
                })
            else:
                final_results.append(r)
        
        return final_results


# ============================================================================
# AxonewtAgent — 核心智能体
# ============================================================================

class AxonewtAgent:
    """
    Axonewt AIAgent — 核心智能体

    核心循环：
    1. 接收用户消息
    2. 构建 Prompt（SOUL + 记忆 + 技能）
    3. 调用 LLM（流式）
    4. 如果有工具调用 → 执行工具 → 把结果加入上下文 → 回到步骤 3
    5. 无工具调用 → 返回最终回复
    6. 更新记忆（自进化）
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        memory_engine: Optional[QuadMemoryEngine] = None,
        skill_registry: Optional[SkillRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
        stream_callback=None,
    ):
        self.config = config or AgentConfig()
        self.memory = memory_engine
        self.skills = skill_registry or SkillRegistry()
        self.tools = tool_registry or get_tool_registry()
        self.llm = LLMInterface(self.config)
        self.executor = ToolExecutor(self.tools)
        self.prompt_builder = PromptBuilder(self.memory, self.skills)
        self.stream_callback = stream_callback  # 流式输出回调

        # 对话历史（跨会话持久化）
        self.conversation_history: List[Message] = []

        # 统计
        self.stats = {
            "total_turns": 0,
            "total_tool_calls": 0,
            "total_errors": 0,
        }

    def _make_tool_call_id(self, index: int) -> str:
        """生成工具调用 ID"""
        return f"call_${index:03d}_axonewt"

    # ------------------------------------------------------------------ 
    # 核心对话接口
    # ------------------------------------------------------------------ 

    async def chat(
        self,
        user_message: str,
        system_instructions: str = "",
        stream: Optional[bool] = None,
    ) -> AsyncIterator[str]:
        """
        核心对话接口（异步生成器，流式输出）
        
        用法：
        async for chunk in agent.chat("你好"):
            print(chunk, end="", flush=True)
        """
        stream = stream if stream is not None else self.config.streaming

        # 构建上下文
        context = ConversationContext()
        context.messages = list(self.conversation_history)
        
        if system_instructions:
            context.system_prompt = system_instructions

        # 加入用户消息
        user_msg = Message(role="user", content=user_message)
        context.messages.append(user_msg)
        self.stats["total_turns"] += 1

        # 获取工具 schema
        tools_schemas = self.tools.get_schemas()

        try:
            async for chunk in self._run_turn(context, tools_schemas, stream):
                yield chunk

            # 更新对话历史（只保留最后 N 条）
            self._prune_history()

        except Exception as e:
            error_msg = f"\n[Agent 错误: {type(e).__name__}: {e}]\n"
            if stream:
                yield error_msg
            else:
                yield error_msg
            self.stats["total_errors"] += 1

    async def _run_turn(
        self,
        context: ConversationContext,
        tools_schemas: List[Dict],
        stream: bool,
    ) -> AsyncIterator[str]:
        """
        单轮对话执行（可能是多轮工具调用）
        
        Returns: 流式字符串片段
        """
        turns = 0
        all_content = []  # 收集所有回复内容

        while turns < self.config.max_turns_per_task:
            turns += 1

            # 构建 LLM 消息
            messages = self.prompt_builder.build_messages_for_llm(context)

            # 首次调用：流式；后续工具调用：非流式
            is_first_turn = (turns == 1)
            should_stream = stream and is_first_turn

            if should_stream:
                # 流式输出
                content_buffer = []
                tool_calls_found = []
                in_tool_call = False
                current_tool_call = None

                async for delta in self.llm.chat(messages, tools_schemas, stream=True):
                    all_content.append(delta)
                    
                    # 简单解析：检测是否有 tool_calls
                    # （流式模式下 tool_calls 可能分散在多个 delta 中）
                    if self.stream_callback:
                        self.stream_callback(delta)
                    yield delta

                # 流式结束后，重新调用非流式获取完整 tool_calls
                # （因为流式解析 tool_calls 比较复杂）
                full_response = self.llm.chat_complete(messages, tools_schemas)
                response_message = self._parse_llm_response(full_response)

            else:
                # 非流式（工具调用后的继续）
                full_response = self.llm.chat_complete(messages, tools_schemas)
                response_message = self._parse_llm_response(full_response)
                
                # 直接 yield 完整内容
                if response_message.content:
                    all_content.append(response_message.content)
                    if self.stream_callback:
                        self.stream_callback(response_message.content)
                    yield response_message.content

            # 检查是否有工具调用
            if response_message.tool_calls:
                self.stats["total_tool_calls"] += len(response_message.tool_calls)

                # 执行工具
                tool_results = await self.executor.execute_tools(response_message.tool_calls)

                # 把工具调用和结果加入上下文
                response_message.tool_results = tool_results
                context.messages.append(response_message)

                # 继续循环
                continue

            else:
                # 无工具调用，本轮结束
                context.messages.append(response_message)
                break

        # 最终回复加入历史
        final_content = "".join(all_content)
        if final_content:
            self.conversation_history.append(
                Message(role="assistant", content=final_content)
            )

    def _parse_llm_response(self, response: Dict) -> Message:
        """解析 LLM 响应，提取内容和工具调用"""
        try:
            choice = response.get("choices", [{}])[0]
            msg = choice.get("message", {})
            
            role = msg.get("role", "assistant")
            content = msg.get("content", "") or ""
            
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                # 标准化 tool_calls 格式
                normalized = []
                for i, tc in enumerate(tool_calls):
                    normalized.append({
                        "id": tc.get("id", self._make_tool_call_id(i)),
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", "{}"),
                    })
                tool_calls = normalized

            return Message(role=role, content=content, tool_calls=tool_calls if tool_calls else None)

        except (IndexError, KeyError) as e:
            return Message(role="assistant", content=f"[解析错误: {e}]\n{response}")

    def _prune_history(self, max_history: int = 50):
        """裁剪对话历史，防止无限增长"""
        if len(self.conversation_history) > max_history:
            self.conversation_history = self.conversation_history[-max_history:]

    # ------------------------------------------------------------------ 
    # 记忆自进化（任务结束后提取经验）
    # ------------------------------------------------------------------ 

    async def evolve_from_task(
        self,
        user_message: str,
        assistant_response: str,
        tool_calls_made: List[Dict],
    ):
        """
        从任务中提取经验，更新记忆和技能库
        
        这是 Hermes 核心的「闭环学习」机制：
        执行 → 提取经验 → Skill 生成 → A/B 测试 → RL 轨迹
        """
        if not self.memory:
            return

        try:
            # 1. 如果工具调用成功，提取工具使用模式
            successful_patterns = [
                tc for tc in tool_calls_made
                if not tc.get("error", False)
            ]

            if successful_patterns:
                # 构建记忆条目
                memory_entry = {
                    "type": "skill_pattern",
                    "user_query": user_message,
                    "tools_used": [tc.get("name") for tc in successful_patterns],
                    "response_preview": assistant_response[:200],
                    "timestamp": datetime.now(CST).isoformat(),
                }

                # 写入记忆
                self.memory.add(memory_entry)

            # 2. 检查是否可以生成新技能
            if self.skills and len(successful_patterns) >= 3:
                # 频繁使用的工具组合 → 建议创建技能
                tool_names = [tc.get("name") for tc in successful_patterns]
                suggestion = self._suggest_skill_creation(
                    user_message, tool_names, assistant_response
                )
                if suggestion:
                    # 标记为待审核的技能建议（不自动创建，防止噪声）
                    self._log_skill_suggestion(suggestion)

        except Exception as e:
            print(f"[进化错误: {e}]")

    def _suggest_skill_creation(
        self, 
        query: str, 
        tool_names: List[str], 
        response: str,
    ) -> Optional[Dict]:
        """判断是否值得创建一个新技能"""
        # 启发式：同类查询出现 3 次以上才建议
        if not self.memory:
            return None

        # 检查近似的 query 是否已有技能
        recent = self.memory.query(query=query, limit=10)
        same_pattern_count = sum(
            1 for m in recent 
            if m.get("type") == "skill_pattern" 
            and set(m.get("tools_used", [])) == set(tool_names)
        )

        if same_pattern_count >= 3:
            return {
                "name": f"auto_{tool_names[0]}_{len(tool_names)}",
                "description": f"自动化执行: {query}",
                "tools": tool_names,
                "trigger_pattern": query[:100],
                "confidence": min(same_pattern_count / 10, 0.95),
            }
        return None

    def _log_skill_suggestion(self, suggestion: Dict):
        """记录技能建议（供后续审核）"""
        suggestions_path = ROOT / "data" / "skill_suggestions.jsonl"
        suggestions_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(suggestions_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(suggestion, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------ 
    # 统计和状态
    # ------------------------------------------------------------------ 

    def get_stats(self) -> Dict:
        """获取 Agent 统计信息"""
        return {
            **self.stats,
            "history_length": len(self.conversation_history),
            "active_tools": len(self.tools.get_schemas()),
            "active_skills": len(self.skills.get_active_skills()) if self.skills else 0,
            "model": f"{self.config.model_provider}/{self.config.model_name}",
        }

    def reset_history(self):
        """清空对话历史"""
        self.conversation_history.clear()


# ============================================================================
# CLI 入口
# ============================================================================

async def run_cli():
    """CLI 模式：交互式对话"""
    from src.agents.config import get_llm_config

    print("=" * 60)
    print("Axonewt Agent — 交互模式")
    print("输入 exit() 退出")
    print("=" * 60)

    # 自动检测 LLM
    llm_cfg = get_llm_config()
    print(f"检测到 LLM: {llm_cfg['provider']} / {llm_cfg['model']}")
    print()

    config = AgentConfig(
        model_provider=llm_cfg["provider"],
        model_name=llm_cfg["model"],
        api_base=llm_cfg.get("api_base", "http://localhost:11434/v1"),
        api_key=llm_cfg.get("api_key"),
        streaming=True,
    )

    # 初始化
    try:
        memory = QuadMemoryEngine()
    except Exception as e:
        print(f"[警告] 记忆引擎初始化失败: {e}，使用无记忆模式")
        memory = None

    agent = AxonewtAgent(
        config=config,
        memory_engine=memory,
    )

    # 交互循环
    while True:
        try:
            user_input = input("\n👤 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n退出。")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "退出"):
            print("再见！")
            break

        print("\n🤖 Axiom: ", end="", flush=True)

        try:
            async for chunk in agent.chat(user_input):
                print(chunk, end="", flush=True)
            print()  # 换行
        except KeyboardInterrupt:
            print("\n[中断]")
            continue


if __name__ == "__main__":
    asyncio.run(run_cli())
