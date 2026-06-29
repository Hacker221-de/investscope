from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime
from app.core.time import utc_now


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    rating: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    rationale: Mapped[str] = mapped_column(Text)
    horizon: Mapped[str] = mapped_column(String(32))
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

