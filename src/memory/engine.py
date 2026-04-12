"""
四层记忆引擎（QuadMemoryEngine）
=================================

统一入口，协调四层记忆架构：

┌─────────────────────────────────────────────┐
│              QuadMemoryEngine               │
│              （统一查询入口）                  │
├──────────┬──────────┬──────────┬────────────┤
│  L1      │  L2      │  L3      │  L4        │
│ Index    │ Context  │ Cache    │ Graph      │
│ 索引     │ 上下文   │ 缓存     │ 图谱       │
│ (常驻)   │ (按需)   │ (会话)   │ (持久)     │
│ ≤25KB   │ FTS5     │ 自动蒸馏 │ 影响分析   │
└──────────┴──────────┴──────────┴────────────┘

查询路由策略：
1. 关键词/元数据 → L1 Index（最快，常驻内存）
2. 项目相关内容 → L2 Context（FTS 全文搜索）
3. 当前会话信息 → L3 Cache（会话内搜索）
4. 代码依赖/健康度 → L4 Graph（图谱遍历）

写入流程：
L3 Cache → [蒸馏] → L1 Index
L2 Context → [关联] → L4 Graph
事件日志 → Mnemosyne-Dev SQLite

整合原则：
- 向后兼容：MnemosyneDev 的现有 API 继续可用
- 渐进增强：新功能通过 Engine 暴露
- 层间协作：自动触发层间数据流转
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .index import MemoryIndex, MemoryEntry
from .context import ProjectContext, ContextEntry
from .cache import SessionCache, CacheEntry
from .graph import NeuralGraph, GraphNode, HealthRecord


CST = timezone(timedelta(hours=8))


@dataclass
class MemoryQuery:
    """统一查询请求"""
    query: str = ""
    keywords: List[str] = None
    layers: List[str] = None     # 指定搜索哪些层 ["l1", "l2", "l3", "l4"]
    context_types: List[str] = None  # L2 类型过滤
    limit: int = 10
    require_fresh_days: int = None  # 新鲜度要求
    include_graph_analysis: bool = False  # 是否包含影响分析
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = self.query.split()
        if self.layers is None:
            self.layers = ["l1", "l2", "l3"]  # 默认搜前三层


@dataclass
class MemoryQueryResult:
    """统一查询结果"""
    query: str = ""
    
    # 各层结果
    l1_results: List[MemoryEntry] = None
    l2_results: List[ContextEntry] = None
    l3_results: List[CacheEntry] = None
    l4_results: Dict = None       # 图谱分析结果
    
    # 融合结果（按相关性排序的跨层合并）
    fused_results: List[Dict] = None
    
    # 元信息
    total_found: int = 0
    query_time_ms: int = 0
    layers_searched: List[str] = None
    
    def to_summary(self) -> str:
        """生成人类可读的结果摘要"""
        parts = []
        
        if self.l1_results:
            parts.append("L1(索引): {}条".format(len(self.l1_results)))
        if self.l2_results:
            parts.append("L2(上下文): {}条".format(len(self.l2_results)))
        if self.l3_results:
            parts.append("L3(缓存): {}条".format(len(self.l3_results)))
        if self.l4_results:
            affected = self.l4_results.get("affected_count", 0)
            if isinstance(affected, int):
                parts.append("L4(图谱): {}节点受影响".format(affected))
        
        return " | ".join(parts) if parts else "无结果"


class QuadMemoryEngine:
    """
    四层记忆引擎 - 统一入口
    
    职责：
    1. 初始化和管理四层记忆组件
    2. 提供统一的查询接口（跨层联合检索）
    3. 协调层间数据流动（蒸馏、关联、同步）
    4. 与 Mnemosyne-Dev 兼容对接
    """
    
    def __init__(
        self,
        workspace_root: str = "D:/opennewt",
        memory_path: str = None,
        context_db: str = None,
        graph_db: str = None,
        auto_distill: bool = True,
    ):
        """
        初始化四层记忆引擎
        
        Args:
            workspace_root: 工作区根目录
            memory_path: MEMORY.md 路径（覆盖默认值）
            context_db: 上下文数据库路径
            graph_db: 图谱数据库路径
            auto_distill: 是否自动执行蒸馏
        """
        self.workspace_root = workspace_root
        self.auto_distill = auto_distill
        self.initialized = False
        
        print("=" * 60)
        print("QuadMemoryEngine - 四层记忆架构")
        print("=" * 60)
        
        # ========== 第一层：索引 ==========
        print("\n[L1] Initializing MemoryIndex...")
        self.l1_index = MemoryIndex(memory_path=memory_path)
        
        # ========== 第二层：上下文 ==========
        print("\n[L2] Initializing ProjectContext...")
        self.l2_context = ProjectContext(
            db_path=context_db or "D:/opennewt/data/project_context.db",
            workspace_root=workspace_root,
        )
        
        # ========== 第三层：缓存 ==========
        print("\n[L3] Initializing SessionCache...")
        self.l3_cache = SessionCache()
        
        # ========== 第四层：图谱 ==========
        print("\n[L4] Initializing NeuralGraph...")
        self.l4_graph = NeuralGraph(db_path=graph_db or "D:/opennewt/data/neural_graph.db")
        
        self.initialized = True
        print("\n" + "=" * 60)
        print("All 4 memory layers initialized successfully!")
        print("=" * 60 + "\n")
    
    # ========== 统一查询接口 ==========
    
    def query(self, request: MemoryQuery) -> MemoryQueryResult:
        """
        统一查询入口
        
        根据请求中的 layers 字段决定搜索哪些层，
        返回各层的独立结果和融合后的综合结果。
        """
        start_time = datetime.now(CST)
        result = MemoryQueryResult(query=request.query)
        result.layers_searched = request.layers
        
        # L1: 索引搜索
        if "l1" in request.layers and request.keywords:
            result.l1_results = self.l1_index.query(
                keywords=request.keywords,
                limit=request.limit,
            )
        
        # L2: 上下文搜索
        if "l2" in request.layers and request.query:
            result.l2_results = self.l2_context.search(
                query=request.query,
                context_types=request.context_types,
                limit=request.limit,
                require_fresh_days=require_fresh_days,
            )
        
        # L3: 会话缓存搜索
        if "l3" in request.layers and request.keywords:
            result.l3_results = self.l3_cache.query(
                keywords=request.keywords,
                limit=request.limit,
            )
        
        # L4: 图谱分析（仅在明确要求时执行，因为较慢）
        if "l4" in request.layers and request.include_graph_analysis:
            # 尝试将关键词映射到文件路径
            for kw in request.keywords:
                node = self.l4_graph.get_node_by_path(kw)
                if node:
                    result.l4_results = self.l4_graph.analyze_impact(node.node_id)
                    break
                
                # 也尝试按名称查找
                nodes = self.l4_graph.find_nodes(limit=1)
                if nodes:
                    result.l4_results = self.l4_graph.analyze_impact(nodes[0].node_id)
                    break
        
        # 融合结果
        result.fused_results = self._fuse_results(result)
        
        # 计算总数
        result.total_found = sum([
            len(r) if r and isinstance(r, list) else 0
            for r in [
                result.l1_results, 
                result.l2_results, 
                result.l3_results,
            ]
        ])
        
        elapsed_ms = (datetime.now(CST) - start_time).total_seconds() * 1000
        result.query_time_ms = int(elapsed_ms)
        
        print("[Engine] Query completed in {}ms: {}".format(
            result.query_time_ms, result.to_summary()
        ))
        
        return result
    
    def _fuse_results(
        self, 
        result: MemoryQueryResult,
    ) -> List[Dict]:
        """
        融合各层查询结果
        
        将来自不同层的结果合并为统一的有序列表。
        去重策略：基于标题/内容相似度。
        排序策略：按来源层权重 + 内容匹配度排序。
        """
        all_items = []
        
        layer_weights = {
            "l1": 3.0,   # 索引最高优先（长期验证过的记忆）
            "l2": 2.0,   # 上下文中等（项目级知识）
            "l3": 1.0,   # 缓存最低（临时信息）
        }
        
        if result.l1_results:
            for entry in result.l1_results:
                all_items.append({
                    "layer": "l1",
                    "layer_name": "长期索引",
                    "title": entry.title,
                    "content_preview": entry.content[:150],
                    "category": entry.category,
                    "is_fresh": entry.is_fresh,
                    "score": layer_weights["l1"] * (1.2 if entry.is_fresh else 0.8),
                    "tags": entry.tags,
                })
        
        if result.l2_results:
            for entry in result.l2_results:
                all_items.append({
                    "layer": "l2",
                    "layer_name": "项目上下文",
                    "title": entry.title,
                    "content_preview": entry.summary or entry.content[:150],
                    "category": entry.context_type,
                    "is_fresh": True,  # 上下文默认视为新鲜
                    "score": layer_weights["l2"] * (1.0 + min(entry.access_count * 0.05, 0.5)),
                    "tags": entry.tags,
                })
        
        if result.l3_results:
            for entry in result.l3_results:
                all_items.append({
                    "layer": "l3",
                    "layer_name": "会话缓存",
                    "title": "[{}] {}".format(entry.role.upper(), entry.entry_id),
                    "content_preview": (entry.summary or entry.content)[:150],
                    "category": entry.role,
                    "is_fresh": True,
                    "score": layer_weights["l3"] * entry.importance_score,
                    "tags": entry.tags,
                })
        
        # 去重（基于标题相似度）+ 排序
        seen_titles = set()
        unique_items = []
        
        for item in sorted(all_items, key=lambda x: x["score"], reverse=True):
            title_key = item["title"].lower()[:50]
            
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                unique_items.append(item)
        
        return unique_items[:20]  # 最多返回20条融合结果
    
    # ========== 写入接口 ==========
    
    def remember(
        self,
        content: str,
        category: str = "工作笔记",
        title: str = "",
        tags: List[str] = None,
        role: str = "user",
        store_to_l1: bool = True,
        store_to_l2: bool = False,
        store_to_l3: bool = True,
        source_file: str = "",
    ) -> Dict[str, Any]:
        """
        统一记忆写入接口
        
        一行代码同时写入多层记忆，由引擎自动路由。
        
        Args:
            content: 要记住的内容
            category: L1 条目类别
            title: 标题（不提供则自动生成）
            tags: 标签列表
            role: 角色（用于 L3 缓存）
            store_to_l1: 是否写入第一层索引
            store_to_l2: 是否写入第二层上下文
            store_to_l3: 是否写入第三层缓存
            
        Returns:
            各层写入结果的汇总字典
        """
        results = {}
        
        if not title:
            # 自动从内容提取标题
            first_line = content.split("\n")[0][:60]
            title = first_line if first_line else "Untitled"
        
        # 写入 L1（长期索引）
        if store_to_l1:
            try:
                entry = self.l1_index.add_entry(
                    category=category,
                    title=title,
                    content=content,
                    tags=tags,
                    source_file=source_file,
                )
                results["l1"] = {"success": True, "entry_id": entry.entry_id}
            except Exception as e:
                results["l1"] = {"success": False, "error": str(e)}
        
        # 写入 L2（项目上下文）
        if store_to_l2:
            try:
                ctx_type = self._infer_context_type(category, tags)
                entry = self.l2_context.add(
                    context_type=ctx_type,
                    title=title,
                    content=content,
                    tags=tags,
                    source_path=source_file,
                )
                results["l2"] = {"success": True, "entry_id": entry.entry_id}
            except Exception as e:
                results["l2"] = {"success": False, "error": str(e)}
        
        # 写入 L3（会话缓存）
        if store_to_l3:
            try:
                entry = self.l3_cache.add(
                    role=role,
                    content=content,
                    tags=tags,
                )
                results["l3"] = {"success": True, "entry_id": entry.entry_id}
            except Exception as e:
                results["l3"] = {"success": False, "error": str(e)}
        
        print("[Engine] Remember '{}' → layers: {}".format(
            title, list(results.keys())
        ))
        
        return results
    
    @staticmethod
    def _infer_context_type(category: str, tags: List[str]) -> str:
        """推断 L2 上下文类型"""
        tag_set = set((t or "").lower() for t in (tags or []))
        cat_lower = (category or "").lower()
        
        type_mapping = {
            "项目决策": "decision",
            "用户偏好": "preference",
            "技术修复": "snippet",
            "深度学习": "note",
            "反思记录": "note",
        }
        
        if cat_lower in type_mapping:
            return type_mapping[cat_lower]
        
        if any(t in tag_set for t in ("decision", "decision")):
            return "decision"
        if any(t in tag_set for t in ("fix", "bug", "repair", "error")):
            return "snippet"
        if any(t in tag_set for t in ("pref", "config", "convention")):
            return "preference"
        
        return "note"
    
    # ========== 蒸馏流程 ==========
    
    def run_distillation(self) -> Dict[str, Any]:
        """
        执行完整的蒸馏流程：
        L3 Cache → 提炼精华 → 写入 L1 Index
        """
        print("[Engine] Starting distillation pipeline...")
        
        # Step 1: 从 L3 蒸馏
        memories = self.l3_cache.distill()
        
        distilled_count = 0
        
        for mem in memories:
            try:
                # 写入 L1
                self.l1_index.add_entry(
                    category=mem["category"],
                    title=mem["title"],
                    content=mem["content"],
                    tags=mem.get("tags"),
                )
                
                # 可选：也写入 L2
                self.l2_context.add(
                    context_type=self._infer_context_type(
                        mem["category"], mem.get("tags")
                    ),
                    title=mem["title"],
                    content=mem["content"],
                    tags=mem.get("tags"),
                )
                
                distilled_count += 1
                
            except Exception as e:
                print("[Engine] Distillation error: {}".format(str(e)))
        
        # Step 2: L1 约束检查
        stats = self.l1_index.get_stats()
        
        result = {
            "distilled_count": distilled_count,
            "l1_total_entries": stats["total_entries"],
            "l1_within_limits": stats["within_limits"],
            "timestamp": datetime.now(CST).isoformat(),
        }
        
        # 如果超限，建议压缩
        if not stats["within_limits"]:
            self.l1_index.compact()
            result["compaction_triggered"] = True
        
        print("[Engine] Distillation complete: {} memories promoted".format(distilled_count))
        
        return result
    
    # ========== 系统提示词生成 ==========
    
    def get_system_prompt_memory(self, max_tokens: int = 800) -> str:
        """
        生成适合注入系统 prompt 的记忆片段
        
        只使用 L1 索引的摘要版本，保持极低 token 消耗。
        """
        return self.l1_index.get_system_prompt_excerpt(max_tokens)
    
    def get_session_context(self, max_tokens: int = 4000) -> str:
        """获取当前会话上下文摘要"""
        return self.l3_cache.get_context_window(max_tokens)
    
    # ========== 图谱快捷操作 ==========
    
    def register_file_node(
        self,
        file_path: str,
        language: str = "python",
        health_score: float = 1.0,
    ) -> GraphNode:
        """快速注册文件节点到图谱"""
        node = GraphNode(
            node_type="file",
            name=os.path.basename(file_path),
            path=file_path,
            language=language,
            health_score=health_score,
        )
        
        return self.l4_graph.add_node(node)
    
    def add_dependency(
        self,
        from_path: str,
        to_path: str,
        dep_type: str = "imports",
    ) -> bool:
        """快速添加文件间依赖关系"""
        src_node = self.l4_graph.get_node_by_path(from_path)
        tgt_node = self.l4_graph.get_node_by_path(to_path)
        
        if not src_node:
            src_node = self.register_file_node(from_path)
        if not tgt_node:
            tgt_node = self.register_file_node(to_path)
        
        from .graph import GraphEdge
        edge = GraphEdge(
            source_id=src_node.node_id,
            target_id=tgt_node.node_id,
            edge_type=dep_type,
        )
        
        self.l4_graph.add_edge(edge)
        return True
    
    def record_repair(
        self,
        file_path: str,
        success: bool,
        damage_type: str = "",
    ) -> bool:
        """记录修复并更新健康度"""
        node = self.l4_graph.get_node_by_path(file_path)
        
        if node:
            self.l4_graph.update_health_from_repair(node.node_id, success, damage_type)
            return True
        
        # 如果节点不存在，先注册再记录
        node = self.register_file_node(file_path)
        self.l4_graph.update_health_from_repair(node.node_id, success, damage_type)
        return True
    
    # ========== 综合报告 ==========
    
    def get_full_report(self) -> Dict[str, Any]:
        """获取四层记忆系统的完整状态报告"""
        l1_stats = self.l1_index.get_stats()
        l2_stats = self.l2_context.get_stats()
        l3_stats = self.l3_cache.get_stats()
        l4_stats = self.l4_graph.get_stats()
        
        return {
            "engine_version": "0.1.0",
            "initialized": self.initialized,
            "workspace_root": self.workspace_root,
            "generated_at": datetime.now(CST).isoformat(),
            
            "layers": {
                "L1_MemoryIndex": l1_stats,
                "L2_ProjectContext": l2_stats,
                "L3_SessionCache": l3_stats,
                "L4_NeuralGraph": l4_stats,
            },
            
            "summary": {
                "total_memories": l1_stats["total_entries"],
                "total_contexts": l2_stats["total_entries"],
                "cache_entries": l3_stats["total_entries"],
                "graph_nodes": l4_stats["total_nodes"],
                "graph_edges": l4_stats["total_edges"],
                "avg_health_score": l4_stats["avg_health_score"],
            },
            
            "alerts": self._generate_alerts(l1_stats, l2_stats, l3_stats, l4_stats),
        }
    
    @staticmethod
    def _generate_alerts(l1, l2, l3, l4) -> List[str]:
        """生成系统告警"""
        alerts = []
        
        if not l1.get("within_limits"):
            alerts.append("⚠️ L1 索引超出容量限制（{}行/{}B），需要压缩".format(
                l1["line_count"], l1["byte_size"]
            ))
        
        if l3.get("capacity_ratio", 0) > 0.8:
            alerts.append("📝 L3 缓存容量已用 {:.0%}，建议执行蒸馏".format(
                l3["capacity_ratio"]
            ))
        
        if l4.get("unhealthy_nodes", 0) > 0:
            alerts.append("🚨 L4 发现 {} 个不健康节点（健康度 < 50%）".format(
                l4["unhealthy_nodes"]
            ))
        
        stale_in_l1 = l1.get("stale_entries", 0)
        if stale_in_l1 > l1.get("fresh_entries", 0):
            alerts.append("⏳ L1 大部分条目已过期（{} 过期 / {} 新鲜)".format(
                stale_in_l1, l1.get("fresh_entries", 0)
            ))
        
        return alerts if alerts else ["✅ 所有系统正常运行"]
