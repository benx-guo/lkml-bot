"""subscribe_patch 命令的辅助函数"""

from typing import Optional, Tuple

from nonebot.log import logger

from lkml.db.models import PatchSubscription
from lkml.service.patch_subscription_service import patch_subscription_service
from lkml.service.thread_service import thread_service

from ..thread import DiscordThreadManager
from ..thread.series_patches import process_and_send_patch


async def check_existing_thread(
    patch_sub: PatchSubscription, thread_manager: DiscordThreadManager
) -> Tuple[Optional[object], bool]:
    """检查现有 Thread 状态

    Args:
        patch_sub: PATCH 订阅对象
        thread_manager: Thread 管理器

    Returns:
        (existing_thread, is_recreate) 元组
    """
    # 先查找 Thread 记录（即使 is_subscribed 为 False，也可能有 thread 记录）
    existing_thread = await thread_service.find_by_patch_subscription_id(patch_sub.id)

    if not existing_thread:
        # 没有 thread 记录，返回 None
        return None, False

    if not existing_thread.is_active:
        # Thread 已被标记为 inactive（可能被删除），清理旧记录以便重建
        logger.info(
            f"Found inactive Thread for PATCH {patch_sub.message_id}, "
            f"will recreate. Old Thread ID: {existing_thread.thread_id}"
        )
        await thread_service.delete(existing_thread)
        # 标记为未订阅（通过设置 is_subscribed = False）
        patch_sub.is_subscribed = False
        # 注意：这里不调用 mark_as_subscribed，因为我们要标记为未订阅
        return None, False

    # 验证 Discord Thread 是否真的存在
    logger.info(
        f"Found existing thread record (ID: {existing_thread.thread_id}), "
        f"verifying if it exists in Discord..."
    )
    thread_exists = await thread_manager.check_thread_exists(existing_thread.thread_id)

    if thread_exists:
        # Thread 存在，返回 Thread 信息（即使 is_subscribed 为 False）
        logger.info(
            f"Thread {existing_thread.thread_id} exists in Discord for PATCH {patch_sub.message_id}"
        )
        return existing_thread, False

    # Thread 不存在，需要重建
    logger.warning(
        f"Thread {existing_thread.thread_id} marked as active but "
        f"doesn't exist in Discord, will recreate for PATCH {patch_sub.message_id}"
    )
    await thread_service.delete(existing_thread)
    patch_sub.is_subscribed = False
    return None, True


async def save_thread_and_mark_subscribed(
    thread_id: str,
    thread_name: str,
    patch_sub: PatchSubscription,
    thread_manager: DiscordThreadManager,
) -> None:
    """保存 Thread 信息并标记为已订阅

    Args:
        thread_id: Thread ID
        thread_name: Thread 名称
        patch_sub: PATCH 订阅对象
        thread_manager: Thread 管理器
    """
    # 检查 Thread 是否已存在于数据库中
    existing_thread_record = await thread_service.find_by_thread_id(thread_id)

    if existing_thread_record:
        # Thread 已存在，更新关联的 patch_subscription_id（如果需要）
        if existing_thread_record.patch_subscription_id != patch_sub.id:
            logger.info(
                f"Thread {thread_id} already exists, updating patch_subscription_id "
                f"from {existing_thread_record.patch_subscription_id} to {patch_sub.id}"
            )
            await thread_service.update_patch_subscription_id(thread_id, patch_sub.id)
    else:
        # 创建新的 Thread 记录
        await thread_service.create(patch_sub.id, thread_id, thread_name)

    # 如果是系列 PATCH，标记整个系列为已订阅
    if patch_sub.series_message_id:
        await _mark_series_subscribed(patch_sub, thread_id, thread_manager)
    else:
        # 单个 PATCH，标记为已订阅并发送到 Thread
        await patch_subscription_service.mark_as_subscribed(patch_sub)
        logger.info(
            f"Marked single PATCH as subscribed: {patch_sub.message_id}, "
            f"is_subscribed={patch_sub.is_subscribed}"
        )
        # 发送单个 PATCH 到 Thread
        try:
            async with thread_manager.database.get_db_session() as session:
                await process_and_send_patch(
                    session,
                    thread_id,
                    patch_sub,
                    thread_manager.send_message_to_thread,
                )
        except Exception as e:
            logger.error(
                f"Failed to send single PATCH to thread: {e}",
                exc_info=True,
            )
            raise


async def _mark_series_subscribed(
    patch_sub: PatchSubscription,
    thread_id: str,
    thread_manager: DiscordThreadManager,
) -> None:
    """标记系列 PATCH 为已订阅

    Args:
        patch_sub: PATCH 订阅对象
        thread_id: Thread ID
        thread_manager: Thread 管理器
    """
    # 获取该系列的所有 PATCH
    series_patches = await patch_subscription_service.get_series_patches(
        patch_sub.series_message_id
    )

    # 标记所有 PATCH 为已订阅，并关联到同一个 Thread
    for patch in series_patches:
        await patch_subscription_service.mark_as_subscribed(patch)

    logger.info(f"Marked {len(series_patches)} patches in series as subscribed")

    # 发送系列的所有 PATCH 到 Thread
    await thread_manager.send_series_patches_to_thread(
        thread_id, series_patches, patch_sub.subsystem_name
    )


def build_success_message(
    patch_sub: PatchSubscription, thread_id: str, is_recreate: bool
) -> str:
    """构建成功消息

    Args:
        patch_sub: PATCH 订阅对象
        thread_id: Thread ID
        is_recreate: 是否是重建

    Returns:
        成功消息字符串
    """
    success_msg = (
        f"✅ {'Thread 已重新创建！' if is_recreate else 'Thread 创建成功！'}\n\n"
    )

    if is_recreate:
        success_msg += (
            "💡 **提示**: 检测到原 Thread 已被删除，已为您创建新的 Thread。\n\n"
        )

    if patch_sub.series_message_id and patch_sub.patch_total:
        success_msg += (
            f"**PATCH Series**: {patch_sub.patch_version or 'v1'} (共 {patch_sub.patch_total} 个)\n"
            f"**Thread**: <#{thread_id}>\n\n"
            f"整个系列的所有 PATCH 和后续回复将在该 Thread 中展示。"
        )
    else:
        success_msg += (
            f"**PATCH**: {patch_sub.subject[:100]}\n"
            f"**Thread**: <#{thread_id}>\n\n"
            f"后续回复将在该 Thread 中展示。"
        )

    return success_msg
