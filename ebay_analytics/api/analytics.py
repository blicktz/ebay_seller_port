"""
eBay Sell Analytics API client.

Handles traffic_report endpoint with support for:
- LISTING dimension with DAY secondary dimension
- listing_ids filter for querying specific items (especially sold listings)
- traffic_source filter for promoted/organic breakdown
- Pagination for large result sets
"""

from typing import List, Dict, Any, Optional
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
        traffic_source: Optional[str] = None,
        limit: int = 200
    ) -> Dict[str, Any]:
        """
        Get traffic report from Analytics API.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            dimension: Report dimension (default: LISTING)
            metrics: List of metrics to retrieve (optional, API will use defaults)
            listing_ids: Optional list of specific item IDs to query
            traffic_source: Optional traffic source filter ('ORGANIC' or 'PROMOTED_LISTINGS')
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

            # Get organic traffic only
            >>> client.get_traffic_report(
            ...     '20260201', '20260225',
            ...     traffic_source='ORGANIC'
            ... )
        """
        url = f"{self.BASE_URL}/traffic_report"

        # Build filter parameter
        filter_param = build_analytics_filter(
            marketplace_id=self.marketplace_id,
            start_date=start_date,
            end_date=end_date,
            listing_ids=listing_ids,
            traffic_source=traffic_source
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
        if traffic_source:
            print(f"    Traffic source: {traffic_source}")

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
        listing_ids: Optional[List[str]] = None,
        traffic_source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get complete traffic report with automatic pagination.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            dimension: Report dimension (default: LISTING)
            metrics: List of metrics to retrieve
            listing_ids: Optional list of specific item IDs
            traffic_source: Optional traffic source filter

        Returns:
            List of all records from all pages

        Note:
            Analytics API returns max 200 records per request.
            This method handles pagination automatically.
        """
        all_records = []
        offset = 0
        limit = 200

        while True:
            response = self.get_traffic_report(
                start_date=start_date,
                end_date=end_date,
                dimension=dimension,
                metrics=metrics,
                listing_ids=listing_ids,
                traffic_source=traffic_source,
                limit=limit
            )

            records = response.get('records', [])
            if not records:
                break

            all_records.extend(records)

            # Check if there are more pages
            if len(records) < limit:
                break

            offset += limit

        return all_records

    def get_traffic_for_active_listings(
        self,
        start_date: str,
        end_date: str,
        traffic_source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get traffic data for active listings (default behavior).

        When no listing_ids filter is provided, the API returns data for active listings.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            traffic_source: Optional traffic source filter

        Returns:
            List of traffic records for active listings
        """
        print(f"📊 Fetching active listings traffic...")

        metrics = [
            'TOTAL_IMPRESSION_TOTAL',
            'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
            'LISTING_VIEWS_TOTAL',
            'TRANSACTION'
        ]

        return self.get_traffic_report_with_pagination(
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            traffic_source=traffic_source
        )

    def get_traffic_for_sold_listings(
        self,
        start_date: str,
        end_date: str,
        item_ids: List[str],
        traffic_source: Optional[str] = None,
        batch_size: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Get traffic data for sold listings using listing_ids filter.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            item_ids: List of sold item IDs
            traffic_source: Optional traffic source filter
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
            'TRANSACTION'
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
                listing_ids=batch,
                traffic_source=traffic_source
            )

            all_records.extend(records)

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
