"""Service 层辅助函数

提供数据转换和实例创建的辅助函数，减少重复代码。
"""

from typing import Dict, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from ..db.repo import (
        FeedMessageRepository,
        PatchCardRepository,
        PatchThreadRepository,
    )
    from .patch_card_service import PatchCardService
    from .thread_service import ThreadService


def extract_common_patch_card_fields(data: Any) -> Dict[str, Any]:
    """提取 PatchCard 的公共字段

    Args:
        data: PatchCard 或 PatchCardData 对象

    Returns:
        包含公共字段的字典
    """
    return {
        "message_id_header": data.message_id_header,
        "subsystem_name": data.subsystem_name,
        "platform_message_id": data.platform_message_id,
        "platform_channel_id": data.platform_channel_id,
        "subject": data.subject,
        "author": data.author,
        "url": data.url,
        "expires_at": data.expires_at,
        "is_series_patch": data.is_series_patch,
        "series_message_id": data.series_message_id,
        "patch_version": data.patch_version,
        "patch_index": data.patch_index,
        "patch_total": data.patch_total,
        "has_thread": getattr(data, "has_thread", False),
        "to_cc_list": getattr(data, "to_cc_list", None),
        # 注意：is_cover_letter 不在数据库中存储，只在 Service 层使用
    }


def extract_common_feed_message_fields(data: Any) -> Dict[str, Any]:
    """提取 FeedMessage 的公共字段

    Args:
        data: FeedMessage 或 FeedMessageData 对象

    Returns:
        包含公共字段的字典
    """
    return {
        "subsystem_name": data.subsystem_name,
        "message_id_header": data.message_id_header,
        "subject": data.subject,
        "author": data.author,
        "author_email": data.author_email,
        "message_id": data.message_id,
        "in_reply_to_header": data.in_reply_to_header,
        "content": data.content,
        "url": data.url,
        "received_at": data.received_at,
        "is_patch": data.is_patch,
        "is_reply": data.is_reply,
        "is_series_patch": data.is_series_patch,
        "patch_version": data.patch_version,
        "patch_index": data.patch_index,
        "patch_total": data.patch_total,
        "is_cover_letter": data.is_cover_letter,
        "series_message_id": data.series_message_id,
    }


def create_repositories_and_services(
    session: "AsyncSession",
) -> Tuple[
    "PatchCardRepository",
    "FeedMessageRepository",
    "PatchThreadRepository",
    "PatchCardService",
    "ThreadService",
]:
    """创建 Repository 和 Service 实例（辅助函数以减少重复代码）

    Args:
        session: 数据库会话

    Returns:
        (patch_card_repo, feed_message_repo, patch_thread_repo, patch_card_service, thread_service)
    """
    from ..db.repo import (
        FeedMessageRepository,
        PatchCardRepository,
        PatchThreadRepository,
    )
    from .patch_card_service import PatchCardService
    from .thread_service import ThreadService

    patch_card_repo = PatchCardRepository(session)
    feed_message_repo = FeedMessageRepository(session)
    patch_thread_repo = PatchThreadRepository(session)

    patch_card_service = PatchCardService(patch_card_repo, feed_message_repo)
    thread_service = ThreadService(
        patch_thread_repo, patch_card_repo, feed_message_repo
    )

    return (
        patch_card_repo,
        feed_message_repo,
        patch_thread_repo,
        patch_card_service,
        thread_service,
    )


def build_single_patch_info(patch_card) -> "SeriesPatchInfo":
    """构建单 PATCH 的 SeriesPatchInfo 对象（辅助函数以减少重复代码）

    Args:
        patch_card: PatchCard 对象

    Returns:
        SeriesPatchInfo 对象
    """
    from .types import SeriesPatchInfo

    return SeriesPatchInfo(
        subject=patch_card.subject,
        patch_index=1,
        patch_total=1,
        message_id=patch_card.message_id_header,
        url=patch_card.url or "",
    )
