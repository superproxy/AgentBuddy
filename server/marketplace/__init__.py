"""AgentBuddy 插件市场服务模块。

独立部署模式：不依赖 config_server.py。
数据存储在 marketplace_dir（index.json + packages/*.zip）。
"""
from .routes import create_marketplace_bp

__all__ = ["create_marketplace_bp"]
