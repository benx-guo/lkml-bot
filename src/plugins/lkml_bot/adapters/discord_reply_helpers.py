"""Discord REPLY 消息处理的辅助函数"""

from typing import Optional

from lkml.feed.patch_parser import parse_patch_subject
from lkml.db.models import PatchSubscription
from lkml.db.repo.email_message_repository import EMAIL_MESSAGE_REPO
from lkml.service.patch_subscription_service import patch_subscription_service
from lkml.service.thread_service import thread_service
from lkml.service.thread_content_service import thread_content_service


async def _find_actual_patch_in_reply_chain(
    session, in_reply_to: str, max_depth: int = 5
) -> Optional[PatchSubscription]:
    """在回复链中查找实际的 PATCH

    递归查找 in_reply_to 链，直到找到实际的 PATCH（不是 cover letter）

    Args:
        session: 数据库会话
        in_reply_to: 回复的 message_id
        max_depth: 最大递归深度

    Returns:
        PATCH 订阅对象，如果不存在则返回 None
    """
    return await thread_content_service.find_actual_patch_for_reply(
        session, in_reply_to, max_depth
    )


async def find_patch_subscription(
    session, in_reply_to: str, reply_subject: Optional[str] = None
) -> Optional[PatchSubscription]:
    """查找 PATCH 订阅

    Args:
        session: 数据库会话
        in_reply_to: 回复的 message_id
        reply_subject: REPLY 的主题（可选，用于查找对应的子 PATCH）

    Returns:
        PATCH 订阅对象，如果不存在则返回 None
    """
    # 1. 先尝试直接匹配 in_reply_to（REPLY 直接回复某个 PATCH）
    patch_sub = await patch_subscription_service.find_by_message_id(in_reply_to)

    # 2. 如果没找到直接匹配，尝试通过 series_message_id 查找
    #    （in_reply_to 可能是 Cover Letter 的 message_id）
    if not patch_sub:
        patch_sub = await patch_subscription_service.find_by_series_message_id(
            in_reply_to
        )

    # 3. 如果找到的是 cover letter (0/n)，尝试在回复链中查找实际的子 PATCH
    if patch_sub and patch_sub.patch_index == 0:
        # 方法1: 在回复链中查找实际的 PATCH
        actual_patch = await _find_actual_patch_in_reply_chain(session, in_reply_to)
        if actual_patch:
            return actual_patch

        # 方法2: 如果 REPLY 的 subject 中包含 patch index，尝试匹配
        if reply_subject:
            reply_patch_info = parse_patch_subject(reply_subject)
            if (
                reply_patch_info.is_patch
                and reply_patch_info.index is not None
                and reply_patch_info.index > 0
                and patch_sub.series_message_id
            ):
                # 获取系列中的所有 PATCH
                series_patches = await patch_subscription_service.get_series_patches(
                    patch_sub.series_message_id
                )
                # 查找匹配的子 PATCH
                for series_patch in series_patches:
                    if series_patch.patch_index == reply_patch_info.index:
                        return series_patch

    return patch_sub


async def find_thread_for_patch(
    patch_sub: PatchSubscription,
) -> Optional[object]:
    """查找 PATCH 对应的 Thread

    Args:
        patch_sub: PATCH 订阅对象

    Returns:
        Thread 对象，如果不存在则返回 None
    """
    if patch_sub.series_message_id:
        # 是系列 PATCH，查找系列中所有 PATCH 的 Thread
        return await _find_series_thread(patch_sub)

    # 单个 PATCH
    if not patch_sub.is_subscribed:
        return None

    return await thread_service.find_by_patch_subscription_id(patch_sub.id)


async def _find_series_thread(patch_sub: PatchSubscription) -> Optional[object]:
    """查找系列 PATCH 的 Thread

    Args:
        patch_sub: PATCH 订阅对象

    Returns:
        Thread 对象，如果不存在则返回 None
    """
    series_patches = await patch_subscription_service.get_series_patches(
        patch_sub.series_message_id
    )

    for series_patch in series_patches:
        if series_patch.is_subscribed:
            thread = await thread_service.find_by_patch_subscription_id(series_patch.id)
            if thread and thread.is_active:
                return thread

    return None


async def get_email_message(session, entry) -> Optional[object]:
    """获取 EmailMessage 对象

    Args:
        session: 数据库会话
        entry: Feed 条目

    Returns:
        EmailMessage 对象，如果不存在则返回 None
    """
    if not entry.metadata or not entry.metadata.message_id:
        return None

    return await EMAIL_MESSAGE_REPO.find_by_message_id_header(
        session, entry.metadata.message_id
    )
