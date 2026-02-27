"""
Metadata sync service.

Fetches listing metadata from Trading API and stores it in the listings_metadata table.
"""

from typing import Dict, Any
from ..api.trading import TradingAPIClient
from ..db.repository import MetadataRepository
from ..config import Config


class MetadataSyncService:
    """Service for syncing listing metadata from Trading API."""

    def __init__(self, config: Config):
        """
        Initialize metadata sync service.

        Args:
            config: Configuration object
        """
        self.config = config
        self.trading_client = TradingAPIClient(config)
        self.metadata_repo = MetadataRepository(config.db_path)

    def sync_metadata(self) -> Dict[str, Any]:
        """
        Sync listing metadata from Trading API.

        Returns:
            Dictionary with sync statistics:
            {
                'total_items': 500,
                'items_updated': 500
            }
        """
        print(f"\n{'='*60}")
        print(f"METADATA SYNC")
        print(f"{'='*60}\n")

        # Fetch metadata from Trading API
        try:
            metadata_list = self.trading_client.get_active_listings_metadata()
        except Exception as e:
            print(f"✗ Error fetching active listings metadata: {e}")
            import traceback
            traceback.print_exc()
            return {
                'error': str(e),
                'total_items': 0,
                'items_updated': 0
            }

        if not metadata_list:
            print(f"⚠ No active listings found")
            return {
                'total_items': 0,
                'items_updated': 0
            }

        print(f"\n📊 Metadata Summary:")
        print(f"   Total active listings fetched: {len(metadata_list)}")
        print()

        # Store in database
        print(f"💾 Storing in database...")
        items_updated = self.metadata_repo.bulk_upsert_listings(metadata_list)
        print(f"   ✓ Updated {items_updated} listings")
        print()

        stats = {
            'total_items': len(metadata_list),
            'items_updated': items_updated
        }

        print(f"✓ Metadata sync completed successfully")
        print(f"{'='*60}\n")

        return stats

    def close(self):
        """Close API clients."""
        self.trading_client.close()


if __name__ == "__main__":
    # Test metadata sync service
    from ..config import load_config

    print("Testing MetadataSyncService...\n")

    try:
        config = load_config()
        service = MetadataSyncService(config)

        print("✓ MetadataSyncService initialized")
        print()

        # Note: Actual sync requires valid token and will hit real API
        # Uncomment below to test with real API (uses your quota)

        # print("Running metadata sync...")
        # stats = service.sync_metadata()
        # print(f"\nSync results:")
        # print(f"  Total items: {stats['total_items']}")
        # print(f"  Items updated: {stats['items_updated']}")

        service.close()
        print("✓ Service closed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
