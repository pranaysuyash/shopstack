import argparse
from pathlib import Path

from shopstack.config import settings
from shopstack.market.sources.swiggy import load_snapshot
from shopstack.persistence.database import Database


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, help="Path to data dir")
    args = parser.parse_args()

    db = Database(settings.db_path)
    data_dir = Path(args.data_dir) if args.data_dir else None
    snapshot = load_snapshot(data_dir=data_dir)

    db.save_market_snapshot(snapshot)

    print("Imported Swiggy snapshot into ShopStack database.")
    print(f"Snapshot ID: {snapshot.snapshot_id}")
    print(f"Imported records: {len(snapshot.normalized_records)}")


if __name__ == "__main__":
    main()
