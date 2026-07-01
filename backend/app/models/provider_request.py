from datetime import datetime

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime


class ProviderRequestLog(Base):
    __tablename__ = "provider_request_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    endpoint: Mapped[str] = mapped_column(String(80))
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status_code: Mapped[int | None] = mapped_column(Integer)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    successful: Mapped[bool] = mapped_column(Boolean, index=True)
    error_type: Mapped[str | None] = mapped_column(String(80))
    request_group_id: Mapped[str] = mapped_column(String(36), index=True)
