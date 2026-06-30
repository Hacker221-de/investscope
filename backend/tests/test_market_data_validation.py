from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.data_sources import ProviderMarketBar, Timeframe


def bar(**changes: object) -> ProviderMarketBar:
    values: dict[str, object] = {
        "timeframe": Timeframe.DAY_1,
        "event_time": datetime(2026, 6, 30, tzinfo=UTC),
        "open": Decimal("100"),
        "high": Decimal("110"),
        "low": Decimal("90"),
        "close": Decimal("105"),
        "volume": 10,
        "provider": "test",
        "received_at": datetime(2026, 6, 30, 23, tzinfo=UTC),
    }
    values.update(changes)
    return ProviderMarketBar.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [("high", Decimal("99")), ("low", Decimal("106"))],
)
def test_invalid_ohlc_is_rejected(field: str, value: Decimal) -> None:
    with pytest.raises(ValidationError):
        bar(**{field: value})


def test_negative_volume_is_rejected() -> None:
    with pytest.raises(ValidationError):
        bar(volume=-1)


def test_missing_market_values_remain_null() -> None:
    result = bar(open=None, high=None, low=None, adjusted_close=None, volume=None)

    assert result.open is None
    assert result.volume is None
