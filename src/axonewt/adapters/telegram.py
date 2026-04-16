"""
Axonewt Telegram Adapter — Telegram 消息网关
=============================================
"""

import asyncio
import json
from typing import Callable, Optional, Any, Dict
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TelegramUpdate:
    """Telegram 更新结构"""
    update_id: int
    chat_id: int
    user_id: int
    text: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    reply_to_message_id: Optional[int] = None


class TelegramAdapter:
    """
    Telegram 平台适配器

    功能：
    - Webhook 或 Long Polling 接收消息
    - 发送文本、图片、按钮
    - 支持命令（/start, /help 等）
    - 群组和私聊支持
    """

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        self._handlers: Dict[str, Callable] = {}
        self._running = False

    def on_message(self, handler: Callable[[TelegramUpdate], Any]) -> None:
        """注册消息处理器"""
        self._handlers["message"] = handler

    def on_command(self, command: str, handler: Callable[[TelegramUpdate], Any]) -> None:
        """注册命令处理器"""
        self._handlers[f"command_{command}"] = handler

    async def _call_api(self, method: str, **kwargs) -> dict:
        """调用 Telegram Bot API"""
        import aiohttp
        url = f"{self.api_base}/{method}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=kwargs) as resp:
                return await resp.json()

    async def send_message(self, chat_id: int, text: str, reply_to: Optional[int] = None,
                          parse_mode: str = "Markdown") -> dict:
        """发送消息"""
        return await self._call_api(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to,
            parse_mode=parse_mode
        )

    async def send_photo(self, chat_id: int, photo: str, caption: Optional[str] = None) -> dict:
        """发送图片"""
        return await self._call_api(
            "sendPhoto",
            chat_id=chat_id,
            photo=photo,
            caption=caption
        )

    async def set_webhook(self, webhook_url: str) -> dict:
        """设置 Webhook"""
        return await self._call_api("setWebhook", url=webhook_url)

    async def process_update(self, update: dict) -> Optional[Any]:
        """处理单个更新"""
        msg = update.get("message", {})
        if not msg:
            return None

        text = msg.get("text", "") or msg.get("caption", "")
        chat = msg.get("chat", {})
        user = msg.get("from", {})

        tg_update = TelegramUpdate(
            update_id=update["update_id"],
            chat_id=chat["id"],
            user_id=user.get("id", 0),
            text=text,
            username=user.get("username"),
            first_name=user.get("first_name"),
            reply_to_message_id=msg.get("reply_to_message", {}).get("message_id"),
        )

        # 命令处理
        if text.startswith("/") and " " not in text[1:]:
            cmd = text[1:].split("@")[0]
            handler = self._handlers.get(f"command_{cmd}")
            if handler:
                return await handler(tg_update)

        # 通用消息处理
        handler = self._handlers.get("message")
        if handler:
            return await handler(tg_update)
        return None

    async def long_poll(self, offset: int = 0, timeout: int = 30) -> None:
        """Long Polling 模式"""
        while self._running:
            try:
                result = await self._call_api("getUpdates", offset=offset + 1, timeout=timeout)
                if result.get("ok"):
                    for update in result.get("result", []):
                        await self.process_update(update)
                        offset = update["update_id"]
            except Exception:
                await asyncio.sleep(5)

    async def start(self) -> None:
        """启动 Telegram bot（Long Polling）"""
        self._running = True
        await self.long_poll()

    async def stop(self) -> None:
        """停止 Telegram bot"""
        self._running = False
