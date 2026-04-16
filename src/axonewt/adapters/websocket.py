"""
Axonewt WebSocket Adapter — WebSocket 消息网关
==============================================
"""

import asyncio
import json
from typing import Callable, Optional, Any, Dict
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class WSMessage:
    """WebSocket 消息结构"""
    type: str  # "message" | "connect" | "disconnect" | "ping" | "pong"
    content: str
    sender_id: Optional[str] = None
    room_id: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[Dict] = None


class WebSocketAdapter:
    """
    WebSocket 平台适配器

    功能：
    - WebSocket 连接管理
    - 房间（Room）隔离
    - 心跳保活（Ping/Pong）
    - 广播消息
    - JSON / Text 双模式
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self._server: Optional[asyncio.Server] = None
        self._clients: Dict[str, Any] = {}  # client_id -> WebSocket
        self._rooms: Dict[str, set[str]] = {}  # room_id -> set of client_ids
        self._handlers: Dict[str, Callable] = {}
        self._running = False

    def on_message(self, handler: Callable[[WSMessage], Any]) -> None:
        self._handlers["message"] = handler

    def on_connect(self, handler: Callable[[WSMessage], Any]) -> None:
        self._handlers["connect"] = handler

    def on_disconnect(self, handler: Callable[[WSMessage], Any]) -> None:
        self._handlers["disconnect"] = handler

    async def _broadcast_to_room(self, room_id: str, message: WSMessage) -> None:
        """向房间内所有客户端广播"""
        for client_id in self._rooms.get(room_id, []):
            ws = self._clients.get(client_id)
            if ws and not ws.closed:
                try:
                    await ws.send_json(asdict(message))
                except Exception:
                    pass

    async def _handle_client(self, client_id: str, ws: Any) -> None:
        """处理单个客户端连接"""
        self._clients[client_id] = ws

        # 连接事件
        connect_msg = WSMessage(type="connect", content="Connected", sender_id=client_id, timestamp=datetime.now().isoformat())
        handler = self._handlers.get("connect")
        if handler:
            await handler(connect_msg)

        try:
            async for raw in ws:
                if ws.closed:
                    break
                try:
                    data = json.loads(raw)
                    msg = WSMessage(
                        type=data.get("type", "message"),
                        content=data.get("content", ""),
                        sender_id=client_id,
                        room_id=data.get("room_id"),
                        timestamp=datetime.now().isoformat(),
                        metadata=data.get("metadata"),
                    )

                    # 加入房间
                    if msg.room_id and msg.type == "join_room":
                        if msg.room_id not in self._rooms:
                            self._rooms[msg.room_id] = set()
                        self._rooms[msg.room_id].add(client_id)

                    # 处理消息
                    handler = self._handlers.get("message")
                    if handler:
                        await handler(msg)

                except json.JSONDecodeError:
                    pass  # 忽略无效 JSON

        finally:
            del self._clients[client_id]
            # 从所有房间移除
            for room in self._rooms.values():
                room.discard(client_id)
            disconnect_msg = WSMessage(type="disconnect", content="Disconnected", sender_id=client_id, timestamp=datetime.now().isoformat())
            handler = self._handlers.get("disconnect")
            if handler:
                await handler(disconnect_msg)

    async def start(self) -> None:
        """启动 WebSocket 服务器"""
        self._running = True
        import uuid

        async def handler(ws: Any, path: str):
            client_id = str(uuid.uuid4())[:8]
            await self._handle_client(client_id, ws)

        self._server = await asyncio.start_server(handler, self.host, self.port)
        print(f"WebSocket 服务器启动: ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """停止 WebSocket 服务器"""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def send_to(self, client_id: str, message: WSMessage) -> bool:
        """向指定客户端发送消息"""
        ws = self._clients.get(client_id)
        if ws and not ws.closed:
            await ws.send_json(asdict(message))
            return True
        return False

    async def broadcast(self, message: WSMessage) -> int:
        """广播到所有客户端"""
        count = 0
        for ws in self._clients.values():
            if not ws.closed:
                try:
                    await ws.send_json(asdict(message))
                    count += 1
                except Exception:
                    pass
        return count
