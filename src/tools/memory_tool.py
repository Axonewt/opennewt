"""
Memory Tools — 记忆系统工具集

工具列表:
- memory_save(key, value, ttl) -> bool
- memory_load(key) -> value
- memory_delete(key) -> bool
- memory_list() -> keys
- memory_search(query) -> results
- memory_stats() -> stats
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

MEMORY_DIR = Path(os.environ.get("AXONEWT_MEMORY_DIR", ".axonewt_memory"))
_MEMORY_INDEX = MEMORY_DIR / "index.json"
_MEMORY_DATA_DIR = MEMORY_DIR / "data"


def _ensure_memory_dir():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _MEMORY_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _MEMORY_INDEX.exists():
        _MEMORY_INDEX.write_text("{}", encoding="utf-8")


def _load_index() -> dict:
    _ensure_memory_dir()
    try:
        return json.loads(_MEMORY_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_index(index: dict):
    _ensure_memory_dir()
    _MEMORY_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def memory_save(key: str, value: str, ttl: int = 0) -> dict[str, Any]:
    """保存记忆"""
    try:
        _ensure_memory_dir()
        index = _load_index()
        data_path = _MEMORY_DATA_DIR / f"{key}.json"
        entry = {
            "key": key,
            "created_at": time.time(),
            "ttl": ttl,
        }
        if ttl > 0:
            entry["expires_at"] = time.time() + ttl
        data = {"entry": entry, "value": value}
        data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        index[key] = entry
        _save_index(index)
        return {"success": True, "key": key}
    except Exception as e:
        return {"success": False, "error": f"memory_save error: {e}"}


def memory_load(key: str) -> dict[str, Any]:
    """加载记忆"""
    try:
        index = _load_index()
        if key not in index:
            return {"success": False, "error": "Key not found"}
        entry = index[key]
        # TTL 检查
        if entry.get("expires_at", 0) > 0 and time.time() > entry["expires_at"]:
            return {"success": False, "error": "Key expired"}
        data_path = _MEMORY_DATA_DIR / f"{key}.json"
        if not data_path.exists():
            return {"success": False, "error": "Data file not found"}
        data = json.loads(data_path.read_text(encoding="utf-8"))
        return {"success": True, "key": key, "value": data["value"], "entry": entry}
    except Exception as e:
        return {"success": False, "error": f"memory_load error: {e}"}


def memory_delete(key: str) -> dict[str, Any]:
    """删除记忆"""
    try:
        index = _load_index()
        if key in index:
            del index[key]
            _save_index(index)
        data_path = _MEMORY_DATA_DIR / f"{key}.json"
        if data_path.exists():
            data_path.unlink()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": f"memory_delete error: {e}"}


def memory_list() -> dict[str, Any]:
    """列出所有记忆 key"""
    try:
        index = _load_index()
        now = time.time()
        keys = []
        for k, entry in index.items():
            if entry.get("expires_at", 0) > 0 and now > entry["expires_at"]:
                continue
            keys.append(k)
        return {"success": True, "keys": keys, "count": len(keys)}
    except Exception as e:
        return {"success": False, "error": f"memory_list error: {e}"}


def memory_search(query: str) -> dict[str, Any]:
    """搜索记忆（关键词）"""
    try:
        index = _load_index()
        now = time.time()
        results = []
        for key, entry in index.items():
            if entry.get("expires_at", 0) > 0 and now > entry["expires_at"]:
                continue
            if query.lower() in key.lower():
                results.append({"key": key, "entry": entry})
        return {"success": True, "results": results, "count": len(results)}
    except Exception as e:
        return {"success": False, "error": f"memory_search error: {e}"}


def memory_stats() -> dict[str, Any]:
    """记忆统计"""
    try:
        index = _load_index()
        now = time.time()
        total = len(index)
        expired = sum(1 for e in index.values() if e.get("expires_at", 0) > 0 and now > e["expires_at"])
        total_size = sum(
            (_MEMORY_DATA_DIR / f"{k}.json").stat().st_size
            for k in index
            if (_MEMORY_DATA_DIR / f"{k}.json").exists()
        )
        return {
            "success": True,
            "total": total,
            "expired": expired,
            "active": total - expired,
            "total_size_bytes": total_size,
        }
    except Exception as e:
        return {"success": False, "error": f"memory_stats error: {e}"}


TOOLS = {
    "memory_save": {"fn": memory_save, "desc": "保存记忆"},
    "memory_load": {"fn": memory_load, "desc": "加载记忆"},
    "memory_delete": {"fn": memory_delete, "desc": "删除记忆"},
    "memory_list": {"fn": memory_list, "desc": "列出所有记忆"},
    "memory_search": {"fn": memory_search, "desc": "搜索记忆"},
    "memory_stats": {"fn": memory_stats, "desc": "记忆统计"},
}
