"""取消订阅子系统命令模块"""

from nonebot.log import logger
from nonebot import on_message
from nonebot.rule import to_me
from nonebot.adapters import Event, Message
from nonebot.params import EventMessage
from nonebot.exception import FinishedException
from ..shared import register_command
from lkml import LKMLService

logger = logger

lkml_service = LKMLService()


# 仅当消息 @ 到机器人，并且以 "/unsubscribe" 开头时处理
unsubscribe_cmd = on_message(rule=to_me(), priority=50, block=False)


@unsubscribe_cmd.handle()
async def handle_unsubscribe(event: Event, message: Message = EventMessage()):
    """处理取消订阅命令"""
    try:
        text = message.extract_plain_text().strip()

        # 处理文本：去除前导空格，查找命令
        text = text.strip()

        # 如果文本以 "/unsubscribe" 开头
        if not text.startswith("/unsubscribe"):
            # 尝试查找 "/unsubscribe" 在文本中的位置
            idx = text.find("/unsubscribe")
            if idx >= 0:
                text = text[idx:].strip()  # 从 "/unsubscribe" 开始
            else:
                # 不匹配 unsubscribe 命令，直接返回（让其他处理器处理）
                logger.debug(
                    f"Text does not match '/unsubscribe', returning. Text: '{text}'"
                )
                return

        # 解析命令参数
        parts = text.split()
        if len(parts) < 2:
            await unsubscribe_cmd.finish(
                "unsubscribe: 缺少 <subsystem>\n用法: @机器人 /unsubscribe <subsystem>"
            )

        subsystem = parts[1].strip()

        if not subsystem:
            await unsubscribe_cmd.finish("unsubscribe: 子系统名称不能为空")

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
            await unsubscribe_cmd.finish("❌ 无法获取用户信息")

        # 调用服务进行退订
        try:
            success = await lkml_service.unsubscribe_subsystem(
                operator_id=str(user_id),
                operator_name=str(user_name),
                subsystem_name=subsystem,
            )

            if success:
                await unsubscribe_cmd.finish(f"✅ 已取消订阅子系统: {subsystem}")
            else:
                await unsubscribe_cmd.finish(
                    "❌ 取消订阅失败，子系统可能不存在或未订阅"
                )
        except FinishedException:
            raise  # 重新抛出 FinishedException，这是正常流程
        except Exception as e:
            logger.error(f"Error in unsubscribe_subsystem: {e}", exc_info=True)
            await unsubscribe_cmd.finish(f"❌ 取消订阅时发生错误: {str(e)}")
    except FinishedException:
        raise  # 重新抛出 FinishedException，这是正常流程
    except Exception as e:
        logger.error(f"Unexpected error in handle_unsubscribe: {e}", exc_info=True)
        await unsubscribe_cmd.finish(f"❌ 处理命令时发生错误: {str(e)}")


# 在导入时注册命令元信息（非管理员命令）
register_command(
    name="unsubscribe",
    usage="/unsubscribe <subsystem>",
    description="取消订阅一个子系统的邮件列表",
    admin_only=False,
)
