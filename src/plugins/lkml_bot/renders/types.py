"""渲染结果数据类型

定义各平台渲染器返回的数据结构，用于传递给客户端发送。
"""

from dataclasses import dataclass
from typing import Dict, Optional

from ..client.discord_params import PatchCardParams


@dataclass
class DiscordRenderedPatchCard:
    """Discord Patch Card 渲染结果"""

    params: PatchCardParams
    description: str
    embed_color: Optional[int] = None
    title: Optional[str] = None


@dataclass
class DiscordRenderedThreadMessage:
    """Discord Thread 消息渲染结果"""

    content: str
    embed: Optional[Dict] = None


@dataclass
class DiscordRenderedThreadOverview:
    """Discord Thread Overview 渲染结果（包含多个子 PATCH 消息）"""

    messages: Dict[int, DiscordRenderedThreadMessage]  # {patch_index: message} 映射


@dataclass
class FeishuRenderedPatchCard:
    """Feishu Patch Card 渲染结果"""

    card: Dict  # Feishu 卡片 JSON


@dataclass
class FeishuRenderedThreadNotification:
    """Feishu Thread 通知卡片渲染结果"""

    card: Dict  # Feishu 卡片 JSON


@dataclass
class DiscordRenderedReplyNotification:
    """Discord Reply 通知渲染结果"""

    title: str
    description: str
    url: Optional[str] = None
    embed_color: int = 0x5865F2  # 默认蓝色


@dataclass
class FeishuRenderedReplyNotification:
    """Feishu Reply 通知渲染结果"""

    card: Dict  # Feishu 卡片 JSON
