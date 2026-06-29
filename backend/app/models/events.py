from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime


class PoliticalEvent(Base):
    __tablename__ = "political_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    region: Mapped[str] = mapped_column(String(80), index=True)
    impact: Mapped[str] = mapped_column(String(16), index=True)
    summary: Mapped[str] = mapped_column(Text)
    occurs_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)

