from decimal import Decimal
import re

import pytest
from pydantic import ValidationError

from app.demo_data import ASSETS, POLITICAL_EVENTS
from app.modules.data_sources import DemoMarketDataSource
from app.modules.forecasting import linear_projection
from app.modules.fundamental_analysis import fundamental_score
from app.modules.political_analysis import political_risk_score
from app.modules.technical_analysis import moving_average_signal
from app.schemas import LegacyPositionCreate


def test_demo_data_source_is_deterministic() -> None:
    source = DemoMarketDataSource()

    assert source.price_for("aapl") == Decimal("213.49")
    assert source.price_for("UNKNOWN") is None


def test_fundamental_score_is_bounded() -> None:
    score = fundamental_score(Decimal("0.40"), Decimal("0.20"), Decimal("0.30"))

    assert score == Decimal("97.00")


def test_technical_signal_detects_uptrend() -> None:
    prices = [Decimal(value) for value in range(1, 22)]

    assert moving_average_signal(prices, short_window=5, long_window=20) == "bullish"


def test_linear_projection_and_political_score() -> None:
    assert linear_projection([Decimal("10"), Decimal("12")], 2) == [
        Decimal("14.00"),
        Decimal("16.00"),
    ]
    assert political_risk_score([Decimal("40"), Decimal("80")]) == Decimal("60.00")


def test_tickers_are_ascii_and_cyrillic_ticker_is_rejected() -> None:
    tickers = [asset["symbol"] for asset in ASSETS]
    tickers.extend(
        symbol for event in POLITICAL_EVENTS for symbol in event["affected_assets"]
    )
    assert all(re.fullmatch(r"[A-Z0-9.\-]+", str(ticker)) for ticker in tickers)
    assert {"NVDA", "TLT"} <= set(tickers)

    with pytest.raises(ValidationError):
        LegacyPositionCreate(
            symbol="\u041d\u0412\u0414\u0410",
            quantity=Decimal("1"),
            average_purchase_price=Decimal("100"),
            purchase_date="2026-01-01",
            currency="USD",
        )
