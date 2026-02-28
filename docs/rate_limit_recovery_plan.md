# Rate Limit Recovery Plan

## Current Situation

**Problem**: eBay API rate limiting is preventing us from re-syncing Feb 24-26 traffic data.

**Status**:
- ✅ View source breakdown implementation complete
- ✅ Database migration complete (5 new columns added)
- ✅ API client updated to request view source metrics
- ✅ Rate limiting delays added (3s between batches)
- ❌ Unable to re-sync due to aggressive rate limiting from multiple attempts

**eBay Rate Limits**:
- 50 API calls per 60 seconds
- With 539 active listings: requires 3 batches per day (200/200/139 items)
- Multiple failed attempts have temporarily exhausted the rate limit quota

## What's Been Fixed

### 1. View Source Metrics Implementation
Added support for capturing view breakdown by traffic source:
- `LISTING_VIEWS_SOURCE_DIRECT` → `views_source_direct`
- `LISTING_VIEWS_SOURCE_OFF_EBAY` → `views_source_off_ebay` (external traffic - this was missing!)
- `LISTING_VIEWS_SOURCE_OTHER_EBAY` → `views_source_other_ebay`
- `LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE` → `views_source_search_results`
- `LISTING_VIEWS_SOURCE_STORE` → `views_source_store`

### 2. Rate Limiting Improvements
- Added 3-second delay between batches (within a day)
- Existing 5-second delay between days
- Created `sync_one_day.py` script for conservative single-day syncing

## Current Database State

**Feb 27, 2026** (Today):
- ✅ Data exists (553 records, 228 total views)
- ❌ View source columns are NULL (synced before we added the metrics)
- **Needs re-sync** to capture source breakdown

**Feb 24-26, 2026**:
- ❌ No data (cleared in preparation for re-sync)
- **Needs sync** with new view source metrics

## Recovery Steps

### Option 1: Wait and Sync One Day at a Time (Recommended)

Wait **10-15 minutes** for eBay's rate limit window to fully clear, then:

```bash
# Wait 10-15 minutes from the last attempt...

# Sync Feb 24
poetry run python sync_one_day.py 20260224

# Wait 2-3 minutes between days to be safe

# Sync Feb 25
poetry run python sync_one_day.py 20260225

# Wait 2-3 minutes

# Sync Feb 26
poetry run python sync_one_day.py 20260226

# Optionally re-sync Feb 27 to get view source breakdown
poetry run python sync_one_day.py 20260227
```

### Option 2: Run Full Sync Later Today

Wait until later today (a few hours) when rate limits have definitely cleared:

```bash
poetry run python clear_and_resync_traffic.py
```

This will sync all 3 days in one go with appropriate delays.

### Option 3: Run Tomorrow Morning

The safest option - run the sync tomorrow morning when you're sure the rate limit window has completely cleared:

```bash
# Tomorrow morning:
poetry run python clear_and_resync_traffic.py
```

## Verifying Results

After syncing, run the verification script:

```bash
poetry run python verify_view_sources.py
```

This will show:
- Total views vs sum of source breakdown
- External (off-eBay) traffic that was previously missing
- Sample records with view source details

## Expected Results

**Before (Old Data)**:
```
Feb 24: 231 views (missing ~100 views)
Source breakdown: All NULL
```

**After (New Data with Source Breakdown)**:
```
Feb 24: ~331 views (matching seller portal)
Source breakdown:
  - Search results: ~159 views
  - Other sources: ~150 views
  - Off-eBay: ~22 views (THIS WAS MISSING!)
  Total: ~331 views
```

The `views_source_off_ebay` column will now capture the external traffic you saw in the seller portal (22 views on Feb 24, similar numbers for other days).

## Technical Notes

### Why We Hit Rate Limits

1. Initial attempts made successful calls (batch 1 & 2 succeeded)
2. But hit rate limit on batch 3
3. Multiple retry attempts exhausted the 50 calls/60s quota
4. Rate limit window needs time to fully clear

### Rate Limit Math

For each day:
- Active listings: 3 API calls (539 items ÷ 200 per batch)
- Sold listings: 1 API call (11-12 items, fits in 1 batch)
- Total: ~4 calls per day
- With retries on failure: Can easily exceed 50 calls

### Solution Applied

- 3s delay between batches (within a day)
- 5s delay between days
- Single-day sync option for more control
- This keeps us well under 50 calls per 60s window

## Summary

All code changes are complete and committed. The implementation is ready to capture view source breakdown including the missing external/off-eBay traffic.

We just need to wait for eBay's rate limit window to clear (10-15 minutes minimum), then sync the data using one of the options above.

Once synced, you'll be able to see the full view breakdown that matches your seller portal, including the external traffic that was previously missing.
