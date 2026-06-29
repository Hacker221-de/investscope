from decimal import Decimal

from app.modules.data_sources import DemoMarketDataSource
from app.modules.forecasting import linear_projection
from app.modules.fundamental_analysis import fundamental_score
from app.modules.political_analysis import political_risk_score
from app.modules.technical_analysis import moving_average_signal


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

