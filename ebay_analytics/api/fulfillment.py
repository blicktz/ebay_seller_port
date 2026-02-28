"""
eBay Sell Fulfillment API client.

Handles getOrders endpoint to retrieve sold items from orders.
Used to identify which listings sold in the last N days so their
traffic data can be queried from the Analytics API.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from .base import BaseAPIClient
from ..config import Config
from ..utils.url_encoding import build_fulfillment_filter


class FulfillmentAPIClient(BaseAPIClient):
    """Client for eBay Sell Fulfillment API."""

    BASE_URL = "https://api.ebay.com/sell/fulfillment/v1"

    def __init__(self, config: Config):
        """
        Initialize Fulfillment API client.

        Args:
            config: Configuration object
        """
        super().__init__(config)

    def get_orders(
        self,
        start_datetime: str,
        end_datetime: str,
        limit: int = 200,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get orders from Fulfillment API.

        Args:
            start_datetime: Start datetime in ISO 8601 format (e.g., '2026-02-01T00:00:00.000Z')
            end_datetime: End datetime in ISO 8601 format
            limit: Number of orders per page (default: 200, max: 200)
            offset: Pagination offset (default: 0)

        Returns:
            Dictionary containing orders data with structure:
            {
                'orders': [
                    {
                        'orderId': '20-12345-67890',
                        'creationDate': '2026-02-15T14:32:21.511Z',
                        'lineItems': [
                            {
                                'itemId': '198115000001',
                                'quantity': 2,
                                'title': 'Product name'
                            }
                        ]
                    }
                ],
                'total': 45,
                'limit': 200,
                'offset': 0
            }
        """
        url = f"{self.BASE_URL}/order"

        # Build filter for order creation date range
        filter_param = build_fulfillment_filter(start_datetime, end_datetime)

        params = {
            'filter': filter_param,
            'limit': limit,
            'offset': offset
        }

        return self.get(url, params=params)

    def get_all_orders(
        self,
        start_datetime: str,
        end_datetime: str
    ) -> List[Dict[str, Any]]:
        """
        Get all orders with automatic pagination.

        Args:
            start_datetime: Start datetime in ISO 8601 format
            end_datetime: End datetime in ISO 8601 format

        Returns:
            List of all order dictionaries

        Note:
            Automatically handles pagination (200 orders per request).
        """
        all_orders = []
        offset = 0
        limit = 200

        print(f"  Fetching orders from {start_datetime[:10]} to {end_datetime[:10]}")

        while True:
            try:
                response = self.get_orders(
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    limit=limit,
                    offset=offset
                )

                orders = response.get('orders', [])
                if not orders:
                    break

                all_orders.extend(orders)
                print(f"    Retrieved {len(orders)} orders (total: {len(all_orders)})")

                # Check if there are more pages
                total = response.get('total', 0)
                if len(all_orders) >= total or len(orders) < limit:
                    break

                offset += limit

            except Exception as e:
                print(f"    ✗ Error fetching orders at offset {offset}: {e}")
                break

        print(f"    ✓ Total orders retrieved: {len(all_orders)}")
        return all_orders

    def extract_sold_items(
        self,
        orders: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract sold item information from orders.

        Args:
            orders: List of order dictionaries from get_all_orders()

        Returns:
            List of sold item dictionaries with structure:
            [
                {
                    'item_id': '198115000001',
                    'sold_date': '2026-02-15',
                    'order_id': '20-12345-67890',
                    'quantity': 2,
                    'title': 'Product name'
                }
            ]
        """
        sold_items = []

        for order in orders:
            order_id = order.get('orderId', '')
            creation_date = order.get('creationDate', '')

            # Parse date (ISO 8601 UTC to YYYY-MM-DD in user's timezone)
            try:
                # Parse UTC timestamp
                dt_utc = datetime.fromisoformat(creation_date.replace('Z', '+00:00'))
                # Convert to user's timezone (e.g., PST)
                dt_local = dt_utc.astimezone(ZoneInfo(self.config.user_timezone))
                # Extract date in local timezone
                sold_date = dt_local.strftime('%Y-%m-%d')
            except (ValueError, AttributeError):
                sold_date = creation_date[:10] if len(creation_date) >= 10 else ''

            # Extract items from line items
            line_items = order.get('lineItems', [])
            for line_item in line_items:
                item_id = line_item.get('itemId') or line_item.get('legacyItemId') or ''
                if not item_id:
                    continue

                sold_items.append({
                    'item_id': str(item_id),
                    'sold_date': sold_date,
                    'order_id': order_id,
                    'quantity': line_item.get('quantity', 1),
                    'title': line_item.get('title', '')
                })

        return sold_items

    def get_sold_items_for_date_range(
        self,
        start_datetime: str,
        end_datetime: str
    ) -> List[Dict[str, Any]]:
        """
        Get sold items for a date range (convenience method).

        Combines get_all_orders() and extract_sold_items().

        Args:
            start_datetime: Start datetime in ISO 8601 format
            end_datetime: End datetime in ISO 8601 format

        Returns:
            List of sold item dictionaries
        """
        print(f"📦 Fetching sold items...")

        orders = self.get_all_orders(start_datetime, end_datetime)
        sold_items = self.extract_sold_items(orders)

        # Get unique item IDs
        unique_item_ids = set(item['item_id'] for item in sold_items)

        print(f"   ✓ Found {len(sold_items)} sold items ({len(unique_item_ids)} unique)")

        return sold_items


if __name__ == "__main__":
    # Test Fulfillment API client
    from ..config import load_config, DateRangeParser
    from datetime import timedelta

    print("Testing FulfillmentAPIClient...\n")

    try:
        config = load_config()
        client = FulfillmentAPIClient(config)

        print(f"✓ Fulfillment API client initialized")
        print(f"  Base URL: {client.BASE_URL}")

        # Test date range formatting
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=7)

        start_iso = DateRangeParser.to_iso8601_with_time(start_dt)
        end_iso = DateRangeParser.to_iso8601_with_time(end_dt)

        print(f"\nTest date range:")
        print(f"  Start: {start_iso}")
        print(f"  End: {end_iso}")

        # Note: Actual API calls require valid token and will hit real API
        # Uncomment below to test with real API (uses your quota)

        # print("\nFetching sold items for last 7 days...")
        # sold_items = client.get_sold_items_for_date_range(start_iso, end_iso)
        # print(f"Results: {len(sold_items)} sold items")
        # if sold_items:
        #     print(f"Sample: {sold_items[0]}")

        client.close()
        print(f"\n✓ Client closed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
