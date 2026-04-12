# 🦎 Axonewt Engine

> 火蜥蜴再生 AI Agent 框架 - 开源、通用、自进化

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)

## ✨ 核心特性

- **🔥 火蜥蜴再生**：每次故障后自我修复，进化更强
- **🧠 四层记忆**：MEMORY.md + 上下文 + 会话缓存 + 神经图谱
- **📊 7S 管理框架**：系统化组织管理
- **🎯 四象限决策**：智能优先级评估
- **🚀 一键安装**：curl ... | bash 开箱即用

## 🗺️ 架构

```
           共同价值观 (SOUL.md)
                   ↑
       ┌───────────┼───────────┐
       ↓           ↓           ↓
      战略        结构        制度
   火蜥蜴再生    四层架构     OACP协议
       ↑           ↑           ↑
       └───────────┼───────────┘
                   ↓
       ┌───────────┼───────────┐
       ↓           ↓           ↓
      风格        人员        技能
     直接精准    Dev团队     SKILL.md
```

## 🚀 快速开始

### 一键安装（Linux/macOS/WSL）

```bash
curl -fsSL https://raw.githubusercontent.com/axonewt/axonewt-engine/main/install.sh | bash
```

### 一键安装（Windows）

```powershell
irm https://raw.githubusercontent.com/axonewt/axonewt-engine/main/install.ps1 | iex
```

### 或手动安装

```bash
# 克隆仓库
git clone https://github.com/axonewt/axonewt-engine.git
cd axonewt-engine

# 安装（需要 Python 3.11+）
pip install -e ".[all]"

# 启动
axonewt
```

## 📖 文档

- [快速开始](docs/getting-started.md)
- [架构文档](docs/architecture/)
- [API 参考](docs/api/)
- [7S 管理框架](docs/7s-framework.md)
- [贡献指南](CONTRIBUTING.md)

## 🔧 命令

| 命令 | 说明 |
|------|------|
| `axonewt` | 启动对话 |
| `axonewt doctor` | 自检环境 |
| `axonewt scan <path>` | 扫描项目健康度 |

## 📦 模块

| 模块 | 说明 |
|------|------|
| `axonewt.memory` | 四层记忆系统 |
| `axonewt.perception` | Soma 感知层 |
| `axonewt.decision` | Plasticus 决策矩阵 |
| `axonewt.healing` | 火蜥蜴自愈引擎 |
| `axonewt.cli` | 命令行工具 |

## 🏛️ 7S 框架

Axonewt 融入麦肯锡 7S 组织管理框架：

| 7S 要素 | 实现 |
|---------|------|
| Shared Values | SOUL.md - 核心价值观 |
| Strategy | 自主修复 + 持续进化 |
| Structure | 四层架构 |
| Systems | OACP 协议 |
| Style | 直接、精准 |
| Staff | Dev Agent 团队 |
| Skills | SKILL.md 模块化 |

## 🎯 四象限决策

```
              紧急程度
           低 ←────────────→ 高
         ┌────────────┬────────────┐
    高   │  第二象限    │  第一象限    │
  重     │  战略投资    │  危机干预    │
  要     ├────────────┼────────────┤
  性     │  第四象限    │  第三象限    │
         │  研究探索    │  执行优化    │
         └────────────┴────────────┘
```

## 🤝 贡献

欢迎提交 Issue 和 PR！请阅读 [贡献指南](CONTRIBUTING.md)。

## 📄 License

MIT License - 详见 [LICENSE](LICENSE)

---

_🦎 让 AI 真正有用，而不是表演有用。_
