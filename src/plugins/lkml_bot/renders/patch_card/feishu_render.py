"""Feishu 平台渲染器"""

from typing import Optional
import httpx

from lkml.service import PatchCard


class FeishuPatchCardRenderer:  # pylint: disable=too-few-public-methods
    """Feishu 平台 PatchCard 渲染器"""

    def __init__(self, config):
        self.config = config

    async def render_and_send(self, patch_card: PatchCard) -> Optional[str]:
        """渲染并发送 PatchCard 到 Feishu 平台

        Args:
            patch_card: 待渲染的 PatchCard 对象

        Returns:
            发送成功的消息 ID 列表（如果有），否则 None
        """
        try:
            url = getattr(self.config, "feishu_webhook_url", "")
            if not url:
                return None

            header_title = patch_card.subject[:200]
            date_str = (
                patch_card.expires_at.strftime("%Y-%m-%d %H:%M UTC")
                if patch_card.expires_at
                else ""
            )
            author_str = patch_card.author or "Unknown"

            subpatch_lines = []
            if patch_card.series_patches:
                for p in patch_card.series_patches:
                    subj = p.subject
                    link = p.url or ""
                    subpatch_lines.append(f"  - [{subj}]({link}) ")
            subpatch_md = (
                "\n".join(subpatch_lines) if subpatch_lines else "No Series Patch"
            )

            card = {
                "msg_type": "interactive",
                "card": {
                    "schema": "2.0",
                    "config": {"update_multi": True},
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": f"{header_title}",
                        },
                        "subtitle": {"tag": "plain_text", "content": ""},
                        "text_tag_list": [
                            {
                                "tag": "text_tag",
                                "text": {"tag": "plain_text", "content": "新提交"},
                                "color": "blue",
                            }
                        ],
                        "template": "blue",
                        "padding": "12px 8px 12px 8px",
                    },
                    "body": {
                        "direction": "vertical",
                        "elements": [
                            {
                                "tag": "column_set",
                                "flex_mode": "stretch",
                                "horizontal_spacing": "8px",
                                "horizontal_align": "left",
                                "columns": [
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "background_style": "blue-50",
                                        "elements": [
                                            {
                                                "tag": "markdown",
                                                "content": (
                                                    f"• **Subsystem** ：{patch_card.subsystem_name}\n"
                                                    + f"• **Date** ：{date_str}\n"
                                                    + f"• **Author** ：{author_str}"
                                                ),
                                                "text_align": "left",
                                                "text_size": "normal",
                                            }
                                        ],
                                        "padding": "12px 12px 12px 12px",
                                        "vertical_spacing": "8px",
                                        "horizontal_align": "left",
                                        "vertical_align": "top",
                                        "weight": 1,
                                    }
                                ],
                                "margin": "0px 0px 0px 0px",
                            },
                            {
                                "tag": "column_set",
                                "flex_mode": "stretch",
                                "horizontal_spacing": "8px",
                                "horizontal_align": "left",
                                "columns": [
                                    {
                                        "tag": "column",
                                        "width": "weighted",
                                        "background_style": "grey-50",
                                        "elements": [
                                            {
                                                "tag": "markdown",
                                                "content": (
                                                    "• **Sub Patches** ：\n"
                                                    + subpatch_md
                                                ),
                                                "text_align": "left",
                                                "text_size": "normal",
                                            }
                                        ],
                                        "padding": "12px 12px 12px 12px",
                                        "vertical_spacing": "8px",
                                        "horizontal_align": "left",
                                        "vertical_align": "top",
                                        "weight": 1,
                                    }
                                ],
                                "margin": "0px 0px 0px 0px",
                            },
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "查看补丁详情",
                                },
                                "type": "primary_filled",
                                "width": "fill",
                                "behaviors": [
                                    {
                                        "type": "open_url",
                                        "default_url": patch_card.url or "",
                                        "pc_url": "",
                                        "ios_url": "",
                                        "android_url": "",
                                    }
                                ],
                                "margin": "4px 0px 4px 0px",
                            },
                        ],
                    },
                },
            }

            async with httpx.AsyncClient() as client:
                await client.post(url, json=card, timeout=30.0)

            return None
        except (httpx.HTTPError, ValueError, AttributeError):
            return None
