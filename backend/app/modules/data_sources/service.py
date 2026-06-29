from decimal import Decimal
from typing import cast

from app.demo_data import ASSETS


class DemoMarketDataSource:
    """Deterministic in-process data source used until real read-only feeds are configured."""

    def list_assets(self) -> list[dict[str, object]]:
        return [asset.copy() for asset in ASSETS]

    def price_for(self, symbol: str) -> Decimal | None:
        asset = next((item for item in ASSETS if item["symbol"] == symbol.upper()), None)
        return cast(Decimal, asset["price"]) if asset is not None else None
