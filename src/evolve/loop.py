"""
Evolution Loop — 技能自进化闭环

核心流程（来自 Hermes Agent）:
  执行任务 -> 提取经验 -> 生成 Skill -> 验证 -> 入库 -> 持续优化
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class TrajectoryStep:
    step_id: int
    tool_name: str
    args: dict
    result: str
    duration: float
    success: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class Trajectory:
    id: str
    task_description: str
    steps: list[TrajectoryStep]
    total_duration: float
    success: bool
    final_output: str
    model: str = "unknown"
    timestamp: float = field(default_factory=time.time)


@dataclass
class SkillTemplate:
    name: str
    description: str
    trigger_words: list[str]
    tool_chain: list[dict]
    examples: list[str]
    verification: str = ""
    score: float = 0.0


class TrajectoryCollector:
    """轨迹收集器"""

    def __init__(self, trajectory_dir: Path | str = ".axonewt_trajectories"):
        self._dir = Path(trajectory_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._current: list[TrajectoryStep] = []
        self._task_description = ""
        self._model = "unknown"

    def start_task(self, task_description: str, model: str = "unknown"):
        self._current = []
        self._task_description = task_description
        self._model = model

    def record_step(self, tool_name: str, args: dict, result: str, duration: float, success: bool):
        step = TrajectoryStep(
            step_id=len(self._current),
            tool_name=tool_name,
            args=args,
            result=result[:1000],
            duration=duration,
            success=success,
        )
        self._current.append(step)

    def finish_task(self, final_output: str, success: bool) -> Trajectory:
        total = sum(s.duration for s in self._current)
        traj = Trajectory(
            id=str(uuid.uuid4())[:12],
            task_description=self._task_description,
            steps=self._current,
            total_duration=total,
            success=success,
            final_output=final_output[:5000],
            model=self._model,
        )
        path = self._dir / f"{traj.id}.json"
        path.write_text(
            json.dumps(
                {
                    "id": traj.id,
                    "task_description": traj.task_description,
                    "steps": [
                        {"step_id": s.step_id, "tool_name": s.tool_name, "args": s.args,
                         "result": s.result, "duration": s.duration, "success": s.success, "timestamp": s.timestamp}
                        for s in traj.steps
                    ],
                    "total_duration": traj.total_duration,
                    "success": traj.success,
                    "final_output": traj.final_output,
                    "model": traj.model,
                    "timestamp": traj.timestamp,
                },
                ensure_ascii=False, indent=2,
            ), encoding="utf-8",
        )
        self._current = []
        return traj

    def recent(self, limit: int = 20) -> list[Trajectory]:
        paths = sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        trajectories = []
        for p in paths[:limit]:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                trajectories.append(Trajectory(**data))
            except Exception:
                continue
        return trajectories


class SkillGenerator:
    """Skill 生成器"""

    def __init__(self, skills_dir: Path | str = "src/skills"):
        self._skills_dir = Path(skills_dir)
        self._skills_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, trajectory: Trajectory) -> Optional[SkillTemplate]:
        if not trajectory.success or len(trajectory.steps) < 2:
            return None
        tool_chain = []
        for step in trajectory.steps:
            if not step.success:
                continue
            tool_chain.append({"tool": step.tool_name, "args_template": self._extract_params(step.args)})
        if len(tool_chain) < 2:
            return None
        tools_used = [s["tool"] for s in tool_chain]
        name = f"{'_'.join(tools_used[:3])}_skill".replace("_tool", "").replace("_", "-").lower()
        desc = trajectory.task_description[:100] if trajectory.task_description else " -> ".join(tools_used)
        trigger_words = self._extract_trigger_words(trajectory.task_description)
        return SkillTemplate(name=name, description=desc, trigger_words=trigger_words,
                             tool_chain=tool_chain, examples=[trajectory.task_description])

    def _extract_params(self, args: dict) -> dict:
        template = {}
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 50:
                template[k] = "{{" + k + "}}"
            elif isinstance(v, (int, float)):
                template[k] = v
            else:
                template[k] = str(v)[:100]
        return template

    def _extract_trigger_words(self, text: str) -> list[str]:
        if not text:
            return []
        words = text.lower().split()
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "for", "and", "or", "but", "我", "的", "是", "在", "了"}
        return [w for w in words if w not in stopwords and len(w) > 2][:10]

    def save(self, template: SkillTemplate) -> str:
        skill_dir = self._skills_dir / template.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = f"# {template.name}\n\n## Metadata\n- **name**: {template.name}\n- **description**: {template.description}\n- **trigger_words**: {', '.join(template.trigger_words)}\n- **score**: {template.score}\n- **generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n- **tool_chain**: {len(template.tool_chain)} steps\n\n## Tool Chain\n"
        for i, step in enumerate(template.tool_chain, 1):
            skill_md += f"{i}. `{step['tool']}`\n"
        skill_md += f"\n## Examples\n" + "\n".join(f"- {e}" for e in template.examples) + "\n\n---\n*Auto-generated by SkillGenerator*\n"
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
        init_py = f'"""Auto-generated skill: {template.name}"""\n\ndef {template.name.replace("-", "_")}(**kwargs):\n    """{template.description}"""\n    pass\n'
        (skill_dir / "__init__.py").write_text(init_py, encoding="utf-8")
        return str(skill_dir)


class EvolutionLoop:
    """
    自进化主循环
    协调 TrajectoryCollector + SkillGenerator，实现闭环自进化
    """

    def __init__(self, trajectory_dir: Path | str = ".axonewt_trajectories", skills_dir: Path | str = "src/skills"):
        self.collector = TrajectoryCollector(trajectory_dir)
        self.generator = SkillGenerator(skills_dir)
        self._enabled = True

    def on_task_start(self, task: str, model: str = "unknown"):
        self.collector.start_task(task, model)

    def on_tool_call(self, tool_name: str, args: dict, result: str, duration: float, success: bool):
        self.collector.record_step(tool_name, args, result, duration, success)

    def on_task_complete(self, final_output: str, success: bool) -> Optional[str]:
        traj = self.collector.finish_task(final_output, success)
        if not traj.success:
            return None
        template = self.generator.generate(traj)
        if template is None:
            return None
        return self.generator.save(template)

    def get_stats(self) -> dict:
        recent = self.collector.recent(limit=100)
        success_count = sum(1 for t in recent if t.success)
        return {
            "total_trajectories": len(recent),
            "successful": success_count,
            "failed": len(recent) - success_count,
            "success_rate": success_count / len(recent) if recent else 0,
        }
