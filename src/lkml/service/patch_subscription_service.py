"""PATCH 订阅服务

封装 PATCH 订阅相关的数据库操作，提供业务逻辑层接口。
"""

import logging
from typing import Optional, List

from ..db.database import get_database
from ..db.models import PatchSubscription
from ..db.repo.patch_subscription_repository import (
    PATCH_SUBSCRIPTION_REPO,
    PatchSubscriptionData,
)

logger = logging.getLogger(__name__)


class PatchSubscriptionService:
    """PATCH 订阅服务类"""

    async def find_by_message_id(self, message_id: str) -> Optional[PatchSubscription]:
        """根据 message_id 查找 PATCH 订阅

        Args:
            message_id: PATCH message_id

        Returns:
            PATCH 订阅对象，如果不存在则返回 None
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                return await PATCH_SUBSCRIPTION_REPO.find_by_message_id(
                    session, message_id
                )
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to find patch subscription by message_id: {e}", exc_info=True
            )
            return None

    async def find_by_series_message_id(
        self, series_message_id: str
    ) -> Optional[PatchSubscription]:
        """根据系列 message_id 查找 PATCH 订阅

        Args:
            series_message_id: 系列 message_id

        Returns:
            PATCH 订阅对象，如果不存在则返回 None
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                return await PATCH_SUBSCRIPTION_REPO.find_by_series_message_id(
                    session, series_message_id
                )
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to find patch subscription by series_message_id: {e}",
                exc_info=True,
            )
            return None

    async def find_series_card(
        self, series_message_id: str
    ) -> Optional[PatchSubscription]:
        """查找系列卡片（Cover Letter）

        Args:
            series_message_id: 系列 message_id

        Returns:
            系列卡片对象，如果不存在则返回 None
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                return await PATCH_SUBSCRIPTION_REPO.find_series_card(
                    session, series_message_id
                )
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to find series card: {e}", exc_info=True)
            return None

    async def create(self, data: PatchSubscriptionData) -> Optional[PatchSubscription]:
        """创建 PATCH 订阅记录

        Args:
            data: PATCH 订阅数据

        Returns:
            创建的 PATCH 订阅对象，失败返回 None
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                patch_sub = await PATCH_SUBSCRIPTION_REPO.create(session, data)
                await session.commit()
                return patch_sub
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to create patch subscription: {e}", exc_info=True)
            return None

    async def mark_as_subscribed(self, patch_sub: PatchSubscription) -> bool:
        """标记 PATCH 为已订阅

        Args:
            patch_sub: PATCH 订阅对象

        Returns:
            成功返回 True，失败返回 False
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                await PATCH_SUBSCRIPTION_REPO.mark_as_subscribed(session, patch_sub)
                await session.commit()
                return True
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to mark patch as subscribed: {e}", exc_info=True)
            return False

    async def get_series_patches(
        self, series_message_id: str
    ) -> List[PatchSubscription]:
        """获取系列的所有 PATCH

        Args:
            series_message_id: 系列 message_id

        Returns:
            系列 PATCH 列表
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                return await PATCH_SUBSCRIPTION_REPO.get_series_patches(
                    session, series_message_id
                )
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to get series patches: {e}", exc_info=True)
            return []


# 全局服务实例
patch_subscription_service = PatchSubscriptionService()
