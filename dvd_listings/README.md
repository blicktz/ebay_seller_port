# DVD Listing Automation

Automate the creation of eBay DVD listings by looking up product information from eBay's Catalog API using UPC codes.

## Features

- **UPC Batch Lookup**: Search multiple DVDs by UPC in efficient batches
- **eBay Catalog Integration**: Retrieve ePID, title, actors, directors, and other DVD details
- **Smart Caching**: Cache catalog data locally (30-day default) to reduce API calls
- **CSV/Text File Support**: Load UPCs from CSV or plain text files
- **Export Results**: Export catalog data to CSV for review
- **CLI Interface**: Command-line tools for all operations
- **Future-Ready**: Designed for extension to image upload and listing creation

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [File Formats](#file-formats)
- [CLI Commands](#cli-commands)
- [Configuration](#configuration)
- [API Details](#api-details)
- [Troubleshooting](#troubleshooting)
- [Future Development](#future-development)

## Quick Start

```bash
# 1. Initialize the database
python -m dvd_listings.cli init-db

# 2. Look up UPCs from a CSV file
python -m dvd_listings.cli lookup-upcs --file upcs.csv

# 3. Export results
python -m dvd_listings.cli export-results --output results.csv

# 4. View statistics
python -m dvd_listings.cli stats
```

## Installation

### Prerequisites

- Python 3.12+
- eBay Developer Account with Production API access
- eBay User Access Token with `commerce.catalog.readonly` or `sell.inventory` scope

### Setup

1. **Configure environment variables** (if not already done):
   ```bash
   # Update .env file with DVD-specific settings
   DVD_DB_PATH=data/dvd_catalog.db
   DVD_CATALOG_BATCH_SIZE=20
   DVD_CACHE_EXPIRY_DAYS=30
   ```

2. **Initialize the database**:
   ```bash
   python -m dvd_listings.cli init-db
   ```

## Usage

### Basic Workflow

1. **Prepare UPC file** - Create a CSV or text file with your DVD UPCs
2. **Run catalog lookup** - Look up products in eBay's catalog
3. **Review results** - Check found vs not-found UPCs
4. **Export data** - Export catalog information for next steps

### Example: Look up 300+ DVDs

```bash
# Create a text file with UPCs (one per line)
cat > my_dvds.txt <<EOF
0786936735390
0012569679672
0013131034196
EOF

# Look up all UPCs and export results
python -m dvd_listings.cli lookup-upcs \\
    --file my_dvds.txt \\
    --export dvd_catalog_results.csv

# Check statistics
python -m dvd_listings.cli stats
```

### Example: CSV File with Metadata

```bash
# If your CSV has UPCs and other data:
python -m dvd_listings.cli lookup-upcs \\
    --file inventory.csv \\
    --file-type csv \\
    --upc-column "UPC Code" \\
    --export results.csv
```

## File Formats

### Text File Format

One UPC per line. Empty lines and lines starting with `#` are ignored.

```text
# My DVD Collection
0786936735390
0012569679672

# More DVDs
0013131034196
```

### CSV File Format

Must have a column containing UPC codes. Specify column name with `--upc-column`.

```csv
upc,title,notes
0786936735390,Toy Story,Great condition
0012569679672,The Matrix,Still sealed
0013131034196,Finding Nemo,DVD
```

## CLI Commands

### `init-db`

Initialize the DVD catalog database.

```bash
python -m dvd_listings.cli init-db [--db-path PATH]
```

**Options:**
- `--db-path`: Override database path from config

**Example:**
```bash
python -m dvd_listings.cli init-db
```

---

### `lookup-upcs`

Look up UPCs from a file using eBay Catalog API.

```bash
python -m dvd_listings.cli lookup-upcs \\
    --file FILE \\
    [--file-type {csv,txt}] \\
    [--upc-column COLUMN] \\
    [--batch-size SIZE] \\
    [--force-refresh] \\
    [--export OUTPUT]
```

**Options:**
- `--file, -f`: Path to file containing UPCs (required)
- `--file-type`: File type (auto-detected if not specified)
- `--upc-column`: Column name for UPCs in CSV (default: "upc")
- `--batch-size`: UPCs per API request (default from config)
- `--force-refresh`: Ignore cache and fetch fresh data
- `--export`: Export results to CSV file

**Examples:**
```bash
# Basic lookup from text file
python -m dvd_listings.cli lookup-upcs --file upcs.txt

# CSV with custom column name
python -m dvd_listings.cli lookup-upcs \\
    --file inventory.csv \\
    --upc-column "Barcode"

# Force refresh and export
python -m dvd_listings.cli lookup-upcs \\
    --file upcs.txt \\
    --force-refresh \\
    --export fresh_results.csv
```

---

### `show-cache`

View cached product data.

```bash
python -m dvd_listings.cli show-cache [--upc UPC] [--limit N]
```

**Options:**
- `--upc`: Show details for specific UPC
- `--limit`: Number of products to show (default: 10)

**Examples:**
```bash
# Show specific product
python -m dvd_listings.cli show-cache --upc 0786936735390

# Show last 20 cached products
python -m dvd_listings.cli show-cache --limit 20
```

---

### `list-not-found`

List UPCs that were not found in eBay catalog.

```bash
python -m dvd_listings.cli list-not-found [--output FILE]
```

**Options:**
- `--output`: Export not-found UPCs to file

**Example:**
```bash
# List not-found UPCs
python -m dvd_listings.cli list-not-found

# Export to file for manual review
python -m dvd_listings.cli list-not-found --output manual_entry_needed.txt
```

---

### `export-results`

Export cached products to CSV file.

```bash
python -m dvd_listings.cli export-results --output FILE
```

**Options:**
- `--output, -o`: Output CSV file path (required)

**Example:**
```bash
python -m dvd_listings.cli export-results --output all_dvds.csv
```

**Output CSV Columns:**
- UPC, ePID, Title, Brand, Format, Genre, Release Year
- Actors, Directors, Studio, Rating
- Primary Image URL, Product Web URL, Fetched At

---

### `stats`

Show database statistics.

```bash
python -m dvd_listings.cli stats
```

**Example Output:**
```
DVD Catalog Statistics
============================================================
Products cached: 287
Total lookups: 305
Not found: 18
Expired entries: 0
Last fetch: 2026-03-13 18:45:23

Top Genres:
  Action: 45
  Comedy: 38
  Drama: 32
  ...
```

---

### `clean-cache`

Remove expired entries from cache.

```bash
python -m dvd_listings.cli clean-cache [--dry-run]
```

**Options:**
- `--dry-run`: Show what would be deleted without actually deleting

**Example:**
```bash
# Preview what will be deleted
python -m dvd_listings.cli clean-cache --dry-run

# Actually clean expired entries
python -m dvd_listings.cli clean-cache
```

## Configuration

All configuration is set in `.env` file. See `.env.example` for details.

### Key Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DVD_DB_PATH` | data/dvd_catalog.db | Database location |
| `DVD_CATALOG_BATCH_SIZE` | 20 | UPCs per API request |
| `DVD_CACHE_EXPIRY_DAYS` | 30 | Cache validity period |
| `DVD_USE_CACHE` | true | Enable/disable cache |
| `DVD_AUTO_EXPORT` | false | Auto-export after lookup |
| `DVD_EXPORT_PATH` | data/dvd_exports | Default export directory |

### Batch Size Tuning

- **10-15**: Conservative, fewer timeout issues
- **20**: Recommended balance (default)
- **30-50**: Faster but may have reliability issues

## API Details

### eBay Commerce Catalog API

**Endpoint:** `GET /commerce/catalog/v1_beta/product_summary/search`

**Authentication:** User Access Token (OAuth 2.0)

**Required Scope:** `commerce.catalog.readonly` or `sell.inventory`

**Rate Limits:**
- 100,000 calls/day per user
- Shared across all Catalog API endpoints

### What Data is Retrieved

For each UPC found in the catalog, the system retrieves:

- **ePID** (eBay Product ID) - Key for creating listings
- **Title** - Official product title
- **Brand** - Manufacturer
- **Aspects** - DVD-specific data:
  - Actors
  - Directors
  - Studio
  - Release Year
  - Format (DVD, Blu-ray, etc.)
  - Genre
  - MPAA Rating
  - Region Code
- **Images** - Product images from catalog
- **URLs** - Links to eBay product page and API endpoint

### Cache Strategy

- **Initial lookup**: Queries eBay Catalog API
- **Subsequent lookups**: Uses cached data if not expired
- **Cache duration**: 30 days (configurable)
- **Force refresh**: `--force-refresh` flag bypasses cache

## Troubleshooting

### "No valid UPCs found in file"

**Causes:**
- UPCs are not 12-13 digits
- Wrong column name in CSV
- File encoding issues

**Solutions:**
```bash
# For CSV, check column name:
head -1 myfile.csv  # Should show column headers

# Use correct column name:
python -m dvd_listings.cli lookup-upcs --file myfile.csv --upc-column "Barcode"

# For text files, ensure one UPC per line with no extra characters
```

---

### "UPC not found in catalog"

**Causes:**
- DVD is not in eBay's master catalog
- UPC is incorrect
- Product is too old/obscure

**Solutions:**
1. Verify UPC is correct
2. Try searching eBay manually with UPC
3. For not-found UPCs, manual entry will be required:
   ```bash
   python -m dvd_listings.cli list-not-found --output manual.txt
   ```

---

### "Rate limit exceeded"

**Cause:** Too many API calls in short time

**Solution:**
- Wait 5-10 minutes and retry
- Reduce batch size:
  ```bash
  python -m dvd_listings.cli lookup-upcs --file upcs.csv --batch-size 10
  ```

---

### "Authentication failed"

**Cause:** Expired or invalid access token

**Solution:**
1. Generate new token at https://developer.ebay.com/my/auth/
2. Ensure token has `commerce.catalog.readonly` scope
3. Update `EBAY_ACCESS_TOKEN` in `.env`

---

### "Database is locked"

**Cause:** Another process is using the database

**Solution:**
- Close other Python processes
- Wait a few seconds and retry
- Check for stale processes: `ps aux | grep python`

## Future Development

This subsystem is Phase 1 of the DVD listing automation workflow. Future phases include:

### Phase 2: Image Management
- Upload DVD cover photos
- Associate images with UPC codes
- Bulk image processing

### Phase 3: Listing Creation
- Create draft listings using ePID
- Set pricing, condition, shipping
- Bulk publish to eBay

### Phase 4: Inventory Management
- Track physical inventory
- SKU generation
- Multi-location support

## Architecture

```
dvd_listings/
├── api/                    # eBay API clients
│   └── catalog.py         # Catalog API client
├── db/                     # Database layer
│   ├── schema.py          # Database schema
│   └── repository.py      # Data access
├── models/                 # Data models
│   └── product.py         # CatalogProduct, DVDAspects
├── services/               # Business logic
│   ├── upc_loader.py      # UPC file loading
│   └── catalog_lookup.py  # Lookup orchestration
├── config.py              # Configuration
└── cli.py                 # Command-line interface
```

## Support

For issues or questions:
1. Check this README and [Troubleshooting](#troubleshooting) section
2. Review eBay Catalog API docs: https://developer.ebay.com/api-docs/commerce/catalog/overview.html
3. Check `.env` configuration

## License

Part of the eBay Seller Analytics project. Use at your own risk and ensure compliance with eBay API terms of service.

---

**Version**: 0.1.0
**Last Updated**: 2026-03-13
