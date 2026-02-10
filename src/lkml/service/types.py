"""Service 层数据类型定义

定义 service 层使用的数据结构，供上层（plugins）使用。
避免上层直接依赖 db 和 repo 层的数据结构。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict


# 类型别名：在运行时导入实际模型，供 plugins 层使用
# 这样 plugins 层就不需要直接依赖 lkml.db.models


@dataclass
class SeriesPatchInfo:
    """系列 PATCH 信息（Service 层）

    表示系列 PATCH 中的一个子 PATCH 的信息
    """

    subject: str
    patch_index: int
    patch_total: int
    message_id: str
    url: str


@dataclass
class PatchCard:
    """PATCH 卡片数据（Service 层）"""

    message_id_header: str
    subsystem_name: str
    platform_message_id: str
    platform_channel_id: str
    subject: str
    author: str
    url: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_series_patch: bool = False
    series_message_id: Optional[str] = None
    patch_version: Optional[str] = None
    patch_index: Optional[int] = None
    patch_total: Optional[int] = None
    has_thread: bool = False  # 是否已建立 Thread
    is_cover_letter: bool = False  # 是否是 Cover Letter
    to_cc_list: Optional[List[str]] = (
        None  # To 和 CC 列表（从 root patch 抓取，合并去重）
    )

    # 渲染相关字段（供 Plugins 层使用）
    series_patches: Optional[List[SeriesPatchInfo]] = (
        None  # 系列 PATCH 列表（如果是系列）
    )
    matched_filters: Optional[List[str]] = (
        None  # 匹配的过滤规则名称列表（用于高亮显示）
    )


@dataclass
class FeedMessage:
    """Feed 消息数据（Service 层）"""

    subsystem_name: str
    message_id_header: str
    subject: str
    author: str
    author_email: str
    message_id: Optional[str] = None
    in_reply_to_header: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None
    received_at: Optional[datetime] = None
    is_patch: bool = False
    is_reply: bool = False
    is_series_patch: bool = False
    patch_version: Optional[str] = None
    patch_index: Optional[int] = None
    patch_total: Optional[int] = None
    is_cover_letter: bool = False
    series_message_id: Optional[str] = None
    matched_filters: Optional[List[str]] = (
        None  # 匹配的过滤规则名称列表（用于高亮显示）
    )


@dataclass
class PatchThread:
    """PATCH Thread 数据（Service 层）"""

    patch_card_message_id_header: str
    thread_id: str
    thread_name: str
    is_active: bool = True
    overview_message_id: Optional[str] = None
    sub_patch_messages: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


@dataclass
class ThreadNode:
    """Thread 层级树节点

    表示邮件讨论树中的一个节点
    """

    message: "FeedMessage"  # 消息内容
    children: List["ThreadNode"]  # 子节点列表
    node_type: str  # "cover_letter" | "sub_patch" | "reply"


@dataclass
class ThreadOverviewData:
    """Thread Overview 渲染数据（供 Plugins 层渲染使用）

    包含渲染 Thread Overview 所需的所有数据
    """

    patch_card: PatchCard  # PatchCard 信息（包含 series_patches）
    root: Optional["ThreadNode"] = None  # 完整层级树
