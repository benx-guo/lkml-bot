"""NoneBot 应用入口

负责初始化 NoneBot、加载配置、注册适配器等。
"""

import os
import sys
from pathlib import Path

import nonebot
from nonebot.adapters.discord import Adapter as DiscordAdapter
from nonebot.adapters.feishu import Adapter as FeishuAdapter
from nonebot.log import logger

# 将 src 目录添加到 Python 路径，以便导入插件模块
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


driver_spec = os.getenv("DRIVER", "~fastapi+~httpx+~websockets")
nonebot.init(driver=driver_spec)

nonebot.load_from_toml("pyproject.toml")

# 手动注册适配器（作为 load_from_toml 的后备方案）
driver = nonebot.get_driver()
if not getattr(driver, "_adapters", None):
    # 优先使用兼容性适配器，如果导入失败则使用原始适配器
    try:
        try:
            from compat.discord_compat_adapter import CompatibleDiscordAdapter

            driver.register_adapter(CompatibleDiscordAdapter)
            logger.info(
                "✓ Registered compatible Discord adapter "
                "(all validation errors will be logged but won't crash the bot)"
            )
        except (ImportError, AttributeError, RuntimeError) as compat_error:
            # 如果兼容性适配器导入失败，回退到原始适配器
            logger.warning(
                f"Failed to import compatible Discord adapter, using original: {compat_error}"
            )
            driver.register_adapter(DiscordAdapter)
    except (ImportError, AttributeError, RuntimeError) as e:
        logger.error(f"Failed to register Discord adapter: {e}")

    try:
        driver.register_adapter(FeishuAdapter)
    except (ImportError, AttributeError, RuntimeError) as e:
        logger.warning(f"Failed to register Feishu adapter: {e}")

app = nonebot.get_asgi()

if __name__ == "__main__":
    nonebot.run()
