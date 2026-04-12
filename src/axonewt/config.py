"""
零配置启动 - 自动检测 LLM
"""
import os
import httpx
from typing import Literal


def detect_llm_provider() -> tuple[str, str]:
    """
    自动检测可用的 LLM 提供商
    返回: (provider, model)
    """
    # 1. 检查 Ollama
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            models = response.json().get("models", [])
            if models:
                return "ollama", models[0]["name"]
    except:
        pass

    # 2. 检查 OpenAI
    if os.getenv("OPENAI_API_KEY"):
        return "openai", "gpt-4"

    # 3. 检查 DeepSeek
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek", "deepseek-chat"

    # 4. 默认回退
    return "ollama", "qwen2.5:7b"


def get_llm_config() -> dict:
    """获取 LLM 配置（用于主程序）"""
    provider, model = detect_llm_provider()

    config = {
        "provider": provider,
        "model": model,
        "api_base": None,
        "api_key": None,
    }

    if provider == "ollama":
        config["api_base"] = "http://localhost:11434/v1"
        config["model"] = model or "qwen2.5:7b"
    elif provider == "openai":
        config["api_base"] = "https://api.openai.com/v1"
        config["api_key"] = os.getenv("OPENAI_API_KEY")
    elif provider == "deepseek":
        config["api_base"] = "https://api.deepseek.com/v1"
        config["api_key"] = os.getenv("DEEPSEEK_API_KEY")

    return config
