"""Thread 管理模块

提供 Discord Thread 的创建、池管理和限制处理功能。
"""

from .exceptions import (
    DiscordAPIError,
    DiscordHTTPError,
    FormatPatchError,
    ThreadPoolFullError,
)
from .manager import DiscordThreadManager
from .params import SeriesCardParams, SubscriptionCardParams

__all__ = [
    "DiscordThreadManager",
    "SeriesCardParams",
    "SubscriptionCardParams",
    "ThreadPoolFullError",
    "DiscordAPIError",
    "DiscordHTTPError",
    "FormatPatchError",
]
