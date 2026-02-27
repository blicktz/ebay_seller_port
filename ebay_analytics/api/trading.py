"""
eBay Trading API client.

Handles XML-based Trading API for retrieving active listings via GetSellerList.
This is the official eBay-recommended API for retrieving all active listings.
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from datetime import datetime
from .base import BaseAPIClient
from ..config import Config


class TradingAPIClient(BaseAPIClient):
    """Client for eBay Trading API (XML-based)."""

    BASE_URL = "https://api.ebay.com/ws/api.dll"
    API_VERSION = "1355"  # Current stable version

    def __init__(self, config: Config):
        """
        Initialize Trading API client.

        Args:
            config: Configuration object
        """
        super().__init__(config)
        self.marketplace_id = config.ebay_marketplace_id

    def _build_xml_request(self, call_name: str, request_body: str) -> str:
        """
        Build XML request for Trading API.

        Args:
            call_name: API call name (e.g., 'GetSellerList')
            request_body: Inner XML content for the request

        Returns:
            Complete XML request string
        """
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<{call_name}Request xmlns="urn:ebay:apis:eBLBaseComponents">
    <ErrorLanguage>en_US</ErrorLanguage>
    <WarningLevel>High</WarningLevel>
    {request_body}
</{call_name}Request>"""
        return xml

    def _parse_xml_response(self, xml_string: str) -> ET.Element:
        """
        Parse XML response from Trading API.

        Args:
            xml_string: XML response string

        Returns:
            Root element of parsed XML

        Raises:
            ValueError: If XML parsing fails
        """
        try:
            root = ET.fromstring(xml_string)
            return root
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse XML response: {e}")

    def _check_response_errors(self, root: ET.Element) -> None:
        """
        Check for errors in Trading API response.

        Args:
            root: Root element of parsed XML response

        Raises:
            APIError: If response contains errors
        """
        # Define namespace
        ns = {'ebay': 'urn:ebay:apis:eBLBaseComponents'}

        # Check Ack status
        ack = root.find('ebay:Ack', ns)
        if ack is not None and ack.text in ['Failure', 'PartialFailure']:
            # Extract error message
            errors = root.findall('ebay:Errors', ns)
            if errors:
                error_messages = []
                for error in errors:
                    short_msg = error.find('ebay:ShortMessage', ns)
                    long_msg = error.find('ebay:LongMessage', ns)
                    error_code = error.find('ebay:ErrorCode', ns)

                    msg = long_msg.text if long_msg is not None else (short_msg.text if short_msg is not None else 'Unknown error')
                    code = error_code.text if error_code is not None else 'Unknown'
                    error_messages.append(f"[{code}] {msg}")

                from .base import APIError
                raise APIError("; ".join(error_messages))

    def get_seller_list(
        self,
        start_time_from: Optional[str] = None,
        start_time_to: Optional[str] = None,
        end_time_from: Optional[str] = None,
        end_time_to: Optional[str] = None,
        page_number: int = 1,
        entries_per_page: int = 200,
        detail_level: str = "ReturnAll"
    ) -> Dict[str, Any]:
        """
        Get seller's active listings using GetSellerList.

        Args:
            start_time_from: Optional start time from filter (ISO 8601 format)
            start_time_to: Optional start time to filter (ISO 8601 format)
            end_time_from: Optional end time from filter (ISO 8601 format)
            end_time_to: Optional end time to filter (ISO 8601 format)
            page_number: Page number for pagination (starts at 1)
            entries_per_page: Items per page (1-200, default 200)
            detail_level: Detail level (default: ReturnAll)

        Returns:
            Dictionary with parsed response data including:
            {
                'items': [...],
                'page_number': 1,
                'total_pages': 5,
                'total_items': 950,
                'has_more_pages': True
            }

        Note:
            With DetailLevel=ReturnAll, maximum is 200 items per page.
            Call repeatedly with page_number to get all items.
            Use EndTimeFrom/EndTimeTo to get all active listings regardless of start date.
        """
        # Build pagination section
        pagination = f"""
    <Pagination>
        <EntriesPerPage>{entries_per_page}</EntriesPerPage>
        <PageNumber>{page_number}</PageNumber>
    </Pagination>"""

        # Build time filter if provided
        time_filter = ""
        if start_time_from:
            time_filter += f"<StartTimeFrom>{start_time_from}</StartTimeFrom>"
        if start_time_to:
            time_filter += f"<StartTimeTo>{start_time_to}</StartTimeTo>"
        if end_time_from:
            time_filter += f"<EndTimeFrom>{end_time_from}</EndTimeFrom>"
        if end_time_to:
            time_filter += f"<EndTimeTo>{end_time_to}</EndTimeTo>"

        # Build request body
        request_body = f"""
    <DetailLevel>{detail_level}</DetailLevel>
    {pagination}
    {time_filter}
    <GranularityLevel>Fine</GranularityLevel>"""

        xml_request = self._build_xml_request('GetSellerList', request_body)

        # Prepare headers
        headers = {
            'X-EBAY-API-SITEID': '0',  # 0 = US
            'X-EBAY-API-COMPATIBILITY-LEVEL': self.API_VERSION,
            'X-EBAY-API-CALL-NAME': 'GetSellerList',
            'X-EBAY-API-IAF-TOKEN': self.config.ebay_access_token,  # OAuth token
            'Content-Type': 'text/xml',
        }

        # Make request
        print(f"  Fetching page {page_number} (up to {entries_per_page} items)...")

        response = self.session.post(
            self.BASE_URL,
            data=xml_request.encode('utf-8'),
            headers=headers,
            timeout=self.config.api_timeout
        )

        # Parse response
        root = self._parse_xml_response(response.text)

        # Check for errors
        self._check_response_errors(root)

        # Parse response data
        return self._parse_seller_list_response(root)

    def _parse_seller_list_response(self, root: ET.Element) -> Dict[str, Any]:
        """
        Parse GetSellerList XML response.

        Args:
            root: Root element of XML response

        Returns:
            Dictionary with items and pagination info
        """
        ns = {'ebay': 'urn:ebay:apis:eBLBaseComponents'}

        # Parse pagination info
        pagination_result = root.find('ebay:PaginationResult', ns)
        total_pages = 1
        total_items = 0

        if pagination_result is not None:
            total_pages_elem = pagination_result.find('ebay:TotalNumberOfPages', ns)
            total_items_elem = pagination_result.find('ebay:TotalNumberOfEntries', ns)

            if total_pages_elem is not None:
                total_pages = int(total_pages_elem.text)
            if total_items_elem is not None:
                total_items = int(total_items_elem.text)

        # Get current page number
        page_number_elem = root.find('ebay:PageNumber', ns)
        page_number = int(page_number_elem.text) if page_number_elem is not None else 1

        # Parse items
        items = []
        item_array = root.find('ebay:ItemArray', ns)

        if item_array is not None:
            for item_elem in item_array.findall('ebay:Item', ns):
                item_data = self._parse_item(item_elem, ns)
                items.append(item_data)

        return {
            'items': items,
            'page_number': page_number,
            'total_pages': total_pages,
            'total_items': total_items,
            'has_more_pages': page_number < total_pages,
            'items_returned': len(items)
        }

    def _parse_item(self, item_elem: ET.Element, ns: Dict[str, str]) -> Dict[str, Any]:
        """
        Parse individual Item element from GetSellerList response.

        Args:
            item_elem: Item XML element
            ns: XML namespace dict

        Returns:
            Dictionary with item data
        """
        def get_text(elem, path):
            """Helper to safely get text from XML element."""
            found = elem.find(path, ns)
            return found.text if found is not None else None

        def get_decimal(elem, path):
            """Helper to safely get decimal value."""
            text = get_text(elem, path)
            try:
                return float(text) if text else None
            except (ValueError, TypeError):
                return None

        def get_int(elem, path):
            """Helper to safely get integer value."""
            text = get_text(elem, path)
            try:
                return int(text) if text else None
            except (ValueError, TypeError):
                return None

        # Extract core fields
        item_id = get_text(item_elem, 'ebay:ItemID')
        title = get_text(item_elem, 'ebay:Title')
        sku = get_text(item_elem, 'ebay:SKU')

        # Pricing
        current_price = get_decimal(item_elem, 'ebay:SellingStatus/ebay:CurrentPrice')
        start_price = get_decimal(item_elem, 'ebay:StartPrice')
        buy_it_now_price = get_decimal(item_elem, 'ebay:BuyItNowPrice')

        # Category
        primary_category = item_elem.find('ebay:PrimaryCategory', ns)
        category_name = None
        category_id = None
        if primary_category is not None:
            category_name = get_text(primary_category, 'ebay:CategoryName')
            category_id = get_text(primary_category, 'ebay:CategoryID')

        # Quantity
        quantity = get_int(item_elem, 'ebay:Quantity')
        quantity_sold = get_int(item_elem, 'ebay:SellingStatus/ebay:QuantitySold')
        quantity_available = get_int(item_elem, 'ebay:QuantityAvailable')

        # If quantity_available not directly available, calculate it
        if quantity_available is None and quantity is not None and quantity_sold is not None:
            quantity_available = max(0, quantity - quantity_sold)

        # Dates
        start_time = get_text(item_elem, 'ebay:ListingDetails/ebay:StartTime')
        end_time = get_text(item_elem, 'ebay:ListingDetails/ebay:EndTime')

        # Convert start time to YYYY-MM-DD format
        start_date = None
        if start_time:
            try:
                dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                start_date = dt.strftime('%Y-%m-%d')
            except (ValueError, AttributeError):
                start_date = start_time[:10] if len(start_time) >= 10 else None

        # Listing status
        listing_status = get_text(item_elem, 'ebay:SellingStatus/ebay:ListingStatus')

        # Promoted status (not available in Trading API, would need Promoted Listings API)
        promoted_status = 'Unknown'

        return {
            'item_id': item_id,
            'title': title,
            'sku': sku,
            'current_price': current_price,
            'start_price': start_price,
            'buy_it_now_price': buy_it_now_price,
            'category_name': category_name,
            'category_id': category_id,
            'quantity': quantity,
            'quantity_sold': quantity_sold,
            'quantity_available': quantity_available,
            'start_time': start_time,
            'start_date': start_date,
            'end_time': end_time,
            'listing_status': listing_status,
            'promoted_status': promoted_status,
            'last_known_status': 'active'  # All items from GetSellerList are active
        }

    def get_all_active_listings(self) -> List[Dict[str, Any]]:
        """
        Get all active listings with automatic pagination.

        Returns:
            List of all active listing dictionaries

        Note:
            Automatically handles pagination (200 items per page).
            For 500+ items, this will make 3+ API calls.
            Uses StartTimeFrom/StartTimeTo (120-day window) to capture all listings
            started in the last 120 days, including both active and ended/sold listings.
        """
        from datetime import datetime, timedelta, timezone

        all_items = []
        seen_item_ids = set()  # Track unique items across time windows

        # Use a 120-day window (API limit is 121 days)
        # Captures all listings started in the last 120 days
        # (includes both active and ended/sold listings)
        now = datetime.now(timezone.utc)
        start_time_from = (now - timedelta(days=120)).isoformat()
        start_time_to = now.isoformat()

        print(f"📦 Fetching all listings from Trading API...")
        print(f"   Using StartTime filter: listings started in last 120 days")
        print(f"   Time window: {start_time_from[:10]} to {start_time_to[:10]}")

        page_number = 1
        while True:
            try:
                response = self.get_seller_list(
                    start_time_from=start_time_from,
                    start_time_to=start_time_to,
                    page_number=page_number,
                    entries_per_page=200,
                    detail_level="ReturnAll"
                )

                items = response.get('items', [])

                # Add only unique items
                for item in items:
                    item_id = item.get('item_id')
                    if item_id and item_id not in seen_item_ids:
                        all_items.append(item)
                        seen_item_ids.add(item_id)

                total_items = response.get('total_items', 0)
                total_pages = response.get('total_pages', 1)

                print(f"    Page {page_number}/{total_pages}: Retrieved {len(items)} items (unique: {len(all_items)})")

                if not response.get('has_more_pages', False):
                    break

                page_number += 1

            except Exception as e:
                print(f"    ✗ Error fetching page {page_number}: {e}")
                break

        print(f"    ✓ Total listings retrieved: {len(all_items)}")
        return all_items

    def extract_metadata_from_listings(
        self,
        listings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract metadata suitable for listings_metadata table.

        Args:
            listings: List of listings from get_all_active_listings()

        Returns:
            List of metadata dictionaries matching database schema
        """
        metadata_list = []

        for listing in listings:
            metadata_list.append({
                'item_id': listing.get('item_id'),
                'title': listing.get('title'),
                'category_name': listing.get('category_name'),
                'start_date': listing.get('start_date'),
                'quantity_available': listing.get('quantity_available', 0),
                'promoted_status': listing.get('promoted_status', 'Unknown'),
                'last_known_status': listing.get('last_known_status', 'active'),
                'current_price': listing.get('current_price'),
                'start_price': listing.get('start_price'),
                'buy_it_now_price': listing.get('buy_it_now_price')
            })

        return metadata_list

    def get_active_listings_metadata(self) -> List[Dict[str, Any]]:
        """
        Get active listings metadata (convenience method).

        Combines get_all_active_listings() and extract_metadata_from_listings().

        Returns:
            List of metadata dictionaries ready for database storage
        """
        listings = self.get_all_active_listings()
        metadata = self.extract_metadata_from_listings(listings)

        print(f"   ✓ Extracted metadata for {len(metadata)} active listings")

        return metadata


if __name__ == "__main__":
    # Test Trading API client
    from ..config import load_config

    print("Testing TradingAPIClient...\n")

    try:
        config = load_config()
        client = TradingAPIClient(config)

        print(f"✓ Trading API client initialized")
        print(f"  Base URL: {client.BASE_URL}")
        print(f"  API Version: {client.API_VERSION}")
        print(f"  Marketplace: {client.marketplace_id}")

        # Note: Actual API calls require valid token and will hit real API
        # Uncomment below to test with real API (uses your quota)

        # print("\nFetching first page of active listings...")
        # result = client.get_seller_list(page_number=1, entries_per_page=10)
        # print(f"Total items: {result['total_items']}")
        # print(f"Items on this page: {len(result['items'])}")
        # if result['items']:
        #     print(f"Sample item: {result['items'][0]['title']}")

        client.close()
        print(f"\n✓ Client closed successfully")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
