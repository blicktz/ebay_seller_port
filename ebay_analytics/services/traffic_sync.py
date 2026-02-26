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
        Sync traffic for active listings (3 API calls).

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format

        Returns:
            Statistics dictionary
        """
        # Call 1: Total metrics (no filter)
        print(f"1️⃣  Fetching TOTAL metrics...")
        try:
            total_records = self.analytics_client.get_traffic_for_active_listings(
                start_date=start_date,
                end_date=end_date,
                traffic_source=None
            )
        except Exception as e:
            print(f"   ✗ Error: {e}")
            total_records = []

        # Call 2: Promoted metrics
        print(f"\n2️⃣  Fetching PROMOTED metrics...")
        try:
            promoted_records = self.analytics_client.get_traffic_for_active_listings(
                start_date=start_date,
                end_date=end_date,
                traffic_source='PROMOTED_LISTINGS'
            )
        except Exception as e:
            print(f"   ✗ Error: {e}")
            promoted_records = []

        # Call 3: Organic metrics
        print(f"\n3️⃣  Fetching ORGANIC metrics...")
        try:
            organic_records = self.analytics_client.get_traffic_for_active_listings(
                start_date=start_date,
                end_date=end_date,
                traffic_source='ORGANIC'
            )
        except Exception as e:
            print(f"   ✗ Error: {e}")
            organic_records = []

        # Merge data
        print(f"\n📊 Merging active listings data...")
        merged_records = self._merge_traffic_data(
            total_records=total_records,
            promoted_records=promoted_records,
            organic_records=organic_records,
            listing_status='active'
        )

        # Store in database
        print(f"💾 Storing {len(merged_records)} active listing records...")
        if merged_records:
            self.traffic_repo.bulk_upsert_traffic(merged_records)
            print(f"   ✓ Stored successfully")
        else:
            print(f"   ⚠ No records to store")

        return {'total_records': len(merged_records)}

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

        # Fetch traffic with batching (3 calls per batch)
        batch_size = self.config.sold_items_batch_size

        # Call 1: Total metrics
        print(f"1️⃣  Fetching TOTAL metrics for sold items...")
        try:
            total_records = self.analytics_client.get_traffic_for_sold_listings(
                start_date=start_date,
                end_date=end_date,
                item_ids=sold_item_ids,
                traffic_source=None,
                batch_size=batch_size
            )
        except Exception as e:
            print(f"   ✗ Error: {e}")
            total_records = []

        # Call 2: Promoted metrics
        print(f"\n2️⃣  Fetching PROMOTED metrics for sold items...")
        try:
            promoted_records = self.analytics_client.get_traffic_for_sold_listings(
                start_date=start_date,
                end_date=end_date,
                item_ids=sold_item_ids,
                traffic_source='PROMOTED_LISTINGS',
                batch_size=batch_size
            )
        except Exception as e:
            print(f"   ✗ Error: {e}")
            promoted_records = []

        # Call 3: Organic metrics
        print(f"\n3️⃣  Fetching ORGANIC metrics for sold items...")
        try:
            organic_records = self.analytics_client.get_traffic_for_sold_listings(
                start_date=start_date,
                end_date=end_date,
                item_ids=sold_item_ids,
                traffic_source='ORGANIC',
                batch_size=batch_size
            )
        except Exception as e:
            print(f"   ✗ Error: {e}")
            organic_records = []

        # Merge data
        print(f"\n📊 Merging sold listings data...")
        merged_records = self._merge_traffic_data(
            total_records=total_records,
            promoted_records=promoted_records,
            organic_records=organic_records,
            listing_status='sold'
        )

        # Store in database
        print(f"💾 Storing {len(merged_records)} sold listing records...")
        if merged_records:
            self.traffic_repo.bulk_upsert_traffic(merged_records)
            print(f"   ✓ Stored successfully")
        else:
            print(f"   ⚠ No records to store")

        return {'total_records': len(merged_records)}

    def _merge_traffic_data(
        self,
        total_records: List[Dict[str, Any]],
        promoted_records: List[Dict[str, Any]],
        organic_records: List[Dict[str, Any]],
        listing_status: str
    ) -> List[Dict[str, Any]]:
        """
        Merge traffic data from 3 API calls into unified records.

        Args:
            total_records: Records from call without filter
            promoted_records: Records from promoted filter
            organic_records: Records from organic filter
            listing_status: 'active' or 'sold'

        Returns:
            List of merged traffic dictionaries
        """
        # Index records by (item_id, date) for merging
        merged = {}

        # Process total metrics
        for record in total_records:
            item_id = record.get('listingId')
            # Note: Analytics API may not include date in response for LISTING dimension
            # We'll use the query date range as the report date
            date_key = (item_id, None)  # Simplified for now

            if date_key not in merged:
                merged[date_key] = {
                    'item_id': item_id,
                    'report_date': None,  # Will need to handle date extraction
                    'listing_status': listing_status
                }

            # Extract metrics
            metrics = self._extract_metrics_from_record(record)
            merged[date_key].update({
                'total_impressions': metrics.get('TOTAL_IMPRESSION_TOTAL'),
                'total_search_impressions': metrics.get('LISTING_IMPRESSION_SEARCH_RESULTS_PAGE'),
                'total_page_views': metrics.get('LISTING_VIEWS_TOTAL'),
                'transactions': metrics.get('TRANSACTION')
            })

        # Process promoted metrics
        for record in promoted_records:
            item_id = record.get('listingId')
            date_key = (item_id, None)

            if date_key in merged:
                metrics = self._extract_metrics_from_record(record)
                merged[date_key].update({
                    'promoted_total_impressions': metrics.get('LISTING_IMPRESSION_TOTAL'),
                    'promoted_search_impressions': metrics.get('LISTING_IMPRESSION_SEARCH_RESULTS_PAGE'),
                    'promoted_page_views': metrics.get('LISTING_VIEWS_TOTAL')
                })

        # Process organic metrics
        for record in organic_records:
            item_id = record.get('listingId')
            date_key = (item_id, None)

            if date_key in merged:
                metrics = self._extract_metrics_from_record(record)
                merged[date_key].update({
                    'organic_total_impressions': metrics.get('LISTING_IMPRESSION_TOTAL'),
                    'organic_search_impressions': metrics.get('LISTING_IMPRESSION_SEARCH_RESULTS_PAGE'),
                    'organic_page_views': metrics.get('LISTING_VIEWS_TOTAL')
                })

        # Set report_date for all records (use today's date as proxy)
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        for record in merged.values():
            if not record['report_date']:
                record['report_date'] = today

        print(f"   Merged {len(merged)} unique item records")

        return list(merged.values())

    def _extract_metrics_from_record(self, record: Dict[str, Any]) -> Dict[str, int]:
        """
        Extract metrics from Analytics API record.

        Args:
            record: API record dictionary

        Returns:
            Dictionary of metric_name -> value
        """
        metrics = {}
        metric_data = record.get('metricData', [])

        for metric in metric_data:
            key = metric.get('key')
            value = metric.get('value')
            try:
                metrics[key] = int(value) if value else 0
            except (ValueError, TypeError):
                metrics[key] = 0

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
