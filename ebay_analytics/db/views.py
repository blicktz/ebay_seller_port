"""
Database views for eBay Analytics.

This module defines database views that provide calculated/corrected metrics
based on the raw data stored in the database tables.
"""

CREATE_TRAFFIC_VIEW_CORRECTED = """
CREATE VIEW IF NOT EXISTS daily_traffic_facts_corrected AS
SELECT
    item_id,
    report_date,
    listing_status,

    -- Impressions (these are accurate from API)
    total_impressions,
    total_search_impressions,

    -- CORRECTED total page views = sum of all view sources
    -- This is the CORRECT metric to use (matches seller portal)
    (COALESCE(views_source_direct, 0) +
     COALESCE(views_source_off_ebay, 0) +
     COALESCE(views_source_other_ebay, 0) +
     COALESCE(views_source_search_results, 0) +
     COALESCE(views_source_store, 0)) AS total_page_views_corrected,

    -- Original API value (INCORRECT - doesn't match sum of sources)
    -- Kept for debugging and comparison purposes
    total_page_views AS total_page_views_api,

    -- Transactions
    transactions,

    -- View source breakdown (the authoritative data)
    views_source_direct,
    views_source_off_ebay,
    views_source_other_ebay,
    views_source_search_results,
    views_source_store,

    -- Promoted/Organic metrics (not currently populated by API)
    promoted_total_impressions,
    promoted_search_impressions,
    promoted_page_views,
    organic_total_impressions,
    organic_search_impressions,
    organic_page_views,

    -- Metadata
    created_at
FROM daily_traffic_facts;
"""

ALL_VIEWS = [
    CREATE_TRAFFIC_VIEW_CORRECTED
]


def create_all_views(conn):
    """
    Create all database views.

    Args:
        conn: SQLite database connection

    Returns:
        Number of views created
    """
    cursor = conn.cursor()

    for view_sql in ALL_VIEWS:
        cursor.execute(view_sql)

    conn.commit()
    return len(ALL_VIEWS)
