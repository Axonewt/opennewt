"""
Axonewt Discord Adapter — Discord 消息网关
==========================================
"""

import asyncio
import json
from typing import Callable, Optional, Any
from dataclasses import dataclass


@dataclass
class DiscordMessage:
    """Discord 消息结构"""
    content: str
    author_id: str
    author_name: str
    channel_id: str
    guild_id: Optional[str] = None
    reply_to: Optional[str] = None


class DiscordAdapter:
    """
    Discord 平台适配器

    功能：
    - 接收 Discord 消息
    - 发送回复
    - 支持 slash commands
    - 支持消息线程
    """

    def __init__(self, token: str, intents: int = 0x200000):
        self.token = token
        self.intents = intents
        self.client = None
        self._handlers: list[Callable] = []
        self._running = False

    def on_message(self, handler: Callable[[DiscordMessage], Any]) -> None:
        """注册消息处理器"""
        self._handlers.append(handler)

    async def send_message(self, channel_id: str, content: str, reply_to: Optional[str] = None) -> dict:
        """发送消息"""
        # 实现使用 discord.py API
        payload = {"content": content, "nonce": str(asyncio.get_event_loop().time_ns())}
        if reply_to:
            payload["message_reference"] = {"message_id": reply_to}
        # 这里实际需要 discord.py HTTP 调用
        return {"channel_id": channel_id, "content": content}

    async def start(self) -> None:
        """启动 Discord bot"""
        import discord
        self._running = True
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)

        @client.event
        async def on_message(message):
            if message.author.bot:
                return
            msg = DiscordMessage(
                content=message.content,
                author_id=str(message.author.id),
                author_name=message.author.name,
                channel_id=str(message.channel.id),
                guild_id=str(message.guild.id) if message.guild else None,
            )
            for handler in self._handlers:
                await handler(msg)

        await client.start(self.token)

    async def stop(self) -> None:
        """停止 Discord bot"""
        self._running = False
        if self.client:
            await self.client.close()

    def is_running(self) -> bool:
        return self._running
