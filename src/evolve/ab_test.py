"""
AB Tester — 技能 A/B 测试框架

用于测试不同 Skill 版本的效率和成功率
记录指标：成功率、耗时、Token 消耗
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class ABResult:
    """A/B 测试结果"""
    test_id: str
    skill_a: str
    skill_b: str
    task: str
    winner: str  # "a" / "b" / "tie"
    score_a: float
    score_b: float
    duration_a: float
    duration_b: float
    timestamp: float = field(default_factory=time.time)


class ABTester:
    """
    A/B 测试器

    用法:
    1. 定义两个版本的 Skill 函数
    2. 用相同任务分别运行
    3. 比较评分，选出优胜者
    """

    def __init__(self, results_dir: Path | str = ".axonewt_ab_tests"):
        self._dir = Path(results_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        task: str,
        skill_a_fn: Callable,
        skill_b_fn: Callable,
        skill_a_name: str = "A",
        skill_b_name: str = "B",
    ) -> ABResult:
        """运行 A/B 测试"""
        test_id = str(uuid.uuid4())[:12]

        # 运行版本 A
        start_a = time.time()
        try:
            result_a = skill_a_fn()
            duration_a = time.time() - start_a
            success_a = result_a.get("success", False)
            score_a = self._calculate_score(success_a, duration_a, result_a)
        except Exception as e:
            duration_a = time.time() - start_a
            score_a = 0.0
            result_a = {"error": str(e)}

        # 运行版本 B
        start_b = time.time()
        try:
            result_b = skill_b_fn()
            duration_b = time.time() - start_b
            success_b = result_b.get("success", False)
            score_b = self._calculate_score(success_b, duration_b, result_b)
        except Exception as e:
            duration_b = time.time() - start_b
            score_b = 0.0
            result_b = {"error": str(e)}

        # 判断胜负
        if score_a > score_b:
            winner = "a"
        elif score_b > score_a:
            winner = "b"
        else:
            winner = "tie"

        ab_result = ABResult(
            test_id=test_id,
            skill_a=skill_a_name,
            skill_b=skill_b_name,
            task=task,
            winner=winner,
            score_a=score_a,
            score_b=score_b,
            duration_a=duration_a,
            duration_b=duration_b,
        )

        # 保存结果
        path = self._dir / f"{test_id}.json"
        path.write_text(
            json.dumps(
                {
                    "test_id": ab_result.test_id,
                    "skill_a": ab_result.skill_a,
                    "skill_b": ab_result.skill_b,
                    "task": ab_result.task,
                    "winner": ab_result.winner,
                    "score_a": ab_result.score_a,
                    "score_b": ab_result.score_b,
                    "duration_a": ab_result.duration_a,
                    "duration_b": ab_result.duration_b,
                    "timestamp": ab_result.timestamp,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return ab_result

    def _calculate_score(self, success: bool, duration: float, result: Any) -> float:
        """计算评分：成功=100分，每秒-5分"""
        if not success:
            return 0.0
        return max(0.0, 100.0 - duration * 5)

    def get_leaderboard(self, limit: int = 20) -> list[dict]:
        """获取 Skill 胜率排行榜"""
        paths = sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        skills: dict[str, dict] = {}
        for p in paths[:limit * 5]:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                for side in ["a", "b"]:
                    name = data[f"skill_{side}"]
                    if name not in skills:
                        skills[name] = {"wins": 0, "losses": 0, "ties": 0, "total": 0, "total_score": 0.0}
                    skills[name]["total"] += 1
                    skills[name]["total_score"] += data[f"score_{side}"]
                    if data["winner"] == side:
                        skills[name]["wins"] += 1
                    elif data["winner"] == "tie":
                        skills[name]["ties"] += 1
                    else:
                        skills[name]["losses"] += 1
            except Exception:
                continue

        leaderboard = []
        for name, stats in skills.items():
            win_rate = stats["wins"] / stats["total"] if stats["total"] > 0 else 0
            avg_score = stats["total_score"] / stats["total"] if stats["total"] > 0 else 0
            leaderboard.append({
                "skill": name,
                "win_rate": round(win_rate * 100, 1),
                "avg_score": round(avg_score, 1),
                "total_tests": stats["total"],
                "wins": stats["wins"],
                "losses": stats["losses"],
            })

        leaderboard.sort(key=lambda x: x["win_rate"], reverse=True)
        return leaderboard[:limit]
