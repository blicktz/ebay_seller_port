"""
eBay Sell Analytics API client.

Handles traffic_report endpoint with support for:
- LISTING dimension with DAY secondary dimension
- listing_ids filter for querying specific items (especially sold listings)
- traffic_source filter for promoted/organic breakdown
- Pagination for large result sets
"""

from typing import List, Dict, Any, Optional
import time
from .base import BaseAPIClient
from ..config import Config
from ..utils.url_encoding import build_analytics_filter


class AnalyticsAPIClient(BaseAPIClient):
    """Client for eBay Sell Analytics API."""

    BASE_URL = "https://api.ebay.com/sell/analytics/v1"

    def __init__(self, config: Config):
        """
        Initialize Analytics API client.

        Args:
            config: Configuration object
        """
        super().__init__(config)
        self.marketplace_id = config.ebay_marketplace_id

    def get_traffic_report(
        self,
        start_date: str,
        end_date: str,
        dimension: str = "LISTING",
        metrics: Optional[List[str]] = None,
        listing_ids: Optional[List[str]] = None,
        limit: int = 200
    ) -> Dict[str, Any]:
        """
        Get traffic report from Analytics API.

        Note: traffic_source is NOT supported as a filter field.
        The Analytics API only supports: marketplace_ids, date_range, and listing_ids.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            dimension: Report dimension (default: LISTING)
            metrics: List of metrics to retrieve (optional, API will use defaults)
            listing_ids: Optional list of specific item IDs to query
            limit: Maximum records per page (default: 200)

        Returns:
            Dictionary containing traffic report data

        Example:
            # Get traffic for all active listings
            >>> client.get_traffic_report('20260201', '20260225')

            # Get traffic for specific sold items
            >>> client.get_traffic_report(
            ...     '20260201', '20260225',
            ...     listing_ids=['123', '456', '789']
            ... )
        """
        url = f"{self.BASE_URL}/traffic_report"

        # Build filter parameter
        filter_param = build_analytics_filter(
            marketplace_id=self.marketplace_id,
            start_date=start_date,
            end_date=end_date,
            listing_ids=listing_ids
        )

        # Build query parameters
        params = {
            'dimension': dimension,
            'filter': filter_param,
        }

        # Add metrics if specified
        if metrics:
            params['metric'] = ','.join(metrics)

        # Add marketplace header
        headers = {
            'X-EBAY-C-MARKETPLACE-ID': self.marketplace_id
        }

        print(f"  Fetching traffic report: {start_date} to {end_date}")
        if listing_ids:
            print(f"    Listing IDs: {len(listing_ids)} items")

        try:
            response = self.get(url, params=params, headers=headers)

            # Log results
            if 'records' in response:
                print(f"    ✓ Retrieved {len(response['records'])} records")

            return response

        except Exception as e:
            print(f"    ✗ Error: {e}")
            raise

    def get_traffic_report_with_pagination(
        self,
        start_date: str,
        end_date: str,
        dimension: str = "LISTING",
        metrics: Optional[List[str]] = None,
        listing_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get traffic report (Analytics API does not support pagination).

        Note: traffic_source filter is NOT supported by the Analytics API.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            dimension: Report dimension (default: LISTING)
            metrics: List of metrics to retrieve
            listing_ids: Optional list of specific item IDs

        Returns:
            List of all records from the API response

        Note:
            The Analytics API returns all available records in a single response.
            There is no pagination support (no next/href links or offset parameter).
            The API may have internal limits on the number of records returned.
        """
        response = self.get_traffic_report(
            start_date=start_date,
            end_date=end_date,
            dimension=dimension,
            metrics=metrics,
            listing_ids=listing_ids,
            limit=200
        )

        return response.get('records', [])

    def get_traffic_for_active_listings(
        self,
        start_date: str,
        end_date: str,
        item_ids: List[str],
        batch_size: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Get traffic data for active listings using listing_ids filter.

        Note: Without listing_ids filter, API only returns max 200 listings.
        With listing_ids filter, we can retrieve all active listings by batching.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            item_ids: List of active item IDs
            batch_size: Number of items per batch (max 200)

        Returns:
            List of traffic records for active listings

        Note:
            Automatically batches requests if item_ids > 200.
        """
        if not item_ids:
            return []

        print(f"📊 Fetching active listings traffic...")
        print(f"   Total active items: {len(item_ids)}")

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

        all_records = []

        # Batch items by batch_size (max 200 per API request)
        for i in range(0, len(item_ids), batch_size):
            batch = item_ids[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(item_ids) + batch_size - 1) // batch_size

            print(f"   Batch {batch_num}/{total_batches}: {len(batch)} items")

            records = self.get_traffic_report_with_pagination(
                start_date=start_date,
                end_date=end_date,
                metrics=metrics,
                listing_ids=batch
            )

            all_records.extend(records)

            # Add delay between batches to avoid rate limiting (except after last batch)
            if batch_num < total_batches:
                delay = 3.0
                print(f"   ⏱  Waiting {delay}s before next batch...")
                time.sleep(delay)

        print(f"   ✓ Total records retrieved: {len(all_records)}")
        return all_records

    def get_traffic_for_sold_listings(
        self,
        start_date: str,
        end_date: str,
        item_ids: List[str],
        batch_size: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Get traffic data for sold listings using listing_ids filter.

        Note: traffic_source filter is NOT supported by the Analytics API.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            item_ids: List of sold item IDs
            batch_size: Number of items per batch (max 200)

        Returns:
            List of traffic records for sold listings

        Note:
            Automatically batches requests if item_ids > 200.
        """
        if not item_ids:
            return []

        print(f"📊 Fetching sold listings traffic...")
        print(f"   Total sold items: {len(item_ids)}")

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

        all_records = []

        # Batch items by batch_size (max 200 per API request)
        for i in range(0, len(item_ids), batch_size):
            batch = item_ids[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(item_ids) + batch_size - 1) // batch_size

            print(f"   Batch {batch_num}/{total_batches}: {len(batch)} items")

            records = self.get_traffic_report_with_pagination(
                start_date=start_date,
                end_date=end_date,
                metrics=metrics,
                listing_ids=batch
            )

            all_records.extend(records)

            # Add delay between batches to avoid rate limiting (except after last batch)
            if batch_num < total_batches:
                delay = 3.0
                print(f"   ⏱  Waiting {delay}s before next batch...")
                time.sleep(delay)

        print(f"   ✓ Total records retrieved: {len(all_records)}")
        return all_records


if __name__ == "__main__":
    # Test Analytics API client
    from ..config import load_config

    print("Testing AnalyticsAPIClient...\n")

    try:
        config = load_config()
        client = AnalyticsAPIClient(config)

        print(f"✓ Analytics API client initialized")
        print(f"  Base URL: {client.BASE_URL}")
        print(f"  Marketplace: {client.marketplace_id}")

        # Note: Actual API calls require valid token and will hit real API
        # Uncomment below to test with real API (uses your quota)

        # from ..config import DateRangeParser
        # start, end = DateRangeParser.get_date_range_last_n_days(7)
        # print(f"\nTesting traffic report for last 7 days: {start} to {end}")
        # result = client.get_traffic_report(start, end)
        # print(f"Records: {len(result.get('records', []))}")

        client.close()
        print(f"\n✓ Client closed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
