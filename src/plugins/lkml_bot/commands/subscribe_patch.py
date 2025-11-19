"""订阅 PATCH 命令

允许用户通过命令订阅特定的 PATCH，为其创建 Thread。
不需要 Interaction Endpoint，直接通过 Discord Bot 消息命令处理。
"""

from nonebot import on_message
from nonebot.rule import to_me
from nonebot.adapters import Message, Event
from nonebot.params import EventMessage
from nonebot.exception import FinishedException
from nonebot.log import logger
from sqlalchemy.exc import SQLAlchemyError

from lkml.db.repo.email_message_repository import EMAIL_MESSAGE_REPO
from lkml.feed.patch_parser import parse_patch_subject
from lkml.service.patch_subscription_service import patch_subscription_service
from lkml.service.thread_content_service import thread_content_service

from ..shared import register_command
from ..thread.discord_api import send_thread_exists_error
from ..thread.exceptions import DiscordHTTPError, FormatPatchError
from .subscribe_patch_helpers import (
    build_success_message,
    check_existing_thread,
    save_thread_and_mark_subscribed,
)
from .subscribe_patch_validation import get_thread_manager, validate_command


# 注册命令元信息
register_command(
    name="watch",
    usage="/watch <message_id> 或 /w <message_id>",
    description="为指定的 PATCH 创建专属 Thread",
    admin_only=False,
)

# 创建 matcher - 需要 @ 提及机器人
# 优先级设为 50，高于 help (40)，确保优先处理
# block=False 确保如果命令不匹配时不阻止其他命令处理
SubscribePatchCmd = on_message(rule=to_me(), priority=50, block=False)


@SubscribePatchCmd.handle()
async def handle_subscribe_patch(_event: Event, message: Message = EventMessage()):
    """处理订阅 PATCH 命令"""
    msg_text = message.extract_plain_text().strip()
    logger.info(f"[watch] Received message: {msg_text}")

    try:
        # 验证命令并获取参数
        message_id, user_info = await validate_command(
            msg_text, _event, SubscribePatchCmd
        )
        if not message_id or not user_info:
            return

        _user_id, user_name = user_info

        # 获取数据库和 Thread 管理器
        database, thread_manager = get_thread_manager()
        if not database or not thread_manager:
            await SubscribePatchCmd.finish("❌ 数据库未初始化，请联系管理员")
            return

        # 查找 PATCH 订阅并检查现有 Thread
        patch_sub, existing_thread, is_recreate = await _find_patch_and_check_thread(
            message_id, thread_manager, SubscribePatchCmd
        )
        if not patch_sub:
            return

        if existing_thread:
            # Thread 存在，返回 Thread 链接
            await _handle_existing_thread(existing_thread, patch_sub, SubscribePatchCmd)
            return

        # 创建新 Thread
        thread_id = await _create_new_thread(
            patch_sub, thread_manager, SubscribePatchCmd
        )
        if not thread_id:
            return

        # 记录成功并发送消息
        logger.info(
            f"User {user_name} successfully subscribed to PATCH: {patch_sub.subject}, "
            f"Thread ID: {thread_id}"
        )
        success_msg = build_success_message(patch_sub, thread_id, is_recreate)
        await SubscribePatchCmd.finish(success_msg)

    except FinishedException:  # pylint: disable=try-except-raise
        # finish() 抛出的异常，直接重新抛出以终止处理
        raise
    except (SQLAlchemyError, DiscordHTTPError, FormatPatchError) as e:
        logger.error(f"Failed to subscribe PATCH: {e}", exc_info=True)
        await SubscribePatchCmd.finish("❌ 订阅失败，请联系管理员查看日志")
    except (ValueError, KeyError, AttributeError) as e:
        logger.error(f"Data error subscribing PATCH: {e}", exc_info=True)
        await SubscribePatchCmd.finish("❌ 订阅失败，请联系管理员查看日志")


async def _find_patch_and_check_thread(message_id: str, thread_manager, matcher):
    """查找 PATCH 订阅并检查现有 Thread

    如果是系列 PATCH，统一使用 Cover Letter 的信息。

    Args:
        database: 数据库实例
        message_id: PATCH message_id
        thread_manager: Thread 管理器
        matcher: NoneBot matcher

    Returns:
        (patch_sub, existing_thread, is_recreate) 元组
        patch_sub 如果是系列 PATCH，则返回 Cover Letter
    """
    # 先尝试从 patch_subscription_service 查找
    patch_sub = await patch_subscription_service.find_by_message_id(message_id)

    if not patch_sub:
        # 如果 patch_subscription_service 中没有，尝试在 EMAIL_MESSAGE_REPO 中查找
        # 需要从 thread_manager 获取 database
        async with thread_manager.database.get_db_session() as session:
            email_message = await EMAIL_MESSAGE_REPO.find_by_message_id_header(
                session, message_id
            )

        if email_message:
            # 解析 PATCH 信息
            patch_info = parse_patch_subject(email_message.subject)
            if not patch_info or not patch_info.is_patch:
                await matcher.finish(
                    f"❌ 找到邮件但非 PATCH: `{message_id}`\n\n"
                    "请确保 message_id 对应的是一个 PATCH 邮件。"
                )
                return None, None, False

            # 创建 PATCH_SUBSCRIPTION 记录
            patch_sub = await _create_patch_subscription_from_email(
                email_message, patch_info, thread_manager
            )
            if not patch_sub:
                await matcher.finish(
                    f"❌ 创建 PATCH 订阅记录失败: `{message_id}`\n\n"
                    "请联系管理员查看日志。"
                )
                return None, None, False
        else:
            await matcher.finish(
                f"❌ 未找到 PATCH: `{message_id}`\n\n"
                "请确保 message_id 正确，或者该 PATCH 已过期。"
            )
            return None, None, False

    # 如果是系列 PATCH，查找 Cover Letter
    if patch_sub.series_message_id:
        cover_letter = await _find_cover_letter(patch_sub.series_message_id)
        if not cover_letter:
            await matcher.finish(
                f"❌ 未找到该系列 PATCH 的 Cover Letter\n\n"
                f"系列 ID: `{patch_sub.series_message_id}`\n"
                f"请确保 Cover Letter 已存在。"
            )
            return None, None, False
        # 使用 Cover Letter 替换当前的 patch_sub
        patch_sub = cover_letter

    # 检查是否已经订阅
    existing_thread, is_recreate = await check_existing_thread(
        patch_sub, thread_manager
    )

    return patch_sub, existing_thread, is_recreate


async def _create_patch_subscription_from_email(
    email_message, patch_info, thread_manager
):
    """从 EmailMessage 创建 PATCH_SUBSCRIPTION 记录

    Args:
        session: 数据库会话
        email_message: EmailMessage 对象
        patch_info: PATCH 信息
        thread_manager: Thread 管理器

    Returns:
        创建的 PatchSubscription 对象，失败返回 None
    """
    try:
        # 获取配置信息
        config = thread_manager.config
        platform_channel_id = config.platform_channel_id
        if not platform_channel_id:
            logger.error("platform_channel_id not configured")
            return None

        # 计算过期时间（24小时）
        expires_at = thread_content_service.calculate_expires_at(24)

        # 构建订阅数据
        subscription_data = thread_content_service.build_subscription_data(
            message_id=email_message.message_id_header,
            subsystem=email_message.subsystem.name,
            platform_message_id="",  # 暂时为空，后续创建 Thread 时会更新
            platform_channel_id=platform_channel_id,
            subject=email_message.subject,
            author=email_message.sender,
            url=email_message.url,
            expires_at=expires_at,
            series_message_id=(
                email_message.message_id_header
                if patch_info.is_cover_letter
                else email_message.in_reply_to_header
            ),
            patch_version=patch_info.version,
            patch_index=patch_info.index,
            patch_total=patch_info.total,
        )

        # 创建订阅记录
        patch_sub = await patch_subscription_service.create(subscription_data)

        logger.info(
            f"Created PATCH subscription from EmailMessage: {email_message.message_id_header}, "
            f"subject: {email_message.subject[:50]}"
        )

        return patch_sub

    except (SQLAlchemyError, ValueError, KeyError, AttributeError) as e:
        logger.error(
            f"Failed to create PATCH subscription from EmailMessage: {e}", exc_info=True
        )
        return None


async def _find_cover_letter(series_message_id: str):
    """查找系列 PATCH 的 Cover Letter

    Args:
        session: 数据库会话
        series_message_id: 系列 message_id

    Returns:
        Cover Letter 的 PATCH 订阅对象，如果不存在则返回 None
    """
    series_patches = await patch_subscription_service.get_series_patches(
        series_message_id
    )
    # 查找 patch_index == 0 的 Cover Letter
    for patch in series_patches:
        if patch.patch_index == 0:
            return patch
    return None


async def _handle_existing_thread(existing_thread, patch_sub, matcher):
    """处理已存在的 Thread

    Args:
        existing_thread: 已存在的 Thread 对象
        patch_sub: PATCH 订阅对象
        matcher: NoneBot matcher
    """
    logger.info(f"Thread {existing_thread.thread_id} exists in Discord, returning link")

    # 如果 thread 存在但 is_subscribed 为 False，标记为已订阅
    if not patch_sub.is_subscribed:
        logger.info(
            f"Thread exists but PATCH {patch_sub.message_id} is not marked as subscribed, "
            f"marking as subscribed now"
        )
        await patch_subscription_service.mark_as_subscribed(patch_sub)

    await matcher.finish(
        f"✅ 此 Thread 已创建\n\n"
        f"Thread: <#{existing_thread.thread_id}>\n"
        f"主题: {patch_sub.subject[:100]}"
    )


async def _create_new_thread(patch_sub, thread_manager, matcher) -> str | None:
    """创建新 Thread

    Args:
        patch_sub: PATCH 订阅对象
        thread_manager: Thread 管理器
        matcher: NoneBot matcher

    Returns:
        Thread ID，如果失败则返回 None
    """
    # 检查 Thread 池
    if not await thread_manager.check_thread_pool_limit():
        await matcher.finish("⚠️ Thread 池已满，暂时无法创建新的 Thread。请稍后再试。")
        return None

    # 创建 Thread
    thread_name = patch_sub.subject[:100]  # Discord thread 名称限制为 100 字符
    thread_id = await thread_manager.create_discord_thread(
        thread_name, patch_sub.platform_message_id
    )

    if not thread_id:
        # Thread 创建失败，可能是 Thread 已存在但无法获取 ID
        # 发送友好的错误消息（包含链接），即使无法获取 Thread ID
        # 因为如果创建失败，很可能是 Thread 已存在
        await send_thread_exists_error(
            thread_manager.config, patch_sub.platform_message_id
        )
        await matcher.finish()  # 不发送额外的错误消息
        return None

    # 保存 Thread 信息并标记整个系列为已订阅
    try:
        await save_thread_and_mark_subscribed(
            thread_id, thread_name, patch_sub, thread_manager
        )
        logger.info(
            f"Successfully saved thread and marked PATCH as subscribed: "
            f"{patch_sub.message_id}, is_subscribed={patch_sub.is_subscribed}"
        )
    except Exception as e:
        logger.error(
            f"Failed to save thread and mark PATCH as subscribed: {e}", exc_info=True
        )
        raise

    return thread_id
