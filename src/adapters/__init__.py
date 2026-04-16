# Platform Adapters — 消息网关抽象层
# 支持 Discord / Telegram / WebSocket / HTTP 四个平台

from .base import PlatformAdapter, AdapterConfig, Message, Event

# 懒加载各平台适配器，缺失依赖时优雅降级
_ADAPTERS = {}
try:
    from .discord_adapter import DiscordAdapter
    _ADAPTERS["DiscordAdapter"] = DiscordAdapter
except ImportError:
    DiscordAdapter = None

try:
    from .telegram_adapter import TelegramAdapter
    _ADAPTERS["TelegramAdapter"] = TelegramAdapter
except ImportError:
    TelegramAdapter = None

try:
    from .websocket_adapter import WebSocketAdapter
    _ADAPTERS["WebSocketAdapter"] = WebSocketAdapter
except ImportError:
    WebSocketAdapter = None

try:
    from .http_adapter import HTTPAdapter
    _ADAPTERS["HTTPAdapter"] = HTTPAdapter
except ImportError:
    HTTPAdapter = None

__all__ = [
    "PlatformAdapter",
    "AdapterConfig",
    "Message",
    "Event",
    "DiscordAdapter",
    "TelegramAdapter",
    "WebSocketAdapter",
    "HTTPAdapter",
]
