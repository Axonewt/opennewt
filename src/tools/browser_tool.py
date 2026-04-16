"""
Web Search Tool — 网页搜索
==========================
"""

import httpx
import re
import html
from typing import Dict, List, Optional


async def web_search(query: str, max_results: int = 5) -> str:
    """
    搜索网页，返回搜索结果摘要

    Args:
        query: 搜索关键词
        max_results: 最大结果数
    """
    try:
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

        if not snippets:
            return f"未找到「{query}」的相关结果"

        results = []
        for i, snippet in enumerate(snippets[:max_results], 1):
            # 清理 HTML
            text = re.sub(r'<[^>]+>', '', snippet)
            text = html.unescape(text).strip()
            results.append(f"{i}. {text}")

        return "\n".join(results) if results else f"未找到「{query}」的相关结果"

    except httpx.HTTPError as e:
        return f"搜索失败（HTTP错误）: {e}"
    except Exception as e:
        return f"搜索失败: {type(e).__name__}: {e}"


async def web_fetch(url: str, max_length: int = 5000) -> str:
    """
    获取网页内容并提取正文

    Args:
        url: 网页 URL
        max_length: 最大返回字符数
    """
    try:
        import html as html_module

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content = resp.text

        # 提取 <title>
        title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.DOTALL | re.IGNORECASE)
        title = html_module.unescape(title_match.group(1).strip()) if title_match else "无标题"

        # 提取 <meta description>
        desc_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            content, re.IGNORECASE
        )
        if not desc_match:
            desc_match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
                content, re.IGNORECASE
            )
        description = desc_match.group(1).strip() if desc_match else ""

        # 移除脚本和样式
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)

        # 提取纯文本
        text = re.sub(r'<[^>]+>', ' ', content)
        text = html_module.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) > max_length:
            text = text[:max_length] + f"\n... [截断，共 {len(text)} 字符]"

        result = f"# {title}\n\n"
        if description:
            result += f"摘要: {description}\n\n"
        result += f"内容:\n{text}"

        return result

    except httpx.HTTPError as e:
        return f"获取失败（HTTP错误）: {e}"
    except Exception as e:
        return f"获取失败: {type(e).__name__}: {e}"
