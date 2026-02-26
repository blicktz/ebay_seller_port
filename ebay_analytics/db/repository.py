"""
Database repository layer for CRUD operations.

Provides data access methods for all three tables:
- listings_metadata
- daily_traffic_facts
- sold_items_cache
"""

import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from .schema import get_connection


class MetadataRepository:
    """Repository for listings_metadata table."""

    def __init__(self, db_path: str = "data/ebay_analytics.db"):
        """
        Initialize metadata repository.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path

    def upsert_listing(
        self,
        item_id: str,
        title: str,
        category_name: Optional[str] = None,
        start_date: Optional[str] = None,
        promoted_status: Optional[str] = None,
        quantity_available: Optional[int] = None,
        last_known_status: Optional[str] = None,
        sold_date: Optional[str] = None
    ) -> None:
        """
        Insert or update listing metadata.

        Args:
            item_id: eBay item ID
            title: Listing title
            category_name: Category name
            start_date: Listing start date (YYYY-MM-DD)
            promoted_status: Promoted status
            quantity_available: Quantity available
            last_known_status: Last known status ('active', 'sold', etc.)
            sold_date: Date item sold (YYYY-MM-DD)
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO listings_metadata (
                item_id, title, category_name, start_date, promoted_status,
                quantity_available, last_known_status, sold_date, status_checked_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(item_id) DO UPDATE SET
                title = excluded.title,
                category_name = COALESCE(excluded.category_name, category_name),
                start_date = COALESCE(excluded.start_date, start_date),
                promoted_status = COALESCE(excluded.promoted_status, promoted_status),
                quantity_available = excluded.quantity_available,
                last_known_status = COALESCE(excluded.last_known_status, last_known_status),
                sold_date = COALESCE(excluded.sold_date, sold_date),
                status_checked_date = CURRENT_TIMESTAMP,
                last_updated = CURRENT_TIMESTAMP
        """, (item_id, title, category_name, start_date, promoted_status,
              quantity_available, last_known_status, sold_date))

        conn.commit()
        conn.close()

    def bulk_upsert_listings(self, listings: List[Dict[str, Any]]) -> int:
        """
        Bulk insert or update multiple listings.

        Args:
            listings: List of listing dictionaries

        Returns:
            Number of listings processed
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        for listing in listings:
            cursor.execute("""
                INSERT INTO listings_metadata (
                    item_id, title, category_name, start_date, promoted_status,
                    quantity_available, last_known_status, sold_date, status_checked_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(item_id) DO UPDATE SET
                    title = excluded.title,
                    category_name = COALESCE(excluded.category_name, category_name),
                    start_date = COALESCE(excluded.start_date, start_date),
                    promoted_status = COALESCE(excluded.promoted_status, promoted_status),
                    quantity_available = excluded.quantity_available,
                    last_known_status = COALESCE(excluded.last_known_status, last_known_status),
                    sold_date = COALESCE(excluded.sold_date, sold_date),
                    status_checked_date = CURRENT_TIMESTAMP,
                    last_updated = CURRENT_TIMESTAMP
            """, (
                listing.get('item_id'),
                listing.get('title'),
                listing.get('category_name'),
                listing.get('start_date'),
                listing.get('promoted_status'),
                listing.get('quantity_available'),
                listing.get('last_known_status'),
                listing.get('sold_date')
            ))

        conn.commit()
        count = len(listings)
        conn.close()

        return count

    def get_listing(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get listing metadata by item ID."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM listings_metadata WHERE item_id = ?", (item_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    def get_all_listings(self) -> List[Dict[str, Any]]:
        """Get all listings metadata."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM listings_metadata ORDER BY item_id")
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]


class TrafficRepository:
    """Repository for daily_traffic_facts table."""

    def __init__(self, db_path: str = "data/ebay_analytics.db"):
        """
        Initialize traffic repository.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path

    def upsert_traffic(
        self,
        item_id: str,
        report_date: str,
        listing_status: str,
        total_impressions: Optional[int] = None,
        total_search_impressions: Optional[int] = None,
        total_page_views: Optional[int] = None,
        transactions: Optional[int] = None,
        promoted_total_impressions: Optional[int] = None,
        promoted_search_impressions: Optional[int] = None,
        promoted_page_views: Optional[int] = None,
        organic_total_impressions: Optional[int] = None,
        organic_search_impressions: Optional[int] = None,
        organic_page_views: Optional[int] = None
    ) -> None:
        """
        Insert or update traffic facts.

        Args:
            item_id: eBay item ID
            report_date: Date in YYYY-MM-DD format
            listing_status: 'active' or 'sold'
            total_impressions: Total impressions
            total_search_impressions: Search impressions
            total_page_views: Total page views
            transactions: Number of transactions
            promoted_total_impressions: Promoted total impressions
            promoted_search_impressions: Promoted search impressions
            promoted_page_views: Promoted page views
            organic_total_impressions: Organic total impressions
            organic_search_impressions: Organic search impressions
            organic_page_views: Organic page views
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO daily_traffic_facts (
                item_id, report_date, listing_status,
                total_impressions, total_search_impressions, total_page_views, transactions,
                promoted_total_impressions, promoted_search_impressions, promoted_page_views,
                organic_total_impressions, organic_search_impressions, organic_page_views
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id, report_date) DO UPDATE SET
                listing_status = excluded.listing_status,
                total_impressions = COALESCE(excluded.total_impressions, total_impressions),
                total_search_impressions = COALESCE(excluded.total_search_impressions, total_search_impressions),
                total_page_views = COALESCE(excluded.total_page_views, total_page_views),
                transactions = COALESCE(excluded.transactions, transactions),
                promoted_total_impressions = COALESCE(excluded.promoted_total_impressions, promoted_total_impressions),
                promoted_search_impressions = COALESCE(excluded.promoted_search_impressions, promoted_search_impressions),
                promoted_page_views = COALESCE(excluded.promoted_page_views, promoted_page_views),
                organic_total_impressions = COALESCE(excluded.organic_total_impressions, organic_total_impressions),
                organic_search_impressions = COALESCE(excluded.organic_search_impressions, organic_search_impressions),
                organic_page_views = COALESCE(excluded.organic_page_views, organic_page_views)
        """, (item_id, report_date, listing_status,
              total_impressions, total_search_impressions, total_page_views, transactions,
              promoted_total_impressions, promoted_search_impressions, promoted_page_views,
              organic_total_impressions, organic_search_impressions, organic_page_views))

        conn.commit()
        conn.close()

    def bulk_upsert_traffic(self, traffic_records: List[Dict[str, Any]]) -> int:
        """
        Bulk insert or update multiple traffic records.

        Args:
            traffic_records: List of traffic dictionaries

        Returns:
            Number of records processed
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        for record in traffic_records:
            cursor.execute("""
                INSERT INTO daily_traffic_facts (
                    item_id, report_date, listing_status,
                    total_impressions, total_search_impressions, total_page_views, transactions,
                    promoted_total_impressions, promoted_search_impressions, promoted_page_views,
                    organic_total_impressions, organic_search_impressions, organic_page_views
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id, report_date) DO UPDATE SET
                    listing_status = excluded.listing_status,
                    total_impressions = COALESCE(excluded.total_impressions, total_impressions),
                    total_search_impressions = COALESCE(excluded.total_search_impressions, total_search_impressions),
                    total_page_views = COALESCE(excluded.total_page_views, total_page_views),
                    transactions = COALESCE(excluded.transactions, transactions),
                    promoted_total_impressions = COALESCE(excluded.promoted_total_impressions, promoted_total_impressions),
                    promoted_search_impressions = COALESCE(excluded.promoted_search_impressions, promoted_search_impressions),
                    promoted_page_views = COALESCE(excluded.promoted_page_views, promoted_page_views),
                    organic_total_impressions = COALESCE(excluded.organic_total_impressions, organic_total_impressions),
                    organic_search_impressions = COALESCE(excluded.organic_search_impressions, organic_search_impressions),
                    organic_page_views = COALESCE(excluded.organic_page_views, organic_page_views)
            """, (
                record.get('item_id'),
                record.get('report_date'),
                record.get('listing_status'),
                record.get('total_impressions'),
                record.get('total_search_impressions'),
                record.get('total_page_views'),
                record.get('transactions'),
                record.get('promoted_total_impressions'),
                record.get('promoted_search_impressions'),
                record.get('promoted_page_views'),
                record.get('organic_total_impressions'),
                record.get('organic_search_impressions'),
                record.get('organic_page_views')
            ))

        conn.commit()
        count = len(traffic_records)
        conn.close()

        return count

    def get_traffic_for_date_range(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """Get traffic data for date range."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM daily_traffic_facts
            WHERE report_date BETWEEN ? AND ?
            ORDER BY report_date DESC, item_id
        """, (start_date, end_date))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]


class SoldItemsRepository:
    """Repository for sold_items_cache table."""

    def __init__(self, db_path: str = "data/ebay_analytics.db"):
        """
        Initialize sold items repository.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path

    def insert_sold_item(
        self,
        item_id: str,
        sold_date: str,
        order_id: str,
        quantity_sold: int
    ) -> None:
        """
        Insert sold item (idempotent due to PRIMARY KEY).

        Args:
            item_id: eBay item ID
            sold_date: Date sold (YYYY-MM-DD)
            order_id: eBay order ID
            quantity_sold: Quantity sold
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO sold_items_cache (
                item_id, sold_date, order_id, quantity_sold
            )
            VALUES (?, ?, ?, ?)
        """, (item_id, sold_date, order_id, quantity_sold))

        conn.commit()
        conn.close()

    def bulk_insert_sold_items(self, sold_items: List[Dict[str, Any]]) -> int:
        """
        Bulk insert sold items.

        Args:
            sold_items: List of sold item dictionaries

        Returns:
            Number of new items inserted
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        inserted = 0
        for item in sold_items:
            cursor.execute("""
                INSERT OR IGNORE INTO sold_items_cache (
                    item_id, sold_date, order_id, quantity_sold
                )
                VALUES (?, ?, ?, ?)
            """, (
                item.get('item_id'),
                item.get('sold_date'),
                item.get('order_id'),
                item.get('quantity', 1)
            ))
            inserted += cursor.rowcount

        conn.commit()
        conn.close()

        return inserted

    def get_sold_items_in_range(
        self,
        start_date: str,
        end_date: str
    ) -> List[str]:
        """
        Get unique sold item IDs for date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of unique item IDs
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT item_id
            FROM sold_items_cache
            WHERE sold_date BETWEEN ? AND ?
            ORDER BY item_id
        """, (start_date, end_date))

        rows = cursor.fetchall()
        conn.close()

        return [row[0] for row in rows]

    def get_unique_sold_item_ids(self, days_back: int = 90) -> List[str]:
        """
        Get all unique sold item IDs from last N days.

        Args:
            days_back: Number of days to look back

        Returns:
            List of unique item IDs
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT item_id
            FROM sold_items_cache
            WHERE sold_date >= date('now', '-' || ? || ' days')
            ORDER BY item_id
        """, (days_back,))

        rows = cursor.fetchall()
        conn.close()

        return [row[0] for row in rows]


if __name__ == "__main__":
    # Test repository layer
    from .schema import init_database

    print("Testing repository layer...\n")

    # Initialize test database
    test_db = "data/test_repository.db"
    conn = init_database(test_db)
    conn.close()

    # Test MetadataRepository
    print("Testing MetadataRepository...")
    meta_repo = MetadataRepository(test_db)

    meta_repo.upsert_listing(
        item_id="123456789",
        title="Test Product",
        category_name="Test Category",
        quantity_available=10,
        last_known_status="active"
    )
    print("  ✓ Inserted test listing")

    listing = meta_repo.get_listing("123456789")
    print(f"  ✓ Retrieved listing: {listing['title']}")

    # Test TrafficRepository
    print("\nTesting TrafficRepository...")
    traffic_repo = TrafficRepository(test_db)

    traffic_repo.upsert_traffic(
        item_id="123456789",
        report_date="2026-02-25",
        listing_status="active",
        total_impressions=100,
        total_page_views=50,
        transactions=2
    )
    print("  ✓ Inserted test traffic data")

    # Test SoldItemsRepository
    print("\nTesting SoldItemsRepository...")
    sold_repo = SoldItemsRepository(test_db)

    sold_repo.insert_sold_item(
        item_id="987654321",
        sold_date="2026-02-20",
        order_id="ORD-123",
        quantity_sold=1
    )
    print("  ✓ Inserted test sold item")

    sold_ids = sold_repo.get_unique_sold_item_ids(90)
    print(f"  ✓ Retrieved {len(sold_ids)} sold item IDs")

    print("\n✓ All repository tests passed!")
