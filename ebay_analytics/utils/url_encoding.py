"""
URL encoding utilities for eBay Analytics API filters.

The Analytics API requires specific URL encoding for filter parameters,
especially for the listing_ids filter syntax.
"""

from typing import List
from urllib.parse import quote


def encode_listing_ids_filter(item_ids: List[str]) -> str:
    """
    Encode listing IDs for Analytics API filter parameter.

    The listing_ids filter syntax is: listing_ids:{id1|id2|id3}
    This must be URL-encoded to: listing_ids:%7Bid1%7Cid2%7Cid3%7D

    Args:
        item_ids: List of eBay item IDs

    Returns:
        URL-encoded listing_ids filter string

    Example:
        >>> encode_listing_ids_filter(['123', '456', '789'])
        'listing_ids:%7B123%7C456%7C789%7D'
    """
    if not item_ids:
        return ""

    # Join IDs with pipe separator
    ids_str = "|".join(str(item_id) for item_id in item_ids)

    # Format as listing_ids:{...}
    raw_filter = f"listing_ids:{{{ids_str}}}"

    # URL encode (only encode special characters, not alphanumerics)
    # { becomes %7B, } becomes %7D, | becomes %7C
    encoded = quote(raw_filter, safe='')

    return encoded


def encode_marketplace_filter(marketplace_id: str) -> str:
    """
    Encode marketplace ID for Analytics API filter parameter.

    Args:
        marketplace_id: eBay marketplace ID (e.g., 'EBAY_US')

    Returns:
        URL-encoded marketplace_ids filter string

    Example:
        >>> encode_marketplace_filter('EBAY_US')
        'marketplace_ids:%7BEBAY_US%7D'
    """
    raw_filter = f"marketplace_ids:{{{marketplace_id}}}"
    return quote(raw_filter, safe='')


def encode_date_range_filter(start_date: str, end_date: str) -> str:
    """
    Encode date range for Analytics API filter parameter.

    Args:
        start_date: Start date in YYYYMMDD format
        end_date: End date in YYYYMMDD format

    Returns:
        URL-encoded date_range filter string

    Example:
        >>> encode_date_range_filter('20260201', '20260225')
        'date_range:%5B20260201..20260225%5D'
    """
    raw_filter = f"date_range:[{start_date}..{end_date}]"
    return quote(raw_filter, safe='')


def build_analytics_filter(
    marketplace_id: str,
    start_date: str,
    end_date: str,
    listing_ids: List[str] = None
) -> str:
    """
    Build complete filter string for Analytics API.

    Combines multiple filter parameters into a single comma-separated string.

    Note: traffic_source is NOT a valid filter field in the Analytics API.
    Valid filters are: marketplace_ids, date_range, and listing_ids only.

    Args:
        marketplace_id: eBay marketplace ID (e.g., 'EBAY_US')
        start_date: Start date in YYYYMMDD format
        end_date: End date in YYYYMMDD format
        listing_ids: Optional list of item IDs to filter

    Returns:
        Complete URL-encoded filter string

    Example:
        >>> build_analytics_filter('EBAY_US', '20260201', '20260225', ['123', '456'])
        'marketplace_ids:%7BEBAY_US%7D,date_range:%5B20260201..20260225%5D,listing_ids:%7B123%7C456%7D'
    """
    filters = []

    # Marketplace (required)
    filters.append(encode_marketplace_filter(marketplace_id))

    # Date range (required)
    filters.append(encode_date_range_filter(start_date, end_date))

    # Listing IDs (optional)
    if listing_ids:
        filters.append(encode_listing_ids_filter(listing_ids))

    return ",".join(filters)


def build_fulfillment_filter(start_datetime: str, end_datetime: str) -> str:
    """
    Build filter string for Fulfillment API.

    Args:
        start_datetime: Start datetime in ISO 8601 format
        end_datetime: End datetime in ISO 8601 format

    Returns:
        Filter string for creationdate

    Example:
        >>> build_fulfillment_filter(
        ...     '2026-02-01T00:00:00.000Z',
        ...     '2026-02-25T23:59:59.999Z'
        ... )
        'creationdate:[2026-02-01T00:00:00.000Z..2026-02-25T23:59:59.999Z]'
    """
    return f"creationdate:[{start_datetime}..{end_datetime}]"


if __name__ == "__main__":
    # Test URL encoding functions
    print("Testing URL encoding utilities...\\n")

    # Test listing IDs encoding
    item_ids = ['198115000001', '198115000002', '198115000003']
    encoded = encode_listing_ids_filter(item_ids)
    print(f"Listing IDs filter:")
    print(f"  Input: {item_ids}")
    print(f"  Encoded: {encoded}")
    print()

    # Test marketplace encoding
    marketplace = encode_marketplace_filter('EBAY_US')
    print(f"Marketplace filter:")
    print(f"  Encoded: {marketplace}")
    print()

    # Test date range encoding
    date_range = encode_date_range_filter('20260201', '20260225')
    print(f"Date range filter:")
    print(f"  Encoded: {date_range}")
    print()

    # Test complete filter building
    complete_filter = build_analytics_filter(
        marketplace_id='EBAY_US',
        start_date='20260201',
        end_date='20260225',
        listing_ids=['198115000001', '198115000002']
    )
    print(f"Complete Analytics filter:")
    print(f"  {complete_filter}")
    print()

    # Test fulfillment filter
    fulfillment_filter = build_fulfillment_filter(
        '2026-02-01T00:00:00.000Z',
        '2026-02-25T23:59:59.999Z'
    )
    print(f"Fulfillment filter:")
    print(f"  {fulfillment_filter}")
    print()

    print("✓ All tests passed")
