from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.core.time import ensure_utc


class PortfolioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PortfolioCreate(PortfolioSchema):
    name: str = Field(min_length=1, max_length=120)
    base_currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("portfolio name must not be empty")
        return normalized

    @field_validator("base_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("currency must contain ASCII letters")
        return normalized


class PortfolioUpdate(PortfolioSchema):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("name cannot be null")
        normalized = value.strip()
        if not normalized:
            raise ValueError("portfolio name must not be empty")
        return normalized

    @field_validator("base_currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("base_currency cannot be null")
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("currency must contain ASCII letters")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "PortfolioUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class PortfolioRead(PortfolioSchema):
    id: int
    name: str
    base_currency: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class PositionCreate(PortfolioSchema):
    asset_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    average_purchase_price: Decimal = Field(ge=0, max_digits=20, decimal_places=6)
    purchase_date: date
    currency: str = Field(min_length=3, max_length=3)
    fees: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("currency must contain ASCII letters")
        return normalized


class PositionUpdate(PortfolioSchema):
    quantity: Decimal | None = Field(
        default=None, gt=0, max_digits=20, decimal_places=8
    )
    average_purchase_price: Decimal | None = Field(
        default=None, ge=0, max_digits=20, decimal_places=6
    )
    purchase_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fees: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)

    @field_validator("quantity", "average_purchase_price", "purchase_date", "currency")
    @classmethod
    def reject_null_updates(cls, value: object, info: ValidationInfo) -> object:
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("currency cannot be null")
        normalized = value.upper()
        if not normalized.isascii() or not normalized.isalpha():
            raise ValueError("currency must contain ASCII letters")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "PositionUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class PositionRead(PortfolioSchema):
    id: int
    portfolio_id: int
    asset_id: int
    symbol: str
    quantity: Decimal
    average_purchase_price: Decimal
    purchase_date: date
    currency: str
    fees: Decimal | None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class PortfolioDetail(PortfolioRead):
    positions: list[PositionRead]
