"""
Database migration: Add view source breakdown columns to daily_traffic_facts table.

This migration adds the following columns:
- views_source_direct
- views_source_off_ebay
- views_source_other_ebay
- views_source_search_results
- views_source_store

These columns capture the breakdown of listing views by traffic source from the
eBay Analytics API LISTING_VIEWS_SOURCE_* metrics.
"""

import sqlite3
from pathlib import Path

def migrate_database(db_path: str = "data/ebay_analytics.db"):
    """Add view source columns to daily_traffic_facts table."""

    if not Path(db_path).exists():
        print(f"Database not found at {db_path}")
        return

    print(f"\n{'='*60}")
    print("Database Migration: Add View Source Columns")
    print(f"{'='*60}\n")
    print(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(daily_traffic_facts)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    new_columns = [
        'views_source_direct',
        'views_source_off_ebay',
        'views_source_other_ebay',
        'views_source_search_results',
        'views_source_store'
    ]

    columns_to_add = [col for col in new_columns if col not in existing_columns]

    if not columns_to_add:
        print("✓ All view source columns already exist. No migration needed.\n")
        conn.close()
        return

    print(f"Adding {len(columns_to_add)} new columns:\n")

    # Add each column
    for column_name in columns_to_add:
        print(f"  • {column_name}")
        try:
            cursor.execute(f"""
                ALTER TABLE daily_traffic_facts
                ADD COLUMN {column_name} INTEGER
            """)
            print(f"    ✓ Added successfully")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"    ⚠ Column already exists, skipping")
            else:
                print(f"    ✗ Error: {e}")
                raise

    conn.commit()

    # Verify columns were added
    cursor.execute("PRAGMA table_info(daily_traffic_facts)")
    final_columns = {row[1] for row in cursor.fetchall()}

    print(f"\n{'='*60}")
    print("Migration Summary")
    print(f"{'='*60}\n")

    for col in new_columns:
        status = "✓" if col in final_columns else "✗"
        print(f"  {status} {col}")

    print(f"\n{'='*60}")
    print("✓ Migration completed successfully")
    print(f"{'='*60}\n")

    conn.close()

if __name__ == "__main__":
    migrate_database()
