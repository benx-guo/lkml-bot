"""Discord 客户端模块

提供 Discord REST API 的底层封装。
"""

from .discord_client import (
    send_discord_embed,
    create_discord_thread,
    check_thread_exists,
    get_existing_thread_id,
    send_message_to_thread,
    update_message_in_thread,
    send_thread_update_notification,
)
from .discord_params import PatchCardParams
from .exceptions import (
    DiscordAPIError,
    DiscordHTTPError,
    FormatPatchError,
    ThreadPoolFullError,
)

__all__ = [
    # Discord API 函数
    "send_discord_embed",
    "create_discord_thread",
    "check_thread_exists",
    "get_existing_thread_id",
    "send_message_to_thread",
    "update_message_in_thread",
    "send_thread_update_notification",
    # 参数类型
    "PatchCardParams",
    # 异常
    "DiscordAPIError",
    "DiscordHTTPError",
    "FormatPatchError",
    "ThreadPoolFullError",
]
