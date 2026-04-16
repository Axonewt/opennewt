"""
Axonewt Tools Registry
======================

工具注册表 - 集中管理所有可用工具。
参考 Hermes Agent 的 tools/registry.py 设计。

工具分类：
- 文件工具（read_file, write_to_file, search_content）
- 终端工具（execute_command）
- Web 工具（web_search, web_fetch）
- 代码工具（grep, patch, diff）

每个工具在 tools/ 目录下有独立的 .py 文件，
通过 registry.register() 自动注册。
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
import json


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    category: str = "generic"
    parameters: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable] = None
    enabled: bool = True

    def to_schema(self) -> Dict[str, Any]:
        """生成 MCP 工具 schema"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters,
            }
        }


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.categories: Dict[str, List[str]] = {}

    def register(self, tool: Tool):
        """注册工具"""
        self.tools[tool.name] = tool
        if tool.category not in self.categories:
            self.categories[tool.category] = []
        if tool.name not in self.categories[tool.category]:
            self.categories[tool.category].append(tool.name)

    def get(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self.tools.get(name)

    def list_all(self) -> List[Tool]:
        """列出所有工具"""
        return list(self.tools.values())

    def list_by_category(self, category: str) -> List[Tool]:
        """按类别列出工具"""
        names = self.categories.get(category, [])
        return [self.tools[n] for n in names if n in self.tools]

    def get_schemas(self) -> List[Dict]:
        """获取所有工具的 MCP schema"""
        return [t.to_schema() for t in self.tools.values() if t.enabled]

    def enable(self, name: str):
        """启用工具"""
        if name in self.tools:
            self.tools[name].enabled = True

    def disable(self, name: str):
        """禁用工具"""
        if name in self.tools:
            self.tools[name].enabled = False

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_tools": len(self.tools),
            "enabled_tools": sum(1 for t in self.tools.values() if t.enabled),
            "categories": list(self.categories.keys()),
            "tools_by_category": {
                cat: len(names) for cat, names in self.categories.items()
            }
        }


# ============================================================================
# 工具实现
# ============================================================================

async def read_file_handler(path: str, encoding: str = "utf-8") -> str:
    """读取文件内容"""
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return f"Error: File not found: {path}"
    try:
        return p.read_text(encoding=encoding)
    except Exception as e:
        return f"Error reading {path}: {e}"


async def write_file_handler(path: str, content: str, encoding: str = "utf-8") -> str:
    """写入文件内容"""
    from pathlib import Path
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        return f"Success: Written to {path}"
    except Exception as e:
        return f"Error writing {path}: {e}"


async def search_handler(query: str, path: str = ".", pattern: str = None) -> str:
    """搜索文件内容"""
    import subprocess
    try:
        args = ["grep", "-rn", query, path]
        if pattern:
            args.extend(["--include", pattern])
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        if result.stdout:
            return result.stdout
        else:
            return "No matches found"
    except Exception as e:
        return f"Error searching: {e}"


async def list_dir_handler(path: str = ".") -> str:
    """列出目录内容"""
    from pathlib import Path
    try:
        items = list(Path(path).iterdir())
        lines = [f"{'📁' if i.is_dir() else '📄'} {i.name}" for i in items]
        return "\n".join(lines) if lines else "(empty)"
    except Exception as e:
        return f"Error listing {path}: {e}"


# ============================================================================
# 默认注册表实例
# ============================================================================

_default_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表（单例）"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
        _register_default_tools(_default_registry)
    return _default_registry


def _register_default_tools(registry: ToolRegistry):
    """注册默认工具"""

    # 文件工具
    registry.register(Tool(
        name="read_file",
        description="读取文件内容，支持指定编码",
        category="file",
        parameters={
            "path": {"type": "string", "description": "文件路径"},
            "encoding": {"type": "string", "description": "编码，默认 utf-8", "default": "utf-8"},
        },
        handler=read_file_handler,
    ))

    registry.register(Tool(
        name="write_file",
        description="写入文件内容，自动创建目录",
        category="file",
        parameters={
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "文件内容"},
            "encoding": {"type": "string", "description": "编码，默认 utf-8", "default": "utf-8"},
        },
        handler=write_file_handler,
    ))

    registry.register(Tool(
        name="search_content",
        description="在文件中搜索内容（grep）",
        category="file",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
            "path": {"type": "string", "description": "搜索路径，默认 ."},
            "pattern": {"type": "string", "description": "文件模式，如 *.py"},
        },
        handler=search_handler,
    ))

    registry.register(Tool(
        name="list_dir",
        description="列出目录内容",
        category="file",
        parameters={
            "path": {"type": "string", "description": "目录路径，默认 ."},
        },
        handler=list_dir_handler,
    ))


# 快捷函数
def list_all_tools() -> List[Tool]:
    return get_tool_registry().list_all()


def get_tool_schemas() -> List[Dict]:
    return get_tool_registry().get_schemas()
