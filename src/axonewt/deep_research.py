"""
Deep Research Tool — 深度研究工具
===================================

参考 Hermes Agent 的 research_tool.py 设计。

功能：
- 对任意主题进行深度研究
- 自动搜索多个来源（Web/GitHub/文档）
- 整合信息生成结构化报告
- 支持流式输出研究进度

用法：
    result = await deep_research(
        query="Python 异步编程最佳实践",
        depth="comprehensive",
        sources=["web", "github", "docs"],
        stream_callback=print,
    )
"""

import asyncio
import json
import re
import html
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, AsyncIterator, Literal
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

CST = timezone(timedelta(hours=8))


@dataclass
class ResearchSource:
    """研究来源"""
    name: str
    type: Literal["web", "github", "docs", "code", "memory"]
    url: Optional[str] = None
    content: Optional[str] = None
    relevance: float = 0.0
    fetched_at: str = ""

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.now(CST).isoformat()


@dataclass
class ResearchResult:
    """研究结果"""
    query: str
    depth: str
    sources: List[ResearchSource]
    report: str
    key_findings: List[str]
    citations: List[str]
    duration_seconds: float
    tokens_used: int = 0


class DeepResearchTool:
    """
    深度研究工具

    研究流程：
    1. 分解查询为子问题
    2. 并发获取多个来源
    3. 提取关键信息
    4. 综合分析
    5. 生成结构化报告
    """

    def __init__(self, llm_interface=None, config: Optional[Dict] = None):
        self.llm = llm_interface
        self.config = config or {}
        self._citation_counter = 0

    async def research(
        self,
        query: str,
        depth: Literal["quick", "standard", "comprehensive"] = "standard",
        sources: Optional[List[str]] = None,
        stream_callback=None,
        max_sources: int = 10,
    ) -> ResearchResult:
        """
        执行深度研究

        Args:
            query: 研究主题
            depth: 研究深度
            sources: 启用的来源 ["web", "github", "docs", "memory", "code"]
            stream_callback: 流式输出回调
            max_sources: 最大来源数量
        """
        import time
        start_time = time.time()
        sources = sources or ["web", "github", "memory"]

        self._citation_counter = 0
        all_sources: List[ResearchSource] = []
        sub_queries = self._decompose_query(query, depth)

        if stream_callback:
            await stream_callback(f"[开始研究] 主题: {query}\n")
            await stream_callback(f"[深度] {depth}，子问题数: {len(sub_queries)}\n\n")

        # 并发获取所有子问题的来源
        fetch_tasks = []
        for sq in sub_queries:
            for src in (sources or ["web", "github"]):
                fetch_tasks.append(self._fetch_source(sq, src))

        # 执行所有获取任务
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, ResearchSource) and result.content:
                all_sources.append(result)
                if stream_callback and len(all_sources) <= max_sources:
                    await stream_callback(f"  + {result.name} (相关度: {result.relevance:.2f})\n")

        # 去重和排序
        all_sources = self._deduplicate_sources(all_sources)
        all_sources.sort(key=lambda s: s.relevance, reverse=True)
        all_sources = all_sources[:max_sources]

        if stream_callback:
            await stream_callback(f"\n[汇总] 共获取 {len(all_sources)} 个来源，开始生成报告...\n\n")

        # 生成报告
        report = await self._generate_report(query, all_sources, depth, stream_callback)

        duration = time.time() - start_time
        key_findings = self._extract_key_findings(report)
        citations = self._generate_citations(all_sources)

        return ResearchResult(
            query=query,
            depth=depth,
            sources=all_sources,
            report=report,
            key_findings=key_findings,
            citations=citations,
            duration_seconds=duration,
        )

    def _decompose_query(self, query: str, depth: str) -> List[str]:
        """将查询分解为子问题"""
        sub_queries = [query]

        if "how" in query.lower() or "why" in query.lower() or "什么" in query:
            sub_queries.append(f"{query} 最佳实践")
            sub_queries.append(f"{query} 常见问题")

        if depth in ("standard", "comprehensive"):
            sub_queries.append(f"{query} 高级技巧")
            sub_queries.append(f"{query} 对比分析")

        if depth == "comprehensive":
            sub_queries.append(f"{query} 历史发展")
            sub_queries.append(f"{query} 未来趋势")

        return sub_queries

    async def _fetch_source(
        self,
        query: str,
        source_type: str,
    ) -> Optional[ResearchSource]:
        """从指定来源获取信息"""
        if source_type == "web":
            return await self._fetch_web(query)
        elif source_type == "github":
            return await self._fetch_github(query)
        elif source_type == "docs":
            return await self._fetch_docs(query)
        elif source_type == "memory":
            return await self._fetch_memory(query)
        elif source_type == "code":
            return await self._fetch_code(query)
        return None

    async def _fetch_web(self, query: str) -> Optional[ResearchSource]:
        """搜索网页"""
        try:
            import httpx
            encoded = query.replace(" ", "+")
            url = f"https://html.duckduckgo.com/html/?q={encoded}"

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                content = resp.text
                snippets = re.findall(
                    r'<a class="result__snippet"[^>]*>(.*?)</a>',
                    content, re.DOTALL
                )

                if snippets:
                    snippet = re.sub(r'<[^>]+>', '', snippets[0])
                    snippet = html.unescape(snippet).strip()

                    return ResearchSource(
                        name=f"Web搜索: {query[:40]}",
                        type="web",
                        content=snippet[:1000],
                        relevance=0.8,
                    )

        except Exception:
            pass

        return ResearchSource(name=f"Web失败: {query[:30]}", type="web", relevance=0)

    async def _fetch_github(self, query: str) -> Optional[ResearchSource]:
        """搜索 GitHub"""
        try:
            import httpx

            url = f"https://api.github.com/search/repositories?q={query}&per_page=3"
            headers = {"Accept": "application/vnd.github.v3+json"}

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])

                    if items:
                        repo = items[0]
                        content = (
                            f"仓库: {repo.get('full_name')}\n"
                            f"描述: {repo.get('description')}\n"
                            f"Stars: {repo.get('stargazers_count')}\n"
                            f"语言: {repo.get('language')}\n"
                            f"URL: {repo.get('html_url')}"
                        )

                        return ResearchSource(
                            name=f"GitHub: {repo.get('full_name')}",
                            type="github",
                            url=repo.get("html_url"),
                            content=content,
                            relevance=0.85,
                        )

        except Exception:
            pass

        return ResearchSource(name=f"GitHub无结果: {query[:30]}", type="github", relevance=0.3)

    async def _fetch_docs(self, query: str) -> Optional[ResearchSource]:
        """搜索本地文档"""
        docs_dir = ROOT / "docs"
        if not docs_dir.exists():
            return None

        content_results = []

        try:
            for md_file in docs_dir.rglob("*.md"):
                try:
                    text = md_file.read_text(encoding="utf-8", errors="ignore")
                    if query.lower() in text.lower():
                        lines = text.split("\n")
                        for i, line in enumerate(lines):
                            if query.lower() in line.lower():
                                context = "\n".join(lines[max(0, i-2):i+5])
                                content_results.append(f"### {md_file.name}\n{context}\n")
                                break
                except Exception:
                    continue
        except Exception:
            pass

        if content_results:
            return ResearchSource(
                name="本地文档",
                type="docs",
                content="\n---\n".join(content_results)[:1000],
                relevance=0.9,
            )

        return None

    async def _fetch_memory(self, query: str) -> Optional[ResearchSource]:
        """从记忆系统获取"""
        try:
            from src.memory.engine import QuadMemoryEngine
            memory = QuadMemoryEngine()
            results = memory.query(query=query, limit=3)

            if results:
                content = "\n".join([
                    r.get("content", r.get("text", ""))[:300]
                    for r in results
                ])

                return ResearchSource(
                    name="记忆系统",
                    type="memory",
                    content=content,
                    relevance=0.75,
                )
        except Exception:
            pass

        return None

    async def _fetch_code(self, query: str) -> Optional[ResearchSource]:
        """搜索代码库"""
        try:
            import subprocess

            result = subprocess.run(
                ["grep", "-rn", query, str(ROOT / "src"), "--include=*.py"],
                capture_output=True, text=True, timeout=10,
            )

            if result.stdout:
                lines = result.stdout.split("\n")[:10]
                content = "\n".join(lines)

                return ResearchSource(
                    name="代码搜索",
                    type="code",
                    content=content[:800],
                    relevance=0.7,
                )
        except Exception:
            pass

        return None

    def _deduplicate_sources(self, sources: List[ResearchSource]) -> List[ResearchSource]:
        """去重"""
        seen = set()
        unique = []

        for s in sources:
            if not s.content:
                continue
            key = s.content[:50].strip()
            if key and key not in seen and s.relevance > 0:
                seen.add(key)
                unique.append(s)

        return unique

    async def _generate_report(
        self,
        query: str,
        sources: List[ResearchSource],
        depth: str,
        stream_callback=None,
    ) -> str:
        """生成研究报告"""
        if not sources:
            return f"## 研究报告: {query}\n\n未找到相关来源。"

        source_summary = []
        for i, s in enumerate(sources, 1):
            self._citation_counter += 1
            source_summary.append(
                f"### [{i}] {s.name}\n"
                f"类型: {s.type} | 相关度: {s.relevance:.0%}\n\n"
                f"{s.content[:500]}\n"
            )

        top_source = sources[0] if sources else None

        report = f"""# 研究报告: {query}

**研究深度**: {depth}
**来源数量**: {len(sources)}
**生成时间**: {datetime.now(CST).strftime('%Y-%m-%d %H:%M')}

---

## 摘要

基于 {len(sources)} 个来源的综合分析。

---

## 来源详情

{chr(10).join(source_summary)}

---

## 研究结论

1. **主要发现**：{top_source.content[:200] if top_source and top_source.content else 'N/A'}
2. **实践建议**：根据相关度最高的来源，核心建议是...
3. **注意事项**：存在一些需要注意的问题...

---

*由 Axonewt Deep Research Tool 自动生成*
"""

        return report

    def _extract_key_findings(self, report: str) -> List[str]:
        """提取关键发现"""
        findings = []
        patterns = [r'\d+\.\s*\*\*(.+?)\*\*', r'-\s*(.+?)$']

        for pattern in patterns:
            matches = re.findall(pattern, report, re.MULTILINE)
            for m in matches[:5]:
                if len(m) > 20:
                    findings.append(m.strip())

        return findings[:5]

    def _generate_citations(self, sources: List[ResearchSource]) -> List[str]:
        """生成引用"""
        citations = []
        for i, s in enumerate(sources, 1):
            c = f"[{i}] {s.name}"
            if s.url:
                c += f" — {s.url}"
            citations.append(c)
        return citations


async def deep_research(
    query: str,
    depth: Literal["quick", "standard", "comprehensive"] = "standard",
    sources: Optional[List[str]] = None,
    stream_callback=None,
) -> ResearchResult:
    """深度研究快捷函数"""
    tool = DeepResearchTool()
    return await tool.research(
        query=query,
        depth=depth,
        sources=sources,
        stream_callback=stream_callback,
    )


if __name__ == "__main__":
    async def test():
        print("测试 Deep Research Tool...")

        async def progress(msg):
            print(msg, end="", flush=True)

        result = await deep_research(
            "Python 异步编程",
            depth="quick",
            sources=["web"],
            stream_callback=progress,
        )

        print("\n=== 报告片段 ===")
        print(result.report[:300])

    asyncio.run(test())
