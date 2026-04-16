"""
Axonewt Evolution Loop — Skill 自进化闭环
==========================================
参考 Hermes Agent 的闭环学习系统：
执行任务 → 提取经验 → 生成 Skill → A/B 测试 → RL 轨迹
"""

import json
import time
import sqlite3
from pathlib import Path
from typing import Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class TrajectoryEntry:
    """轨迹条目 — 单次工具调用记录"""
    timestamp: str
    task_id: str
    user_message: str
    agent_response: str
    tools_used: list[str]
    tool_results: list[dict]
    success: bool
    duration_ms: int
    token_cost: int = 0


@dataclass
class SkillCandidate:
    """技能候选 — 从轨迹提取的经验"""
    name: str
    description: str
    trigger_patterns: list[str]
    tool_chain: list[dict]  # [{"tool": "...", "params": {...}}, ...]
    success_rate: float = 0.0
    total_uses: int = 0
    avg_duration_ms: int = 0
    source_session: str = ""


class EvolutionLoop:
    """
    自进化闭环核心 — 「火蜥蜴再生」能力

    流程：
    1. Monitor   → 监控每次任务执行
    2. Extract   → 从轨迹中提取成功模式
    3. Generate  → 生成 Skill 候选
    4. Test      → A/B 测试验证
    5. Adopt     → 验证通过则入库
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "evolve.db"
        self._init_db()
        self._pending_candidates: list[SkillCandidate] = []

    def _init_db(self) -> None:
        """初始化进化数据库"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_id TEXT NOT NULL,
                user_message TEXT,
                agent_response TEXT,
                tools_used TEXT,
                tool_results TEXT,
                success INTEGER,
                duration_ms INTEGER,
                token_cost INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS skill_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                trigger_patterns TEXT,
                tool_chain TEXT,
                success_rate REAL,
                total_uses INTEGER,
                avg_duration_ms INTEGER,
                status TEXT DEFAULT 'candidate',
                created_at TEXT,
                adopted_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS ab_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT,
                variant_a TEXT,
                variant_b TEXT,
                winner TEXT,
                confidence REAL,
                tested_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    # ── Phase 1: Monitor ─────────────────────────────

    def record_trajectory(
        self,
        task_id: str,
        user_message: str,
        agent_response: str,
        tools_used: list[str],
        tool_results: list[dict],
        success: bool,
        duration_ms: int,
        token_cost: int = 0
    ) -> int:
        """记录一次任务轨迹"""
        entry = TrajectoryEntry(
            timestamp=datetime.now().isoformat(),
            task_id=task_id,
            user_message=user_message,
            agent_response=agent_response,
            tools_used=tools_used,
            tool_results=tool_results,
            success=success,
            duration_ms=duration_ms,
            token_cost=token_cost
        )
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO trajectories
            (timestamp, task_id, user_message, agent_response, tools_used, tool_results, success, duration_ms, token_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.timestamp, entry.task_id, entry.user_message, entry.agent_response,
            json.dumps(entry.tools_used), json.dumps(entry.tool_results),
            int(entry.success), entry.duration_ms, entry.token_cost
        ))
        traj_id = c.lastrowid
        conn.commit()
        conn.close()
        return traj_id

    def monitor_task(self, task_id: str) -> Optional[TrajectoryEntry]:
        """查询任务轨迹"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM trajectories WHERE task_id = ? ORDER BY id DESC LIMIT 1", (task_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return TrajectoryEntry(**dict(row))
        return None

    # ── Phase 2: Extract ──────────────────────────────

    def extract_patterns(self, min_successes: int = 3) -> list[SkillCandidate]:
        """从轨迹中提取成功模式"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # 找重复使用的工具链
        c.execute("""
            SELECT tools_used, COUNT(*) as cnt, AVG(duration_ms) as avg_ms, SUM(success) as successes
            FROM trajectories
            GROUP BY tools_used
            HAVING successes >= ?
            ORDER BY cnt DESC
            LIMIT 20
        """, (min_successes,))

        candidates = []
        for row in c.fetchall():
            tools = json.loads(row["tools_used"])
            if len(tools) < 2:
                continue  # 单工具不需要抽象

            # 生成候选名称
            tool_chain_key = " → ".join(tools[:3])
            name = f"auto_{tools[0]}_{tools[-1]}".lower().replace("_", "").replace("-", "")

            candidate = SkillCandidate(
                name=name,
                description=f"自动生成的技能链：{tool_chain_key}",
                trigger_patterns=self._extract_triggers(tools),
                tool_chain=[{"tool": t, "params": {}} for t in tools],
                success_rate=row["successes"] / row["cnt"],
                total_uses=row["cnt"],
                avg_duration_ms=int(row["avg_ms"]),
                source_session=datetime.now().strftime("%Y%m%d_%H%M%S")
            )
            candidates.append(candidate)

        conn.close()
        return candidates

    def _extract_triggers(self, tools: list[str]) -> list[str]:
        """从工具链提取触发词"""
        triggers = []
        trigger_map = {
            "read": ["读文件", "查看", "打开"],
            "write": ["写文件", "创建", "修改"],
            "search": ["搜索", "查找", "找"],
            "execute": ["执行", "运行", "命令"],
            "git": ["git", "提交", "推送"],
            "github": ["github", "仓库"],
            "web": ["搜索", "查", "找"],
        }
        for tool in tools:
            key = tool.lower().split("_")[0]
            if key in trigger_map:
                triggers.extend(trigger_map[key])
        return list(set(triggers))[:5]

    # ── Phase 3: Generate ─────────────────────────────

    def generate_skill(self, candidate: SkillCandidate) -> str:
        """生成 Skill.md 文件内容"""
        tool_chain_yaml = "\n".join(
            f"      - tool: '{c['tool']}'" for c in candidate.tool_chain
        )
        triggers_yaml = "\n".join(f"      - {t}" for t in candidate.trigger_patterns)

        skill_md = f"""---
name: {candidate.name}
description: {candidate.description}
trigger:
{triggers_yaml}
version: "1.0"
author: auto-evolved
created: {candidate.created_at or datetime.now().isoformat()}
performance:
  success_rate: {candidate.success_rate:.1%}
  total_uses: {candidate.total_uses}
  avg_duration_ms: {candidate.avg_duration_ms}
---

# {candidate.name}

{candidate.description}

## 工具链

```yaml
tool_chain:
{tool_chain_yaml}
```

## 使用示例

```
axonewt execute {candidate.name}
```

## 自动生成信息

- 来源：Evolve 系统自动提取
- 原始 session：{candidate.source_session}
- 验证状态：待验证
"""
        return skill_md

    # ── Phase 4: Test ────────────────────────────────

    def submit_for_test(self, candidate: SkillCandidate) -> None:
        """提交候选技能进行测试"""
        self._pending_candidates.append(candidate)

    def get_pending_candidates(self) -> list[SkillCandidate]:
        """获取待测试的候选"""
        return self._pending_candidates.copy()

    # ── Phase 5: Adopt ────────────────────────────────

    def adopt_skill(self, candidate: SkillCandidate, skill_content: str, skill_dir: Path) -> bool:
        """采纳技能 — 验证通过后写入技能库"""
        skill_file = skill_dir / f"{candidate.name}.md"
        try:
            skill_file.write_text(skill_content, encoding="utf-8")
            # 更新数据库
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO skill_candidates
                (name, description, trigger_patterns, tool_chain, success_rate, total_uses, avg_duration_ms, status, created_at, adopted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'adopted', ?, ?)
            """, (
                candidate.name, candidate.description,
                json.dumps(candidate.trigger_patterns), json.dumps(candidate.tool_chain),
                candidate.success_rate, candidate.total_uses, candidate.avg_duration_ms,
                datetime.now().isoformat(), datetime.now().isoformat()
            ))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    # ── 统计 ─────────────────────────────────────────

    def get_stats(self) -> dict:
        """获取进化统计"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as total, SUM(success) as successes, AVG(duration_ms) as avg_ms FROM trajectories")
        row = c.fetchone()
        c.execute("SELECT COUNT(*) as total FROM skill_candidates WHERE status = 'adopted'")
        adopted = c.fetchone()
        c.execute("SELECT COUNT(*) as total FROM ab_tests WHERE winner IS NOT NULL")
        tests = c.fetchone()
        conn.close()
        return {
            "total_trajectories": row["total"],
            "successful_trajectories": row["successes"] or 0,
            "avg_duration_ms": int(row["avg_ms"] or 0),
            "adopted_skills": adopted["total"],
            "completed_tests": tests["total"],
            "pending_candidates": len(self._pending_candidates),
        }
