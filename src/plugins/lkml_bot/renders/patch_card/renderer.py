"""PatchCard 渲染器

Plugins 层渲染器：只负责将 PatchCard 渲染成 Discord 格式。
所有业务逻辑由 Service 层处理，发送由客户端处理。
"""

from lkml.service import PatchCard

from ...client.discord_params import PatchCardParams
from ..helpers import build_author_display, build_cc_summary, build_content_excerpt
from ..types import DiscordRenderedPatchCard


class PatchCardRenderer:
    """PatchCard 渲染器

    职责：
    1. 将 PatchCard 渲染成 Discord Embed 格式
    2. 仅此而已

    不做：
    - 数据查询
    - 业务逻辑判断
    - 数据库操作
    - 发送消息（由客户端负责）
    """

    def __init__(self, config):
        """初始化渲染器

        Args:
            config: 配置对象
        """
        self.config = config

    def render(self, patch_card: PatchCard) -> DiscordRenderedPatchCard:
        """渲染 PatchCard 为 Discord 格式（不发送）

        Args:
            patch_card: PatchCard 数据（由 Service 层准备好，包含 series_patches）

        Returns:
            DiscordRenderedPatchCard 渲染结果
        """
        # 构建描述
        description = self._build_description(patch_card)

        # 构建标题（如果匹配了 filter，添加高亮标记）
        title_prefix = "⭐ " if patch_card.matched_filters else "📨 "
        title = f"{title_prefix}{patch_card.subject[:200]}"

        # 构建 Embed 参数
        params = PatchCardParams(
            subsystem=patch_card.subsystem_name,
            message_id_header=patch_card.message_id_header,
            subject=patch_card.subject,
            author=patch_card.author,
            received_at=patch_card.received_at or patch_card.expires_at,
            url=patch_card.url,
            series_message_id=patch_card.series_message_id,
            patch_version=patch_card.patch_version,
            patch_index=patch_card.patch_index,
            patch_total=patch_card.patch_total,
        )

        # 如果匹配了 filter，使用高亮颜色（金色）
        embed_color = 0xFFD700 if patch_card.matched_filters else 0x5865F2

        return DiscordRenderedPatchCard(
            params=params,
            description=description,
            embed_color=embed_color,
            title=title,
        )

    def _build_description(  # pylint: disable=too-many-branches
        self, patch_card: PatchCard
    ) -> str:
        """构建 Embed 描述（纯渲染逻辑）

        Args:
            patch_card: PatchCard 数据

        Returns:
            描述字符串
        """
        lines = []

        # 基本信息（YAML 格式）
        lines.append("```yaml")
        lines.append(f"Subsystem: {patch_card.subsystem_name}")
        date_value = patch_card.received_at or patch_card.expires_at
        if date_value:
            lines.append(f"Date: {date_value.strftime('%Y-%m-%d %H:%M:%S')}")

        author_str = build_author_display(patch_card.author, patch_card.author_email)
        lines.append(f"Author: {author_str}")

        # Version（有时才显示）
        if patch_card.patch_version:
            lines.append(f"Version: {patch_card.patch_version}")

        # 如果是系列，显示总数和已接收数
        if patch_card.is_series_patch and patch_card.patch_total:
            received = (
                len(patch_card.series_patches) if patch_card.series_patches else 0
            )
            lines.append(f"Total Patches: {patch_card.patch_total}")
            lines.append(f"Received: {received}/{patch_card.patch_total}")

        lines.append("```")

        # Content excerpt（优先使用 AI 摘要，fallback 到规则截断）
        if patch_card.summary:
            lines.append(f"> {patch_card.summary}")
        elif patch_card.content:
            excerpt = build_content_excerpt(patch_card.content)
            if excerpt:
                lines.append(excerpt)

        # CC 列表（缩略显示）
        if patch_card.to_cc_list:
            cc_str = build_cc_summary(patch_card.to_cc_list)
            if cc_str:
                lines.append(cc_str)

        # 匹配的 filter 名称
        if patch_card.matched_filters:
            filters_str = ", ".join(patch_card.matched_filters)
            lines.append(f"**Matched Filters:** {filters_str}")

        # 系列 PATCH 列表
        if patch_card.series_patches:
            lines.append("**Series:**\n")
            for patch in patch_card.series_patches:
                subject = patch.subject
                url = patch.url
                # 截断主题长度
                subject_truncated = (
                    subject[:80] + "..." if len(subject) > 80 else subject
                )
                if url:
                    lines.append(f"[{subject_truncated}]({url})")
                else:
                    lines.append(subject_truncated)

        # 添加 watch 命令提示
        lines.append(
            "\nCreate a dedicated Thread to receive follow-up replies using the command:"
        )
        lines.append("```bash")
        lines.append(f"/watch {patch_card.message_id_header}")
        lines.append("```")

        return "\n".join(lines)

    def render_reply_notification(self, payload: dict):
        """渲染 Reply 通知为 Discord 格式（不发送）

        Args:
            payload: Reply 通知数据

        Returns:
            DiscordRenderedReplyNotification 渲染结果
        """
        from ..types import DiscordRenderedReplyNotification

        title = self._build_reply_title(payload)
        description = self._build_reply_description(payload)

        return DiscordRenderedReplyNotification(
            title=title,
            description=description,
            url=payload.get("reply_url"),
            embed_color=0x5865F2,
        )

    def _build_reply_title(self, payload: dict) -> str:
        """构建 Reply 通知标题"""
        reply_subject = payload.get("reply_subject") or ""
        reply_author = payload.get("reply_author") or "unknown"
        if reply_subject:
            return f"\U0001f4ac {reply_subject}"
        return f"\U0001f4ac [Reply from {reply_author}]"

    def _build_reply_description(self, payload: dict) -> str:
        """构建 Reply 通知描述"""
        reply_author = payload.get("reply_author") or "unknown"
        reply_author_name = payload.get("reply_author_name") or ""
        reply_subsystem = payload.get("reply_subsystem") or ""
        reply_date = payload.get("reply_date") or ""
        reply_content = payload.get("reply_content") or ""
        root_subject = payload.get("root_subject") or ""
        root_url = payload.get("root_url")

        author_display = build_author_display(reply_author_name, reply_author)

        lines = []

        # 信息框（YAML 格式）
        lines.append("```yaml")
        if reply_subsystem:
            lines.append(f"Subsystem: {reply_subsystem}")
        if reply_date:
            lines.append(f"Date: {reply_date}")
        lines.append(f"Author: {author_display}")
        lines.append("```")

        # Reply content（优先使用 AI 摘要，fallback 到规则截断）
        reply_summary = payload.get("reply_summary")
        if reply_summary:
            lines.append(f"> {reply_summary}")
        elif reply_content:
            excerpt = build_content_excerpt(reply_content)
            if excerpt:
                lines.append(excerpt)

        # In reply to（措辞优化）
        if root_subject:
            lines.append("**In reply to:**")
            if root_url:
                lines.append(f"[{root_subject}]({root_url})")
            else:
                lines.append(root_subject)

        return "\n".join(lines)
