"""
Axonewt CLI - 火蜥蜴再生 AI Agent 命令行入口
============================================

完整 CLI，参考 Hermes Agent 设计：
- 交互式对话 /ask 模式
- 非交互扫描 /scan 模式
- 实时监控 /monitor 模式
- 记忆管理 /memory 模式
- 自检 /doctor 模式

用法:
    axonewt                    # 交互式对话
    axonewt ask "问题"         # 单次问答
    axonewt scan [path]        # 健康扫描
    axonewt monitor           # 实时监控
    axonewt memory             # 记忆管理
    axonewt doctor             # 环境自检
    axonewt repair             # 触发自愈
    axonewt model [name]      # 切换模型
    axonewt stats              # 查看统计
    axonewt log [n]           # 查看最近日志
"""

import sys
import os
import json
import time
import asyncio
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.syntax import Syntax
    from rich.markdown import Markdown
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

try:
    import typer
    HAS_TYPER = True
except ImportError:
    HAS_TYPER = False


console = Console()
app = typer.Typer(name="axonewt", help="🦎 Axonewt Engine - 火蜥蜴再生 AI Agent")


# ============================================================================
# 工具函数
# ============================================================================

def cprint(text: str, style: str = "white", **kwargs):
    """跨平台的彩色打印"""
    if HAS_RICH:
        console.print(text, style=style, **kwargs)
    else:
        print(text)


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🦎 Axonewt Engine  v0.3.0                            ║
║   火蜥蜴再生 AI Agent                                     ║
║   Neural Plasticity Engine                                ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""
    cprint(banner, "cyan")


def print_success(text: str):
    cprint(f"  ✅ {text}", "green")


def print_error(text: str):
    cprint(f"  ❌ {text}", "red")


def print_warning(text: str):
    cprint(f"  ⚠️  {text}", "yellow")


def print_info(text: str):
    cprint(f"  ℹ️  {text}", "blue")


def detect_llm() -> Dict[str, Any]:
    """自动检测可用的 LLM"""
    results = {}

    # 检查 Ollama
    try:
        if HAS_HTTPX:
            resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                results["ollama"] = {
                    "available": True,
                    "models": [m["name"] for m in models],
                    "default": models[0]["name"] if models else None
                }
            else:
                results["ollama"] = {"available": False, "error": f"HTTP {resp.status_code}"}
        else:
            results["ollama"] = {"available": False, "error": "httpx not installed"}
    except Exception as e:
        results["ollama"] = {"available": False, "error": str(e)}

    # 检查 OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        results["openai"] = {"available": True, "key_set": True}
    else:
        results["openai"] = {"available": False, "key_set": False}

    # 检查 DeepSeek
    ds_key = os.getenv("DEEPSEEK_API_KEY")
    if ds_key:
        results["deepseek"] = {"available": True, "key_set": True}
    else:
        results["deepseek"] = {"available": False, "key_set": False}

    return results


# ============================================================================
# /doctor - 环境自检
# ============================================================================

@app.command("doctor")
def doctor():
    """自检安装环境，诊断常见问题"""
    print_banner()
    cprint("\n🩺 Axonewt 环境自检\n", "bold cyan")

    issues_found = 0

    # Python 版本
    v = sys.version_info
    if v >= (3, 11):
        print_success(f"Python {v.major}.{v.minor}.{v.micro} ✅")
    else:
        print_error(f"Python {v.major}.{v.minor} ❌ (需要 3.11+)")
        issues_found += 1

    # 关键依赖
    deps = [
        ("httpx", HAS_HTTPX),
        ("rich", HAS_RICH),
        ("typer", HAS_TYPER),
        ("pydantic", True),
        ("fastapi", True),
        ("uvicorn", True),
        ("yaml", True),
    ]

    for name, ok in deps:
        try:
            __import__(name if name != "yaml" else "yaml")
            print_success(f"{name} ✅")
        except ImportError:
            print_error(f"{name} ❌ (pip install {name})")
            issues_found += 1

    # LLM 检测
    cprint("\n🔍 LLM 提供商检测\n", "bold cyan")
    llm_results = detect_llm()

    for provider, info in llm_results.items():
        if info.get("available"):
            models = info.get("models", [])
            default = info.get("default", "N/A")
            print_success(f"{provider}: 可用 (默认: {default})")
            if models:
                for m in models[:5]:
                    cprint(f"      - {m}", "white")
        else:
            reason = info.get("error") or info.get("key_set", "未设置 API Key")
            print_warning(f"{provider}: 不可用 ({reason})")

    # Ollama 模型详情
    if llm_results.get("ollama", {}).get("available"):
        ollama_info = llm_results["ollama"]
        models = ollama_info.get("models", [])
        if not models:
            print_warning("Ollama 运行中但未安装任何模型")
            print_info("运行 'ollama pull qwen2.5:7b' 下载模型")
            issues_found += 1
        else:
            print_success(f"已安装 {len(models)} 个模型")

    # 端口检测
    cprint("\n🌐 端口检测\n", "bold cyan")
    ports = [
        (5055, "Axonewt API Server"),
        (11434, "Ollama"),
    ]

    for port, name in ports:
        try:
            if HAS_HTTPX:
                resp = httpx.get(f"http://localhost:{port}/health", timeout=1)
                print_success(f"{port} ({name}): 已运行 ✅")
            else:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()
                if result == 0:
                    print_success(f"{port} ({name}): 已运行 ✅")
                else:
                    print_warning(f"{port} ({name}): 未运行")
        except Exception:
            print_warning(f"{port} ({name}): 未运行")

    # 总结
    cprint("\n" + "=" * 50, "cyan")
    if issues_found == 0:
        cprint("✅ 环境检查通过！可以正常运行 Axonewt。", "bold green")
    else:
        cprint(f"⚠️  发现 {issues_found} 个问题，请修复后再运行。", "bold yellow")

    cprint("=" * 50, "cyan")


# ============================================================================
# /scan - 健康扫描
# ============================================================================

@app.command("scan")
def scan(
    path: str = ".",
    threshold: float = 0.7,
    verbose: bool = False,
):
    """扫描代码库健康度"""
    print_banner()
    cprint(f"\n🔍 扫描: {path}\n", "bold cyan")

    project_path = Path(path).resolve()
    if not project_path.exists():
        print_error(f"路径不存在: {path}")
        raise typer.Exit(1)

    try:
        from src.agents.soma_dev import SomaDev
        soma = SomaDev(project_path=str(project_path))
        report = soma.scan_codebase()

        health = report["health_score"]
        status = report.get("health_status", "unknown")

        # 状态面板
        if status == "healthy":
            status_color = "green"
        elif status == "subhealthy":
            status_color = "yellow"
        else:
            status_color = "red"

        cprint(f"\n总体健康度: ", "bold", end="")
        cprint(f"{health:.3f} ({status})", status_color)

        # 详细指标
        if HAS_RICH:
            table = Table(title="详细指标", show_header=True, header_style="bold cyan")
            table.add_column("指标", style="cyan")
            table.add_column("分数", style="white")
            table.add_column("状态", style="white")

            metrics = report.get("metrics", {})
            for name, value in metrics.items():
                if value > 0.8:
                    icon, color = "✅", "green"
                elif value > 0.6:
                    icon, color = "⚠️", "yellow"
                else:
                    icon, color = "❌", "red"
                table.add_row(name, f"{value:.3f}", f"{icon} {color}")

            console.print(table)
        else:
            for name, value in report.get("metrics", {}).items():
                cprint(f"  {name}: {value:.3f}", "white")

        # 问题列表
        issues = report.get("issues", [])
        if issues:
            cprint(f"\n⚠️  发现 {len(issues)} 个问题:\n", "bold yellow")
            for i, issue in enumerate(issues[:10], 1):
                cprint(f"  {i}. {issue}", "yellow")

        # 是否需要修复
        needs_repair = health < threshold
        cprint(f"\n{'需要修复 ❌' if needs_repair else '无需修复 ✅'}", 
                "red" if needs_repair else "green")

        if verbose and HAS_RICH:
            cprint(f"\n📋 完整报告:\n", "bold")
            md = f"```json\n{json.dumps(report, indent=2, default=str)}\n```\n"
            console.print(Syntax(md, "json"))

    except ImportError as e:
        print_error(f"导入失败: {e}")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"扫描失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)


# ============================================================================
# /repair - 触发自愈
# ============================================================================

@app.command("repair")
def repair(
    path: str = ".",
    dry_run: bool = True,
    auto_approve: bool = False,
):
    """触发端到端自愈流程"""
    print_banner()
    cprint(f"\n🔧 自愈模式: {'Dry Run' if dry_run else '执行修复'}\n", 
            "bold cyan" if dry_run else "bold red")

    project_path = Path(path).resolve()
    if not project_path.exists():
        print_error(f"路径不存在: {path}")
        raise typer.Exit(1)

    try:
        from src.agents.soma_dev import SomaDev
        from src.agents.plasticus_dev import PlasticusDev
        from src.agents.effector_dev import EffectorDev
        from src.agents.mnemosyne_dev import MnemosyneDev
        from src.protocol.oacp import BlueprintMessage
        import yaml

        # 加载配置
        config_path = ROOT / "config.yaml"
        config = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        github_token = os.getenv("GITHUB_TOKEN")
        llm_cfg = config.get("llm", {})
        llm_provider = llm_cfg.get("provider", "ollama")

        cprint("初始化 Agent...\n", "white")

        soma = SomaDev(project_path=str(project_path), github_token=github_token)
        plasticus = PlasticusDev(
            ollama_url=llm_cfg.get("base_url", "http://127.0.0.1:11434"),
            ollama_model=llm_cfg.get("model", "glm-4.7-flash:latest"),
            github_token=github_token
        )
        effector = EffectorDev(project_path=str(project_path), github_token=github_token)
        mnemosyne = MnemosyneDev(db_path=str(ROOT / "data" / "opennewt.db"))

        if auto_approve:
            os.environ["EFFECTOR_AUTO_APPROVE"] = "true"

        # Phase 1: Soma 扫描
        cprint("[1/4] Soma 感知层 - 扫描代码库...\n", "bold cyan")
        report = soma.scan_codebase()
        health = report["health_score"]

        if health >= 0.7:
            print_success(f"健康度 {health:.3f} >= 0.7，无需修复")
            return

        print_warning(f"健康度 {health:.3f} < 0.7，触发修复\n")

        # Phase 2: Plasticus 决策
        cprint("[2/4] Plasticus 决策层 - 生成修复方案...\n", "bold cyan")
        plans = plasticus.generate_plans(
            damage_type="CODE_DECAY",
            location="scanned by CLI",
            symptoms=[f"Health score {health:.3f}"],
            health_score=health,
            use_llm=True
        )

        if not plans:
            print_error("无法生成修复方案")
            return

        best_plan = plasticus.evaluate_plans(plans)
        print_success(f"最优方案: {best_plan.name}")
        print_info(f"  预估停机: {best_plan.downtime_seconds}s")
        print_info(f"  成功率预测: {best_plan.historical_success_rate*100:.0f}%")
        print_info(f"  步骤数: {len(best_plan.steps)}\n")

        if dry_run:
            print_warning("[Dry Run] 以下是计划步骤，未实际执行:\n")
            for i, step in enumerate(best_plan.steps, 1):
                desc = step.get("description", step.get("name", f"Step {i}"))
                cprint(f"  {i}. {desc}", "yellow")
            return

        # Phase 3: Effector 执行
        cprint("[3/4] Effector 执行层 - 执行修复...\n", "bold cyan")
        blueprint = BlueprintMessage.create(
            plan_id=f"CLI-{int(time.time())}",
            strategy=best_plan.name,
            steps=[{
                "number": i + 1,
                "name": step.get("name", step.get("description", f"Step {i+1}")),
                "description": step.get("description", ""),
                "action": step.get("description", ""),
                "type": step.get("type", "generic"),
            } for i, step in enumerate(best_plan.steps)],
            estimated_downtime=f"{best_plan.downtime_seconds}s",
            success_rate_prediction=best_plan.historical_success_rate,
            rollback_plan="git revert"
        )

        report = effector.execute_blueprint(blueprint)
        exec_status = report.payload.get("status", "unknown")

        if exec_status == "success":
            print_success("修复执行成功 ✅")
        elif exec_status == "partial_success":
            print_warning("部分成功 ⚠️")
        else:
            print_error(f"修复失败 ❌ ({exec_status})")

        # Phase 4: 验证
        cprint("\n[4/4] 验证修复效果...\n", "bold cyan")
        new_report = soma.scan_codebase()
        new_health = new_report["health_score"]
        delta = new_health - health

        if delta > 0:
            print_success(f"健康度提升: {health:.3f} → {new_health:.3f} (+{delta:.3f})")
        else:
            print_warning(f"健康度变化: {health:.3f} → {new_health:.3f} ({delta:+.3f})")

    except Exception as e:
        print_error(f"自愈失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)


# ============================================================================
# /monitor - 实时监控
# ============================================================================

@app.command("monitor")
def monitor(
    path: str = ".",
    interval: int = 30,
    threshold: float = 0.7,
):
    """实时监控代码库健康度"""
    print_banner()
    cprint(f"\n📡 监控模式: {path} (间隔 {interval}s)\n", "bold cyan")
    cprint("按 Ctrl+C 停止\n", "yellow")

    project_path = Path(path).resolve()
    if not project_path.exists():
        print_error(f"路径不存在: {path}")
        raise typer.Exit(1)

    try:
        from src.agents.soma_dev import SomaDev
        github_token = os.getenv("GITHUB_TOKEN")
        soma = SomaDev(project_path=str(project_path), github_token=github_token)

        iteration = 0
        health_history = []

        while True:
            iteration += 1
            try:
                report = soma.scan_codebase()
                health = report["health_score"]
                health_history.append(health)

                # 趋势计算
                if len(health_history) >= 3:
                    recent = health_history[-3:]
                    if recent[-1] > recent[0] + 0.05:
                        trend = "📈 上升"
                    elif recent[-1] < recent[0] - 0.05:
                        trend = "📉 下降"
                    else:
                        trend = "➡️ 稳定"
                else:
                    trend = "➡️ 稳定"

                # 颜色
                if health >= 0.8:
                    color = "green"
                elif health >= threshold:
                    color = "yellow"
                else:
                    color = "red"

                timestamp = time.strftime("%H:%M:%S")
                cprint(f"[{timestamp}] #{iteration:03d} ", "white", end="")
                cprint(f"健康度: {health:.3f}", color, end="  ")
                cprint(trend, "cyan", end="  ")

                if health < threshold:
                    print_warning("⚠️ 低于阈值")
                else:
                    print_success("✅")

                # 检测到问题
                issues = report.get("issues", [])
                if issues:
                    for issue in issues[:3]:
                        cprint(f"    → {issue[:60]}", "yellow")

                time.sleep(interval)

            except KeyboardInterrupt:
                cprint("\n\n👋 监控已停止", "bold cyan")
                break
            except Exception as e:
                print_error(f"扫描失败: {e}")
                time.sleep(interval)

    except ImportError as e:
        print_error(f"导入失败: {e}")
        raise typer.Exit(1)


# ============================================================================
# /stats - 统计信息
# ============================================================================

@app.command("stats")
def stats():
    """查看引擎统计信息"""
    print_banner()

    try:
        from src.agents.mnemosyne_dev import MnemosyneDev

        db_path = ROOT / "data" / "opennewt.db"
        if not db_path.exists():
            print_warning("数据库不存在，请先运行扫描")
            return

        mnemosyne = MnemosyneDev(db_path=str(db_path))
        stats_data = mnemosyne.get_statistics()

        if HAS_RICH:
            table = Table(title="引擎统计", show_header=True, header_style="bold cyan")
            table.add_column("指标", style="cyan")
            table.add_column("值", style="white")

            for key, value in stats_data.items():
                table.add_row(key, str(value))

            console.print(table)
        else:
            for key, value in stats_data.items():
                cprint(f"  {key}: {value}", "white")

    except Exception as e:
        print_error(f"获取统计失败: {e}")


# ============================================================================
# /log - 查看日志
# ============================================================================

@app.command("log")
def log(n: int = 20):
    """查看最近的引擎日志"""
    log_path = ROOT / "data" / "opennewt.log"

    if not log_path.exists():
        log_path = ROOT / "logs" / "opennewt.log"

    if not log_path.exists():
        print_warning("未找到日志文件")
        return

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        recent = lines[-n:] if len(lines) > n else lines

        if HAS_RICH:
            for line in recent:
                line = line.strip()
                if not line:
                    continue
                if "ERROR" in line or "❌" in line:
                    console.print(line, style="red")
                elif "WARNING" in line or "⚠️" in line:
                    console.print(line, style="yellow")
                elif "✅" in line or "SUCCESS" in line:
                    console.print(line, style="green")
                else:
                    console.print(line, style="white")
        else:
            for line in recent:
                print(line.strip())

    except Exception as e:
        print_error(f"读取日志失败: {e}")


# ============================================================================
# /ask - 单次问答
# ============================================================================

@app.command("ask")
def ask(question: str):
    """向 LLM 提问（使用配置的模型）"""
    print_banner()
    cprint(f"\n🤖 问题: {question}\n", "bold cyan")

    try:
        import yaml
        config_path = ROOT / "config.yaml"
        config = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        llm_cfg = config.get("llm", {})
        provider = llm_cfg.get("provider", "ollama")

        if provider == "ollama":
            from src.integrations.ollama_client import OllamaClient
            client = OllamaClient(
                base_url=llm_cfg.get("base_url", "http://127.0.0.1:11434")
            )
            model = llm_cfg.get("model", "glm-4.7-flash:latest")

            cprint("💬 思考中...\n", "yellow")

            response = client.chat_completion(
                model=model,
                messages=[{"role": "user", "content": question}],
                temperature=0.7,
                max_tokens=2048
            )

            cprint(f"🤖 回复:\n", "bold green")
            if HAS_RICH:
                console.print(Panel(response.text, border_style="green"))
            else:
                cprint(response.text, "white")

        elif provider in ("openai", "deepseek"):
            try:
                from openai import OpenAI
            except ImportError:
                print_error("请安装 openai: pip install openai")
                return

            if provider == "deepseek":
                api_key = os.getenv("DEEPSEEK_API_KEY")
                base_url = llm_cfg.get("deepseek", {}).get("base_url", "https://api.deepseek.com/v1")
                model = llm_cfg.get("model", "deepseek-chat")
            else:
                api_key = os.getenv("OPENAI_API_KEY")
                base_url = llm_cfg.get("openai", {}).get("base_url", None)
                model = llm_cfg.get("model", "gpt-4o-mini")

            kwargs = {"api_key": api_key, "model": model}
            if base_url:
                kwargs["base_url"] = base_url

            client = OpenAI(**kwargs)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": question}]
            )
            answer = response.choices[0].message.content
            cprint(f"🤖 回复:\n", "bold green")
            if HAS_RICH:
                console.print(Panel(answer, border_style="green"))
            else:
                cprint(answer, "white")

        else:
            print_error(f"不支持的 LLM 提供商: {provider}")

    except Exception as e:
        print_error(f"问答失败: {e}")


# ============================================================================
# /model - 模型管理
# ============================================================================

@app.command("model")
def model(
    action: str = "list",
    name: str = None,
):
    """切换或查看 LLM 模型"""
    print_banner()

    if action == "list":
        cprint("\n📋 可用模型\n", "bold cyan")
        llm_results = detect_llm()

        for provider, info in llm_results.items():
            if info.get("available"):
                models = info.get("models", [])
                cprint(f"\n{provider}:", "bold green")
                if models:
                    for m in models:
                        cprint(f"  - {m}", "white")
                else:
                    cprint("  (无)", "yellow")
            else:
                cprint(f"\n{provider}: ", "bold red", end="")
                reason = info.get("error") or "不可用"
                cprint(reason, "red")

    elif action == "set" and name:
        cprint(f"\n🔧 切换模型: {name}\n", "bold cyan")
        # 修改 config.yaml
        config_path = ROOT / "config.yaml"
        try:
            import yaml
            config = {}
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}

            config.setdefault("llm", {})["model"] = name
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True)

            print_success(f"已切换为: {name}")
            print_info(f"配置文件: {config_path}")

        except Exception as e:
            print_error(f"切换失败: {e}")

    else:
        cprint("\n用法:", "bold")
        cprint("  axonewt model list     # 列出可用模型", "white")
        cprint("  axonewt model set <name>  # 切换模型", "white")


# ============================================================================
# /version - 版本信息
# ============================================================================

@app.command("version")
def version():
    """显示版本信息"""
    print_banner()
    cprint(f"\n🦎 Axonewt Engine v0.3.0", "bold cyan")
    cprint(f"   Python {sys.version.split()[0]}", "white")
    cprint(f"   项目目录: {ROOT}\n", "white")


# ============================================================================
# 主入口
# ============================================================================

def main():
    """CLI 主入口"""
    try:
        app()
    except KeyboardInterrupt:
        cprint("\n\n👋 再见！", "cyan")
    except Exception as e:
        print_error(f"CLI 错误: {e}")
        raise


if __name__ == "__main__":
    main()
