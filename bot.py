"""NoneBot 应用入口

负责初始化 NoneBot、加载配置、注册适配器等。
"""

import os
import nonebot
from nonebot import get_driver


def register_adapters_if_empty() -> None:
    """如果适配器为空，则尝试注册常见适配器"""
    driver = get_driver()
    if driver._adapters:  # type: ignore
        return

    # Best-effort manual registration for common adapters
    try:
        from nonebot.adapters.discord import Adapter as DiscordAdapter  # type: ignore

        driver.register_adapter(DiscordAdapter)
    except Exception:
        pass

    try:
        from nonebot.adapters.feishu import Adapter as FeishuAdapter  # type: ignore

        driver.register_adapter(FeishuAdapter)
    except Exception:
        pass


driver_spec = os.getenv("DRIVER", "~fastapi+~httpx+~websockets")
nonebot.init(driver=driver_spec)

nonebot.load_from_toml("pyproject.toml")
try:
    nonebot.load_adapters()
except Exception:
    pass
register_adapters_if_empty()

# Strict startup: require at least one adapter when STRICT_STARTUP=1
if os.getenv("STRICT_STARTUP") == "1":
    driver = get_driver()
    if not driver._adapters:  # type: ignore
        raise SystemExit(
            "STRICT_STARTUP=1 and no adapters loaded. Ensure adapters are installed and configured."
        )

app = nonebot.get_asgi()

if __name__ == "__main__":
    nonebot.run()
