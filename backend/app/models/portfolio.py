from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime
from app.core.time import utc_now


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    base_currency: Mapped[str] = mapped_column(String(3), default="USD")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    positions: Mapped[list["Position"]] = relationship(back_populates="portfolio")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    average_purchase_price: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    purchase_date: Mapped[date] = mapped_column(Date())
    currency: Mapped[str] = mapped_column(String(3))
    fees: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    portfolio: Mapped[Portfolio] = relationship(back_populates="positions")
