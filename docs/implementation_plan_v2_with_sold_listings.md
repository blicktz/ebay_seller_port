# eBay Seller Analytics Implementation Plan

**Version:** 2.0 (with Sold Listings Support)
**Date:** 2026-02-25
**Status:** Planning Phase

---

## Executive Summary

This document outlines the complete implementation plan for building an eBay Seller Analytics system that replicates the "Listings Traffic Report" CSV using the eBay Sell Analytics API, Sell Inventory API, Sell Fulfillment API, and a local SQLite database.

### Key Features
- Modular Python package with clean separation of concerns
- SQLite database for efficient local caching and historical storage
- Makefile-based interface with configurable date ranges
- CSV export matching eBay's exact 29-column format
- Fact-based storage (calculations only at report generation time)
- **NEW: Support for both ACTIVE and SOLD listings traffic data**

### Design Principles
1. **Store only facts**: Never store calculated/derived metrics in database
2. **5 API calls per sync**: Required for complete active + sold + promoted/organic breakdown
3. **Configurable via Makefile**: Simple, repeatable, user-friendly interface
4. **Handle API limitations transparently**: Document and handle missing metrics
5. **90-day sold listing window**: Automatically track and sync sold items within retention period

---

## 1. Project Structure

```
ebay_seller_port/
├── Makefile                         # Primary execution interface
├── .env                             # Configuration (tokens, dates, marketplace)
├── .env.example                     # Template for configuration
├── pyproject.toml                   # Poetry dependencies
├── poetry.lock
├── README.md                        # User documentation
├── ebay_analytics_test.py           # (existing test file)
│
├── ebay_analytics/                  # Main Python package
│   ├── __init__.py                  # Package initialization
│   ├── config.py                    # Configuration loader (.env parser)
│   │
│   ├── api/                         # API client layer
│   │   ├── __init__.py
│   │   ├── base.py                  # Base client (auth, rate limit, retry)
│   │   ├── analytics.py             # Analytics API client
│   │   ├── inventory.py             # Inventory API client
│   │   └── fulfillment.py           # NEW: Fulfillment API client (sold items)
│   │
│   ├── db/                          # Database layer
│   │   ├── __init__.py
│   │   ├── schema.py                # Table definitions & initialization
│   │   └── repository.py            # Data access layer (CRUD)
│   │
│   ├── services/                    # Business logic layer
│   │   ├── __init__.py
│   │   ├── metadata_sync.py         # Sync listing metadata
│   │   ├── sold_items_sync.py       # NEW: Sync sold item IDs from Fulfillment API
│   │   ├── traffic_sync.py          # Sync traffic data (5 API calls total)
│   │   └── report_generator.py      # Generate CSV reports
│   │
│   ├── utils/                       # NEW: Utility functions
│   │   ├── __init__.py
│   │   └── url_encoding.py          # URL encoding for listing_ids filter
│   │
│   └── cli.py                       # CLI entry points
│
├── data/                            # Database storage
│   ├── .gitkeep
│   └── ebay_analytics.db            # SQLite database (generated)
│
├── reports/                         # Generated CSV exports
│   └── .gitkeep
│
├── tests/                           # Unit tests
│   ├── __init__.py
│   ├── test_api/
│   ├── test_db/
│   └── test_services/
│
└── docs/                            # Documentation
    ├── eBay Analytics API Mapping.md  # (existing)
    ├── implementation_plan.md         # Original plan (v1)
    └── implementation_plan_v2_with_sold_listings.md  # This file
```

---

## 2. Database Design

### Philosophy: FACT-ONLY Storage

The database stores ONLY raw metrics from the API. All derived metrics (percentages, rates, calculated fields) are computed at query/report generation time.

**Benefits:**
- Single source of truth
- Easy to recalculate if formulas change
- No risk of stale calculated data
- Smaller database size

### Table 1: `listings_metadata`

Stores static/semi-static information about listings from the Inventory API.

```sql
CREATE TABLE listings_metadata (
    item_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category_name TEXT,
    start_date TEXT,                     -- Format: YYYY-MM-DD
    promoted_status TEXT,                -- "Promoted" | "Not Promoted" | "Unknown"
    quantity_available INTEGER,

    -- NEW: Track listing lifecycle status
    last_known_status TEXT,              -- 'active' | 'sold' | 'unsold' | 'ended'
    sold_date TEXT,                      -- YYYY-MM-DD (when item sold, NULL if not sold)
    status_checked_date DATETIME,        -- When we last verified status

    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_metadata_updated ON listings_metadata(last_updated);
CREATE INDEX idx_metadata_sold_date ON listings_metadata(sold_date);
CREATE INDEX idx_metadata_status ON listings_metadata(last_known_status);
```

**Update Strategy:**
- Run once daily for active listings
- Run weekly for sold listings status check
- Use `INSERT OR REPLACE` for upserts

### Table 2: `daily_traffic_facts`

Stores raw traffic metrics from Analytics API. Each row represents one listing on one date.

```sql
CREATE TABLE daily_traffic_facts (
    item_id TEXT NOT NULL,
    report_date TEXT NOT NULL,           -- Format: YYYY-MM-DD

    -- NEW: Track whether data is for active or sold listing
    listing_status TEXT,                 -- 'active' | 'sold'

    -- CALL 1 (Active) / CALL 3 (Sold): No filter (total/aggregate metrics)
    total_impressions INTEGER,           -- TOTAL_IMPRESSION_TOTAL
    total_search_impressions INTEGER,    -- LISTING_IMPRESSION_SEARCH_RESULTS_PAGE
    total_page_views INTEGER,            -- LISTING_VIEWS_TOTAL
    transactions INTEGER,                -- TRANSACTION (quantity sold)

    -- CALL 2 (Active) / CALL 4 (Sold): traffic_source filter = PROMOTED_LISTINGS
    promoted_total_impressions INTEGER,  -- LISTING_IMPRESSION_TOTAL (promoted only)
    promoted_search_impressions INTEGER, -- LISTING_IMPRESSION_SEARCH_RESULTS_PAGE (promoted)
    promoted_page_views INTEGER,         -- LISTING_VIEWS_TOTAL (promoted only)

    -- CALL 3 (Active) / CALL 5 (Sold): traffic_source filter = ORGANIC
    organic_total_impressions INTEGER,   -- LISTING_IMPRESSION_TOTAL (organic only)
    organic_search_impressions INTEGER,  -- LISTING_IMPRESSION_SEARCH_RESULTS_PAGE (organic)
    organic_page_views INTEGER,          -- LISTING_VIEWS_TOTAL (organic only)

    -- Metadata
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (item_id, report_date),
    FOREIGN KEY (item_id) REFERENCES listings_metadata(item_id)
);

CREATE INDEX idx_traffic_date ON daily_traffic_facts(report_date);
CREATE INDEX idx_traffic_item ON daily_traffic_facts(item_id);
CREATE INDEX idx_traffic_status ON daily_traffic_facts(listing_status);
CREATE INDEX idx_traffic_created ON daily_traffic_facts(created_at);
```

**Update Strategy:**
- Use `INSERT OR IGNORE` for idempotent updates
- Historical data doesn't change after finalization (48 hours)
- Recommended: Daily incremental sync for last 3 days (active + sold)

### Table 3: `sold_items_cache` (NEW)

Caches sold item IDs from Fulfillment API to optimize traffic queries.

```sql
CREATE TABLE sold_items_cache (
    item_id TEXT NOT NULL,
    sold_date TEXT NOT NULL,             -- YYYY-MM-DD (when item sold)
    order_id TEXT,                       -- eBay order ID
    quantity_sold INTEGER,               -- How many units sold in this order
    discovered_date DATETIME DEFAULT CURRENT_TIMESTAMP,  -- When we found this sale

    PRIMARY KEY (item_id, sold_date, order_id),
    FOREIGN KEY (item_id) REFERENCES listings_metadata(item_id)
);

CREATE INDEX idx_sold_cache_date ON sold_items_cache(sold_date);
CREATE INDEX idx_sold_cache_discovered ON sold_items_cache(discovered_date);
```

**Purpose:**
- Track which items sold in the last 90 days
- Avoid querying Fulfillment API repeatedly for same data
- Enable efficient batching for Analytics API calls with listing_ids filter

---

## 3. API Integration Strategy

### 3.1 Analytics API Calls (5 Total Per Sync)

**Endpoint:** `GET https://api.ebay.com/sell/analytics/v1/traffic_report`

**Required Parameters:**
- `dimension=LISTING` (one row per item)
- `filter=date_range:[YYYYMMDD..YYYYMMDD]`
- Header: `X-EBAY-C-MARKETPLACE-ID: EBAY_US`
- Header: `Authorization: Bearer {access_token}`

**Five Call Strategy (per date range):**

| Call # | Purpose | Filter | Target |
|--------|---------|--------|--------|
| 1 | Active - Total metrics | None (defaults to active) | All active listings |
| 2 | Active - Promoted only | `traffic_source:{PROMOTED_LISTINGS}` | Active promoted traffic |
| 3 | Active - Organic only | `traffic_source:{ORGANIC}` | Active organic traffic |
| 4 | Sold - Total metrics | `listing_ids:{id1|id2|...}` | Sold listings traffic |
| 5 | Sold - Promoted/Organic | `listing_ids:{...},traffic_source:{...}` | Sold promoted/organic (2 sub-calls) |

**Sold Listings Filter Syntax:**
```
Raw format:
filter=marketplace_ids:{EBAY_US},date_range:[20260201..20260225],listing_ids:{id1|id2|id3}

URL-encoded format (required):
filter=marketplace_ids:%7BEBAY_US%7D,date_range:%5B20260201..20260225%5D,listing_ids:%7Bid1%7Cid2%7Cid3%7D

Where:
- { = %7B
- } = %7D
- [ = %5B
- ] = %5D
- | = %7C (pipe separator between IDs)
```

**Batching for Sold Items:**
- Maximum 200 item IDs per API call
- If >200 sold items: batch into multiple calls
- Example: 1,000 sold items = 5 batched calls

**Why 5+ calls?**
- Cannot combine active + sold listings in single query
- Must query sold items separately with listing_ids filter
- Need promoted/organic breakdown for both active and sold
- Total calls = 3 (active) + 2 (sold) + batching overhead

### 3.2 Fulfillment API Calls (NEW)

**Endpoint:** `GET https://api.ebay.com/sell/fulfillment/v1/order`

**Purpose:** Identify which items sold in the last N days (up to 90)

**Request Parameters:**
```
GET /sell/fulfillment/v1/order?filter=...&limit=200&offset=0

Query Parameters:
- filter: creationdate:[2024-02-21T08:25:43.511Z..2024-04-21T08:25:43.511Z]
- limit: 200 (max per request)
- offset: 0, 200, 400, ... (pagination)
```

**Data Extraction:**
```json
Response:
{
  "orders": [
    {
      "orderId": "20-12345-67890",
      "creationDate": "2024-03-15T14:32:21.511Z",
      "lineItems": [
        {
          "itemId": "123456789012",  // <-- Extract this
          "quantity": 2,
          "title": "Product Name"
        }
      ]
    }
  ]
}
```

**Update Frequency:**
- Run daily or weekly
- Query last 90 days to catch all sold items within traffic retention window
- Store item IDs in `sold_items_cache` table

### 3.3 Inventory API Calls

**Endpoint:** `GET https://api.ebay.com/sell/inventory/v1/inventory_item`

**Purpose:** Fetch listing metadata (title, category, inventory status)

**Update Frequency:** Once daily or on-demand

---

## 4. Sold Listings Integration Workflow

### Step 1: Identify Sold Items (Weekly or Daily)

```python
def sync_sold_items(days_back=90):
    """
    1. Query Fulfillment API for orders in date range
    2. Extract unique item IDs from lineItems
    3. Store in sold_items_cache with sold dates
    """
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)

    offset = 0
    sold_items = []

    while True:
        response = fulfillment_api.get_orders(
            filter=f'creationdate:[{start_date.isoformat()}..{end_date.isoformat()}]',
            limit=200,
            offset=offset
        )

        for order in response['orders']:
            for line_item in order['lineItems']:
                sold_items.append({
                    'item_id': line_item['itemId'],
                    'sold_date': parse_date(order['creationDate']),
                    'order_id': order['orderId'],
                    'quantity': line_item['quantity']
                })

        if len(response['orders']) < 200:
            break
        offset += 200

    # Store in database
    repository.bulk_insert_sold_items(sold_items)
    return sold_items
```

### Step 2: Query Traffic for Sold Items (Daily)

```python
def sync_sold_items_traffic(start_date, end_date):
    """
    1. Retrieve sold item IDs from cache
    2. Batch by 200 items
    3. Query Analytics API with listing_ids filter
    4. Store results with listing_status='sold'
    """
    # Get sold items within date range (or last 90 days)
    sold_item_ids = repository.get_sold_items_in_range(
        sold_start=start_date - timedelta(days=90),
        sold_end=end_date
    )

    batch_size = 200
    all_traffic = []

    for i in range(0, len(sold_item_ids), batch_size):
        batch = sold_item_ids[i:i+batch_size]

        # Call 1: Total metrics for sold items
        traffic_total = analytics_api.get_traffic_report(
            dimension='LISTING',
            date_range=(start_date, end_date),
            listing_ids=batch,  # Will be URL-encoded
            metrics=['TOTAL_IMPRESSION_TOTAL', 'LISTING_VIEWS_TOTAL', 'TRANSACTION']
        )

        # Call 2: Promoted metrics for sold items
        traffic_promoted = analytics_api.get_traffic_report(
            dimension='LISTING',
            date_range=(start_date, end_date),
            listing_ids=batch,
            traffic_source='PROMOTED_LISTINGS',
            metrics=[...]
        )

        # Call 3: Organic metrics for sold items
        traffic_organic = analytics_api.get_traffic_report(
            dimension='LISTING',
            date_range=(start_date, end_date),
            listing_ids=batch,
            traffic_source='ORGANIC',
            metrics=[...]
        )

        # Merge results
        merged_traffic = merge_traffic_data(traffic_total, traffic_promoted, traffic_organic)

        # Mark as sold
        for record in merged_traffic:
            record['listing_status'] = 'sold'

        all_traffic.extend(merged_traffic)

    # Store in database
    repository.bulk_upsert_traffic(all_traffic)
    return all_traffic
```

### Step 3: Query Traffic for Active Items (Daily)

```python
def sync_active_items_traffic(start_date, end_date):
    """
    Standard 3-call process for active listings (no listing_ids filter)
    """
    # Call 1: Total metrics (defaults to active listings)
    traffic_total = analytics_api.get_traffic_report(
        dimension='LISTING',
        date_range=(start_date, end_date),
        metrics=[...]
    )

    # Call 2: Promoted
    traffic_promoted = analytics_api.get_traffic_report(
        dimension='LISTING',
        date_range=(start_date, end_date),
        traffic_source='PROMOTED_LISTINGS',
        metrics=[...]
    )

    # Call 3: Organic
    traffic_organic = analytics_api.get_traffic_report(
        dimension='LISTING',
        date_range=(start_date, end_date),
        traffic_source='ORGANIC',
        metrics=[...]
    )

    # Merge and mark as active
    merged_traffic = merge_traffic_data(traffic_total, traffic_promoted, traffic_organic)
    for record in merged_traffic:
        record['listing_status'] = 'active'

    repository.bulk_upsert_traffic(merged_traffic)
    return merged_traffic
```

### Step 4: Combine in Report (Always)

```sql
-- Report query includes both active and sold listings
SELECT
    m.title,
    m.item_id,
    t.listing_status,  -- NEW: Show if item is active or sold
    t.total_impressions,
    ...
FROM daily_traffic_facts t
JOIN listings_metadata m ON t.item_id = m.item_id
WHERE t.report_date BETWEEN ? AND ?
ORDER BY t.listing_status, t.report_date DESC, t.item_id;
```

---

## 5. CSV Output Format

### 5.1 Exact Column Mapping (29 Columns)

**No changes to column structure** - sold listings will appear as additional rows in the same format.

### 5.2 SQL Query for Report Generation (UPDATED)

```sql
SELECT
    m.title AS "Listing title",
    m.item_id AS "eBay item ID",
    m.start_date AS "Item Start Date",
    m.category_name AS "Category",
    m.promoted_status AS "Current promoted listings status",

    -- NEW: Show quantity based on listing status
    CASE
        WHEN t.listing_status = 'sold' THEN 0  -- Sold items have 0 available
        ELSE m.quantity_available
    END AS "Quantity available",

    t.total_impressions AS "Total impressions",

    -- CALCULATED: Click-through rate
    CASE
        WHEN t.total_impressions > 0
        THEN ROUND((CAST(t.total_page_views AS REAL) / t.total_impressions) * 100, 2)
        ELSE NULL
    END AS "Click-through rate",

    t.transactions AS "Quantity sold",

    NULL AS "% Top 20 Search Impressions",

    -- CALCULATED: Sales conversion rate
    CASE
        WHEN t.total_page_views > 0
        THEN ROUND((CAST(t.transactions AS REAL) / t.total_page_views) * 100, 2)
        ELSE NULL
    END AS "Sales conversion rate",

    NULL AS "Top 20 search slot impressions from promoted listings",
    NULL AS "% change in top 20 search slot impressions from promoted listings",
    NULL AS "Top 20 search slot organic impressions",
    NULL AS "% change in top 20 search slot impressions",
    NULL AS "Rest of search slot impressions",

    t.total_search_impressions AS "Total Search Impressions",

    -- CALCULATED: Non-search promoted impressions
    (t.promoted_total_impressions - t.promoted_search_impressions) AS "Non-search promoted listings impressions",

    NULL AS "% Change in non-search promoted listings impressions",

    -- CALCULATED: Non-search organic impressions
    (t.organic_total_impressions - t.organic_search_impressions) AS "Non-search organic impressions",

    NULL AS "% Change in non-search organic impressions",

    t.promoted_total_impressions AS "Total Promoted Listings impressions (applies to eBay site only)",
    NULL AS "Total Promoted Offsite impressions (applies to off-eBay only)",
    t.organic_total_impressions AS "Total organic impressions on eBay site",
    t.total_page_views AS "Total page views",
    t.promoted_page_views AS "Page views via promoted listings impressions on eBay site",
    NULL AS "Page views via promoted listings Impressions from outside eBay (search engines, affiliates)",
    t.organic_page_views AS "Page views via organic impressions on eBay site",
    NULL AS "Page views from organic impressions outside eBay (Includes page views from search engines)"

FROM daily_traffic_facts t
JOIN listings_metadata m ON t.item_id = m.item_id
WHERE t.report_date BETWEEN ? AND ?
ORDER BY
    t.listing_status DESC,  -- 'sold' before 'active' (alphabetical)
    t.report_date DESC,
    t.item_id;
```

**Output will include:**
- Active listings (current inventory)
- Sold listings (within 90-day window)
- Both types in the same CSV with same 29 columns

---

## 6. Makefile Design (UPDATED)

### 6.1 Configuration Variables

```makefile
# Configuration with defaults
START_DATE ?= $(shell date -v-7d +%Y%m%d)    # 7 days ago (macOS)
END_DATE ?= $(shell date +%Y%m%d)            # Today
SOLD_LOOKBACK ?= 90                          # Days to look back for sold items
MARKETPLACE ?= EBAY_US
OUTPUT_FILE ?= reports/traffic_report_$(shell date +%Y%m%d_%H%M%S).csv
DB_PATH ?= data/ebay_analytics.db
```

### 6.2 Core Targets (UPDATED)

```makefile
.PHONY: help install init-db sync-metadata sync-sold-items sync-traffic generate-report full-sync clean-db test

help:
	@echo "eBay Seller Analytics - Available Commands"
	@echo ""
	@echo "  make install           Install dependencies via Poetry"
	@echo "  make init-db           Initialize database schema"
	@echo "  make sync-metadata     Sync listing metadata from Inventory API"
	@echo "  make sync-sold-items   Sync sold item IDs from Fulfillment API (NEW)"
	@echo "  make sync-traffic      Sync traffic data for active + sold listings"
	@echo "  make generate-report   Generate CSV report (includes sold listings)"
	@echo "  make full-sync         Run complete sync: metadata + sold + traffic + report"
	@echo "  make clean-db          Reset database (WARNING: deletes all data)"
	@echo "  make test              Run unit tests"
	@echo ""
	@echo "Date Range Configuration:"
	@echo "  START_DATE=$(START_DATE) (default: 7 days ago)"
	@echo "  END_DATE=$(END_DATE) (default: today)"
	@echo "  SOLD_LOOKBACK=$(SOLD_LOOKBACK) days (default: 90)"
	@echo ""
	@echo "Examples:"
	@echo "  make sync-sold-items SOLD_LOOKBACK=60"
	@echo "  make sync-traffic START_DATE=20260201 END_DATE=20260225"
	@echo "  make full-sync START_DATE=20260218"

install:
	poetry install

init-db:
	poetry run python -m ebay_analytics.cli init-db --db-path $(DB_PATH)

sync-metadata:
	poetry run python -m ebay_analytics.cli sync-metadata --marketplace $(MARKETPLACE)

sync-sold-items:
	poetry run python -m ebay_analytics.cli sync-sold-items \
		--days-back $(SOLD_LOOKBACK) \
		--marketplace $(MARKETPLACE)

sync-traffic:
	@echo "Syncing traffic for active + sold listings..."
	poetry run python -m ebay_analytics.cli sync-traffic \
		--start-date $(START_DATE) \
		--end-date $(END_DATE) \
		--marketplace $(MARKETPLACE) \
		--include-sold

generate-report:
	poetry run python -m ebay_analytics.cli generate-report \
		--start-date $(START_DATE) \
		--end-date $(END_DATE) \
		--output $(OUTPUT_FILE)

full-sync:
	@echo "Running full sync: metadata + sold items + traffic + report"
	$(MAKE) sync-metadata
	$(MAKE) sync-sold-items
	$(MAKE) sync-traffic
	$(MAKE) generate-report

clean-db:
	@echo "WARNING: This will delete all data. Press Ctrl+C to cancel, or Enter to continue..."
	@read
	rm -f $(DB_PATH)
	$(MAKE) init-db

test:
	poetry run pytest tests/ -v
```

### 6.3 Example Usage (UPDATED)

```bash
# Basic: Last 7 days (includes active + sold within 90 days)
make full-sync

# Sync sold items only (weekly recommended)
make sync-sold-items SOLD_LOOKBACK=90

# Custom date range with sold items
make sync-traffic START_DATE=20260201 END_DATE=20260225

# Generate report including sold listings
make generate-report START_DATE=20260215 END_DATE=20260222

# Check sold items from last 30 days only
make sync-sold-items SOLD_LOOKBACK=30
```

---

## 7. Implementation Phases (UPDATED)

### Phase 1: Foundation (Database & Config) - Day 1
**Goal:** Setup project structure and database layer

**Tasks:**
1. Create folder structure
2. Update `pyproject.toml` (add `click`)
3. Create `ebay_analytics/db/schema.py`:
   - Define **3 tables** (listings_metadata, daily_traffic_facts, sold_items_cache)
   - Add new indexes for listing_status and sold_date
4. Create `ebay_analytics/config.py`
5. Create `.env.example` with sold items configuration

**Testing:**
- Verify 3 tables created successfully
- Check indexes exist

---

### Phase 2: API Client Layer - Day 2
**Goal:** Build robust API clients including Fulfillment API

**Tasks:**
1. Create `ebay_analytics/api/base.py` (common functionality)
2. Create `ebay_analytics/api/analytics.py`:
   - Support for `listing_ids` filter parameter
   - URL encoding utility for filter syntax
3. **NEW:** Create `ebay_analytics/api/fulfillment.py`:
   - `get_orders(filter, limit, offset)` method
   - Parse order response and extract item IDs
   - Handle pagination (200 orders per page)
4. Create `ebay_analytics/api/inventory.py`
5. **NEW:** Create `ebay_analytics/utils/url_encoding.py`:
   - URL encode listing_ids filter: `{id1|id2|id3}` → `%7Bid1%7Cid2%7Cid3%7D`

**Testing:**
- Mock Fulfillment API response
- Test listing_ids URL encoding
- Test pagination

---

### Phase 3: Database Repository Layer - Day 3
**Goal:** Data access layer with CRUD for all 3 tables

**Tasks:**
1. Update `ebay_analytics/db/repository.py`:
   - `MetadataRepository`: Add methods for sold_date and listing_status
   - `TrafficRepository`: Add listing_status parameter to upserts
   - **NEW:** `SoldItemsRepository`:
     - `bulk_insert_sold_items(items)`
     - `get_sold_items_in_range(start, end)`
     - `get_unique_sold_item_ids(days_back=90)`

**Testing:**
- Test sold items cache operations
- Verify listing_status stored correctly

---

### Phase 4: Sold Items Sync Service - Day 4 (NEW)
**Goal:** Implement Fulfillment API integration

**Tasks:**
1. **NEW:** Create `ebay_analytics/services/sold_items_sync.py`:
   - `SoldItemsSyncService` class
   - Method: `sync_sold_items(days_back=90)`
   - Call Fulfillment API → parse orders → extract item IDs
   - Handle pagination (potentially 1000s of orders)
   - Store in `sold_items_cache` table
   - Update `listings_metadata` with sold_date
   - Progress logging

**Deliverables:**
- Working sold items sync service
- Integration test with mock Fulfillment API

**Testing:**
- Mock Fulfillment API with multi-page response
- Verify item IDs extracted correctly
- Test date parsing (ISO 8601 → YYYY-MM-DD)

---

### Phase 5: Traffic Sync Services - Day 5-6 (UPDATED)
**Goal:** Update traffic sync to handle both active and sold listings

**Tasks:**
1. Update `ebay_analytics/services/traffic_sync.py`:
   - `TrafficSyncService` class
   - Method: `sync_active_traffic(start, end)` - 3 API calls (existing logic)
   - **NEW:** Method: `sync_sold_traffic(start, end)`:
     - Get sold item IDs from repository
     - Batch by 200 items
     - Make 3 API calls per batch (total, promoted, organic)
     - Use `listing_ids` filter with URL encoding
     - Mark results with `listing_status='sold'`
   - Method: `sync_all_traffic(start, end)` - orchestrates both
   - Handle batching for large sold item counts
   - Progress logging (show batch progress)

**Deliverables:**
- Complete traffic sync for active + sold
- Proper batching for >200 sold items
- Integration tests

**Testing:**
- Mock scenarios with 50, 200, 500 sold items
- Verify batching logic
- Test listing_ids filter encoding
- Verify active vs sold marked correctly

---

### Phase 6: Report Generator - Day 7
**Goal:** Generate CSV including both active and sold listings

**Tasks:**
1. Update `ebay_analytics/services/report_generator.py`:
   - Execute updated SQL query (includes listing_status)
   - Handle quantity_available for sold items (show as 0)
   - Optionally add column or indicator for sold items
   - Format output matching eBay's 29 columns
   - Sort: sold items first, then active (or configurable)

**Testing:**
- Verify both active and sold rows in output
- Check calculations still correct
- Test edge cases (all sold, all active, mixed)

---

### Phase 7: CLI & Makefile - Day 8
**Goal:** User interface with sold listings support

**Tasks:**
1. Update `ebay_analytics/cli.py`:
   - **NEW:** Add `sync-sold-items` command:
     - `--days-back` option (default: 90)
     - `--marketplace` option
   - Update `sync-traffic` command:
     - `--include-sold` flag (default: True)
   - Update progress output to show sold items count

2. Update `Makefile` with new targets

**Testing:**
- Test all CLI commands
- Verify Makefile targets work
- Test date range parsing

---

### Phase 8: Documentation & Testing - Day 9
**Goal:** Complete documentation with sold listings instructions

**Tasks:**
1. Update `README.md`:
   - Explain sold listings support
   - Document 90-day retention window
   - Usage examples for sold items sync
   - Troubleshooting for sold listings

2. Complete test suite
3. Document sold listings limitations (90-day window)

---

## 8. Configuration (.env) (UPDATED)

### Required Variables

```bash
# eBay API Authentication
EBAY_ACCESS_TOKEN=your_production_access_token_here

# Marketplace Configuration
EBAY_MARKETPLACE_ID=EBAY_US

# Database Configuration
DB_PATH=data/ebay_analytics.db

# NEW: Sold Listings Configuration
SOLD_ITEMS_LOOKBACK_DAYS=90  # How far back to check for sold items (max 90)
SYNC_SOLD_ITEMS_ENABLED=true  # Enable/disable sold items syncing

# Optional: Default Date Ranges
DEFAULT_START_DATE=20260218
DEFAULT_END_DATE=20260225

# Optional: API Rate Limiting
API_MAX_RETRIES=3
API_RETRY_DELAY=2  # seconds
API_TIMEOUT=30     # seconds

# Optional: Batching Configuration
SOLD_ITEMS_BATCH_SIZE=200  # Max item IDs per Analytics API call
```

---

## 9. Dependencies (pyproject.toml)

```toml
[tool.poetry.dependencies]
python = "^3.8"
requests = "^2.31.0"
python-dotenv = "^1.0.0"
click = "^8.1.7"  # CLI framework

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
pytest-cov = "^4.1.0"
black = "^23.7.0"
flake8 = "^6.1.0"
```

---

## 10. Known Limitations & Workarounds (UPDATED)

### 10.1 Top 20 Search Position Metrics NOT Available
(No change from v1)

### 10.2 Percentage Change Columns Require Historical Baseline
(No change from v1)

### 10.3 **NEW:** 90-Day Sold Listings Traffic Retention

**Problem:** Analytics API only retains traffic data for sold listings for 90 days after sale.

**Implication:**
- Items sold >90 days ago: No traffic data available
- Must sync traffic within 90-day window or data is lost forever

**Workaround:**
- Run `sync-sold-items` at least weekly
- Run `sync-traffic` daily to capture before expiration
- Archive old data in database for historical analysis

### 10.4 **NEW:** Fulfillment API Date Format Complexity

**Problem:** Fulfillment API requires ISO 8601 format (2024-02-21T08:25:43.511Z) while Analytics API uses YYYYMMDD format.

**Solution:**
- Implement date conversion utility in `config.py`
- Handle timezone conversions properly (UTC)

### 10.5 **NEW:** Batching Overhead for Large Inventories

**Problem:** Sellers with >1,000 sold items per 90 days require many API calls.

**Example:**
- 2,000 sold items = 10 batches × 3 calls = 30 Analytics API calls
- Plus 1 Fulfillment API call per 200 orders

**Mitigation:**
- Implement smart caching (don't re-query sold items already in DB)
- Only sync incremental (new sales since last run)
- Run sold items sync weekly, not daily

### 10.6 Rate Limits & Pagination
(Updated from v1 to include Fulfillment API limits)

---

## 11. Performance Optimization Strategies (NEW)

### 11.1 Incremental Sold Items Sync

Instead of querying all 90 days every time:

```python
def sync_sold_items_incremental():
    """
    Only fetch orders since last sync date
    """
    last_sync = repository.get_last_sold_items_sync_date()
    if last_sync:
        start_date = last_sync
    else:
        start_date = datetime.now() - timedelta(days=90)

    end_date = datetime.now()

    # Only query new orders
    new_orders = fulfillment_api.get_orders(
        filter=f'creationdate:[{start_date.isoformat()}..{end_date.isoformat()}]'
    )

    # Store and return only new sold items
    return process_new_sold_items(new_orders)
```

### 11.2 Smart Batching for Traffic Queries

Group sold items by date ranges to reduce API calls:

```python
def batch_sold_items_by_date(sold_items, window_days=7):
    """
    Group sold items by date windows to optimize queries
    """
    batches = {}
    for item in sold_items:
        week_key = (item['sold_date'] // window_days) * window_days
        if week_key not in batches:
            batches[week_key] = []
        batches[week_key].append(item['item_id'])

    return batches  # Each batch covers one week
```

### 11.3 Parallel API Calls

Use async/threading for independent API calls:

```python
import concurrent.futures

def sync_traffic_parallel(start_date, end_date):
    """
    Run active and sold traffic sync in parallel
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_active = executor.submit(sync_active_traffic, start_date, end_date)
        future_sold = executor.submit(sync_sold_traffic, start_date, end_date)

        active_results = future_active.result()
        sold_results = future_sold.result()

    return active_results + sold_results
```

---

## 12. Success Criteria (UPDATED)

### Phase 1-8 Completion Checklist

- [ ] Database schema with 3 tables (metadata, traffic, sold_items_cache)
- [ ] Fulfillment API client implemented
- [ ] Analytics API supports listing_ids filter with URL encoding
- [ ] Sold items sync service functional
- [ ] Traffic sync works for both active and sold listings
- [ ] Batching logic handles >200 sold items correctly
- [ ] Report generator includes sold listings
- [ ] CLI has sync-sold-items command
- [ ] Makefile updated with sold listings targets
- [ ] README documents sold listings feature
- [ ] Test coverage >80%
- [ ] **NEW:** Can run end-to-end with sold listings successfully
- [ ] **NEW:** CSV output includes both active and sold items

### Validation Tests (UPDATED)

1. **End-to-End Test with Sold Listings:**
   ```bash
   make init-db
   make sync-metadata
   make sync-sold-items SOLD_LOOKBACK=30  # Last 30 days
   make sync-traffic START_DATE=20260218 END_DATE=20260225
   make generate-report
   ```
   - Verify: CSV includes both active and sold listings
   - Verify: Sold items have listing_status='sold' in database
   - Verify: Quantity available = 0 for sold items in CSV

2. **Batching Test:**
   - Mock scenario with 500 sold items
   - Verify: 3 batches created (200, 200, 100)
   - Verify: 9 API calls made (3 per batch)

3. **Data Integrity Test:**
   - Compare sold items from Fulfillment API with Analytics API results
   - Verify sold items have traffic data
   - Check that items sold >90 days ago return no traffic data

---

## 13. Timeline Summary (UPDATED)

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| 1. Foundation | 1 day | Database schema (3 tables), config |
| 2. API Clients | 1 day | Analytics, Inventory, **Fulfillment** clients |
| 3. Repository | 1 day | Data access for all 3 tables |
| 4. Sold Items Sync | 1 day | **NEW:** Fulfillment API integration |
| 5. Traffic Sync | 2 days | Active + sold traffic with batching |
| 6. Report Generator | 1 day | CSV with sold listings |
| 7. CLI & Makefile | 1 day | Updated interface |
| 8. Documentation | 1 day | README, tests, sold listings docs |

**Total Estimated Time:** 9 days (was 8 days in v1)

---

## Appendix A: API Call Sequence Diagram

```
[Daily Sync Process with Sold Listings]

1. Sync Sold Items (Weekly or Daily)
   ├─> Fulfillment API: GET /order (creationdate filter)
   ├─> Extract itemId from lineItems
   └─> Store in sold_items_cache table

2. Sync Active Listings Traffic (Daily)
   ├─> Analytics API Call 1: GET /traffic_report (no filter)
   ├─> Analytics API Call 2: GET /traffic_report (traffic_source=PROMOTED_LISTINGS)
   ├─> Analytics API Call 3: GET /traffic_report (traffic_source=ORGANIC)
   └─> Store with listing_status='active'

3. Sync Sold Listings Traffic (Daily)
   ├─> Get sold item IDs from sold_items_cache
   ├─> Batch into groups of 200
   ├─> For each batch:
   │   ├─> Analytics API Call 4: GET /traffic_report (listing_ids={...})
   │   ├─> Analytics API Call 5: GET /traffic_report (listing_ids={...}, traffic_source=PROMOTED)
   │   └─> Analytics API Call 6: GET /traffic_report (listing_ids={...}, traffic_source=ORGANIC)
   └─> Store with listing_status='sold'

4. Generate Report
   ├─> SQL Query: JOIN traffic + metadata
   ├─> Filter by date range
   ├─> Include both active and sold rows
   └─> Export to CSV (29 columns)
```

---

## Appendix B: Sold Listings API Examples

### Example 1: Fulfillment API Request

```bash
curl -X GET "https://api.ebay.com/sell/fulfillment/v1/order?filter=creationdate:[2026-02-01T00:00:00.000Z..2026-02-25T23:59:59.999Z]&limit=200&offset=0" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Accept: application/json"
```

**Response:**
```json
{
  "orders": [
    {
      "orderId": "20-12345-67890",
      "creationDate": "2026-02-15T14:32:21.511Z",
      "lineItems": [
        {"itemId": "198115000001", "quantity": 1, "title": "Wonderland #6"},
        {"itemId": "198115000002", "quantity": 2, "title": "Wonderland #4"}
      ]
    }
  ],
  "total": 1,
  "limit": 200,
  "offset": 0
}
```

### Example 2: Analytics API with listing_ids Filter

```bash
curl -X GET "https://api.ebay.com/sell/analytics/v1/traffic_report?dimension=LISTING&metric=TOTAL_IMPRESSION_TOTAL,LISTING_VIEWS_TOTAL,TRANSACTION&filter=marketplace_ids:%7BEBAY_US%7D,date_range:%5B20260201..20260225%5D,listing_ids:%7B198115000001%7C198115000002%7D" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "X-EBAY-C-MARKETPLACE-ID: EBAY_US"
```

**Response:**
```json
{
  "records": [
    {
      "listingId": "198115000001",
      "metricData": [
        {"key": "TOTAL_IMPRESSION_TOTAL", "value": "245"},
        {"key": "LISTING_VIEWS_TOTAL", "value": "67"},
        {"key": "TRANSACTION", "value": "1"}
      ]
    },
    {
      "listingId": "198115000002",
      "metricData": [
        {"key": "TOTAL_IMPRESSION_TOTAL", "value": "156"},
        {"key": "LISTING_VIEWS_TOTAL", "value": "34"},
        {"key": "TRANSACTION", "value": "2"}
      ]
    }
  ]
}
```

---

**End of Implementation Plan v2.0 (with Sold Listings Support)**
