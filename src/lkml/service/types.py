"""Service 层数据类型定义

定义 service 层使用的数据结构，供上层（plugins）使用。
避免上层直接依赖 db 和 repo 层的数据结构。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

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
    sub_patch_messages: Optional[Dict[int, str]] = None  # {patch_index: message_id}
    overview_message_id: Optional[str] = None
    created_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


@dataclass
class ReplyMapEntry:
    """回复映射条目

    表示回复层级结构中的一个节点
    """

    reply: Any  # FeedMessage 对象
    children: List[str]  # 子回复的 message_id_header 列表


@dataclass
class ReplyHierarchy:
    """回复层级结构

    表示 PATCH 的所有回复的层级关系
    """

    reply_map: Dict[str, ReplyMapEntry]  # {message_id: ReplyMapEntry}
    root_replies: List[str]  # 根回复的 message_id_header 列表


@dataclass
class SubPatchOverviewData:
    """单个子 PATCH 的 Overview 数据（供 Plugins 层渲染使用）

    包含渲染单个子 PATCH 所需的完整数据：
    - PATCH 信息
    - 该 PATCH 的所有回复（包括直接和间接回复）
    - 回复层级结构（基于该 PATCH 的回复构建）
    """

    patch: SeriesPatchInfo  # 子 PATCH 信息
    replies: List[FeedMessage]  # 该 PATCH 的所有回复列表
    reply_hierarchy: ReplyHierarchy  # 该 PATCH 的回复层级结构


@dataclass
class ThreadOverviewData:
    """Thread Overview 渲染数据（供 Plugins 层渲染使用）

    包含渲染 Thread Overview 所需的所有数据
    """

    patch_card: PatchCard  # PatchCard 信息（包含 series_patches）
    replies: List[FeedMessage]  # 所有回复列表
    reply_hierarchy: ReplyHierarchy  # 回复层级结构
    sub_patch_overviews: Optional[List[SubPatchOverviewData]] = (
        None  # 每个子 PATCH 的独立 overview 数据（Series Patch 时使用）
    )
