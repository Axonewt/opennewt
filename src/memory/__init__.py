"""
Axonewt 四层记忆架构
=====================

融合 Claude Code + Hermes Agent 的记忆系统：

Layer 1 - MemoryIndex (index.py):
  MEMORY.md 索引入口，极低 token，始终加载在系统 prompt 中。
  约束：≤200 行，≤25KB。

Layer 2 - ProjectContext (context.py):
  任务相关的具体文件、决策、背景。通过相似度检索按需加载。

Layer 3 - SessionCache (cache.py):
  会话中的临时信息。自动压缩蒸馏到 MEMORY.md。

Layer 4 - NeuralGraph (graph.py):
  Axonewt 特有的代码关系图谱 + 健康度追踪 + 变化检测。

Engine (engine.py):
  统一入口，四层协调，提供查询接口。

记忆新鲜度规则：
- ≤1 天：视为新鲜
- >1 天：自动附加警告标签
"""

from .index import MemoryIndex, MemoryEntry
from .context import ProjectContext, ContextEntry
from .cache import SessionCache, CacheEntry
from .graph import NeuralGraph, GraphNode, GraphEdge
from .engine import QuadMemoryEngine

__all__ = [
    "MemoryIndex",
    "MemoryEntry",
    "ProjectContext",
    "ContextEntry",
    "SessionCache",
    "CacheEntry",
    "NeuralGraph",
    "GraphNode",
    "GraphEdge",
    "QuadMemoryEngine",
]

__version__ = "0.1.0"
