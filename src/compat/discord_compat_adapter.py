"""Discord 适配器兼容性包装器

用于处理 Discord 适配器的 Pydantic 验证错误，避免程序崩溃。
无论什么事件，如果处理不了，就记录错误但不抛出异常。
"""

import asyncio
from typing import Optional

from pydantic import ValidationError

from nonebot.adapters.discord import Adapter as DiscordAdapter
from nonebot.adapters.discord.event import Event as DiscordEvent, MessageEvent
from nonebot.adapters.discord.payload import (
    Dispatch,
    Heartbeat,
    HeartbeatAck,
    InvalidSession,
    Payload,
    Reconnect,
)
from nonebot.exception import WebSocketClosed
from nonebot.log import logger


class CompatibleDiscordAdapter(DiscordAdapter):
    """兼容性 Discord 适配器包装器

    重写 payload_to_event 和 _loop 方法，捕获所有验证错误并记录日志，
    避免因 Discord API 数据格式变化导致的程序崩溃。
    """

    @classmethod
    def payload_to_event(cls, payload: Dispatch) -> Optional[DiscordEvent]:
        """将 Discord WebSocket payload 转换为事件对象

        如果遇到任何验证错误，记录错误日志并返回 None，而不是抛出异常。
        这样可以防止 Bot 崩溃，同时保留错误信息用于调试。

        Args:
            payload: Discord Dispatch payload 对象

        Returns:
            事件对象，如果解析失败则返回 None
        """
        event_type = getattr(payload, "type", "unknown")
        sequence = getattr(payload, "sequence", None)

        try:
            # 调用父类方法进行正常解析
            return super().payload_to_event(payload)
        except ValidationError as e:
            # 捕获 Pydantic 验证错误
            logger.error(
                "Discord event validation error (ignored to prevent crash): "
                f"event_type={event_type}, sequence={sequence}, "
                f"errors={len(e.errors())}"
            )

            # 记录详细的验证错误
            for i, error in enumerate(e.errors()[:10], 1):  # 最多记录前10个错误
                error_loc = " -> ".join(str(loc) for loc in error.get("loc", []))
                error_msg = error.get("msg", "unknown error")
                logger.error(f"  Validation error {i}: {error_loc}: {error_msg}")

            # 返回 None，表示无法解析此事件
            # 这样适配器会跳过这个事件，继续处理下一个
            return None
        except (RuntimeError, ValueError, AttributeError, TypeError, OSError) as e:
            # 捕获常见的运行时异常，记录但不抛出
            logger.error(
                "Unexpected error parsing Discord event (ignored to prevent crash): "
                f"event_type={event_type}, sequence={sequence}, "
                f"error={type(e).__name__}: {e}",
                exc_info=True,
            )
            return None

    def _handle_dispatch_payload(self, bot, payload: Dispatch) -> bool:
        """处理 Dispatch payload

        Args:
            bot: Bot 实例
            payload: Dispatch payload 对象

        Returns:
            True 表示继续循环，False 表示需要退出循环
        """
        bot.sequence = payload.sequence
        # 使用 payload_to_event 方法，它会捕获验证错误并返回 None
        event = self.payload_to_event(payload)
        if event is None:
            # 如果事件解析失败（返回 None），跳过这个事件
            logger.debug(
                "Skipping event due to validation error: "
                f"type={payload.type}, sequence={payload.sequence}"
            )
            return True

        # 检查是否是自己的消息（避免循环）
        if not (
            isinstance(event, MessageEvent)
            and event.get_user_id() == bot.self_id
            and not self.discord_config.discord_handle_self_message
        ):
            asyncio.create_task(bot.handle_event(event))
        return True

    async def _handle_payload(self, bot, ws, payload: Payload) -> bool:
        """处理不同类型的 payload

        Args:
            bot: Bot 实例
            ws: WebSocket 连接
            payload: Payload 对象

        Returns:
            True 表示继续循环，False 表示需要退出循环
        """
        # 使用 if-elif 链减少 return 语句数量（合并相同返回值的分支）
        if isinstance(payload, Dispatch):
            return self._handle_dispatch_payload(bot, payload)
        if isinstance(payload, Heartbeat):
            return await self._handle_heartbeat(ws, bot)
        if isinstance(payload, HeartbeatAck):
            return self._handle_heartbeat_ack()
        if isinstance(payload, Reconnect):
            return self._handle_reconnect()
        if isinstance(payload, InvalidSession):
            return self._handle_invalid_session(bot)
        # 处理基类 Payload 或未知类型（合并相同返回值的分支）
        if isinstance(payload, Payload):
            logger.debug(
                f"Received base Payload type (unrecognized), skipping: {type(payload)}"
            )
        else:
            logger.warning(f"Unknown payload type: {type(payload)}, skipping")
        return True

    async def _handle_heartbeat(self, ws, bot) -> bool:
        """处理心跳 payload"""
        await self._heartbeat(ws, bot)
        return True

    def _handle_heartbeat_ack(self) -> bool:
        """处理心跳 ACK"""
        logger.trace("Heartbeat ACK")
        return True

    def _handle_reconnect(self) -> bool:
        """处理重连请求"""
        logger.warning("Received reconnect event from server. Try to reconnect...")
        return False

    def _handle_invalid_session(self, bot) -> bool:
        """处理无效会话"""
        bot.clear()
        logger.error("Received invalid session event from server. Try to reconnect...")
        return False

    @staticmethod
    def _is_connection_closed_error(exception: Exception) -> bool:
        """检查是否是连接关闭相关的异常

        Args:
            exception: 异常对象

        Returns:
            True 表示是连接关闭异常，False 表示不是
        """
        if isinstance(exception, (WebSocketClosed, BrokenPipeError)):
            return True
        error_name = type(exception).__name__
        error_module = type(exception).__module__
        return (
            "ConnectionClosed" in error_name
            or "WebSocketClosed" in error_name
            or ("websockets" in error_module and "ConnectionClosed" in error_name)
        )

    async def _handle_loop_exception(self, exception: Exception) -> bool:
        """处理循环中的异常

        Args:
            exception: 异常对象

        Returns:
            True 表示继续循环，False 表示需要退出循环
        """
        if self._is_connection_closed_error(exception):
            # WebSocket 连接关闭，正常退出循环让适配器重新连接
            logger.info(
                f"WebSocket connection closed ({type(exception).__name__}), "
                "exiting loop to allow reconnection"
            )
            return False
        if isinstance(
            exception, (RuntimeError, ValueError, AttributeError, OSError, TypeError)
        ):
            # 捕获常见的运行时异常，记录但不中断循环
            logger.error(
                "Error in Discord adapter loop (continuing to prevent crash): "
                f"{type(exception).__name__}: {exception}",
                exc_info=True,
            )
            # 等待一小段时间后继续，避免快速循环
            await asyncio.sleep(1)
            return True
        # 其他未知异常，记录但不中断循环
        logger.error(
            "Unexpected error in Discord adapter loop (continuing): "
            f"{type(exception).__name__}: {exception}",
            exc_info=True,
        )
        await asyncio.sleep(1)
        return True

    async def _loop(self, bot, ws):
        """重写 _loop 方法，处理 payload_to_event 返回 None 的情况

        主要改进：
        1. 捕获所有异常，防止 Bot 崩溃
        2. 处理 payload_to_event 返回 None 的情况
        3. 确保循环继续运行，不会因为单个事件失败而停止
        """
        while True:
            try:
                payload = await self.receive_payload(ws)
                logger.trace(f"Received payload: {payload}")

                should_continue = await self._handle_payload(bot, ws, payload)
                if not should_continue:
                    break
            except (KeyboardInterrupt, SystemExit):
                # 系统级异常需要重新抛出，不捕获
                raise
            except (
                RuntimeError,
                ValueError,
                AttributeError,
                OSError,
                TypeError,
                ConnectionError,
                IOError,
                TimeoutError,
                WebSocketClosed,
                BrokenPipeError,
            ) as e:
                # 捕获已知的异常类型
                should_continue = await self._handle_loop_exception(e)
                if not should_continue:
                    break
            except Exception as e:  # pylint: disable=broad-exception-caught
                # 捕获其他未知异常作为兜底，防止 Bot 崩溃
                # 这是必要的，因为 Discord API 可能返回各种未预期的异常
                should_continue = await self._handle_loop_exception(e)
                if not should_continue:
                    break
