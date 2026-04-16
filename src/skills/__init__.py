"""
Axonewt Skills System
=====================

Skill 是 Axonewt 的可复用任务模板。
参考 Hermes Agent 的 SKILL.md 标准，定义在 skills/ 目录中。

每个 Skill 由一个目录组成：
    skills/
    ├── README.md              # 技能索引
    ├── code-review/          # 技能1
    │   ├── SKILL.md          # 技能定义
    │   └── scripts/          # 辅助脚本
    └── refactor/
        └── SKILL.md

SKILL.md 格式（参考 Hermes Agent）：
    ---
    name: skill-name
    description: 简短描述
    version: 1.0.0
    triggers:
      - "review" / "检查" / "review code"
    actions:
      - run: shell command
      - read: file path
      - patch: file path
    ---
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml


class Skill:
    """技能定义"""

    def __init__(
        self,
        name: str,
        description: str,
        version: str = "1.0.0",
        triggers: List[str] = None,
        actions: List[Dict[str, Any]] = None,
        metadata: Dict[str, Any] = None,
    ):
        self.name = name
        self.description = description
        self.version = version
        self.triggers = triggers or []
        self.actions = actions or []
        self.metadata = metadata or {}

    def matches(self, query: str) -> bool:
        """检查查询是否匹配此技能"""
        query_lower = query.lower()
        return any(
            trigger.lower() in query_lower for trigger in self.triggers
        )

    def __repr__(self):
        return f"Skill(name={self.name}, version={self.version})"


class SkillRegistry:
    """技能注册表"""

    def __init__(self, skills_dir: str = None):
        self.skills_dir = Path(skills_dir) if skills_dir else Path(__file__).parent
        self.skills: Dict[str, Skill] = {}
        self._load_all()

    def _load_all(self):
        """加载所有技能"""
        if not self.skills_dir.exists():
            return

        for item in self.skills_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skill = self._load_skill(item)
                if skill:
                    self.skills[skill.name] = skill

    def _load_skill(self, skill_dir: Path) -> Optional[Skill]:
        """加载单个技能"""
        skill_file = skill_dir / "SKILL.md"
        try:
            content = skill_file.read_text(encoding="utf-8")

            # 解析 YAML frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    body = parts[2].strip()

                    return Skill(
                        name=frontmatter.get("name", skill_dir.name),
                        description=frontmatter.get("description", ""),
                        version=frontmatter.get("version", "1.0.0"),
                        triggers=frontmatter.get("triggers", []),
                        actions=frontmatter.get("actions", []),
                        metadata={
                            "body": body,
                            "path": str(skill_dir),
                        }
                    )
        except Exception as e:
            print(f"[SkillRegistry] Failed to load {skill_dir}: {e}")

        return None

    def find(self, query: str) -> List[Skill]:
        """查找匹配的技能"""
        return [s for s in self.skills.values() if s.matches(query)]

    def get(self, name: str) -> Optional[Skill]:
        """获取指定技能"""
        return self.skills.get(name)

    def list_all(self) -> List[Skill]:
        """列出所有技能"""
        return list(self.skills.values())

    def register(self, skill: Skill):
        """注册新技能"""
        self.skills[skill.name] = skill

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_skills": len(self.skills),
            "skill_names": list(self.skills.keys()),
        }


# 默认注册表实例
_default_registry: Optional[SkillRegistry] = None


def get_registry(skills_dir: str = None) -> SkillRegistry:
    """获取技能注册表（单例）"""
    global _default_registry
    if _default_registry is None:
        _default_registry = SkillRegistry(skills_dir)
    return _default_registry


def find_skill(query: str) -> List[Skill]:
    """快捷函数：查找匹配的技能"""
    return get_registry().find(query)
