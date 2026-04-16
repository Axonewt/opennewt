# Axonewt 架构文档

> 火蜥蜴再生神经可塑性引擎 — 技术架构详解

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    REST API (FastAPI)                            │
│              http://127.0.0.1:5055 / WebSocket                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────┐   SIGNAL    ┌───────────┐  BLUEPRINT   ┌──────────┐│
│  │  Soma   │───────────▶│ Plasticus  │─────────────▶│ Effector ││
│  │(Percept)│            │ (Decision) │              │(Execute) ││
│  └─────────┘             └───────────┘              └────┬─────┘│
│       │                                                  │       │
│       │ health_score                                     │ report│
│       ▼                                                  ▼       │
│  ┌──────────┐                                        ┌──────────┐│
│  │  Target   │◀── register/scan ── REST API ──────────│Mnemosyne ││
│  │(Your Code)│                                        │ (Memory) ││
│  └──────────┘                                         └──────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    MCP Server (可选)                       │   │
│  │  scan_health | repair | register_target | get_events | ... │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 🦎 四层 Agent 系统

### Soma（感知层）

**职责**：持续监控代码库健康度，检测损伤，触发再生循环。

| 能力 | 说明 |
|------|------|
| AST 静态分析 | Python 代码复杂度、docstring、函数长度 |
| 测试覆盖率扫描 | 统计 test_*.py 比例 |
| 依赖健康度 | requirements.txt、安全漏洞检测 |
| 文档完整度 | README.md、docs/ 目录 |

```python
from src.agents.soma_dev import SomaDev

soma = SomaDev(project_path="/path/to/project")
report = soma.scan_codebase()
# report["health_score"] → 0.0 ~ 1.0
```

### Plasticus（决策层）

**职责**：接收损伤信号，生成多套修复方案，评估并选择最优。

```python
from src.agents.plasticus_dev import PlasticusDev

plasticus = PlasticusDev(
    ollama_url="http://127.0.0.1:11434",
    ollama_model="glm-4.7-flash:latest"
)
plans = plasticus.generate_plans(
    damage_type="CODE_DECAY",
    location="src/api/server.py",
    symptoms=["健康度 0.62 < 0.7"],
    health_score=0.62
)
best_plan = plasticus.evaluate_plans(plans)
```

### Effector（执行层）

**职责**：执行修复蓝图，渐进式修改代码，自动回滚。

```python
from src.agents.effector_dev import EffectorDev
from src.protocol.oacp import BlueprintMessage

effector = EffectorDev(project_path="/path/to/project")
report = effector.execute_blueprint(blueprint)
```

### Mnemosyne（记忆层）

**职责**：记录所有事件，维护免疫记忆，提供历史案例查询。

```python
from src.agents.mnemosyne_dev import MnemosyneDev

mnemosyne = MnemosyneDev(db_path="data/opennewt.db")
stats = mnemosyne.get_statistics()
similar = mnemosyne.query_similar_cases(damage_type="CODE_DECAY", symptoms=[])
```

## 🔄 OACP 协议

```
SIGNAL ──▶ BLUEPRINT ──▶ EXECUTION_REPORT
 (Soma)    (Plasticus)    (Effector)
                 │
                 └── QUERY ──▶ EXECUTION_REPORT
                   (Mnemosyne)
```

| 消息类型 | 源 | 目标 | 说明 |
|---------|-----|------|------|
| `SIGNAL` | Soma | Plasticus | 损伤报告 |
| `BLUEPRINT` | Plasticus | Effector | 修复方案 |
| `EXECUTION_REPORT` | Effector | Mnemosyne | 执行结果 |
| `QUERY` | Plasticus | Mnemosyne | 历史查询 |

## 🧠 四层记忆架构

```
┌──────────────────────────────────────────┐
│         QuadMemoryEngine (统一入口)         │
├──────────┬──────────┬──────────┬──────────┤
│  L1      │  L2      │  L3      │  L4      │
│ Index     │ Context  │ Cache    │ Graph    │
│ 索引      │ 上下文   │ 缓存     │ 图谱     │
│ (常驻)    │ (FTS5)   │ (会话)   │ (持久)   │
│ ≤25KB    │ 全文搜索  │ 自动蒸馏  │ 影响分析 │
└──────────┴──────────┴──────────┴──────────┘
```

## 🌐 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/status` | GET | 引擎状态 |
| `/api/scan` | POST | 扫描代码库 |
| `/api/repair` | POST | 同步自愈 |
| `/api/repair/async` | POST | 异步自愈 |
| `/api/repair/{id}` | GET | 查询任务 |
| `/api/targets` | POST | 注册目标 |
| `/api/targets` | GET | 列出目标 |
| `/api/events` | GET | 事件历史 |
| `/api/stats` | GET | 全局统计 |
| `/api/immune-memory` | GET | 免疫记忆 |
| `/api/llm/chat` | POST | LLM 代理 |
| `/ws/logs` | WS | 实时日志 |

## 🚀 部署架构

### 开发模式
```bash
python api_server.py --port 5055
```

### Docker 模式
```bash
docker-compose up -d
```

### MCP 集成
```bash
# Claude Desktop 配置
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

## 📊 数据流

```
用户请求 → FastAPI → EngineState → Agent 初始化
                            ↓
                       Soma 扫描
                            ↓
                     健康度评估
                            ↓
            ┌───────────────┴───────────────┐
            ↓                               ↓
       健康 ≥ 0.7                      健康 < 0.7
       (无需操作)                   触发修复链路
                                       ↓
                              SIGNAL → Plasticus
                                       ↓
                                 BLUEPRINT
                                       ↓
                                  Effector
                                       ↓
                               EXECUTION_REPORT
                                       ↓
                                  Mnemosyne
                                       ↓
                               返回结果给用户
```
