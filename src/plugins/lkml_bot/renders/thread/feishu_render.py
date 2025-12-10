"""Feishu 线程概览渲染器"""

from typing import Dict, Optional

import httpx

from lkml.service.types import SubPatchOverviewData, ThreadOverviewData


class FeishuThreadOverviewRenderer:  # pylint: disable=too-few-public-methods
    """Feishu 平台 ThreadOverview 渲染器"""

    def __init__(self, config):
        self.config = config

    async def render_and_send(  # pylint: disable=unused-argument
        self, thread_id: str, overview_data: ThreadOverviewData
    ) -> Dict[int, str]:
        """渲染并发送 ThreadOverview 到 Feishu 平台

        Args:
            thread_id: 线程 ID
            overview_data: 线程概览数据

        Returns:
            发送成功的消息 ID 映射（如果有），否则空字典
        """
        try:
            url = getattr(self.config, "feishu_webhook_url", "")
            if not url:
                return {}

            subject = overview_data.patch_card.subject[:200]

            lines = []
            if overview_data.sub_patch_overviews:
                for sp in overview_data.sub_patch_overviews:
                    subj = sp.patch.subject
                    link = sp.patch.url or ""
                    lines.append(f"  - [{subj}]({link}) ")
            sub_md = "\n".join(lines) if lines else ""

            card = {
                "msg_type": "interactive",
                "card": {
                    "schema": "2.0",
                    "config": {"update_multi": True},
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": f"Thread Reply: {subject}",
                        },
                        "subtitle": {"tag": "plain_text", "content": ""},
                        "text_tag_list": [
                            {
                                "tag": "text_tag",
                                "text": {"tag": "plain_text", "content": "新回复"},
                                "color": "green",
                            }
                        ],
                        "template": "green",
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
                                        "background_style": "grey-50",
                                        "elements": [
                                            {
                                                "tag": "markdown",
                                                "content": (
                                                    "• **Sub Patches** ：\n" + sub_md
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
                            }
                        ],
                    },
                },
            }

            async with httpx.AsyncClient() as client:
                await client.post(url, json=card, timeout=30.0)

            return {}
        except (httpx.HTTPError, ValueError, AttributeError):
            return {}

    async def update_sub_patch_message(  # pylint: disable=unused-argument
        self, thread_id: str, message_id: str, sub_overview: SubPatchOverviewData
    ) -> Optional[bool]:
        """更新子补丁消息

        Args:
            thread_id: 线程 ID
            message_id: 消息 ID
            sub_overview: 子补丁概览数据

        Returns:
            更新成功返回 True，否则 None
        """
        try:
            url = getattr(self.config, "feishu_webhook_url", "")
            if not url:
                return None

            subj = sub_overview.patch.subject[:200]
            link = sub_overview.patch.url or ""

            card = {
                "msg_type": "interactive",
                "card": {
                    "schema": "2.0",
                    "config": {"update_multi": True},
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": f"Thread Reply: {subj}",
                        },
                        "subtitle": {"tag": "plain_text", "content": ""},
                        "text_tag_list": [
                            {
                                "tag": "text_tag",
                                "text": {"tag": "plain_text", "content": "有回复"},
                                "color": "green",
                            }
                        ],
                        "template": "green",
                        "padding": "12px 8px 12px 8px",
                    },
                    "body": {
                        "direction": "vertical",
                        "elements": [
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
                                        "default_url": link or "",
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

            return True
        except (httpx.HTTPError, ValueError, AttributeError):
            return None
