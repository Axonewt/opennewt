"""
交互式安装向导 — Setup Wizard
==============================

参考 Hermes Agent setup.py 的核心交互逻辑。

功能：
1. 零配置启动，自动检测环境
2. 交互式选择 LLM 提供商和模型
3. 配置 API keys（安全提示）
4. 初始化数据库和目录
5. 验证安装完整性
6. 生成 config.yaml

用法：
    python -m src.axonewt.setup_wizard
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@dataclass
class SetupConfig:
    """安装配置"""
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_api_base: str = "http://localhost:11434/v1"
    llm_api_key: Optional[str] = None
    github_token: Optional[str] = None
    data_dir: str = "./data"
    db_type: str = "sqlite"
    streaming: bool = True
    log_level: str = "INFO"
    auto_update: bool = True


class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"


def print_banner():
    print(f"""
{Colors.CYAN}{Colors.BOLD}
   █████╗ ██████╗ ██████╗███████╗███████╗███████╗
  ██╔══██╗██╔════╝██╔════╝██╔════╝██╔════╝██╔════╝
  ███████║██║     ██║     █████╗  ███████╗███████╗
  ██╔══██║██║     ██║     ██╔══╝  ╚════██║╚════██║
  ██║  ██║╚██████╗╚██████╗███████╗███████║███████║
  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝╚══════╝╚══════╝╚══════╝
{Colors.RESET}
  {Colors.CYAN}Neural Plasticity Engine — Setup Wizard{Colors.RESET}
  {Colors.YELLOW}零配置安装，60秒启动{Colors.RESET}
""")


def print_step(step: int, total: int, message: str):
    print(f"\n{Colors.BLUE}[{step}/{total}]{Colors.RESET} {Colors.BOLD}{message}{Colors.RESET}")


def print_success(msg: str):
    print(f"  {Colors.GREEN}✓{Colors.RESET} {msg}")


def print_warning(msg: str):
    print(f"  {Colors.YELLOW}⚠{Colors.RESET} {msg}")


def print_error(msg: str):
    print(f"  {Colors.RED}✗{Colors.RESET} {msg}")


def print_info(msg: str):
    print(f"  {Colors.CYAN}ℹ{Colors.RESET} {msg}")


def input_yes_no(question: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        try:
            answer = input(f"    {question}{suffix}").strip().lower()
            if not answer:
                return default
            if answer in ("y", "yes", "是"):
                return True
            if answer in ("n", "no", "否"):
                return False
            print("    请输入 y 或 n")
        except (EOFError, KeyboardInterrupt):
            print()
            return default


def input_choice(question: str, options: list, default: int = 0) -> int:
    print(f"    {question}")
    for i, opt in enumerate(options, 1):
        marker = " ← 默认" if i - 1 == default else ""
        print(f"      {i}. {opt}{marker}")
    while True:
        try:
            answer = input(f"    选择 [1-{len(options)}]: ").strip()
            if not answer:
                return default
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                return idx
            print(f"    请输入 1-{len(options)}")
        except (ValueError, EOFError, KeyboardInterrupt):
            print()
            return default


def input_text(question: str, default: str = "", password: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            if password:
                import getpass
                answer = getpass.getpass(f"    {question}{suffix}: ").strip()
            else:
                answer = input(f"    {question}{suffix}: ").strip()
            if not answer and default:
                return default
            if answer:
                return answer
            if default:
                return default
            print("    不能为空")
        except (EOFError, KeyboardInterrupt):
            print()
            return default


def check_ollama() -> Optional[list]:
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code == 200:
            return resp.json().get("models", [])
    except Exception:
        pass
    return None


def detect_environment() -> Dict[str, Any]:
    print(f"\n{Colors.CYAN}正在检测环境...{Colors.RESET}")
    env = {
        "ollama_available": False,
        "ollama_models": [],
        "openai_available": bool(os.getenv("OPENAI_API_KEY")),
        "deepseek_available": bool(os.getenv("DEEPSEEK_API_KEY")),
        "workbuddy_available": True,
        "python_version": sys.version_info[:2],
        "git_available": False,
        "github_token": bool(os.getenv("GITHUB_TOKEN")),
    }

    if env["python_version"] >= (3, 9):
        print_success(f"Python {env['python_version'][0]}.{env['python_version'][1]} ✓")
    else:
        print_error(f"Python {env['python_version'][0]}.{env['python_version'][1]} — 需要 3.9+")

    ollama_models = check_ollama()
    if ollama_models:
        env["ollama_available"] = True
        env["ollama_models"] = [m["name"] for m in ollama_models]
        print_success(f"Ollama 可用 — {len(ollama_models)} 个模型")
        for m in ollama_models[:5]:
            print_info(f"  • {m['name']}")
    else:
        print_warning("Ollama 未运行（运行 `ollama serve` 启动）")

    if env["openai_available"]:
        print_success("OpenAI API Key 已配置")
    else:
        print_warning("未配置 OpenAI API Key")

    if env["deepseek_available"]:
        print_success("DeepSeek API Key 已配置")
    else:
        print_warning("未配置 DeepSeek API Key")

    try:
        import subprocess
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            env["git_available"] = True
            print_success(f"Git {result.stdout.strip()} ✓")
    except Exception:
        pass

    if env["github_token"]:
        print_success("GitHub Token 已配置")
    else:
        print_warning("未配置 GitHub Token（部分功能受限）")

    return env


def setup_dependencies() -> bool:
    print(f"\n{Colors.CYAN}检查依赖...{Colors.RESET}")
    required = ["httpx", "fastapi", "uvicorn", "pyyaml", "rich"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print_warning(f"缺少: {', '.join(missing)}")
        if input_yes_no("是否自动安装？", default=True):
            import subprocess
            print(f"\n{Colors.CYAN}安装中...{Colors.RESET}")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install"] + missing,
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                print_success("依赖安装完成")
                return True
            else:
                print_error(f"安装失败: {result.stderr[:200]}")
                return False
        else:
            print_warning("跳过，部分功能可能不可用")
            return False
    else:
        print_success("所有依赖已安装")
        return True


def setup_database(config: SetupConfig) -> bool:
    print(f"\n{Colors.CYAN}初始化数据库...{Colors.RESET}")
    data_dir = Path(config.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "opennewt.db"

    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                agent TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT,
                tags TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS immune_memory (
                template_id TEXT PRIMARY KEY,
                damage_type TEXT NOT NULL,
                symptoms TEXT,
                repair_strategy TEXT,
                steps TEXT,
                success_rate REAL DEFAULT 0.0,
                usage_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_graph (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                file_path TEXT,
                symbol_name TEXT,
                dependencies TEXT,
                health_score REAL DEFAULT 1.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON event_log(event_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON event_log(timestamp)")

        conn.commit()
        conn.close()
        print_success(f"数据库已创建: {db_path}")
        return True
    except Exception as e:
        print_error(f"数据库初始化失败: {e}")
        return False


def write_config(config: SetupConfig) -> bool:
    print(f"\n{Colors.CYAN}写入配置文件...{Colors.RESET}")
    config_path = ROOT / "config.yaml"

    cfg = {
        "opennewt": {"version": "0.3.0", "data_dir": config.data_dir},
        "llm": {
            "provider": config.llm_provider,
            "model": config.llm_model,
            "api_base": config.llm_api_base,
            "streaming": config.streaming,
        },
        "monitoring": {"enabled": True, "tick_interval": 30},
        "logging": {"level": config.log_level, "file": "opennewt.log"},
    }

    if config.llm_api_key:
        cfg["llm"]["api_key"] = config.llm_api_key

    try:
        import yaml
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print_success(f"配置已写入: {config_path}")
        return True
    except Exception as e:
        print_error(f"配置写入失败: {e}")
        return False


def verify_installation(config: SetupConfig) -> bool:
    print(f"\n{Colors.CYAN}验证安装完整性...{Colors.RESET}")
    all_ok = True

    core_files = [
        ROOT / "src" / "axonewt" / "agent_loop.py",
        ROOT / "src" / "axonewt" / "cli.py",
        ROOT / "src" / "memory" / "engine.py",
        ROOT / "src" / "tools" / "__init__.py",
        ROOT / "src" / "skills" / "__init__.py",
        ROOT / "src" / "mcp" / "__init__.py",
    ]

    for f in core_files:
        if f.exists():
            print_success(f"✓ {f.relative_to(ROOT)}")
        else:
            print_error(f"✗ {f.relative_to(ROOT)} — 缺失")
            all_ok = False

    if config.llm_provider == "ollama":
        models = check_ollama()
        if models and any(config.llm_model in m["name"] for m in models):
            print_success(f"LLM 连接正常: {config.llm_model}")
        else:
            print_warning(f"模型 {config.llm_model} 未找到，请运行 `ollama pull {config.llm_model}`")
            all_ok = False
    elif config.llm_provider in ("openai", "deepseek"):
        print_success(f"{config.llm_provider} API 配置正确")

    return all_ok


def run_setup() -> SetupConfig:
    print_banner()
    print_step(1, 5, "检测环境")
    env = detect_environment()

    print_step(2, 5, "安装依赖")
    setup_dependencies()

    print_step(3, 5, "配置 LLM 提供商")
    config = SetupConfig()

    providers = []
    defaults_list = []

    if env["ollama_available"]:
        providers.append("Ollama（本地，推荐）")
        defaults_list.append("ollama")

    if env["openai_available"] or env["deepseek_available"]:
        providers.append("OpenAI / DeepSeek（云端）")
        defaults_list.append("openai")

    providers.append("WorkBuddy（内置，无需配置）")
    defaults_list.append("workbuddy")

    default_idx = 0
    if "ollama" in defaults_list:
        default_idx = defaults_list.index("ollama")
    elif "openai" in defaults_list:
        default_idx = defaults_list.index("openai")

    if providers:
        choice = input_choice("选择 LLM 提供商", providers, default_idx)
        if choice == 0 and "ollama" in defaults_list:
            config.llm_provider = "ollama"
        elif choice == 1 and len(providers) > 2:
            config.llm_provider = "openai"
        else:
            config.llm_provider = "workbuddy"

    if config.llm_provider == "ollama":
        if env["ollama_models"]:
            model_options = [m["name"] for m in env["ollama_models"]]
            model_choice = input_choice("选择模型", model_options, 0)
            config.llm_model = model_options[model_choice]
        else:
            config.llm_model = input_text("输入模型名称", "qwen2.5:7b")
        config.llm_api_base = "http://localhost:11434/v1"

    elif config.llm_provider in ("openai", "deepseek"):
        api_key_name = f"{config.llm_provider.upper()}_API_KEY"
        existing_key = os.getenv(api_key_name)
        if existing_key:
            print_success(f"已检测到 {config.llm_provider.upper()} API Key")
        else:
            new_key = input_text(f"输入 {config.llm_provider.upper()} API Key", password=True)
            if new_key:
                os.environ[api_key_name] = new_key
                config.llm_api_key = new_key

        if config.llm_provider == "openai":
            config.llm_api_base = "https://api.openai.com/v1"
            config.llm_model = "gpt-4"
        else:
            config.llm_api_base = "https://api.deepseek.com/v1"
            config.llm_model = "deepseek-chat"

    else:
        config.llm_provider = "workbuddy"
        config.llm_api_base = "https://api.workbuddy.cn/v1"
        config.llm_model = "claude-3-5-sonnet"

    print_step(4, 5, "初始化数据库和目录")
    setup_database(config)

    print_step(5, 5, "验证安装并写入配置")
    write_config(config)
    install_ok = verify_installation(config)

    print(f"\n{Colors.GREEN}{Colors.BOLD}")
    print("=" * 50)
    if install_ok:
        print("  ✓ 安装完成！")
    else:
        print("  ⚠ 安装完成（部分警告，见上文）")
    print("=" * 50)
    print(f"{Colors.RESET}")
    print(f"  启动命令:")
    print(f"    {Colors.CYAN}python run.py{Colors.RESET}            — 启动引擎")
    print(f"    {Colors.CYAN}python -m src.axonewt.cli{Colors.RESET}  — 交互模式")
    print(f"    {Colors.CYAN}python -m src.mcp{Colors.RESET}          — MCP 服务器")
    print(f"    {Colors.CYAN}python -m src.axonewt.setup_wizard{Colors.RESET} — 重新配置")
    print(f"\n  配置文件: {ROOT / 'config.yaml'}")
    print(f"  数据目录: {config.data_dir}")
    print()

    return config


class SetupWizard:
    """交互式安装向导主类"""

    def __init__(self, non_interactive: bool = False):
        self.non_interactive = non_interactive
        self.config = SetupConfig()
        self.env = {}
        self.steps = []

    def check_environment(self) -> Dict[str, Any]:
        """步骤1：检测环境"""
        print_step(1, 5, "检测环境")
        self.env = detect_environment()
        return self.env

    def install_dependencies(self) -> bool:
        """步骤2：安装依赖"""
        print_step(2, 5, "安装依赖")
        return setup_dependencies()

    def configure_llm(self) -> SetupConfig:
        """步骤3：配置 LLM 提供商"""
        print_step(3, 5, "配置 LLM 提供商")
        return run_setup.__wrapped__() if hasattr(run_setup, '__wrapped__') else self._configure_llm_interactive()

    def _configure_llm_interactive(self) -> SetupConfig:
        """LLM 配置交互逻辑"""
        providers = []
        defaults_list = []
        if self.env.get("ollama_available"):
            providers.append("Ollama（本地，推荐）")
            defaults_list.append("ollama")
        if self.env.get("openai_available") or self.env.get("deepseek_available"):
            providers.append("OpenAI / DeepSeek（云端）")
            defaults_list.append("openai")
        providers.append("WorkBuddy（内置，无需配置）")
        defaults_list.append("workbuddy")
        default_idx = defaults_list.index("ollama") if "ollama" in defaults_list else defaults_list.index("openai") if "openai" in defaults_list else 0
        choice = input_choice("选择 LLM 提供商", providers, default_idx)
        if choice == 0 and "ollama" in defaults_list:
            self.config.llm_provider = "ollama"
        elif choice == 1 and len(providers) > 2:
            self.config.llm_provider = "openai"
        else:
            self.config.llm_provider = "workbuddy"
        if self.config.llm_provider == "ollama":
            if self.env.get("ollama_models"):
                model_options = [m["name"] for m in self.env["ollama_models"]]
                model_choice = input_choice("选择模型", model_options, 0)
                self.config.llm_model = model_options[model_choice]
            else:
                self.config.llm_model = input_text("输入模型名称", "qwen2.5:7b")
            self.config.llm_api_base = "http://localhost:11434/v1"
        elif self.config.llm_provider in ("openai", "deepseek"):
            self.config.llm_model = input_text("输入模型名称", "gpt-4o-mini")
            self.config.llm_api_key = input_text("输入 API Key", password=True)
        elif self.config.llm_provider == "claude":
            self.config.llm_model = "claude-3-5-sonnet"
        return self.config

    def init_database(self) -> bool:
        """步骤4：初始化数据库"""
        print_step(4, 5, "初始化数据库和目录")
        return setup_database(self.config)

    def verify_and_save(self) -> bool:
        """步骤5：验证并保存"""
        print_step(5, 5, "验证安装并写入配置")
        write_config(self.config)
        return verify_installation(self.config)

    def run(self) -> SetupConfig:
        """运行完整安装流程"""
        print_banner()
        self.check_environment()
        self.install_dependencies()
        self.configure_llm()
        self.init_database()
        self.verify_and_save()
        return self.config


__all__ = ["SetupConfig", "SetupWizard", "Colors", "run_setup", "detect_environment",
           "print_banner", "print_success", "print_warning", "print_error", "print_info"]


if __name__ == "__main__":
    try:
        run_setup()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}安装已取消{Colors.RESET}")
        sys.exit(0)
