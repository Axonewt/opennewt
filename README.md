# 🦎 Axonewt Engine

> 火蜥蜴再生 AI Agent 框架 — 开源、通用、自进化

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Stars](https://img.shields.io/github/stars/axonewt/axonewt-engine)](https://github.com/axonewt/axonewt-engine)
[![Last Commit](https://img.shields.io/github/last-commit/axonewt/axonewt-engine)](https://github.com/axonewt/axonewt-engine)

**核心理念**："像蝾螈重新长出尾巴一样，你的 AI 系统在受损后自我修复。"

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔄 **火蜥蜴再生** | 检测代码问题 → 生成修复方案 → 自动执行 → 验证效果 |
| 🧠 **四层记忆** | L1索引(≤25KB) + L2上下文(FTS5) + L3缓存(自动蒸馏) + L4图谱(影响分析) |
| 🎯 **四象限决策** | P0危机干预 / P1战略投资 / P2执行优化 / P3研究探索 |
| 📊 **7S 管理框架** | 共同价值观 + 战略 + 结构 + 制度 + 风格 + 人员 + 技能 |
| 🌐 **多 LLM 支持** | Ollama(本地) / OpenAI / DeepSeek，自动检测 |
| 🔌 **MCP 服务端** | 8个工具暴露给 Claude Desktop / Cursor / Windsurf |
| 📡 **REST API** | 完整 HTTP API + WebSocket 实时日志 |
| 🐳 **Docker 部署** | 一键 `docker-compose up` |

---

## 🏗️ 架构

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

---

## 🚀 快速开始

### 一键安装

**Windows:**
```powershell
irm https://raw.githubusercontent.com/axonewt/axonewt-engine/main/install.ps1 | iex
```

**Linux/macOS/WSL:**
```bash
curl -fsSL https://raw.githubusercontent.com/axonewt/axonewt-engine/main/install.sh | bash
```

### 或手动安装

```bash
git clone https://github.com/axonewt/axonewt-engine.git
cd axonewt-engine
pip install -r requirements.txt

# 启动
python api_server.py --port 5055

# 或 CLI
axonewt doctor
```

---

## 📋 CLI 命令

| 命令 | 说明 |
|------|------|
| `axonewt` | 交互式对话 |
| `axonewt doctor` | 环境自检 |
| `axonewt scan [path]` | 健康扫描 |
| `axonewt repair [path]` | 触发自愈 |
| `axonewt monitor [path]` | 实时监控 |
| `axonewt ask "问题"` | 单次问答 |
| `axonewt stats` | 查看统计 |
| `axonewt model list` | 列出模型 |

---

## 🌐 API 接口

访问 `http://127.0.0.1:5055/docs` 查看完整 Swagger 文档。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/scan` | POST | 扫描代码库 |
| `/api/repair` | POST | 同步自愈 |
| `/api/repair/async` | POST | 异步自愈 |
| `/api/targets` | POST/GET | 目标管理 |
| `/api/events` | GET | 事件历史 |
| `/api/immune-memory` | GET | 免疫记忆 |
| `/api/llm/chat` | POST | LLM 代理 |
| `/ws/logs` | WS | 实时日志 |

---

## 🔌 MCP 集成

在 Claude Desktop / Cursor / Windsurf 中配置：

```json
{
  "mcpServers": {
    "axonewt": {
      "command": "python",
      "args": ["-m", "src.mcp"],
      "cwd": "/path/to/axonewt-engine"
    }
  }
}
```

**可用工具:** `scan_health`, `repair`, `register_target`, `list_targets`, `scan_target`, `get_events`, `get_stats`, `get_immune_memory`

---

## 📦 核心模块

| 模块 | 代码行数 | 说明 |
|------|----------|------|
| `src/agents/soma_dev.py` | 738 | 感知层，健康扫描 |
| `src/agents/plasticus_dev.py` | 920 | 决策层，LLM修复方案生成 |
| `src/agents/effector_dev.py` | 960 | 执行层，代码修改+回滚 |
| `src/agents/mnemosyne_dev.py` | 466 | 记忆层，事件+免疫记忆 |
| `src/api/server.py` | 1608 | FastAPI服务器，完整REST API |
| `src/mcp/__init__.py` | 530+ | MCP服务端，8个工具 |
| `src/memory/engine.py` | 616 | 四层记忆引擎 |

---

## 🛠️ 技术栈

- **语言**: Python 3.11+
- **框架**: FastAPI + Uvicorn + Typer + Rich
- **数据库**: SQLite + FTS5
- **LLM**: Ollama / OpenAI / DeepSeek
- **协议**: OACP (OpenNewt Agent Communication Protocol)
- **容器**: Docker + Docker Compose

---

## 📖 文档

- [快速开始](docs/getting-started/quickstart.md)
- [架构文档](docs/architecture/overview.md)
- [CLI 参考](docs/cli-reference.md)

---

## 🤝 贡献

欢迎提交 Issue 和 PR！

```bash
git clone https://github.com/axonewt/axonewt-engine.git
cd axonewt-engine
pip install -e ".[dev]"
pytest tests/
```

---

## 📄 License

MIT License - 详见 [LICENSE](LICENSE)

---

_🦎 让 AI 真正有用，而不是表演有用。_
