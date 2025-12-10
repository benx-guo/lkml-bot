"""Discord 客户端参数类型

用于 discord_client.py 中的函数参数。
这些是临时参数类型，仅用于 Discord API 调用，不包含业务逻辑。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PatchCardParams:
    """PatchCard 参数（仅用于 Discord API 调用）"""

    subsystem: str
    message_id_header: str
    subject: str
    author: str
    received_at: datetime
    url: Optional[str] = None
    series_message_id: Optional[str] = None
    patch_version: Optional[str] = None
    patch_index: Optional[int] = None
    patch_total: Optional[int] = None
