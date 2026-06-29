from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime
from app.core.time import utc_now


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    sector: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    prices: Mapped[list["PricePoint"]] = relationship(back_populates="asset")


class PricePoint(Base):
    __tablename__ = "price_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6))

    asset: Mapped[Asset] = relationship(back_populates="prices")

