"""
第二层：ProjectContext（项目上下文）
===================================

核心设计原则：
- 按需加载，不常驻内存
- 通过相似度检索召回最相关的上下文
- 存储任务相关的具体文件、决策、背景

功能：
1. 基于关键词/标签的上下文检索（轻量，无需向量库）
2. 支持多种上下文类型：文件、决策、偏好、代码片段
3. 自动关联相关条目
4. 上下文生命周期管理

上下文类型：
- file: 文件路径及其摘要
- decision: 技术决策记录
- preference: 用户/项目偏好
- snippet: 代码片段或配置示例
- note: 自由格式笔记
"""

import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


CST = timezone(timedelta(hours=8))


@dataclass
class ContextEntry:
    """项目上下文条目"""
    entry_id: str = ""
    context_type: str = ""      # file | decision | preference | snippet | note
    title: str = ""
    content: str = ""
    summary: str = ""           # 短摘要（用于快速浏览）
    tags: List[str] = field(default_factory=list)
    source_path: str = ""       # 关联的文件路径
    related_ids: List[str] = field(default_factory=list)  # 关联的其他上下文 ID
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    access_count: int = 0       # 访问次数（用于热度排序）
    last_accessed: str = ""     # 最后访问时间
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        return d
    
    def relevance_score(self, query_terms: List[str]) -> float:
        """
        计算与查询的相关性分数
        
        基于词频 + 标签匹配 + 访问热度的混合评分。
        """
        score = 0.0
        
        searchable = "{} {} {} {}".format(
            self.title, self.summary, self.content, " ".join(self.tags)
        ).lower()
        
        query_text = " ".join(query_terms).lower()
        
        for term in query_terms:
            term_lower = term.lower()
            
            # 标题精确匹配权重最高
            if term_lower in self.title.lower():
                score += 5.0
            
            # 摘要匹配
            elif term_lower in self.summary.lower():
                score += 3.0
            
            # 标签匹配
            elif any(term_lower in t.lower() for t in self.tags):
                score += 2.5
            
            # 内容包含
            elif term_lower in searchable:
                score += 1.0
        
        # 热度加分：最近被频繁访问的条目更相关
        if self.access_count > 0:
            score += min(self.access_count * 0.2, 2.0)
        
        return score


class ProjectContext:
    """
    第二层：项目上下文管理器
    
    职责：
    - 存储和检索任务相关的具体上下文
    - 基于相似度的按需召回
    - 管理上下文的生命周期
    - 维护上下文之间的关联关系
    """
    
    def __init__(self, db_path: str = None, workspace_root: str = None):
        """
        初始化项目上下文管理器
        
        Args:
            db_path: SQLite 数据库路径。默认 data/project_context.db
            workspace_root: 项目根目录（用于解析相对路径）
        """
        if db_path is None:
            db_path = "D:/opennewt/data/project_context.db"
        
        self.db_path = db_path
        self.workspace_root = workspace_root or ""
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表结构"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 主表：上下文条目
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS context_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT UNIQUE NOT NULL,
            context_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            source_path TEXT DEFAULT '',
            related_ids TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            access_count INTEGER DEFAULT 0,
            last_accessed TEXT
        )
        """)
        
        # 全文搜索索引（使用 FTS5）
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS context_fts USING fts5(
            entry_id,
            title,
            summary,
            content,
            tags,
            tokenize='porter unicode61'
        )
        """)
        
        # 触发器：自动同步 FTS 索引
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS ctx_ai AFTER INSERT ON context_entries BEGIN
            INSERT INTO context_fts(entry_id, title, summary, content, tags)
            VALUES (new.entry_id, new.title, new.summary, new.content, new.tags);
        END
        """)
        
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS ctx_ad AFTER DELETE ON context_entries BEGIN
            DELETE FROM context_fts WHERE entry_id = old.entry_id;
        END
        """)
        
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS ctx_au AFTER UPDATE ON context_entries BEGIN
            DELETE FROM context_fts WHERE entry_id = old.entry_id;
            INSERT INTO context_fts(entry_id, title, summary, content, tags)
            VALUES (new.entry_id, new.title, new.summary, new.content, new.tags);
        END
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ctx_type ON context_entries(context_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ctx_tags ON context_entries(tags)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ctx_updated ON context_entries(updated_at)")
        
        conn.commit()
        conn.close()
        
        print("[ProjectContext] Database initialized: {}".format(self.db_path))
    
    def _generate_id(self) -> str:
        """生成唯一 ID"""
        timestamp = datetime.now(CST).strftime("%Y%m%d%H%M%S%f")
        return "CTX-{}".format(timestamp)
    
    def add(
        self,
        context_type: str,
        title: str,
        content: str = "",
        summary: str = "",
        tags: List[str] = None,
        source_path: str = "",
        related_ids: List[str] = None,
        metadata: Dict = None,
    ) -> ContextEntry:
        """
        添加新的上下文条目
        
        Args:
            context_type: 上下文类型 (file|decision|preference|snippet|note)
            title: 标题
            content: 完整内容
            summary: 短摘要（如不提供则自动截取前200字符）
            tags: 标签列表
            source_path: 关联文件路径
            related_ids: 关联条目 ID 列表
            metadata: 额外元数据
            
        Returns:
            创建的 ContextEntry
        """
        now = datetime.now(CST).isoformat()
        entry_id = self._generate_id()
        
        # 自动生成摘要
        if not summary and content:
            summary = content[:200].replace("\n", " ")
        
        entry = ContextEntry(
            entry_id=entry_id,
            context_type=context_type,
            title=title,
            content=content,
            summary=summary,
            tags=tags or [],
            source_path=source_path,
            related_ids=related_ids or [],
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO context_entries 
                   (entry_id, context_type, title, content, summary, tags,
                    source_path, related_ids, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.entry_id, entry.context_type, entry.title,
                    entry.content, entry.summary, json.dumps(entry.tags),
                    entry.source_path, json.dumps(entry.related_ids),
                    json.dumps(entry.metadata), entry.created_at, entry.updated_at,
                )
            )
            
            conn.commit()
            print("[ProjectContext] Added [{}] {}: {}".format(
                context_type, entry_id, title
            ))
        finally:
            conn.close()
        
        return entry
    
    def search(
        self,
        query: str,
        context_types: List[str] = None,
        limit: int = 10,
        require_fresh_days: int = None,
    ) -> List[ContextEntry]:
        """
        全文搜索上下文
        
        使用 SQLite FTS5 进行全文检索。
        
        Args:
            query: 搜索查询字符串
            context_types: 限定上下文类型（None 表示全部）
            limit: 返回结果上限
            require_fresh_days: 只返回 N 天内更新的条目
            
        Returns:
            匹配的上下文列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # FTS5 搜索
            where_clauses = []
            params = []
            
            base_query = """
                SELECT e.entry_id, e.context_type, e.title, e.content,
                       e.summary, e.tags, e.source_path, e.related_ids,
                       e.metadata, e.created_at, e.updated_at,
                       e.access_count, e.last_accessed,
                       rank
                FROM context_entries e
                JOIN context_fts fts ON e.entry_id = fts.entry_id
                WHERE context_fts MATCH ?
            """
            params.append(query)
            
            if context_types:
                placeholders = ",".join(["?" for _ in context_types])
                base_query += " AND e.context_type IN ({})".format(placeholders)
                params.extend(context_types)
            
            if require_fresh_days is not None:
                cutoff = (datetime.now(CST) - timedelta(days=require_fresh_days)).isoformat()
                base_query += " AND e.updated_at >= ?"
                params.append(cutoff)
            
            base_query += " ORDER BY rank LIMIT ?"
            params.append(limit)
            
            cursor.execute(base_query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(ContextEntry(
                    entry_id=row[0],
                    context_type=row[1],
                    title=row[2],
                    content=row[3],
                    summary=row[4],
                    tags=json.loads(row[5]),
                    source_path=row[6],
                    related_ids=json.loads(row[7]),
                    metadata=json.loads(row[8]),
                    created_at=row[9],
                    updated_at=row[10],
                    access_count=row[11],
                    last_accessed=row[12] or "",
                ))
            
            # 更新访问计数
            if results:
                ids = [r.entry_id for r in results]
                now = datetime.now(CST).isoformat()
                
                for eid in ids:
                    cursor.execute(
                        """UPDATE context_entries 
                           SET access_count = access_count + 1, 
                               last_accessed = ?
                           WHERE entry_id = ?""",
                        (now, eid)
                    )
                conn.commit()
            
            print("[ProjectContext] Search '{}' returned {} results".format(
                query, len(results)
            ))
            
            return results
            
        finally:
            conn.close()
    
    def get_by_id(self, entry_id: str) -> Optional[ContextEntry]:
        """根据 ID 获取上下文条目"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM context_entries WHERE entry_id = ?", (entry_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return ContextEntry(
            entry_id=row[1], context_type=row[2], title=row[3],
            content=row[4], summary=row[5], tags=json.loads(row[6]),
            source_path=row[7], related_ids=json.loads(row[8]),
            metadata=json.loads(row[9]), created_at=row[10],
            updated_at=row[11], access_count=row[12],
            last_accessed=row[13] or "",
        )
    
    def get_by_type(self, context_type: str, limit: int = 20) -> List[ContextEntry]:
        """获取指定类型的所有上下文条目"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT * FROM context_entries 
               WHERE context_type = ? 
               ORDER BY updated_at DESC LIMIT ?""",
            (context_type, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [
            ContextEntry(
                entry_id=r[1], context_type=r[2], title=r[3],
                content=r[4], summary=r[5], tags=json.loads(r[6]),
                source_path=r[7], related_ids=json.loads(r[8]),
                metadata=json.loads(r[9]), created_at=r[10],
                updated_at=r[11], access_count=r[12],
                last_accessed=r[13] or "",
            )
            for r in rows
        ]
    
    def update(self, entry_id: str, **kwargs) -> bool:
        """更新上下文条目"""
        allowed_fields = {
            "title", "content", "summary", "tags",
            "source_path", "related_ids", "metadata"
        }
        
        updates = {}
        for k, v in kwargs.items():
            if k in allowed_fields:
                updates[k] = v
        
        if not updates:
            return False
        
        updates["updated_at"] = datetime.now(CST).isoformat()
        
        set_clauses = []
        values = []
        
        for k, v in updates.items():
            set_clauses.append("{} = ?".format(k))
            values.append(json.dumps(v) if isinstance(v, (list, dict)) else v)
        
        values.append(entry_id)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE context_entries SET {} WHERE entry_id = ?".format(
                ", ".join(set_clauses)
            ),
            values
        )
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def delete(self, entry_id: str) -> bool:
        """删除上下文条目"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM context_entries WHERE entry_id = ?", (entry_id,))
        success = cursor.rowcount > 0
        
        conn.commit()
        conn.close()
        
        return success
    
    def link(self, entry_id_1: str, entry_id_2: str) -> bool:
        """建立两个上下文条目之间的双向关联"""
        entry1 = self.get_by_id(entry_id_1)
        entry2 = self.get_by_id(entry_id_2)
        
        if not entry1 or not entry2:
            return False
        
        # 双向添加
        if entry_id_2 not in entry1.related_ids:
            entry1.related_ids.append(entry_id_2)
            self.update(entry_id_1, related_ids=entry1.related_ids)
        
        if entry_id_1 not in entry2.related_ids:
            entry2.related_ids.append(entry_id_1)
            self.update(entry_id_2, related_ids=entry2.related_ids)
        
        return True
    
    def get_related(self, entry_id: str, depth: int = 1) -> List[ContextEntry]:
        """
        获取关联条目（BFS 遍历）
        
        Args:
            entry_id: 起点 ID
            depth: 关联深度
            
        Returns:
            关联条目列表
        """
        visited = {entry_id}
        queue = [entry_id]
        current_depth = 0
        results = []
        
        while queue and current_depth < depth:
            level_size = len(queue)
            
            for _ in range(level_size):
                current_id = queue.pop(0)
                entry = self.get_by_id(current_id)
                
                if entry and current_id != entry_id:
                    results.append(entry)
                
                if entry:
                    for rid in entry.related_ids:
                        if rid not in visited:
                            visited.add(rid)
                            queue.append(rid)
            
            current_depth += 1
        
        return results
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM context_entries")
        total = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT context_type, COUNT(*) FROM context_entries GROUP BY context_type"
        )
        type_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute("SELECT SUM(access_count) FROM context_entries")
        total_accesses = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            "total_entries": total,
            "by_type": type_counts,
            "total_accesses": total_accesses,
            "db_path": self.db_path,
        }
