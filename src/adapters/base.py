"""
Platform Adapter Base — 消息网关抽象层
定义所有平台适配器的公共接口和类型
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import asyncio


class EventType(Enum):
    MESSAGE = "message"
    COMMAND = "command"
    CALLBACK = "callback"
    EDIT = "edit"
    DELETE = "delete"


@dataclass
class AdapterConfig:
    """平台配置"""
    platform: str = ""
    enabled: bool = False
    api_key: str = ""
    api_secret: str = ""
    bot_token: str = ""
    webhook_url: str = ""
    server_host: str = "0.0.0.0"
    server_port: int = 8080
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.platform:
            self.platform = self.__class__.__name__.replace("Adapter", "").lower()


@dataclass
class Message:
    """统一消息格式"""
    platform: str
    event_type: EventType
    channel_id: str
    user_id: str
    username: str
    content: str
    raw: dict = field(default_factory=dict)
    timestamp: float = 0.0

    @classmethod
    def from_raw(cls, platform: str, raw: dict, event_type: EventType = EventType.MESSAGE) -> "Message":
        return cls(
            platform=platform,
            event_type=event_type,
            channel_id=raw.get("channel_id", raw.get("chat_id", "")),
            user_id=raw.get("user_id", raw.get("from_id", raw.get("from", {}).get("id", ""))),
            username=raw.get("username", raw.get("from", {}).get("username", raw.get("from", {}).get("first_name", "unknown"))),
            content=raw.get("content", raw.get("text", raw.get("caption", ""))),
            raw=raw,
        )


@dataclass
class Event:
    """统一事件格式"""
    type: EventType
    data: Any = None
    raw: dict = field(default_factory=dict)


class PlatformAdapter(ABC):
    """
    平台适配器抽象基类

    子类必须实现:
    - send_message(channel_id, text) -> bool
    - start() / stop()
    """

    def __init__(self, config: AdapterConfig):
        self.config = config
        self._running = False
        self._handlers: dict[EventType, list] = {e: [] for e in EventType}

    # ── 公共 API ────────────────────────────────────────────

    def on(self, event_type: EventType, handler):
        """注册事件处理器"""
        self._handlers[event_type].append(handler)

    async def emit(self, event: Event):
        """触发事件到所有处理器"""
        for handler in self._handlers.get(event.type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                print(f"[{self.config.platform}] Handler error: {e}")

    @abstractmethod
    async def send_message(self, channel_id: str, text: str, **kwargs) -> bool:
        """发送消息到指定渠道"""
        pass

    @abstractmethod
    async def start(self):
        """启动适配器"""
        self._running = True

    @abstractmethod
    async def stop(self):
        """停止适配器"""
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    # ── 工具方法 ────────────────────────────────────────────

    def _format_status(self, text: str) -> str:
        """格式化状态文本"""
        return f"**{text}**"

    def _format_code(self, text: str, lang: str = "") -> str:
        """格式化代码块"""
        return f"```{lang}\n{text}\n```"

    def _format_error(self, text: str) -> str:
        """格式化错误"""
        return f"❌ {text}"
