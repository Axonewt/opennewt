# Axonewt Tools — 统一工具注册表

def _load_tools(module, name):
    """从模块加载 TOOLS dict，不存在则尝试加载函数"""
    if hasattr(module, "TOOLS"):
        return getattr(module, "TOOLS")
    # 回退：收集模块中所有函数
    tools = {}
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        attr = getattr(module, attr_name)
        if callable(attr) and not attr_name.startswith("__"):
            tools[attr_name] = {"fn": attr, "desc": attr.__doc__ or attr_name}
    return tools


from . import browser_tool
from . import code_tool
from . import filesystem_tool
from . import github_tool
from . import memory_tool
from . import terminal_tool

_ALL_TOOLS = {}
_ALL_TOOLS.update(_load_tools(browser_tool, "browser"))
_ALL_TOOLS.update(_load_tools(code_tool, "code"))
_ALL_TOOLS.update(_load_tools(filesystem_tool, "filesystem"))
_ALL_TOOLS.update(_load_tools(github_tool, "github"))
_ALL_TOOLS.update(_load_tools(memory_tool, "memory"))
_ALL_TOOLS.update(_load_tools(terminal_tool, "terminal"))

# 兼容旧 API
ALL_TOOLS = _ALL_TOOLS


def get_tool(name: str):
    return ALL_TOOLS.get(name)


def list_tools() -> list[str]:
    return sorted(ALL_TOOLS.keys())


def tool_count() -> int:
    return len(ALL_TOOLS)


__all__ = ["ALL_TOOLS", "get_tool", "list_tools", "tool_count"]
