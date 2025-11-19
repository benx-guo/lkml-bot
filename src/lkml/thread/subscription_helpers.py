"""订阅相关的辅助函数

提供订阅数据构建、过期时间计算等功能。
这是 lkml 域的核心功能，不依赖于任何特定的渲染平台。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from lkml.db.models import PatchSubscription
from lkml.db.repo.patch_subscription_repository import PatchSubscriptionData
from lkml.service.patch_subscription_service import patch_subscription_service

logger = logging.getLogger(__name__)


async def check_existing_subscription(message_id: str) -> Optional[PatchSubscription]:
    """检查是否已存在订阅

    Args:
        message_id: PATCH message_id

    Returns:
        已存在的订阅对象，如果不存在则返回 None
    """
    return await patch_subscription_service.find_by_message_id(message_id)


def build_subscription_data(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    message_id: str,
    subsystem: str,
    platform_message_id: str,
    platform_channel_id: str,
    subject: str,
    author: str,
    url: Optional[str],
    expires_at: datetime,
    series_message_id: Optional[str],
    patch_version: Optional[str],
    patch_index: Optional[int],
    patch_total: Optional[int],
) -> PatchSubscriptionData:
    """构建订阅数据

    Args:
        message_id: PATCH message_id
        subsystem: 子系统名称
        platform_message_id: 平台消息 ID
        platform_channel_id: 平台频道 ID
        subject: PATCH 主题
        author: PATCH 作者
        url: PATCH 链接
        expires_at: 过期时间
        series_message_id: 系列 message_id
        patch_version: PATCH 版本
        patch_index: PATCH 索引
        patch_total: PATCH 总数

    Returns:
        订阅数据对象
    """
    return PatchSubscriptionData(
        message_id=message_id,
        subsystem_name=subsystem,
        platform_message_id=platform_message_id,
        platform_channel_id=platform_channel_id,
        subject=subject,
        author=author,
        url=url,
        expires_at=expires_at,
        series_message_id=series_message_id,
        patch_version=patch_version,
        patch_index=patch_index,
        patch_total=patch_total,
    )


def calculate_expires_at(timeout_hours: int) -> datetime:
    """计算过期时间

    Args:
        timeout_hours: 超时小时数

    Returns:
        过期时间
    """
    return datetime.utcnow() + timedelta(hours=timeout_hours)


def log_subscription_created(
    subject: str,
    series_message_id: Optional[str],
    patch_version: Optional[str],
    patch_index: Optional[int],
    patch_total: Optional[int],
) -> None:
    """记录订阅创建日志

    Args:
        subject: PATCH 主题
        series_message_id: 系列 message_id
        patch_version: PATCH 版本
        patch_index: PATCH 索引
        patch_total: PATCH 总数
    """
    if series_message_id:
        logger.info(
            f"Created subscription card for PATCH series: {subject} "
            f"(version={patch_version}, {patch_index}/{patch_total}, series={series_message_id})"
        )
    else:
        logger.info(f"Created subscription card for PATCH: {subject}")
