"""
eBay Catalog API client for DVD product lookup.

This client extends the BaseAPIClient from ebay_analytics to provide
access to the eBay Commerce Catalog API for looking up DVD products by UPC.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

# Add parent directory to path to import ebay_analytics
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ebay_analytics.api.base import BaseAPIClient
from ebay_analytics.config import Config


class CatalogAPIClient(BaseAPIClient):
    """
    Client for eBay Commerce Catalog API.

    Provides methods to search for DVD products by UPC/GTIN and retrieve
    detailed product information including ePID, title, aspects, and images.
    """

    BASE_URL = "https://api.ebay.com/commerce/catalog/v1_beta"

    def __init__(self, config: Config):
        """
        Initialize Catalog API client.

        Args:
            config: Configuration object with eBay API credentials
        """
        super().__init__(config)

        # Add marketplace header for Catalog API
        self.session.headers.update({
            'X-EBAY-C-MARKETPLACE-ID': config.ebay_marketplace_id
        })

    def search_by_gtin(
        self,
        gtins: List[str],
        limit: int = 200,
        fieldgroups: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search catalog by one or more GTINs (UPC/EAN/ISBN).

        Args:
            gtins: List of GTIN values (UPC codes)
            limit: Results per page (1-200, default: 200)
            fieldgroups: Optional response content control
                       (MATCHING_PRODUCTS, ASPECT_REFINEMENTS, FULL)

        Returns:
            ProductSearchResponse dictionary with fields:
            - total: Total number of matches
            - productSummaries: Array of product summary objects
            - href: URL to this search
            - limit: Page size
            - offset: Current offset

        Example:
            >>> client = CatalogAPIClient(config)
            >>> result = client.search_by_gtin(['0786936735390'])
            >>> if result.get('productSummaries'):
            ...     product = result['productSummaries'][0]
            ...     print(f"Found: {product['title']}")
            ...     print(f"ePID: {product['epid']}")
        """
        url = f"{self.BASE_URL}/product_summary/search"

        params = {
            'gtin': ','.join(gtins),
            'limit': str(min(limit, 200))  # Max 200
        }

        if fieldgroups:
            params['fieldgroups'] = fieldgroups

        return self.get(url, params=params)

    def get_product(self, epid: str) -> Dict[str, Any]:
        """
        Get full product details by ePID.

        This method retrieves comprehensive product information including
        descriptions, categories, and all available aspects.

        Args:
            epid: eBay Product ID (from search results)

        Returns:
            Full Product object dictionary

        Example:
            >>> product = client.get_product('123456789')
            >>> print(product['title'])
            >>> print(product.get('description', 'N/A'))
        """
        url = f"{self.BASE_URL}/product/{epid}"
        return self.get(url)

    def search_dvds_by_upcs(
        self,
        upcs: List[str],
        batch_size: int = 20,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Search for multiple DVDs with automatic batching and progress tracking.

        This is the recommended method for bulk DVD lookups. It automatically
        batches UPCs into optimal request sizes and handles delays between
        batches to respect rate limits.

        Args:
            upcs: List of UPC codes to search
            batch_size: Number of UPCs per request (default: 20, max: 50)
            progress_callback: Optional function called after each batch
                             with signature: callback(batch_num, total_batches, found_count)

        Returns:
            Dictionary with:
            - products: List of all found product summaries
            - found_count: Number of products found
            - not_found_upcs: List of UPCs not in catalog
            - batch_count: Number of batches processed
            - total_searched: Total UPCs searched

        Example:
            >>> def progress(batch, total, found):
            ...     print(f"Batch {batch}/{total}: {found} products found")
            >>>
            >>> result = client.search_dvds_by_upcs(
            ...     upcs=['0786936735390', '0012569679672'],
            ...     progress_callback=progress
            ... )
            >>> print(f"Found {result['found_count']} products")
            >>> for upc in result['not_found_upcs']:
            ...     print(f"Not found: {upc}")
        """
        all_products = []
        found_upcs = set()
        total_batches = (len(upcs) + batch_size - 1) // batch_size  # Ceiling division

        for i in range(0, len(upcs), batch_size):
            batch = upcs[i:i + batch_size]
            batch_num = i // batch_size + 1

            print(f"[Batch {batch_num}/{total_batches}] Searching {len(batch)} UPCs...")

            try:
                response = self.search_by_gtin(batch)
                products = response.get('productSummaries', [])
                all_products.extend(products)

                # Track which UPCs were found (normalize to 12 digits for comparison)
                for product in products:
                    product_upcs = product.get('upc', [])
                    # Normalize UPCs: strip leading zeros and pad to 12 digits
                    for upc in product_upcs:
                        normalized = upc.lstrip('0').zfill(12) if upc.lstrip('0') else '0'.zfill(12)
                        found_upcs.add(normalized)

                    # Also check 'gtin' field
                    product_gtins = product.get('gtin', [])
                    for gtin in product_gtins:
                        normalized = gtin.lstrip('0').zfill(12) if gtin.lstrip('0') else '0'.zfill(12)
                        found_upcs.add(normalized)

                print(f"  → Found {len(products)} product(s)")

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(batch_num, total_batches, len(all_products))

            except Exception as e:
                print(f"  ✗ Error searching batch: {e}")
                # Continue with next batch rather than failing completely

            # Delay between batches (except for the last batch)
            if i + batch_size < len(upcs):
                delay = self.config.api_call_delay_between_batches
                print(f"  Waiting {delay:.1f}s before next batch...")
                time.sleep(delay)

        # Determine which UPCs were not found
        searched_upcs = set(upcs)
        not_found_upcs = list(searched_upcs - found_upcs)

        return {
            'products': all_products,
            'found_count': len(all_products),
            'not_found_upcs': not_found_upcs,
            'batch_count': total_batches,
            'total_searched': len(upcs)
        }

    def search_single_upc(self, upc: str) -> Optional[Dict[str, Any]]:
        """
        Search for a single UPC and return the first matching product.

        Convenience method for single UPC lookups that returns None
        if the UPC is not found in the catalog.

        Args:
            upc: Single UPC code to search

        Returns:
            Product summary dictionary or None if not found

        Example:
            >>> product = client.search_single_upc('0786936735390')
            >>> if product:
            ...     print(f"Found: {product['title']}")
            ... else:
            ...     print("UPC not in catalog")
        """
        response = self.search_by_gtin([upc], limit=1)
        products = response.get('productSummaries', [])

        if products:
            return products[0]
        return None


if __name__ == "__main__":
    """Test Catalog API client with sample UPC."""
    from ebay_analytics.config import load_config

    print("Testing CatalogAPIClient...")
    print("=" * 60)

    try:
        config = load_config()
        client = CatalogAPIClient(config)

        print(f"✓ Client initialized")
        print(f"  Base URL: {client.BASE_URL}")
        print(f"  Marketplace: {config.ebay_marketplace_id}")
        print()

        # Test with a sample DVD UPC (Toy Story)
        test_upc = "0786936735390"
        print(f"Testing single UPC search: {test_upc}")
        print("-" * 60)

        product = client.search_single_upc(test_upc)

        if product:
            print(f"✓ Product found!")
            print(f"  ePID: {product.get('epid')}")
            print(f"  Title: {product.get('title')}")
            print(f"  Brand: {product.get('brand', 'N/A')}")

            aspects = product.get('aspects', [])
            if aspects:
                print(f"  Aspects:")
                for aspect in aspects[:5]:  # Show first 5
                    name = aspect.get('localizedName')
                    values = aspect.get('localizedValues', [])
                    print(f"    - {name}: {', '.join(values)}")
        else:
            print("✗ UPC not found in catalog")

        print()
        print("Session stats:")
        stats = client.get_session_stats()
        print(f"  Total API calls: {stats['total_calls']}")
        print(f"  Duration: {stats['duration_seconds']:.1f}s")

        client.close()
        print()
        print("✓ Test completed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
