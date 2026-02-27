"""
Traffic sync service.

Fetches traffic data from Analytics API for both active and sold listings,
including promoted/organic breakdown with proper batching.
"""

from typing import Dict, Any, List, Optional
from ..api.analytics import AnalyticsAPIClient
from ..db.repository import TrafficRepository, SoldItemsRepository
from ..config import Config, DateRangeParser


class TrafficSyncService:
    """Service for syncing traffic data from Analytics API."""

    def __init__(self, config: Config):
        """
        Initialize traffic sync service.

        Args:
            config: Configuration object
        """
        self.config = config
        self.analytics_client = AnalyticsAPIClient(config)
        self.traffic_repo = TrafficRepository(config.db_path)
        self.sold_items_repo = SoldItemsRepository(config.db_path)

    def sync_traffic(
        self,
        start_date: str,
        end_date: str,
        include_sold: bool = True
    ) -> Dict[str, Any]:
        """
        Sync traffic data for both active and sold listings.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            include_sold: Whether to include sold listings (default: True)

        Returns:
            Dictionary with sync statistics
        """
        print(f"\n{'='*60}")
        print(f"TRAFFIC SYNC")
        print(f"{'='*60}\n")

        print(f"Date range: {start_date} to {end_date}")
        print(f"Include sold listings: {include_sold}")
        print()

        stats = {
            'active_listings': 0,
            'sold_listings': 0,
            'total_records': 0,
            'date_range': (start_date, end_date)
        }

        # Sync active listings traffic
        print(f"\n🔵 Syncing ACTIVE listings traffic...")
        print(f"{'='*60}\n")
        active_stats = self._sync_active_listings_traffic(start_date, end_date)
        stats['active_listings'] = active_stats['total_records']

        # Sync sold listings traffic
        if include_sold and self.config.sync_sold_items_enabled:
            print(f"\n🟢 Syncing SOLD listings traffic...")
            print(f"{'='*60}\n")
            sold_stats = self._sync_sold_listings_traffic(start_date, end_date)
            stats['sold_listings'] = sold_stats['total_records']
        else:
            print(f"\n⚠ Skipping sold listings sync (disabled or not requested)")

        stats['total_records'] = stats['active_listings'] + stats['sold_listings']

        print(f"\n✓ Traffic sync completed successfully")
        print(f"  Active listings: {stats['active_listings']} records")
        print(f"  Sold listings: {stats['sold_listings']} records")
        print(f"  Total: {stats['total_records']} records")
        print(f"{'='*60}\n")

        return stats

    def _sync_active_listings_traffic(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Sync traffic for active listings (1 API call).

        Note: Promoted vs organic breakdown is NOT supported by Analytics API.
        Only total traffic metrics are retrieved.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format

        Returns:
            Statistics dictionary
        """
        # Fetch total metrics
        print(f"📊 Fetching traffic metrics...")
        try:
            records = self.analytics_client.get_traffic_for_active_listings(
                start_date=start_date,
                end_date=end_date
            )
        except Exception as e:
            print(f"   ✗ Error: {e}")
            records = []

        # Convert to database format
        print(f"\n📊 Processing {len(records)} records...")
        db_records = self._convert_to_db_format(records, 'active', start_date, end_date)

        # Store in database
        print(f"💾 Storing {len(db_records)} active listing records...")
        if db_records:
            self.traffic_repo.bulk_upsert_traffic(db_records)
            print(f"   ✓ Stored successfully")
        else:
            print(f"   ⚠ No records to store")

        return {'total_records': len(db_records)}

    def _sync_sold_listings_traffic(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Sync traffic for sold listings with batching.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format

        Returns:
            Statistics dictionary
        """
        # Get sold item IDs from cache
        start_date_iso = DateRangeParser.parse_compact_date(start_date)
        end_date_iso = DateRangeParser.parse_compact_date(end_date)

        start_date_str = DateRangeParser.to_iso_format(start_date_iso)
        end_date_str = DateRangeParser.to_iso_format(end_date_iso)

        sold_item_ids = self.sold_items_repo.get_sold_items_in_range(
            start_date_str,
            end_date_str
        )

        if not sold_item_ids:
            # Try getting all sold items from last 90 days
            print(f"   No sold items found for date range, checking last 90 days...")
            sold_item_ids = self.sold_items_repo.get_unique_sold_item_ids(90)

        if not sold_item_ids:
            print(f"   ⚠ No sold items found in cache")
            print(f"   ℹ  Run 'sync-sold-items' first to populate sold items cache")
            return {'total_records': 0}

        print(f"   Found {len(sold_item_ids)} sold items to query")
        print()

        # Fetch traffic metrics
        batch_size = self.config.sold_items_batch_size

        print(f"📊 Fetching traffic metrics for sold items...")
        try:
            records = self.analytics_client.get_traffic_for_sold_listings(
                start_date=start_date,
                end_date=end_date,
                item_ids=sold_item_ids,
                batch_size=batch_size
            )
        except Exception as e:
            print(f"   ✗ Error: {e}")
            records = []

        # Convert to database format
        print(f"\n📊 Processing {len(records)} records...")
        db_records = self._convert_to_db_format(records, 'sold', start_date, end_date)

        # Store in database
        print(f"💾 Storing {len(db_records)} sold listing records...")
        if db_records:
            self.traffic_repo.bulk_upsert_traffic(db_records)
            print(f"   ✓ Stored successfully")
        else:
            print(f"   ⚠ No records to store")

        return {'total_records': len(db_records)}

    def _convert_to_db_format(
        self,
        records: List[Dict[str, Any]],
        listing_status: str,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Convert API records to database format.

        Note: Promoted vs organic breakdown is NOT available from the Analytics API.
        Those fields will be set to NULL.

        Args:
            records: Records from Analytics API
            listing_status: 'active' or 'sold'
            start_date: Start date for report
            end_date: End date for report

        Returns:
            List of database-ready dictionaries
        """
        from datetime import datetime

        db_records = []

        # Use middle of date range for report_date if not in API response
        # (Analytics API doesn't always include date per record)
        default_date = datetime.now().strftime('%Y-%m-%d')

        for record in records:
            # Extract item_id from dimensionValues
            dimension_values = record.get('dimensionValues', [])
            if not dimension_values or not dimension_values[0].get('value'):
                continue

            item_id = dimension_values[0]['value']

            # Extract metrics
            metrics = self._extract_metrics_from_record(record)

            # Build database record
            db_record = {
                'item_id': item_id,
                'report_date': default_date,  # API doesn't include date per record
                'listing_status': listing_status,
                # Total metrics
                'total_impressions': metrics.get('TOTAL_IMPRESSION_TOTAL'),
                'total_search_impressions': metrics.get('LISTING_IMPRESSION_SEARCH_RESULTS_PAGE'),
                'total_page_views': metrics.get('LISTING_VIEWS_TOTAL'),
                'transactions': metrics.get('TRANSACTION'),
                # Promoted metrics - NOT available from Analytics API (set to NULL)
                'promoted_total_impressions': None,
                'promoted_search_impressions': None,
                'promoted_page_views': None,
                # Organic metrics - NOT available from Analytics API (set to NULL)
                'organic_total_impressions': None,
                'organic_search_impressions': None,
                'organic_page_views': None
            }

            db_records.append(db_record)

        return db_records

    def _extract_metrics_from_record(self, record: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract metrics from Analytics API record.

        The Analytics API returns metrics in metricValues array.
        The order matches the order of metrics requested.

        Args:
            record: API record dictionary

        Returns:
            Dictionary of metric_name -> value
        """
        metrics = {}
        metric_values = record.get('metricValues', [])

        # Metrics are returned in the same order as requested:
        # ['TOTAL_IMPRESSION_TOTAL', 'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
        #  'LISTING_VIEWS_TOTAL', 'TRANSACTION']
        metric_names = [
            'TOTAL_IMPRESSION_TOTAL',
            'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
            'LISTING_VIEWS_TOTAL',
            'TRANSACTION'
        ]

        for i, metric_name in enumerate(metric_names):
            if i < len(metric_values):
                value = metric_values[i].get('value', 0)
                try:
                    metrics[metric_name] = int(value) if value else 0
                except (ValueError, TypeError):
                    metrics[metric_name] = 0
            else:
                metrics[metric_name] = 0

        return metrics

    def close(self):
        """Close API clients."""
        self.analytics_client.close()


if __name__ == "__main__":
    # Test traffic sync service
    from ..config import load_config, DateRangeParser

    print("Testing TrafficSyncService...\n")

    try:
        config = load_config()
        service = TrafficSyncService(config)

        print("✓ TrafficSyncService initialized")
        print()

        # Test date range
        start, end = DateRangeParser.get_date_range_last_n_days(7)
        print(f"Test date range: {start} to {end}")
        print()

        # Note: Actual sync requires valid token and will hit real API
        # Uncomment below to test with real API (uses your quota)

        # print("Running traffic sync...")
        # stats = service.sync_traffic(start, end, include_sold=True)
        # print(f"\nSync results:")
        # print(f"  Active listings: {stats['active_listings']}")
        # print(f"  Sold listings: {stats['sold_listings']}")
        # print(f"  Total: {stats['total_records']}")

        service.close()
        print("✓ Service closed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
