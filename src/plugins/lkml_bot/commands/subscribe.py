"""订阅子系统命令模块"""

from nonebot.log import logger
from nonebot import on_message
from nonebot.rule import to_me
from nonebot.adapters import Event, Message
from nonebot.params import EventMessage
from nonebot.exception import FinishedException
from ..shared import register_command
from lkml import LKMLService

lkml_service = LKMLService()

logger = logger

# 仅当消息 @ 到机器人，并且以 "/subscribe" 开头时处理
# 优先级设为 50，高于 help (40)，确保优先匹配
subscribe_cmd = on_message(rule=to_me(), priority=50, block=False)


@subscribe_cmd.handle()
async def handle_subscribe(event: Event, message: Message = EventMessage()):
    """处理订阅命令

    Args:
        event: 事件对象
        message: 消息对象
    """
    try:
        # 获取消息纯文本（Discord 适配器会自动去除 mention）
        text = message.extract_plain_text().strip()

        logger.info(f"Subscribe command handler triggered, text: '{text}'")

        # 处理文本：去除前导空格，查找命令
        text = text.strip()

        # 如果文本以 "/subscribe" 开头
        if not text.startswith("/subscribe"):
            # 尝试查找 "/subscribe" 在文本中的位置
            idx = text.find("/subscribe")
            if idx >= 0:
                text = text[idx:].strip()  # 从 "/subscribe" 开始
            else:
                # 不匹配 subscribe 命令，直接返回（让其他处理器处理）
                logger.debug(
                    f"Text does not match '/subscribe', returning. Text: '{text}'"
                )
                return

        # 解析命令参数
        parts = text.split()
        if len(parts) < 2:
            await subscribe_cmd.finish(
                "subscribe: 缺少 <subsystem>\n用法: @机器人 /subscribe <subsystem>"
            )

        subsystem = parts[1].strip()
        logger.info(f"Processing subscribe request for subsystem: {subsystem}")

        if not subsystem:
            await subscribe_cmd.finish("subscribe: 子系统名称不能为空")

        # 获取用户信息
        try:
            user_id = event.get_user_id()
            user_name = user_id
            if hasattr(event, "author"):
                author = getattr(event, "author", {})
                if isinstance(author, dict):
                    user_name = author.get("username", user_id)
                elif hasattr(author, "username"):
                    user_name = author.username
                elif hasattr(author, "global_name"):
                    user_name = author.global_name or user_id
            logger.debug(f"Operator: {user_id} ({user_name})")
        except FinishedException:
            raise  # 重新抛出 FinishedException，这是正常流程
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            await subscribe_cmd.finish("❌ 无法获取用户信息")

        # 调用服务进行订阅
        try:
            success = await lkml_service.subscribe_subsystem(
                operator_id=str(user_id),
                operator_name=str(user_name),
                subsystem_name=subsystem,
            )

            if success:
                await subscribe_cmd.finish(f"✅ 已订阅子系统: {subsystem}")
            else:
                from ..config import get_config

                config = get_config()
                if subsystem not in config.get_supported_subsystems():
                    await subscribe_cmd.finish(
                        f"❌ 不支持的子系统: {subsystem}\n支持的子系统: {', '.join(config.get_supported_subsystems())}"
                    )
                else:
                    await subscribe_cmd.finish("❌ 订阅失败，请稍后重试")
        except FinishedException:
            raise  # 重新抛出 FinishedException，这是正常流程
        except Exception as e:
            logger.error(f"Error in subscribe_subsystem: {e}", exc_info=True)
            await subscribe_cmd.finish(f"❌ 订阅时发生错误: {str(e)}")
    except FinishedException:
        raise  # 重新抛出 FinishedException，这是正常流程
    except Exception as e:
        logger.error(f"Unexpected error in handle_subscribe: {e}", exc_info=True)
        await subscribe_cmd.finish(f"❌ 处理命令时发生错误: {str(e)}")


# 在导入时注册命令元信息（非管理员命令）
register_command(
    name="subscribe",
    usage="/subscribe <subsystem>",
    description="订阅一个子系统的邮件列表",
    admin_only=False,
)
