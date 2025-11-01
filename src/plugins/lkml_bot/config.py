"""插件配置管理模块（包含机器人特定配置）"""

from lkml.config import LKMLConfig as BaseLKMLConfig


class PluginConfig(BaseLKMLConfig):
    """插件层配置（扩展基础配置，添加机器人特定配置）"""

    # Discord 配置（机器人特定）
    discord_webhook_url: str = ""

    @classmethod
    def from_env(cls) -> "PluginConfig":
        """从环境变量创建配置"""
        import os

        # 先创建基础配置（已经处理了所有基础配置的环境变量和默认值）
        base_config = BaseLKMLConfig.from_env()

        # 获取 Discord webhook URL（从环境变量读取，可在 .env 文件中配置）
        discord_webhook_url = os.getenv("LKML_DISCORD_WEBHOOK_URL", "")

        return cls(
            database_url=base_config.database_url,
            manual_subsystems=base_config.manual_subsystems,
            max_news_count=base_config.max_news_count,
            monitoring_interval=base_config.monitoring_interval,
            last_update_dt_override_iso=base_config.last_update_dt_override_iso,
            discord_webhook_url=discord_webhook_url,
        )


def get_config() -> PluginConfig:
    """获取配置实例（单例模式）"""
    if not hasattr(get_config, "_instance"):
        get_config._instance = PluginConfig.from_env()
    return get_config._instance
