from pydantic import BaseModel, Field


class Config(BaseModel):
    """EhPreview 插件的配置模型."""

    e_cookie: str = Field(
        default="",
        description="用于访问 E-Hentai / ExHentai 的 Cookie",
    )
    p_cookie: str = Field(
        default="",
        description="用于访问 Pixiv 的 Cookie",
    )
    proxy: str | None = Field(
        default=None,
        description="下载时使用的代理，例如 'http://127.0.0.1:7890'",
    )
    download_dir: str = Field(default="data/eh_preview", description="画廊下载文件的根目录")
    cache_max_days: int = Field(
        default=30, description="缓存最大保留天数。超过这个天数的旧缓存将在启动时被自动清理。"
    )
    cache_max_entries: int = Field(
        default=500,
        description="缓存最大条目数。如果清理完过期缓存后，总数依然超过此值，将按先进先出的原则清理最旧的缓存。",
    )
