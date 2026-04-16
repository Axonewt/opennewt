---
name: code-review
description: AI 代码审查技能 - 检测代码问题、提出改进建议
version: 1.0.0
triggers:
  - "review"
  - "审查"
  - "检查代码"
  - "代码审查"
actions:
  - run: "ruff check {path}"
  - run: "mypy {path}"
  - read: "{path}"
---

# Code Review Skill

## 概述

自动审查代码质量，发现潜在问题，提出改进建议。

## 使用方法

```
axonewt skill code-review <file_or_dir>
```

## 审查维度

1. **代码风格** — ruff / pylint
2. **类型检查** — mypy
3. **安全漏洞** — bandit
4. **性能问题** — 自动检测
5. **复杂度** — AST 分析

## 输出格式

```json
{
  "score": 0.85,
  "issues": [
    {
      "file": "src/main.py",
      "line": 42,
      "severity": "warning",
      "type": "style",
      "message": "Missing docstring"
    }
  ],
  "suggestions": [
    "添加类型注解提高可读性",
    "拆分过长函数"
  ]
}
```
