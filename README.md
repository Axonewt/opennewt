<p align="center">
  <strong>OpenNewt Engine</strong>
</p>

<p align="center">
  <strong>Regenerative Neural Infrastructure for Edge AI</strong><br>
  <em>Like a salamander regrows its tail, your AI systems self-heal after damage.</em>
</p>

<p align="center">
  <a href="https://github.com/Axonewt/opennewt-engine"><img src="https://img.shields.io/badge/version-0.3.0-blue" alt="Version"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-green" alt="Python 3.12+"></a>
  <a href="https://github.com/Axonewt/opennewt-engine/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-orange" alt="License"></a>
</p>

---

## What is OpenNewt?

OpenNewt is a **self-healing engine** for AI infrastructure. It monitors your codebase, detects damage, generates repair plans using LLM, and automatically executes fixes — all without human intervention.

Unlike monitoring tools that just **alert** you when things break, OpenNewt **repairs** them.

### Core Innovation: Neural Plasticity

Inspired by biological nervous systems, OpenNewt applies four principles:

| Biological Principle | OpenNewt Equivalent |
|---|---|
| Pain receptors detect injury | **Soma** — continuous health scanning |
| Neural pathways route signals | **Message Bus** — agent communication |
| Plasticity rewires connections | **Plasticus** — LLM-powered repair planning |
| Memory stores successful responses | **Mnemosyne** — immune memory for fast response |

**One-liner**: Not "better monitoring" — but "regenerative nervous system for AI infrastructure."

---

## Quick Start

### Prerequisites

- Python 3.12+
- An LLM provider (Ollama for local, or OpenAI/DeepSeek API keys)

### Install & Run

```bash
# Clone the repository
git clone https://github.com/Axonewt/opennewt-engine.git
cd opennewt-engine

# Create virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy configuration
cp .env.example .env

# Start the API server
python api_server.py --port 8088
```

That's it. The API server is now running at `http://127.0.0.1:8088`.

Open **http://127.0.0.1:8088** for the real-time Dashboard, or **http://127.0.0.1:8088/docs** for interactive API documentation (Swagger UI).

### Verify It Works

```bash
# Health check
curl http://127.0.0.1:8088/health

# Scan your codebase
curl -X POST http://127.0.0.1:8088/api/scan

# Register a target for monitoring
curl -X POST http://127.0.0.1:8088/api/targets \
  -H "Content-Type: application/json" \
  -d '{"name":"my-project","path":"/path/to/your/project"}'

# Trigger a full self-heal cycle (scan -> plan -> execute -> verify)
curl -X POST http://127.0.0.1:8088/api/repair
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    REST API (FastAPI)                  │
│              http://127.0.0.1:8088                     │
├──────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────┐   SIGNAL    ┌───────────┐  BLUEPRINT    │
│  │  Soma   │────────────▶│ Plasticus │─────────────┐ │
│  │(Percept)│             │ (Decision)│              │ │
│  └─────────┘             └───────────┘              ▼ │
│       │                                        ┌──────────┐  REPORT   ┌──────────┐
│       │ health_score                           │ Effector │─────────▶│Mnemosyne │
│       │                                        │(Execute) │           │ (Memory) │
│       ▼                                        └──────────┘           └──────────┘
│  ┌──────────┐                                                          │
│  │  Target   │◀── register/scan ───────────── REST API ───────────────┘
│  │(Your Code)│
│  └──────────┘
│
│  ┌─────────────────────────┐
│  │      LLM Providers      │
│  │  Ollama / OpenAI / DeepSeek  │
│  └─────────────────────────┘
└──────────────────────────────────────────────────────┘
```

### Four-Layer Agent System

1. **Soma (Perception)** — Scans codebase health using AST analysis, static checks, and complexity metrics. Triggers repair when health drops below threshold.

2. **Plasticus (Decision)** — Generates multiple repair plans using LLM, evaluates them with a plasticity assessment matrix, and selects the optimal approach.

3. **Effector (Execution)** — Executes approved repairs: file modifications, Git operations, process management. Supports auto-rollback on failure.

4. **Mnemosyne (Memory)** — Records all events in SQLite, maintains immune memory of successful repair patterns for faster future response.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Engine health check |
| `GET` | `/api/status` | Detailed engine status |
| `GET` | `/api/stats` | Engine statistics |
| `GET` | `/api/agents` | Agent status overview |
| `POST` | `/api/scan` | Trigger Soma health scan |
| `POST` | `/api/repair` | Full self-heal cycle (sync) |
| `POST` | `/api/repair/async` | Async self-heal (returns task_id) |
| `GET` | `/api/repair/{id}` | Query repair task status |
| `GET` | `/api/repairs` | List all repair tasks |
| `POST` | `/api/targets` | Register a monitoring target |
| `GET` | `/api/targets` | List all targets |
| `DELETE` | `/api/targets/{id}` | Remove a target |
| `POST` | `/api/targets/{id}/scan` | Manually scan a target |
| `GET` | `/api/events` | Event history (paginated) |
| `GET` | `/api/immune-memory` | Successful repair patterns |
| `POST` | `/api/llm/chat` | LLM proxy (multi-provider) |
| `GET` | `/api/llm/models` | List available LLM models |
| `WS` | `/ws/logs` | Real-time log streaming |

Full interactive docs at `/docs` (Swagger UI) or `/redoc` (ReDoc).

---

## MCP Server

OpenNewt exposes 8 tools via the [Model Context Protocol](https://modelcontextprotocol.io), enabling direct integration with **Claude Desktop**, **Cursor**, **Windsurf**, and any MCP-compatible client.

### Available Tools

| Tool | Description |
|------|-------------|
| `scan_health` | Scan codebase health (multi-dimensional analysis) |
| `repair` | End-to-end self-healing (scan → AI plan → execute) |
| `register_target` | Register a codebase for continuous monitoring |
| `list_targets` | List all registered targets |
| `scan_target` | Manually trigger a scan for a specific target |
| `get_events` | Query engine event history |
| `get_stats` | Engine-wide statistics and agent status |
| `get_immune_memory` | Query successful repair patterns |

### Claude Desktop Configuration

Add to your Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "opennewt": {
      "command": "python",
      "args": ["-m", "src.mcp"],
      "cwd": "D:/opennewt-engine",
      "env": {
        "PYTHONPATH": "D:/opennewt-engine"
      }
    }
  }
}
```

### Cursor / Windsurf

Add to `.cursor/mcp.json` or MCP settings:

```json
{
  "mcpServers": {
    "opennewt": {
      "command": "python",
      "args": ["-m", "src.mcp"],
      "cwd": "/path/to/opennewt-engine",
      "env": {
        "PYTHONPATH": "/path/to/opennewt-engine"
      }
    }
  }
}
```

### SSE Mode (HTTP Transport)

For non-stdio clients or remote access:

```bash
python -m src.mcp --transport sse --port 9010
```

---

## Configuration

Edit `config.yaml`:

```yaml
llm:
  provider: "ollama"        # "ollama" | "openai" | "deepseek"
  model: "glm-4.7-flash:latest"
  base_url: "http://127.0.0.1:11434"

agents:
  soma:
    health_threshold: 0.7   # Trigger repair below this score
    scan_interval: 30       # Seconds between scans

api:
  host: "127.0.0.1"
  port: 8088

monitoring:
  tick_interval: 30         # Main loop interval (seconds)
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENNEWT_API_KEY` | Enable API key auth (set any value) | Disabled |
| `GITHUB_TOKEN` | GitHub API token for PR operations | None |
| `DEEPSEEK_API_KEY` | DeepSeek API key | None |
| `OPENAI_API_KEY` | OpenAI API key | None |

---

## Use Cases

### 1. Codebase Self-Healing
```bash
# Register your project and let OpenNewt monitor & fix it
curl -X POST http://127.0.0.1:8088/api/targets \
  -d '{"name":"my-api","path":"/home/user/my-api","auto_repair":true}'
```

### 2. One-Shot Repair
```bash
# Something broke? Ask OpenNewt to fix it
curl -X POST http://127.0.0.1:8088/api/repair
```

### 3. LLM Gateway
```bash
# Use OpenNewt as a unified LLM proxy
curl -X POST http://127.0.0.1:8088/api/llm/chat \
  -d '{"messages":[{"role":"user","content":"Hello"}],"provider":"deepseek"}'
```

---

## Roadmap

- [x] **Phase 1** — Engine boot: perception → decision → memory loop
- [x] **Phase 2** — Self-heal cycle: end-to-end autonomous repair
- [x] **Phase 3** — REST API: full HTTP interface for any client
- [x] **Phase 4** — MCP Server: native integration with Claude/Cursor
- [x] **Phase 5** — Dashboard: real-time web UI for monitoring
- [x] **Phase 6** — Docker: containerized deployment
- [ ] **Phase 7** — Multi-node: distributed healing for microservices
- [ ] **Phase 8** — Enterprise: auth, RBAC, audit logs

---

## Key Concepts

| Term | Meaning |
|------|---------|
| **Synaptic Rewiring** | Rebuild pathways within 3s when a node fails |
| **Neural Plasticity** | Adapt to new environments without retraining |
| **Adaptive Routing** | Auto-accelerate high-frequency paths |
| **Collateral Sprouting** | Activate backup paths when primary fails |
| **Dry Run** | Simulate repair, only execute if success rate > 90% |
| **Gradual Cutover** | Switch engines mid-flight, zero downtime |
| **Immune Memory** | Leverage historical success patterns for faster response |

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>OpenNewt</strong> — AI infrastructure that heals itself.<br>
  <a href="https://github.com/Axonewt/opennewt-engine">GitHub</a> · MIT License
</p>
