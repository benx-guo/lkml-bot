"""Discord API 调用相关功能"""

from typing import Dict, List, Optional

import httpx
from nonebot.log import logger

from lkml.feed.patch_parser import parse_patch_subject

from .exceptions import DiscordHTTPError, FormatPatchError
from .params import SubscriptionCardParams

# Discord embed description 限制为 4096 字符
DISCORD_EMBED_DESCRIPTION_MAX_LENGTH = 4096


def truncate_description(description: str) -> str:
    """截断描述以符合 Discord embed 限制

    Args:
        description: 原始描述

    Returns:
        截断后的描述
    """
    if len(description) > DISCORD_EMBED_DESCRIPTION_MAX_LENGTH:
        logger.warning(
            f"Description too long ({len(description)} chars), truncating to {DISCORD_EMBED_DESCRIPTION_MAX_LENGTH}"
        )
        description = description[:4093] + "..."
    return description


async def send_discord_embed(
    config, params: SubscriptionCardParams, description: str
) -> Optional[str]:
    """发送 Discord embed 消息

    Args:
        config: 配置对象
        params: 订阅卡片参数
        description: embed 描述

    Returns:
        Discord 消息 ID，失败返回 None
    """
    # 构建标题
    title = f"📨 {params.subject[:200]}"

    # 构建订阅卡片内容
    embed = {
        "title": title,
        "description": description,
        "color": 0x5865F2,  # Discord 蓝色
        "footer": {
            "text": "Will be automatically deleted if no one subscribes within 24 hours"
        },
    }

    if params.url:
        embed["url"] = params.url

    # 发送到 Discord
    headers = {
        "Authorization": f"Bot {config.discord_bot_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://discord.com/api/v10/channels/{config.platform_channel_id}/messages",
            json={"embeds": [embed]},
            headers=headers,
            timeout=30.0,
        )

        if response.status_code in {200, 201}:
            result = response.json()
            platform_message_id = result.get("id")
            logger.info(f"Sent subscription card, message ID: {platform_message_id}")
            return platform_message_id
        logger.error(
            f"Failed to send subscription card: {response.status_code}, {response.text}"
        )
        return None


def _format_patch_list(patches: list, format_patch_list_item_func) -> List[str]:
    """格式化 PATCH 列表

    Args:
        patches: PATCH 列表
        format_patch_list_item_func: 格式化函数

    Returns:
        格式化后的 PATCH 列表
    """
    patch_list = []
    for patch in patches:
        try:
            patch_list.append(format_patch_list_item_func(patch))
        except (ValueError, AttributeError, KeyError) as e:
            logger.warning(f"Failed to format patch list item: {e}, patch: {patch}")
            continue
        except Exception as e:
            raise FormatPatchError(f"Unexpected error formatting patch: {e}") from e
    return patch_list


def _build_series_description(series_card, patch_info, patch_list: List[str]) -> str:
    """构建系列描述

    Args:
        series_card: 系列卡片订阅对象
        patch_info: 解析后的 patch 信息
        patch_list: 格式化后的 PATCH 列表

    Returns:
        描述字符串
    """
    yaml_content = f"""```yaml
Message ID: {series_card.message_id}
Author: {series_card.author}
Subsystem: {series_card.subsystem_name}
Version: {patch_info.version or 'v1'}
Total Patches: {patch_info.total + 1}
Received: {len(patch_list)}/{patch_info.total + 1}
```"""

    description_parts = [
        yaml_content,
        "**Series:**",
        "",
    ]
    description_parts.extend(patch_list)
    description_parts.extend(
        [
            "",
            "💡 **Want to create a dedicated Thread to receive follow-up replies?**",
            "Subscribe using the command:",
            f"```bash\n/watch {series_card.message_id}\n```",
            f"or: ```bash\n/w {series_card.message_id}\n```",
        ]
    )

    description = "\n".join(description_parts)
    return truncate_description(description)


def _build_series_embed(series_card, description: str) -> Dict:
    """构建系列 embed

    Args:
        series_card: 系列卡片订阅对象
        description: 描述字符串

    Returns:
        embed 字典
    """
    title = f"📨 {series_card.subject[:120]}"
    embed = {
        "title": title,
        "description": description,
        "color": 0x5865F2,
        "footer": {
            "text": "Will be automatically deleted if no one subscribes within 24 hours"
        },
    }

    if series_card.url:
        embed["url"] = series_card.url

    return embed


async def _update_discord_message(config, series_card, embed: Dict) -> None:
    """更新 Discord 消息

    Args:
        config: 配置对象
        series_card: 系列卡片订阅对象
        embed: embed 字典

    Raises:
        DiscordHTTPError: 当 HTTP 请求失败时
        httpx.HTTPError: 当网络请求失败时
    """
    headers = {
        "Authorization": f"Bot {config.discord_bot_token}",
        "Content-Type": "application/json",
    }

    message_data = {"embeds": [embed]}

    try:
        async with httpx.AsyncClient() as client:
            channel_id = series_card.platform_channel_id
            message_id = series_card.platform_message_id
            url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"
            response = await client.patch(
                url,
                json=message_data,
                headers=headers,
                timeout=30.0,
            )

            if response.status_code in {200, 201}:
                logger.info(f"Updated series card: {series_card.subject}")
                return

            raise DiscordHTTPError(
                response.status_code,
                f"Failed to update series card: {response.text}",
            )
    except httpx.HTTPError as e:
        # 重新抛出 httpx.HTTPError，让上层处理
        logger.debug(
            f"HTTP error in _update_discord_message: {type(e).__name__}: {str(e)}, "
            f"channel_id={channel_id}, message_id={message_id}"
        )
        raise


async def update_discord_series_card(
    config, series_card, patches: list, format_patch_list_item_func
) -> None:
    """更新 Discord 上的系列卡片

    Args:
        config: 配置对象
        series_card: 系列卡片订阅对象
        patches: PATCH 列表
        format_patch_list_item_func: 格式化 PATCH 列表项的函数
    """
    try:
        logger.debug(
            f"Starting to update Discord series card: "
            f"message_id={series_card.message_id}, "
            f"patches_count={len(patches)}"
        )

        if not config.discord_bot_token or not config.platform_channel_id:
            logger.debug(
                "Missing Discord bot token or channel ID, skipping card update"
            )
            return

        patch_list = _format_patch_list(patches, format_patch_list_item_func)
        patch_info = parse_patch_subject(series_card.subject)
        description = _build_series_description(series_card, patch_info, patch_list)
        embed = _build_series_embed(series_card, description)
        await _update_discord_message(config, series_card, embed)

    except (DiscordHTTPError, FormatPatchError) as e:
        logger.error(
            f"Failed to update Discord series card: {e}, "
            f"series_card_id={series_card.id if series_card else 'None'}, "
            f"platform_message_id={getattr(series_card, 'platform_message_id', 'N/A')}, "
            f"patches_count={len(patches) if patches else 0}",
            exc_info=True,
        )
    except httpx.HTTPError as e:
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e) if str(e) else "Unknown HTTP error",
        }
        # 如果是 RequestError，尝试获取更多信息
        if hasattr(e, "request") and e.request:  # pylint: disable=no-member
            error_details["url"] = str(e.request.url)  # pylint: disable=no-member
        # 检查是否有 response 属性（某些 httpx 错误类型有）
        response = getattr(e, "response", None)
        if response:
            error_details["status_code"] = getattr(response, "status_code", None)
            response_text = getattr(response, "text", None)
            if response_text:
                error_details["response_text"] = response_text[:200]

        logger.error(
            f"HTTP error updating Discord series card: {error_details}, "
            f"series_card_id={series_card.id if series_card else 'None'}, "
            f"platform_message_id={getattr(series_card, 'platform_message_id', 'N/A')}, "
            f"platform_channel_id={getattr(series_card, 'platform_channel_id', 'N/A')}",
            exc_info=True,
        )


async def _handle_thread_exists_error(config, message_id: str) -> Optional[str]:
    """处理 Thread 已存在的错误

    Args:
        config: 配置对象
        message_id: Discord 消息 ID

    Returns:
        已存在的 Thread ID，如果无法获取则返回 None
    """
    logger.warning(
        f"Thread already exists for message {message_id}, attempting to retrieve existing thread"
    )
    return await _handle_existing_thread_retrieval(config, message_id)


async def _handle_existing_thread_retrieval(config, message_id: str) -> Optional[str]:
    """处理已存在 Thread 的检索逻辑

    Args:
        config: 配置对象
        message_id: Discord 消息 ID

    Returns:
        已存在的 Thread ID，如果无法获取则返回 None
    """
    existing_thread_id = await get_existing_thread_id(config, message_id)
    if existing_thread_id:
        logger.info(f"Found existing thread: {existing_thread_id}")
        return existing_thread_id
    # 无法获取 Thread ID，返回 None（由上层处理错误消息）
    logger.warning(f"Could not retrieve existing thread ID for message {message_id}")
    return None


async def _create_thread_request(
    config, thread_name: str, message_id: str
) -> Optional[str]:
    """发送创建 Thread 的 HTTP 请求

    Args:
        config: 配置对象
        thread_name: Thread 名称
        message_id: Discord 消息 ID

    Returns:
        Thread ID，失败返回 None
    """
    headers = {
        "Authorization": f"Bot {config.discord_bot_token}",
        "Content-Type": "application/json",
    }

    thread_data = {
        "name": thread_name[:100],  # Discord thread 名称限制为 100 字符
        "auto_archive_duration": 10080,  # 7 天后自动归档
    }

    async with httpx.AsyncClient() as client:
        channel_id = config.platform_channel_id
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/threads"
        response = await client.post(
            url,
            json=thread_data,
            headers=headers,
            timeout=30.0,
        )

        if response.status_code in {200, 201}:
            thread_data = response.json()
            thread_id = thread_data.get("id")
            logger.info(f"Created Discord Thread: {thread_name} (ID: {thread_id})")
            return thread_id

        # 检查是否是 Thread 已存在的错误
        error_data = response.json() if response.text else {}
        error_code = error_data.get("code")

        if response.status_code == 400 and error_code == 160004:
            # Thread 已存在，尝试获取 Thread ID
            thread_id = await _handle_thread_exists_error(config, message_id)
            if thread_id:
                return thread_id
            # 如果无法获取 Thread ID，返回 None（由上层处理）
            return None

        logger.error(
            f"Failed to create Discord Thread: {response.status_code}, {response.text}"
        )
        return None


async def create_discord_thread(
    config, thread_name: str, message_id: str
) -> Optional[str]:
    """创建 Discord Thread

    Args:
        config: 配置对象
        thread_name: Thread 名称
        message_id: Discord 消息 ID（Thread 将从这条消息创建）

    Returns:
        Thread ID，失败返回 None
    """
    try:
        if not config.discord_bot_token or not config.platform_channel_id:
            logger.error("Discord bot token or channel ID not configured")
            return None

        return await _create_thread_request(config, thread_name, message_id)

    except httpx.HTTPError as e:
        logger.error(f"HTTP error creating Discord Thread: {e}", exc_info=True)
        return None
    except (ValueError, KeyError) as e:
        logger.error(f"Data error creating Discord Thread: {e}", exc_info=True)
        return None


async def get_existing_thread_id(config, message_id: str) -> Optional[str]:
    """获取已存在的 Thread ID

    Args:
        config: 配置对象
        message_id: Discord 消息 ID

    Returns:
        Thread ID，如果不存在则返回 None
    """
    try:
        if not config.discord_bot_token:
            return None

        headers = {
            "Authorization": f"Bot {config.discord_bot_token}",
        }

        async with httpx.AsyncClient() as client:
            # 方法1: 获取消息对象，检查是否有 thread 字段
            response = await client.get(
                f"https://discord.com/api/v10/channels/{config.platform_channel_id}/messages/{message_id}",
                headers=headers,
                timeout=30.0,
            )

            if response.status_code == 200:
                message_data = response.json()
                # 检查消息是否有 thread 字段
                thread = message_data.get("thread")
                if thread and thread.get("id"):
                    return thread.get("id")

            # 方法2: 如果方法1失败，尝试获取活跃的 Threads
            response = await client.get(
                f"https://discord.com/api/v10/channels/{config.platform_channel_id}/threads/active",
                headers=headers,
                timeout=30.0,
            )

            if response.status_code == 200:
                threads_data = response.json()
                threads = threads_data.get("threads", [])
                # 查找与消息相关的 Thread（通过 parent_id 匹配）
                for thread in threads:
                    if thread.get("parent_id") == message_id:
                        return thread.get("id")

            return None

    except httpx.HTTPError as e:
        logger.warning(f"HTTP error getting existing thread ID: {e}")
        return None
    except (ValueError, KeyError) as e:
        logger.warning(f"Data error getting existing thread ID: {e}")
        return None


async def send_thread_exists_error(  # pylint: disable=unused-argument
    config, message_id: str
) -> None:
    """发送 Thread 已存在的错误消息

    Args:
        config: 配置对象
        message_id: Discord 消息 ID
    """
    try:
        if not config.discord_bot_token or not config.platform_channel_id:
            return

        headers = {
            "Authorization": f"Bot {config.discord_bot_token}",
            "Content-Type": "application/json",
        }

        # 尝试获取已存在的 Thread ID
        thread_id = await get_existing_thread_id(config, message_id)
        thread_link = None
        if thread_id:
            # 构建 Discord Thread 链接
            # 使用消息链接格式，Discord 会自动跳转到对应的 Thread
            # 格式：https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
            # 如果没有 guild_id，使用 @me 表示当前用户
            thread_link = f"https://discord.com/channels/@me/{config.platform_channel_id}/{message_id}"

        # 构建错误消息描述
        description = "此消息已经有一个 Thread 了。\n\n请使用现有的 Thread 继续讨论。"
        if thread_link:
            description += f"\n\n[点击跳转到 Thread →]({thread_link})"

        error_embed = {
            "title": "⚠️ Thread 已存在",
            "description": description,
            "color": 0xFFA500,  # 橙色
            "footer": {"text": "LKML Bot"},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://discord.com/api/v10/channels/{config.platform_channel_id}/messages",
                json={"embeds": [error_embed]},
                headers=headers,
                timeout=30.0,
            )

            if response.status_code in {200, 201}:
                logger.info("Sent thread exists error message")
            else:
                logger.warning(
                    f"Failed to send thread exists error message: {response.status_code}, {response.text}"
                )

    except httpx.HTTPError as e:
        logger.warning(f"HTTP error sending thread exists error: {e}")
    except (ValueError, KeyError) as e:
        logger.warning(f"Data error sending thread exists error: {e}")


def _is_thread_type(thread_data: Dict) -> bool:
    """检查是否是 Thread 类型

    Args:
        thread_data: Thread 数据字典

    Returns:
        如果是 Thread 类型返回 True
    """
    thread_type = thread_data.get("type")
    # Thread 类型是 11 (PUBLIC_THREAD) 或 12 (PRIVATE_THREAD)
    return thread_type in {11, 12}


async def _check_thread_request(config, thread_id: str) -> bool:
    """发送检查 Thread 的 HTTP 请求

    Args:
        config: 配置对象
        thread_id: Discord Thread ID

    Returns:
        如果 Thread 存在返回 True，否则返回 False
    """
    headers = {
        "Authorization": f"Bot {config.discord_bot_token}",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://discord.com/api/v10/channels/{thread_id}",
            headers=headers,
            timeout=30.0,
        )

        if response.status_code == 200:
            thread_data = response.json()
            return _is_thread_type(thread_data)
        if response.status_code == 404:
            return False
        logger.warning(
            f"Unexpected status code when checking thread: {response.status_code}"
        )
        return False


async def check_thread_exists(config, thread_id: str) -> bool:
    """检查 Thread 是否真的存在于 Discord

    Args:
        config: 配置对象
        thread_id: Discord Thread ID

    Returns:
        如果 Thread 存在返回 True，否则返回 False
    """
    try:
        if not config.discord_bot_token:
            logger.error("Discord bot token not configured")
            return False

        return await _check_thread_request(config, thread_id)

    except httpx.HTTPError as e:
        logger.warning(f"HTTP error checking thread existence: {e}")
        return False
    except (ValueError, KeyError) as e:
        logger.warning(f"Data error checking thread existence: {e}")
        return False


async def send_message_to_thread(
    config, thread_id: str, content: str, embed: Optional[Dict] = None
) -> bool:
    """发送消息到 Thread

    Args:
        config: 配置对象
        thread_id: Thread ID
        content: 消息内容
        embed: 可选的 embed 字典

    Returns:
        成功返回 True，失败返回 False
    """
    try:
        if not config.discord_bot_token:
            logger.error("Discord bot token not configured")
            return False

        headers = {
            "Authorization": f"Bot {config.discord_bot_token}",
            "Content-Type": "application/json",
        }

        message_data = {}
        if content:
            message_data["content"] = content
        if embed:
            message_data["embeds"] = [embed]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://discord.com/api/v10/channels/{thread_id}/messages",
                json=message_data,
                headers=headers,
                timeout=30.0,
            )

            if response.status_code in {200, 201}:
                logger.debug(f"Sent message to thread {thread_id}")
                return True
            logger.error(
                f"Failed to send message to Thread: {response.status_code}, {response.text}"
            )
            return False

    except httpx.HTTPError as e:
        logger.error(f"HTTP error sending message to Thread: {e}", exc_info=True)
        return False
    except (ValueError, KeyError) as e:
        logger.error(f"Data error sending message to Thread: {e}", exc_info=True)
        return False
