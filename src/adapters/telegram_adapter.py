"""
Telegram Adapter — Telegram Bot 适配器
"""

import asyncio
from typing import Optional

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from .base import PlatformAdapter, AdapterConfig, Message, Event, EventType


class TelegramAdapter(PlatformAdapter):
    """
    Telegram 平台适配器

    需要配置:
    - bot_token: Telegram Bot Token (from @BotFather)
    - api_url: 可选，自定义 API URL (用于代理)
    """

    def __init__(self, config: AdapterConfig):
        super().__init__(config)
        self._token = config.bot_token
        self._api_url = config.extra.get("api_url", "https://api.telegram.org")
        self._offset = 0
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self):
        """长轮询 Telegram Updates"""
        base_url = f"{self._api_url}/bot{self._token}"
        while self._running:
            try:
                async with asyncio.timeout(30):
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        params = {"offset": self._offset, "timeout": 0}
                        async with session.get(
                            f"{base_url}/getUpdates", params=params
                        ) as resp:
                            data = await resp.json()
                            if data.get("ok"):
                                for update in data.get("result", []):
                                    self._offset = update["update_id"] + 1
                                    await self._handle_update(update)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[Telegram] Poll error: {e}")
                await asyncio.sleep(3)

    async def _handle_update(self, update: dict):
        """处理单个更新"""
        msg = update.get("message", update.get("edited_message", {}))
        if not msg:
            return
        raw = {
            "channel_id": str(msg["chat"]["id"]),
            "user_id": str(msg["from"]["id"]),
            "username": msg["from"].get("username", msg["from"].get("first_name", "unknown")),
            "content": msg.get("text", ""),
        }
        event = Event(
            type=EventType.MESSAGE,
            data=Message.from_raw("telegram", raw),
            raw=raw,
        )
        await self.emit(event)

    async def send_message(self, channel_id: str, text: str, **kwargs) -> bool:
        """通过 Telegram API 发送消息"""
        base_url = f"{self._api_url}/bot{self._token}"
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"chat_id": channel_id, "text": text}
                async with session.post(
                    f"{base_url}/sendMessage", json=payload
                ) as resp:
                    data = await resp.json()
                    return data.get("ok", False)
        except Exception as e:
            print(f"[Telegram] Send error: {e}")
            return False
