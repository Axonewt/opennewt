"""
OpenNewt Engine v0.3 — REST API Server

Phase 3: 产品级 HTTP API，替代 Bridge 文件系统通信。

架构:
    FastAPI + Uvicorn
    所有 Agent 通过 REST API 暴露
    WebSocket 实时日志推送
    API Key 基础鉴权

启动:
    python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8088 --reload
    或:
    python api_server.py --port 8088

API 端点:
    GET  /health              — 引擎健康检查（免鉴权）
    GET  /api/status          — 引擎状态（版本、Agent、配置）
    POST /api/scan            — Soma 扫描代码库健康度
    POST /api/repair          — 端到端自愈（扫描→决策→执行→返回报告）
    POST /api/repair/async    — 异步自愈（返回 task_id，后台执行）
    GET  /api/repair/{id}     — 查询自愈任务状态
    GET  /api/repairs         — 列出所有自愈任务
    POST /api/targets         — 注册守护目标
    GET  /api/targets         — 列出所有守护目标
    DELETE /api/targets/{id}  — 删除守护目标
    GET  /api/events          — 事件历史流
    GET  /api/agents          — Agent 状态概览
    GET  /api/stats           — 引擎统计数据
    POST /api/llm/chat        — LLM 代理（OpenAI/DeepSeek/Ollama）
    GET  /api/llm/models      — 列出可用 LLM 模型
    WS   /ws/logs             — 实时日志推送
"""

import os
import sys
import json
import asyncio
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

# Project root — server.py is in src/api/, so go up 2 levels
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import yaml

# ============================================================================
# 日志
# ============================================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("axonewt-api")

# ============================================================================
# 日志广播器（WebSocket 推送用）
# ============================================================================

class LogBroadcaster:
    """实时日志广播到所有 WebSocket 客户端"""

    def __init__(self):
        self.clients: List[WebSocket] = []
        self._buffer: List[str] = []
        self._max_buffer = 500

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)
        # 发送历史日志
        for line in self._buffer[-100:]:
            try:
                await ws.send_text(line)
            except Exception:
                pass
        logger.info(f"WebSocket client connected (total: {len(self.clients)})")

    def disconnect(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, message: str):
        self._buffer.append(message)
        if len(self._buffer) > self._max_buffer:
            self._buffer = self._buffer[-self._max_buffer:]
        disconnected = []
        for ws in self.clients:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


broadcaster = LogBroadcaster()


class APIHandler(logging.Handler):
    """将日志同时广播到 WebSocket"""

    def emit(self, record):
        try:
            msg = self.format(record)
            # 同步广播（通过事件循环）
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(broadcaster.broadcast(msg))
            except RuntimeError:
                pass
        except Exception:
            pass


# 给 uvicorn access log 和自定义 logger 都加上广播
api_handler = APIHandler()
api_handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s"))
logging.getLogger("axonewt-api").addHandler(api_handler)

# ============================================================================
# 配置
# ============================================================================

def load_config() -> dict:
    path = ROOT / "config.yaml"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


# ============================================================================
# Pydantic Models
# ============================================================================

class ScanRequest(BaseModel):
    """扫描请求"""
    project_path: Optional[str] = None  # None = 使用配置中的路径
    full_report: bool = False  # 是否返回完整报告


class RepairRequest(BaseModel):
    """修复请求"""
    project_path: Optional[str] = None
    auto_approve: bool = True  # 自动批准敏感操作
    use_llm: bool = True  # 使用 LLM 生成修复方案
    health_threshold: float = 0.7  # 触发修复的健康度阈值


class LLMChatRequest(BaseModel):
    """LLM 聊天请求"""
    messages: List[Dict[str, str]]
    model: Optional[str] = None  # None = 使用配置中的默认模型
    provider: Optional[str] = None  # "ollama" | "openai" | "deepseek"
    temperature: float = 0.7
    max_tokens: int = 2048


class LLMChatResponse(BaseModel):
    """LLM 聊天响应"""
    content: str
    model: str
    provider: str
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None


# ============================================================================
# 引擎状态管理
# ============================================================================

class EngineState:
    """引擎全局状态"""

    def __init__(self):
        self.config: dict = {}
        self.started_at: str = ""
        self.scan_count: int = 0
        self.repair_count: int = 0
        self.repair_tasks: Dict[str, Dict[str, Any]] = {}
        # Agent 实例（延迟初始化）
        self._soma = None
        self._plasticus = None
        self._effector = None
        self._mnemosyne = None
        # Daemon 状态
        self.daemon_running: bool = False
        self.daemon_task: Optional[asyncio.Task] = None
        self.daemon_interval: int = 60  # 默认 60 秒扫描间隔
        self.daemon_last_tick: str = ""
        self.daemon_tick_count: int = 0
        # 健康度趋势（每个 target 保留最近 20 次扫描）
        self._health_history: Dict[str, List[Dict]] = {}
        self._max_history = 20

    def init_agents(self):
        """初始化所有 Agent"""
        from src.agents.soma_dev import SomaDev
        from src.agents.plasticus_dev import PlasticusDev
        from src.agents.effector_dev import EffectorDev
        from src.agents.mnemosyne_dev import MnemosyneDev

        db_path = str(ROOT / "data" / "opennewt.db")
        github_token = os.getenv("GITHUB_TOKEN")

        self._mnemosyne = MnemosyneDev(db_path=db_path)
        self._soma = SomaDev(project_path=str(ROOT), github_token=github_token)

        llm_cfg = self.config.get("llm", {})
        llm_provider = llm_cfg.get("provider", "ollama")

        if llm_provider == "workbuddy":
            self._plasticus = PlasticusDev(workbuddy_enabled=True, github_token=github_token)
        elif llm_provider == "ollama":
            self._plasticus = PlasticusDev(
                ollama_url=llm_cfg.get("base_url", "http://127.0.0.1:11434"),
                ollama_model=llm_cfg.get("model", "glm-4.7-flash:latest"),
                github_token=github_token
            )
        else:
            self._plasticus = PlasticusDev(
                ollama_url=llm_cfg.get("base_url", "http://127.0.0.1:11434"),
                ollama_model=llm_cfg.get("model", "glm-4.7-flash:latest"),
                github_token=github_token
            )

        self._effector = EffectorDev(project_path=str(ROOT), github_token=github_token)

        logger.info("All agents initialized")

    @property
    def soma(self):
        if self._soma is None:
            self.init_agents()
        return self._soma

    @property
    def plasticus(self):
        if self._plasticus is None:
            self.init_agents()
        return self._plasticus

    @property
    def effector(self):
        if self._effector is None:
            self.init_agents()
        return self._effector

    @property
    def mnemosyne(self):
        if self._mnemosyne is None:
            self.init_agents()
        return self._mnemosyne


engine_state = EngineState()

# ============================================================================
# FastAPI App
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    engine_state.config = load_config()
    engine_state.started_at = datetime.now().isoformat()

    # Daemon 配置
    daemon_cfg = engine_state.config.get("daemon", {})
    engine_state.daemon_interval = daemon_cfg.get("interval", 60)

    logger.info("OpenNewt API Server starting...")
    logger.info(f"Project: {ROOT}")
    logger.info(f"Daemon interval: {engine_state.daemon_interval}s")

    # 启动 Daemon 后台监控循环
    engine_state.daemon_running = True
    engine_state.daemon_task = asyncio.create_task(
        daemon_monitor_loop(),
        name="daemon-monitor"
    )
    logger.info("Daemon monitor started")

    yield

    # 关闭 Daemon
    engine_state.daemon_running = False
    if engine_state.daemon_task and not engine_state.daemon_task.done():
        engine_state.daemon_task.cancel()
        try:
            await engine_state.daemon_task
        except asyncio.CancelledError:
            pass
    logger.info("Daemon monitor stopped")
    logger.info("OpenNewt API Server shutting down...")


app = FastAPI(
    title="OpenNewt Engine API",
    description="Axonewt Neural Plasticity Engine — REST API v0.3",
    version="0.3.0",
    lifespan=lifespan,
)

# Serve Dashboard static files
_dashboard_dir = ROOT / "dashboard"
if _dashboard_dir.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(_dashboard_dir)), name="dashboard")


# ============================================================================
# 根路由
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Redirect to Dashboard"""
    from starlette.responses import RedirectResponse
    return RedirectResponse(url="/dashboard/index.html")


@app.get("/health")
async def health_check():
    """引擎健康检查（供负载均衡器/监控系统使用）"""
    return {
        "status": "ok",
        "version": "0.3.0",
        "uptime_seconds": (
            datetime.now() - datetime.fromisoformat(engine_state.started_at)
        ).total_seconds() if engine_state.started_at else 0,
    }


@app.get("/api/status")
async def get_status():
    """引擎详细状态"""
    return {
        "version": "0.3.0",
        "started_at": engine_state.started_at,
        "project_path": str(ROOT),
        "scan_count": engine_state.scan_count,
        "repair_count": engine_state.repair_count,
        "active_repairs": len([
            t for t in engine_state.repair_tasks.values() if t["status"] == "running"
        ]),
        "llm_provider": engine_state.config.get("llm", {}).get("provider", "ollama"),
        "llm_model": engine_state.config.get("llm", {}).get("model", "glm-4.7-flash:latest"),
    }


# ============================================================================
# Soma: 代码扫描 API
# ============================================================================

@app.post("/api/scan")
async def scan_codebase(req: ScanRequest = ScanRequest()):
    """扫描代码库健康度

    调用 Soma 进行多维度健康评估，返回详细报告。
    """
    try:
        logger.info("Starting codebase scan...")
        engine_state.scan_count += 1

        report = engine_state.soma.scan_codebase()

        logger.info(f"Scan complete: health={report['health_score']:.3f}")

        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "health_score": report["health_score"],
            "health_status": report.get("health_status", "unknown"),
            "needs_repair": report["health_score"] < 0.7,
            "metrics": {
                "static_analysis": report.get("static_analysis_score"),
                "test_coverage": report.get("test_coverage"),
                "dependency_health": report.get("dependency_health"),
                "code_complexity": report.get("code_complexity"),
                "historical_stability": report.get("historical_stability"),
                "documentation": report.get("documentation_completeness"),
            },
            "issues": report.get("issues", []),
            "full_report": report if req.full_report else None,
        }

    except Exception as e:
        logger.error(f"Scan failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")


# ============================================================================
# 端到端自愈 API
# ============================================================================

def _run_repair_sync(task_id: str, req: RepairRequest):
    """同步执行自愈流程（在后台线程中运行）"""
    try:
        task = engine_state.repair_tasks[task_id]
        task["status"] = "running"
        task["started_at"] = datetime.now().isoformat()
        logger.info(f"[Repair {task_id}] Starting repair cycle...")

        # Phase 1: 感知 — Soma 扫描
        logger.info(f"[Repair {task_id}] Phase 1: Scanning health...")
        soma_report = engine_state.soma.scan_codebase()
        health_score = soma_report["health_score"]
        task["health_score_before"] = health_score
        logger.info(f"[Repair {task_id}] Health score: {health_score:.3f}")

        if health_score >= req.health_threshold:
            task["status"] = "skipped"
            task["message"] = f"Health score {health_score:.3f} >= threshold {req.health_threshold}, no repair needed"
            task["finished_at"] = datetime.now().isoformat()
            logger.info(f"[Repair {task_id}] Skipped: system healthy")
            return

        # Phase 2: 决策 — Plasticus 生成修复方案
        logger.info(f"[Repair {task_id}] Phase 2: Generating repair plans...")
        plans = engine_state.plasticus.generate_plans(
            damage_type="CODE_DECAY",
            location="detected by API scan",
            symptoms=[f"Health score {health_score:.3f}"],
            health_score=health_score,
            use_llm=req.use_llm,
            use_multi_sample=False
        )

        if not plans:
            task["status"] = "no_plans"
            task["message"] = "No repair plans generated"
            task["finished_at"] = datetime.now().isoformat()
            logger.info(f"[Repair {task_id}] No plans generated")
            return

        best_plan = engine_state.plasticus.evaluate_plans(plans)
        task["plan_name"] = best_plan.name
        task["plan_steps"] = len(best_plan.steps)
        logger.info(f"[Repair {task_id}] Best plan: {best_plan.name} ({len(best_plan.steps)} steps)")

        # Phase 3: 执行 — Effector 执行修复
        logger.info(f"[Repair {task_id}] Phase 3: Executing repair...")

        from src.protocol.oacp import BlueprintMessage

        if req.auto_approve:
            os.environ["EFFECTOR_AUTO_APPROVE"] = "true"

        blueprint = BlueprintMessage.create(
            plan_id=f"API-{task_id[:8]}",
            strategy=best_plan.name,
            steps=[
                {
                    "number": i + 1,
                    "name": step.get("name", step.get("description", f"Step {i+1}")),
                    "description": step.get("description", ""),
                    "action": step.get("description", f"Step {i+1}"),
                    "type": step.get("type", "generic"),
                    "file_path": step.get("file_path"),
                    "content": step.get("content"),
                }
                for i, step in enumerate(best_plan.steps)
            ],
            estimated_downtime=f"{best_plan.downtime_seconds}s",
            success_rate_prediction=best_plan.historical_success_rate,
            rollback_plan="Revert changes"
        )

        report = engine_state.effector.execute_blueprint(blueprint)

        task["repair_status"] = report.payload.get("status")
        task["steps_completed"] = report.payload.get("steps_completed", 0)
        task["steps_total"] = report.payload.get("steps_total", 0)
        task["errors"] = report.payload.get("errors", [])

        # Phase 4: 验证 — 重新扫描
        logger.info(f"[Repair {task_id}] Phase 4: Verifying repair...")
        post_report = engine_state.soma.scan_codebase()
        post_health = post_report["health_score"]
        task["health_score_after"] = post_health
        task["health_delta"] = round(post_health - health_score, 3)

        task["status"] = "success" if post_health > health_score else "partial"
        task["finished_at"] = datetime.now().isoformat()
        logger.info(f"[Repair {task_id}] Complete: {health_score:.3f} -> {post_health:.3f} (delta: {post_health - health_score:+.3f})")

        # 记录到 Mnemosyne
        try:
            from src.agents.mnemosyne_dev import Event
            event = Event(
                event_id=f"API-{task_id}",
                timestamp=datetime.now().isoformat() + "Z",
                agent="API-Server",
                event_type="REPAIR",
                payload={
                    "plan": best_plan.name,
                    "status": task["status"],
                    "health_before": health_score,
                    "health_after": post_health,
                    "steps_completed": task["steps_completed"],
                }
            )
            engine_state.mnemosyne.log_event(event)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[Repair {task_id}] Failed: {e}")
        traceback.print_exc()
        task["status"] = "failed"
        task["message"] = str(e)
        task["errors"] = [str(e)]
        task["finished_at"] = datetime.now().isoformat()


@app.post("/api/repair")
async def repair_sync(req: RepairRequest = RepairRequest(), background_tasks: BackgroundTasks = None):
    """同步端到端自愈

    完整流程：Soma扫描 → Plasticus决策 → Effector执行 → 验证
    返回完整修复报告。可能需要 30-120 秒。
    """
    task_id = f"R-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    engine_state.repair_tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }

    # 在线程池中运行同步代码
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_repair_sync, task_id, req)

    engine_state.repair_count += 1
    return engine_state.repair_tasks[task_id]


@app.post("/api/repair/async")
async def repair_async(req: RepairRequest = RepairRequest()):
    """异步端到端自愈

    立即返回 task_id，后台执行修复。
    通过 GET /api/repair/{id} 查询进度。
    """
    task_id = f"R-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    engine_state.repair_tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
    }

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_repair_sync, task_id, req)

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Repair task started. Poll /api/repair/{task_id} for progress.",
        "poll_url": f"/api/repair/{task_id}",
    }


@app.get("/api/repair/{task_id}")
async def get_repair_status(task_id: str):
    """查询自愈任务状态"""
    task = engine_state.repair_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.get("/api/repairs")
async def list_repairs():
    """列出所有自愈任务"""
    return {
        "total": len(engine_state.repair_tasks),
        "tasks": list(engine_state.repair_tasks.values())
    }


# ============================================================================
# LLM 代理 API
# ============================================================================

@app.post("/api/llm/chat", response_model=LLMChatResponse)
async def llm_chat(req: LLMChatRequest):
    """通用 LLM 代理

    统一接口，支持 OpenAI / DeepSeek / Ollama。
    通过 provider 参数切换后端。
    """
    try:
        llm_cfg = engine_state.config.get("llm", {})
        provider = req.provider or llm_cfg.get("provider", "ollama")
        model = req.model or llm_cfg.get("model", "glm-4.7-flash:latest")

        logger.info(f"LLM chat: provider={provider}, model={model}, messages={len(req.messages)}")

        if provider == "ollama":
            from src.integrations.ollama_client import OllamaClient
            client = OllamaClient(
                base_url=llm_cfg.get("base_url", "http://127.0.0.1:11434"),
                model=model
            )
            # 构造 prompt
            prompt = "\n".join(
                f"{'[User]' if m['role'] == 'user' else '[Assistant]'} {m['content']}"
                for m in req.messages
            )
            result = client.generate(prompt)
            return LLMChatResponse(
                content=result.text,
                model=model,
                provider=provider,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
            )

        elif provider in ("openai", "deepseek"):
            try:
                from openai import OpenAI
            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="openai package not installed. Run: pip install openai"
                )

            # DeepSeek 兼容 OpenAI API
            if provider == "deepseek":
                api_key = os.getenv("DEEPSEEK_API_KEY", "")
                base_url = llm_cfg.get("deepseek", {}).get("base_url", "https://api.deepseek.com/v1")
                model = model or "deepseek-chat"
            else:
                api_key = os.getenv("OPENAI_API_KEY", "")
                base_url = llm_cfg.get("openai", {}).get("base_url", None)
                model = model or "gpt-4o-mini"

            kwargs: Dict[str, Any] = {
                "api_key": api_key,
                "model": model,
            }
            if base_url:
                kwargs["base_url"] = base_url

            client = OpenAI(**kwargs)
            response = client.chat.completions.create(
                model=model,
                messages=req.messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
            )

            choice = response.choices[0]
            return LLMChatResponse(
                content=choice.message.content,
                model=model,
                provider=provider,
                tokens_in=response.usage.prompt_tokens if response.usage else None,
                tokens_out=response.usage.completion_tokens if response.usage else None,
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider: {provider}. Supported: ollama, openai, deepseek"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LLM chat failed: {e}")
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")


@app.get("/api/llm/models")
async def list_llm_models():
    """列出可用的 LLM 模型"""
    llm_cfg = engine_state.config.get("llm", {})
    provider = llm_cfg.get("provider", "ollama")

    models = {
        "current_provider": provider,
        "current_model": llm_cfg.get("model", "glm-4.7-flash:latest"),
        "supported_providers": ["ollama", "openai", "deepseek"],
    }

    # 尝试获取 Ollama 模型列表
    if provider == "ollama":
        try:
            import requests
            base_url = llm_cfg.get("base_url", "http://127.0.0.1:11434")
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                ollama_models = [m["name"] for m in resp.json().get("models", [])]
                models["ollama_available"] = ollama_models
        except Exception:
            models["ollama_available"] = ["connection_failed"]

    return models


# ============================================================================
# WebSocket: 实时日志
# ============================================================================

@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    """WebSocket 实时日志推送

    连接后接收引擎所有日志输出。
    """
    await broadcaster.connect(websocket)
    try:
        while True:
            # 保持连接，客户端可发 ping
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.disconnect(websocket)


# ============================================================================
# 历史记录 API
# ============================================================================

# ============================================================================
# 事件历史 API
# ============================================================================

@app.get("/api/events")
async def get_event_history(
    limit: int = 50,
    offset: int = 0,
    event_type: Optional[str] = None,
    agent: Optional[str] = None,
):
    """查询引擎事件历史

    支持分页和按类型/Agent 过滤。
    """
    try:
        import sqlite3
        db_path = str(ROOT / "data" / "opennewt.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        where_clauses = []
        params: list = []
        if event_type:
            where_clauses.append("event_type = ?")
            params.append(event_type)
        if agent:
            where_clauses.append("agent = ?")
            params.append(agent)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Count
        cursor.execute(f"SELECT COUNT(*) FROM event_log {where_sql}", params)
        total = cursor.fetchone()[0]

        # Fetch
        cursor.execute(
            f"SELECT event_id, timestamp, agent, event_type, payload, tags "
            f"FROM event_log {where_sql} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        rows = cursor.fetchall()
        conn.close()

        events = []
        for row in rows:
            try:
                payload = json.loads(row["payload"]) if row["payload"] else {}
            except (json.JSONDecodeError, TypeError):
                payload = {}
            try:
                tags = json.loads(row["tags"]) if row["tags"] else []
            except (json.JSONDecodeError, TypeError):
                tags = []
            events.append({
                "event_id": row["event_id"],
                "timestamp": row["timestamp"],
                "agent": row["agent"],
                "event_type": row["event_type"],
                "payload": payload,
                "tags": tags,
            })

        return {
            "events": events,
            "count": len(events),
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error(f"Failed to query events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 免疫记忆 API
# ============================================================================

@app.get("/api/immune-memory")
async def get_immune_memory(limit: int = 20):
    """查询免疫记忆（历史成功修复模式）"""
    try:
        import sqlite3
        db_path = str(ROOT / "data" / "opennewt.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM immune_memory ORDER BY success_rate DESC, usage_count DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()

        memories = []
        for row in rows:
            try:
                symptoms = json.loads(row["symptoms"]) if row["symptoms"] else []
            except (json.JSONDecodeError, TypeError):
                symptoms = []
            try:
                steps = json.loads(row["steps"]) if row["steps"] else []
            except (json.JSONDecodeError, TypeError):
                steps = []
            memories.append({
                "template_id": row["template_id"],
                "damage_type": row["damage_type"],
                "symptoms": symptoms,
                "repair_strategy": row["repair_strategy"],
                "steps": steps,
                "success_rate": row["success_rate"],
                "last_used": row["last_used"],
                "usage_count": row["usage_count"],
            })

        return {"immune_memory": memories, "count": len(memories)}
    except Exception as e:
        logger.error(f"Failed to query immune memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Agent 状态 API
# ============================================================================

@app.get("/api/agents")
async def get_agents_status():
    """获取所有 Agent 的状态概览"""
    try:
        agents_info = {
            "soma": {
                "name": "Soma-Dev",
                "role": "Perception Layer",
                "description": "Code health scanner, damage detector",
                "status": "ready" if engine_state._soma else "lazy",
            },
            "plasticus": {
                "name": "Plasticus-Dev",
                "role": "Decision Layer",
                "description": "Repair plan generator, LLM-powered decision making",
                "status": "ready" if engine_state._plasticus else "lazy",
            },
            "effector": {
                "name": "Effector-Dev",
                "role": "Execution Layer",
                "description": "Code modification, Git operations, process management",
                "status": "ready" if engine_state._effector else "lazy",
            },
            "mnemosyne": {
                "name": "Mnemosyne-Dev",
                "role": "Memory Layer",
                "description": "Event logging, code graph, immune memory",
                "status": "ready" if engine_state._mnemosyne else "lazy",
            },
        }

        # 从数据库获取统计
        try:
            stats = engine_state.mnemosyne.get_statistics()
            agents_info["mnemosyne"]["statistics"] = stats
        except Exception:
            pass

        return {
            "agents": agents_info,
            "total_agents": 4,
            "active_agents": sum(1 for a in agents_info.values() if a["status"] == "ready"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 统计 API
# ============================================================================

@app.get("/api/stats")
async def get_engine_stats():
    """引擎全局统计"""
    try:
        stats = {
            "version": "0.3.0",
            "uptime_seconds": (
                datetime.now() - datetime.fromisoformat(engine_state.started_at)
            ).total_seconds() if engine_state.started_at else 0,
            "scan_count": engine_state.scan_count,
            "repair_count": engine_state.repair_count,
            "active_repairs": len([
                t for t in engine_state.repair_tasks.values() if t["status"] == "running"
            ]),
            "total_repairs": len(engine_state.repair_tasks),
            "llm_provider": engine_state.config.get("llm", {}).get("provider", "ollama"),
            "llm_model": engine_state.config.get("llm", {}).get("model", "glm-4.7-flash:latest"),
        }

        # 从 Mnemosyne 获取数据库统计
        try:
            db_stats = engine_state.mnemosyne.get_statistics()
            stats["database"] = db_stats
        except Exception:
            stats["database"] = {"error": "statistics unavailable"}

        # 修复成功率
        if engine_state.repair_tasks:
            completed = [t for t in engine_state.repair_tasks.values() if t["status"] in ("success", "partial", "failed")]
            if completed:
                success_count = sum(1 for t in completed if t["status"] == "success")
                stats["repair_success_rate"] = round(success_count / len(completed), 2)
                stats["repairs_completed"] = len(completed)

        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 目标注册 API（核心差异化功能）
# ============================================================================

class TargetRegisterRequest(BaseModel):
    """目标注册请求"""
    name: str = Field(..., description="Target display name")
    path: str = Field(..., description="Absolute path to monitor")
    scan_interval: int = Field(60, description="Scan interval in seconds", ge=10)
    health_threshold: float = Field(0.7, description="Health threshold to trigger repair", ge=0.0, le=1.0)
    auto_repair: bool = Field(True, description="Auto-repair when health drops below threshold")
    tags: List[str] = Field(default_factory=list, description="Custom tags for categorization")


class TargetInfo(BaseModel):
    """目标信息"""
    target_id: str
    name: str
    path: str
    scan_interval: int
    health_threshold: float
    auto_repair: bool
    tags: List[str]
    created_at: str
    last_scan: Optional[str] = None
    last_health: Optional[float] = None
    status: str = "active"


# ═══════════════════════════════════════════════════════════════════════════
# Daemon Monitor — 持续监控循环
# ═══════════════════════════════════════════════════════════════════════════

async def daemon_monitor_loop():
    """
    后台持续监控循环。
    
    每个 tick：
    1. 遍历所有 active targets
    2. 对每个 target 执行 Soma 健康扫描
    3. 记录健康度趋势
    4. 如果健康度低于阈值且 auto_repair=True，自动触发自愈链路
    5. 广播日志到 WebSocket
    """
    from src.agents.soma_dev import SomaDev
    from src.agents.mnemosyne_dev import Event

    await broadcaster.broadcast(json.dumps({
        "level": "INFO", "source": "daemon",
        "message": "Daemon monitor loop started",
        "timestamp": datetime.now().isoformat()
    }))

    while engine_state.daemon_running:
        try:
            engine_state.daemon_tick_count += 1
            tick_id = engine_state.daemon_tick_count
            engine_state.daemon_last_tick = datetime.now().isoformat()

            active_targets = {
                k: v for k, v in _targets_store.items()
                if v.get("status") == "active"
            }

            if not active_targets:
                await asyncio.sleep(engine_state.daemon_interval)
                continue

            await broadcaster.broadcast(json.dumps({
                "level": "INFO", "source": "daemon",
                "message": f"Tick #{tick_id}: scanning {len(active_targets)} target(s)",
                "timestamp": datetime.now().isoformat()
            }))

            for target_id, target in active_targets.items():
                if not engine_state.daemon_running:
                    break

                target_path = target["path"]
                threshold = target.get("health_threshold", 0.7)
                auto_repair = target.get("auto_repair", False)

                # 检查是否需要扫描（基于 scan_interval）
                last_scan = target.get("last_scan")
                scan_interval = target.get("scan_interval", 60)
                if last_scan:
                    try:
                        elapsed = (datetime.now() - datetime.fromisoformat(last_scan)).total_seconds()
                        if elapsed < scan_interval:
                            continue  # 还没到扫描时间
                    except Exception:
                        pass

                # Soma 扫描
                try:
                    scanner = SomaDev(project_path=target_path)
                    report = scanner.scan_codebase()
                    health_score = report["health_score"]
                    health_status = report.get("health_status", "unknown")

                    # 更新 target 状态
                    target["last_scan"] = datetime.now().isoformat()
                    target["last_health"] = health_score

                    # 记录健康度趋势
                    if target_id not in engine_state._health_history:
                        engine_state._health_history[target_id] = []

                    history_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "health_score": health_score,
                        "health_status": health_status,
                        "tick": tick_id,
                    }
                    engine_state._health_history[target_id].append(history_entry)
                    if len(engine_state._health_history[target_id]) > engine_state._max_history:
                        engine_state._health_history[target_id] = \
                            engine_state._health_history[target_id][-engine_state._max_history:]

                    engine_state.scan_count += 1

                    # 计算趋势（对比最近 5 次扫描）
                    trend = "stable"
                    history = engine_state._health_history[target_id]
                    if len(history) >= 3:
                        recent = [h["health_score"] for h in history[-5:]]
                        diff = recent[-1] - recent[0]
                        if diff > 0.05:
                            trend = "improving"
                        elif diff < -0.05:
                            trend = "degrading"

                    await broadcaster.broadcast(json.dumps({
                        "level": "INFO" if health_score >= threshold else "WARNING",
                        "source": "soma",
                        "message": (
                            f"[{target['name']}] Health: {health_score:.2f} "
                            f"({health_status}) trend={trend}"
                        ),
                        "data": {
                            "target_id": target_id,
                            "target_name": target["name"],
                            "health_score": health_score,
                            "health_status": health_status,
                            "trend": trend,
                            "threshold": threshold,
                        },
                        "timestamp": datetime.now().isoformat()
                    }))

                    # 记录到 Mnemosyne
                    try:
                        if engine_state._mnemosyne:
                            event = Event(
                                event_id=f"DAEMON-{tick_id}-{target_id[:8]}",
                                timestamp=datetime.now().isoformat() + "Z",
                                agent="Soma-Dev",
                                event_type="TICK",
                                payload={
                                    "target_id": target_id,
                                    "target_name": target["name"],
                                    "health_score": health_score,
                                    "health_status": health_status,
                                    "trend": trend,
                                    "tick": tick_id,
                                }
                            )
                            engine_state._mnemosyne.log_event(event)
                    except Exception:
                        pass

                    # 健康度低于阈值 → 触发自愈
                    if health_score < threshold and auto_repair:
                        await broadcaster.broadcast(json.dumps({
                            "level": "ERROR", "source": "daemon",
                            "message": (
                                f"[{target['name']}] Health {health_score:.2f} < "
                                f"threshold {threshold}! Triggering auto-repair..."
                            ),
                            "data": {
                                "target_id": target_id,
                                "target_name": target["name"],
                                "health_score": health_score,
                                "threshold": threshold,
                            },
                            "timestamp": datetime.now().isoformat()
                        }))

                        # 异步触发自愈
                        repair_task_id = f"AUTO-{tick_id}-{target_id[:8]}"
                        engine_state.repair_tasks[repair_task_id] = {
                            "task_id": repair_task_id,
                            "target_id": target_id,
                            "target_name": target["name"],
                            "status": "running",
                            "trigger": "daemon_auto",
                            "health_score": health_score,
                            "created_at": datetime.now().isoformat(),
                            "result": None,
                        }

                        # 后台执行自愈（不阻塞扫描循环）
                        asyncio.create_task(
                            _daemon_auto_repair(repair_task_id, target_id, target, report),
                            name=f"repair-{repair_task_id}"
                        )

                except Exception as e:
                    logger.error(f"Daemon scan failed for {target['name']}: {e}")
                    await broadcaster.broadcast(json.dumps({
                        "level": "ERROR", "source": "daemon",
                        "message": f"[{target['name']}] Scan error: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }))

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Daemon tick error: {e}")
            import traceback
            traceback.print_exc()

        # 等待下一个 tick
        try:
            await asyncio.wait_for(
                asyncio.Event().wait(),
                timeout=engine_state.daemon_interval
            )
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            break


async def _daemon_auto_repair(
    task_id: str,
    target_id: str,
    target: dict,
    soma_report: dict
):
    """Daemon 触发的自动自愈流程"""
    from src.protocol.oacp import SignalMessage, DamageType, Priority
    from src.agents.message_bus import MessageBus
    from src.agents.mnemosyne_dev import Event

    try:
        health_score = soma_report["health_score"]

        # 1. 创建 SIGNAL
        signal = SignalMessage.create(
            damage_type=DamageType.CODE_DECAY,
            severity=Priority.P0 if health_score < 0.5 else Priority.P1,
            location=f"target:{target['name']}",
            symptoms=[f"Health score {health_score:.2f}"],
            health_score=health_score,
        )
        signal.payload["soma_report"] = soma_report
        signal.payload["issues"] = soma_report.get("issues", [])
        signal.payload["target_id"] = target_id
        signal.payload["target_name"] = target["name"]

        await broadcaster.broadcast(json.dumps({
            "level": "INFO", "source": "daemon",
            "message": f"[{target['name']}] SIGNAL sent to Plasticus",
            "timestamp": datetime.now().isoformat()
        }))

        # 2. 启动消息总线执行自愈链路
        bus = MessageBus()
        bus.register("Plasticus-Dev", _make_plasticus_handler(task_id, target))
        bus.register("Effector-Dev", _make_effector_handler(task_id, target))
        bus.register("Mnemosyne-Dev", _make_mnemosyne_handler(task_id, target))
        await bus.start()

        await bus.send(signal)

        # 等待总线处理完成（最多 120 秒）
        for _ in range(120):
            pending = sum(q.qsize() for q in bus._mailboxes.values())
            if pending == 0:
                await asyncio.sleep(1)
                pending = sum(q.qsize() for q in bus._mailboxes.values())
                if pending == 0:
                    break
            await asyncio.sleep(1)

        await bus.stop()

        # 3. 扫描修复后健康度
        from src.agents.soma_dev import SomaDev
        scanner = SomaDev(project_path=target["path"])
        new_report = scanner.scan_codebase()
        new_health = new_report["health_score"]

        status = "success" if new_health >= target.get("health_threshold", 0.7) else "partial"
        engine_state.repair_count += 1

        engine_state.repair_tasks[task_id].update({
            "status": status,
            "health_after": new_health,
            "health_before": health_score,
            "completed_at": datetime.now().isoformat(),
            "result": {
                "status": status,
                "health_before": health_score,
                "health_after": new_health,
                "improvement": new_health - health_score,
            }
        })

        await broadcaster.broadcast(json.dumps({
            "level": "INFO" if status == "success" else "WARNING",
            "source": "daemon",
            "message": (
                f"[{target['name']}] Auto-repair {status}: "
                f"{health_score:.2f} → {new_health:.2f}"
            ),
            "data": {
                "task_id": task_id,
                "target_name": target["name"],
                "status": status,
                "health_before": health_score,
                "health_after": new_health,
            },
            "timestamp": datetime.now().isoformat()
        }))

    except Exception as e:
        logger.error(f"Auto-repair failed for {task_id}: {e}")
        engine_state.repair_tasks[task_id].update({
            "status": "failed",
            "completed_at": datetime.now().isoformat(),
            "result": {"error": str(e)}
        })
        await broadcaster.broadcast(json.dumps({
            "level": "ERROR", "source": "daemon",
            "message": f"[{target['name']}] Auto-repair failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }))


def _make_plasticus_handler(task_id, target):
    """创建 Plasticus 信号处理器（闭包）"""
    async def handler(message):
        try:
            from src.protocol.oacp import BlueprintMessage
            payload = message.payload

            plans = engine_state.plasticus.generate_plans(
                damage_type=payload.get("damage_type", "CODE_DECAY"),
                location=payload.get("location", "unknown"),
                symptoms=payload.get("symptoms", []),
                health_score=payload.get("health_score", 0.0),
                use_llm=True,
                use_multi_sample=False,
            )

            if not plans:
                await broadcaster.broadcast(json.dumps({
                    "level": "WARNING", "source": "daemon",
                    "message": f"[{target['name']}] No repair plans generated",
                    "timestamp": datetime.now().isoformat()
                }))
                return None

            best = engine_state.plasticus.evaluate_plans(plans)
            blueprint = BlueprintMessage.create(
                plan_id=task_id,
                strategy=best.name,
                steps=[
                    {
                        "number": i + 1,
                        "name": s.get("name", s.get("description", f"Step {i+1}")),
                        "description": s.get("description", ""),
                        "action": s.get("description", f"Step {i+1}"),
                        "type": s.get("type", "generic"),
                        "file_path": s.get("file_path"),
                        "content": s.get("content"),
                    }
                    for i, s in enumerate(best.steps)
                ],
                estimated_downtime=f"{best.downtime_seconds}s",
                success_rate_prediction=best.historical_success_rate,
                rollback_plan="Revert changes",
            )

            await broadcaster.broadcast(json.dumps({
                "level": "INFO", "source": "daemon",
                "message": (
                    f"[{target['name']}] Blueprint generated: "
                    f"{best.name} ({len(best.steps)} steps, "
                    f"success rate {best.historical_success_rate*100:.0f}%)"
                ),
                "timestamp": datetime.now().isoformat()
            }))

            return blueprint
        except Exception as e:
            await broadcaster.broadcast(json.dumps({
                "level": "ERROR", "source": "daemon",
                "message": f"[{target['name']}] Plasticus error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }))
            return None
    return handler


def _make_effector_handler(task_id, target):
    """创建 Effector 蓝图处理器（闭包）"""
    async def handler(message):
        try:
            from src.protocol.oacp import ExecutionReportMessage

            os.environ["EFFECTOR_AUTO_APPROVE"] = "true"
            report = engine_state.effector.execute_blueprint(message)

            await broadcaster.broadcast(json.dumps({
                "level": "INFO", "source": "daemon",
                "message": (
                    f"[{target['name']}] Effector executed: "
                    f"{report.payload.get('status', 'unknown')}"
                ),
                "timestamp": datetime.now().isoformat()
            }))

            return report
        except Exception as e:
            await broadcaster.broadcast(json.dumps({
                "level": "ERROR", "source": "daemon",
                "message": f"[{target['name']}] Effector error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }))
            return ExecutionReportMessage.create(
                plan_id=task_id,
                status="failed",
                steps_completed=0,
                steps_total=0,
                errors=[str(e)],
            )
    return handler


def _make_mnemosyne_handler(task_id, target):
    """创建 Mnemosyne 报告处理器（闭包）"""
    async def handler(message):
        try:
            from src.agents.mnemosyne_dev import Event
            payload = message.payload

            event = Event(
                event_id=f"REPAIR-{task_id}",
                timestamp=datetime.now().isoformat() + "Z",
                agent="Effector-Dev",
                event_type="EXECUTION_REPORT",
                payload={
                    "task_id": task_id,
                    "target_id": target.get("target_id"),
                    "target_name": target.get("name"),
                    "status": payload.get("status"),
                    "steps_completed": payload.get("steps_completed"),
                    "steps_total": payload.get("steps_total"),
                    "errors": payload.get("errors", []),
                }
            )
            engine_state.mnemosyne.log_event(event)
        except Exception:
            pass
        return None
    return handler


# ═══════════════════════════════════════════════════════════════════════════
# Daemon Control API
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/daemon")
async def get_daemon_status():
    """获取 Daemon 监控状态"""
    return {
        "running": engine_state.daemon_running,
        "interval": engine_state.daemon_interval,
        "last_tick": engine_state.daemon_last_tick,
        "tick_count": engine_state.daemon_tick_count,
        "targets_monitored": sum(
            1 for t in _targets_store.values() if t.get("status") == "active"
        ),
        "health_history": {
            tid: {
                "current": hist[-1] if hist else None,
                "trend": _calc_trend(hist) if len(hist) >= 2 else "unknown",
                "count": len(hist),
            }
            for tid, hist in engine_state._health_history.items()
        },
    }


@app.post("/api/daemon/interval")
async def set_daemon_interval(interval: int = 60):
    """设置 Daemon 扫描间隔（秒）"""
    if interval < 10:
        raise HTTPException(status_code=400, detail="Interval must be >= 10 seconds")
    if interval > 3600:
        raise HTTPException(status_code=400, detail="Interval must be <= 3600 seconds")
    engine_state.daemon_interval = interval
    logger.info(f"Daemon interval changed to {interval}s")
    return {"status": "ok", "interval": interval}


def _calc_trend(history: List[Dict]) -> str:
    """计算健康度趋势"""
    if len(history) < 2:
        return "unknown"
    recent = [h["health_score"] for h in history[-5:]]
    diff = recent[-1] - recent[0]
    if diff > 0.05:
        return "improving"
    elif diff < -0.05:
        return "degrading"
    return "stable"


# 内存中的目标列表（产品化后应持久化到数据库）
_targets_store: Dict[str, dict] = {}


@app.post("/api/targets", response_model=TargetInfo, status_code=201)
async def register_target(req: TargetRegisterRequest):
    """注册守护目标

    OpenNewt 的核心能力：注册一个代码库/服务，引擎会持续监控并在需要时自动修复。
    """
    import hashlib
    target_id = hashlib.sha256(f"{req.path}:{req.name}".encode()).hexdigest()[:12]

    if target_id in _targets_store:
        raise HTTPException(status_code=409, detail=f"Target {target_id} already exists")

    target = {
        "target_id": target_id,
        "name": req.name,
        "path": str(req.path),
        "scan_interval": req.scan_interval,
        "health_threshold": req.health_threshold,
        "auto_repair": req.auto_repair,
        "tags": req.tags,
        "created_at": datetime.now().isoformat(),
        "last_scan": None,
        "last_health": None,
        "status": "active",
    }

    _targets_store[target_id] = target
    logger.info(f"Target registered: {req.name} ({req.path})")
    return target


@app.get("/api/targets")
async def list_targets():
    """列出所有注册的守护目标"""
    return {
        "targets": list(_targets_store.values()),
        "total": len(_targets_store),
    }


@app.get("/api/targets/{target_id}")
async def get_target(target_id: str):
    """获取单个目标详情"""
    target = _targets_store.get(target_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"Target {target_id} not found")
    return target


@app.delete("/api/targets/{target_id}")
async def delete_target(target_id: str):
    """删除守护目标"""
    if target_id not in _targets_store:
        raise HTTPException(status_code=404, detail=f"Target {target_id} not found")
    removed = _targets_store.pop(target_id)
    logger.info(f"Target removed: {removed['name']}")
    return {"status": "ok", "removed": removed["name"]}


@app.post("/api/targets/{target_id}/scan")
async def scan_target(target_id: str):
    """手动触发目标扫描"""
    target = _targets_store.get(target_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"Target {target_id} not found")

    try:
        from src.agents.soma_dev import SomaDev
        scanner = SomaDev(project_path=target["path"])
        report = scanner.scan_codebase()

        target["last_scan"] = datetime.now().isoformat()
        target["last_health"] = report["health_score"]

        return {
            "target_id": target_id,
            "name": target["name"],
            "health_score": report["health_score"],
            "health_status": report.get("health_status", "unknown"),
            "needs_repair": report["health_score"] < target["health_threshold"],
            "issues": report.get("issues", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")


# ============================================================================
# API Key 鉴权（可选，通过环境变量启用）
# ============================================================================

# 如果设置了 OPENNEWT_API_KEY 环境变量，则启用 API Key 鉴权
_API_KEY = os.getenv("OPENNEWT_API_KEY")


if _API_KEY:
    from fastapi.security import APIKeyHeader

    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    @app.middleware("http")
    async def api_key_middleware(request: Request, call_next):
        # 免鉴权路径
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)
        if request.url.path.startswith("/ws/"):
            return await call_next(request)

        # 检查 API Key
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != _API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key. Set X-API-Key header."},
            )

        return await call_next(request)

    logger.info("API Key authentication enabled (X-API-Key)")

else:
    logger.info("API Key authentication disabled (set OPENNEWT_API_KEY to enable)")
