"""
eBay Sell Inventory API client.

Handles inventory_item endpoint to retrieve listing metadata
including title, category, quantity available, and listing status.
"""

from typing import List, Dict, Any, Optional
from .base import BaseAPIClient
from ..config import Config


class InventoryAPIClient(BaseAPIClient):
    """Client for eBay Sell Inventory API."""

    BASE_URL = "https://api.ebay.com/sell/inventory/v1"

    def __init__(self, config: Config):
        """
        Initialize Inventory API client.

        Args:
            config: Configuration object
        """
        super().__init__(config)

    def get_inventory_items(
        self,
        limit: int = 200,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get inventory items.

        Args:
            limit: Number of items per page (default: 200, max: 200)
            offset: Pagination offset (default: 0)

        Returns:
            Dictionary containing inventory items with structure:
            {
                'inventoryItems': [
                    {
                        'sku': 'SKU-123',
                        'product': {
                            'title': 'Product name',
                            'aspects': {...}
                        },
                        'availability': {
                            'shipToLocationAvailability': {
                                'quantity': 50
                            }
                        }
                    }
                ],
                'total': 100,
                'size': 200,
                'offset': 0
            }
        """
        url = f"{self.BASE_URL}/inventory_item"

        params = {
            'limit': limit,
            'offset': offset
        }

        return self.get(url, params=params)

    def get_all_inventory_items(self) -> List[Dict[str, Any]]:
        """
        Get all inventory items with automatic pagination.

        Returns:
            List of all inventory item dictionaries

        Note:
            Automatically handles pagination (200 items per request).
        """
        all_items = []
        offset = 0
        limit = 200

        print(f"  Fetching inventory items...")

        while True:
            try:
                response = self.get_inventory_items(limit=limit, offset=offset)

                items = response.get('inventoryItems', [])
                if not items:
                    break

                all_items.extend(items)
                print(f"    Retrieved {len(items)} items (total: {len(all_items)})")

                # Check if there are more pages
                total = response.get('total', 0)
                if len(all_items) >= total or len(items) < limit:
                    break

                offset += limit

            except Exception as e:
                print(f"    ✗ Error fetching inventory at offset {offset}: {e}")
                break

        print(f"    ✓ Total inventory items retrieved: {len(all_items)}")
        return all_items

    def get_inventory_item_by_sku(self, sku: str) -> Dict[str, Any]:
        """
        Get a specific inventory item by SKU.

        Args:
            sku: Item SKU

        Returns:
            Inventory item dictionary
        """
        url = f"{self.BASE_URL}/inventory_item/{sku}"
        return self.get(url)

    def extract_metadata_from_inventory(
        self,
        inventory_items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract listing metadata from inventory items.

        Args:
            inventory_items: List of inventory items from get_all_inventory_items()

        Returns:
            List of metadata dictionaries with structure:
            [
                {
                    'item_id': 'SKU-123',
                    'title': 'Product name',
                    'category_name': 'Category',
                    'quantity_available': 50,
                    'promoted_status': 'Not Promoted',
                    'last_known_status': 'active'
                }
            ]

        Note:
            The Inventory API uses SKU as the primary identifier, but for
            active listings, we'll need to map these to eBay item IDs separately.
        """
        metadata_list = []

        for item in inventory_items:
            sku = item.get('sku', '')

            # Extract product info
            product = item.get('product', {})
            title = product.get('title', '')

            # Extract quantity
            availability = item.get('availability', {})
            ship_availability = availability.get('shipToLocationAvailability', {})
            quantity = ship_availability.get('quantity', 0)

            # Note: Category and item ID require additional API calls or offer data
            # For now, we'll extract what's available from inventory_item endpoint

            metadata_list.append({
                'item_id': sku,  # Will need to map to eBay item ID
                'title': title,
                'category_name': None,  # Not available from this endpoint
                'quantity_available': quantity,
                'promoted_status': 'Unknown',  # Would need Promoted Listings API
                'last_known_status': 'active'
            })

        return metadata_list

    def get_inventory_metadata(self) -> List[Dict[str, Any]]:
        """
        Get inventory metadata (convenience method).

        Combines get_all_inventory_items() and extract_metadata_from_inventory().

        Returns:
            List of metadata dictionaries
        """
        print(f"📦 Fetching inventory metadata...")

        items = self.get_all_inventory_items()
        metadata = self.extract_metadata_from_inventory(items)

        print(f"   ✓ Extracted metadata for {len(metadata)} items")

        return metadata


if __name__ == "__main__":
    # Test Inventory API client
    from ..config import load_config

    print("Testing InventoryAPIClient...\n")

    try:
        config = load_config()
        client = InventoryAPIClient(config)

        print(f"✓ Inventory API client initialized")
        print(f"  Base URL: {client.BASE_URL}")

        # Note: Actual API calls require valid token and will hit real API
        # Uncomment below to test with real API (uses your quota)

        # print("\nFetching inventory metadata...")
        # metadata = client.get_inventory_metadata()
        # print(f"Results: {len(metadata)} items")
        # if metadata:
        #     print(f"Sample: {metadata[0]}")

        client.close()
        print(f"\n✓ Client closed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
