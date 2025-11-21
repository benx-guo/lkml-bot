"""PATCH Thread 仓库

负责 PATCH Thread 的数据库操作。
这是平台无关的仓库，可以用于任何支持 Thread 功能的平台。
"""

import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..models import PatchThread

logger = logging.getLogger(__name__)


@dataclass
class PatchThreadData:
    """PATCH Thread 数据"""

    patch_card_id: int
    thread_id: str
    thread_name: str


class PatchThreadRepository:
    """PATCH Thread 仓库"""

    async def create(self, session: AsyncSession, data: PatchThreadData) -> PatchThread:
        """创建 PATCH Thread 记录

        Args:
            session: 数据库会话
            data: PATCH Thread 数据

        Returns:
            创建的 PATCH Thread 对象
        """
        thread = PatchThread(
            patch_card_id=data.patch_card_id,
            thread_id=data.thread_id,
            thread_name=data.thread_name,
        )
        session.add(thread)
        await session.flush()
        logger.debug(f"Created PATCH Thread: {data.thread_id}")
        return thread

    async def find_by_thread_id(
        self, session: AsyncSession, thread_id: str
    ) -> Optional[PatchThread]:
        """根据 thread_id 查找 PATCH Thread

        Args:
            session: 数据库会话
            thread_id: Thread ID

        Returns:
            PATCH Thread 对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(PatchThread).where(PatchThread.thread_id == thread_id)
        )
        return result.scalar_one_or_none()

    async def find_by_patch_card_id(
        self, session: AsyncSession, patch_card_id: int
    ) -> Optional[PatchThread]:
        """根据 PATCH 卡片 ID 查找 PATCH Thread

        Args:
            session: 数据库会话
            patch_card_id: PATCH 卡片 ID

        Returns:
            PATCH Thread 对象，如果不存在则返回 None
        """
        result = await session.execute(
            select(PatchThread).where(PatchThread.patch_card_id == patch_card_id)
        )
        return result.scalar_one_or_none()

    async def archive_thread(
        self, session: AsyncSession, thread: PatchThread
    ) -> PatchThread:
        """归档 PATCH Thread

        Args:
            session: 数据库会话
            thread: PATCH Thread 对象

        Returns:
            更新后的 PATCH Thread 对象
        """
        thread.is_active = False
        thread.archived_at = datetime.utcnow()
        await session.flush()
        logger.debug(f"Archived PATCH Thread: {thread.thread_id}")
        return thread

    async def count_active_threads(self, session: AsyncSession) -> int:
        """统计活跃的 Thread 数量

        Args:
            session: 数据库会话

        Returns:
            活跃的 Thread 数量
        """
        result = await session.execute(
            select(PatchThread).where(PatchThread.is_active.is_(True))
        )
        return len(list(result.scalars().all()))

    async def update_thread_status(
        self, session: AsyncSession, thread_id: str, is_active: bool
    ) -> bool:
        """更新 Thread 的活跃状态

        Args:
            session: 数据库会话
            thread_id: Thread ID
            is_active: 是否活跃

        Returns:
            是否更新成功
        """
        result = await session.execute(
            update(PatchThread)
            .where(PatchThread.thread_id == thread_id)
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

    async def update_overview_message_id(
        self, session: AsyncSession, thread_id: str, overview_message_id: str
    ) -> bool:
        """更新 Thread 的 Overview 消息 ID

        Args:
            session: 数据库会话
            thread_id: Thread ID
            overview_message_id: Overview 消息 ID

        Returns:
            是否更新成功
        """
        result = await session.execute(
            update(PatchThread)
            .where(PatchThread.thread_id == thread_id)
            .values(overview_message_id=overview_message_id)
        )
        if result.rowcount > 0:
            logger.debug(
                f"Updated Thread overview_message_id: {thread_id}, message_id={overview_message_id}"
            )
            return True
        logger.warning(f"Thread not found for overview_message_id update: {thread_id}")
        return False


# 全局仓库实例
PATCH_THREAD_REPO = PatchThreadRepository()
