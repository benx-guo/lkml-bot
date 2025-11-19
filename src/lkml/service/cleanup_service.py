"""清理服务

负责定期清理过期的 PATCH 订阅和相关数据。
这是 lkml 域的核心功能，不依赖于任何特定的渲染平台。
"""

from typing import Callable, Optional

import logging
from sqlalchemy.exc import SQLAlchemyError

from lkml.db.repo.patch_subscription_repository import PATCH_SUBSCRIPTION_REPO

logger = logging.getLogger(__name__)


class CleanupService:
    """清理服务

    定期清理过期且未订阅的 PATCH 订阅卡片和相关数据。
    """

    def __init__(
        self,
        database,
        delete_message_callback: Optional[Callable] = None,
        archive_thread_callback: Optional[Callable] = None,
    ):
        """初始化清理服务

        Args:
            database: 数据库实例
            delete_message_callback: 可选的删除消息回调函数
                (channel_id: str, message_id: str) -> bool
            archive_thread_callback: 可选的归档 Thread 回调函数
                (patch_subscription_id: int) -> None
        """
        self.database = database
        self.delete_message_callback = delete_message_callback
        self.archive_thread_callback = archive_thread_callback

    async def cleanup_expired_subscriptions(self) -> None:
        """清理过期且未订阅的 PATCH 订阅"""
        try:
            logger.info("Starting cleanup of expired subscriptions...")

            async with self.database.get_db_session() as session:
                # 查找过期且未订阅的 PATCH
                expired_subs = await PATCH_SUBSCRIPTION_REPO.find_expired_unsubscribed(
                    session
                )

                if not expired_subs:
                    logger.info("No expired subscriptions to cleanup")
                    return

                logger.info(
                    f"Found {len(expired_subs)} expired subscriptions to cleanup"
                )

                for patch_sub in expired_subs:
                    await self._cleanup_subscription(session, patch_sub)

                await session.commit()
                logger.info(
                    f"Cleanup completed: removed {len(expired_subs)} expired subscriptions"
                )

        except SQLAlchemyError as e:
            logger.error(f"Failed to cleanup expired subscriptions: {e}", exc_info=True)
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(
                f"Data error cleaning up expired subscriptions: {e}", exc_info=True
            )

    async def _cleanup_subscription(self, session, patch_sub) -> None:
        """清理单个订阅

        Args:
            session: 数据库会话
            patch_sub: PATCH 订阅对象
        """
        try:
            # 如果提供了删除消息的回调，调用它删除平台消息
            if (
                self.delete_message_callback
                and patch_sub.platform_channel_id
                and patch_sub.platform_message_id
            ):
                await self.delete_message_callback(
                    patch_sub.platform_channel_id, patch_sub.platform_message_id
                )

            # 如果提供了归档 Thread 的回调，调用它
            if self.archive_thread_callback:
                await self.archive_thread_callback(patch_sub.id)

            # 删除订阅记录
            await PATCH_SUBSCRIPTION_REPO.delete_by_id(session, patch_sub.id)

            logger.debug(f"Cleaned up subscription: {patch_sub.subject}")

        except SQLAlchemyError as e:
            logger.error(f"Failed to cleanup subscription {patch_sub.id}: {e}")
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Data error cleaning up subscription {patch_sub.id}: {e}")

    async def archive_old_threads(self, days: int = 7) -> None:
        """归档旧的 Thread

        Args:
            days: 归档多少天前创建的 Thread
        """
        try:
            logger.info(f"Archiving threads older than {days} days...")

            # TODO: 实现归档逻辑
            # 这需要查询创建时间超过指定天数的活跃 Thread

        except SQLAlchemyError as e:
            logger.error(f"Failed to archive old threads: {e}", exc_info=True)
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Data error archiving old threads: {e}", exc_info=True)
