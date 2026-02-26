"""
Sold items sync service.

Fetches sold items from Fulfillment API and stores them in the sold_items_cache table.
This enables querying traffic data for sold listings via the Analytics API.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from ..api.fulfillment import FulfillmentAPIClient
from ..db.repository import SoldItemsRepository, MetadataRepository
from ..config import Config, DateRangeParser


class SoldItemsSyncService:
    """Service for syncing sold items from Fulfillment API."""

    def __init__(self, config: Config):
        """
        Initialize sold items sync service.

        Args:
            config: Configuration object
        """
        self.config = config
        self.fulfillment_client = FulfillmentAPIClient(config)
        self.sold_items_repo = SoldItemsRepository(config.db_path)
        self.metadata_repo = MetadataRepository(config.db_path)

    def sync_sold_items(self, days_back: int = None) -> Dict[str, Any]:
        """
        Sync sold items from Fulfillment API for the last N days.

        Args:
            days_back: Number of days to look back (default: from config, max 90)

        Returns:
            Dictionary with sync statistics:
            {
                'total_orders': 45,
                'total_sold_items': 67,
                'unique_items': 54,
                'new_items_cached': 12,
                'date_range': ('2026-01-27', '2026-02-25')
            }
        """
        if days_back is None:
            days_back = self.config.sold_items_lookback_days

        # Validate days_back (max 90 due to API retention)
        if days_back > 90:
            print(f"⚠ Warning: days_back={days_back} exceeds 90-day retention window")
            print(f"  Setting to 90 days (Analytics API limit)")
            days_back = 90

        print(f"\n{'='*60}")
        print(f"SOLD ITEMS SYNC - Last {days_back} Days")
        print(f"{'='*60}\n")

        # Calculate date range
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days_back)

        start_iso = DateRangeParser.to_iso8601_with_time(start_dt)
        end_iso = DateRangeParser.to_iso8601_with_time(end_dt)

        start_date_str = DateRangeParser.to_iso_format(start_dt)
        end_date_str = DateRangeParser.to_iso_format(end_dt)

        print(f"Date range: {start_date_str} to {end_date_str}")
        print()

        # Fetch sold items from Fulfillment API
        try:
            sold_items = self.fulfillment_client.get_sold_items_for_date_range(
                start_iso,
                end_iso
            )
        except Exception as e:
            print(f"✗ Error fetching sold items: {e}")
            return {
                'error': str(e),
                'total_orders': 0,
                'total_sold_items': 0,
                'unique_items': 0,
                'new_items_cached': 0,
                'date_range': (start_date_str, end_date_str)
            }

        # Calculate statistics
        unique_items = set(item['item_id'] for item in sold_items)

        print(f"\n📊 Sold Items Summary:")
        print(f"   Total sold items: {len(sold_items)}")
        print(f"   Unique item IDs: {len(unique_items)}")
        print()

        # Store in database
        print(f"💾 Storing in database...")
        new_items = self.sold_items_repo.bulk_insert_sold_items(sold_items)
        print(f"   ✓ Cached {new_items} new sold items")
        print()

        # Update metadata for sold items
        print(f"📝 Updating metadata for sold items...")
        self._update_metadata_for_sold_items(sold_items)
        print()

        stats = {
            'total_sold_items': len(sold_items),
            'unique_items': len(unique_items),
            'new_items_cached': new_items,
            'date_range': (start_date_str, end_date_str)
        }

        print(f"✓ Sold items sync completed successfully")
        print(f"{'='*60}\n")

        return stats

    def _update_metadata_for_sold_items(self, sold_items: List[Dict[str, Any]]) -> None:
        """
        Update metadata table with sold status for sold items.

        Args:
            sold_items: List of sold item dictionaries
        """
        # Group by item_id to avoid duplicate updates
        items_by_id = {}
        for item in sold_items:
            item_id = item['item_id']
            if item_id not in items_by_id:
                items_by_id[item_id] = item

        for item_id, item in items_by_id.items():
            try:
                # Check if listing exists in metadata
                existing = self.metadata_repo.get_listing(item_id)

                if existing:
                    # Update existing with sold status
                    self.metadata_repo.upsert_listing(
                        item_id=item_id,
                        title=existing.get('title', item.get('title', 'Unknown')),
                        last_known_status='sold',
                        sold_date=item.get('sold_date'),
                        quantity_available=0  # Sold items have 0 available
                    )
                else:
                    # Create new metadata entry
                    self.metadata_repo.upsert_listing(
                        item_id=item_id,
                        title=item.get('title', 'Unknown'),
                        last_known_status='sold',
                        sold_date=item.get('sold_date'),
                        quantity_available=0
                    )

            except Exception as e:
                print(f"     ⚠ Warning: Could not update metadata for {item_id}: {e}")

        print(f"   ✓ Updated metadata for {len(items_by_id)} unique items")

    def get_sold_items_summary(self, days_back: int = 90) -> Dict[str, Any]:
        """
        Get summary of sold items currently in cache.

        Args:
            days_back: Number of days to look back (default: 90)

        Returns:
            Dictionary with sold items statistics
        """
        sold_item_ids = self.sold_items_repo.get_unique_sold_item_ids(days_back)

        return {
            'unique_sold_items': len(sold_item_ids),
            'days_back': days_back,
            'item_ids': sold_item_ids
        }

    def close(self):
        """Close API clients."""
        self.fulfillment_client.close()


if __name__ == "__main__":
    # Test sold items sync service
    from ..config import load_config

    print("Testing SoldItemsSyncService...\n")

    try:
        config = load_config()

        # Check if sold items sync is enabled
        if not config.sync_sold_items_enabled:
            print("⚠ Sold items sync is disabled in configuration")
            print("  Set SYNC_SOLD_ITEMS_ENABLED=true in .env to enable")
            exit(0)

        service = SoldItemsSyncService(config)

        print("✓ SoldItemsSyncService initialized")
        print(f"  Lookback days: {config.sold_items_lookback_days}")
        print()

        # Note: Actual sync requires valid token and will hit real APIs
        # Uncomment below to test with real API (uses your quota)

        # print("Running sold items sync...")
        # stats = service.sync_sold_items(days_back=7)  # Test with 7 days
        # print(f"\nSync results:")
        # print(f"  Total sold items: {stats['total_sold_items']}")
        # print(f"  Unique items: {stats['unique_items']}")
        # print(f"  New items cached: {stats['new_items_cached']}")

        service.close()
        print("✓ Service closed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
