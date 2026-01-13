"""消息适配器模块"""

from .discord_adapter import DiscordAdapter
from .message_adapter import MessageAdapter

# 导出兼容性适配器（如果可用）
try:
    from .discord_compat_adapter import CompatibleDiscordAdapter

    __all__ = ["DiscordAdapter", "MessageAdapter", "CompatibleDiscordAdapter"]
except ImportError:
    __all__ = ["DiscordAdapter", "MessageAdapter"]
