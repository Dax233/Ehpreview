# plugins_human/eh_preview/models.py
import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import declarative_base

# 这是只属于 eh_preview 插件的 Base，和核心的 Base 互不干扰！
Base = declarative_base()


class DownloadRecord(Base):
    """eh_preview 插件的专属下载记录模型."""

    __tablename__ = "download_records"

    url = Column(String(512), primary_key=True)
    status = Column(String(20), nullable=False, index=True)
    title = Column(String, nullable=True)
    result_path = Column(String, nullable=True)
    result_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
