"""Discord 消息适配器

负责将邮件列表更新消息发送到 Discord 平台。
"""

try:
    import httpx
except ImportError:
    httpx = None

from nonebot.log import logger
from sqlalchemy.exc import SQLAlchemyError

from lkml.feed import SubsystemUpdate, FeedEntry
from .discord_reply_embed import (
    build_description,
    build_content_fields,
    build_reply_embed,
    clean_content,
    clean_subject,
    extract_content,
    format_date,
)
from .discord_reply_helpers import (
    find_patch_subscription,
    find_thread_for_patch,
    get_email_message,
)

from ..config import get_config
from ..renders import DiscordRenderer
from ..thread import DiscordThreadManager
from ..thread.exceptions import DiscordHTTPError, FormatPatchError
from .message_adapter import MessageAdapter


class DiscordAdapter(MessageAdapter):
    """Discord 消息适配器

    实现 MessageAdapter 接口，通过 Discord 发送消息。
    支持 Thread 模式：PATCH 发送订阅卡片，REPLY 发送到对应 Thread。
    """

    def __init__(self, database=None):
        """初始化 Discord 适配器

        Args:
            database: 数据库实例
        """
        self.config = get_config()
        self.renderer = DiscordRenderer()
        self.database = database
        self.thread_manager = None
        if database:
            self.thread_manager = DiscordThreadManager(database)

    async def send_subsystem_update(
        self, subsystem: str, update_data: SubsystemUpdate
    ) -> None:
        """通过 Discord 发送消息

        Args:
            subsystem: 子系统名称
            update_data: 更新数据
        """
        try:
            # 如果没有更新，直接返回
            if update_data.new_count == 0 and update_data.reply_count == 0:
                logger.info(f"No updates for {subsystem}")
                return

            # 如果配置了 Thread 模式，使用 Thread 模式处理
            if self.thread_manager and self.config.discord_bot_token:
                await self._send_with_thread_mode(subsystem, update_data)
            else:
                # 否则使用传统的 Webhook 模式
                await self._send_with_webhook_mode(subsystem, update_data)

        except (RuntimeError, ValueError, AttributeError, OSError) as e:
            logger.error(f"Failed to send message to Discord: {e}", exc_info=True)
            # 不抛出异常，避免影响主流程

    async def _send_with_webhook_mode(
        self, subsystem: str, update_data: SubsystemUpdate
    ) -> None:
        """使用 Webhook 模式发送消息（传统模式）

        Args:
            subsystem: 子系统名称
            update_data: 更新数据
        """
        webhook_url = self.config.discord_webhook_url
        if not webhook_url:
            logger.debug("Discord webhook URL not configured, skipping Discord send")
            return

        if not httpx:
            logger.error("httpx is not installed, cannot send Discord webhook messages")
            return

        # 使用渲染器构建 Embed 数据
        embed = self.renderer.render(subsystem, update_data)

        # 准备发送的数据
        data = {"embeds": [embed]}

        # 发送 webhook 请求
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=data)
            if response.status_code in {200, 204}:
                logger.info(
                    f"Successfully sent message via Discord webhook for {subsystem}"
                )
            else:
                logger.error(
                    f"Failed to send Discord webhook message: "
                    f"status {response.status_code}, {response.text}"
                )

    async def _send_with_thread_mode(
        self, subsystem: str, update_data: SubsystemUpdate
    ) -> None:
        """使用 Thread 模式发送消息

        注意：PATCH 订阅卡片由 CardBuilderService 独立构建，这里只处理 REPLY

        Args:
            subsystem: 子系统名称
            update_data: 更新数据
        """
        for entry in update_data.entries:
            if entry.content.is_reply:
                # 这是一个 REPLY 消息，发送到对应的 Thread
                await self._handle_reply_message(subsystem, entry)
            elif entry.content.is_patch:
                # PATCH 消息已通过 CardBuilderService 处理，这里只记录
                logger.debug(
                    f"PATCH message saved to database, card will be built by CardBuilderService: {entry.subject}"
                )
            else:
                # 其他消息，使用传统方式发送
                logger.debug(f"Non-PATCH non-REPLY message: {entry.subject}")

    # _handle_patch_message 方法已移除
    # PATCH 订阅卡片现在由 CardBuilderService 统一构建

    async def _handle_reply_message(  # pylint: disable=unused-argument
        self, subsystem: str, entry: FeedEntry
    ) -> None:
        """处理 REPLY 消息，发送到对应的 Thread

        Args:
            subsystem: 子系统名称
            entry: Feed 条目
        """
        try:
            if not self.database:
                logger.warning("Database not configured, cannot handle REPLY message")
                return

            # 从 entry 中获取 in_reply_to_header
            in_reply_to = entry.metadata.in_reply_to if entry.metadata else None

            if not in_reply_to:
                logger.debug(f"No in_reply_to found for REPLY: {entry.subject}")
                return

            # 查找对应的 PATCH 订阅和 Thread
            async with self.database.get_db_session() as session:
                patch_sub, thread, email_msg = await _find_reply_targets(
                    session, entry, in_reply_to
                )

                if not patch_sub or not thread:
                    return

                # 构建并发送 REPLY 消息
                await _send_reply_to_thread(
                    self, entry, patch_sub, in_reply_to, thread, email_msg
                )

        except (SQLAlchemyError, DiscordHTTPError, FormatPatchError) as e:
            logger.error(f"Failed to handle REPLY message: {e}", exc_info=True)
        except (ValueError, KeyError, AttributeError) as e:
            logger.error(f"Data error handling REPLY message: {e}", exc_info=True)

    def _build_reply_embed(  # pylint: disable=unused-argument
        self, entry: FeedEntry, parent_patch, in_reply_to: str, email_msg=None
    ) -> dict:
        """构建 REPLY 消息的 Embed

        Args:
            entry: Feed 条目
            parent_patch: 父 PATCH 对象
            in_reply_to: In-Reply-To Message-ID
            email_msg: EmailMessage 对象（可选）

        Returns:
            Discord Embed 字典
        """
        # 清理 subject
        subject = clean_subject(entry.subject)

        # 获取日期
        date_str = format_date(email_msg)

        # 获取并清理内容
        content = extract_content(entry, email_msg)
        content_clean = clean_content(content) if content else ""

        # 构建描述
        description = build_description(entry, date_str)

        # 构建字段
        fields = build_content_fields(content_clean, entry.url)

        # 构建 Embed
        return build_reply_embed(
            entry, in_reply_to, email_msg, subject, description, fields
        )


async def _find_reply_targets(session, entry, in_reply_to: str):
    """查找 REPLY 消息的目标

    Args:
        session: 数据库会话
        entry: Feed 条目
        in_reply_to: 回复的 message_id

    Returns:
        (patch_sub, thread, email_msg) 元组
    """
    # 查找 PATCH 订阅，传入 REPLY 的 subject 以便找到对应的子 PATCH
    patch_sub = await find_patch_subscription(
        session, in_reply_to, reply_subject=entry.subject
    )

    if not patch_sub:
        logger.debug(
            f"No PATCH found for REPLY: {entry.subject}, in_reply_to: {in_reply_to}"
        )
        return None, None, None

    # 查找 Thread
    thread = await find_thread_for_patch(patch_sub)

    if not thread or not thread.is_active:
        logger.debug(
            f"No active Thread found for REPLY: {entry.subject}, "
            f"in_reply_to: {in_reply_to}"
        )
        return None, None, None

    # 查询 EmailMessage 获取完整信息
    email_msg = await get_email_message(session, entry)

    return patch_sub, thread, email_msg


async def _send_reply_to_thread(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    adapter, entry, patch_sub, in_reply_to: str, thread, email_msg
) -> None:
    """发送 REPLY 消息到 Thread

    Args:
        adapter: DiscordAdapter 实例
        entry: Feed 条目
        patch_sub: PATCH 订阅对象
        in_reply_to: 回复的 message_id
        thread: Thread 对象
        email_msg: EmailMessage 对象
    """
    # 构建 REPLY 消息的 Embed
    embed = adapter._build_reply_embed(  # pylint: disable=protected-access
        entry, patch_sub, in_reply_to, email_msg
    )

    # 发送到 Thread
    success = await adapter.thread_manager.send_message_to_thread(
        thread_id=thread.thread_id,
        content="",
        embed=embed,
    )

    if success:
        logger.info(f"Sent REPLY to Thread: {entry.subject}")
    else:
        logger.error(f"Failed to send REPLY to Thread: {entry.subject}")
