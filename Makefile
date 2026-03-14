# eBay Seller Analytics - Makefile
# Provides convenient targets for running analytics tasks with configurable date ranges

.PHONY: help install init-db sync-metadata sync-sold-items sync-traffic generate-report full-sync clean-db verify test dvd-init-db dvd-lookup dvd-stats dvd-export dvd-clean-cache dvd-expire-all dvd-not-found generate-csv dvd-generate-csv

# Configuration variables (can be overridden: make sync-traffic START_DATE=20260201)
START_DATE ?= $(shell date -v-7d +%Y%m%d 2>/dev/null || date -d "7 days ago" +%Y%m%d 2>/dev/null)
END_DATE ?= $(shell date +%Y%m%d)
SOLD_LOOKBACK ?= 90
MARKETPLACE ?= EBAY_US
OUTPUT_FILE ?= reports/traffic_report_$(shell date +%Y%m%d_%H%M%S).csv
DB_PATH ?= data/ebay_analytics.db

# DVD Listing Automation variables
DVD_FILE ?= inputs/VHS-0314-1413.txt
DVD_DB_PATH ?= data/dvd_catalog.db
DVD_BATCH_SIZE ?= 20
DVD_EXPORT_FILE ?= data/dvd_exports/catalog_$(shell date +%Y%m%d_%H%M%S).csv

# Colors for output
COLOR_RESET = \033[0m
COLOR_BOLD = \033[1m
COLOR_GREEN = \033[32m
COLOR_BLUE = \033[34m
COLOR_YELLOW = \033[33m

help:
	@echo "$(COLOR_BOLD)eBay Seller Analytics - Available Commands$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_GREEN)Setup & Installation:$(COLOR_RESET)"
	@echo "  make install           Install dependencies via Poetry"
	@echo "  make init-db           Initialize database schema"
	@echo "  make verify            Verify database schema"
	@echo ""
	@echo "$(COLOR_GREEN)Data Syncing:$(COLOR_RESET)"
	@echo "  make sync-metadata     Sync listing metadata from Inventory API"
	@echo "  make sync-sold-items   Sync sold item IDs from Fulfillment API"
	@echo "  make sync-traffic      Sync traffic data for active + sold listings"
	@echo "  make full-sync         Run complete sync: metadata + sold + traffic + report"
	@echo ""
	@echo "$(COLOR_GREEN)Report Generation:$(COLOR_RESET)"
	@echo "  make generate-report   Generate CSV report (requires data in DB)"
	@echo ""
	@echo "$(COLOR_GREEN)Utilities:$(COLOR_RESET)"
	@echo "  make clean-db          Reset database (WARNING: deletes all data)"
	@echo "  make test              Run unit tests"
	@echo "  make help              Show this help message"
	@echo ""
	@echo "$(COLOR_GREEN)Media Listing Automation (DVD/CD/VHS):$(COLOR_RESET)"
	@echo "  make dvd-init-db       Initialize media catalog database"
	@echo "  make dvd-lookup        Look up UPCs from file (FILE=upcs.txt)"
	@echo "  make dvd-stats         Show catalog statistics"
	@echo "  make dvd-export        Export catalog to CSV"
	@echo "  make dvd-not-found     List UPCs not found in catalog"
	@echo "  make dvd-clean-cache   Remove expired cache entries"
	@echo "  make dvd-expire-all    Mark all entries as expired (keep history)"
	@echo "  make generate-csv      Generate eBay bulk upload CSV (set MEDIA_TYPE in .env)"
	@echo ""
	@echo "$(COLOR_YELLOW)Date Range Configuration:$(COLOR_RESET)"
	@echo "  START_DATE=$(START_DATE) (default: 7 days ago)"
	@echo "  END_DATE=$(END_DATE) (default: today)"
	@echo "  SOLD_LOOKBACK=$(SOLD_LOOKBACK) days (default: 90)"
	@echo "  MARKETPLACE=$(MARKETPLACE)"
	@echo ""
	@echo "$(COLOR_YELLOW)Examples:$(COLOR_RESET)"
	@echo "  make sync-traffic START_DATE=20260201 END_DATE=20260225"
	@echo "  make sync-sold-items SOLD_LOOKBACK=60"
	@echo "  make generate-report START_DATE=20260218 OUTPUT_FILE=reports/feb_week3.csv"
	@echo "  make full-sync START_DATE=20260201 END_DATE=20260225"
	@echo "  make dvd-lookup FILE=my_dvds.csv BATCH_SIZE=15"
	@echo ""

install:
	@echo "$(COLOR_BLUE)Installing dependencies via Poetry...$(COLOR_RESET)"
	poetry install
	@echo "$(COLOR_GREEN)✓ Installation complete$(COLOR_RESET)"

init-db:
	@echo "$(COLOR_BLUE)Initializing database...$(COLOR_RESET)"
	poetry run python -m ebay_analytics.cli init-db --db-path $(DB_PATH)

verify:
	@echo "$(COLOR_BLUE)Verifying database schema...$(COLOR_RESET)"
	poetry run python -m ebay_analytics.cli verify --db-path $(DB_PATH)

sync-metadata:
	@echo "$(COLOR_BLUE)Syncing listing metadata...$(COLOR_RESET)"
	@echo "  Marketplace: $(MARKETPLACE)"
	poetry run python -m ebay_analytics.cli sync-metadata --marketplace $(MARKETPLACE)

sync-sold-items:
	@echo "$(COLOR_BLUE)Syncing sold items...$(COLOR_RESET)"
	@echo "  Lookback: $(SOLD_LOOKBACK) days"
	@echo "  Marketplace: $(MARKETPLACE)"
	poetry run python -m ebay_analytics.cli sync-sold-items \
		--days-back $(SOLD_LOOKBACK) \
		--marketplace $(MARKETPLACE)

sync-traffic:
	@echo "$(COLOR_BLUE)Syncing traffic data...$(COLOR_RESET)"
	@echo "  Date range: $(START_DATE) to $(END_DATE)"
	@echo "  Marketplace: $(MARKETPLACE)"
	@echo "  Including sold listings: yes"
	poetry run python -m ebay_analytics.cli sync-traffic \
		--start-date $(START_DATE) \
		--end-date $(END_DATE) \
		--marketplace $(MARKETPLACE) \
		--include-sold

generate-report:
	@echo "$(COLOR_BLUE)Generating CSV report...$(COLOR_RESET)"
	@echo "  Date range: $(START_DATE) to $(END_DATE)"
	@echo "  Output: $(OUTPUT_FILE)"
	@mkdir -p reports
	poetry run python -m ebay_analytics.cli generate-report \
		--start-date $(START_DATE) \
		--end-date $(END_DATE) \
		--output $(OUTPUT_FILE)

full-sync:
	@echo "$(COLOR_BOLD)$(COLOR_GREEN)Running full sync...$(COLOR_RESET)"
	@echo "  Date range: $(START_DATE) to $(END_DATE)"
	@echo "  Sold items lookback: $(SOLD_LOOKBACK) days"
	@echo "  Output: $(OUTPUT_FILE)"
	@echo ""
	poetry run python -m ebay_analytics.cli full-sync \
		--start-date $(START_DATE) \
		--end-date $(END_DATE) \
		--output $(OUTPUT_FILE) \
		--days-back-sold $(SOLD_LOOKBACK)

clean-db:
	@echo "$(COLOR_YELLOW)WARNING: This will delete all data!$(COLOR_RESET)"
	@echo "Press Ctrl+C to cancel, or Enter to continue..."
	@read confirm
	rm -f $(DB_PATH)
	@echo "$(COLOR_GREEN)✓ Database deleted$(COLOR_RESET)"
	@$(MAKE) init-db

test:
	@echo "$(COLOR_BLUE)Running unit tests...$(COLOR_RESET)"
	poetry run pytest tests/ -v --cov=ebay_analytics --cov-report=term-missing

# Quick shortcuts for common workflows
.PHONY: quick-sync quick-report

quick-sync:
	@echo "$(COLOR_BOLD)Quick sync (last 7 days)...$(COLOR_RESET)"
	@$(MAKE) sync-metadata
	@$(MAKE) sync-sold-items SOLD_LOOKBACK=30
	@$(MAKE) sync-traffic

quick-report:
	@echo "$(COLOR_BOLD)Quick report (last 7 days)...$(COLOR_RESET)"
	@$(MAKE) generate-report

# ==============================================================================
# DVD Listing Automation Targets
# ==============================================================================

dvd-init-db:
	@echo "$(COLOR_BLUE)Initializing DVD catalog database...$(COLOR_RESET)"
	poetry run python -m dvd_listings.cli init-db --db-path $(DVD_DB_PATH)
	@echo "$(COLOR_GREEN)✓ DVD database initialized$(COLOR_RESET)"

dvd-lookup:
	@echo "$(COLOR_BLUE)Looking up DVDs from file...$(COLOR_RESET)"
	@echo "  File: $(DVD_FILE)"
	@echo "  Batch size: $(DVD_BATCH_SIZE)"
	@echo "  Export: $(DVD_EXPORT_FILE)"
	poetry run python -m dvd_listings.cli lookup-upcs \
		--file $(DVD_FILE) \
		--batch-size $(DVD_BATCH_SIZE) \
		--export $(DVD_EXPORT_FILE)

dvd-stats:
	@echo "$(COLOR_BLUE)DVD Catalog Statistics$(COLOR_RESET)"
	poetry run python -m dvd_listings.cli stats

dvd-export:
	@echo "$(COLOR_BLUE)Exporting DVD catalog...$(COLOR_RESET)"
	@mkdir -p data/dvd_exports
	poetry run python -m dvd_listings.cli export-results --output $(DVD_EXPORT_FILE)

dvd-not-found:
	@echo "$(COLOR_BLUE)UPCs not found in catalog:$(COLOR_RESET)"
	poetry run python -m dvd_listings.cli list-not-found

dvd-clean-cache:
	@echo "$(COLOR_BLUE)Cleaning expired cache entries...$(COLOR_RESET)"
	poetry run python -m dvd_listings.cli clean-cache

dvd-expire-all:
	@echo "$(COLOR_BLUE)Expiring all active cache entries...$(COLOR_RESET)"
	poetry run python -m dvd_listings.cli expire-all

generate-csv:
	@echo "$(COLOR_BLUE)Generating eBay bulk upload draft CSV (Media Type: $${MEDIA_TYPE:-DVD})...$(COLOR_RESET)"
	poetry run python scripts/generate_ebay_draft.py

# Backward compatibility alias
dvd-generate-csv: generate-csv
