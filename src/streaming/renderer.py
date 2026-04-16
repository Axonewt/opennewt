"""
Streaming Renderer — 流式输出渲染器

功能:
- 实时显示 AI 思考过程（逐字输出）
- 工具调用状态卡片
- 进度条和 Spinner
- 错误高亮
- Markdown 渲染
"""

import sys
import time
import re
from typing import Optional

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.markdown import Markdown
    from rich.live import Live
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class ToolCallTracker:
    """工具调用追踪器"""

    def __init__(self):
        self.active: dict[str, dict] = {}
        self.completed: list[dict] = []
        self.failed: list[dict] = []

    def start(self, tool_id: str, name: str, args: dict):
        self.active[tool_id] = {
            "name": name,
            "args": args,
            "started_at": time.time(),
        }

    def finish(self, tool_id: str, result: str = ""):
        if tool_id in self.active:
            entry = self.active.pop(tool_id)
            entry["duration"] = time.time() - entry["started_at"]
            entry["result"] = result[:100] if result else ""
            self.completed.append(entry)

    def fail(self, tool_id: str, error: str):
        if tool_id in self.active:
            entry = self.active.pop(tool_id)
            entry["duration"] = time.time() - entry["started_at"]
            entry["error"] = error
            self.failed.append(entry)

    @property
    def stats(self) -> dict:
        return {
            "active": len(self.active),
            "completed": len(self.completed),
            "failed": len(self.failed),
        }


class StreamingRenderer:
    """
    流式渲染器

    使用 Rich 库实现:
    - Markdown 实时渲染
    - 工具调用卡片
    - 进度条
    - 错误高亮
    """

    def __init__(self, console: Optional["Console"] = None, use_rich: bool = True):
        if not RICH_AVAILABLE:
            self._console = None
            self._use_rich = False
            return
        self._console = console or Console(color_system="256")
        self._use_rich = use_rich and RICH_AVAILABLE
        self._tracker = ToolCallTracker()
        self._thinking_buffer = ""
        self._buffer = ""

    # ── 公共 API ────────────────────────────────────────────

    def print(self, text: str, style: str = ""):
        """打印普通文本"""
        if self._use_rich and self._console:
            if style:
                self._console.print(text, style=style)
            else:
                self._console.print(text)
        else:
            print(text, file=sys.stdout)

    def print_markdown(self, text: str):
        """渲染 Markdown"""
        if self._use_rich and self._console:
            md = Markdown(text)
            self._console.print(md)
        else:
            print(text)

    def print_panel(self, title: str, content: str, border_style: str = "blue"):
        """打印面板"""
        if self._use_rich and self._console:
            panel = Panel(content, title=title, border_style=border_style)
            self._console.print(panel)
        else:
            print(f"=== {title} ===\n{content}")

    def print_code(self, code: str, language: str = "python"):
        """打印代码块"""
        if self._use_rich and self._console:
            syntax = Syntax(code, language, theme="monokai", line_numbers=True)
            self._console.print(syntax)
        else:
            print(f"```{language}\n{code}\n```")

    def print_error(self, text: str):
        """打印错误（红色高亮）"""
        self.print(f"[red]❌ {text}[/red]")

    def print_success(self, text: str):
        """打印成功（绿色）"""
        self.print(f"[green]✅ {text}[/green]")

    def print_warning(self, text: str):
        """打印警告（黄色）"""
        self.print(f"[yellow]⚠️ {text}[/yellow]")

    def print_info(self, text: str):
        """打印信息（蓝色）"""
        self.print(f"[blue]ℹ️ {text}[/blue]")

    def stream_thinking(self, text: str):
        """流式输出思考内容"""
        self._thinking_buffer += text
        if self._use_rich and self._console:
            self._console.print(text, end="", style="dim italic")
        else:
            sys.stdout.write(text)
            sys.stdout.flush()

    def flush_thinking(self):
        """结束当前思考流"""
        self._thinking_buffer = ""

    def start_tool(self, tool_id: str, name: str, args: dict):
        """开始工具调用"""
        self._tracker.start(tool_id, name, args)
        if self._use_rich and self._console:
            arg_preview = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(args.items())[:3])
            self._console.print(
                f"[dim]🔧 {name}({arg_preview})[/dim]", end=""
            )
        else:
            print(f"  → {name}(...)")

    def finish_tool(self, tool_id: str, result_preview: str = ""):
        """结束工具调用"""
        self._tracker.finish(tool_id, result_preview)
        if self._use_rich and self._console:
            self._console.print(" [green]✓[/green]")
        else:
            print(" [OK]")

    def fail_tool(self, tool_id: str, error: str):
        """工具调用失败"""
        self._tracker.fail(tool_id, error)
        if self._use_rich and self._console:
            self._console.print(f" [red]✗ {error[:50]}[/red]")
        else:
            print(f" [FAIL] {error[:50]}")

    def print_tool_summary(self):
        """打印工具调用汇总"""
        stats = self._tracker.stats
        completed = stats["completed"]
        failed = stats["failed"]
        total_time = sum(e["duration"] for e in self._tracker.completed)

        if self._use_rich and self._console:
            table = Table(title="工具调用汇总")
            table.add_column("状态", style="cyan")
            table.add_column("数量", style="white")
            table.add_row("完成", f"[green]{completed}[/green]")
            table.add_row("失败", f"[red]{failed}[/red]")
            table.add_row("总耗时", f"{total_time:.2f}s")
            self._console.print(table)
        else:
            print(f"\n--- 工具汇总: 完成={completed} 失败={failed} 总耗时={total_time:.2f}s ---")

    def progress_context(self, description: str):
        """进度条上下文"""
        if self._use_rich and self._console:
            return Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TimeElapsedColumn(),
                console=self._console,
            )
        return None

    def rule(self, title: str = ""):
        """分隔线"""
        if self._use_rich and self._console:
            self._console.rule(title)
        else:
            print(f"\n{'='*60}\n{title}\n{'='*60}\n")
