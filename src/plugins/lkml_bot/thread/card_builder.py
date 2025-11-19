"""卡片构建相关功能"""

from nonebot.log import logger

from lkml.feed.patch_parser import parse_patch_subject
from lkml.service.patch_subscription_service import patch_subscription_service

from .models import SimplePatch
from .params import SubscriptionCardParams
from .discord_api import truncate_description


def format_patch_list_item(patch, max_subject_length: int = 80) -> str:
    """格式化 PATCH 列表项

    Args:
        patch: Patch 对象（需要有 subject 和 url 属性）
        max_subject_length: 主题最大长度

    Returns:
        格式化后的字符串
    """
    subject = getattr(patch, "subject", "")
    subject_truncated = subject[:max_subject_length] if subject else ""

    url = getattr(patch, "url", None)
    if url:
        return f"[{subject_truncated}]({url})"
    return f"{subject_truncated}"


async def get_series_patches(params: SubscriptionCardParams, session) -> list:
    """获取系列 PATCH 列表

    Args:
        params: 订阅卡片参数
        session: 数据库会话

    Returns:
        系列 PATCH 列表
    """
    if not params.series_message_id or params.patch_total is None:
        return []

    if session:  # noqa: ARG001
        # 如果有异步session，使用 service 查询（session 参数保留以兼容现有接口）
        series_patches = await patch_subscription_service.get_series_patches(
            params.series_message_id
        )
        logger.info(
            f"Queried {len(series_patches)} patches from database for series {params.series_message_id}"
        )
        return series_patches

    if params.series_info and params.series_info.get("patches"):
        # 如果提供了series_info（来自同步版本），使用它
        logger.info(
            f"Using series_info with {len(params.series_info['patches'])} patches for series {params.series_message_id}"
        )
        series_patches = [SimplePatch(p) for p in params.series_info["patches"]]
        for i, p in enumerate(series_patches):
            logger.debug(
                f"  Patch {i}: [{p.patch_index}/{p.patch_total}] {p.subject[:50]}"
            )
        return series_patches

    logger.warning(
        f"No series_info or session provided for series {params.series_message_id}, "
        f"will only show current patch"
    )
    return []


def build_subscription_description(
    params: SubscriptionCardParams, series_patches: list
) -> str:
    """构建订阅卡片描述

    Args:
        params: 订阅卡片参数
        series_patches: 系列 PATCH 列表

    Returns:
        描述字符串
    """
    # 解析 PATCH 信息以优化显示
    patch_info = parse_patch_subject(params.subject)

    if series_patches:
        # 系列 PATCH 的 YAML 格式
        yaml_content = f"""```yaml
Message ID: {params.message_id}
Author: {params.author}
Subsystem: {params.subsystem}
Version: {params.patch_version or 'v1'}
Total Patches: {params.patch_total + 1}
Received: {len(series_patches)}/{params.patch_total + 1}
```"""
        description_parts = [yaml_content, "", "**Series:**"]

        # 显示系列中的所有 PATCH
        for patch in series_patches:
            description_parts.append(format_patch_list_item(patch))
    else:
        # 单个 PATCH 的 YAML 格式
        yaml_lines = [
            f"Author: {params.author}",
            f"Subsystem: {params.subsystem}",
        ]

        # 如果有版本信息，添加到 YAML
        if params.patch_version:
            yaml_lines.append(f"Version: {params.patch_version}")

        # 如果是系列的一部分（但不是 cover letter），添加索引信息
        if patch_info.is_patch and patch_info.total is not None:
            if patch_info.is_cover_letter:
                yaml_lines.append(f"Cover Letter: 0/{patch_info.total}")
            else:
                yaml_lines.append(f"Part: {patch_info.index}/{patch_info.total}")

        yaml_content = "```yaml\n" + "\n".join(yaml_lines) + "\n```"
        description_parts = [yaml_content]

    # 添加提示信息
    description_parts.extend(
        [
            "💡 **Want to create a dedicated Thread to receive follow-up replies?**",
            "Subscribe using the command:",
            f"```bash\n/watch {params.message_id}\n```",
            f"or: ```bash\n/w {params.message_id}\n```",
        ]
    )

    description = "\n".join(description_parts)
    return truncate_description(description)
