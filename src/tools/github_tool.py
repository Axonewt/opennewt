"""
GitHub Tool — GitHub API 操作
==============================
"""

import httpx
import json
from typing import Dict, Optional


async def github_api(
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict] = None,
    token: Optional[str] = None,
) -> str:
    """
    通用 GitHub API 调用

    Args:
        endpoint: API 端点（如 "/repos/nousresearch/hermes-agent"）
        method: HTTP 方法
        data: 请求体
        token: GitHub Personal Access Token
    """
    try:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Axonewt-OpenNewt",
        }
        if token:
            headers["Authorization"] = f"token {token}"

        url = f"https://api.github.com{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=data)
            elif method == "PATCH":
                resp = await client.patch(url, headers=headers, json=data)
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                return f"Error: 不支持的 HTTP 方法: {method}"

            resp.raise_for_status()
            result = resp.json()
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    except httpx.HTTPStatusError as e:
        return f"GitHub API 错误: {e.response.status_code}"
    except Exception as e:
        return f"GitHub API 错误: {type(e).__name__}: {e}"


async def github_search_repos(query: str, token: Optional[str] = None) -> str:
    """搜索 GitHub 仓库"""
    return await github_api(
        endpoint=f"/search/repositories?q={query}&per_page=5&sort=stars",
        token=token,
    )


async def github_get_repo(owner: str, repo: str, token: Optional[str] = None) -> str:
    """获取仓库信息"""
    return await github_api(endpoint=f"/repos/{owner}/{repo}", token=token)


async def github_list_issues(
    owner: str,
    repo: str,
    state: str = "open",
    token: Optional[str] = None,
) -> str:
    """列出仓库的 Issues"""
    return await github_api(
        endpoint=f"/repos/{owner}/{repo}/issues?state={state}&per_page=10",
        token=token,
    )
