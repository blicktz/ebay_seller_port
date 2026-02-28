"""
Sync traffic data for a single day - more conservative to avoid rate limits.
"""

import sys
from ebay_analytics.config import load_config
from ebay_analytics.services.traffic_sync import TrafficSyncService

def sync_single_day(date: str):
    """
    Sync traffic data for a single day.

    Args:
        date: Date in YYYYMMDD format (e.g., '20260224')
    """

    print("\n" + "="*70)
    print(f"SYNC TRAFFIC DATA FOR {date}")
    print("="*70 + "\n")

    config = load_config()
    sync_service = TrafficSyncService(config)

    try:
        stats = sync_service.sync_traffic(
            start_date=date,
            end_date=date,
            include_sold=True
        )

        print("\n" + "="*70)
        print("✓ SYNC COMPLETED")
        print("="*70)
        print(f"  Active listings: {stats.get('active_listings', 0)} records")
        print(f"  Sold listings: {stats.get('sold_listings', 0)} records")
        print(f"  Total: {stats.get('total_records', 0)} records")
        print("="*70 + "\n")

    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        raise
    finally:
        sync_service.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sync_one_day.py YYYYMMDD")
        print("Example: python sync_one_day.py 20260224")
        sys.exit(1)

    date = sys.argv[1]
    sync_single_day(date)
