"""
Axonewt HTTP Adapter — HTTP Webhook/REST 消息网关
=================================================
"""

import asyncio
import json
from typing import Callable, Optional, Any, Dict
from dataclasses import dataclass
from datetime import datetime
from aiohttp import web


@dataclass
class HTTPRequest:
    """HTTP 请求结构"""
    method: str
    path: str
    headers: Dict[str, str]
    body: Optional[dict]
    query: Dict[str, str]
    client_ip: str


class HTTPAdapter:
    """
    HTTP 平台适配器

    功能：
    - REST API 端点
    - Webhook 接收
    - SSE（Server-Sent Events）流式响应
    - 路由管理
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.app = web.Application()
        self._routes: Dict[str, Callable] = {}
        self._running = False
        self._runner: Optional[web.AppRunner] = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        """设置默认路由"""

        async def health_handler(request):
            return web.json_response({"status": "ok", "service": "axonewt"})

        async def webhook_handler(request):
            body = await request.json() if request.can_read_body else {}
            req = HTTPRequest(
                method=request.method,
                path=request.path,
                headers=dict(request.headers),
                body=body,
                query=dict(request.query),
                client_ip=request.remote or "unknown"
            )
            handler = self._routes.get("webhook")
            if handler:
                result = await handler(req)
                return web.json_response(result)
            return web.json_response({"received": True})

        self.app.router.add_get("/health", health_handler)
        self.app.router.add_post("/webhook", webhook_handler)

    def route(self, path: str, method: str = "POST") -> Callable:
        """装饰器注册路由"""
        def decorator(func: Callable) -> Callable:
            key = f"{method}:{path}"
            self._routes[key] = func
            self.app.router.add_route(method, path, func)
            return func
        return decorator

    def on_webhook(self, handler: Callable[[HTTPRequest], Any]) -> None:
        """注册 Webhook 处理器"""
        self._routes["webhook"] = handler

    async def start(self) -> None:
        """启动 HTTP 服务器"""
        self._running = True
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        print(f"HTTP 服务器启动: http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """停止 HTTP 服务器"""
        self._running = False
        if self._runner:
            await self._runner.cleanup()

    async def send_sse(self, request: web.Request, generator: Callable) -> web.StreamResponse:
        """SSE 流式响应"""
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}
        )
        await response.prepare(request)
        try:
            async for chunk in generator():
                await response.write(f"data: {json.dumps(chunk)}\n\n")
        finally:
            await response.write_eof()
        return response
