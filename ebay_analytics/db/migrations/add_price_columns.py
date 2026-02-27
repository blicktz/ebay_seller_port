"""
Database migration: Add price columns to listings_metadata table.

Adds current_price, start_price, and buy_it_now_price columns.
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import load_config


def migrate(db_path: str):
    """
    Add price columns to listings_metadata table.

    Args:
        db_path: Path to SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Adding price columns to listings_metadata table...")

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(listings_metadata)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'current_price' not in columns:
            cursor.execute("ALTER TABLE listings_metadata ADD COLUMN current_price REAL")
            print("  ✓ Added current_price column")
        else:
            print("  - current_price column already exists")

        if 'start_price' not in columns:
            cursor.execute("ALTER TABLE listings_metadata ADD COLUMN start_price REAL")
            print("  ✓ Added start_price column")
        else:
            print("  - start_price column already exists")

        if 'buy_it_now_price' not in columns:
            cursor.execute("ALTER TABLE listings_metadata ADD COLUMN buy_it_now_price REAL")
            print("  ✓ Added buy_it_now_price column")
        else:
            print("  - buy_it_now_price column already exists")

        conn.commit()
        print("\n✓ Migration completed successfully")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    config = load_config()
    migrate(config.db_path)
