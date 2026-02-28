"""
Clear traffic data for Feb 24-26, 2026 and re-sync with view source breakdown metrics.
"""

from ebay_analytics.config import load_config
from ebay_analytics.db.repository import TrafficRepository
from ebay_analytics.services.traffic_sync import TrafficSyncService

def clear_and_resync():
    """Clear and re-sync traffic data for Feb 24-26."""

    print("\n" + "="*70)
    print("CLEAR AND RE-SYNC TRAFFIC DATA (FEB 24-26, 2026)")
    print("="*70 + "\n")

    # Load config
    config = load_config()
    traffic_repo = TrafficRepository(config.db_path)

    # Define date range
    start_date = '2026-02-24'
    end_date = '2026-02-26'

    print(f"📅 Date range: {start_date} to {end_date}\n")

    # Clear existing data for these dates
    print("🗑️  Clearing existing traffic data for these dates...")

    import sqlite3
    from ebay_analytics.db.schema import get_connection

    conn = get_connection(config.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM daily_traffic_facts
        WHERE report_date BETWEEN ? AND ?
    """, (start_date, end_date))

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"   ✓ Deleted {deleted_count} existing records\n")

    # Re-sync with new metrics
    print("🔄 Starting traffic sync with view source breakdown...\n")

    sync_service = TrafficSyncService(config)

    stats = sync_service.sync_traffic(
        start_date='20260224',
        end_date='20260226',
        include_sold=True
    )

    print("\n" + "="*70)
    print("✓ SYNC COMPLETED")
    print("="*70)
    print(f"  Active listings: {stats.get('active_listings', 0)} records")
    print(f"  Sold listings: {stats.get('sold_listings', 0)} records")
    print(f"  Total: {stats.get('total_records', 0)} records")
    print("="*70 + "\n")

    sync_service.close()

if __name__ == "__main__":
    clear_and_resync()
