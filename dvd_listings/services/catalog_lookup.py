"""
Catalog Lookup Orchestration Service.

This service orchestrates the complete DVD lookup workflow:
1. Loads UPCs from files
2. Checks cache for existing data
3. Calls eBay Catalog API for missing UPCs
4. Stores results in database
5. Generates summary reports
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ebay_analytics.config import Config
from ..api.catalog import CatalogAPIClient
from ..db.repository import CatalogRepository
from ..models.product import CatalogProduct


@dataclass
class LookupSummary:
    """Summary of catalog lookup operation."""

    total_upcs: int
    cache_hits: int
    api_lookups: int
    found_count: int
    not_found_count: int
    errors: List[Dict[str, Any]]
    duration_seconds: float


class CatalogLookupService:
    """
    Service for orchestrating DVD catalog lookups.

    Combines UPC loading, caching, API calls, and database storage
    into a complete workflow.
    """

    def __init__(
        self,
        config: Config,
        db_path: str = "data/dvd_catalog.db",
        batch_size: int = 20,
        use_cache: bool = True
    ):
        """
        Initialize catalog lookup service.

        Args:
            config: Configuration with eBay API credentials
            db_path: Path to catalog database
            batch_size: Number of UPCs per API request
            use_cache: Whether to use cached data
        """
        self.config = config
        self.batch_size = batch_size
        self.use_cache = use_cache

        self.api_client = CatalogAPIClient(config)
        self.repository = CatalogRepository(db_path)

    def lookup_upcs(
        self,
        upcs: List[str],
        force_refresh: bool = False,
        progress_callback: Optional[callable] = None,
        media_type: str = 'DVD'
    ) -> LookupSummary:
        """
        Look up multiple UPCs in eBay catalog.

        Checks cache first, then makes API calls for missing UPCs.
        Stores all results in database.

        Args:
            upcs: List of UPC codes to look up
            force_refresh: If True, ignore cache and fetch fresh data
            progress_callback: Optional callback function(current, total, message)
            media_type: Media type (DVD, CD, VHS) - from MEDIA_TYPE env var

        Returns:
            LookupSummary with results and statistics

        Example:
            >>> service = CatalogLookupService(config)
            >>> summary = service.lookup_upcs(['0786936735390', '0012569679672'])
            >>> print(f"Found {summary.found_count} products")
            >>> print(f"Cache hits: {summary.cache_hits}")
        """
        start_time = datetime.now()

        cache_hits = 0
        api_lookups = 0
        found_count = 0
        not_found_upcs: List[str] = []
        errors: List[Dict[str, Any]] = []

        # Phase 1: Check cache for existing data
        upcs_to_fetch = []

        print(f"Checking cache for {len(upcs)} UPC(s)...")

        for upc in upcs:
            if self.use_cache and not force_refresh:
                cached_products = self.repository.get_products_by_upc(upc)
                if cached_products:
                    cache_hits += 1
                    found_count += len(cached_products)
                    if len(cached_products) == 1:
                        print(f"  ✓ Cache hit: {upc} - {cached_products[0].title}")
                    else:
                        print(f"  ✓ Cache hit: {upc} - {len(cached_products)} editions")
                        for product in cached_products:
                            print(f"      - {product.title}")
                    continue

            upcs_to_fetch.append(upc)

        print(f"  Cache hits: {cache_hits}/{len(upcs)}")
        print(f"  Need to fetch: {len(upcs_to_fetch)}")
        print()

        # Phase 2: Fetch missing UPCs from API
        if upcs_to_fetch:
            print(f"Fetching {len(upcs_to_fetch)} UPC(s) from eBay Catalog API...")

            try:
                result = self.api_client.search_dvds_by_upcs(
                    upcs=upcs_to_fetch,
                    batch_size=self.batch_size,
                    progress_callback=progress_callback
                )

                api_lookups = result['total_searched']
                products = result['products']
                not_found_upcs = result['not_found_upcs']

                print()
                print(f"API Results:")
                print(f"  Found: {result['found_count']} products")
                print(f"  Not found: {len(not_found_upcs)} UPCs")
                print()

                # Phase 3: Store products in database
                if products:
                    print(f"Storing {len(products)} product(s) in database...")

                    # Track UPCs with multiple matches
                    upc_counts = {}
                    for product_data in products:
                        upc_raw = (
                            product_data.get('upc', [None])[0]
                            or product_data.get('gtin', [None])[0]
                            or ''
                        )
                        if upc_raw:
                            normalized_upc = upc_raw.lstrip('0').zfill(12) if upc_raw.lstrip('0') else '0'.zfill(12)
                            upc_counts[normalized_upc] = upc_counts.get(normalized_upc, 0) + 1

                    for product_data in products:
                        try:
                            # Convert API response to CatalogProduct with media type from env
                            product = CatalogProduct.from_api_response(product_data, media_type=media_type)

                            # Save to database
                            self.repository.save_product(product)
                            found_count += 1

                            print(f"  ✓ Saved: {product.upc} - {product.title}")

                        except Exception as e:
                            errors.append({
                                'upc': product_data.get('upc', ['unknown'])[0],
                                'error': str(e),
                                'type': 'save_error'
                            })
                            print(f"  ✗ Error saving product: {e}")

                    # Show warning for UPCs with multiple editions
                    multi_edition_upcs = [upc for upc, count in upc_counts.items() if count > 1]
                    if multi_edition_upcs:
                        print()
                        print(f"  ⚠ Note: {len(multi_edition_upcs)} UPC(s) have multiple editions:")
                        for upc in multi_edition_upcs:
                            print(f"      - {upc} ({upc_counts[upc]} editions)")
                        print(f"  Review your export to choose the correct edition.")

                # Phase 4: Log not-found UPCs
                if not_found_upcs:
                    print()
                    print(f"Logging {len(not_found_upcs)} not-found UPC(s)...")

                    for upc in not_found_upcs:
                        self.repository.log_lookup(upc, found=False)
                        print(f"  - {upc}")

            except Exception as e:
                errors.append({
                    'error': str(e),
                    'type': 'api_error'
                })
                print(f"✗ API Error: {e}")

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        # Create summary
        summary = LookupSummary(
            total_upcs=len(upcs),
            cache_hits=cache_hits,
            api_lookups=api_lookups,
            found_count=found_count,
            not_found_count=len(not_found_upcs),
            errors=errors,
            duration_seconds=duration
        )

        return summary

    def lookup_from_file(
        self,
        filepath: str,
        file_type: Optional[str] = None,
        upc_column: str = 'upc',
        force_refresh: bool = False,
        media_type: str = 'DVD'
    ) -> LookupSummary:
        """
        Load UPCs from file and perform catalog lookup.

        Args:
            filepath: Path to file containing UPCs
            file_type: File type ('csv' or 'txt'), auto-detected if None
            upc_column: Column name for CSV files
            force_refresh: If True, ignore cache

        Returns:
            LookupSummary with results

        Example:
            >>> summary = service.lookup_from_file('upcs.csv')
            >>> print(f"Processed {summary.total_upcs} UPCs")
        """
        from .upc_loader import UPCLoader

        print(f"Loading UPCs from: {filepath}")
        print("-" * 60)

        # Load UPCs from file
        if file_type == 'csv' or filepath.endswith('.csv'):
            load_result = UPCLoader.load_from_csv(
                filepath,
                upc_column=upc_column,
                skip_invalid=True
            )
        else:
            load_result = UPCLoader.load_from_text(
                filepath,
                skip_invalid=True
            )

        print(f"✓ Loaded {load_result.valid_count} valid UPC(s)")
        print(f"  Total lines: {load_result.total_lines}")
        print(f"  Valid: {load_result.valid_count}")
        print(f"  Invalid: {load_result.invalid_count}")
        print(f"  Duplicates removed: {load_result.duplicate_count}")

        if load_result.invalid_upcs:
            print(f"\n⚠ Invalid UPCs:")
            for invalid in load_result.invalid_upcs[:10]:  # Show first 10
                print(f"  Line {invalid['line']}: {invalid['value']} - {invalid['reason']}")
            if len(load_result.invalid_upcs) > 10:
                print(f"  ... and {len(load_result.invalid_upcs) - 10} more")

        print()
        print("=" * 60)
        print()

        # Perform lookup
        return self.lookup_upcs(
            upcs=load_result.upcs,
            force_refresh=force_refresh,
            media_type=media_type
        )

    def get_summary_report(self, summary: LookupSummary) -> str:
        """
        Generate a formatted summary report.

        Args:
            summary: LookupSummary object

        Returns:
            Formatted summary string

        Example:
            >>> summary = service.lookup_upcs(upcs)
            >>> print(service.get_summary_report(summary))
        """
        lines = []
        lines.append("=" * 60)
        lines.append("CATALOG LOOKUP SUMMARY")
        lines.append("=" * 60)
        lines.append(f"Total UPCs processed: {summary.total_upcs}")
        lines.append(f"Cache hits: {summary.cache_hits}")
        lines.append(f"API lookups: {summary.api_lookups}")
        lines.append(f"")
        lines.append(f"Results:")
        lines.append(f"  ✓ Found: {summary.found_count}")
        lines.append(f"  ✗ Not found: {summary.not_found_count}")
        lines.append(f"")
        lines.append(f"Duration: {summary.duration_seconds:.1f} seconds")

        if summary.errors:
            lines.append(f"")
            lines.append(f"Errors: {len(summary.errors)}")
            for error in summary.errors[:5]:  # Show first 5
                lines.append(f"  - {error.get('type')}: {error.get('error')}")
            if len(summary.errors) > 5:
                lines.append(f"  ... and {len(summary.errors) - 5} more")

        lines.append("=" * 60)

        return "\n".join(lines)

    def export_results_to_csv(
        self,
        output_path: str,
        include_cached: bool = True
    ) -> int:
        """
        Export catalog products to CSV file.

        Args:
            output_path: Path to output CSV file
            include_cached: If True, include all cached products

        Returns:
            Number of products exported

        Example:
            >>> count = service.export_results_to_csv('results.csv')
            >>> print(f"Exported {count} products")
        """
        import csv

        products = self.repository.get_all_products(include_expired=False)

        if not products:
            print("No products to export")
            return 0

        # Create output directory if needed
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # Write header
            writer.writerow([
                'UPC',
                'ePID',
                'Title',
                'Brand',
                'Format',
                'Genre',
                'Release Year',
                'Actors',
                'Directors',
                'Studio',
                'Rating',
                'Primary Image URL',
                'Product Web URL',
                'Fetched At'
            ])

            # Write products
            for product in products:
                actors = ', '.join(product.dvd_aspects.actors) if product.dvd_aspects else ''
                directors = ', '.join(product.dvd_aspects.directors) if product.dvd_aspects else ''

                writer.writerow([
                    product.upc,
                    product.epid,
                    product.title,
                    product.brand or '',
                    product.dvd_aspects.format if product.dvd_aspects else '',
                    product.dvd_aspects.genre if product.dvd_aspects else '',
                    product.dvd_aspects.release_year if product.dvd_aspects else '',
                    actors,
                    directors,
                    product.dvd_aspects.studio if product.dvd_aspects else '',
                    product.dvd_aspects.rating if product.dvd_aspects else '',
                    product.primary_image_url or '',
                    product.product_web_url or '',
                    product.fetched_at.isoformat() if product.fetched_at else ''
                ])

        print(f"✓ Exported {len(products)} product(s) to {output_path}")
        return len(products)


if __name__ == "__main__":
    """Test catalog lookup service."""
    from ebay_analytics.config import load_config
    from ..db.schema import init_database

    print("Testing CatalogLookupService...")
    print("=" * 60)

    try:
        # Load config
        config = load_config()

        # Initialize test database
        test_db = "data/dvd_catalog_test.db"
        init_database(test_db)

        # Create service
        service = CatalogLookupService(
            config=config,
            db_path=test_db,
            batch_size=10
        )

        print("✓ Service initialized")
        print()

        # Test with sample UPCs
        test_upcs = [
            '0786936735390',  # Toy Story
            '0012569679672',  # The Matrix
        ]

        print(f"Testing lookup with {len(test_upcs)} UPCs...")
        summary = service.lookup_upcs(test_upcs)

        print()
        print(service.get_summary_report(summary))

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
