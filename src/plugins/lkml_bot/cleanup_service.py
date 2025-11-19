"""Discord 清理服务适配器

包装 lkml.service.cleanup_service，提供 Discord 特定的消息删除和 Thread 归档功能。
"""

import httpx
from nonebot.log import logger

from lkml.service.cleanup_service import CleanupService as BaseCleanupService
from lkml.service.thread_service import thread_service

from .config import get_config
from .thread.exceptions import DiscordHTTPError


class CleanupService(BaseCleanupService):
    """Discord 清理服务

    继承自 lkml.service.cleanup_service，添加 Discord 特定的消息删除和 Thread 归档功能。
    """

    def __init__(self, database):
        """初始化清理服务

        Args:
            database: 数据库实例
        """
        self.config = get_config()
        # 传递 Discord 消息删除回调和 Thread 归档回调
        super().__init__(
            database,
            delete_message_callback=self._delete_discord_message,
            archive_thread_callback=self._archive_thread,
        )

    async def _archive_thread(self, patch_subscription_id: int) -> None:
        """归档 Thread

        Args:
            patch_subscription_id: PATCH 订阅 ID
        """
        thread = await thread_service.find_by_patch_subscription_id(
            patch_subscription_id
        )
        if thread and thread.is_active:
            await thread_service.archive(thread)

    async def _delete_discord_message(self, channel_id: str, message_id: str) -> bool:
        """删除 Discord 消息

        Args:
            channel_id: 频道 ID
            message_id: 消息 ID

        Returns:
            成功返回 True，失败返回 False
        """
        try:
            if not self.config.discord_bot_token:
                logger.error("Discord bot token not configured")
                return False

            headers = {
                "Authorization": f"Bot {self.config.discord_bot_token}",
            }

            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code in {200, 204}:
                    logger.debug(f"Deleted Discord message: {message_id}")
                    return True
                if response.status_code == 404:
                    # 消息已经不存在了，也算成功
                    logger.debug(f"Discord message already deleted: {message_id}")
                    return True
                logger.error(
                    f"Failed to delete Discord message: {response.status_code}, {response.text}"
                )
                return False

        except (DiscordHTTPError, httpx.HTTPError) as e:
            logger.error(f"Failed to delete Discord message: {e}", exc_info=True)
            return False
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Data error deleting Discord message: {e}", exc_info=True)
            return False


# 全局清理服务实例（延迟初始化）
_cleanup_service = None


def get_cleanup_service(database) -> CleanupService:
    """获取清理服务实例

    Args:
        database: 数据库实例

    Returns:
        清理服务实例
    """
    global _cleanup_service  # pylint: disable=global-statement
    if _cleanup_service is None:
        _cleanup_service = CleanupService(database)
    return _cleanup_service
