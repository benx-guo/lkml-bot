"""多平台发送服务（Patch Card）

负责协调将 PatchCard 发送到多个平台：
- Discord：创建订阅卡片（用于后续 Thread 功能）
- Feishu：发送通知卡片

Service 层只关心“有一个 PatchCard 要发送”，以及“用于持久化的主平台消息 ID
和频道 ID”（目前选择 Discord 作为主平台），具体多平台细节由本模块处理。
"""

from typing import Optional, Tuple

from nonebot.log import logger

from lkml.service import PatchCard

from .client.discord_client import DiscordClient
from .client.discord_channel import send_channel_embed
from .client.feishu_client import FeishuClient
from .renders.patch_card.renderer import PatchCardRenderer
from .renders.patch_card.feishu_render import FeishuPatchCardRenderer


class MultiPlatformPatchCardSender:  # pylint: disable=too-few-public-methods
    """PatchCard 多平台发送服务

    当前实现：
    - Discord：渲染并发送订阅卡片，返回消息 ID + 频道 ID
    - Feishu：渲染并发送卡片（如果配置了 webhook），忽略消息 ID
    """

    def __init__(
        self,
        discord_client: DiscordClient,
        discord_renderer: PatchCardRenderer,
        feishu_client: FeishuClient,
        feishu_renderer: FeishuPatchCardRenderer,
    ):
        self.discord_client = discord_client
        self.discord_renderer = discord_renderer
        self.feishu_client = feishu_client
        self.feishu_renderer = feishu_renderer

    async def send_patch_card(
        self, patch_card: PatchCard
    ) -> Tuple[Optional[str], Optional[str]]:
        """发送 PatchCard 到各个平台

        Args:
            patch_card: PatchCard 渲染数据

        Returns:
            (platform_message_id, platform_channel_id)
            - 当前选择 Discord 作为主平台：返回 Discord 消息 ID 和频道 ID
            - 如果 Discord 发送失败，则返回 (None, None)
        """
        platform_message_id: Optional[str] = None
        platform_channel_id: Optional[str] = None

        # 1) Discord：渲染并发送
        try:
            discord_rendered = self.discord_renderer.render(patch_card)
            platform_message_id = await self.discord_client.send_patch_card(
                discord_rendered
            )
            if platform_message_id:
                # Discord 频道 ID 从配置中获取
                channel_id = getattr(
                    getattr(self.discord_client, "config", None),
                    "platform_channel_id",
                    "",
                )
                platform_channel_id = str(channel_id) if channel_id is not None else ""
                logger.info(
                    "Sent PATCH card to Discord: message_id=%s, channel_id=%s",
                    platform_message_id,
                    platform_channel_id,
                )
            else:
                logger.warning("Failed to send PATCH card to Discord")
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Error sending PATCH card to Discord: %s", e, exc_info=True)

        # 2) Feishu：渲染并发送
        try:
            feishu_rendered = self.feishu_renderer.render(patch_card)
            await self.feishu_client.send_patch_card(feishu_rendered)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning(f"Error sending PATCH card to Feishu: {e}", exc_info=True)

        return platform_message_id, platform_channel_id

    async def send_reply_notification(self, payload: dict) -> None:
        """发送 Reply 视角通知消息到各平台"""
        # 1) Discord：发送 embed 到频道
        try:
            channel_id = getattr(
                getattr(self.discord_client, "config", None),
                "platform_channel_id",
                "",
            )
            if not channel_id:
                logger.warning(
                    "Discord channel ID not configured for reply notification"
                )
            else:
                # 使用 Discord renderer 渲染
                discord_rendered = self.discord_renderer.render_reply_notification(
                    payload
                )
                message_id = await send_channel_embed(
                    self.discord_client.config,
                    discord_rendered.title,
                    discord_rendered.description,
                    url=discord_rendered.url,
                    color=discord_rendered.embed_color,
                )
                if message_id:
                    logger.info("Sent reply notification to Discord: %s", message_id)
                else:
                    logger.warning("Failed to send reply notification to Discord")
        except Exception as e:  # pylint: disable=broad-except
            logger.error(
                "Error sending reply notification to Discord: %s", e, exc_info=True
            )

        # 2) Feishu：发送卡片消息
        try:
            # 使用 Feishu renderer 渲染
            feishu_rendered = self.feishu_renderer.render_reply_notification(payload)
            # render_reply_notification 返回的 card 已经包含完整结构，直接发送
            success = await self.feishu_client.send_webhook_payload(
                feishu_rendered.card, "reply notification"
            )
            if not success:
                logger.warning("Reply notification not sent to Feishu")
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("Error sending reply notification to Feishu: %s", e)
