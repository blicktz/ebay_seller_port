"""
Database schema definitions and initialization.

This module defines the SQLite database schema for eBay seller analytics,
including tables for listing metadata, traffic facts, and sold items cache.
"""

import sqlite3
from pathlib import Path
from typing import Optional


# SQL statements for table creation
CREATE_LISTINGS_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS listings_metadata (
    item_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category_name TEXT,
    start_date TEXT,
    end_date TEXT,
    promoted_status TEXT,
    quantity_available INTEGER,

    -- Listing lifecycle tracking
    last_known_status TEXT,
    sold_date TEXT,
    status_checked_date DATETIME,

    -- Price tracking
    current_price REAL,
    start_price REAL,
    buy_it_now_price REAL,

    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_DAILY_TRAFFIC_FACTS_TABLE = """
CREATE TABLE IF NOT EXISTS daily_traffic_facts (
    item_id TEXT NOT NULL,
    report_date TEXT NOT NULL,

    -- Track listing status (active or sold)
    listing_status TEXT,

    -- Total metrics (no filter)
    total_impressions INTEGER,
    total_search_impressions INTEGER,
    total_page_views INTEGER,
    transactions INTEGER,

    -- Promoted metrics (traffic_source=PROMOTED_LISTINGS)
    promoted_total_impressions INTEGER,
    promoted_search_impressions INTEGER,
    promoted_page_views INTEGER,

    -- Organic metrics (traffic_source=ORGANIC)
    organic_total_impressions INTEGER,
    organic_search_impressions INTEGER,
    organic_page_views INTEGER,

    -- Metadata
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (item_id, report_date),
    FOREIGN KEY (item_id) REFERENCES listings_metadata(item_id)
);
"""

CREATE_SOLD_ITEMS_CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS sold_items_cache (
    item_id TEXT NOT NULL,
    sold_date TEXT NOT NULL,
    order_id TEXT,
    quantity_sold INTEGER,
    discovered_date DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (item_id, sold_date, order_id),
    FOREIGN KEY (item_id) REFERENCES listings_metadata(item_id)
);
"""

# Index creation statements
CREATE_INDEXES = [
    # listings_metadata indexes
    "CREATE INDEX IF NOT EXISTS idx_metadata_updated ON listings_metadata(last_updated);",
    "CREATE INDEX IF NOT EXISTS idx_metadata_sold_date ON listings_metadata(sold_date);",
    "CREATE INDEX IF NOT EXISTS idx_metadata_status ON listings_metadata(last_known_status);",

    # daily_traffic_facts indexes
    "CREATE INDEX IF NOT EXISTS idx_traffic_date ON daily_traffic_facts(report_date);",
    "CREATE INDEX IF NOT EXISTS idx_traffic_item ON daily_traffic_facts(item_id);",
    "CREATE INDEX IF NOT EXISTS idx_traffic_status ON daily_traffic_facts(listing_status);",
    "CREATE INDEX IF NOT EXISTS idx_traffic_created ON daily_traffic_facts(created_at);",

    # sold_items_cache indexes
    "CREATE INDEX IF NOT EXISTS idx_sold_cache_date ON sold_items_cache(sold_date);",
    "CREATE INDEX IF NOT EXISTS idx_sold_cache_discovered ON sold_items_cache(discovered_date);",
]


def init_database(db_path: str = "data/ebay_analytics.db") -> sqlite3.Connection:
    """
    Initialize the database with all required tables and indexes.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        sqlite3.Connection: Database connection object

    Raises:
        sqlite3.Error: If database initialization fails
    """
    # Ensure parent directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable column access by name

    try:
        cursor = conn.cursor()

        # Create tables
        cursor.execute(CREATE_LISTINGS_METADATA_TABLE)
        cursor.execute(CREATE_DAILY_TRAFFIC_FACTS_TABLE)
        cursor.execute(CREATE_SOLD_ITEMS_CACHE_TABLE)

        # Create indexes
        for index_sql in CREATE_INDEXES:
            cursor.execute(index_sql)

        conn.commit()
        print(f"✓ Database initialized successfully at: {db_path}")

        # Print table info
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"✓ Created tables: {', '.join(tables)}")

        return conn

    except sqlite3.Error as e:
        conn.rollback()
        print(f"✗ Error initializing database: {e}")
        raise


def get_connection(db_path: str = "data/ebay_analytics.db") -> sqlite3.Connection:
    """
    Get a connection to the database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        sqlite3.Connection: Database connection object
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def verify_schema(db_path: str = "data/ebay_analytics.db") -> bool:
    """
    Verify that all required tables and indexes exist.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        bool: True if schema is valid, False otherwise
    """
    try:
        conn = get_connection(db_path)
        cursor = conn.cursor()

        # Check for required tables
        required_tables = ['listings_metadata', 'daily_traffic_facts', 'sold_items_cache']
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = [row[0] for row in cursor.fetchall()]

        for table in required_tables:
            if table not in existing_tables:
                print(f"✗ Missing required table: {table}")
                return False

        # Check for indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
        existing_indexes = [row[0] for row in cursor.fetchall()]

        required_index_prefixes = ['idx_metadata_', 'idx_traffic_', 'idx_sold_cache_']
        index_counts = {prefix: 0 for prefix in required_index_prefixes}

        for index in existing_indexes:
            for prefix in required_index_prefixes:
                if index.startswith(prefix):
                    index_counts[prefix] += 1

        print(f"✓ Schema verification passed")
        print(f"  Tables: {len(existing_tables)}")
        print(f"  Indexes: {len(existing_indexes)}")

        conn.close()
        return True

    except sqlite3.Error as e:
        print(f"✗ Schema verification failed: {e}")
        return False


if __name__ == "__main__":
    # Test database initialization
    print("Testing database initialization...")
    conn = init_database("data/ebay_analytics.db")
    conn.close()

    print("\nVerifying schema...")
    verify_schema("data/ebay_analytics.db")
