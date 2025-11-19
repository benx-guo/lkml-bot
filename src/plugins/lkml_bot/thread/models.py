"""Thread 相关模型类"""


class SimplePatch:  # pylint: disable=too-few-public-methods
    """简单的 Patch 对象，用于模拟 PatchSubscription

    用于从同步版本的 series_info 中创建临时对象。
    """

    def __init__(self, data):
        self.subject = data["subject"]
        self.patch_index = data["patch_index"]
        self.patch_total = data["patch_total"]
        self.message_id = data.get("message_id")
        self.url = data.get("url")
