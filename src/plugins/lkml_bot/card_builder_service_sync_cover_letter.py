"""Cover Letter 卡片构建辅助函数"""

from datetime import datetime, timedelta
from typing import List

from nonebot.log import logger

from lkml.db.models import PatchSubscription
from lkml.db.repo.patch_subscription_repository import PatchSubscriptionData
from lkml.feed.patch_parser import parse_patch_subject
from lkml.service.patch_subscription_service import patch_subscription_service

from .thread.params import SeriesCardParams


async def create_sub_patch_subscriptions(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    series_patches_info: List[dict],
    cover_letter_email,
    patch_info,
    series_id: str,
    platform_message_id: str,
    platform_channel_id: str,
) -> None:
    """为所有子 PATCH 创建订阅记录

    Args:
        series_patches_info: 系列 PATCH 信息列表
        cover_letter_email: Cover Letter 邮件对象
        patch_info: Cover Letter 的 PATCH 信息
        series_id: 系列 ID
        platform_message_id: Discord 消息 ID
        platform_channel_id: Discord 频道 ID
    """
    for patch_info_item in series_patches_info:
        # 跳过 Cover Letter（已存在）
        if patch_info_item["patch_index"] == 0:
            continue

        # 检查是否已存在
        existing_sub = await patch_subscription_service.find_by_message_id(
            patch_info_item["message_id"]
        )

        if not existing_sub:
            # 创建订阅记录（但不发送 Discord 消息）
            expires_at = datetime.utcnow() + timedelta(hours=24)
            data = PatchSubscriptionData(
                message_id=patch_info_item["message_id"],
                subsystem_name=cover_letter_email.subsystem.name,
                platform_message_id=platform_message_id,
                platform_channel_id=platform_channel_id,
                subject=patch_info_item["subject"],
                author=cover_letter_email.sender,
                url=patch_info_item["url"],
                expires_at=expires_at,
                series_message_id=series_id,
                patch_version=patch_info.version,
                patch_index=patch_info_item["patch_index"],
                patch_total=patch_info_item["patch_total"],
            )
            await patch_subscription_service.create(data)


def build_series_card_params(
    cover_letter_email,
    patch_info,
    series_id: str,
    series_info: dict,
) -> SeriesCardParams:
    """构建系列卡片参数

    Args:
        cover_letter_email: Cover Letter 邮件对象
        patch_info: Cover Letter 的 PATCH 信息
        series_id: 系列 ID
        series_info: 系列信息字典

    Returns:
        系列卡片参数
    """
    return SeriesCardParams(
        subsystem=cover_letter_email.subsystem.name,
        message_id=cover_letter_email.message_id_header,
        subject=cover_letter_email.subject,
        author=cover_letter_email.sender,
        url=cover_letter_email.url,
        series_message_id=series_id,
        patch_version=patch_info.version,
        patch_index=patch_info.index,  # 0
        patch_total=patch_info.total,
        series_info=series_info,
    )


async def update_existing_card(
    thread_manager,
    cover_letter_email,
    series_id: str,
    series_patches_info: List[dict],
    existing_card: PatchSubscription,
) -> str:
    """更新已存在的卡片

    Args:
        thread_manager: Thread 管理器
        cover_letter_email: Cover Letter 邮件对象
        series_id: 系列 ID
        series_patches_info: 系列 PATCH 信息列表
        existing_card: 已存在的卡片

    Returns:
        'updated' 或 'exists'
    """
    logger.info(
        f"[SYNC] Cover letter card exists for series: {cover_letter_email.subject}, "
        f"checking for new patches to add..."
    )

    # 为所有子 PATCH 创建订阅记录（如果不存在）
    await create_sub_patch_subscriptions(
        series_patches_info,
        cover_letter_email,
        parse_patch_subject(cover_letter_email.subject),
        series_id,
        existing_card.platform_message_id,
        existing_card.platform_channel_id,
    )

    # 获取 Cover Letter 卡片
    cover_card = await patch_subscription_service.find_by_message_id(
        cover_letter_email.message_id_header
    )

    if cover_card and cover_card.platform_message_id:
        # 获取该系列的所有 PATCH 订阅记录
        series_patches_from_db = await patch_subscription_service.get_series_patches(
            series_id
        )

        # 更新 Discord 卡片
        await thread_manager.update_series_card(cover_card, series_patches_from_db)

        logger.info(
            f"[SYNC] Updated Discord card for cover letter: {cover_letter_email.subject}, "
            f"now showing {len(series_patches_from_db)} patches"
        )
        return "updated"
    return "exists"


async def create_new_card(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    thread_manager,
    cover_letter_email,
    patch_info,
    series_id: str,
    series_patches_info: List[dict],
    series_info: dict,
) -> str:
    """创建新的卡片

    Args:
        thread_manager: Thread 管理器
        cover_letter_email: Cover Letter 邮件对象
        patch_info: Cover Letter 的 PATCH 信息
        series_id: 系列 ID
        series_patches_info: 系列 PATCH 信息列表
        series_info: 系列信息字典

    Returns:
        'created' 或 'exists'
    """
    params = build_series_card_params(
        cover_letter_email, patch_info, series_id, series_info
    )
    result = await thread_manager.create_or_update_series_card(params, session=None)

    if not result:
        return "exists"

    logger.info(
        f"[SYNC] Created cover letter card for series: {cover_letter_email.subject}, "
        f"with {len(series_patches_info)} patches (from EmailMessage table)"
    )

    # 为所有子 PATCH 创建订阅记录（如果不存在）
    await create_sub_patch_subscriptions(
        series_patches_info,
        cover_letter_email,
        patch_info,
        series_id,
        result.platform_message_id,
        result.platform_channel_id,
    )

    # 创建完所有订阅记录后，立即更新 Discord 卡片以显示所有 PATCH
    logger.info(
        f"[SYNC] Immediately updating Discord card to show all {len(series_patches_info)} patches"
    )

    # 获取 Cover Letter 卡片
    cover_card = await patch_subscription_service.find_by_message_id(
        cover_letter_email.message_id_header
    )

    if cover_card:
        # 获取所有系列 PATCH
        all_series_patches = await patch_subscription_service.get_series_patches(
            series_id
        )

        logger.info(
            f"[SYNC] Found {len(all_series_patches)} patches in database, updating Discord card"
        )

        # 立即更新 Discord 卡片
        await thread_manager.update_series_card(cover_card, all_series_patches)

        logger.info("[SYNC] Successfully updated Discord card with all patches")

    return "created"
