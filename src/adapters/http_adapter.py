"""
HTTP Adapter — HTTP Webhook + REST API 适配器
支持 POST webhook 接收和 REST API 发送
"""

import asyncio
import json
from typing import Optional

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    web = None

from .base import PlatformAdapter, AdapterConfig, Message, Event, EventType


class HTTPAdapter(PlatformAdapter):
    """
    HTTP 适配器（Webhook 接收 + REST API 发送）

    配置:
    - server_host: 绑定地址，默认 0.0.0.0
    - server_port: 绑定端口，默认 8080
    - webhook_path: Webhook 接收路径，默认 /webhook
    - api_key: 可选，API 密钥验证
    """

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self._host = config.server_host
        self._port = config.server_port
        self._webhook_path = config.extra.get("webhook_path", "/webhook")
        self._api_key = config.api_key
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

    async def start(self):
        if self._running:
            return
        self._app = web.Application()
        self._app.router.add_post(self._webhook_path, self._webhook_handler)
        self._app.router.add_get("/health", self._health_handler)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        print(f"[HTTP] Server started on {self._host}:{self._port}")
        self._running = True

    async def stop(self):
        self._running = False
        if self._runner:
            await self._runner.cleanup()

    async def _webhook_handler(self, request: web.Request) -> web.Response:
        """处理 POST webhook"""
        if self._api_key:
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != self._api_key:
                return web.Response(status=401, text="Unauthorized")

        try:
            data = await request.json()
        except Exception:
            data = await request.post()

        raw = dict(data) if isinstance(data, dict) else {"raw": str(data)}
        event = Event(
            type=EventType.MESSAGE,
            data=Message(
                platform="http",
                event_type=EventType.MESSAGE,
                channel_id=raw.get("channel_id", "default"),
                user_id=raw.get("user_id", raw.get("from", "unknown")),
                username=raw.get("username", "http_user"),
                content=raw.get("content", raw.get("text", raw.get("message", ""))),
                raw=raw,
            ),
            raw=raw,
        )
        await self.emit(event)
        return web.Response(text="OK")

    async def _health_handler(self, request: web.Request) -> web.Response:
        return web.Response(text="OK")

    async def send_message(self, channel_id: str, text: str, **kwargs) -> bool:
        """
        通过 HTTP POST 发送消息到预设的 webhook_url
        channel_id 作为 webhook_url 模板参数
        """
        url = self.config.extra.get("webhook_template", "").format(channel_id=channel_id)
        if not url:
            url = self.config.webhook_url
        if not url:
            return False
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"content": text, "channel_id": channel_id}
                async with session.post(url, json=payload) as resp:
                    return resp.status < 400
        except Exception as e:
            print(f"[HTTP] Send error: {e}")
            return False
