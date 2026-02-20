"""Feishu 线程概览渲染器

只负责渲染 Thread Overview 为 Feishu 卡片格式。
发送由客户端负责。
"""

from lkml.service.types import ThreadOverviewData

from ..helpers import build_author_display
from ..types import FeishuRenderedThreadNotification


class FeishuThreadOverviewRenderer:  # pylint: disable=too-few-public-methods
    """Feishu 平台 ThreadOverview 渲染器（只负责渲染，不负责发送）"""

    def __init__(self, config):
        self.config = config  # 目前未使用，保留以便未来扩展

    def render_create_notification(  # pylint: disable=too-many-locals
        self, overview_data: ThreadOverviewData
    ) -> FeishuRenderedThreadNotification:
        """渲染 Thread 创建通知卡片（不发送）

        Args:
            overview_data: 线程概览数据

        Returns:
            FeishuRenderedThreadNotification 渲染结果
        """
        pc = overview_data.patch_card
        subject = pc.subject[:200]
        patch_card_link = pc.url or ""

        # 基本信息
        date_value = pc.received_at or pc.expires_at
        date_str = date_value.strftime("%Y-%m-%d %H:%M UTC") if date_value else ""
        author_str = build_author_display(pc.author, pc.author_email)

        base_content_lines = [
            f"• **Subsystem** ：{pc.subsystem_name}",
            f"• **Author** ：{author_str}",
        ]
        if date_str:
            base_content_lines.append(f"• **Date** ：{date_str}")
        base_content = "\n".join(base_content_lines)

        # Series list
        lines = []
        if pc.series_patches:
            for sp in pc.series_patches:
                subj = sp.subject
                link = sp.url or ""
                lines.append(f"  - [{subj}]({link}) ")
        sub_md = "\n".join(lines) if lines else ""

        elements = [
            # 基本信息块
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
                                "content": base_content,
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
        ]

        # Series 列表块（有时才显示）
        if sub_md:
            elements.append(
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
                                    "content": ("• **Series** ：\n" + sub_md),
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
            )

        # 查看详情按钮
        elements.append(
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
                        "default_url": patch_card_link or "",
                        "pc_url": "",
                        "ios_url": "",
                        "android_url": "",
                    }
                ],
                "margin": "4px 0px 4px 0px",
            }
        )

        card = {
            "msg_type": "interactive",
            "card": {
                "schema": "2.0",
                "config": {"update_multi": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"Thread Create: {subject}",
                    },
                    "subtitle": {"tag": "plain_text", "content": ""},
                    "text_tag_list": [
                        {
                            "tag": "text_tag",
                            "text": {
                                "tag": "plain_text",
                                "content": "Thread 已创建，有新回复时将自动推送",
                            },
                            "color": "green",
                        }
                    ],
                    "template": "green",
                    "padding": "12px 8px 12px 8px",
                },
                "body": {
                    "direction": "vertical",
                    "elements": elements,
                },
            },
        }

        return FeishuRenderedThreadNotification(card=card)

    def render_update_notification(  # pylint: disable=too-many-locals
        self,
        overview_data: ThreadOverviewData,
        reply_summary: str = "",
        reply_author: str = "",
        reply_author_email: str = "",
        reply_date: str = "",
        reply_url: str = "",
        reply_content: str = "",
    ) -> FeishuRenderedThreadNotification:
        """渲染 Thread 更新通知卡片（不发送）

        Args:
            overview_data: 线程概览数据
            reply_summary: Reply 的 AI 摘要（可选）
            reply_author: 回复者名称
            reply_author_email: 回复者邮箱
            reply_date: 回复日期字符串
            reply_url: 回复在 lore.kernel.org 上的链接
            reply_content: 回复的原始内容（用于 fallback 摘要）

        Returns:
            FeishuRenderedThreadNotification 渲染结果
        """
        from ..helpers import build_content_excerpt

        pc = overview_data.patch_card
        subj = pc.subject[:200]
        patch_link = pc.url or ""

        # 使用调用方传入的回复信息，fallback 到层级树查找
        if reply_author or reply_author_email:
            author_display = build_author_display(reply_author, reply_author_email)
            latest_url = ""
        else:
            author_display, latest_url = self._find_latest_reply_info(overview_data)

        # 基本信息
        info_lines = []
        if author_display:
            info_lines.append(f"• **Reply From** ：{author_display}")
        if reply_date:
            info_lines.append(f"• **Date** ：{reply_date}")

        info_content = "\n".join(info_lines)

        # 摘要：AI summary 优先，fallback 到 content excerpt
        summary_text = reply_summary
        if not summary_text and reply_content:
            summary_text = build_content_excerpt(reply_content, quote_prefix="")

        # 按钮优先跳转到 reply_url，fallback 到层级树 latest_url，再 fallback 到 patch
        button_url = reply_url or latest_url or patch_link

        elements = [
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
                                "content": info_content,
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
        ]

        # 摘要块（AI summary 或 content excerpt，有内容时才显示）
        if summary_text:
            elements.append(
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
                                    "content": summary_text,
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
            )

        elements.append(
            {
                "tag": "button",
                "text": {
                    "tag": "plain_text",
                    "content": "查看最新回复",
                },
                "type": "primary_filled",
                "width": "fill",
                "behaviors": [
                    {
                        "type": "open_url",
                        "default_url": button_url,
                        "pc_url": "",
                        "ios_url": "",
                        "android_url": "",
                    }
                ],
                "margin": "4px 0px 4px 0px",
            },
        )

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
                    "elements": elements,
                },
            },
        }

        return FeishuRenderedThreadNotification(card=card)

    @staticmethod
    def _find_latest_reply_info(
        overview_data: ThreadOverviewData,
    ) -> tuple[str, str]:
        """从层级树中找到最新回复者名称和 URL

        Returns:
            (author, url) 元组，找不到时返回 ("", "")
        """
        if not overview_data.root:
            return "", ""

        # DFS 遍历树，找到最新的 reply 节点（按 received_at 排序）
        from lkml.service.types import ThreadNode

        latest_author = ""
        latest_url = ""
        latest_time = None

        def _walk(node: ThreadNode):
            nonlocal latest_author, latest_url, latest_time
            if node.node_type == "reply":
                msg = node.message
                if msg.received_at and (
                    latest_time is None or msg.received_at > latest_time
                ):
                    latest_time = msg.received_at
                    latest_author = msg.author or ""
                    latest_url = msg.url or ""
            for child in node.children:
                _walk(child)

        _walk(overview_data.root)
        return latest_author, latest_url
