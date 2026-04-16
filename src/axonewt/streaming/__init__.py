"""
Axonewt Streaming Renderer — 流式输出渲染器
============================================
使用 Rich 库实现：
- Markdown 渲染
- 代码块语法高亮
- 工具调用实时显示
- 进度条和 Spinner
- 错误高亮
"""

from .renderer import StreamingRenderer, ConsoleManager

__all__ = ["StreamingRenderer", "ConsoleManager"]
