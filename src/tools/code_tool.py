"""
Code Tools — 代码相关工具集

工具列表:
- execute_command(cmd, cwd, timeout) -> output
- run_python(code, timeout) -> result
- run_tests(path) -> results
- lint_code(path) -> issues
- format_code(path) -> bool
- git_status(cwd) -> status
- git_log(cwd, limit) -> commits
- git_diff(cwd) -> changes
"""

import subprocess
import sys
import tempfile
import os
import json
from typing import Any


def execute_command(cmd: str, cwd: str = ".", timeout: int = 60) -> dict[str, Any]:
    """执行 Shell 命令"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": f"Execute error: {e}"}


def run_python(code: str, timeout: int = 30) -> dict[str, Any]:
    """执行 Python 代码"""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            temp_path = f.name
        try:
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                timeout=timeout,
                text=True,
            )
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
            }
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
    except Exception as e:
        return {"success": False, "error": f"Python run error: {e}"}


def git_status(cwd: str = ".") -> dict[str, Any]:
    """Git 状态"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return {
            "success": True,
            "changed": [l for l in lines if l.startswith(" M")],
            "untracked": [l for l in lines if l.startswith("??")],
            "staged": [l for l in lines if l.startswith("M ") or l.startswith("A ")],
            "clean": len(lines) == 0,
        }
    except Exception as e:
        return {"success": False, "error": f"git status error: {e}"}


def git_log(cwd: str = ".", limit: int = 10) -> dict[str, Any]:
    """Git 提交日志"""
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-n{limit}"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        commits = [c for c in result.stdout.strip().split("\n") if c]
        return {"success": True, "commits": commits, "count": len(commits)}
    except Exception as e:
        return {"success": False, "error": f"git log error: {e}"}


def git_diff(cwd: str = ".") -> dict[str, Any]:
    """Git 差异"""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {"success": True, "diff": result.stdout[:2000]}
    except Exception as e:
        return {"success": False, "error": f"git diff error: {e}"}


def git_branch(cwd: str = ".") -> dict[str, Any]:
    """Git 分支"""
    try:
        result = subprocess.run(
            ["git", "branch", "-v"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        current = next((l[2:] for l in lines if l.startswith("* ")), "unknown")
        branches = [l[2:] for l in lines]
        return {"success": True, "current": current, "branches": branches}
    except Exception as e:
        return {"success": False, "error": f"git branch error: {e}"}


# ── 工具注册表 ────────────────────────────────────────────

TOOLS = {
    "execute_command": {"fn": execute_command, "desc": "执行 Shell 命令"},
    "run_python": {"fn": run_python, "desc": "执行 Python 代码"},
    "git_status": {"fn": git_status, "desc": "Git 状态"},
    "git_log": {"fn": git_log, "desc": "Git 提交日志"},
    "git_diff": {"fn": git_diff, "desc": "Git 差异"},
    "git_branch": {"fn": git_branch, "desc": "Git 分支信息"},
}
