"""
Traffic sync service.

Fetches traffic data from Analytics API for both active and sold listings,
including promoted/organic breakdown with proper batching.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
from ..api.analytics import AnalyticsAPIClient
from ..db.repository import TrafficRepository, SoldItemsRepository, MetadataRepository
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
        self.metadata_repo = MetadataRepository(config.db_path)

    def _generate_date_range(self, start_date: str, end_date: str) -> List[str]:
        """
        Generate list of dates in range (inclusive).

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format

        Returns:
            List of date strings in YYYYMMDD format
        """
        # Parse dates
        start_dt = datetime.strptime(start_date, '%Y%m%d')
        end_dt = datetime.strptime(end_date, '%Y%m%d')

        # Generate all dates in range
        dates = []
        current_dt = start_dt
        while current_dt <= end_dt:
            dates.append(current_dt.strftime('%Y%m%d'))
            current_dt += timedelta(days=1)

        return dates

    def sync_traffic(
        self,
        start_date: str,
        end_date: str,
        include_sold: bool = True
    ) -> Dict[str, Any]:
        """
        Sync traffic data day-by-day for both active and sold listings.

        Note: Analytics API does NOT support DAY dimension, so we loop through
        each day and make separate API calls to get daily granularity.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            include_sold: Whether to include sold listings (default: True)

        Returns:
            Dictionary with sync statistics
        """
        print(f"\n{'='*60}")
        print(f"TRAFFIC SYNC (DAY-BY-DAY)")
        print(f"{'='*60}\n")

        # Generate list of dates to sync
        date_range = self._generate_date_range(start_date, end_date)
        total_days = len(date_range)

        print(f"Date range: {start_date} to {end_date}")
        print(f"Total days: {total_days}")
        print(f"Include sold listings: {include_sold}")
        print(f"Delay between days: {self.config.api_call_delay_seconds}s")
        print()

        # Get already-synced dates from database
        start_date_iso = datetime.strptime(start_date, '%Y%m%d').strftime('%Y-%m-%d')
        end_date_iso = datetime.strptime(end_date, '%Y%m%d').strftime('%Y-%m-%d')
        synced_dates = self.traffic_repo.get_synced_dates(start_date_iso, end_date_iso)

        # Get today's date (always re-sync today since data may change)
        today = datetime.now(ZoneInfo(self.config.user_timezone)).strftime('%Y%m%d')

        # Filter dates to skip already-synced (except today)
        dates_to_sync = []
        dates_skipped = []
        for date_str in date_range:
            date_iso = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
            if date_iso not in synced_dates or date_str == today:
                dates_to_sync.append(date_str)
            else:
                dates_skipped.append(date_str)

        if dates_skipped:
            print(f"⏭  Skipping {len(dates_skipped)} already-synced dates:")
            for skipped in dates_skipped[:5]:  # Show first 5
                print(f"    {skipped}")
            if len(dates_skipped) > 5:
                print(f"    ... and {len(dates_skipped) - 5} more")
            print()

        days_to_sync = len(dates_to_sync)
        print(f"📊 Will sync {days_to_sync} days")
        print()

        if not dates_to_sync:
            print("✓ All dates already synced - nothing to do!")
            return {
                'active_listings': 0,
                'sold_listings': 0,
                'total_records': 0,
                'total_days': 0,
                'date_range': (start_date, end_date)
            }

        stats = {
            'active_listings': 0,
            'sold_listings': 0,
            'total_records': 0,
            'total_days': days_to_sync,
            'date_range': (start_date, end_date)
        }

        # Loop through each day to sync
        for day_idx, day_str in enumerate(dates_to_sync, 1):
            print(f"\n{'='*60}")
            print(f"📅 Day {day_idx}/{days_to_sync}: {day_str}")
            print(f"{'='*60}\n")

            # Sync active listings for this day
            print(f"🔵 Syncing ACTIVE listings...")
            active_stats = self._sync_active_listings_traffic(day_str, day_str)
            stats['active_listings'] += active_stats['total_records']
            print(f"   ✓ {active_stats['total_records']} active records")

            # Sync sold listings for this day
            if include_sold and self.config.sync_sold_items_enabled:
                print(f"🟢 Syncing SOLD listings...")
                sold_stats = self._sync_sold_listings_traffic(day_str, day_str)
                stats['sold_listings'] += sold_stats['total_records']
                print(f"   ✓ {sold_stats['total_records']} sold records")

            # Update total
            day_total = active_stats['total_records'] + (sold_stats.get('total_records', 0) if include_sold and self.config.sync_sold_items_enabled else 0)
            stats['total_records'] += day_total

            print(f"\n   Day {day_idx} total: {day_total} records")

            # Add delay before next day (except for last day)
            if day_idx < days_to_sync:
                delay = self.config.api_call_delay_seconds
                print(f"   ⏱  Waiting {delay}s before next day...")
                time.sleep(delay)

        print(f"\n{'='*60}")
        print(f"✓ Traffic sync completed successfully")
        print(f"{'='*60}")
        print(f"  Active listings: {stats['active_listings']} records")
        print(f"  Sold listings: {stats['sold_listings']} records")
        print(f"  Total: {stats['total_records']} records")
        print(f"  Days synced: {total_days}")
        print(f"{'='*60}\n")

        return stats

    def _sync_active_listings_traffic(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Sync traffic for active listings with batching.

        Note: Promoted vs organic breakdown is NOT supported by Analytics API.
        Only total traffic metrics are retrieved.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format

        Returns:
            Statistics dictionary
        """
        # Get active listing IDs from metadata
        active_item_ids = self.metadata_repo.get_active_listing_ids()

        if not active_item_ids:
            print(f"   ⚠ No active listings found in metadata")
            return {'total_records': 0}

        print(f"   Found {len(active_item_ids)} active listings to query")
        print()

        # Fetch traffic metrics with batching
        batch_size = self.config.sold_items_batch_size
        print(f"📊 Fetching traffic metrics...")
        try:
            records = self.analytics_client.get_traffic_for_active_listings(
                start_date=start_date,
                end_date=end_date,
                item_ids=active_item_ids,
                batch_size=batch_size
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

        # Convert start_date (YYYYMMDD) to report_date (YYYY-MM-DD)
        # Since we now call API with single-day ranges (start_date == end_date),
        # we use start_date as the report_date for this batch
        report_date = datetime.strptime(start_date, '%Y%m%d').strftime('%Y-%m-%d')

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
                'report_date': report_date,  # Use date from API call (single day)
                'listing_status': listing_status,
                # Total metrics
                'total_impressions': metrics.get('TOTAL_IMPRESSION_TOTAL'),
                'total_search_impressions': metrics.get('LISTING_IMPRESSION_SEARCH_RESULTS_PAGE'),
                'total_page_views': metrics.get('LISTING_VIEWS_TOTAL'),
                'transactions': metrics.get('TRANSACTION'),
                # View breakdown by source
                'views_source_direct': metrics.get('LISTING_VIEWS_SOURCE_DIRECT'),
                'views_source_off_ebay': metrics.get('LISTING_VIEWS_SOURCE_OFF_EBAY'),
                'views_source_other_ebay': metrics.get('LISTING_VIEWS_SOURCE_OTHER_EBAY'),
                'views_source_search_results': metrics.get('LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE'),
                'views_source_store': metrics.get('LISTING_VIEWS_SOURCE_STORE'),
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
        #  'LISTING_VIEWS_TOTAL', 'TRANSACTION', 'LISTING_VIEWS_SOURCE_*']
        metric_names = [
            'TOTAL_IMPRESSION_TOTAL',
            'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
            'LISTING_VIEWS_TOTAL',
            'TRANSACTION',
            'LISTING_VIEWS_SOURCE_DIRECT',
            'LISTING_VIEWS_SOURCE_OFF_EBAY',
            'LISTING_VIEWS_SOURCE_OTHER_EBAY',
            'LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE',
            'LISTING_VIEWS_SOURCE_STORE'
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
