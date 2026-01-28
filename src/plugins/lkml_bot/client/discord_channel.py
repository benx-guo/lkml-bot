"""Discord 频道消息发送工具"""

import asyncio
from typing import Optional

import httpx
from nonebot.log import logger

from .discord_client import truncate_description


def _build_channel_headers(config) -> dict:
    """构建 Discord 请求头"""
    return {
        "Authorization": f"Bot {config.discord_bot_token}",
        "Content-Type": "application/json",
    }


def _build_channel_url(config) -> str:
    """构建 Discord 频道发送 URL"""
    return f"https://discord.com/api/v10/channels/{config.platform_channel_id}/messages"


async def _post_embed_with_retries(
    url_path: str, headers: dict, embed: dict, max_retries: int
) -> Optional[str]:
    """发送 embed 请求并处理重试"""
    result_message_id: Optional[str] = None
    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url_path,
                    json={"embeds": [embed]},
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code in {200, 201}:
                    result = response.json()
                    result_message_id = result.get("id")
                    break

                if response.status_code == 429:
                    retry_after = response.json().get("retry_after", 1.0)
                    logger.warning(
                        "Discord rate limit hit (429), retry after %ss "
                        "(attempt %d/%d)",
                        retry_after,
                        attempt + 1,
                        max_retries,
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    break

                logger.error(
                    "Failed to send embed to channel: %s, %s",
                    response.status_code,
                    response.text,
                )
                break
            except httpx.TimeoutException:
                logger.error("Timeout sending Discord channel embed")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                break
            except (httpx.HTTPError, RuntimeError) as e:
                logger.error(
                    "Error sending Discord channel embed: %s", e, exc_info=True
                )
                break

    return result_message_id


def _build_channel_embed(
    title: str, description: str, url: Optional[str], color: Optional[int]
) -> dict:
    """构建 Discord embed 数据"""
    embed = {
        "title": title[:256],
        "description": truncate_description(description),
        "color": color if color is not None else 0x5865F2,
    }
    if url:
        embed["url"] = url
    return embed


async def send_channel_embed(
    config,
    title: str,
    description: str,
    url: Optional[str] = None,
    color: Optional[int] = None,
    max_retries: int = 3,
) -> Optional[str]:
    """发送 embed 消息到频道（带 rate limit 处理）"""
    try:
        if not config.discord_bot_token or not config.platform_channel_id:
            logger.error("Discord bot token or channel ID not configured")
            return None

        headers = _build_channel_headers(config)
        embed = _build_channel_embed(title, description, url, color)
        url_path = _build_channel_url(config)

        return await _post_embed_with_retries(url_path, headers, embed, max_retries)
    except (ValueError, KeyError) as e:
        logger.error("Data error sending Discord channel embed: %s", e, exc_info=True)
        return None
