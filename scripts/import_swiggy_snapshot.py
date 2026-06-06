from shopstack.config import settings
from shopstack.data_sources.swiggy import import_swiggy_fresh_vegetables_snapshot
from shopstack.persistence.database import Database


def main() -> None:
    db = Database(settings.db_path)
    summary = import_swiggy_fresh_vegetables_snapshot(db)
    print("Imported Swiggy snapshot into ShopStack database.")
    print(f"Source file: {summary['source_file']}")
    print(f"Imported records: {summary['imported_records']}")
    print(f"Skipped records: {summary['skipped_records']}")
    print(f"Unique items: {summary['unique_items']}")
    print("Top discounts:")
    for item in summary["top_discounts"]:
        print(f" - {item['name']} ({item['canonical_name']}): {item['price_inr']} INR, {item['discount_percent']}%")


if __name__ == "__main__":
    main()
