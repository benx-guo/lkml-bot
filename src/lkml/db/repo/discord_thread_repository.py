"""Discord Thread 仓库

负责 Discord Thread 的数据库操作。
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from nonebot.log import logger

from ..models import DiscordThread


@dataclass
class DiscordThreadData:
    """Discord Thread 数据"""

    patch_subscription_id: int
    thread_id: str
    thread_name: str


class DiscordThreadRepository:
    """Discord Thread 仓库"""

    async def create(
        self, session: AsyncSession, data: DiscordThreadData
    ) -> DiscordThread:
        """创建 Discord Thread 记录

        Args:
            session: 数据库会话
            data: Discord Thread 数据

        Returns:
            创建的 Discord Thread 对象
        """
        thread = DiscordThread(
            patch_subscription_id=data.patch_subscription_id,
            thread_id=data.thread_id,
            thread_name=data.thread_name,
        )
        session.add(thread)
        await session.flush()
        logger.debug(f"Created Discord Thread: {data.thread_id}")
        return thread

    async def find_by_thread_id(
        self, session: AsyncSession, thread_id: str
    ) -> Optional[DiscordThread]:
        """根据 thread_id 查找 Discord Thread

        Args:
            session: 数据库会话
            thread_id: Discord Thread ID

        Returns:
            Discord Thread 对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(DiscordThread).where(DiscordThread.thread_id == thread_id)
        )
        return result.scalar_one_or_none()

    async def find_by_patch_subscription_id(
        self, session: AsyncSession, patch_sub_id: int
    ) -> Optional[DiscordThread]:
        """根据 PATCH 订阅 ID 查找 Discord Thread

        Args:
            session: 数据库会话
            patch_sub_id: PATCH 订阅 ID

        Returns:
            Discord Thread 对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(DiscordThread).where(
                DiscordThread.patch_subscription_id == patch_sub_id
            )
        )
        return result.scalar_one_or_none()

    async def archive_thread(
        self, session: AsyncSession, thread: DiscordThread
    ) -> DiscordThread:
        """归档 Discord Thread

        Args:
            session: 数据库会话
            thread: Discord Thread 对象

        Returns:
            更新后的 Discord Thread 对象
        """
        thread.is_active = False
        thread.archived_at = datetime.utcnow()
        await session.flush()
        logger.debug(f"Archived Discord Thread: {thread.thread_id}")
        return thread

    async def count_active_threads(self, session: AsyncSession) -> int:
        """统计活跃的 Thread 数量

        Args:
            session: 数据库会话

        Returns:
            活跃的 Thread 数量
        """
        result = await session.execute(
            select(DiscordThread).where(DiscordThread.is_active.is_(True))
        )
        return len(list(result.scalars().all()))

    async def update_thread_status(
        self, session: AsyncSession, thread_id: str, is_active: bool
    ) -> bool:
        """更新 Thread 的活跃状态

        Args:
            session: 数据库会话
            thread_id: Discord Thread ID
            is_active: 是否活跃

        Returns:
            是否更新成功
        """
        result = await session.execute(
            update(DiscordThread)
            .where(DiscordThread.thread_id == thread_id)
            .values(
                is_active=is_active,
                archived_at=datetime.utcnow() if not is_active else None,
            )
        )
        if result.rowcount > 0:
            logger.debug(f"Updated Thread status: {thread_id}, active={is_active}")
            return True
            logger.warning(f"Thread not found for status update: {thread_id}")
            return False


# 全局仓库实例
DISCORD_THREAD_REPO = DiscordThreadRepository()
