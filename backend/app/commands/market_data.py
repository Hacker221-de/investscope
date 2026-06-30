import argparse
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.repositories import MarketDataRepository


@dataclass(frozen=True, slots=True)
class DemoCleanupResult:
    found: int
    deleted: int


def purge_demo_market_bars(session: Session, *, confirmed: bool = False) -> DemoCleanupResult:
    """Delete only MarketBar rows whose provider is exactly ``demo``."""
    repository = MarketDataRepository(session)
    found = repository.count_bars("demo")
    if not confirmed:
        return DemoCleanupResult(found=found, deleted=0)
    deleted = repository.delete_demo_bars()
    session.commit()
    return DemoCleanupResult(found=found, deleted=deleted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InvestScope market-data maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    purge = subparsers.add_parser(
        "purge-demo-bars",
        help="delete only market_bars rows with provider=demo",
    )
    purge.add_argument(
        "--confirm",
        action="store_true",
        help="perform deletion; without this flag the command is a dry run",
    )
    arguments = parser.parse_args(argv)

    if arguments.command == "purge-demo-bars":
        with SessionLocal() as session:
            result = purge_demo_market_bars(session, confirmed=arguments.confirm)
        if arguments.confirm:
            print(f"Deleted demo MarketBar rows: {result.deleted}")
        else:
            print(f"Dry run: {result.found} demo MarketBar rows; nothing deleted")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
