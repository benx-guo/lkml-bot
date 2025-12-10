"""Thread 相关异常"""


class ThreadPoolFullError(Exception):
    """Thread 池已满异常"""


class DiscordAPIError(Exception):
    """Discord API 调用异常"""


class DiscordHTTPError(Exception):
    """Discord HTTP 请求异常"""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Discord API error {status_code}: {message}")


class FormatPatchError(Exception):
    """格式化 Patch 失败异常"""
