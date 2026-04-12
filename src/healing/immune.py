"""
免疫记忆 - 防止重复犯错（火蜥蜴断尾后再生的记忆）
=====================================================

基于 SQLite 的持久化免疫记忆系统。

核心概念：
- 错误签名（signature）: 错误的唯一标识
- 免疫阈值: 成功修复同一错误 N 次后，自动免疫
- 免疫记录: 记录错误模式及其修复方案

免疫机制：
  首次遇到错误 → 诊断 + 修复 → 学习
  再次遇到     → 检查免疫 → 若已免疫直接应用修复方案
  持续成功     → 免疫强度增加
  修复失败     → 免疫强度降低
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .detector import ErrorReport
from .diagnostician import DiagnosticResult

logger = logging.getLogger(__name__)

# 默认免疫阈值：同一错误成功修复 3 次后自动免疫
DEFAULT_IMMUNITY_THRESHOLD = 3


@dataclass
class ImmuneRecord:
    """
    免疫记录

    记录一个已学习的错误模式及其修复方案。
    """
    id: int
    error_signature: str
    error_type: str
    root_cause: str
    fix_pattern: str
    fix_type: str
    success_count: int
    failure_count: int
    immunity_threshold: int
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def is_immune(self) -> bool:
        """是否已完全免疫"""
        return self.success_count >= self.immunity_threshold

    @property
    def immunity_strength(self) -> float:
        """
        免疫强度（0.0 - 1.0）

        success_count / immunity_threshold，封顶 1.0
        """
        return min(self.success_count / max(self.immunity_threshold, 1), 1.0)

    @property
    def confidence(self) -> float:
        """
        修复方案的置信度

        基于成功/失败次数计算。
        """
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5  # 无数据时返回中性值
        return self.success_count / total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "error_signature": self.error_signature,
            "error_type": self.error_type,
            "root_cause": self.root_cause,
            "fix_pattern": self.fix_pattern,
            "fix_type": self.fix_type,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "immunity_threshold": self.immunity_threshold,
            "is_immune": self.is_immune,
            "immunity_strength": self.immunity_strength,
            "confidence": self.confidence,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
        }


class ImmuneMemory:
    """
    免疫记忆

    SQLite 持久化存储，跨会话保留免疫记忆。
    支持错误模式的学习、查询和免疫检查。
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        immunity_threshold: int = DEFAULT_IMMUNITY_THRESHOLD,
    ):
        """
        Args:
            db_path: SQLite 数据库路径（默认 ~/.axonewt/immune.db）
            immunity_threshold: 免疫阈值（成功修复次数）
        """
        if db_path is None:
            db_path = str(Path.home() / ".axonewt" / "immune.db")

        self.db_path = db_path
        self.immunity_threshold = immunity_threshold

        # 确保目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS immune_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_signature TEXT UNIQUE NOT NULL,
                    error_type TEXT NOT NULL,
                    root_cause TEXT DEFAULT '',
                    fix_pattern TEXT DEFAULT '',
                    fix_type TEXT DEFAULT 'manual',
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    immunity_threshold INTEGER DEFAULT 3,
                    last_success TEXT,
                    last_failure TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_error_signature
                ON immune_patterns(error_signature)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_error_type
                ON immune_patterns(error_type)
            """)
            conn.commit()
        finally:
            conn.close()

    def is_immune(self, error_report: ErrorReport) -> bool:
        """
        检查是否已免疫

        Args:
            error_report: 错误报告

        Returns:
            是否已免疫（True = 直接应用已知修复方案）
        """
        signature = error_report.get_signature()
        record = self._get_record(signature)

        if record is None:
            return False

        return record.is_immune

    def get_immunity(self, error_report: ErrorReport) -> Optional[ImmuneRecord]:
        """
        获取免疫记录（如果存在）

        Args:
            error_report: 错误报告

        Returns:
            免疫记录（如果存在且有效），否则 None
        """
        signature = error_report.get_signature()
        return self._get_record(signature)

    def learn(
        self,
        error_report: ErrorReport,
        diagnostic: DiagnosticResult,
        success: bool = True,
    ):
        """
        学习新的错误模式

        如果修复成功，增加成功计数；失败则增加失败计数。

        Args:
            error_report: 错误报告
            diagnostic: 诊断结果
            success: 修复是否成功
        """
        signature = error_report.get_signature()
        now = datetime.utcnow().isoformat() + "Z"

        conn = sqlite3.connect(self.db_path)
        try:
            # 尝试更新现有记录
            cursor = conn.execute(
                "SELECT id FROM immune_patterns WHERE error_signature = ?",
                (signature,),
            )
            existing = cursor.fetchone()

            if existing:
                if success:
                    conn.execute("""
                        UPDATE immune_patterns
                        SET success_count = success_count + 1,
                            last_success = ?,
                            root_cause = ?,
                            fix_pattern = ?,
                            fix_type = ?,
                            updated_at = ?
                        WHERE error_signature = ?
                    """, (
                        now,
                        diagnostic.root_cause,
                        diagnostic.fix_suggestion,
                        diagnostic.fix_type,
                        now,
                        signature,
                    ))
                else:
                    conn.execute("""
                        UPDATE immune_patterns
                        SET failure_count = failure_count + 1,
                            last_failure = ?,
                            updated_at = ?
                        WHERE error_signature = ?
                    """, (now, now, signature))
            else:
                conn.execute("""
                    INSERT INTO immune_patterns
                    (error_signature, error_type, root_cause, fix_pattern,
                     fix_type, success_count, failure_count,
                     immunity_threshold, last_success, last_failure,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signature,
                    error_report.error_type.value,
                    diagnostic.root_cause,
                    diagnostic.fix_suggestion,
                    diagnostic.fix_type,
                    1 if success else 0,
                    0 if success else 1,
                    self.immunity_threshold,
                    now if success else None,
                    None if success else now,
                    now,
                    now,
                ))

            conn.commit()
        finally:
            conn.close()

    def get_recommended_fix(
        self,
        error_report: ErrorReport,
    ) -> Optional[Dict[str, Any]]:
        """
        获取推荐的修复方案

        如果已免疫或存在高置信度记录，返回推荐的修复方案。

        Args:
            error_report: 错误报告

        Returns:
            推荐修复方案字典（如果存在），否则 None
        """
        record = self.get_immunity(error_report)

        if record is None:
            return None

        return {
            "source": "immune_memory",
            "is_immune": record.is_immune,
            "immunity_strength": record.immunity_strength,
            "confidence": record.confidence,
            "success_count": record.success_count,
            "root_cause": record.root_cause,
            "fix_pattern": record.fix_pattern,
            "fix_type": record.fix_type,
        }

    def search_similar(
        self,
        error_report: ErrorReport,
        limit: int = 5,
    ) -> List[ImmuneRecord]:
        """
        搜索相似的错误记录

        基于错误类型进行模糊匹配。

        Args:
            error_report: 错误报告
            limit: 最大返回数量

        Returns:
            相似记录列表
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                SELECT id, error_signature, error_type, root_cause,
                       fix_pattern, fix_type, success_count, failure_count,
                       immunity_threshold, last_success, last_failure,
                       created_at, updated_at
                FROM immune_patterns
                WHERE error_type = ?
                ORDER BY success_count DESC, failure_count ASC
                LIMIT ?
            """, (error_report.error_type.value, limit))

            records = []
            for row in cursor.fetchall():
                records.append(self._row_to_record(row))

            return records
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """
        获取免疫记忆统计

        Returns:
            统计信息字典
        """
        conn = sqlite3.connect(self.db_path)
        try:
            # 总记录数
            total = conn.execute(
                "SELECT COUNT(*) FROM immune_patterns"
            ).fetchone()[0]

            # 已免疫数量
            immune_count = conn.execute(
                f"SELECT COUNT(*) FROM immune_patterns "
                f"WHERE success_count >= {self.immunity_threshold}"
            ).fetchone()[0]

            # 按错误类型统计
            type_stats = conn.execute("""
                SELECT error_type, COUNT(*), SUM(success_count), SUM(failure_count)
                FROM immune_patterns
                GROUP BY error_type
            """).fetchall()

            return {
                "total_patterns": total,
                "immune_patterns": immune_count,
                "immunity_coverage": immune_count / max(total, 1) * 100,
                "by_error_type": [
                    {
                        "type": row[0],
                        "count": row[1],
                        "total_successes": row[2],
                        "total_failures": row[3],
                    }
                    for row in type_stats
                ],
                "db_path": self.db_path,
            }
        finally:
            conn.close()

    def clear(self):
        """清除所有免疫记忆（慎用）"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM immune_patterns")
            conn.execute("VACUUM")
            conn.commit()
            logger.info("[ImmuneMemory] 已清除所有免疫记忆")
        finally:
            conn.close()

    def _get_record(self, signature: str) -> Optional[ImmuneRecord]:
        """根据签名获取免疫记录"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("""
                SELECT id, error_signature, error_type, root_cause,
                       fix_pattern, fix_type, success_count, failure_count,
                       immunity_threshold, last_success, last_failure,
                       created_at, updated_at
                FROM immune_patterns
                WHERE error_signature = ?
            """, (signature,))

            row = cursor.fetchone()
            if row:
                return self._row_to_record(row)
            return None
        finally:
            conn.close()

    def _row_to_record(self, row) -> ImmuneRecord:
        """将数据库行转换为 ImmuneRecord"""
        return ImmuneRecord(
            id=row[0],
            error_signature=row[1],
            error_type=row[2],
            root_cause=row[3],
            fix_pattern=row[4],
            fix_type=row[5],
            success_count=row[6],
            failure_count=row[7],
            immunity_threshold=row[8],
            last_success=row[9],
            last_failure=row[10],
            created_at=row[11] if len(row) > 11 else "",
            updated_at=row[12] if len(row) > 12 else "",
        )
