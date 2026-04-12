"""
第四层：NeuralGraph（神经图谱）
================================

核心设计原则（Axonewt 特有）：
- 代码依赖关系的有向图
- 文件/模块健康度追踪
- 变化检测和影响分析
- 与现有 Mnemosyne-Dev 的 code_graph 兼容并增强

功能：
1. 维护代码节点（文件、模块、函数）和边（依赖关系）
2. 健康度评分：基于修复历史、测试覆盖率、变更频率
3. 影响分析：一个文件变化会影响哪些其他文件
4. 变化追踪：记录每次扫描的快照，检测漂移
5. 模式挖掘：发现频繁出问题的模块集群

图数据结构：
- Node: 文件/模块/函数
- Edge: import/call/inherit 依赖关系
- HealthRecord: 健康度历史记录
"""

import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict


CST = timezone(timedelta(hours=8))


@dataclass
class GraphNode:
    """图谱节点（代表文件、模块或函数）"""
    node_id: str = ""
    node_type: str = ""          # file | module | function | class
    name: str = ""               # 显示名称
    path: str = ""               # 文件路径（file 类型必填）
    language: str = ""           # 编程语言
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 健康度属性
    health_score: float = 1.0    # [0.0, 1.0] 越高越健康
    test_coverage: float = 0.0   # 测试覆盖率 [0.0, 1.0]
    change_frequency: float = 0.0  # 变更频率（每周变更次数）
    
    last_scanned: str = ""
    created_at: str = ""
    updated_at: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def health_status(self) -> str:
        """返回健康状态描述"""
        if self.health_score >= 0.8:
            return "healthy"
        elif self.health_score >= 0.5:
            return "warning"
        elif self.health_score >= 0.3:
            return "degraded"
        else:
            return "critical"


@dataclass
class GraphEdge:
    """图谱边（依赖关系）"""
    edge_id: str = ""
    source_id: str = ""          # 起点 node_id
    target_id: str = ""          # 终点 node_id
    edge_type: str = ""          # imports | calls | inherits | contains
    strength: float = 1.0        # 依赖强度 [0.0, 1.0]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class HealthRecord:
    """健康度记录（时间序列）"""
    record_id: str = ""
    node_id: str = ""
    health_score: float = 0.0
    test_coverage: float = 0.0
    repair_count: int = 0         # 该周期内修复次数
    change_count: int = 0         # 该周期内变更次数
    timestamp: str = ""
    notes: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)


class NeuralGraph:
    """
    第四层：神经图谱
    
    职责：
    - 管理代码依赖图
    - 追踪健康度和变化
    - 提供影响分析和模式挖掘
    - 与 Mnemosyne-Dev 的 code_graph 表兼容
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化神经图谱
        
        Args:
            db_path: SQLite 数据库路径。默认 D:/opennewt/data/neural_graph.db
        """
        if db_path is None:
            db_path = "D:/opennewt/data/neural_graph.db"
        
        self.db_path = db_path
        self._init_db()
        
        # 内存中的邻接表缓存
        self._adjacency: Dict[str, Set[str]] = defaultdict(set)
        self._reverse_adj: Dict[str, Set[str]] = defaultdict(set)
        self._nodes_cache: Dict[str, GraphNode] = {}
        self._cache_loaded = False
    
    def _init_db(self):
        """初始化数据库"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 节点表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT UNIQUE NOT NULL,
            node_type TEXT NOT NULL,
            name TEXT NOT NULL,
            path TEXT DEFAULT '',
            language TEXT DEFAULT '',
            health_score REAL DEFAULT 1.0,
            test_coverage REAL DEFAULT 0.0,
            change_frequency REAL DEFAULT 0.0,
            metadata TEXT DEFAULT '{}',
            last_scanned TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        
        # 边表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edge_id TEXT UNIQUE NOT NULL,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            strength REAL DEFAULT 1.0,
            metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_id) REFERENCES graph_nodes(node_id),
            FOREIGN KEY (target_id) REFERENCES graph_nodes(node_id)
        )
        """)
        
        # 健康度历史表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS health_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT UNIQUE NOT NULL,
            node_id TEXT NOT NULL,
            health_score REAL NOT NULL,
            test_coverage REAL DEFAULT 0.0,
            repair_count INTEGER DEFAULT 0,
            change_count INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL,
            notes TEXT DEFAULT '',
            FOREIGN KEY (node_id) REFERENCES graph_nodes(node_id)
        )
        """)
        
        # 变化快照表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS change_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT UNIQUE NOT NULL,
            node_id TEXT NOT NULL,
            file_hash TEXT,
            line_count INTEGER DEFAULT 0,
            complexity_estimate REAL DEFAULT 0.0,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (node_id) REFERENCES graph_nodes(node_id)
        )
        """)
        
        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_node_type ON graph_nodes(node_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_node_path ON graph_nodes(path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_source ON graph_edges(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_target ON graph_edges(target_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_node ON health_records(node_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_time ON health_records(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_node ON change_snapshots(node_id)")
        
        conn.commit()
        conn.close()
        
        print("[NeuralGraph] Database initialized: {}".format(self.db_path))
    
    def _load_cache(self):
        """加载邻接表到内存"""
        if self._cache_loaded:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 加载节点
        cursor.execute(
            "SELECT node_id, name, node_type, path, health_score FROM graph_nodes"
        )
        for row in cursor.fetchall():
            self._nodes_cache[row[0]] = GraphNode(
                node_id=row[0], name=row[1], node_type=row[2],
                path=row[3], health_score=row[4]
            )
        
        # 加载边到邻接表
        cursor.execute("SELECT source_id, target_id FROM graph_edges")
        for src, tgt in cursor.fetchall():
            self._adjacency[src].add(tgt)
            self._reverse_adj[tgt].add(src)
        
        conn.close()
        self._cache_loaded = True
        
        print("[NeuralGraph] Cache loaded: {} nodes, {} edges".format(
            len(self._nodes_cache), sum(len(v) for v in self._adjacency.values())
        ))
    
    def _generate_id(self, prefix: str) -> str:
        ts = datetime.now(CST).strftime("%Y%m%d%H%M%S%f")
        return "{}-{}".format(prefix, ts)
    
    # ========== 节点操作 ==========
    
    def add_node(self, node: GraphNode) -> GraphNode:
        """添加或更新节点"""
        if not node.node_id:
            node.node_id = self._generate_id("NODE")
        
        now = datetime.now(CST).isoformat()
        node.updated_at = now
        
        if not node.created_at:
            node.created_at = now
            node.last_scanned = now
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT OR REPLACE INTO graph_nodes 
                   (node_id, node_type, name, path, language,
                    health_score, test_coverage, change_frequency,
                    metadata, last_scanned, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    node.node_id, node.node_type, node.name, node.path,
                    node.language, node.health_score, node.test_coverage,
                    node.change_frequency, json.dumps(node.metadata),
                    node.last_scanned, node.created_at, node.updated_at,
                )
            )
            
            conn.commit()
            
            # 更新缓存
            self._nodes_cache[node.node_id] = node
            
            print("[NeuralGraph] Added node: {} ({})".format(node.node_id, node.name))
            
        finally:
            conn.close()
        
        return node
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """获取节点"""
        if node_id in self._nodes_cache:
            return self._nodes_cache[node_id]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM graph_nodes WHERE node_id = ?", (node_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        node = GraphNode(
            node_id=row[1], node_type=row[2], name=row[3],
            path=row[4], language=row[5],
            health_score=row[6], test_coverage=row[7],
            change_frequency=row[8], metadata=json.loads(row[9]),
            last_scanned=row[10], created_at=row[11], updated_at=row[12],
        )
        
        self._nodes_cache[node_id] = node
        return node
    
    def get_node_by_path(self, path: str) -> Optional[GraphNode]:
        """通过文件路径查找节点"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM graph_nodes WHERE path = ?", (path,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return GraphNode(
            node_id=row[1], node_type=row[2], name=row[3],
            path=row[4], language=row[5],
            health_score=row[6], test_coverage=row[7],
            change_frequency=row[8], metadata=json.loads(row[9]),
            last_scanned=row[10], created_at=row[11], updated_at=row[12],
        )
    
    def find_nodes(
        self,
        node_type: str = None,
        language: str = None,
        min_health: float = None,
        limit: int = 50,
    ) -> List[GraphNode]:
        """
        查找符合条件的节点
        
        Args:
            node_type: 节点类型筛选
            language: 编程语言筛选
            min_health: 最低健康度
            limit: 结果上限
            
        Returns:
            匹配的节点列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        conditions = []
        params = []
        
        if node_type:
            conditions.append("node_type = ?")
            params.append(node_type)
        
        if language:
            conditions.append("language = ?")
            params.append(language)
        
        if min_health is not None:
            conditions.append("health_score <= ?")
            params.append(min_health)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = "SELECT * FROM graph_nodes WHERE {} ORDER BY health_score ASC LIMIT {}".format(
            where_clause, limit
        )
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [
            GraphNode(
                node_id=r[1], node_type=r[2], name=r[3], path=r[4],
                language=r[5], health_score=r[6], test_coverage=r[7],
                change_frequency=r[8], metadata=json.loads(r[9]),
                last_scanned=r[10], created_at=r[11], updated_at=r[12],
            )
            for r in rows
        ]
    
    # ========== 边操作 ==========
    
    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        """添加依赖边"""
        if not edge.edge_id:
            edge.edge_id = self._generate_id("EDGE")
        
        if not edge.created_at:
            edge.created_at = datetime.now(CST).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT OR REPLACE INTO graph_edges
                   (edge_id, source_id, target_id, edge_type, strength, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge.edge_id, edge.source_id, edge.target_id,
                    edge.edge_type, edge.strength,
                    json.dumps(edge.metadata), edge.created_at,
                )
            )
            
            conn.commit()
            
            # 更新内存缓存
            self._adjacency[edge.source_id].add(edge.target_id)
            self._reverse_adj[edge.target_id].add(edge.source_id)
            
        finally:
            conn.close()
        
        return edge
    
    def get_dependencies(self, node_id: str, depth: int = 1) -> Set[str]:
        """
        获取节点的所有下游依赖（BFS）
        
        Args:
            node_id: 起点 ID
            depth: 遍历深度
            
        Returns:
            依赖节点 ID 集合
        """
        self._load_cache()
        
        visited = set()
        queue = [(node_id, 0)]
        
        while queue:
            current, d = queue.pop(0)
            
            if d > depth or current in visited:
                continue
            
            visited.add(current)
            
            for neighbor in self._adjacency.get(current, set()):
                if neighbor not in visited:
                    queue.append((neighbor, d + 1))
        
        visited.discard(node_id)  # 移除自身
        return visited
    
    def get_dependents(self, node_id: str, depth: int = 1) -> Set[str]:
        """
        获取所有依赖于该节点的上游节点（反向遍历）
        
        用于影响分析：如果这个文件变了，哪些文件会受影响。
        """
        self._load_cache()
        
        visited = set()
        queue = [(node_id, 0)]
        
        while queue:
            current, d = queue.pop(0)
            
            if d > depth or current in visited:
                continue
            
            visited.add(current)
            
            for neighbor in self._reverse_adj.get(current, set()):
                if neighbor not in visited:
                    queue.append((neighbor, d + 1))
        
        visited.discard(node_id)
        return visited
    
    def analyze_impact(self, node_id: str, max_depth: int = 3) -> Dict[str, Any]:
        """
        影响分析
        
        分析修改某个节点会对整个系统产生什么影响。
        
        Args:
            node_id: 要分析的节点
            max_depth: 最大分析深度
            
        Returns:
            影响分析报告
        """
        self._load_cache()
        
        node = self.get_node(node_id)
        if not node:
            return {"error": "Node not found: {}".format(node_id)}
        
        dependents = self.get_dependents(node_id, depth=max_depth)
        
        # 收集受影响的节点详情
        affected_nodes = []
        total_risk = 0.0
        
        for dep_id in dependents:
            dep_node = self.get_node(dep_id)
            if dep_node:
                # 受影响节点的健康度越低，风险越高
                risk_factor = (1.0 - dep_node.health_score) * dep_node.change_frequency
                affected_nodes.append({
                    "node_id": dep_id,
                    "name": dep_node.name,
                    "path": dep_node.path,
                    "health_score": dep_node.health_score,
                    "change_frequency": dep_node.change_frequency,
                    "risk_factor": round(risk_factor, 3),
                })
                total_risk += risk_factor
        
        # 按风险排序
        affected_nodes.sort(key=lambda x: x["risk_factor"], reverse=True)
        
        report = {
            "source_node": {
                "node_id": node_id,
                "name": node.name,
                "path": node.path,
                "health_score": node.health_score,
            },
            "affected_count": len(dependents),
            "total_risk_score": round(total_risk, 3),
            "affected_nodes": affected_nodes[:20],  # 最多显示20个
            "analysis_depth": max_depth,
            "analyzed_at": datetime.now(CST).isoformat(),
        }
        
        print("[NeuralGraph] Impact analysis for {}: {} nodes affected, risk={:.2f}".format(
            node_id, len(dependents), total_risk
        ))
        
        return report
    
    # ========== 健康度操作 ==========
    
    def record_health(self, record: HealthRecord):
        """记录一次健康度快照"""
        if not record.record_id:
            record.record_id = self._generate_id("HEALTH")
        
        if not record.timestamp:
            record.timestamp = datetime.now(CST).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO health_records
                   (record_id, node_id, health_score, test_coverage,
                    repair_count, change_count, timestamp, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.record_id, record.node_id, record.health_score,
                    record.test_coverage, record.repair_count,
                    record.change_count, record.timestamp, record.notes,
                )
            )
            
            # 同步更新节点的当前健康度
            cursor.execute(
                """UPDATE graph_nodes 
                   SET health_score = ?, test_coverage = ?, updated_at = ?
                   WHERE node_id = ?""",
                (record.health_score, record.test_coverage,
                 datetime.now(CST).isoformat(), record.node_id)
            )
            
            conn.commit()
        finally:
            conn.close()
    
    def get_health_history(
        self,
        node_id: str,
        days: int = 30,
    ) -> List[HealthRecord]:
        """获取指定节点的健康度历史"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = (datetime.now(CST) - timedelta(days=days)).isoformat()
        
        cursor.execute(
            """SELECT * FROM health_records 
               WHERE node_id = ? AND timestamp >= ?
               ORDER BY timestamp ASC""",
            (node_id, cutoff)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            HealthRecord(
                record_id=r[1], node_id=r[2], health_score=r[3],
                test_coverage=r[4], repair_count=r[5],
                change_count=r[6], timestamp=r[7], notes=r[8],
            )
            for r in rows
        ]
    
    def update_health_from_repair(
        self,
        node_id: str,
        success: bool,
        damage_type: str = "",
    ):
        """
        根据修复结果更新健康度
        
        成功修复 → 健康度微升
        失败修复 → 健康度下降
        """
        node = self.get_node(node_id)
        if not node:
            return
        
        # 计算新的健康度
        delta = 0.05 if success else -0.1
        new_health = max(0.0, min(1.0, node.health_score + delta))
        
        # 高频变化的模块降权更多
        frequency_penalty = node.change_frequency * 0.02
        new_health = max(0.0, new_health - frequency_penalty)
        
        # 记录历史
        record = HealthRecord(
            node_id=node_id,
            health_score=new_health,
            repair_count=1 if success else 0,
            change_count=1,
            notes="Repair result: {}, type: {}".format(
                "SUCCESS" if success else "FAILED", damage_type
            ),
        )
        
        self.record_health(record)
        
        print("[NeuralGraph] Updated health for {}: {:.2f} ({:+.2f})".format(
            node_id, new_health, delta
        ))
    
    # ========== 变化检测 ==========
    
    def take_snapshot(self, node_id: str, file_content_hash: str, line_count: int):
        """记录文件快照用于变化检测"""
        snapshot_id = self._generate_id("SNAP")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            """INSERT INTO change_snapshots
               (snapshot_id, node_id, file_hash, line_count, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (snapshot_id, node_id, file_content_hash, line_count,
             datetime.now(CST).isoformat())
        )
        
        conn.commit()
        conn.close()
    
    def detect_changes(self, node_id: str) -> Dict[str, Any]:
        """
        检测文件是否发生了变化
        
        对比最近两次快照的 hash。
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT snapshot_id, file_hash, line_count, timestamp 
               FROM change_snapshots 
               WHERE node_id = ? 
               ORDER BY timestamp DESC LIMIT 2""",
            (node_id,)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        if len(rows) < 2:
            return {"changed": False, "reason": "insufficient snapshots"}
        
        latest, previous = rows[0], rows[1]
        
        changed = latest[1] != previous[1]  # hash 不同则已变
        
        return {
            "changed": changed,
            "latest_snapshot": latest[0],
            "previous_snapshot": previous[0],
            "latest_hash": latest[1][:12],
            "previous_hash": previous[1][:12],
            "line_count_change": latest[2] - previous[2],
            "latest_time": latest[3],
            "previous_time": previous[3],
        }
    
    # ========== 模式挖掘 ==========
    
    def find_problem_clusters(self, threshold: float = 0.4) -> List[Dict]:
        """
        发现问题集群
        
        找出低健康度的密集连接区域——这些是系统的"痛点"区域。
        """
        low_health_nodes = self.find_nodes(min_health=threshold)
        
        if len(low_health_nodes) < 2:
            return []
        
        clusters = []
        visited = set()
        
        for node in low_health_nodes:
            if node.node_id in visited:
                continue
            
            # BFS 找连通的低健康度组件
            cluster = [node]
            cluster_ids = {node.node_id}
            visited.add(node.node_id)
            
            queue = [node.node_id]
            while queue:
                current = queue.pop(0)
                
                for neighbor in self._adjacency.get(current, set()):
                    if neighbor not in visited and neighbor in {
                        n.node_id for n in low_health_nodes
                    }:
                        visited.add(neighbor)
                        cluster_ids.add(neighbor)
                        
                        n = self.get_node(neighbor)
                        if n:
                            cluster.append(n)
                        queue.append(neighbor)
            
            if len(cluster) >= 2:  # 至少2个节点才算集群
                avg_health = sum(n.health_score for n in cluster) / len(cluster)
                
                clusters.append({
                    "cluster_size": len(cluster),
                    "avg_health": round(avg_health, 3),
                    "nodes": [
                        {
                            "node_id": n.node_id,
                            "name": n.name,
                            "path": n.path,
                            "health_score": n.health_score,
                        }
                        for n in sorted(cluster, key=lambda x: x.health_score)
                    ],
                })
        
        # 按严重程度排序
        clusters.sort(key=lambda c: c["avg_health"])
        
        print("[NeuralGraph] Found {} problem clusters (health < {:.0%})".format(
            len(clusters), threshold
        ))
        
        return clusters
    
    # ========== 统计 ==========
    
    def get_stats(self) -> Dict:
        """获取图谱统计信息"""
        self._load_cache()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM graph_nodes")
        node_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM graph_edges")
        edge_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT AVG(health_score), MIN(health_score) FROM graph_nodes")
        avg_health, min_health = cursor.fetchone()
        
        cursor.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE health_score < 0.5"
        )
        unhealthy_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM health_records")
        health_record_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_nodes": node_count,
            "total_edges": edge_count,
            "avg_health_score": round(avg_health or 0, 3),
            "min_health_score": min_health or 0,
            "unhealthy_nodes": unhealthy_count,
            "health_records": health_record_count,
            "db_path": self.db_path,
        }
