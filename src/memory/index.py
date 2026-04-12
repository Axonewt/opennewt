"""
第一层：MemoryIndex（MEMORY.md 索引）
====================================

核心设计原则：
- 极低 token 消耗，始终加载在系统 prompt 中
- 约束：≤200 行，≤25KB
- 回答「我知道我记过什么」，而非存储全部内容

功能：
1. 解析 MEMORY.md 中的结构化索引条目
2. 支持增量更新（append-only）
3. 记忆新鲜度标注（>1天自动加警告标签）
4. 提供关键词快速检索

数据格式约定：
MEMORY.md 使用 Markdown 结构：
## [类别] 标题
- **key**: value  （元数据）
- 描述文本...

时间戳格式：YYYY-MM-DD
"""

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# 时区设置（东八区）
CST = timezone(timedelta(hours=8))

# 约束常量
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25 * 1024  # 25KB
FRESHNESS_THRESHOLD_DAYS = 1


@dataclass
class MemoryEntry:
    """记忆索引条目"""
    category: str           # 类别（如 "用户偏好", "项目决策", "技术栈"）
    title: str              # 标题
    content: str            # 内容摘要
    tags: List[str] = field(default_factory=list)
    source_file: str = ""   # 来源文件路径（可选）
    created_at: str = ""    # 创建日期 YYYY-MM-DD
    updated_at: str = ""    # 最后更新日期 YYYY-MM-DD
    is_fresh: bool = True   # 是否新鲜（≤1天）
    raw_line_range: Tuple[int, int] = (0, 0)  # 原始文件行号范围
    
    def to_dict(self) -> Dict:
        return {
            "category": self.category,
            "title": self.title,
            "content": self.content[:200],  # 摘要截断
            "tags": self.tags,
            "source_file": self.source_file,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_fresh": self.is_fresh,
        }


class MemoryIndex:
    """
    第一层记忆索引
    
    职责：
    - 读取和解析 MEMORY.md
    - 维护内存中的索引结构
    - 支持增量更新
    - 新鲜度管理
    """
    
    def __init__(self, memory_path: str = None):
        """
        初始化记忆索引
        
        Args:
            memory_path: MEMORY.md 文件路径。默认 ~/.workbuddy/memory/MEMORY.md
        """
        if memory_path is None:
            home = os.path.expanduser("~")
            memory_path = os.path.join(
                home, ".workbuddy", "memory", "MEMORY.md"
            )
        
        self.memory_path = memory_path
        self.entries: List[MemoryEntry] = []
        self._raw_content: str = ""
        self._last_loaded: Optional[datetime] = None
        self._entry_count: int = 0
        
        # 自动加载
        if os.path.exists(self.memory_path):
            self.reload()
        else:
            # 创建空 MEMORY.md
            self._create_empty_memory()
    
    def _create_empty_memory(self):
        """创建空的 MEMORY.md 文件"""
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        template = """# MEMORY.md - 长期记忆索引

---

*最后更新: {date}*

## 📋 目录

<!-- 
使用说明：
- 每个条目以 ## 开头
- 格式：## [类别] 标题
- 时间戳放在条目末尾
- 保持 ≤{max_lines} 行
-->

---

""".format(
            date=datetime.now(CST).strftime("%Y-%m-%d"),
            max_lines=MAX_INDEX_LINES
        )
        
        with open(self.memory_path, "w", encoding="utf-8") as f:
            f.write(template)
        
        self._raw_content = template
        print("[MemoryIndex] Created empty MEMORY.md: {}".format(self.memory_path))
    
    def reload(self):
        """重新加载 MEMORY.md"""
        if not os.path.exists(self.memory_path):
            print("[MemoryIndex] WARNING: Memory file not found: {}".format(self.memory_path))
            return
        
        with open(self.memory_path, "r", encoding="utf-8") as f:
            self._raw_content = f.read()
        
        self._parse_entries()
        self._last_loaded = datetime.now(CST)
        
        print("[MemoryIndex] Loaded {} entries from MEMORY.md ({} bytes)".format(
            len(self.entries), len(self._raw_content)
        ))
        
        # 检查约束
        self._validate_constraints()
    
    def _parse_entries(self):
        """解析 MEMORY.md 中的条目"""
        self.entries = []
        lines = self._raw_content.split("\n")
        
        current_entry = None
        content_lines = []
        start_line = 0
        
        # 匹配 ## [Category] Title 或 ## Title 格式
        header_pattern = re.compile(r"^##\s+(\[([^\]]+)\]\s*)?(.+)$")
        
        for i, line in enumerate(lines):
            match = header_pattern.match(line)
            
            if match:
                # 保存前一个条目
                if current_entry is not None:
                    current_entry.content = "\n".join(content_lines).strip()
                    current_entry.raw_line_range = (start_line, i - 1)
                    self.entries.append(current_entry)
                
                category = match.group(2) or "未分类"
                title = match.group(3).strip()
                start_line = i
                
                current_entry = MemoryEntry(
                    category=category,
                    title=title,
                    content="",
                    tags=[],
                )
                content_lines = []
            elif current_entry is not None and line.startswith("- **"):
                # 解析元数据字段 - **key**: value
                meta_match = re.match(r"-\s+\*\*(\w+(?:\s*\w+)*)\*\*:\s*(.+)", line)
                if meta_match:
                    key = meta_match.group(1).lower()
                    value = meta_match.group(2).strip()
                    
                    if key == "tags":
                        current_entry.tags = [t.strip() for t in value.split(",")]
                    elif key == "updated" or key == "更新":
                        current_entry.updated_at = value
                    elif key == "created" or key == "创建":
                        current_entry.created_at = value
                    elif key == "source" or key == "来源":
                        current_entry.source_file = value
            elif current_entry is not None and line.strip():
                # 普通内容行
                if not line.startswith("#") and not line.startswith("<!--"):
                    content_lines.append(line)
        
        # 保存最后一个条目
        if current_entry is not None:
            current_entry.content = "\n".join(content_lines).strip()
            current_entry.raw_line_range = (start_line, len(lines) - 1)
            self.entries.append(current_entry)
        
        # 更新新鲜度
        self._update_freshness()
        
        self._entry_count = len(self.entries)
    
    def _update_freshness(self):
        """更新所有条目的新鲜度"""
        now = datetime.now(CST)
        
        for entry in self.entries:
            date_str = entry.updated_at or entry.created_at
            
            if date_str:
                try:
                    entry_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CST)
                    days_old = (now - entry_date).days
                    entry.is_fresh = days_old <= FRESHNESS_THRESHOLD_DAYS
                except ValueError:
                    # 无法解析日期，默认为不新鲜
                    entry.is_fresh = False
            else:
                entry.is_fresh = False
    
    def _validate_constraints(self):
        """验证约束条件"""
        line_count = len(self._raw_content.split("\n"))
        byte_count = len(self._raw_content.encode("utf-8"))
        
        warnings = []
        
        if line_count > MAX_INDEX_LINES:
            warnings.append(
                "Line count {} exceeds limit {}. Need compaction.".format(
                    line_count, MAX_INDEX_LINES
                )
            )
        
        if byte_count > MAX_INDEX_BYTES:
            warnings.append(
                "Size {:.1f}KB exceeds limit {:.1f}KB. Need compaction.".format(
                    byte_count / 1024, MAX_INDEX_BYTES / 1024
                )
            )
        
        if warnings:
            for w in warnings:
                print("[MemoryIndex] WARNING: {}".format(w))
        
        return len(warnings) == 0
    
    def query(self, keywords: List[str], limit: int = 5) -> List[MemoryEntry]:
        """
        关键词查询记忆索引
        
        基于简单的关键词匹配 + 标签匹配 + 新鲜度排序。
        不依赖向量模型，保持轻量。
        
        Args:
            keywords: 查询关键词列表
            limit: 返回结果上限
            
        Returns:
            匹配的记忆条目列表
        """
        scored_entries = []
        
        for entry in self.entries:
            score = 0.0
            searchable_text = "{} {}".format(entry.title, entry.content).lower()
            
            for kw in keywords:
                kw_lower = kw.lower()
                
                # 标题完全匹配权重最高
                if kw_lower in entry.title.lower():
                    score += 3.0
                
                # 内容包含
                if kw_lower in searchable_text:
                    score += 1.0
                
                # 标签匹配
                if any(kw_lower in tag.lower() for tag in entry.tags):
                    score += 2.0
            
            # 新鲜度加分
            if entry.is_fresh:
                score += 0.5
            
            if score > 0:
                scored_entries.append((score, entry))
        
        # 按分数降序排列
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        
        result = [item[1] for item in scored_entries[:limit]]
        
        print("[MemoryIndex] Query '{}' returned {} results".format(
            " ".join(keywords), len(result)
        ))
        
        return result
    
    def add_entry(
        self,
        category: str,
        title: str,
        content: str,
        tags: List[str] = None,
        source_file: str = "",
    ) -> MemoryEntry:
        """
        增量添加新记忆条目
        
        追加到 MEMORY.md 末尾，不重写整个文件。
        
        Args:
            category: 条目类别
            title: 条目标题
            content: 条目内容
            tags: 标签列表
            source_file: 来源文件
            
        Returns:
            新创建的 MemoryEntry
        """
        now = datetime.now(CST)
        date_str = now.strftime("%Y-%m-%d")
        tags_str = ", ".join(tags or [])
        
        # 构建新条目的 Markdown
        new_entry = """

## [{category}] {title}

- **Updated**: {date}
{tags_line}
- **Fresh**: ✅

{content}

""".format(
            category=category,
            title=title,
            date=date_str,
            tags_line="- **Tags**: {}".format(tags_str) if tags_str else "",
            content=content,
        )
        
        # 追加到文件末尾
        with open(self.memory_path, "a", encoding="utf-8") as f:
            f.write(new_entry)
        
        # 创建内存中的条目对象
        entry = MemoryEntry(
            category=category,
            title=title,
            content=content,
            tags=tags or [],
            source_file=source_file,
            created_at=date_str,
            updated_at=date_str,
            is_fresh=True,
        )
        
        self.entries.append(entry)
        self._entry_count += 1
        
        # 重新加载以验证约束
        self.reload()
        
        print("[MemoryIndex] Added entry: [{}] {}".format(category, title))
        
        return entry
    
    def update_entry(
        self,
        title: str,
        new_content: str = None,
        new_tags: List[str] = None,
    ) -> bool:
        """
        更新已有条目
        
        通过标题匹配定位条目，更新内容和/或标签。
        
        Args:
            title: 要更新的条目标题
            new_content: 新内容（None 则不更新）
            new_tags: 新标签（None 则不更新）
            
        Returns:
            是否成功更新
        """
        for i, entry in enumerate(self.entries):
            if entry.title.lower() == title.lower():
                if new_content is not None:
                    entry.content = new_content
                if new_tags is not None:
                    entry.tags = new_tags
                
                entry.updated_at = datetime.now(CST).strftime("%Y-%m-%d")
                entry.is_fresh = True
                
                print("[MemoryIndex] Updated entry: {}".format(title))
                return True
        
        print("[MemoryIndex] Entry not found: {}".format(title))
        return False
    
    def get_stale_entries(self, days: int = 7) -> List[MemoryEntry]:
        """
        获取过期条目
        
        Args:
            days: 过期天数阈值
            
        Returns:
            过期的记忆条目列表
        """
        now = datetime.now(CST)
        stale = []
        
        for entry in self.entries:
            date_str = entry.updated_at or entry.created_at
            if date_str:
                try:
                    entry_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CST)
                    if (now - entry_date).days > days:
                        stale.append(entry)
                except ValueError:
                    pass
        
        return stale
    
    def get_stats(self) -> Dict:
        """获取索引统计信息"""
        fresh_count = sum(1 for e in self.entries if e.is_fresh)
        stale_count = len(self.entries) - fresh_count
        
        categories = {}
        for e in self.entries:
            categories[e.category] = categories.get(e.category, 0) + 1
        
        byte_size = len(self._raw_content.encode("utf-8")) if self._raw_content else 0
        line_count = len(self._raw_content.split("\n")) if self._raw_content else 0
        
        return {
            "total_entries": len(self.entries),
            "fresh_entries": fresh_count,
            "stale_entries": stale_count,
            "categories": categories,
            "byte_size": byte_size,
            "line_count": line_count,
            "within_limits": byte_size <= MAX_INDEX_BYTES and line_count <= MAX_INDEX_LINES,
            "last_loaded": self._last_loaded.isoformat() if self._last_loaded else None,
            "memory_path": self.memory_path,
        }
    
    def get_system_prompt_excerpt(self, max_tokens: int = 500) -> str:
        """
        生成用于系统 prompt 的摘要片段
        
        只返回每个条目的标题+一行摘要，极低 token。
        
        Args:
            max_tokens: 大致 token 上限（字符数近似值）
            
        Returns:
            适合放入系统 prompt 的摘要文本
        """
        lines = ["# Memory Index Summary"]
        lines.append("")
        
        for entry in self.entries:
            freshness_mark = "✅" if entry.is_fresh else "⚠️"
            # 取第一行作为摘要
            first_line = entry.content.split("\n")[0][:80]
            
            lines.append(
                "- [{}] {} {}: {}...".format(
                    freshness_mark, entry.category, entry.title, first_line
                )
            )
        
        result = "\n".join(lines)
        
        # 如果超长则截断
        if len(result) > max_tokens * 3:  # 粗略估算
            result = result[:max_tokens * 3] + "\n... (truncated)"
        
        return result
    
    def compact(self, target_lines: int = MAX_INDEX_LINES * 80 // 100) -> bool:
        """
        压缩索引
        
        合并过时条目、删除低价值内容。
        
        Args:
            target_lines: 目标行数
            
        Returns:
            是否成功压缩
        """
        current_lines = len(self._raw_content.split("\n"))
        
        if current_lines <= target_lines:
            print("[MemoryIndex] No compaction needed: {} lines".format(current_lines))
            return True
        
        print("[MemoryIndex] Compacting: {} -> target {} lines".format(
            current_lines, target_lines
        ))
        
        # 策略：标记过时且无标签的条目为待删除候选
        to_remove = []
        
        for entry in self.entries:
            # 删除条件：超过14天 + 无标签 + 非核心类别
            if not entry.is_fresh and not entry.tags:
                if entry.category not in ("用户信息", "核心决策"):
                    to_remove.append(entry)
        
        # 实际删除逻辑需要修改原始 markdown
        # 这里先记录，实际操作在更高层的 engine 中协调
        print("[MemoryIndex] Marked {} entries for removal".format(len(to_remove)))
        
        return len(to_remove) > 0
