"""
WebSocket Adapter — WebSocket 服务器适配器
支持浏览器和自定义 WebSocket 客户端连接
"""

import asyncio
import json
import uuid
from typing import Optional

from .base import PlatformAdapter, AdapterConfig, Message, Event, EventType


class WebSocketAdapter(PlatformAdapter):
    """
    WebSocket 服务器适配器

    配置:
    - server_host: 绑定地址，默认 0.0.0.0
    - server_port: 绑定端口，默认 8080
    - enabled: True
    """

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self._host = config.server_host
        self._port = config.server_port
        self._server: Optional[asyncio.Server] = None
        self._clients: dict[str, asyncio.StreamReader] = {}
        self._writers: dict[str, asyncio.StreamWriter] = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        print(f"[WebSocket] Server started on {self._host}:{self._port}")

    async def stop(self):
        self._running = False
        for writer in self._writers.values():
            writer.close()
            await writer.wait_closed()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        client_id = str(uuid.uuid4())[:8]
        self._clients[client_id] = reader
        self._writers[client_id] = writer
        addr = writer.get_extra_info("peername")
        print(f"[WebSocket] Client connected: {client_id} ({addr})")

        try:
            while self._running:
                try:
                    data = await asyncio.wait_for(reader.read(4096), timeout=60)
                    if not data:
                        break
                    text = data.decode("utf-8")
                    for line in text.split("\n"):
                        if not line.strip():
                            continue
                        try:
                            msg_data = json.loads(line)
                            event = Event(
                                type=EventType.MESSAGE,
                                data=Message(
                                    platform="websocket",
                                    event_type=EventType.MESSAGE,
                                    channel_id=client_id,
                                    user_id=msg_data.get("user_id", client_id),
                                    username=msg_data.get("username", f"user_{client_id}"),
                                    content=msg_data.get("content", ""),
                                    raw=msg_data,
                                ),
                                raw=msg_data,
                            )
                            await self.emit(event)
                        except json.JSONDecodeError:
                            pass
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            print(f"[WebSocket] Client error: {e}")
        finally:
            del self._clients[client_id]
            del self._writers[client_id]
            writer.close()
            await writer.wait_closed()
            print(f"[WebSocket] Client disconnected: {client_id}")

    async def send_message(self, channel_id: str, text: str, **kwargs) -> bool:
        """发送消息到指定客户端"""
        writer = self._writers.get(channel_id)
        if not writer:
            return False
        try:
            msg = json.dumps({"content": text, "type": "message"}, ensure_ascii=False)
            writer.write(f"{msg}\n".encode("utf-8"))
            await writer.drain()
            return True
        except Exception as e:
            print(f"[WebSocket] Send error: {e}")
            return False

    async def broadcast(self, text: str):
        """广播消息到所有客户端"""
        msg = json.dumps({"content": text, "type": "broadcast"}, ensure_ascii=False)
        for writer in self._writers.values():
            try:
                writer.write(f"{msg}\n".encode("utf-8"))
            except Exception:
                pass
        for writer in self._writers.values():
            try:
                await writer.drain()
            except Exception:
                pass
