"""PATCH 订阅仓库

负责 PATCH 订阅的数据库操作。
"""

import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..models import PatchCard

logger = logging.getLogger(__name__)


@dataclass
class PatchCardData:
    """PATCH 卡片数据"""

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


class PatchCardRepository:  # pylint: disable=too-many-instance-attributes
    """PATCH 卡片仓库"""

    async def create(self, session: AsyncSession, data: PatchCardData) -> PatchCard:
        """创建 PATCH 订阅记录

        Args:
            session: 数据库会话
            data: PATCH 订阅数据

        Returns:
            创建的 PATCH 订阅对象
        """
        patch_card = PatchCard(
            message_id_header=data.message_id_header,
            subsystem_name=data.subsystem_name,
            platform_message_id=data.platform_message_id,
            platform_channel_id=data.platform_channel_id,
            subject=data.subject,
            author=data.author,
            url=data.url,
            expires_at=data.expires_at or datetime.utcnow(),
            is_series_patch=data.is_series_patch,
            series_message_id=data.series_message_id,
            patch_version=data.patch_version,
            patch_index=data.patch_index,
            patch_total=data.patch_total,
        )
        session.add(patch_card)
        await session.flush()
        logger.debug(f"Created PATCH card: {data.message_id_header}")
        return patch_card

    async def find_by_message_id_header(
        self, session: AsyncSession, message_id_header: str
    ) -> Optional[PatchCard]:
        """根据 message_id_header 查找 PATCH 订阅

        Args:
            session: 数据库会话
            message_id_header: PATCH 的 message_id_header

        Returns:
            PATCH 订阅对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(PatchCard).where(PatchCard.message_id_header == message_id_header)
        )
        return result.scalar_one_or_none()

    async def find_by_platform_message_id(
        self, session: AsyncSession, platform_message_id: str
    ) -> Optional[PatchCard]:
        """根据平台消息 ID 查找 PATCH 订阅

        Args:
            session: 数据库会话
            platform_message_id: 平台卡片消息 ID

        Returns:
            PATCH 订阅对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(PatchCard).where(
                PatchCard.platform_message_id == platform_message_id
            )
        )
        return result.scalar_one_or_none()

    async def mark_as_has_thread(
        self, session: AsyncSession, patch_card: PatchCard
    ) -> PatchCard:
        """标记 PATCH 为已建立 Thread

        Args:
            session: 数据库会话
            patch_card: PATCH 卡片对象

        Returns:
            更新后的 PATCH 卡片对象
        """
        patch_card.has_thread = True
        await session.flush()
        logger.debug(f"Marked PATCH as has_thread: {patch_card.message_id_header}")
        return patch_card

    async def find_expired_without_thread(
        self, session: AsyncSession
    ) -> List[PatchCard]:
        """查找过期且未建立 Thread 的 PATCH

        Args:
            session: 数据库会话

        Returns:
            过期且未建立 Thread 的 PATCH 卡片列表
        """
        now = datetime.utcnow()
        result = await session.execute(
            select(PatchCard).where(
                ~PatchCard.has_thread,
                PatchCard.expires_at <= now,
            )
        )
        return list(result.scalars().all())

    async def delete_by_id(self, session: AsyncSession, patch_card_id: int) -> None:
        """删除 PATCH 卡片

        Args:
            session: 数据库会话
            patch_card_id: PATCH 卡片 ID
        """
        await session.execute(delete(PatchCard).where(PatchCard.id == patch_card_id))
        await session.flush()
        logger.debug(f"Deleted PATCH card: {patch_card_id}")

    async def find_by_series_message_id(
        self, session: AsyncSession, series_message_id: str
    ) -> Optional[PatchCard]:
        """根据系列 message_id 查找已建立 Thread 的 PATCH

        Args:
            session: 数据库会话
            series_message_id: 系列 PATCH 的根 message_id

        Returns:
            PATCH 卡片对象，如果不存在或未建立 Thread 则返回 None
        """
        result = await session.execute(
            select(PatchCard).where(
                PatchCard.series_message_id == series_message_id,
                PatchCard.has_thread.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def find_series_patch_card(
        self, session: AsyncSession, series_message_id: str
    ) -> Optional[PatchCard]:
        """查找系列的汇总卡片（已发送平台消息的）

        查找第一个有 platform_message_id 的 PATCH 记录。
        这确保我们总是更新同一张平台卡片。

        Args:
            session: 数据库会话
            series_message_id: 系列 PATCH 的根 message_id

        Returns:
            系列汇总卡片，如果不存在则返回 None
        """
        # 查找第一个有 platform_message_id 的记录（按创建时间排序）
        result = await session.execute(
            select(PatchCard)
            .where(
                PatchCard.series_message_id == series_message_id,
                PatchCard.platform_message_id != "",
                PatchCard.platform_message_id.isnot(None),
            )
            .order_by(PatchCard.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_series_patches(
        self, session: AsyncSession, series_message_id: str
    ) -> list[PatchCard]:
        """获取系列的所有 PATCH

        Args:
            session: 数据库会话
            series_message_id: 系列 PATCH 的根 message_id

        Returns:
            系列的所有 PATCH 列表，按序号排序
        """
        result = await session.execute(
            select(PatchCard)
            .where(PatchCard.series_message_id == series_message_id)
            .order_by(PatchCard.patch_index)
        )
        return list(result.scalars().all())


# 全局仓库实例
PATCH_CARD_REPO = PatchCardRepository()
