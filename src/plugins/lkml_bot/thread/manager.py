"""Discord Thread 管理器

负责管理 Discord Thread 的创建、更新和生命周期。
"""

from datetime import datetime, timedelta
from typing import Dict, Optional

from nonebot.log import logger
from sqlalchemy.exc import SQLAlchemyError

from lkml.db.models import PatchSubscription
from lkml.db.repo.patch_subscription_repository import PatchSubscriptionData
from lkml.service.patch_subscription_service import patch_subscription_service
from lkml.service.thread_service import thread_service

from ..config import get_config
from .card_builder import (
    build_subscription_description,
    format_patch_list_item,
    get_series_patches,
)
from .discord_api import (
    _handle_existing_thread_retrieval,
    check_thread_exists as api_check_thread_exists,
    create_discord_thread as api_create_discord_thread,
    send_discord_embed,
    send_message_to_thread as api_send_message_to_thread,
    update_discord_series_card,
)
from .exceptions import DiscordHTTPError, FormatPatchError
from .params import SeriesCardParams, SubscriptionCardParams
from .series_patches import process_and_send_patch
from .subscription_card_creation import create_subscription_card_core


class DiscordThreadManager:
    """Discord Thread 管理器

    负责创建和管理 Discord Threads，包括池管理和限制处理。
    """

    def __init__(self, database):
        """初始化 Thread 管理器

        Args:
            database: 数据库实例
        """
        self.database = database
        self.config = get_config()

    def _format_patch_list_item(self, patch, max_subject_length: int = 80) -> str:
        """格式化 PATCH 列表项

        Args:
            patch: Patch 对象（需要有 subject 和 url 属性）
            max_subject_length: 主题最大长度

        Returns:
            格式化后的字符串
        """
        return format_patch_list_item(patch, max_subject_length)

    async def create_or_update_series_card(
        self, params: SeriesCardParams, session=None
    ) -> Optional[PatchSubscription]:
        """创建或更新系列汇总卡片

        对于系列 PATCH，只创建一个汇总卡片，显示整个系列的目录。
        每个 PATCH 都会保存到数据库，但只有第一个 PATCH 会发送 Discord 消息，
        后续的 PATCH 会更新这个消息。

        Args:
            params: 系列卡片参数
            session: 可选的外部 session

        Returns:
            PATCH 订阅对象，失败返回 None
        """
        local_session = None

        try:
            if not params.series_message_id:
                # 不是系列，直接创建普通卡片
                return await self.create_subscription_card(
                    params.subsystem,
                    params.message_id,
                    params.subject,
                    params.author,
                    params.url,
                    params.series_message_id,
                    params.patch_version,
                    params.patch_index,
                    params.patch_total,
                    session=session,
                )

            # 使用外部 session 或创建新的
            if session is None:
                async with self.database.get_db_session() as session_context:
                    local_session = session_context
                    session = session_context

            # 保存当前 PATCH 到数据库
            current_patch = await self._save_patch_to_database(params)

            # 检查是否已经有系列卡片
            series_card = await patch_subscription_service.find_series_card(
                params.series_message_id
            )

            if series_card:
                # 已有系列卡片，更新 Discord 消息
                await self._update_existing_series_card(series_card, params, session)
                return series_card

            # 首次创建系列卡片
            return await self._create_new_series_card(params, current_patch, session)

        except (SQLAlchemyError, DiscordHTTPError, FormatPatchError) as e:
            logger.error(f"Failed to create/update series card: {e}", exc_info=True)
            return None
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Data error in create/update series card: {e}", exc_info=True)
            return None
        finally:
            # 如果是内部创建的 session，需要关闭
            if local_session:
                try:
                    await local_session.close()
                except (SQLAlchemyError, RuntimeError) as e:
                    logger.warning(f"Error closing session: {e}")

    async def _save_patch_to_database(
        self, params: SeriesCardParams
    ) -> PatchSubscription:
        """保存 PATCH 到数据库

        Args:
            params: 系列卡片参数

        Returns:
            PATCH 订阅对象
        """
        existing_patch = await patch_subscription_service.find_by_message_id(
            params.message_id
        )

        if existing_patch:
            logger.debug(f"PATCH already exists: {params.message_id}")
            return existing_patch

        # 创建数据库记录，但不发送 Discord 消息
        expires_at = datetime.utcnow() + timedelta(
            hours=self.config.thread_subscription_timeout_hours
        )

        data = PatchSubscriptionData(
            message_id=params.message_id,
            subsystem_name=params.subsystem,
            platform_message_id="",  # 暂时为空
            platform_channel_id=self.config.platform_channel_id,
            subject=params.subject,
            author=params.author,
            url=params.url,
            expires_at=expires_at,
            series_message_id=params.series_message_id,
            patch_version=params.patch_version,
            patch_index=params.patch_index,
            patch_total=params.patch_total,
        )
        current_patch = await patch_subscription_service.create(data)
        logger.info(
            f"Saved PATCH {params.patch_index}/{params.patch_total} to database: {params.subject}"
        )
        return current_patch

    async def _update_existing_series_card(
        self,
        series_card: PatchSubscription,
        params: SeriesCardParams,
        session,
    ) -> None:
        """更新已存在的系列卡片

        Args:
            series_card: 系列卡片订阅对象
            params: 系列卡片参数
            session: 数据库会话
        """
        logger.info(
            f"Updating existing series card for {params.subject} "
            f"(version={params.patch_version}, {params.patch_index}/{params.patch_total})"
        )
        await self.update_series_card(series_card, session)

    async def _create_new_series_card(
        self,
        params: SeriesCardParams,
        current_patch: PatchSubscription,
        session,
    ) -> PatchSubscription:
        """创建新的系列卡片

        Args:
            params: 系列卡片参数
            current_patch: 当前 PATCH 订阅对象
            session: 数据库会话

        Returns:
            PATCH 订阅对象
        """
        logger.info(
            f"Creating new series card for {params.subject} "
            f"(version={params.patch_version}, {params.patch_index}/{params.patch_total})"
        )
        card_params = SubscriptionCardParams(
            subsystem=params.subsystem,
            message_id=params.message_id,
            subject=params.subject,
            author=params.author,
            url=params.url,
            series_message_id=params.series_message_id,
            patch_version=params.patch_version,
            patch_index=params.patch_index,
            patch_total=params.patch_total,
            series_info=params.series_info,
        )
        platform_message_id = await self._send_subscription_card(card_params, session)

        if platform_message_id and current_patch:
            # 更新当前 PATCH 的 platform_message_id
            current_patch.platform_message_id = platform_message_id
            await session.flush()
            logger.info(
                f"Series card created with platform_message_id: {platform_message_id}"
            )

        return current_patch

    async def update_series_card(
        self, series_card: PatchSubscription, session_or_patches
    ) -> None:
        """更新系列卡片，显示最新的 PATCH 列表

        Args:
            series_card: 系列卡片订阅对象
            session_or_patches: 数据库会话（从外部传入，避免嵌套）或 PATCH 列表
        """
        try:
            # 判断第二个参数是 session 还是 patches 列表
            if isinstance(session_or_patches, list):
                # 如果传入的是列表，直接使用
                patches = session_or_patches
            else:
                # 如果传入的是 session，查询获取该系列的所有 PATCH
                patches = await patch_subscription_service.get_series_patches(
                    series_card.series_message_id
                )

            # 更新 Discord 消息
            await update_discord_series_card(
                self.config, series_card, patches, self._format_patch_list_item
            )

        except (DiscordHTTPError, FormatPatchError) as e:
            logger.error(f"Failed to update series card: {e}", exc_info=True)
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Data error updating series card: {e}", exc_info=True)

    async def create_subscription_card(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        subsystem: str,
        message_id: str,
        subject: str,
        author: str,
        url: Optional[str] = None,
        series_message_id: Optional[str] = None,
        patch_version: Optional[str] = None,
        patch_index: Optional[int] = None,
        patch_total: Optional[int] = None,
        session=None,  # 可选的外部 session
    ) -> Optional[PatchSubscription]:
        """创建订阅卡片

        Args:
            subsystem: 子系统名称
            message_id: PATCH 的 message_id
            subject: PATCH 主题
            author: PATCH 作者
            url: PATCH 链接

        Returns:
            创建的 PatchSubscription 对象，失败返回 None
        """
        try:
            # 使用外部 session 或创建新的
            if session is None:
                async with self.database.get_db_session() as session_context:
                    return await self._create_subscription_card_internal(
                        subsystem,
                        message_id,
                        subject,
                        author,
                        url,
                        series_message_id,
                        patch_version,
                        patch_index,
                        patch_total,
                        session_context,
                    )
            else:
                return await self._create_subscription_card_internal(
                    subsystem,
                    message_id,
                    subject,
                    author,
                    url,
                    series_message_id,
                    patch_version,
                    patch_index,
                    patch_total,
                    session,
                )

        except (SQLAlchemyError, DiscordHTTPError, FormatPatchError) as e:
            logger.error(f"Failed to create subscription card: {e}", exc_info=True)
            return None
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Data error creating subscription card: {e}", exc_info=True)
            return None

    async def _create_subscription_card_internal(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        subsystem: str,
        message_id: str,
        subject: str,
        author: str,
        url: Optional[str],
        series_message_id: Optional[str],
        patch_version: Optional[str],
        patch_index: Optional[int],
        patch_total: Optional[int],
        session,
    ) -> Optional[PatchSubscription]:
        """创建订阅卡片的内部实现

        Args:
            subsystem: 子系统名称
            message_id: PATCH 的 message_id
            subject: PATCH 主题
            author: PATCH 作者
            url: PATCH 链接
            series_message_id: 系列 message_id
            patch_version: PATCH 版本
            patch_index: PATCH 索引
            patch_total: PATCH 总数
            session: 数据库会话

        Returns:
            创建的 PatchSubscription 对象，失败返回 None
        """
        # 构建卡片参数
        card_params = SubscriptionCardParams(
            subsystem=subsystem,
            message_id=message_id,
            subject=subject,
            author=author,
            url=url,
            series_message_id=series_message_id,
            patch_version=patch_version,
            patch_index=patch_index,
            patch_total=patch_total,
        )

        # 创建订阅卡片
        return await create_subscription_card_core(
            session,
            message_id,
            card_params,
            self._send_subscription_card,
            self.config.platform_channel_id,
            self.config.thread_subscription_timeout_hours,
        )

    async def _send_subscription_card(
        self, params: SubscriptionCardParams, session=None
    ) -> Optional[str]:
        """发送订阅卡片到 Discord（命令订阅模式）

        如果是系列 PATCH，会查询数据库中该系列的所有 PATCH 并显示目录。

        Args:
            params: 订阅卡片参数
            session: 可选的外部 session

        Returns:
            Discord 消息 ID，失败返回 None
        """
        try:
            if not self.config.discord_bot_token or not self.config.platform_channel_id:
                logger.error("Discord bot token or channel ID not configured")
                return None

            # 查询系列 PATCH
            series_patches = await get_series_patches(params, session)

            # 构建描述
            description = build_subscription_description(params, series_patches)

            # 构建并发送 embed
            return await send_discord_embed(self.config, params, description)

        except (DiscordHTTPError, FormatPatchError) as e:
            logger.error(f"Failed to send subscription card: {e}", exc_info=True)
            return None
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Data error sending subscription card: {e}", exc_info=True)
            return None

    async def send_series_patches_to_thread(  # pylint: disable=unused-argument
        self, thread_id: str, patches: list, subsystem: str
    ) -> None:
        """将系列的所有 PATCH 发送到 Thread

        Args:
            thread_id: Discord Thread ID
            patches: 系列的所有 PATCH 列表
            subsystem: 子系统名称
        """
        try:
            if not patches:
                return

            logger.info(f"Sending {len(patches)} patches to thread {thread_id}")

            # 逐个发送 PATCH 详情
            async with self.database.get_db_session() as session:
                for patch in patches:
                    await process_and_send_patch(
                        session,
                        thread_id,
                        patch,
                        self.send_message_to_thread,
                    )

            logger.info(f"Successfully sent all patches to thread {thread_id}")

        except (SQLAlchemyError, DiscordHTTPError, FormatPatchError) as e:
            logger.error(f"Failed to send series patches to thread: {e}", exc_info=True)
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(
                f"Data error sending series patches to thread: {e}", exc_info=True
            )

    async def create_discord_thread(
        self, thread_name: str, message_id: str
    ) -> Optional[str]:
        """创建 Discord Thread

        Args:
            thread_name: Thread 名称
            message_id: Discord 消息 ID（Thread 将从这条消息创建）

        Returns:
            Thread ID，失败返回 None
        """
        thread_id = await api_create_discord_thread(
            self.config, thread_name, message_id
        )
        if thread_id:
            return thread_id

        # 如果创建失败，尝试获取已存在的 Thread ID
        return await _handle_existing_thread_retrieval(self.config, message_id)

    async def check_thread_exists(self, thread_id: str) -> bool:
        """检查 Thread 是否真的存在于 Discord

        Args:
            thread_id: Discord Thread ID

        Returns:
            如果 Thread 存在返回 True，否则返回 False
        """
        return await api_check_thread_exists(self.config, thread_id)

    async def send_message_to_thread(
        self, thread_id: str, content: str, embed: Optional[Dict] = None
    ) -> bool:
        """发送消息到 Thread

        Args:
            thread_id: Thread ID
            content: 消息内容
            embed: 可选的 embed 字典

        Returns:
            成功返回 True，失败返回 False
        """
        return await api_send_message_to_thread(self.config, thread_id, content, embed)

    async def check_thread_pool_limit(self) -> bool:
        """检查 Thread 池是否已满

        Returns:
            如果未满返回 True，已满返回 False
        """
        try:
            active_count = await thread_service.count_active_threads()
            max_threads = self.config.thread_pool_max_size

            if active_count >= max_threads:
                logger.warning(
                    f"Thread pool is full: {active_count}/{max_threads} threads active"
                )
                return False

            logger.debug(
                f"Thread pool status: {active_count}/{max_threads} threads active"
            )
            return True

        except SQLAlchemyError as e:
            logger.error(
                f"Database error checking thread pool limit: {e}", exc_info=True
            )
            return False
        except (ValueError, AttributeError) as e:
            logger.error(f"Data error checking thread pool limit: {e}", exc_info=True)
            return False
