"""Thread 服务

封装 Thread 相关的数据库操作，提供业务逻辑层接口。
"""

import logging
from typing import Optional

from ..db.database import get_database
from ..db.models import PatchThread
from ..db.repo.patch_thread_repository import (
    PATCH_THREAD_REPO,
    PatchThreadData,
)

logger = logging.getLogger(__name__)


class ThreadService:
    """Thread 服务类"""

    async def find_by_patch_subscription_id(
        self, patch_subscription_id: int
    ) -> Optional[PatchThread]:
        """根据 PATCH 订阅 ID 查找 Thread

        Args:
            patch_subscription_id: PATCH 订阅 ID

        Returns:
            Thread 对象，如果不存在则返回 None
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                return await PATCH_THREAD_REPO.find_by_patch_subscription_id(
                    session, patch_subscription_id
                )
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to find thread by patch_subscription_id: {e}", exc_info=True
            )
            return None

    async def find_by_thread_id(self, thread_id: str) -> Optional[PatchThread]:
        """根据 Thread ID 查找 Thread

        Args:
            thread_id: Thread ID

        Returns:
            Thread 对象，如果不存在则返回 None
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                return await PATCH_THREAD_REPO.find_by_thread_id(session, thread_id)
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to find thread by thread_id: {e}", exc_info=True)
            return None

    async def create(
        self, patch_subscription_id: int, thread_id: str, thread_name: str
    ) -> Optional[PatchThread]:
        """创建 Thread 记录

        Args:
            patch_subscription_id: PATCH 订阅 ID
            thread_id: Thread ID
            thread_name: Thread 名称

        Returns:
            创建的 Thread 对象，失败返回 None
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                thread_data = PatchThreadData(
                    patch_subscription_id=patch_subscription_id,
                    thread_id=thread_id,
                    thread_name=thread_name[:100],
                )
                thread = await PATCH_THREAD_REPO.create(session, thread_data)
                await session.commit()
                return thread
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to create thread: {e}", exc_info=True)
            return None

    async def update_patch_subscription_id(
        self, thread_id: str, patch_subscription_id: int
    ) -> bool:
        """更新 Thread 的 patch_subscription_id

        Args:
            thread_id: Thread ID
            patch_subscription_id: 新的 PATCH 订阅 ID

        Returns:
            成功返回 True，失败返回 False
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                thread = await PATCH_THREAD_REPO.find_by_thread_id(session, thread_id)
                if thread:
                    thread.patch_subscription_id = patch_subscription_id
                    await session.commit()
                    return True
                return False
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to update thread patch_subscription_id: {e}", exc_info=True
            )
            return False

    async def delete(self, thread: PatchThread) -> bool:
        """删除 Thread 记录

        Args:
            thread: Thread 对象

        Returns:
            成功返回 True，失败返回 False
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                await session.delete(thread)
                await session.commit()
                return True
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to delete thread: {e}", exc_info=True)
            return False

    async def archive(self, thread: PatchThread) -> bool:
        """归档 Thread

        Args:
            thread: Thread 对象

        Returns:
            成功返回 True，失败返回 False
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                await PATCH_THREAD_REPO.archive_thread(session, thread)
                await session.commit()
                return True
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to archive thread: {e}", exc_info=True)
            return False

    async def count_active_threads(self) -> int:
        """统计活跃的 Thread 数量

        Returns:
            活跃 Thread 数量
        """
        try:
            database = get_database()
            async with database.get_db_session() as session:
                return await PATCH_THREAD_REPO.count_active_threads(session)
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(f"Failed to count active threads: {e}", exc_info=True)
            return 0


# 全局服务实例
thread_service = ThreadService()
