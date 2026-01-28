"""Feed 消息服务

处理 feed 消息到达时的逻辑：
1. PATCH 消息：如果是 PATCH 且 patch_cards 中不存在，则新建
2. REPLY 消息：查找对应的 PATCH 卡片，如果存在且 Thread 已创建，则更新 Thread 内容

架构说明：
- Plugins 层只负责渲染（PatchCardRenderer, ThreadOverviewRenderer）
- Service 层负责业务逻辑（PatchCardService, ThreadService, FeedMessageService）
"""

# pylint: disable=too-many-lines

import logging
from typing import Optional, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.repo import (
    FeedMessageData,
    FeedMessageRepository,
    PatchCardRepository,
)
from .types import (
    FeedMessage as ServiceFeedMessage,
    PatchCard,
    PatchThread,
    SeriesPatchInfo,
    ThreadOverviewData,
)
from .patch_card_service import PatchCardService

logger = logging.getLogger(__name__)


@runtime_checkable
class ReplyNotificationSender(Protocol):
    """Protocol for reply notification sender."""

    async def send_reply_notification(self, payload: dict) -> None:
        """Send a reply notification."""


class FeedMessageService:
    """Feed 消息服务

    封装 Feed 消息处理的业务逻辑，包括 PATCH 和 REPLY 消息的处理。
    """

    def __init__(
        self,
        patch_card_sender=None,
        thread_sender=None,
    ):
        """初始化处理器

        Args:
            patch_card_sender: PatchCard 多平台发送服务
            thread_sender: Thread 多平台发送服务
        """
        # 通过统一的多平台发送服务发送（由 Plugins 层注入）
        self.patch_card_sender = patch_card_sender
        self.thread_sender = thread_sender

    # ========== 公共方法 ==========

    async def process_email_message(
        self,
        session: AsyncSession,
        feed_message: FeedMessageData,
        classification,
    ) -> None:
        """处理单个 FeedMessage

        根据消息类型（PATCH/REPLY）执行相应的处理逻辑。

        Args:
            session: 数据库会话
            feed_message: Feed 消息对象
            classification: 消息分类结果（MessageClassification）
        """
        if classification.is_patch:
            await self._process_patch_message(session, feed_message, classification)
        elif classification.is_reply:
            await self._process_reply_message(session, feed_message)

    # ========== 私有方法 ==========

    async def _process_patch_message(
        self,
        session: AsyncSession,
        feed_message: FeedMessageData,
        classification,
    ) -> None:
        """处理 PATCH 消息

        如果是 PATCH 且 patch_cards 中不存在，则新建。

        Args:
            session: 数据库会话
            feed_message: Feed 消息对象（必须是 PATCH）
            classification: 消息分类结果
        """
        if not feed_message.message_id_header:
            logger.warning(
                f"PATCH message has no message_id_header: {feed_message.subject[:100]}"
            )
            return

        # 检查是否已存在 PATCH 卡片
        from ..db.database import get_patch_card_service

        async with get_patch_card_service() as patch_card_service:
            if await patch_card_service.find_by_message_id_header(
                feed_message.message_id_header
            ):
                logger.debug(
                    f"PATCH card already exists: {feed_message.message_id_header}, "
                    f"subject: {feed_message.subject[:50]}"
                )
                return

        # 创建新的 PATCH 卡片并发送到 Discord
        try:
            # 检查渲染器是否可用
            if not self.patch_card_sender:
                logger.debug(
                    f"PatchCard renderer not configured, skipping PATCH card creation: "
                    f"{feed_message.message_id_header}"
                )
                return

            # 从分类结果中获取 PATCH 信息
            patch_info = classification.patch_info
            # Series PATCH 处理：只发送 Cover Letter，子 PATCH 不单独创建卡片
            if classification.series_message_id and patch_info:
                if not (
                    patch_info.is_cover_letter
                    or feed_message.is_cover_letter
                    or (patch_info.index is not None and patch_info.index == 0)
                ):
                    # 子 PATCH (1/n, 2/n, ...) 只保存在 feed_message 表中
                    logger.debug(
                        f"Skipping patch_card creation for series sub-PATCH: "
                        f"{feed_message.message_id_header}, "
                        f"subject: {feed_message.subject[:50]}, "
                        f"patch_index: {patch_info.index}/{patch_info.total}. "
                        f"Sub-patch is stored in feed_message table only."
                    )
                    return

            # 准备 Service 层的 FeedMessage 对象
            service_feed_message = self._convert_to_service_feed_message(
                feed_message, patch_info, classification.series_message_id
            )

            # 应用过滤规则（在默认 filter 基础上）
            should_create, matched_filters = await self._should_create_patch_card(
                session, service_feed_message, patch_info
            )
            if not should_create:
                logger.debug(
                    f"Patch card creation filtered out by rules: {feed_message.message_id_header}, "
                    f"subject: {feed_message.subject[:50]}"
                )
                return

            # 将匹配的过滤规则名称传递给 service_feed_message（用于后续渲染）
            if matched_filters:
                service_feed_message.matched_filters = matched_filters

            # 检查 PATCH 卡片是否已存在
            async with get_patch_card_service() as service:
                patch_card = await service.get_patch_card_with_series_data(
                    feed_message.message_id_header
                )

            auto_watch_enabled = await self._is_auto_watch_enabled(
                session, matched_filters
            )

            # PATCH 卡片不存在，准备创建
            if not patch_card:
                patch_card = await self._create_and_send_patch_card(  # pylint: disable=too-many-arguments
                    session,
                    feed_message,
                    service_feed_message,
                    patch_info,
                    classification.series_message_id,
                )

            if patch_card:
                logger.info(
                    f"Created PATCH card and sent: {feed_message.message_id_header}, "
                    f"subject: {feed_message.subject[:50]}, "
                    f"is_series={classification.is_series_patch}, "
                    f"platform_message_id={patch_card.platform_message_id}"
                )
                if auto_watch_enabled and not patch_card.has_thread:
                    await self._auto_watch_patch_card(session, patch_card)
            else:
                logger.warning(
                    f"Failed to create PATCH card for: {feed_message.message_id_header}, "
                    f"subject: {feed_message.subject[:50]}"
                )

        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to create PATCH card from feed message: {e}",
                exc_info=True,
            )

    async def _create_and_send_patch_card(  # pylint: disable=too-many-arguments
        self,
        session: AsyncSession,
        feed_message: FeedMessageData,
        service_feed_message,
        patch_info,
        series_message_id: Optional[str],
    ):
        """创建并发送 PATCH 卡片到各平台"""
        # 如果是 Cover Letter，查询数据库中已有的子 PATCH
        series_patches = await self._get_series_patches_for_cover_letter(  # pylint: disable=too-many-arguments
            session, feed_message, service_feed_message, series_message_id, patch_info
        )

        # 构建用于渲染和发送的 PatchCard（Service 层统一构建数据）
        temp_patch_card = (
            self._build_temp_patch_card(  # pylint: disable=too-many-arguments
                feed_message,
                service_feed_message,
                series_message_id,
                patch_info,
                series_patches,
            )
        )

        # 使用 PatchCard 发送服务（如果已注入）
        platform_message_id = None
        platform_channel_id = ""

        if self.patch_card_sender is not None:
            try:
                platform_message_id, platform_channel_id = (
                    await self.patch_card_sender.send_patch_card(temp_patch_card)
                )
            except (RuntimeError, ValueError, AttributeError) as e:
                logger.error(
                    "Failed to send PATCH card via patch_card_sender: %s",
                    e,
                    exc_info=True,
                )
                platform_message_id = None
                platform_channel_id = ""

        if not platform_message_id:
            logger.warning(
                "Failed to send PATCH card via any sender requiring message id: %s",
                feed_message.message_id_header,
            )
            return None

        # 保存到数据库
        return await self._save_patch_card_to_database(
            session, service_feed_message, platform_message_id, platform_channel_id
        )

    async def _get_series_patches_for_cover_letter(  # pylint: disable=too-many-arguments
        self, session, feed_message, service_feed_message, series_message_id, patch_info
    ):
        """获取 Cover Letter 的子 PATCH 列表"""
        if not (service_feed_message.is_cover_letter and series_message_id):
            return []

        feed_msg_repo = FeedMessageRepository(session)
        sub_patches = await feed_msg_repo.find_by_series_message_id(series_message_id)

        series_patches = [
            SeriesPatchInfo(
                subject=p.subject,
                url=p.url or "",
                message_id=p.message_id_header,
                patch_index=p.patch_index or 0,
                patch_total=patch_info.total or 0 if patch_info else 0,
            )
            for p in sub_patches
            if p.patch_index != 0
            and p.message_id_header != feed_message.message_id_header
        ]
        series_patches.sort(key=lambda x: x.patch_index)
        return series_patches

    def _build_temp_patch_card(  # pylint: disable=too-many-arguments
        self,
        feed_message,
        service_feed_message,
        series_message_id,
        patch_info,
        series_patches,
    ):
        """构建临时 PatchCard 对象用于渲染"""
        # PatchCard 已在模块顶部导入，不需要重新导入

        return PatchCard(
            message_id_header=feed_message.message_id_header,
            subsystem_name=feed_message.subsystem_name,
            platform_message_id="",
            platform_channel_id="",
            subject=feed_message.subject,
            author=feed_message.author,
            url=feed_message.url,
            expires_at=feed_message.received_at,
            is_series_patch=service_feed_message.is_series_patch,
            series_message_id=series_message_id,
            patch_version=patch_info.version if patch_info else None,
            patch_index=patch_info.index if patch_info else None,
            patch_total=patch_info.total if patch_info else None,
            has_thread=False,
            is_cover_letter=service_feed_message.is_cover_letter,
            series_patches=series_patches,
            matched_filters=service_feed_message.matched_filters,
        )

    async def _save_patch_card_to_database(
        self, session, service_feed_message, platform_message_id, platform_channel_id
    ):
        """保存 PATCH 卡片到数据库"""
        patch_card_repo = PatchCardRepository(session)
        feed_message_repo = FeedMessageRepository(session)
        patch_card_service = PatchCardService(patch_card_repo, feed_message_repo)

        return await patch_card_service.create_patch_card(
            feed_message=service_feed_message,
            platform_message_id=platform_message_id,
            platform_channel_id=platform_channel_id,
            timeout_hours=24,
        )

    async def _process_reply_message(
        self, session: AsyncSession, feed_message: FeedMessageData
    ) -> None:
        """处理 REPLY 消息

        查找对应的 PATCH 卡片，如果存在且 Thread 已创建，则更新 Thread 内容。

        Args:
            session: 数据库会话
            feed_message: Feed 消息对象（必须是 REPLY）
        """
        if not feed_message.in_reply_to_header:
            logger.debug(
                f"REPLY message has no in_reply_to_header: {feed_message.subject[:100]}"
            )
            return

        # 查找回复对应的 PATCH 卡片和 Thread
        patch_card, thread = await self._find_patch_card_and_thread_for_reply(
            session, feed_message
        )

        # 已建立并激活 Thread：保持现状，仅更新 Thread
        if patch_card and thread and thread.is_active:
            # 更新 Thread：如果是多消息模式，只更新对应的子 PATCH 消息
            # 传入 session 以确保能查询到新保存的 REPLY（还在同一事务中）
            await self._update_thread_with_reply(
                session, thread, patch_card, feed_message.in_reply_to_header
            )
            return

        # Reply Perspective：未建立 Thread 或无卡片时的补充处理
        await self._process_reply_perspective(session, feed_message, patch_card)

    async def _find_patch_card_and_thread_for_reply(
        self, session: AsyncSession, feed_message: FeedMessageData
    ):
        """查找回复对应的 PATCH 卡片和 Thread"""

        # 创建 Repository 和 Service 实例（使用辅助函数以减少重复代码）
        from .helpers import create_repositories_and_services

        (
            _,
            _,
            _,
            patch_card_service,
            thread_service,
        ) = create_repositories_and_services(session)

        # 查找 PATCH 卡片
        patch_card = await self._find_patch_card_for_reply(
            session, patch_card_service, feed_message
        )

        if not patch_card:
            return None, None

        # 如果是系列 PATCH，需要填充 series_patches 数据（用于后续匹配子 PATCH）
        if patch_card.is_series_patch and patch_card.series_message_id:
            patch_card = await patch_card_service.get_patch_card_with_series_data(
                patch_card.message_id_header
            )
            if not patch_card:
                return None, None

        # 查找 Thread
        thread = await thread_service.find_by_message_id_header(
            patch_card.message_id_header
        )

        if not thread or not thread.is_active:
            logger.debug(
                f"No active Thread found for REPLY: {feed_message.subject[:100]}, "
                f"message_id_header: {patch_card.message_id_header}"
            )
            return patch_card, None

        return patch_card, thread

    async def _find_patch_card_for_reply(
        self,
        session: AsyncSession,
        patch_card_service: PatchCardService,
        feed_message: FeedMessageData,
    ):
        """查找回复对应的 PATCH 卡片

        查找逻辑：
        1. 直接匹配 in_reply_to_header（可能是 Cover Letter 或单 PATCH）
        2. 如果没找到，可能是回复子 PATCH 的情况，通过子 PATCH 的 series_message_id 查找 Cover Letter
        """
        # 1. 直接匹配 in_reply_to_header（可能是 Cover Letter 或单 PATCH）
        patch_card = await patch_card_service.find_by_message_id_header(
            feed_message.in_reply_to_header
        )

        # 2. 如果没找到，可能是回复子 PATCH 的情况
        if not patch_card:
            feed_message_repo = FeedMessageRepository(session)
            sub_patch_feed_message = await feed_message_repo.find_by_message_id_header(
                feed_message.in_reply_to_header
            )

            # 如果找到了子 PATCH 的 feed_message，通过它的 series_message_id 查找 Cover Letter
            if sub_patch_feed_message and sub_patch_feed_message.series_message_id:
                patch_card = await patch_card_service.find_series_patch_card(
                    sub_patch_feed_message.series_message_id
                )
                if patch_card:
                    logger.debug(
                        f"Found Cover Letter via sub-patch series_message_id: "
                        f"in_reply_to={feed_message.in_reply_to_header}, "
                        f"series_message_id={sub_patch_feed_message.series_message_id}"
                    )

        if not patch_card:
            logger.debug(
                f"No PATCH card found for REPLY: {feed_message.subject[:100]}, "
                f"in_reply_to: {feed_message.in_reply_to_header}"
            )

        return patch_card

    async def _process_reply_perspective(
        self,
        session: AsyncSession,
        reply_message: FeedMessageData,
        existing_patch_card: Optional[PatchCard],
    ) -> None:
        """Reply Perspective 处理逻辑

        规则：
        - 如果 Reply 对应的 Patch 已建立 Thread（has_thread=True），不做额外处理
        - 如果 Patch Card 不存在：根据过滤规则创建并推送 Patch Card，然后自动 watch
        - 如果 Patch Card 已存在但未 watch：自动 watch
        """
        try:
            patch_context = await self._build_reply_patch_context(
                session, reply_message
            )
            if not patch_context:
                return

            target_patch, patch_info, service_feed_message, matched_filters = (
                patch_context
            )

            if matched_filters:
                service_feed_message.matched_filters = matched_filters

            patch_card = await self._get_existing_patch_card_for_reply(
                session, existing_patch_card, target_patch
            )

            if patch_card and patch_card.has_thread:
                return

            # Patch Card 不存在：创建并推送
            if not patch_card:
                created_card = await self._create_and_send_patch_card(  # pylint: disable=too-many-arguments
                    session,
                    target_patch,
                    service_feed_message,
                    patch_info,
                    target_patch.series_message_id,
                )
                if created_card:
                    logger.info(
                        "Created PATCH card via reply perspective: %s",
                        target_patch.message_id_header,
                    )
                patch_card = created_card

            if not patch_card:
                return

            await self._send_reply_notice(reply_message, target_patch)

            if await self._is_auto_watch_enabled(session, matched_filters):
                await self._auto_watch_patch_card(session, patch_card)
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                "Failed to process reply perspective: %s",
                e,
                exc_info=True,
            )

    async def _build_reply_patch_context(
        self, session: AsyncSession, reply_message: FeedMessageData
    ) -> Optional[tuple[FeedMessageData, object, ServiceFeedMessage, list[str]]]:
        """构建 Reply 视角处理上下文（目标 Patch + 过滤信息）"""
        target_patch = await self._resolve_patch_feed_message_for_reply(
            session, reply_message
        )
        if not target_patch or not target_patch.subject:
            return None

        from ..feed.feed_message_classifier import parse_patch_subject

        patch_info = parse_patch_subject(target_patch.subject)
        if not patch_info or not patch_info.is_patch:
            return None

        # Reply 视角过滤：使用 reply 内容判断是否命中规则
        filter_message = self._convert_to_service_feed_message(
            reply_message, patch_info, target_patch.series_message_id
        )
        should_create, matched_filters = await self._should_create_patch_card(
            session, filter_message, patch_info
        )
        if not should_create:
            return None
        if not matched_filters:
            # Reply 视角必须命中过滤规则才触发后续处理
            return None

        # Patch Card 创建数据仍使用 Patch 本身
        service_feed_message = self._convert_to_service_feed_message(
            target_patch, patch_info, target_patch.series_message_id
        )

        return target_patch, patch_info, service_feed_message, matched_filters

    async def _get_existing_patch_card_for_reply(
        self,
        session: AsyncSession,
        existing_patch_card: Optional[PatchCard],
        target_patch: FeedMessageData,
    ) -> Optional[PatchCard]:
        """获取 Reply 对应的 PatchCard"""
        if existing_patch_card:
            return existing_patch_card

        from .helpers import create_repositories_and_services

        (_, _, _, patch_card_service, _) = create_repositories_and_services(session)
        return await self._find_patch_card_for_feed_message(
            patch_card_service, target_patch
        )

    async def _is_auto_watch_enabled(
        self, session: AsyncSession, matched_filters: Optional[list[str]]
    ) -> bool:
        """判断是否允许自动 watch（需要命中过滤规则且全局开关开启）"""
        if not matched_filters:
            return False
        from ..db.repo import FilterConfigRepository

        config_repo = FilterConfigRepository(session)
        return await config_repo.get_auto_watch_enabled()

    async def _send_reply_notice(
        self, reply_message: FeedMessageData, root_patch: FeedMessageData
    ) -> None:
        """发送 Reply 视角通知消息"""
        if not self.patch_card_sender:
            return

        if not isinstance(self.patch_card_sender, ReplyNotificationSender):
            return

        payload = {
            "reply_author": reply_message.author_email or reply_message.author,
            "reply_subject": reply_message.subject or "",
            "reply_url": reply_message.url,
            "reply_subsystem": reply_message.subsystem_name or "",
            "reply_date": (
                reply_message.received_at.strftime("%Y-%m-%d %H:%M:%S")
                if reply_message.received_at
                else ""
            ),
            "root_subject": root_patch.subject or "",
            "root_url": root_patch.url,
        }
        await self.patch_card_sender.send_reply_notification(payload)

    async def _resolve_patch_feed_message_for_reply(
        self, session: AsyncSession, reply_message: FeedMessageData
    ) -> Optional[FeedMessageData]:
        """解析 Reply 对应的 Patch feed_message（Cover Letter 或 Single Patch）"""
        if not reply_message.in_reply_to_header:
            return None

        feed_message_repo = FeedMessageRepository(session)
        from .thread_service import _extract_message_id_from_header

        async def find_patch_in_chain(
            message_id_header: str,
        ) -> Optional[FeedMessageData]:
            current_raw = message_id_header
            visited: set[str] = set()
            depth = 0

            while current_raw and depth < 30:
                current_id = _extract_message_id_from_header(current_raw)
                if not current_id or current_id in visited:
                    break
                visited.add(current_id)

                msg = await feed_message_repo.find_by_message_id_header(current_id)
                if not msg:
                    return None

                if msg.is_patch and not msg.is_reply:
                    if (
                        msg.is_series_patch
                        and not msg.is_cover_letter
                        and msg.series_message_id
                    ):
                        cover = await feed_message_repo.find_by_message_id_header(
                            msg.series_message_id
                        )
                        if cover and cover.is_patch and not cover.is_reply:
                            return cover
                    return msg

                current_raw = msg.in_reply_to_header
                depth += 1
            return None

        parent = await feed_message_repo.find_by_message_id_header(
            _extract_message_id_from_header(reply_message.in_reply_to_header)
            or reply_message.in_reply_to_header
        )

        # 优先沿 in-reply-to 链找到真正的 PATCH
        resolved = await find_patch_in_chain(reply_message.in_reply_to_header)
        if resolved:
            return resolved

        # 回复到 REPLY：尝试通过 series_message_id 找到根 PATCH
        series_id = reply_message.series_message_id or (
            parent.series_message_id if parent else None
        )
        if series_id:
            root = await feed_message_repo.find_by_message_id_header(series_id)
            if root and root.is_patch and not root.is_reply:
                return root

        return None

    async def _find_patch_card_for_feed_message(
        self, patch_card_service: PatchCardService, patch_message: FeedMessageData
    ) -> Optional[PatchCard]:
        """根据 Patch feed_message 查找 PatchCard"""
        patch_card = await patch_card_service.find_by_message_id_header(
            patch_message.message_id_header
        )
        if patch_card:
            return patch_card
        if patch_message.series_message_id:
            return await patch_card_service.find_series_patch_card(
                patch_message.series_message_id
            )
        return None

    async def _auto_watch_patch_card(
        self, session: AsyncSession, patch_card: PatchCard
    ) -> None:
        """自动创建 Thread 并标记 watch 状态"""
        if not self.thread_sender:
            logger.debug("Thread sender not configured, skip auto watch")
            return

        if not patch_card.platform_message_id:
            logger.warning(
                "Patch card has no platform_message_id, cannot create thread: %s",
                patch_card.message_id_header,
            )
            return

        from .helpers import create_repositories_and_services

        (_, _, _, patch_card_service, thread_service) = (
            create_repositories_and_services(session)
        )

        existing_thread = await thread_service.find_by_message_id_header(
            patch_card.message_id_header
        )
        if existing_thread and existing_thread.is_active:
            if not patch_card.has_thread:
                await patch_card_service.mark_as_has_thread(
                    patch_card.message_id_header
                )
            return

        # 刷新 session，确保刚创建的 patch_card 在同一个 session 中可见
        await session.flush()

        # 使用同一个 session 的 patch_card_service，确保能看到刚创建的 patch_card
        overview_data = await thread_service.prepare_thread_overview_data(
            patch_card.message_id_header, patch_card_service=patch_card_service
        )
        if not overview_data:
            logger.warning(
                "Failed to prepare thread overview data for auto watch: %s",
                patch_card.message_id_header,
            )
            return

        thread_name = patch_card.subject[:100]
        thread_id, sub_patch_messages = (
            await self.thread_sender.create_thread_and_send_overview(
                thread_name, patch_card.platform_message_id, overview_data
            )
        )

        if not thread_id:
            logger.warning(
                "Failed to create thread for auto watch: %s",
                patch_card.message_id_header,
            )
            return

        await thread_service.create(
            patch_card.message_id_header,
            thread_id,
            thread_name,
        )
        if sub_patch_messages:
            await thread_service.update_sub_patch_messages(
                thread_id, sub_patch_messages
            )

        await patch_card_service.mark_as_has_thread(patch_card.message_id_header)

    async def _send_thread_update_notification(
        self, thread: PatchThread, patch_card: PatchCard
    ):
        """发送 Thread 更新通知到频道

        Args:
            thread: Thread 对象
            patch_card: PATCH 卡片对象
        """
        try:
            # 使用新的 thread_sender（如果可用）
            if self.thread_sender:
                channel_id = patch_card.platform_channel_id
                if not channel_id:
                    logger.warning(
                        f"Channel ID not available, cannot send thread update notification "
                        f"for thread {thread.thread_id}"
                    )
                    return

                success = await self.thread_sender.send_thread_update_notification(
                    channel_id,
                    thread.thread_id,
                    patch_card.platform_message_id,
                )

                if success:
                    logger.info(
                        f"Sent thread update notification for thread {thread.thread_id} "
                        f"in channel {channel_id}"
                    )
                else:
                    logger.warning(
                        f"Failed to send thread update notification for thread {thread.thread_id}"
                    )
                return
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to send thread update notification: {e}",
                exc_info=True,
            )

    async def _update_thread_with_reply(
        self,
        session: AsyncSession,
        thread: PatchThread,
        patch_card: PatchCard,
        in_reply_to_header: str,
    ):
        """当 Reply 到达时，更新 Thread

        根据是否配置了 ``thread_sender``，选择对应的更新实现。

        Args:
            session: 数据库会话（用于查询，确保能查询到新保存的 REPLY）
            thread: Thread 对象
            patch_card: PATCH 卡片对象
            in_reply_to_header: Reply 的 in_reply_to 头部
        """
        if self.thread_sender:
            await self._update_thread_with_reply_via_thread_sender(
                session, thread, patch_card, in_reply_to_header
            )
            return

        await self._update_thread_with_reply_via_renderers(
            session, thread, patch_card, in_reply_to_header
        )

    async def _update_thread_with_reply_via_thread_sender(
        self,
        session: AsyncSession,
        thread: PatchThread,
        patch_card: PatchCard,
        in_reply_to_header: str,
    ) -> None:
        """当 Reply 到达时，使用 ``thread_sender`` 更新 Thread。"""
        try:
            target_patch, target_patch_index = await self._find_target_patch_for_reply(
                patch_card, in_reply_to_header
            )

            if not target_patch or target_patch_index is None:
                logger.debug(
                    "Could not find target patch for reply: %s", in_reply_to_header
                )
                return

            message_id = self._get_thread_overview_message_id(thread)

            if not message_id:
                logger.warning(
                    "No overview message_id found for thread %s",
                    thread.thread_id,
                )
                return

            overview_data = await self._prepare_thread_overview_data(
                session, patch_card.message_id_header
            )

            if not overview_data:
                return

            success = await self.thread_sender.update_thread_overview(
                thread.thread_id,
                message_id,
                overview_data,
            )

            if success:
                logger.info(
                    "Updated thread overview message in thread %s",
                    thread.thread_id,
                )
                await self._send_thread_update_notification(thread, patch_card)
            else:
                logger.warning(
                    "Failed to update thread overview message in thread %s",
                    thread.thread_id,
                )
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                "Failed to update thread with reply: %s",
                e,
                exc_info=True,
            )

    async def _update_thread_with_reply_via_renderers(
        self,
        session: AsyncSession,
        thread: PatchThread,
        patch_card: PatchCard,
        in_reply_to_header: str,
    ) -> None:
        """当 Reply 到达时，通过渲染器列表更新 Thread。"""
        try:
            target_patch, target_patch_index = await self._find_target_patch_for_reply(
                patch_card, in_reply_to_header
            )

            if not target_patch or target_patch_index is None:
                logger.debug(
                    "Could not find target patch for reply: %s", in_reply_to_header
                )
                return

            message_id = self._get_thread_overview_message_id(thread)

            if not message_id:
                logger.warning(
                    "No overview message_id found for thread %s",
                    thread.thread_id,
                )
                return

            overview_data = await self._prepare_thread_overview_data(
                session, patch_card.message_id_header
            )

            if not overview_data:
                return

            successes: list[bool] = []
            for renderer in self.thread_overview_renderers:
                try:
                    result = await renderer.update_sub_patch_message(
                        thread.thread_id,
                        message_id,
                        overview_data,
                    )
                    successes.append(bool(result))
                except (RuntimeError, ValueError, AttributeError) as e:
                    successes.append(False)
                    logger.error(
                        "Failed to update patch [%s] message in thread %s: %s",
                        target_patch_index,
                        thread.thread_id,
                        e,
                        exc_info=True,
                    )

            if any(successes):
                logger.info(
                    "Updated thread overview message in thread %s",
                    thread.thread_id,
                )
                await self._send_thread_update_notification(thread, patch_card)
            else:
                logger.warning(
                    "Failed to update thread overview message in thread %s",
                    thread.thread_id,
                )
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                "Failed to update thread with reply: %s",
                e,
                exc_info=True,
            )

    async def _find_target_patch_for_reply(
        self, patch_card: PatchCard, in_reply_to_header: str
    ) -> tuple:
        """找到 REPLY 对应的 Patch

        Args:
            patch_card: PATCH 卡片对象
            in_reply_to_header: Reply 的 in_reply_to 头部

        Returns:
            (target_patch, target_patch_index) 元组，如果找不到返回 (None, None)
        """
        from .helpers import build_single_patch_info
        from .thread_service import _extract_message_id_from_header

        # 提取 in_reply_to 中的 message_id
        in_reply_to = _extract_message_id_from_header(in_reply_to_header)
        if not in_reply_to:
            return None, None

        target_patch = None
        target_patch_index = None

        # 单 Patch：直接匹配
        if not patch_card.is_series_patch:
            if patch_card.message_id_header in in_reply_to:
                target_patch = build_single_patch_info(patch_card)
                target_patch_index = 1
            return target_patch, target_patch_index

        # Series Patch：首先检查是否回复 Cover Letter
        if patch_card.message_id_header in in_reply_to:
            # 回复 Cover Letter，查找 Cover Letter 对应的 patch
            if patch_card.series_patches:
                for patch in patch_card.series_patches:
                    if patch.patch_index == 0:  # Cover Letter
                        target_patch = patch
                        target_patch_index = 0
                        break
            # 如果找不到 Cover Letter 的 patch，使用 patch_card 构建一个
            # 这种情况不应该发生，但为了健壮性，我们处理它
            if not target_patch:
                logger.warning(
                    f"Cover Letter patch not found in series_patches for {patch_card.message_id_header}, "
                    f"using patch_card to build patch info"
                )
                target_patch = SeriesPatchInfo(
                    subject=patch_card.subject,
                    patch_index=0,
                    patch_total=patch_card.patch_total or 1,
                    message_id=patch_card.message_id_header,
                    url=patch_card.url or "",
                )
                target_patch_index = 0

            return target_patch, target_patch_index

        # Series Patch：查找匹配的子 Patch
        if patch_card.series_patches:
            for patch in patch_card.series_patches:
                if patch.patch_index == 0:  # 跳过 Cover Letter
                    continue
                if patch.message_id and patch.message_id in in_reply_to:
                    target_patch = patch
                    target_patch_index = patch.patch_index
                    break

        return target_patch, target_patch_index

    def _get_thread_overview_message_id(self, thread: PatchThread) -> Optional[str]:
        """获取 Thread Overview 的消息 ID。"""
        sub_patch_messages = thread.sub_patch_messages or {}
        if sub_patch_messages:
            return next(iter(sub_patch_messages.values()))
        return None

    async def _prepare_thread_overview_data(
        self, session: AsyncSession, message_id_header: str
    ) -> Optional[ThreadOverviewData]:
        """准备 Thread Overview 数据（用于更新单条概览消息）。"""
        from .helpers import create_repositories_and_services

        try:
            (
                _,
                _,
                _,
                _,
                thread_service,
            ) = create_repositories_and_services(session)
            return await thread_service.prepare_thread_overview_data(message_id_header)
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.error(
                f"Failed to prepare thread overview data: {e}",
                exc_info=True,
            )
            return None

    async def _should_create_patch_card(
        self,
        session: AsyncSession,
        service_feed_message: ServiceFeedMessage,
        patch_info,
    ) -> tuple[bool, list[str]]:
        """判断是否应该创建 Patch Card（应用过滤规则）

        Args:
            session: 数据库会话
            service_feed_message: Service 层的 FeedMessage 对象
            patch_info: PATCH 信息

        Returns:
            (should_create, matched_filter_names) 元组
            - should_create: True 表示应该创建，False 表示不应该创建
            - matched_filter_names: 匹配的过滤规则名称列表
        """
        try:
            from ..db.repo import (
                PatchCardFilterRepository as LocalPatchCardFilterRepository,
                PatchCardRepository as LocalPatchCardRepository,
                FilterConfigRepository,
                FeedMessageRepository as LocalFeedMessageRepository,
            )
            from .patch_card_filter_service import PatchCardFilterService

            filter_repo = LocalPatchCardFilterRepository(session)
            patch_card_repo = LocalPatchCardRepository(session)
            filter_config_repo = FilterConfigRepository(session)
            feed_message_repo = LocalFeedMessageRepository(session)
            filter_service = PatchCardFilterService(
                filter_repo, patch_card_repo, filter_config_repo, feed_message_repo
            )

            return await filter_service.should_create_patch_card(
                service_feed_message, patch_info
            )
        except (RuntimeError, ValueError, AttributeError) as e:
            logger.warning(
                f"Failed to check filter rules, allowing creation by default: {e}",
                exc_info=True,
            )
            # 如果过滤检查失败，默认允许创建（保持原有行为）
            return (True, [])

    def _convert_to_service_feed_message(
        self, feed_message, patch_info, series_message_id
    ) -> ServiceFeedMessage:
        """转换为 Service 层的 FeedMessage 对象

        Args:
            feed_message: Repository 层的 FeedMessageData
            patch_info: PATCH 信息
            series_message_id: Series 消息 ID

        Returns:
            Service 层的 FeedMessage 对象
        """
        is_series = (
            series_message_id is not None
            and (patch_info.total is not None and patch_info.total > 1)
            if patch_info
            else False
        )

        return ServiceFeedMessage(
            subsystem_name=feed_message.subsystem_name,
            message_id_header=feed_message.message_id_header,
            subject=feed_message.subject,
            author=feed_message.author,
            author_email=feed_message.author_email,
            message_id=feed_message.message_id,
            in_reply_to_header=feed_message.in_reply_to_header,
            content=feed_message.content,
            url=feed_message.url,
            received_at=feed_message.received_at,
            is_patch=feed_message.is_patch,
            is_reply=feed_message.is_reply,
            is_series_patch=is_series,
            patch_version=patch_info.version if patch_info else None,
            patch_index=patch_info.index if patch_info else None,
            patch_total=patch_info.total if patch_info else None,
            is_cover_letter=patch_info.is_cover_letter if patch_info else False,
            series_message_id=series_message_id,
        )
