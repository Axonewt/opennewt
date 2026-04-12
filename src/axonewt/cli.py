"""
Axonewt CLI - 命令行入口
参考 Hermes Agent 的 CLI 设计
"""
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="axonewt",
    help="🦎 Axonewt Engine - 火蜥蜴再生 AI Agent",
)
console = Console()


@app.command()
def start():
    """启动 Axonewt 对话"""
    console.print("[bold green]🦎[/bold green] Axonewt Engine 启动中...")
    # TODO: 集成主程序
    console.print("[yellow]⚠️ 主程序集成中...[/yellow]")


@app.command("doctor")
def doctor():
    """自检安装环境"""
    console.print("[bold cyan]🩺[/bold cyan] Axonewt 自检")
    console.print("")

    table = Table(title="环境检查")
    table.add_column("检查项", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("详情")

    # 检查 Python
    import sys
    python_ok = sys.version_info >= (3, 11)
    table.add_row("Python", "✅" if python_ok else "❌", f"{sys.version}")

    # 检查 LLM (Ollama)
    import httpx
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            models = response.json().get("models", [])
            llm_status = "✅ 可用" if models else "⚠️ 未安装模型"
            llm_detail = ", ".join([m["name"] for m in models[:3]]) if models else "运行 'ollama pull qwen2.5:7b'"
        else:
            llm_status = "❌ 不可用"
            llm_detail = f"HTTP {response.status_code}"
    except Exception as e:
        llm_status = "❌ 未运行"
        llm_detail = "运行 'ollama serve' 启动"

    table.add_row("LLM (Ollama)", llm_status, llm_detail)

    # 检查依赖
    deps = [
        ("typer", "✅" if "typer" in dir() else "❌"),
        ("rich", "✅" if "rich" in dir() else "❌"),
        ("httpx", "✅" if "httpx" in dir() else "❌"),
    ]

    # 打印表格
    console.print(table)

    # 建议
    console.print("")
    console.print("[bold]建议操作:[/bold]")
    console.print("  1. 安装 Ollama: curl -fsSL https://ollama.ai/install.sh | sh")
    console.print("  2. 下载模型: ollama pull qwen2.5:7b")
    console.print("  3. 运行 'axonewt' 启动")


@app.command("scan")
def scan(path: str = "."):
    """扫描项目健康度"""
    console.print(f"[bold cyan]🔍[/bold cyan] 扫描 {path}")
    # TODO: 集成 Soma 感知层
    console.print("[yellow]⚠️ Soma 感知层集成中...[/yellow]")


def main():
    """CLI 入口"""
    app()


if __name__ == "__main__":
    main()
