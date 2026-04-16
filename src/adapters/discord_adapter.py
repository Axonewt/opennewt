"""
Discord Adapter — Discord 机器人适配器
"""

import asyncio
import json
from typing import Optional

try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

from .base import PlatformAdapter, AdapterConfig, Message, Event, EventType


class DiscordAdapter(PlatformAdapter):
    """
    Discord 平台适配器

    需要配置:
    - bot_token: Discord Bot Token
    - enabled: True
    """

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self.client: Optional[discord.Client] = None
        self._token = config.bot_token
        self._intents = discord.Intents.default()
        self._intents.message_content = True

    async def start(self):
        if self._running:
            return
        self.client = discord.Client(intents=self._intents)

        @self.client.event
        async def on_message(msg: discord.Message):
            if msg.author.bot:
                return
            raw = {
                "channel_id": str(msg.channel.id),
                "user_id": str(msg.author.id),
                "username": msg.author.name,
                "content": msg.content,
            }
            event = Event(
                type=EventType.MESSAGE,
                data=Message.from_raw("discord", raw),
                raw=raw,
            )
            await self.emit(event)

        @self.client.event
        async def on_ready():
            print(f"[Discord] Bot connected as {self.client.user}")

        await self.client.start(self._token)
        self._running = True

    async def stop(self):
        self._running = False
        if self.client:
            await self.client.close()

    async def send_message(self, channel_id: str, text: str, **kwargs) -> bool:
        """通过 Discord API 发送消息"""
        if not self.client or not self.client.is_ready():
            return False
        try:
            channel = self.client.get_channel(int(channel_id))
            if channel:
                await channel.send(text)
                return True
        except Exception as e:
            print(f"[Discord] Send error: {e}")
        return False
