"""邮件监控编排器（与调度器同目录层级，但置于 feed 包）

负责协调多个子系统的监控任务，聚合结果并统一管理。
"""

from nonebot.log import logger
from datetime import datetime

from ..config import Config
from ..db.database import Database
from .feed import FeedProcessor
from .types import (
    FeedProcessResult,
    MonitoringResult,
    SubsystemMonitoringResult,
)

logger = logger


class LKMLFeedMonitor:
    """循环各子系统、调用处理逻辑并聚合结果

    负责遍历所有配置的子系统，调用 FeedProcessor 处理每个子系统的 feed，
    并将所有结果聚合为一个 MonitoringResult 对象。
    """

    def __init__(
        self, *, config: Config, processor: FeedProcessor, database: Database = None
    ) -> None:
        """初始化监控器

        Args:
            config: 配置实例
            processor: Feed 处理器
            database: 数据库实例（可选，用于查询订阅状态）
        """
        self.config = config
        self.processor = processor
        self.database = database

    async def run_monitoring(self) -> MonitoringResult:
        """运行一次监控任务

        Returns:
            监控结果，包含所有子系统的处理结果和统计信息
        """
        start_time = datetime.now()
        config = self.config

        results: list[FeedProcessResult] = []
        errors: list[str] = []
        total_new_count = 0
        total_reply_count = 0

        # 获取支持的子系统列表
        supported_subsystems = config.get_supported_subsystems()
        if not supported_subsystems:
            logger.warning(
                "No supported subsystems found. Check vger cache and manual configuration."
            )

        # 获取已订阅的子系统列表
        subscribed_subsystems = await self._get_subscribed_subsystems()
        if not subscribed_subsystems:
            logger.info("No subscribed subsystems found, skipping feed monitoring")
            end_time = datetime.now()
            return MonitoringResult(
                total_subsystems=0,
                processed_subsystems=0,
                total_new_count=0,
                total_reply_count=0,
                results=[],
                start_time=start_time,
                end_time=end_time,
                errors=None,
                error_count=0,
            )

        logger.info(f"Supported subsystems: {supported_subsystems}")
        logger.info(f"Subscribed subsystems to monitor: {subscribed_subsystems}")

        # 只处理已订阅的子系统
        for subsystem_name in subscribed_subsystems:
            feed_url = f"https://lore.kernel.org/{subsystem_name}/new.atom"
            try:
                result = await self.processor.process_feed(subsystem_name, feed_url)
                results.append(result)
                total_new_count += result.new_count
                total_reply_count += result.reply_count
            except Exception as e:
                error_msg = (
                    f"Failed to process feed for {subsystem_name} ({feed_url}): {e}"
                )
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
                results.append(
                    FeedProcessResult(
                        subsystem=subsystem_name, new_count=0, reply_count=0, entries=[]
                    )
                )

        end_time = datetime.now()

        subsystem_results: list[SubsystemMonitoringResult] = []
        for result in results:
            subsystem_results.append(
                SubsystemMonitoringResult(
                    subsystem=result.subsystem,
                    new_count=result.new_count,
                    reply_count=result.reply_count,
                    entries=result.entries,
                    subscribed_users=[],
                    title=f"{result.subsystem} 邮件列表",
                )
            )

        return MonitoringResult(
            total_subsystems=len(subscribed_subsystems),
            processed_subsystems=len(subsystem_results),
            total_new_count=total_new_count,
            total_reply_count=total_reply_count,
            results=subsystem_results,
            start_time=start_time,
            end_time=end_time,
            errors=errors if errors else None,
            error_count=len(errors) if errors else 0,
        )

    async def _get_subscribed_subsystems(self) -> list[str]:
        """获取已订阅的子系统列表

        Returns:
            已订阅的子系统名称列表
        """
        if not self.database:
            logger.warning("Database not available, cannot query subscribed subsystems")
            return []

        try:
            from sqlalchemy import select
            from ..db.models import Subsystem

            async with self.database.get_db_session() as session:
                result = await session.execute(
                    select(Subsystem.name).where(Subsystem.subscribed)
                )
                return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get subscribed subsystems: {e}", exc_info=True)
            return []


# 由上层注入配置与依赖创建实例
