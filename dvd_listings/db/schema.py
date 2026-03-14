"""
Database schema for DVD catalog cache.

This module defines the SQLite database schema for storing eBay catalog
product data retrieved via the Commerce Catalog API.
"""

import sqlite3
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta


# SQL statements for table creation
CREATE_CATALOG_PRODUCTS_TABLE = """
CREATE TABLE IF NOT EXISTS catalog_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    epid TEXT UNIQUE NOT NULL,
    upc TEXT NOT NULL,
    all_gtins TEXT,  -- JSON array of all GTINs

    -- Product info
    title TEXT,
    brand TEXT,

    -- Images
    primary_image_url TEXT,
    additional_images TEXT,  -- JSON array

    -- Media type
    media_type TEXT DEFAULT 'DVD',  -- DVD, CD, VHS

    -- DVD-specific aspects
    actors TEXT,  -- JSON array
    directors TEXT,  -- JSON array
    studio TEXT,
    release_year TEXT,
    format TEXT,  -- DVD, Blu-ray, etc.
    genre TEXT,
    rating TEXT,  -- MPAA rating
    region_code TEXT,

    -- Full aspects blob for flexibility
    aspects_json TEXT,  -- Full aspects array as JSON

    -- Category info
    primary_category_id TEXT,
    category_name TEXT,

    -- URLs
    product_api_url TEXT,
    product_web_url TEXT,

    -- Metadata
    fetched_at TIMESTAMP NOT NULL,
    cache_expires_at TIMESTAMP,
    fetch_source TEXT DEFAULT 'catalog_api'
);
"""

CREATE_CATALOG_LOOKUP_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS catalog_lookup_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    upc TEXT NOT NULL,
    found BOOLEAN NOT NULL,
    epid TEXT,
    lookup_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT
);
"""

# Index creation statements
CREATE_INDEXES = [
    # catalog_products indexes
    "CREATE INDEX IF NOT EXISTS idx_catalog_upc ON catalog_products(upc);",
    "CREATE INDEX IF NOT EXISTS idx_catalog_epid ON catalog_products(epid);",
    "CREATE INDEX IF NOT EXISTS idx_catalog_fetched ON catalog_products(fetched_at);",
    "CREATE INDEX IF NOT EXISTS idx_catalog_expires ON catalog_products(cache_expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_catalog_title ON catalog_products(title);",
    "CREATE INDEX IF NOT EXISTS idx_catalog_media_type ON catalog_products(media_type);",

    # catalog_lookup_log indexes
    "CREATE INDEX IF NOT EXISTS idx_lookup_upc ON catalog_lookup_log(upc);",
    "CREATE INDEX IF NOT EXISTS idx_lookup_date ON catalog_lookup_log(lookup_date);",
    "CREATE INDEX IF NOT EXISTS idx_lookup_found ON catalog_lookup_log(found);",
]


def init_database(db_path: str = "data/dvd_catalog.db") -> None:
    """
    Initialize the DVD catalog database with tables and indexes.

    Creates all tables and indexes if they don't exist. Safe to call
    multiple times (uses CREATE IF NOT EXISTS).

    Args:
        db_path: Path to SQLite database file

    Example:
        >>> init_database('data/dvd_catalog.db')
        ✓ Database initialized at data/dvd_catalog.db
    """
    # Create directory if it doesn't exist
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"Initializing database at: {db_path}")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Create tables
        print("  Creating tables...")
        cursor.execute(CREATE_CATALOG_PRODUCTS_TABLE)
        cursor.execute(CREATE_CATALOG_LOOKUP_LOG_TABLE)

        # Create indexes
        print("  Creating indexes...")
        for index_sql in CREATE_INDEXES:
            cursor.execute(index_sql)

        conn.commit()

        # Verify tables were created
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name;
        """)
        tables = [row[0] for row in cursor.fetchall()]

        print(f"  ✓ Created {len(tables)} table(s): {', '.join(tables)}")

    print(f"✓ Database initialized successfully")


def get_database_info(db_path: str = "data/dvd_catalog.db") -> dict:
    """
    Get information about the database.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Dictionary with database statistics

    Example:
        >>> info = get_database_info()
        >>> print(f"Products cached: {info['product_count']}")
    """
    if not Path(db_path).exists():
        return {
            'exists': False,
            'product_count': 0,
            'lookup_count': 0,
            'not_found_count': 0,
        }

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Count products
        cursor.execute("SELECT COUNT(*) FROM catalog_products;")
        product_count = cursor.fetchone()[0]

        # Count total lookups
        cursor.execute("SELECT COUNT(*) FROM catalog_lookup_log;")
        lookup_count = cursor.fetchone()[0]

        # Count not found
        cursor.execute("SELECT COUNT(*) FROM catalog_lookup_log WHERE found = 0;")
        not_found_count = cursor.fetchone()[0]

        # Get cache expiration info
        cursor.execute("""
            SELECT
                COUNT(*) as expired_count
            FROM catalog_products
            WHERE cache_expires_at < datetime('now');
        """)
        expired_count = cursor.fetchone()[0]

        # Get most recent fetch
        cursor.execute("""
            SELECT MAX(fetched_at) FROM catalog_products;
        """)
        last_fetch = cursor.fetchone()[0]

        return {
            'exists': True,
            'product_count': product_count,
            'lookup_count': lookup_count,
            'not_found_count': not_found_count,
            'expired_count': expired_count,
            'last_fetch': last_fetch,
        }


def clean_expired_cache(
    db_path: str = "data/dvd_catalog.db",
    dry_run: bool = False
) -> int:
    """
    Remove expired entries from the catalog cache.

    Args:
        db_path: Path to SQLite database file
        dry_run: If True, only count expired entries without deleting

    Returns:
        Number of expired entries (or that would be deleted in dry_run)

    Example:
        >>> count = clean_expired_cache(dry_run=True)
        >>> print(f"Would delete {count} expired products")
        >>> count = clean_expired_cache()
        >>> print(f"Deleted {count} expired products")
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Count expired entries
        cursor.execute("""
            SELECT COUNT(*) FROM catalog_products
            WHERE cache_expires_at < datetime('now');
        """)
        count = cursor.fetchone()[0]

        if not dry_run and count > 0:
            # Delete expired entries
            cursor.execute("""
                DELETE FROM catalog_products
                WHERE cache_expires_at < datetime('now');
            """)
            conn.commit()
            print(f"Deleted {count} expired product(s) from cache")
        elif count > 0:
            print(f"Found {count} expired product(s) (dry run mode)")

        return count


def expire_all_cache(
    db_path: str = "data/dvd_catalog.db"
) -> int:
    """
    Mark all active entries in the catalog cache as expired.
    Keeps historical records in the DB while preventing future exports.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Number of entries expired
    """
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Count non-expired entries
        cursor.execute("""
            SELECT COUNT(*) FROM catalog_products
            WHERE cache_expires_at >= datetime('now');
        """)
        count = cursor.fetchone()[0]

        if count > 0:
            cursor.execute("""
                UPDATE catalog_products
                SET cache_expires_at = datetime('now', '-1 second')
                WHERE cache_expires_at >= datetime('now');
            """)
            conn.commit()
            print(f"Expired {count} active product(s) in cache")

        return count


def migrate_add_media_type_column(
    db_path: str = "data/dvd_catalog.db"
) -> bool:
    """
    Add media_type column to existing catalog_products table.

    Safe to call on databases that already have the column.

    Args:
        db_path: Path to SQLite database file

    Returns:
        True if migration was applied, False if column already exists

    Example:
        >>> migrate_add_media_type_column('data/dvd_catalog.db')
        Added media_type column to catalog_products
        True
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(catalog_products);")
        columns = [row[1] for row in cursor.fetchall()]

        if 'media_type' in columns:
            print("  media_type column already exists, skipping migration")
            return False

        # Add the column
        print("  Adding media_type column to catalog_products...")
        cursor.execute("""
            ALTER TABLE catalog_products
            ADD COLUMN media_type TEXT DEFAULT 'DVD';
        """)

        # Create index
        print("  Creating index on media_type...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_catalog_media_type
            ON catalog_products(media_type);
        """)

        conn.commit()
        print("  ✓ Migration completed: media_type column added")
        return True


if __name__ == "__main__":
    """Test database initialization."""
    import sys

    print("DVD Catalog Database Schema Test")
    print("=" * 60)

    # Use test database
    test_db = "data/dvd_catalog_test.db"

    try:
        # Initialize
        init_database(test_db)
        print()

        # Get info
        print("Database Information:")
        info = get_database_info(test_db)
        for key, value in info.items():
            print(f"  {key}: {value}")
        print()

        print("✓ Schema test completed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
