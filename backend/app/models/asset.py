from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, ExactNumeric, UTCDateTime
from app.core.time import utc_now


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    sector: Mapped[str | None] = mapped_column(String(80))
    industry: Mapped[str | None] = mapped_column(String(120))
    provider_symbol: Mapped[str | None] = mapped_column(String(32))
    cik: Mapped[str | None] = mapped_column(String(10), index=True)
    sec_entity_name: Mapped[str | None] = mapped_column(String(240))
    sec_exchange: Mapped[str | None] = mapped_column(String(80))
    sec_last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    bars: Mapped[list["MarketBar"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    company_profiles: Mapped[list["CompanyProfile"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    filings: Mapped[list["CompanyFiling"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    financial_facts: Mapped[list["FinancialFact"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class MarketBar(Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "timeframe", "event_time", "provider",
            name="uq_market_bars_asset_timeframe_event_provider",
        ),
        CheckConstraint("volume IS NULL OR volume >= 0", name="volume_nonnegative"),
        CheckConstraint(
            "high IS NULL OR ((open IS NULL OR high >= open) AND "
            "(close IS NULL OR high >= close) AND (low IS NULL OR high >= low))",
            name="high_valid",
        ),
        CheckConstraint(
            "low IS NULL OR ((open IS NULL OR low <= open) AND "
            "(close IS NULL OR low <= close) AND (high IS NULL OR low <= high))",
            name="low_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    event_time: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    open: Mapped[Decimal | None] = mapped_column(ExactNumeric(20, 8))
    high: Mapped[Decimal | None] = mapped_column(ExactNumeric(20, 8))
    low: Mapped[Decimal | None] = mapped_column(ExactNumeric(20, 8))
    close: Mapped[Decimal | None] = mapped_column(ExactNumeric(20, 8))
    adjusted_close: Mapped[Decimal | None] = mapped_column(ExactNumeric(20, 8))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime] = mapped_column(UTCDateTime())
    inserted_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)

    asset: Mapped[Asset] = relationship(back_populates="bars")
