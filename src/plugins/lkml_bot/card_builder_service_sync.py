"""同步版本的卡片构建服务

使用同步数据库操作来避免 greenlet 问题
"""

import asyncio
from typing import Dict, List

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from nonebot.log import logger

from lkml.db.models import Base
from lkml.service.thread_content_service import thread_content_service

from .card_builder_service_sync_cover_letter import (
    create_new_card,
    update_existing_card,
)
from .thread.exceptions import DiscordHTTPError, FormatPatchError


class CardBuilderServiceSync:
    """同步版本的订阅卡片构建服务"""

    def __init__(self, database_url: str, thread_manager):
        """初始化同步卡片构建服务

        Args:
            database_url: 数据库URL（将转换为同步版本）
            thread_manager: Discord Thread 管理器
        """
        # 将异步 URL 转换为同步 URL
        sync_url = database_url.replace("sqlite+aiosqlite://", "sqlite://")

        self.engine = create_engine(sync_url, echo=False)
        self.session_factory = sessionmaker(bind=self.engine)
        self.thread_manager = thread_manager

        # 确保表已创建（使用 checkfirst=True 避免重复创建）
        Base.metadata.create_all(self.engine, checkfirst=True)

        logger.info(f"Initialized sync card builder with database: {sync_url}")

    def build_cards_from_emails(self, hours: int = 24) -> Dict[str, int]:
        """同步方式构建订阅卡片

        Args:
            hours: 扫描最近多少小时的邮件

        Returns:
            统计信息
        """
        stats = {
            "scanned": 0,
            "single_patches": 0,
            "series_patches": 0,
            "cards_created": 0,
            "cards_updated": 0,
            "errors": 0,
        }

        session = self.session_factory()
        try:
            # 1. 扫描最近的 PATCH 邮件
            emails = thread_content_service.scan_recent_patch_emails(session, hours)
            stats["scanned"] = len(emails)
            logger.info(
                f"[SYNC] Scanned {len(emails)} PATCH emails from last {hours} hours"
            )

            # 2. 分析 PATCH 类型
            single_patches, series_groups = thread_content_service.categorize_patches(
                emails
            )
            stats["single_patches"] = len(single_patches)
            stats["series_patches"] = sum(
                len(patches) for patches in series_groups.values()
            )

            logger.info(
                f"[SYNC] Found {stats['single_patches']} single patches, "
                f"{len(series_groups)} series with {stats['series_patches']} total patches"
            )

            # 3. 处理单个 PATCH
            self._process_single_patches(single_patches, stats)

            # 4. 处理系列 PATCH
            self._process_series_patches(series_groups, session, stats)

            session.commit()

        except SQLAlchemyError as e:
            logger.error(
                f"[SYNC] Database error building cards from emails: {e}", exc_info=True
            )
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(
                f"[SYNC] Data error building cards from emails: {e}", exc_info=True
            )
            session.rollback()
            stats["errors"] += 1
        finally:
            session.close()

        logger.info(
            f"[SYNC] Card building completed: "
            f"scanned={stats['scanned']}, "
            f"created={stats['cards_created']}, "
            f"updated={stats['cards_updated']}, "
            f"errors={stats['errors']}"
        )

        return stats

    def _process_single_patches(
        self, single_patches: List, stats: Dict[str, int]
    ) -> None:
        """处理单个 PATCH

        Args:
            single_patches: 单个 PATCH 列表
            stats: 统计信息字典
        """
        for email, patch_info in single_patches:
            try:
                result = asyncio.run(self._build_single_patch_async(email, patch_info))
                if result == "created":
                    stats["cards_created"] += 1
            except (SQLAlchemyError, DiscordHTTPError, FormatPatchError) as e:
                logger.error(
                    f"[SYNC] Failed to build card for single PATCH {email.message_id_header}: {e}"
                )
                stats["errors"] += 1
            except (ValueError, KeyError, AttributeError) as e:
                logger.error(
                    f"[SYNC] Data error building card for single PATCH {email.message_id_header}: {e}"
                )
                stats["errors"] += 1

    def _process_series_patches(
        self, series_groups: Dict, session, stats: Dict[str, int]
    ) -> None:
        """处理系列 PATCH

        Args:
            series_groups: 系列 PATCH 字典
            session: 数据库会话
            stats: 统计信息字典
        """
        for series_id, _series_emails_info in series_groups.items():
            try:
                # 验证 Cover Letter
                cover_result = thread_content_service.validate_cover_letter(
                    session, series_id
                )
                if not cover_result:
                    logger.debug(
                        f"[SYNC] Skipping series {series_id}: Cover Letter not found or invalid"
                    )
                    continue

                cover_letter, cover_patch_info = cover_result

                # 为 Cover Letter 创建/更新卡片
                self._process_cover_letter_card(
                    cover_letter, cover_patch_info, series_id, session, stats
                )

            except (SQLAlchemyError, DiscordHTTPError, FormatPatchError) as e:
                logger.error(
                    f"[SYNC] Failed to build card for series {series_id}: {e}",
                    exc_info=True,
                )
                stats["errors"] += 1
            except (ValueError, KeyError, AttributeError) as e:
                logger.error(
                    f"[SYNC] Data error building card for series {series_id}: {e}",
                    exc_info=True,
                )
                stats["errors"] += 1

    def _process_cover_letter_card(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        cover_letter,
        cover_patch_info,
        series_id: str,
        session,
        stats: Dict[str, int],
    ) -> None:
        """处理 Cover Letter 卡片

        Args:
            cover_letter: Cover Letter 邮件对象
            cover_patch_info: Cover Letter 的 PATCH 信息
            series_id: 系列 ID
            session: 数据库会话
            stats: 统计信息字典
        """
        try:
            result = asyncio.run(
                self._build_or_update_cover_letter_card_async(
                    cover_letter, cover_patch_info, series_id, session
                )
            )
            if result == "created":
                stats["cards_created"] += 1
            elif result == "updated":
                stats["cards_updated"] += 1
        except (SQLAlchemyError, DiscordHTTPError, FormatPatchError) as e:
            logger.error(f"[SYNC] Failed to build/update cover letter card: {e}")
            stats["errors"] += 1
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"[SYNC] Data error building/updating cover letter card: {e}")
            stats["errors"] += 1

    async def _build_single_patch_async(self, email, patch_info) -> str:
        """异步方式构建单个 PATCH 卡片"""
        result = await self.thread_manager.create_subscription_card(
            subsystem=email.subsystem.name,
            message_id=email.message_id_header,
            subject=email.subject,
            author=email.sender,
            url=email.url,
            series_message_id=None,
            patch_version=patch_info.version,
            patch_index=patch_info.index,
            patch_total=patch_info.total,
            session=None,
        )

        if result:
            logger.info(f"[SYNC] Created card for single PATCH: {email.subject}")
            return "created"
        return "exists"

    async def _build_or_update_cover_letter_card_async(
        self, cover_letter_email, patch_info, series_id, session
    ) -> str:
        """异步方式为 Cover Letter 创建或更新系列卡片

        Args:
            cover_letter_email: Cover Letter 邮件对象
            patch_info: PATCH信息（Cover Letter 的）
            series_id: 系列ID（即 Cover Letter 的 message_id）
            session: 同步数据库session（用于查询系列PATCH）

        Returns:
            'created', 'updated' 或 'exists'
        """
        # 查询该系列的所有 PATCH 邮件
        series_emails = thread_content_service.query_series_emails(session, series_id)
        logger.info(f"[SYNC] Found {len(series_emails)} emails for series {series_id}")

        # 解析所有 PATCH 并构建系列信息
        series_patches_info = thread_content_service.build_series_patches_info(
            series_emails
        )
        logger.info(
            f"[SYNC] Prepared series_info with {len(series_patches_info)} patches"
        )

        # 构建系列信息字典
        series_info = {"patches": series_patches_info}

        # 检查是否已存在 Cover Letter 的订阅卡片
        existing_card = thread_content_service.check_existing_card(
            session, cover_letter_email
        )

        if existing_card:
            return await update_existing_card(
                self.thread_manager,
                cover_letter_email,
                series_id,
                series_patches_info,
                existing_card,
            )

        # 卡片不存在，创建新的
        return await create_new_card(
            self.thread_manager,
            cover_letter_email,
            patch_info,
            series_id,
            series_patches_info,
            series_info,
        )


# 全局实例（延迟初始化）
_sync_card_builder_service = None


def get_sync_card_builder_service(
    database_url: str, thread_manager
):  # pylint: disable=global-statement
    """获取同步卡片构建服务实例"""
    global _sync_card_builder_service  # noqa: W0603  # pylint: disable=global-statement
    if _sync_card_builder_service is None:
        _sync_card_builder_service = CardBuilderServiceSync(
            database_url, thread_manager
        )
    return _sync_card_builder_service
