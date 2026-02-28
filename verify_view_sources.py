"""
Verify that view source breakdown data is being captured correctly.

This script checks the database to see if the new view source columns contain data,
and compares the sum of source views with the total views to ensure accuracy.
"""

from ebay_analytics.config import load_config
from ebay_analytics.db.schema import get_connection

def verify_view_sources():
    """Verify view source breakdown in database."""

    print("\n" + "="*70)
    print("VIEW SOURCE BREAKDOWN VERIFICATION")
    print("="*70 + "\n")

    config = load_config()
    conn = get_connection(config.db_path)
    cursor = conn.cursor()

    # Check for specific dates
    dates_to_check = ['2026-02-24', '2026-02-25', '2026-02-26']

    for date in dates_to_check:
        print(f"\n📅 Date: {date}")
        print("-" * 70)

        cursor.execute("""
            SELECT
                COUNT(*) as record_count,
                SUM(total_page_views) as total_views,
                SUM(views_source_direct) as direct_views,
                SUM(views_source_off_ebay) as off_ebay_views,
                SUM(views_source_other_ebay) as other_ebay_views,
                SUM(views_source_search_results) as search_views,
                SUM(views_source_store) as store_views
            FROM daily_traffic_facts
            WHERE report_date = ?
        """, (date,))

        row = cursor.fetchone()

        if row and row[0] > 0:
            record_count = row[0]
            total_views = row[1] or 0
            direct = row[2] or 0
            off_ebay = row[3] or 0
            other_ebay = row[4] or 0
            search = row[5] or 0
            store = row[6] or 0

            source_sum = direct + off_ebay + other_ebay + search + store

            print(f"  Records: {record_count}")
            print(f"\n  Total Views (LISTING_VIEWS_TOTAL): {total_views:,}")
            print(f"\n  View Source Breakdown:")
            print(f"    Direct:         {direct:>8,}")
            print(f"    Off-eBay:       {off_ebay:>8,}  <-- External traffic")
            print(f"    Other eBay:     {other_ebay:>8,}")
            print(f"    Search Results: {search:>8,}")
            print(f"    Store:          {store:>8,}")
            print(f"    {'─'*40}")
            print(f"    Sum of sources: {source_sum:>8,}")

            # Check if sources match total
            if source_sum > 0:
                if abs(source_sum - total_views) <= 1:  # Allow for rounding
                    print(f"\n  ✓ Source breakdown matches total views!")
                else:
                    diff = source_sum - total_views
                    print(f"\n  ⚠ Difference: {diff:+,} ({diff/total_views*100:+.1f}%)")

                # Show external traffic percentage
                if total_views > 0:
                    external_pct = (off_ebay / total_views) * 100
                    print(f"  📊 External traffic: {external_pct:.1f}% of total views")
            else:
                print(f"\n  ⚠ No view source data captured yet")

        else:
            print(f"  ⚠ No data found for this date")

    # Show a sample of recent records with source breakdown
    print(f"\n\n{'='*70}")
    print("SAMPLE RECORDS WITH VIEW SOURCE BREAKDOWN")
    print("="*70 + "\n")

    cursor.execute("""
        SELECT
            item_id,
            report_date,
            total_page_views,
            views_source_direct,
            views_source_off_ebay,
            views_source_other_ebay,
            views_source_search_results,
            views_source_store
        FROM daily_traffic_facts
        WHERE report_date BETWEEN '2026-02-24' AND '2026-02-26'
          AND total_page_views > 0
        ORDER BY views_source_off_ebay DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    if rows:
        print("Top 10 listings by external (off-eBay) views:\n")
        print(f"{'Item ID':<15} {'Date':<12} {'Total':<8} {'Direct':<8} {'Off-eBay':<8} {'Other':<8} {'Search':<8} {'Store':<8}")
        print("-" * 95)

        for row in rows:
            item_id = row[0]
            date = row[1]
            total = row[2] or 0
            direct = row[3] or 0
            off_ebay = row[4] or 0
            other = row[5] or 0
            search = row[6] or 0
            store = row[7] or 0

            print(f"{item_id:<15} {date:<12} {total:<8} {direct:<8} {off_ebay:<8} {other:<8} {search:<8} {store:<8}")
    else:
        print("No records found with view data.")

    print(f"\n{'='*70}\n")

    conn.close()

if __name__ == "__main__":
    verify_view_sources()
