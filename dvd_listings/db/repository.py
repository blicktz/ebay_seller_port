"""
Repository for DVD catalog data access.

Provides a data access layer for storing and retrieving eBay catalog
product information from the SQLite database.
"""

import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json

from ..models.product import CatalogProduct


class CatalogRepository:
    """Repository for accessing DVD catalog data in the database."""

    def __init__(self, db_path: str = "data/dvd_catalog.db"):
        """
        Initialize catalog repository.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure database directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    def save_product(
        self,
        product: CatalogProduct,
        cache_expiry_days: int = 30
    ) -> None:
        """
        Save or update a catalog product in the database.

        Args:
            product: CatalogProduct instance to save
            cache_expiry_days: Number of days before cache expires (default: 30)

        Example:
            >>> repo = CatalogRepository()
            >>> product = CatalogProduct.from_api_response(api_data)
            >>> repo.save_product(product)
        """
        # Set cache expiration if not already set
        if not product.cache_expires_at:
            product.cache_expires_at = datetime.now() + timedelta(days=cache_expiry_days)

        # Convert product to database dict
        data = product.to_db_dict()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Upsert (INSERT OR REPLACE)
            cursor.execute("""
                INSERT OR REPLACE INTO catalog_products (
                    epid, upc, all_gtins, title, brand, media_type,
                    primary_image_url, additional_images,
                    actors, directors, studio, release_year, format, genre, rating, region_code,
                    aspects_json, primary_category_id, category_name,
                    product_api_url, product_web_url,
                    fetched_at, cache_expires_at, fetch_source
                ) VALUES (
                    :epid, :upc, :all_gtins, :title, :brand, :media_type,
                    :primary_image_url, :additional_images,
                    :actors, :directors, :studio, :release_year, :format, :genre, :rating, :region_code,
                    :aspects_json, :primary_category_id, :category_name,
                    :product_api_url, :product_web_url,
                    :fetched_at, :cache_expires_at, :fetch_source
                )
            """, data)

            conn.commit()

    def get_product_by_upc(
        self,
        upc: str,
        include_expired: bool = False
    ) -> Optional[CatalogProduct]:
        """
        Retrieve a catalog product by UPC.

        Args:
            upc: UPC code to search for
            include_expired: If False, only return non-expired cached entries

        Returns:
            CatalogProduct instance or None if not found

        Example:
            >>> repo = CatalogRepository()
            >>> product = repo.get_product_by_upc('0786936735390')
            >>> if product:
            ...     print(product.title)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if include_expired:
                cursor.execute("""
                    SELECT * FROM catalog_products
                    WHERE upc = ?
                    LIMIT 1
                """, (upc,))
            else:
                cursor.execute("""
                    SELECT * FROM catalog_products
                    WHERE upc = ?
                      AND (cache_expires_at IS NULL OR cache_expires_at > datetime('now'))
                    LIMIT 1
                """, (upc,))

            row = cursor.fetchone()

            if row:
                return CatalogProduct.from_db_row(dict(row))
            return None

    def get_products_by_upc(
        self,
        upc: str,
        include_expired: bool = False
    ) -> List[CatalogProduct]:
        """
        Retrieve ALL catalog products matching a UPC.

        This method returns all products for a given UPC, which is important
        because one UPC can match multiple editions/versions (e.g., different
        years, regions, or formats of the same DVD).

        Args:
            upc: UPC code to search for
            include_expired: If False, only return non-expired cached entries

        Returns:
            List of CatalogProduct instances (may be empty)

        Example:
            >>> repo = CatalogRepository()
            >>> products = repo.get_products_by_upc('883929304127')
            >>> print(f"Found {len(products)} edition(s)")
            >>> for product in products:
            ...     print(f"  - {product.title}")
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if include_expired:
                cursor.execute("""
                    SELECT * FROM catalog_products
                    WHERE upc = ?
                    ORDER BY fetched_at DESC
                """, (upc,))
            else:
                cursor.execute("""
                    SELECT * FROM catalog_products
                    WHERE upc = ?
                      AND (cache_expires_at IS NULL OR cache_expires_at > datetime('now'))
                    ORDER BY fetched_at DESC
                """, (upc,))

            rows = cursor.fetchall()
            return [CatalogProduct.from_db_row(dict(row)) for row in rows]

    def get_product_by_epid(self, epid: str) -> Optional[CatalogProduct]:
        """
        Retrieve a catalog product by ePID.

        Args:
            epid: eBay Product ID

        Returns:
            CatalogProduct instance or None if not found

        Example:
            >>> product = repo.get_product_by_epid('123456789')
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM catalog_products
                WHERE epid = ?
                LIMIT 1
            """, (epid,))

            row = cursor.fetchone()

            if row:
                return CatalogProduct.from_db_row(dict(row))
            return None

    def log_lookup(
        self,
        upc: str,
        found: bool,
        epid: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Log a catalog lookup attempt.

        Args:
            upc: UPC code that was searched
            found: Whether the UPC was found in the catalog
            epid: eBay Product ID if found
            error_message: Error message if lookup failed

        Example:
            >>> repo.log_lookup('0786936735390', found=True, epid='123456')
            >>> repo.log_lookup('9999999999999', found=False)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO catalog_lookup_log (upc, found, epid, error_message)
                VALUES (?, ?, ?, ?)
            """, (upc, found, epid, error_message))

            conn.commit()

    def get_not_found_upcs(
        self,
        since_date: Optional[datetime] = None
    ) -> List[str]:
        """
        Get list of UPCs that were not found in the catalog.

        Args:
            since_date: Optional date filter (only lookups after this date)

        Returns:
            List of UPC codes not found in catalog

        Example:
            >>> repo = CatalogRepository()
            >>> not_found = repo.get_not_found_upcs()
            >>> print(f"Missing {len(not_found)} UPCs from catalog")
            >>> for upc in not_found:
            ...     print(f"  - {upc}")
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if since_date:
                cursor.execute("""
                    SELECT DISTINCT upc
                    FROM catalog_lookup_log
                    WHERE found = 0 AND lookup_date >= ?
                    ORDER BY upc
                """, (since_date.isoformat(),))
            else:
                cursor.execute("""
                    SELECT DISTINCT upc
                    FROM catalog_lookup_log
                    WHERE found = 0
                    ORDER BY upc
                """)

            return [row[0] for row in cursor.fetchall()]

    def get_all_products(
        self,
        include_expired: bool = False,
        limit: Optional[int] = None,
        media_type: Optional[str] = None
    ) -> List[CatalogProduct]:
        """
        Get all catalog products from the database.

        Args:
            include_expired: If False, only return non-expired cached entries
            limit: Optional limit on number of products to return
            media_type: Optional filter by media type (DVD, CD, VHS)

        Returns:
            List of CatalogProduct instances

        Example:
            >>> products = repo.get_all_products(limit=100, media_type='CD')
            >>> for product in products:
            ...     print(f"{product.upc}: {product.title}")
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            conditions = []
            params = []

            # Cache expiration filter
            if not include_expired:
                conditions.append("(cache_expires_at IS NULL OR cache_expires_at > datetime('now'))")

            # Media type filter
            if media_type:
                conditions.append("media_type = ?")
                params.append(media_type)

            # Build query
            if conditions:
                where_clause = " WHERE " + " AND ".join(conditions)
            else:
                where_clause = ""

            query = f"SELECT * FROM catalog_products{where_clause} ORDER BY fetched_at DESC"

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [CatalogProduct.from_db_row(dict(row)) for row in rows]

    def search_products(
        self,
        title_search: Optional[str] = None,
        genre: Optional[str] = None,
        year: Optional[str] = None,
        limit: int = 50
    ) -> List[CatalogProduct]:
        """
        Search products by various criteria.

        Args:
            title_search: Search term for title (case-insensitive)
            genre: Filter by genre
            year: Filter by release year
            limit: Maximum number of results

        Returns:
            List of matching CatalogProduct instances

        Example:
            >>> products = repo.search_products(title_search='Star Wars')
            >>> products = repo.search_products(genre='Action', year='2010')
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            conditions = []
            params = []

            if title_search:
                conditions.append("title LIKE ?")
                params.append(f"%{title_search}%")

            if genre:
                conditions.append("genre = ?")
                params.append(genre)

            if year:
                conditions.append("release_year = ?")
                params.append(year)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT * FROM catalog_products
                WHERE {where_clause}
                ORDER BY title
                LIMIT ?
            """
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [CatalogProduct.from_db_row(dict(row)) for row in rows]

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the catalog cache.

        Returns:
            Dictionary with various statistics

        Example:
            >>> stats = repo.get_statistics()
            >>> print(f"Total products: {stats['total_products']}")
            >>> print(f"Expired: {stats['expired_count']}")
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total products
            cursor.execute("SELECT COUNT(*) FROM catalog_products")
            total_products = cursor.fetchone()[0]

            # Expired count
            cursor.execute("""
                SELECT COUNT(*) FROM catalog_products
                WHERE cache_expires_at < datetime('now')
            """)
            expired_count = cursor.fetchone()[0]

            # Total lookups
            cursor.execute("SELECT COUNT(*) FROM catalog_lookup_log")
            total_lookups = cursor.fetchone()[0]

            # Not found count
            cursor.execute("SELECT COUNT(DISTINCT upc) FROM catalog_lookup_log WHERE found = 0")
            not_found_count = cursor.fetchone()[0]

            # Most recent fetch
            cursor.execute("SELECT MAX(fetched_at) FROM catalog_products")
            last_fetch = cursor.fetchone()[0]

            # Genre distribution
            cursor.execute("""
                SELECT genre, COUNT(*) as count
                FROM catalog_products
                WHERE genre IS NOT NULL
                GROUP BY genre
                ORDER BY count DESC
                LIMIT 10
            """)
            genre_distribution = [(row[0], row[1]) for row in cursor.fetchall()]

            return {
                'total_products': total_products,
                'expired_count': expired_count,
                'active_count': total_products - expired_count,
                'total_lookups': total_lookups,
                'not_found_count': not_found_count,
                'last_fetch': last_fetch,
                'genre_distribution': genre_distribution,
            }


if __name__ == "__main__":
    """Test repository functionality."""
    from .schema import init_database

    print("Testing CatalogRepository...")
    print("=" * 60)

    # Initialize test database
    test_db = "data/dvd_catalog_test.db"
    init_database(test_db)
    print()

    # Create repository
    repo = CatalogRepository(test_db)
    print("✓ Repository initialized")
    print()

    # Test statistics
    print("Statistics:")
    stats = repo.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print()

    print("✓ Repository test completed successfully")
