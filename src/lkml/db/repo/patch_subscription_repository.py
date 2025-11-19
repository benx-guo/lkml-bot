"""PATCH 订阅仓库

负责 PATCH 订阅的数据库操作。
"""

from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from nonebot.log import logger

from ..models import PatchSubscription


@dataclass
class PatchSubscriptionData:
    """PATCH 订阅数据"""

    message_id: str
    subsystem_name: str
    discord_message_id: str
    discord_channel_id: str
    subject: str
    author: str
    url: Optional[str] = None
    expires_at: Optional[datetime] = None
    series_message_id: Optional[str] = None
    patch_version: Optional[str] = None
    patch_index: Optional[int] = None
    patch_total: Optional[int] = None


class PatchSubscriptionRepository:  # pylint: disable=too-many-instance-attributes
    """PATCH 订阅仓库"""

    async def create(
        self, session: AsyncSession, data: PatchSubscriptionData
    ) -> PatchSubscription:
        """创建 PATCH 订阅记录

        Args:
            session: 数据库会话
            data: PATCH 订阅数据

        Returns:
            创建的 PATCH 订阅对象
        """
        patch_sub = PatchSubscription(
            message_id=data.message_id,
            subsystem_name=data.subsystem_name,
            discord_message_id=data.discord_message_id,
            discord_channel_id=data.discord_channel_id,
            subject=data.subject,
            author=data.author,
            url=data.url,
            expires_at=data.expires_at or datetime.utcnow(),
            series_message_id=data.series_message_id,
            patch_version=data.patch_version,
            patch_index=data.patch_index,
            patch_total=data.patch_total,
        )
        session.add(patch_sub)
        await session.flush()
        logger.debug(f"Created PATCH subscription: {data.message_id}")
        return patch_sub

    async def find_by_message_id(
        self, session: AsyncSession, message_id: str
    ) -> Optional[PatchSubscription]:
        """根据 message_id 查找 PATCH 订阅

        Args:
            session: 数据库会话
            message_id: PATCH 的 message_id

        Returns:
            PATCH 订阅对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(PatchSubscription).where(PatchSubscription.message_id == message_id)
        )
        return result.scalar_one_or_none()

    async def find_by_discord_message_id(
        self, session: AsyncSession, discord_message_id: str
    ) -> Optional[PatchSubscription]:
        """根据 Discord 消息 ID 查找 PATCH 订阅

        Args:
            session: 数据库会话
            discord_message_id: Discord 卡片消息 ID

        Returns:
            PATCH 订阅对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(PatchSubscription).where(
                PatchSubscription.discord_message_id == discord_message_id
            )
        )
        return result.scalar_one_or_none()

    async def mark_as_subscribed(
        self, session: AsyncSession, patch_sub: PatchSubscription
    ) -> PatchSubscription:
        """标记 PATCH 为已订阅

        Args:
            session: 数据库会话
            patch_sub: PATCH 订阅对象

        Returns:
            更新后的 PATCH 订阅对象
        """
        patch_sub.is_subscribed = True
        await session.flush()
        logger.debug(f"Marked PATCH as subscribed: {patch_sub.message_id}")
        return patch_sub

    async def find_expired_unsubscribed(
        self, session: AsyncSession
    ) -> List[PatchSubscription]:
        """查找过期且未订阅的 PATCH

        Args:
            session: 数据库会话

        Returns:
            过期且未订阅的 PATCH 订阅列表
        """
        now = datetime.utcnow()
        result = await session.execute(
            select(PatchSubscription).where(
                ~PatchSubscription.is_subscribed,
                PatchSubscription.expires_at <= now,
            )
        )
        return list(result.scalars().all())

    async def delete_by_id(self, session: AsyncSession, patch_sub_id: int) -> None:
        """删除 PATCH 订阅

        Args:
            session: 数据库会话
            patch_sub_id: PATCH 订阅 ID
        """
        await session.execute(
            delete(PatchSubscription).where(PatchSubscription.id == patch_sub_id)
        )
        await session.flush()
        logger.debug(f"Deleted PATCH subscription: {patch_sub_id}")

    async def find_by_series_message_id(
        self, session: AsyncSession, series_message_id: str
    ) -> Optional[PatchSubscription]:
        """根据系列 message_id 查找已订阅的 PATCH

        Args:
            session: 数据库会话
            series_message_id: 系列 PATCH 的根 message_id

        Returns:
            PATCH 订阅对象，如果不存在或未订阅则返回 None
        """
        result = await session.execute(
            select(PatchSubscription).where(
                PatchSubscription.series_message_id == series_message_id,
                PatchSubscription.is_subscribed.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def find_series_card(
        self, session: AsyncSession, series_message_id: str
    ) -> Optional[PatchSubscription]:
        """查找系列的汇总卡片（已发送 Discord 消息的）

        查找第一个有 discord_message_id 的 PATCH 记录。
        这确保我们总是更新同一张 Discord 卡片。

        Args:
            session: 数据库会话
            series_message_id: 系列 PATCH 的根 message_id

        Returns:
            系列汇总卡片，如果不存在则返回 None
        """
        # 查找第一个有 discord_message_id 的记录（按创建时间排序）
        result = await session.execute(
            select(PatchSubscription)
            .where(
                PatchSubscription.series_message_id == series_message_id,
                PatchSubscription.discord_message_id != "",
                PatchSubscription.discord_message_id.isnot(None),
            )
            .order_by(PatchSubscription.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_series_patches(
        self, session: AsyncSession, series_message_id: str
    ) -> list[PatchSubscription]:
        """获取系列的所有 PATCH

        Args:
            session: 数据库会话
            series_message_id: 系列 PATCH 的根 message_id

        Returns:
            系列的所有 PATCH 列表，按序号排序
        """
        result = await session.execute(
            select(PatchSubscription)
            .where(PatchSubscription.series_message_id == series_message_id)
            .order_by(PatchSubscription.patch_index)
        )
        return list(result.scalars().all())


# 全局仓库实例
PATCH_SUBSCRIPTION_REPO = PatchSubscriptionRepository()
