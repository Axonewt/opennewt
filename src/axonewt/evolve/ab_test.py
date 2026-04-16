"""
Axonewt A/B Testing Framework — 技能对比测试
============================================
"""

import json
import random
import sqlite3
from pathlib import Path
from typing import Callable, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import math


@dataclass
class ABTestResult:
    """A/B 测试结果"""
    skill_name: str
    variant_a: str
    variant_b: str
    winner: Optional[str]
    confidence: float
    tested_at: str
    samples_a: int = 0
    samples_b: int = 0
    success_rate_a: float = 0.0
    success_rate_b: float = 0.0


class ABTester:
    """
    A/B 测试框架 — 验证技能变体的实际效果

    使用两层方法：
    1. 频率学派：A/B 测试（需足够样本）
    2. 贝叶斯学派：Thompson 采样（样本少时更可靠）
    """

    def __init__(self, db_path: str = "./data/evolve.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def create_test(
        self,
        skill_name: str,
        variant_a: str,  # 技能A的内容
        variant_b: str,  # 技能B的内容
    ) -> int:
        """创建新的 A/B 测试"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS ab_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT,
                variant_a TEXT,
                variant_b TEXT,
                variant_a_successes INTEGER DEFAULT 0,
                variant_a_trials INTEGER DEFAULT 0,
                variant_b_successes INTEGER DEFAULT 0,
                variant_b_trials INTEGER DEFAULT 0,
                winner TEXT,
                confidence REAL DEFAULT 0.0,
                tested_at TEXT
            )
        """)
        c.execute("""
            INSERT INTO ab_tests (skill_name, variant_a, variant_b, tested_at)
            VALUES (?, ?, ?, ?)
        """, (skill_name, variant_a, variant_b, datetime.now().isoformat()))
        test_id = c.lastrowid
        conn.commit()
        conn.close()
        return test_id

    def record_result(self, test_id: int, variant: str, success: bool) -> None:
        """记录单次测试结果"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        col_success = f"variant_{variant}_successes"
        col_trials = f"variant_{variant}_trials"
        c.execute(f"UPDATE ab_tests SET {col_success} = {col_success} + ?, {col_trials} = {col_trials} + 1 WHERE id = ?",
                  (int(success), test_id))
        conn.commit()
        conn.close()

    def get_recommendation(self, test_id: int) -> str:
        """
        Thompson 采样推荐 — 样本少时用贝叶斯，样本多时用频率学
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM ab_tests WHERE id = ?", (test_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return "a"  # 默认选 A

        a_trials = row[5]  # variant_a_trials
        b_trials = row[7]  # variant_b_trials
        a_successes = row[4]  # variant_a_successes
        b_successes = row[6]  # variant_b_successes

        total = a_trials + b_trials

        if total < 10:
            # 样本太少，用 Thompson 采样
            alpha_a, beta_a = a_successes + 1, max(1, a_trials - a_successes + 1)
            alpha_b, beta_b = b_successes + 1, max(1, b_trials - b_successes + 1)
            # 简化 Beta 分布采样
            sample_a = (a_successes + 1) / (a_trials + 2) + random.gauss(0, 0.3)
            sample_b = (b_successes + 1) / (b_trials + 2) + random.gauss(0, 0.3)
            return "a" if sample_a >= sample_b else "b"
        else:
            # 样本足够，用胜率比较
            rate_a = a_successes / a_trials if a_trials > 0 else 0
            rate_b = b_successes / b_trials if b_trials > 0 else 0
            return "a" if rate_a >= rate_b else "b"

    def finalize_test(self, test_id: int) -> ABTestResult:
        """完成测试，计算胜者和置信度"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM ab_tests WHERE id = ?", (test_id,))
        row = c.fetchone()
        conn.close()

        a_trials = row[5]
        b_trials = row[7]
        a_successes = row[4]
        b_successes = row[6]

        rate_a = a_successes / a_trials if a_trials > 0 else 0
        rate_b = b_successes / b_trials if b_trials > 0 else 0
        total = a_trials + b_trials

        # Z-score 置信度
        if total > 30:
            pooled = (a_successes + b_successes) / total
            se = math.sqrt(pooled * (1 - pooled) * (1/a_trials + 1/b_trials)) if a_trials > 0 and b_trials > 0 else 0.5
            z = abs(rate_a - rate_b) / max(se, 0.001)
            confidence = min(1.0, 1 - 2 * (1 / (1 + math.exp(z * 0.5)))) if z > 0 else 0.0
        else:
            confidence = total / 100  # 样本少则置信度低

        winner = "a" if rate_a > rate_b else "b" if rate_b > rate_a else None

        # 更新数据库
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE ab_tests SET winner = ?, confidence = ? WHERE id = ?",
                  (winner, confidence, test_id))
        conn.commit()
        conn.close()

        return ABTestResult(
            skill_name=row[1],
            variant_a=row[2],
            variant_b=row[3],
            winner=winner,
            confidence=confidence,
            tested_at=row[8],
            samples_a=a_trials,
            samples_b=b_trials,
            success_rate_a=rate_a,
            success_rate_b=rate_b
        )
