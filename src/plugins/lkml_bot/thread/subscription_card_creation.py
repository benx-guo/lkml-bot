"""订阅卡片创建的核心逻辑"""

from typing import Optional

from nonebot.log import logger

from lkml.db.models import PatchSubscription
from lkml.service.patch_subscription_service import patch_subscription_service
from lkml.service.thread_content_service import thread_content_service

from .params import SubscriptionCardParams


async def create_and_save_subscription(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    card_params: SubscriptionCardParams,
    platform_message_id: str,
    platform_channel_id: str,
    timeout_hours: int,
) -> Optional[PatchSubscription]:
    """创建并保存订阅记录

    Args:
        card_params: 卡片参数
        platform_message_id: Discord 消息 ID
        platform_channel_id: Discord 频道 ID
        timeout_hours: 超时小时数

    Returns:
        创建的 PatchSubscription 对象
    """
    # 计算过期时间
    expires_at = thread_content_service.calculate_expires_at(timeout_hours)

    # 构建订阅数据
    data = thread_content_service.build_subscription_data(
        card_params.message_id,
        card_params.subsystem,
        platform_message_id,
        platform_channel_id,
        card_params.subject,
        card_params.author,
        card_params.url,
        expires_at,
        card_params.series_message_id,
        card_params.patch_version,
        card_params.patch_index,
        card_params.patch_total,
    )

    # 保存到数据库
    patch_sub = await patch_subscription_service.create(data)

    # 记录详细信息
    thread_content_service.log_subscription_created(
        card_params.subject,
        card_params.series_message_id,
        card_params.patch_version,
        card_params.patch_index,
        card_params.patch_total,
    )

    return patch_sub


async def create_subscription_card_core(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    session,
    message_id: str,
    card_params: SubscriptionCardParams,
    send_card_func,
    platform_channel_id: str,
    timeout_hours: int,
) -> Optional[PatchSubscription]:
    """创建订阅卡片的核心逻辑

    Args:
        session: 数据库会话（用于 send_card_func）
        message_id: PATCH message_id
        card_params: 卡片参数
        send_card_func: 发送卡片函数
        platform_channel_id: Discord 频道 ID
        timeout_hours: 超时小时数

    Returns:
        创建的 PatchSubscription 对象，失败返回 None
    """
    # 检查是否已存在
    existing = await thread_content_service.check_existing_subscription(message_id)
    if existing:
        logger.debug(f"Subscription card already exists: {message_id}")
        return existing

    # 发送订阅卡片到 Discord
    platform_message_id = await send_card_func(card_params, session)
    if not platform_message_id:
        return None

    # 创建并保存订阅记录
    return await create_and_save_subscription(
        card_params,
        platform_message_id,
        platform_channel_id,
        timeout_hours,
    )
