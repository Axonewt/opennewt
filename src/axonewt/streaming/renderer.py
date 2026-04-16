"""
Axonewt Stream Renderer — 流式输出渲染器
==========================================
"""

import sys
import io
import time
from typing import Optional, Callable, Any
from dataclasses import dataclass, field


@dataclass
class RenderConfig:
    """渲染配置"""
    show_timestamps: bool = True
    show_tool_calls: bool = True
    show_thinking: bool = True
    rich_theme: str = "monokai"
    max_output_width: int = 120


class StreamingRenderer:
    """
    流式渲染器 — 边想边说，不是等全部生成完再输出
    """

    def __init__(self, config: Optional[RenderConfig] = None):
        self.config = config or RenderConfig()
        self._buffer = ""
        self._tool_call_depth = 0
        self._last_line = ""

    # ── 工具调用显示 ─────────────────────────────────

    def tool_start(self, tool_name: str, params: dict) -> None:
        """工具开始调用"""
        if not self.config.show_tool_calls:
            return
        indent = "  " * self._tool_call_depth
        param_preview = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(params.items())[:3])
        print(f"{indent}🔧 → {tool_name}({param_preview})", flush=True)

    def tool_result(self, tool_name: str, result: Any, error: Optional[str] = None) -> None:
        """工具返回结果"""
        if not self.config.show_tool_calls:
            return
        indent = "  " * self._tool_call_depth
        if error:
            print(f"{indent}  ❌ {error[:80]}", flush=True)
        else:
            preview = str(result)[:60] if result else "无返回"
            print(f"{indent}  ✅ {preview}", flush=True)

    def tool_depth_up(self) -> None:
        self._tool_call_depth += 1

    def tool_depth_down(self) -> None:
        self._tool_call_depth = max(0, self._tool_call_depth - 1)

    # ── 思考状态 ─────────────────────────────────────

    def thinking(self, message: str) -> None:
        """显示思考状态"""
        if not self.config.show_thinking:
            return
        print(f"💭 {message}", flush=True)

    def agent_speak(self, role: str, content: str) -> None:
        """Agent 说话"""
        prefix = "🤖" if role == "assistant" else "📝"
        if len(content) > 200:
            content = content[:200] + "..."
        print(f"{prefix} [{role}] {content}", flush=True)

    # ── 进度显示 ─────────────────────────────────────

    def progress_start(self, task_id: str, description: str) -> None:
        """开始进度任务"""
        print(f"📊 {task_id}: {description}", flush=True)

    def progress_update(self, task_id: str, current: int, total: int) -> None:
        """更新进度"""
        pct = current / total * 100 if total > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"\r📊 [{bar}] {pct:.0f}% ({current}/{total})", end="", flush=True)

    def progress_done(self, task_id: str) -> None:
        """进度完成"""
        print(f"\r✅ {task_id} 完成", flush=True)

    # ── 错误和警告 ───────────────────────────────────

    def error(self, message: str) -> None:
        print(f"❌ 错误: {message}", flush=True, file=sys.stderr)

    def warning(self, message: str) -> None:
        print(f"⚠️  警告: {message}", flush=True)

    def success(self, message: str) -> None:
        print(f"✅ {message}", flush=True)

    # ── 分隔线 ───────────────────────────────────────

    def divider(self, char: str = "─", width: int = 60) -> None:
        print(char * width, flush=True)


class ConsoleManager:
    """控制台管理器 — 统一管理所有输出"""

    def __init__(self, renderer: Optional[StreamingRenderer] = None):
        self.renderer = renderer or StreamingRenderer()

    def capture_output(self, func: Callable) -> str:
        """捕获函数的标准输出"""
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        try:
            func()
        finally:
            sys.stdout = old_stdout
        return buffer.getvalue()

    def with_spinner(self, message: str, func: Callable[[], Any]) -> Any:
        """带 Spinner 的执行"""
        chars = "|/-\\"
        import threading
        result = [None]
        done = [False]

        def spin():
            i = 0
            while not done[0]:
                print(f"\r{chars[i % 4]} {message}...", end="", flush=True)
                time.sleep(0.1)
                i += 1

        t = threading.Thread(target=spin)
        t.start()
        try:
            result[0] = func()
        finally:
            done[0] = True
            t.join()
            print(f"\r✅ {message} 完成", flush=True)
        return result[0]
