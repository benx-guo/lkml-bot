"""数据库模块（数据库接口和实现）

定义了数据库访问的抽象接口和具体实现，提供统一的数据库会话管理。
"""

from abc import ABC, abstractmethod
from typing import Optional
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

__all__ = ["Database", "LKMLDatabase", "set_database", "get_database"]


class Database(ABC):
    """数据库接口

    定义数据库访问的抽象接口，支持不同的数据库实现。
    """

    @abstractmethod
    def get_db_session(self):
        """获取数据库会话（返回异步上下文管理器）

        Returns:
            异步上下文管理器，用于获取数据库会话
        """
        pass


# 全局数据库实例（由插件层注入）
_database: Optional[Database] = None


def set_database(database: Database) -> None:
    """设置数据库实例

    Args:
        database: 数据库实现实例
    """
    global _database
    _database = database


def get_database() -> Database:
    """获取数据库实例

    Returns:
        数据库实例

    Raises:
        RuntimeError: 如果数据库未初始化
    """
    if _database is None:
        raise RuntimeError("Database not initialized. Call set_database() first.")
    return _database


class LKMLDatabase(Database):
    """LKML 数据库实现

    使用 SQLAlchemy 实现异步数据库访问，支持自动建表。
    """

    def __init__(self, database_url: str, base):
        """初始化数据库连接

        Args:
            database_url: 数据库连接 URL
            base: SQLAlchemy 的 Base 类
        """
        self.database_url = database_url
        self.base = base
        self._engine = None
        self._session_factory = None
        self._tables_created = False

    def _init_engine(self):
        """初始化数据库引擎（懒加载模式）"""
        if self._engine is None:
            self._engine = create_async_engine(
                self.database_url,
                echo=False,
                future=True,
            )
            self._session_factory = async_sessionmaker(
                self._engine, class_=AsyncSession, expire_on_commit=False
            )

    async def _ensure_tables(self):
        """确保数据库表已创建

        首次调用时自动创建表结构。
        本项目不考虑历史迁移场景；如需变更结构，请手动清空或重建数据库。
        """
        if not self._tables_created:
            self._init_engine()
            async with self._engine.begin() as conn:
                await conn.run_sync(self.base.metadata.create_all)
            self._tables_created = True

    @asynccontextmanager
    async def get_db_session(self):
        """获取数据库会话

        Yields:
            数据库会话对象，使用完毕后自动提交或回滚
        """
        self._init_engine()
        await self._ensure_tables()
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
