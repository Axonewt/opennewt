"""
Filesystem Tools — 文件系统工具集

工具列表:
- read_file(path) -> content
- write_file(path, content) -> bool
- edit_file(path, old_str, new_str) -> bool
- delete_file(path) -> bool
- copy_file(src, dst) -> bool
- move_file(src, dst) -> bool
- list_dir(path) -> entries
- search_content(path, pattern) -> matches
- search_file(path, pattern, recursive) -> files
- make_dir(path) -> bool
- file_info(path) -> metadata
"""

import os
import shutil
import re
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(os.environ.get("AXONEWT_WORKSPACE", "/workspace"))


def _resolve_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    # 安全检查：不允许访问 WORKSPACE_ROOT 之外的文件
    try:
        p.relative_to(WORKSPACE_ROOT)
    except ValueError:
        # 允许绝对路径在 WORKSPACE_ROOT 内的文件
        if not str(p).startswith(str(WORKSPACE_ROOT)):
            raise PermissionError(f"Access denied: {path} is outside workspace")
    return p


# ── 工具函数 ──────────────────────────────────────────────

def read_file(path: str) -> dict[str, Any]:
    """读取文件内容"""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if p.is_dir():
            return {"success": False, "error": f"Path is a directory: {path}"}
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {
            "success": True,
            "content": content,
            "size": p.stat().st_size,
            "lines": len(content.splitlines()),
        }
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Read error: {e}"}


def write_file(path: str, content: str, append: bool = False) -> dict[str, Any]:
    """写入文件内容"""
    try:
        p = _resolve_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(p, mode, encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "bytes": len(content.encode("utf-8"))}
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Write error: {e}"}


def edit_file(path: str, old_str: str, new_str: str) -> dict[str, Any]:
    """编辑文件（替换字符串）"""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return {"success": False, "error": f"File not found: {path}"}
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        if old_str not in content:
            return {"success": False, "error": "old_str not found in file"}
        new_content = content.replace(old_str, new_str, 1)
        with open(p, "w", encoding="utf-8") as f:
            f.write(new_content)
        return {
            "success": True,
            "replacements": 1,
            "bytes": len(new_content.encode("utf-8")),
        }
    except Exception as e:
        return {"success": False, "error": f"Edit error: {e}"}


def delete_file(path: str) -> dict[str, Any]:
    """删除文件或目录"""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return {"success": False, "error": f"Path not found: {path}"}
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": f"Delete error: {e}"}


def copy_file(src: str, dst: str) -> dict[str, Any]:
    """复制文件"""
    try:
        src_p = _resolve_path(src)
        dst_p = _resolve_path(dst)
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_p, dst_p)
        return {"success": True, "dst": str(dst_p)}
    except Exception as e:
        return {"success": False, "error": f"Copy error: {e}"}


def move_file(src: str, dst: str) -> dict[str, Any]:
    """移动文件"""
    try:
        src_p = _resolve_path(src)
        dst_p = _resolve_path(dst)
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dst_p))
        return {"success": True, "dst": str(dst_p)}
    except Exception as e:
        return {"success": False, "error": f"Move error: {e}"}


def list_dir(path: str) -> dict[str, Any]:
    """列出目录内容"""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return {"success": False, "error": f"Path not found: {path}"}
        if not p.is_dir():
            return {"success": False, "error": f"Path is not a directory: {path}"}
        entries = []
        for item in p.iterdir():
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
        entries.sort(key=lambda x: (x["type"] != "dir", x["name"]))
        return {"success": True, "entries": entries, "count": len(entries)}
    except Exception as e:
        return {"success": False, "error": f"List error: {e}"}


def search_content(path: str, pattern: str, case_sensitive: bool = False) -> dict[str, Any]:
    """在文件中搜索内容（正则）"""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return {"success": False, "error": f"Path not found: {path}"}
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
        matches = []
        if p.is_file():
            files_to_search = [p]
        else:
            files_to_search = list(p.rglob("*")) if p.is_dir() else []
            files_to_search = [f for f in files_to_search if f.is_file() and f.size() < 10 * 1024 * 1024]

        for f in files_to_search:
            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fp:
                    for lineno, line in enumerate(fp, 1):
                        if regex.search(line):
                            matches.append({
                                "file": str(f.relative_to(WORKSPACE_ROOT)),
                                "line": lineno,
                                "text": line.rstrip(),
                            })
            except Exception:
                continue
        return {"success": True, "matches": matches, "count": len(matches)}
    except Exception as e:
        return {"success": False, "error": f"Search error: {e}"}


def search_file(path: str, pattern: str, recursive: bool = True) -> dict[str, Any]:
    """按名称搜索文件"""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return {"success": False, "error": f"Path not found: {path}"}
        regex = re.compile(pattern, re.IGNORECASE)
        results = []
        root = p.rglob("*") if recursive and p.is_dir() else p.parent.glob(p.name)
        for f in root:
            if f.is_file() and regex.search(f.name):
                results.append(str(f.relative_to(WORKSPACE_ROOT)))
        return {"success": True, "files": results, "count": len(results)}
    except Exception as e:
        return {"success": False, "error": f"Search error: {e}"}


def make_dir(path: str) -> dict[str, Any]:
    """创建目录"""
    try:
        p = _resolve_path(path)
        p.mkdir(parents=True, exist_ok=True)
        return {"success": True, "path": str(p)}
    except Exception as e:
        return {"success": False, "error": f"mkdir error: {e}"}


def file_info(path: str) -> dict[str, Any]:
    """获取文件元数据"""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return {"success": False, "error": f"Path not found: {path}"}
        stat = p.stat()
        return {
            "success": True,
            "name": p.name,
            "type": "dir" if p.is_dir() else "file",
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
            "readable": os.access(p, os.R_OK),
            "writable": os.access(p, os.W_OK),
        }
    except Exception as e:
        return {"success": False, "error": f"Info error: {e}"}


# ── 工具注册表 ────────────────────────────────────────────

TOOLS = {
    "read_file": {"fn": read_file, "desc": "读取文件内容"},
    "write_file": {"fn": write_file, "desc": "写入文件内容"},
    "edit_file": {"fn": edit_file, "desc": "编辑文件（字符串替换）"},
    "delete_file": {"fn": delete_file, "desc": "删除文件或目录"},
    "copy_file": {"fn": copy_file, "desc": "复制文件"},
    "move_file": {"fn": move_file, "desc": "移动文件"},
    "list_dir": {"fn": list_dir, "desc": "列出目录内容"},
    "search_content": {"fn": search_content, "desc": "在文件中搜索内容"},
    "search_file": {"fn": search_file, "desc": "按名称搜索文件"},
    "make_dir": {"fn": make_dir, "desc": "创建目录"},
    "file_info": {"fn": file_info, "desc": "获取文件元数据"},
}
