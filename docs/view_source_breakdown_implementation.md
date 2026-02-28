# View Source Breakdown Implementation

## Problem

Listing views in the database were 30-50% lower than seller portal because we were missing external/off-eBay traffic.

**Example (Feb 24, 2026):**
- Seller Portal: 331 views (159 organic + 150 promoted + **22 external**)
- Database: 231 views (missing external traffic)

## Root Cause

The Analytics API metric `LISTING_VIEWS_TOTAL` does not include all traffic sources. According to the eBay Analytics API documentation, there are separate metrics for breaking down views by source:

- `LISTING_VIEWS_SOURCE_DIRECT` - Direct views
- `LISTING_VIEWS_SOURCE_OFF_EBAY` - **External/off-eBay traffic** (this was missing!)
- `LISTING_VIEWS_SOURCE_OTHER_EBAY` - Other eBay sources
- `LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE` - Search results views
- `LISTING_VIEWS_SOURCE_STORE` - Store views

## Solution

### 1. Database Schema Changes

Added 5 new columns to `daily_traffic_facts` table:

```sql
ALTER TABLE daily_traffic_facts ADD COLUMN views_source_direct INTEGER;
ALTER TABLE daily_traffic_facts ADD COLUMN views_source_off_ebay INTEGER;
ALTER TABLE daily_traffic_facts ADD COLUMN views_source_other_ebay INTEGER;
ALTER TABLE daily_traffic_facts ADD COLUMN views_source_search_results INTEGER;
ALTER TABLE daily_traffic_facts ADD COLUMN views_source_store INTEGER;
```

Migration script: `migrate_add_view_sources.py`

### 2. API Client Changes

Updated `ebay_analytics/api/analytics.py` to request additional metrics:

**Before:**
```python
metrics = [
    'TOTAL_IMPRESSION_TOTAL',
    'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
    'LISTING_VIEWS_TOTAL',
    'TRANSACTION'
]
```

**After:**
```python
metrics = [
    'TOTAL_IMPRESSION_TOTAL',
    'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
    'LISTING_VIEWS_TOTAL',
    'TRANSACTION',
    # View breakdown by source
    'LISTING_VIEWS_SOURCE_DIRECT',
    'LISTING_VIEWS_SOURCE_OFF_EBAY',
    'LISTING_VIEWS_SOURCE_OTHER_EBAY',
    'LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE',
    'LISTING_VIEWS_SOURCE_STORE'
]
```

Updated both `get_traffic_for_active_listings()` and `get_traffic_for_sold_listings()` methods.

### 3. Traffic Sync Changes

Updated `ebay_analytics/services/traffic_sync.py`:

- Added new metrics to parsing logic in `_extract_metrics_from_record()`
- Added new columns to database record building in `_convert_to_db_format()`

### 4. Repository Changes

Updated `ebay_analytics/db/repository.py`:

- Added new columns to INSERT statement in `bulk_upsert_traffic()`
- Added new columns to UPDATE statement in conflict resolution

## Files Modified

1. **ebay_analytics/db/schema.py** - Added 5 new columns to table schema
2. **ebay_analytics/api/analytics.py** - Added 5 new metrics to API requests
3. **ebay_analytics/services/traffic_sync.py** - Updated parsing and conversion logic
4. **ebay_analytics/db/repository.py** - Updated database insert/update statements

## New Scripts

1. **migrate_add_view_sources.py** - Database migration to add new columns (COMPLETED)
2. **clear_and_resync_traffic.py** - Clear Feb 24-26 data and re-sync with new metrics
3. **verify_view_sources.py** - Verify view source breakdown is captured correctly
4. **test_view_metrics.py** - Test script for metric combinations

## Next Steps

### 1. Refresh eBay API Token

The current access token has expired. You need to refresh it before re-syncing:

```bash
# Follow eBay's OAuth flow to get a new access token
# Update your .env file with the new token
```

### 2. Re-sync Traffic Data

Once the token is refreshed, run:

```bash
poetry run python clear_and_resync_traffic.py
```

This will:
- Delete existing data for Feb 24-26, 2026
- Re-sync with the new view source breakdown metrics
- Capture external/off-eBay traffic that was missing

### 3. Verify Results

After re-syncing, run:

```bash
poetry run python verify_view_sources.py
```

This will show:
- Total views vs sum of source breakdown
- External traffic percentage
- Sample records with highest external traffic

### 4. Compare with Portal

The new `views_source_off_ebay` column should now capture the external traffic shown in the seller portal, bringing our total views in line with the portal numbers.

## Expected Results

After re-syncing with new metrics:

**Feb 24, 2026:**
- Portal: 331 views (159 organic + 150 promoted + 22 external)
- Database: ~331 views (sum of all source metrics including `views_source_off_ebay`)

The discrepancy should be resolved as we're now capturing all traffic sources.

## Technical Notes

### Why LISTING_VIEWS_TOTAL Alone Isn't Enough

The eBay Analytics API appears to calculate `LISTING_VIEWS_TOTAL` differently than the sum of source breakdowns. Based on the API documentation and seller portal, to get accurate view counts matching the portal, you need to:

1. Request the source breakdown metrics explicitly
2. Sum them up for the total: `direct + off_ebay + other_ebay + search_results + store`

### Promoted vs Organic Classification

The portal shows "Organic" and "Promoted" breakdowns, but the API provides source breakdowns instead:

- **Portal "Organic"** likely = `search_results + store + direct + other_ebay` (non-promoted sources)
- **Portal "External"** = `off_ebay` (external traffic)
- **Portal "Promoted"** = Requires `traffic_source=PROMOTED_LISTINGS` filter (not implemented yet)

For now, we're capturing the full source breakdown which gives us the missing external traffic.

## API Reference

**eBay Analytics API Documentation:**
- https://developer.ebay.com/api-docs/sell/analytics/resources/traffic_report/methods/getTrafficReport

**Available Metrics:**
- LISTING_VIEWS_SOURCE_DIRECT
- LISTING_VIEWS_SOURCE_OFF_EBAY (external traffic)
- LISTING_VIEWS_SOURCE_OTHER_EBAY
- LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE
- LISTING_VIEWS_SOURCE_STORE
- LISTING_VIEWS_TOTAL (may not equal sum of sources)
