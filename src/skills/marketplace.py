"""
Axonewt Skill Marketplace — 技能市场
======================================

参考 Hermes Agent 的 Skills 系统和 SkillCraft 治理框架。

功能：
1. 技能搜索 — 按关键词/分类/标签搜索技能
2. 技能安装 — 从 GitHub/本地/URL 安装技能
3. 技能管理 — 启用/禁用/删除/更新技能
4. 技能验证 — 安装前安全审计 + 安装后功能验证
5. 技能分享 — 导出技能包供他人使用
6. 本地技能库 — 管理已安装技能

技能包结构：
    skill-package/
    ├── SKILL.md          # 技能定义（YAML frontmatter + Markdown body）
    ├── scripts/          # 辅助脚本（可选）
    │   └── main.py
    ├── references/       # 参考文档（可选）
    └── assets/           # 资源文件（可选）

技能来源：
    1. 本地 skills/ 目录
    2. GitHub 仓库（用户/组织）
    3. URL 直接下载
    4. 本地 .zip/.tar.gz 文件

安全审计：
    - SKILL.md frontmatter 解析
    - 脚本文件扫描（危险命令检测）
    - 依赖检查
    - 文件大小限制
"""

import os
import sys
import json
import yaml
import shutil
import hashlib
import tempfile
import zipfile
import tarfile
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict

CST = timezone(timedelta(hours=8))
logger = logging.getLogger("axonewt.marketplace")

ROOT = Path(__file__).parent.parent.parent
DEFAULT_SKILLS_DIR = ROOT / "skills"
INSTALLED_SKILLS_DIR = ROOT / "data" / "installed_skills"
SKILL_INDEX_FILE = ROOT / "data" / "skill_index.json"


# ============================================================================
# 技能定义（增强版）
# ============================================================================

@dataclass
class SkillDefinition:
    """增强版技能定义"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    source: str = "local"  # local, github, url, file
    source_url: str = ""
    triggers: List[str] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    category: str = "general"
    examples: List[str] = field(default_factory=list)
    config_vars: List[Dict[str, str]] = field(default_factory=list)  # [{name, description, default}]
    dependencies: List[str] = field(default_factory=list)  # pip packages
    platforms: List[str] = field(default_factory=list)  # platform filters
    body: str = ""  # Markdown body
    install_path: str = ""
    install_date: str = ""
    last_updated: str = ""
    enabled: bool = True
    usage_count: int = 0
    success_count: int = 0
    rating: float = 0.0

    def __post_init__(self):
        now = datetime.now(CST).isoformat()
        if not self.install_date:
            self.install_date = now
        if not self.last_updated:
            self.last_updated = now

    @property
    def success_rate(self) -> float:
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count

    def matches(self, query: str) -> bool:
        query_lower = query.lower()
        return any(t.lower() in query_lower for t in self.triggers)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "SkillDefinition":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_skill_md(cls, content: str, source: str = "local", install_path: str = "") -> "SkillDefinition":
        """从 SKILL.md 内容解析技能定义"""
        body = ""
        frontmatter = {}

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()

        return cls(
            name=frontmatter.get("name", "unknown"),
            description=frontmatter.get("description", ""),
            version=frontmatter.get("version", "1.0.0"),
            author=frontmatter.get("author", ""),
            source=source,
            triggers=frontmatter.get("triggers", []),
            actions=frontmatter.get("actions", []),
            tags=frontmatter.get("tags", []),
            category=frontmatter.get("category", "general"),
            examples=frontmatter.get("examples", []),
            config_vars=frontmatter.get("config_vars", []),
            dependencies=frontmatter.get("dependencies", []),
            platforms=frontmatter.get("platforms", []),
            body=body,
            install_path=install_path,
        )


# ============================================================================
# 安全审计
# ============================================================================

DANGEROUS_PATTERNS = [
    r"rm\s+-rf",
    r"shutil\.rmtree",
    r"os\.system\(",
    r"subprocess.*shell\s*=\s*True",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__\s*\(",
    r"pickle\.loads",
    r"marshal\.loads",
    r"\.git\b",
    r"password",
    r"secret_key",
    r"api_key.*=.*['\"]",
    r"token.*=.*['\"]",
]

MAX_SKILL_SIZE = 10 * 1024 * 1024  # 10MB


@dataclass
class AuditResult:
    """审计结果"""
    passed: bool
    risk_level: str  # safe, low, medium, high, critical
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    file_count: int = 0
    total_size: int = 0


class SkillAuditor:
    """技能安全审计器"""

    def audit_directory(self, skill_dir: Path) -> AuditResult:
        """审计技能目录"""
        result = AuditResult(passed=True, risk_level="safe")
        
        if not skill_dir.exists():
            return AuditResult(passed=False, risk_level="critical", errors=["目录不存在"])

        # 检查总大小
        total_size = sum(f.stat().st_size for f in skill_dir.rglob("*") if f.is_file())
        result.total_size = total_size
        if total_size > MAX_SKILL_SIZE:
            result.passed = False
            result.risk_level = "high"
            result.errors.append(f"技能包过大: {total_size / 1024 / 1024:.1f}MB > {MAX_SKILL_SIZE / 1024 / 1024}MB")
            return result

        # 检查文件
        for f in skill_dir.rglob("*"):
            if f.is_file():
                result.file_count += 1
                # 检查文件路径
                self._check_path(f, skill_dir, result)
                # 检查文件内容
                if f.suffix in (".py", ".sh", ".bat", ".ps1", ".js"):
                    self._check_content(f, result)

        # 检查 SKILL.md
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            result.warnings.append("缺少 SKILL.md 文件")

        # 确定风险等级
        if result.errors:
            result.passed = False
            result.risk_level = "critical" if len(result.errors) > 2 else "high"
        elif result.warnings:
            result.risk_level = "medium" if len(result.warnings) > 3 else "low"

        return result

    def _check_path(self, file_path: Path, skill_dir: Path, result: AuditResult):
        """检查文件路径安全性"""
        rel = file_path.relative_to(skill_dir)
        parts = str(rel).replace("\\", "/").split("/")
        
        # 禁止的路径模式
        blocked = [".git", "__pycache__", ".env", "credentials", "secrets"]
        for part in parts:
            if part in blocked:
                result.errors.append(f"禁止的路径: {rel}")
                break

    def _check_content(self, file_path: Path, result: AuditResult):
        """检查文件内容安全性"""
        import re
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in DANGEROUS_PATTERNS:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    msg = f"{file_path.name}: 检测到可疑模式 '{pattern}'"
                    result.warnings.append(msg)
        except Exception as e:
            result.warnings.append(f"无法检查 {file_path.name}: {e}")


# ============================================================================
# 技能安装器
# ============================================================================

class SkillInstaller:
    """技能安装器"""

    def __init__(self, install_dir: str = None):
        self.install_dir = Path(install_dir) if install_dir else INSTALLED_SKILLS_DIR
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self.auditor = SkillAuditor()

    def install_from_github(self, repo_url: str, skill_name: str = None) -> Tuple[bool, str]:
        """从 GitHub 安装技能"""
        try:
            import httpx
            
            # 标准化 URL
            if repo_url.startswith("https://github.com/"):
                api_url = repo_url.replace("https://github.com/", "https://api.github.com/repos/")
            else:
                return False, "无效的 GitHub URL"

            # 下载 ZIP
            zip_url = f"{api_url}/zipball/main"
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = Path(tmpdir) / "skill.zip"
                
                with httpx.stream("GET", zip_url, follow_redirects=True, timeout=30.0) as resp:
                    if resp.status_code != 200:
                        return False, f"下载失败: HTTP {resp.status_code}"
                    with open(zip_path, "wb") as f:
                        for chunk in resp.iter_bytes(8192):
                            f.write(chunk)

                # 解压
                extract_dir = Path(tmpdir) / "extracted"
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_dir)

                # 找到技能目录（GitHub zip 会有一个前缀目录）
                skill_dir = self._find_skill_dir(extract_dir)
                if not skill_dir:
                    return False, "找不到 SKILL.md"

                # 安全审计
                audit = self.auditor.audit_directory(skill_dir)
                if not audit.passed:
                    return False, f"安全审计未通过: {'; '.join(audit.errors)}"

                # 安装
                name = skill_name or skill_dir.name
                target_dir = self.install_dir / name
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.copytree(skill_dir, target_dir)

                return True, f"已安装到 {target_dir}"
        except ImportError:
            return False, "httpx 库未安装"
        except Exception as e:
            return False, f"安装失败: {e}"

    def install_from_url(self, url: str, skill_name: str = None) -> Tuple[bool, str]:
        """从 URL 下载安装技能（ZIP/TAR.GZ）"""
        try:
            import httpx
            
            with tempfile.TemporaryDirectory() as tmpdir:
                # 下载
                suffix = ".zip" if ".zip" in url else ".tar.gz"
                file_path = Path(tmpdir) / f"skill{suffix}"
                
                with httpx.stream("GET", url, follow_redirects=True, timeout=30.0) as resp:
                    if resp.status_code != 200:
                        return False, f"下载失败: HTTP {resp.status_code}"
                    with open(file_path, "wb") as f:
                        for chunk in resp.iter_bytes(8192):
                            f.write(chunk)

                # 解压
                extract_dir = Path(tmpdir) / "extracted"
                if suffix == ".zip":
                    with zipfile.ZipFile(file_path, "r") as zf:
                        zf.extractall(extract_dir)
                else:
                    with tarfile.open(file_path, "r:gz") as tf:
                        tf.extractall(extract_dir)

                # 找技能目录
                skill_dir = self._find_skill_dir(extract_dir)
                if not skill_dir:
                    return False, "找不到 SKILL.md"

                # 安全审计
                audit = self.auditor.audit_directory(skill_dir)
                if not audit.passed:
                    return False, f"安全审计未通过: {'; '.join(audit.errors)}"

                # 安装
                name = skill_name or skill_dir.name
                target_dir = self.install_dir / name
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.copytree(skill_dir, target_dir)

                return True, f"已安装到 {target_dir}"
        except Exception as e:
            return False, f"安装失败: {e}"

    def install_from_local(self, source_path: str, skill_name: str = None) -> Tuple[bool, str]:
        """从本地目录安装技能"""
        source = Path(source_path)
        if not source.exists():
            return False, f"路径不存在: {source}"

        skill_dir = self._find_skill_dir(source)
        if not skill_dir:
            return False, "找不到 SKILL.md"

        # 安全审计
        audit = self.auditor.audit_directory(skill_dir)
        if not audit.passed:
            return False, f"安全审计未通过: {'; '.join(audit.errors)}"

        # 安装
        name = skill_name or skill_dir.name
        target_dir = self.install_dir / name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(skill_dir, target_dir)

        return True, f"已安装到 {target_dir}"

    def uninstall(self, skill_name: str) -> Tuple[bool, str]:
        """卸载技能"""
        target_dir = self.install_dir / skill_name
        if not target_dir.exists():
            return False, f"技能不存在: {skill_name}"
        shutil.rmtree(target_dir)
        return True, f"已卸载: {skill_name}"

    def update(self, skill_name: str) -> Tuple[bool, str]:
        """更新技能（需要 source_url）"""
        skill_index = self._load_index()
        if skill_name not in skill_index:
            return False, f"技能未在索引中: {skill_name}"

        source = skill_index[skill_name].get("source", "")
        source_url = skill_index[skill_name].get("source_url", "")

        if source == "github" and source_url:
            self.uninstall(skill_name)
            return self.install_from_github(source_url, skill_name)
        elif source == "url" and source_url:
            self.uninstall(skill_name)
            return self.install_from_url(source_url, skill_name)
        else:
            return False, "本地技能不支持自动更新"

    def _find_skill_dir(self, base: Path) -> Optional[Path]:
        """递归查找包含 SKILL.md 的目录"""
        if (base / "SKILL.md").exists():
            return base
        for child in base.iterdir():
            if child.is_dir():
                result = self._find_skill_dir(child)
                if result:
                    return result
        return None

    def _load_index(self) -> Dict:
        """加载技能索引"""
        if SKILL_INDEX_FILE.exists():
            try:
                return json.loads(SKILL_INDEX_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_index(self, index: Dict):
        """保存技能索引"""
        SKILL_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        SKILL_INDEX_FILE.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


# ============================================================================
# 技能市场
# ============================================================================

class SkillMarketplace:
    """
    技能市场 — 技能的搜索、安装、管理、分享
    
    参考 Hermes Agent 的 Skills 系统。
    整合 SkillCraft 治理框架的核心理念：
    - 浅层优先：保持技能扁平独立
    - 强制验证：安装后必须验证
    - 精准沉淀：只固化反复有用的模式
    - 定期清理：淘汰低效技能
    """

    def __init__(self, skills_dir: str = None, install_dir: str = None):
        self.skills_dir = Path(skills_dir) if skills_dir else DEFAULT_SKILLS_DIR
        self.installer = SkillInstaller(install_dir)
        self._skills: Dict[str, SkillDefinition] = {}
        self._load_skills()

    def _load_skills(self):
        """加载所有技能（内置 + 已安装）"""
        self._skills.clear()

        # 加载内置技能
        self._load_from_dir(self.skills_dir, source="local")

        # 加载已安装技能
        installed_dir = self.installer.install_dir
        if installed_dir.exists():
            self._load_from_dir(installed_dir, source="installed")

    def _load_from_dir(self, directory: Path, source: str = "local"):
        """从目录加载技能"""
        if not directory.exists():
            return

        for item in directory.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                try:
                    content = (item / "SKILL.md").read_text(encoding="utf-8")
                    skill = SkillDefinition.from_skill_md(
                        content, source=source, install_path=str(item)
                    )
                    # 已安装技能不覆盖内置技能
                    if skill.name not in self._skills or source == "installed":
                        self._skills[skill.name] = skill
                except Exception as e:
                    logger.warning(f"加载技能失败 {item}: {e}")

    # ---------------------------------------------------------------
    # 搜索
    # ---------------------------------------------------------------

    def search(self, query: str, category: str = None, tags: List[str] = None) -> List[SkillDefinition]:
        """搜索技能"""
        results = []
        query_lower = query.lower()

        for skill in self._skills.values():
            if not skill.enabled:
                continue

            # 分类过滤
            if category and skill.category != category:
                continue

            # 标签过滤
            if tags and not any(t in skill.tags for t in tags):
                continue

            # 关键词匹配
            searchable = f"{skill.name} {skill.description} {' '.join(skill.triggers)} {' '.join(skill.tags)}".lower()
            if query_lower in searchable:
                results.append(skill)

        # 按成功率排序
        results.sort(key=lambda s: (s.success_rate, s.usage_count), reverse=True)
        return results

    def find(self, query: str) -> List[SkillDefinition]:
        """查找匹配的技能（按触发词匹配）"""
        return [s for s in self._skills.values() if s.enabled and s.matches(query)]

    def get(self, name: str) -> Optional[SkillDefinition]:
        """获取指定技能"""
        return self._skills.get(name)

    def list_all(self, category: str = None) -> List[SkillDefinition]:
        """列出所有技能"""
        skills = list(self._skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        return sorted(skills, key=lambda s: s.name)

    def list_categories(self) -> List[str]:
        """列出所有分类"""
        cats = set()
        for s in self._skills.values():
            cats.add(s.category)
        return sorted(cats)

    # ---------------------------------------------------------------
    # 安装
    # ---------------------------------------------------------------

    def install(self, source: str, name: str = None) -> Tuple[bool, str, Optional[SkillDefinition]]:
        """
        安装技能（自动检测来源类型）
        
        source: GitHub URL / HTTP URL / 本地路径
        name: 可选的技能名称
        """
        source_lower = source.lower()

        if source_lower.startswith("https://github.com/") or source_lower.startswith("http://github.com/"):
            ok, msg = self.installer.install_from_github(source, name)
        elif source_lower.startswith("https://") or source_lower.startswith("http://"):
            ok, msg = self.installer.install_from_url(source, name)
        elif Path(source).exists():
            ok, msg = self.installer.install_from_local(source, name)
        else:
            return False, "无法识别来源类型", None

        if ok:
            self._load_skills()
            installed_name = name or Path(msg).name
            skill = self._skills.get(installed_name)
            return True, msg, skill

        return False, msg, None

    def uninstall(self, name: str) -> Tuple[bool, str]:
        """卸载技能"""
        ok, msg = self.installer.uninstall(name)
        if ok:
            self._skills.pop(name, None)
        return ok, msg

    # ---------------------------------------------------------------
    # 管理
    # ---------------------------------------------------------------

    def enable(self, name: str) -> bool:
        """启用技能"""
        skill = self._skills.get(name)
        if skill:
            skill.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用技能"""
        skill = self._skills.get(name)
        if skill:
            skill.enabled = False
            return True
        return False

    def record_usage(self, name: str, success: bool):
        """记录技能使用情况"""
        skill = self._skills.get(name)
        if skill:
            skill.usage_count += 1
            if success:
                skill.success_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """获取市场统计"""
        total = len(self._skills)
        enabled = sum(1 for s in self._skills.values() if s.enabled)
        installed = sum(1 for s in self._skills.values() if s.source == "installed")
        
        categories = {}
        for s in self._skills.values():
            cat = s.category
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += 1

        return {
            "total_skills": total,
            "enabled_skills": enabled,
            "installed_skills": installed,
            "categories": categories,
            "top_skills": sorted(
                [(s.name, s.success_rate, s.usage_count) for s in self._skills.values()],
                key=lambda x: x[1], reverse=True,
            )[:10],
        }

    def export_skill(self, name: str, output_path: str) -> Tuple[bool, str]:
        """导出技能为 ZIP 包"""
        skill = self._skills.get(name)
        if not skill:
            return False, f"技能不存在: {name}"

        skill_dir = Path(skill.install_path)
        if not skill_dir.exists():
            return False, f"技能目录不存在: {skill_dir}"

        try:
            output = Path(output_path)
            if output.suffix != ".zip":
                output = output.with_suffix(".zip")
            
            shutil.make_archive(str(output.with_suffix("")), "zip", skill_dir)
            return True, str(output)
        except Exception as e:
            return False, f"导出失败: {e}"

    def cleanup_unused(self, min_success_rate: float = 0.3, min_usage: int = 3) -> List[str]:
        """
        清理低效技能
        
        规则：
        - 成功率 < min_success_rate 且使用次数 >= min_usage 的技能建议删除
        """
        candidates = []
        for name, skill in self._skills.items():
            if (skill.usage_count >= min_usage 
                and skill.success_rate < min_success_rate
                and skill.source == "installed"):
                candidates.append({
                    "name": name,
                    "success_rate": skill.success_rate,
                    "usage_count": skill.usage_count,
                })
        return candidates
