# Axonewt Skills

> 可复用的任务模板，参考 Hermes Agent SKILL.md 标准。

## 技能列表

| 技能 | 描述 | 触发词 |
|------|------|--------|
| `code-review` | 代码审查 | review, 检查, 审查 |
| `refactor` | 重构建议 | refactor, 重构 |
| `debug` | 调试助手 | debug, 调试, 错误 |
| `test-gen` | 测试生成 | test, 测试 |

## 创建新技能

在 `skills/` 目录下创建目录和 `SKILL.md`：

```bash
mkdir skills/my-skill
touch skills/my-skill/SKILL.md
```

### SKILL.md 格式

```yaml
---
name: my-skill
description: 我的自定义技能
version: 1.0.0
triggers:
  - "触发词1"
  - "触发词2"
actions:
  - run: "echo hello"
  - read: "src/main.py"
---
这里是技能的详细说明和使用示例。
```

### Frontmatter 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 技能唯一名称 |
| `description` | ✅ | 简短描述 |
| `version` | ❌ | 版本号，默认 1.0.0 |
| `triggers` | ✅ | 触发词列表 |
| `actions` | ❌ | 动作序列 |

## 使用技能

```python
from src.skills import find_skill, get_registry

# 查找匹配的技能
skills = find_skill("帮我审查代码")

# 列出所有技能
registry = get_registry()
for skill in registry.list_all():
    print(f"{skill.name}: {skill.description}")

# 获取指定技能
skill = registry.get("code-review")
```
