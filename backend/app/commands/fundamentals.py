import argparse
from dataclasses import asdict
import json
from collections.abc import Sequence

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.modules.fundamental_analysis.manual_import import (
    SecImportError,
    SecManualJsonImportService,
)
from app.repositories import FundamentalRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.commands.fundamentals",
        description="Safe SEC company bootstrap commands.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_company = subparsers.add_parser(
        "set-company",
        help="Store a validated ticker, CIK and official company identity.",
    )
    set_company.add_argument("--symbol", required=True)
    set_company.add_argument("--cik", required=True)
    set_company.add_argument("--name", required=True)
    set_company.add_argument("--exchange")
    import_json = subparsers.add_parser(
        "import-sec-json",
        help="Import local official SEC submissions and companyfacts JSON files.",
    )
    import_json.add_argument("--symbol", required=True)
    import_json.add_argument("--submissions-file", required=True)
    import_json.add_argument("--companyfacts-file", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "set-company":
        with SessionLocal() as session:
            try:
                asset = FundamentalRepository(session).set_known_company(
                    symbol=args.symbol,
                    cik=args.cik,
                    legal_name=args.name,
                    exchange=args.exchange,
                )
            except ValueError as error:
                parser.error(str(error))
        print(
            f"Stored SEC company symbol={asset.symbol} cik={asset.cik} "
            f"exchange={asset.sec_exchange or '-'}"
        )
        return 0

    if args.command == "import-sec-json":
        with SessionLocal() as session:
            try:
                result = SecManualJsonImportService(
                    session,
                    max_file_mb=get_settings().sec_import_max_file_mb,
                ).import_files(
                    symbol=args.symbol,
                    submissions_file=args.submissions_file,
                    companyfacts_file=args.companyfacts_file,
                )
            except SecImportError as error:
                parser.error(f"{error.code}: {error}")
            except ValueError as error:
                parser.error(str(error))
        print(json.dumps(asdict(result), default=str, ensure_ascii=False, sort_keys=True))
        return 0

    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
