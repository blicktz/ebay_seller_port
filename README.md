# eBay Seller Analytics

A comprehensive tool for fetching, storing, and analyzing eBay seller traffic data, replicating eBay's "Listings Traffic Report" with support for both **active and sold listings**.

## Features

- **Complete Traffic Data**: Fetches data for both active listings and sold items (within 90-day window)
- **Promoted/Organic Breakdown**: Separate metrics for promoted vs organic traffic
- **Local SQLite Storage**: Efficient caching and historical data retention
- **Exact CSV Format**: Generates reports matching eBay's 29-column format
- **Configurable Date Ranges**: Flexible date range selection via Makefile
- **Automatic Batching**: Handles large inventories with intelligent API batching
- **Retry Logic**: Robust error handling with exponential backoff

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Makefile Commands](#makefile-commands)
- [Database Schema](#database-schema)
- [API Limitations](#api-limitations)
- [Troubleshooting](#troubleshooting)

## Installation

### Prerequisites

- Python 3.12+
- Poetry (Python package manager)
- eBay Developer Account with Production API access

### Setup

1. **Clone or download this project**

2. **Install dependencies**
   ```bash
   make install
   # or
   poetry install
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your eBay access token
   ```

4. **Initialize database**
   ```bash
   make init-db
   ```

## Configuration

### Environment Variables

Edit `.env` file with your settings:

```bash
# REQUIRED: eBay API Authentication
EBAY_ACCESS_TOKEN=your_production_access_token_here

# Marketplace Configuration
EBAY_MARKETPLACE_ID=EBAY_US

# Database Path
DB_PATH=data/ebay_analytics.db

# Sold Listings Configuration
SOLD_ITEMS_LOOKBACK_DAYS=90
SYNC_SOLD_ITEMS_ENABLED=true

# Optional: API Configuration
API_MAX_RETRIES=3
API_RETRY_DELAY=2.0
API_TIMEOUT=30
```

### Getting Your eBay Access Token

1. Go to [eBay Developer Portal](https://developer.ebay.com/my/auth/)
2. Create an application (if not already done)
3. Generate a **Production User Access Token**
4. Copy the token to your `.env` file

**Note**: Tokens expire! You'll need to refresh them periodically.

## Quick Start

### Generate Report for Last 7 Days (All-in-One)

```bash
make full-sync
```

This will:
1. Sync listing metadata from Inventory API
2. Fetch sold items from last 90 days
3. Sync traffic data for active + sold listings
4. Generate CSV report

**Output**: `reports/traffic_report_<timestamp>.csv`

### Custom Date Range

```bash
make full-sync START_DATE=20260201 END_DATE=20260225
```

## Usage

### Step-by-Step Workflow

#### 1. Initialize Database (First Time Only)

```bash
make init-db
```

#### 2. Sync Listing Metadata

Fetch listing details (titles, categories, quantities):

```bash
make sync-metadata
```

#### 3. Sync Sold Items

Fetch sold item IDs from last N days:

```bash
make sync-sold-items SOLD_LOOKBACK=90
```

**Important**: Run this at least weekly to capture sold items within the 90-day retention window.

#### 4. Sync Traffic Data

Fetch traffic metrics for both active and sold listings:

```bash
make sync-traffic START_DATE=20260201 END_DATE=20260225
```

#### 5. Generate Report

Create CSV report from database:

```bash
make generate-report START_DATE=20260201 END_DATE=20260225 OUTPUT_FILE=reports/my_report.csv
```

## Makefile Commands

### Setup & Initialization

| Command | Description |
|---------|-------------|
| `make install` | Install dependencies via Poetry |
| `make init-db` | Initialize database schema |
| `make verify` | Verify database schema is valid |

### Data Syncing

| Command | Description | Parameters |
|---------|-------------|------------|
| `make sync-metadata` | Sync listing metadata | `MARKETPLACE` |
| `make sync-sold-items` | Sync sold items | `SOLD_LOOKBACK`, `MARKETPLACE` |
| `make sync-traffic` | Sync traffic data | `START_DATE`, `END_DATE`, `MARKETPLACE` |
| `make full-sync` | Complete sync + report | All date parameters |

### Report Generation

| Command | Description | Parameters |
|---------|-------------|------------|
| `make generate-report` | Generate CSV report | `START_DATE`, `END_DATE`, `OUTPUT_FILE` |

### Utilities

| Command | Description |
|---------|-------------|
| `make clean-db` | Reset database (deletes all data) |
| `make test` | Run unit tests |
| `make help` | Show all available commands |

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `START_DATE` | 7 days ago | Start date in YYYYMMDD format |
| `END_DATE` | Today | End date in YYYYMMDD format |
| `SOLD_LOOKBACK` | 90 | Days to look back for sold items |
| `MARKETPLACE` | EBAY_US | eBay marketplace ID |
| `OUTPUT_FILE` | Auto-generated | Output CSV file path |
| `DB_PATH` | data/ebay_analytics.db | Database file path |

### Example Commands

```bash
# Sync traffic for specific date range
make sync-traffic START_DATE=20260101 END_DATE=20260131

# Sync sold items from last 30 days only
make sync-sold-items SOLD_LOOKBACK=30

# Generate report for February 2026
make generate-report START_DATE=20260201 END_DATE=20260228 OUTPUT_FILE=reports/feb_2026.csv

# Full sync for Q1 2026
make full-sync START_DATE=20260101 END_DATE=20260331
```

## Database Schema

### Tables

#### `listings_metadata`
Stores listing information (title, category, status)

#### `daily_traffic_facts`
Stores raw traffic metrics (impressions, views, transactions)

#### `sold_items_cache`
Caches sold item IDs from Fulfillment API

### Fact-Only Storage

The database stores **only raw metrics** from APIs. All calculated fields (percentages, rates) are computed during report generation.

**Benefits**:
- Single source of truth
- Easy to recalculate if formulas change
- Smaller database size

## CSV Output Format

The generated CSV matches eBay's official "Listings Traffic Report" with **29 columns**:

1. Listing title
2. eBay item ID
3. Item Start Date
4. Category
5. Current promoted listings status
6. Quantity available
7. Total impressions
8. Click-through rate
9. Quantity sold
10. % Top 20 Search Impressions *(not available via API)*
11. Sales conversion rate
12-16. Top 20 position metrics *(not available via API)*
17. Total Search Impressions
18. Non-search promoted listings impressions
19-21. % Change metrics *(future enhancement)*
22. Total Promoted Listings impressions
23. Total Promoted Offsite impressions *(research needed)*
24. Total organic impressions
25. Total page views
26. Page views via promoted listings
27. Page views via promoted offsite *(may not be separable)*
28. Page views via organic
29. Page views organic offsite *(may not be separable)*

### Known Limitations

**Columns with NULL values**:
- Top 20 search position metrics (columns 10-16): Only available in Seller Hub UI
- % Change columns (13, 15, 19, 21): Requires historical baseline (future enhancement)
- Offsite metrics (23, 27, 29): May not be separable from main metrics

## API Limitations

### eBay Analytics API

- **Max 200 listings per request**: Automatically handled with batching
- **90-day query window**: Maximum date range per request
- **2-year historical data**: Can query up to 2 years back
- **Sold listings retention**: Traffic data only available for 90 days after sale

### eBay Fulfillment API

- **90-day order history**: Only returns orders from last 90 days
- **200 orders per request**: Automatically paginated

### Rate Limits

The system implements automatic retry with exponential backoff. Default configuration:
- Max retries: 3
- Retry delay: 2 seconds (increases exponentially)
- Request timeout: 30 seconds

## Troubleshooting

### "Authentication failed" Error

**Solution**: Your access token has expired. Generate a new token from eBay Developer Portal and update `.env`

### "No sold items found in cache"

**Solution**: Run `make sync-sold-items` first to populate the sold items cache

### "Rate limit exceeded"

**Solution**: Wait a few minutes and retry. The system will automatically retry with backoff.

### Missing Top 20 position data in CSV

**Expected**: These metrics are not available via the Analytics API. The columns will be blank.

### Empty CSV / No data

**Checklist**:
1. Verify date range has data: `make verify`
2. Check database has records: `sqlite3 data/ebay_analytics.db "SELECT COUNT(*) FROM daily_traffic_facts;"`
3. Ensure you've run sync commands first
4. Verify access token is valid

### Token expired during long sync

**Solution**: The system will fail with authentication error. Generate fresh token and restart sync.

## Advanced Usage

### CLI Commands (Without Makefile)

```bash
# Initialize database
poetry run python -m ebay_analytics.cli init-db

# Sync metadata
poetry run python -m ebay_analytics.cli sync-metadata

# Sync sold items
poetry run python -m ebay_analytics.cli sync-sold-items --days-back 90

# Sync traffic
poetry run python -m ebay_analytics.cli sync-traffic \\
  --start-date 20260201 \\
  --end-date 20260225 \\
  --include-sold

# Generate report
poetry run python -m ebay_analytics.cli generate-report \\
  --start-date 20260201 \\
  --end-date 20260225 \\
  --output reports/my_report.csv

# Full sync
poetry run python -m ebay_analytics.cli full-sync \\
  --start-date 20260201 \\
  --end-date 20260225
```

### Querying the Database Directly

```bash
sqlite3 data/ebay_analytics.db

# View schema
.schema

# Count total traffic records
SELECT COUNT(*) FROM daily_traffic_facts;

# View sample data
SELECT * FROM daily_traffic_facts LIMIT 5;

# Get top 10 listings by impressions
SELECT item_id, SUM(total_impressions) as total
FROM daily_traffic_facts
GROUP BY item_id
ORDER BY total DESC
LIMIT 10;
```

## Architecture

```
ebay_analytics/
├── api/              # API clients (Analytics, Fulfillment, Inventory)
├── db/               # Database schema & repositories
├── services/         # Business logic (sync services, report generator)
├── utils/            # Utilities (URL encoding, date parsing)
├── config.py         # Configuration loader
└── cli.py            # Command-line interface
```

## Performance Optimization

### For Large Inventories (>1000 items)

1. **Incremental sold items sync**: Run weekly instead of full 90-day sync
2. **Batch size configuration**: Adjust `SOLD_ITEMS_BATCH_SIZE` in `.env`
3. **Parallel API calls**: The traffic sync makes 3+ calls automatically
4. **Database indexing**: Already optimized with indexes on key columns

### Typical Sync Times

- **Metadata sync**: ~1-2 minutes (1000 items)
- **Sold items sync**: ~2-5 minutes (90 days, 500 orders)
- **Traffic sync**: ~5-10 minutes (both active + sold)
- **Report generation**: <1 second (from database)

## Support

For issues, questions, or feature requests:
1. Check the [Implementation Plan](docs/implementation_plan_v2_with_sold_listings.md) for technical details
2. Review [eBay Analytics API Mapping](docs/eBay%20Analytics%20API%20Mapping.md) for API specifics
3. Check troubleshooting section above

## License

This is a custom implementation for eBay seller analytics. Use at your own risk and ensure compliance with eBay API terms of service.

---

**Version**: 1.0.0
**Last Updated**: 2026-02-26
