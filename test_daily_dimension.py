#!/usr/bin/env python3
"""
Test script to verify eBay Analytics API DAY dimension behavior.

This script tests whether adding dimension=DAY returns day-by-day data
instead of aggregated totals across the date range.

Usage:
    poetry run python test_daily_dimension.py
"""

import sys
import json
from datetime import datetime, timedelta

# Import our existing modules
from ebay_analytics.config import load_config
from ebay_analytics.api.analytics import AnalyticsAPIClient
from ebay_analytics.db.repository import MetadataRepository


def test_day_dimension():
    """Test Analytics API with DAY secondary dimension."""

    print("=" * 80)
    print("TESTING eBay Analytics API - DAY DIMENSION")
    print("=" * 80)
    print()

    # Load config
    try:
        config = load_config()
        print("✓ Configuration loaded")
    except Exception as e:
        print(f"✗ Failed to load config: {e}")
        return False

    # Get a few active listing IDs for testing
    try:
        metadata_repo = MetadataRepository(config.db_path)
        all_active_ids = metadata_repo.get_active_listing_ids()

        # Use only first 5 items for testing
        test_item_ids = all_active_ids[:5]

        print(f"✓ Retrieved {len(test_item_ids)} test listing IDs")
        print(f"  Test IDs: {test_item_ids[:3]}...")
        print()
    except Exception as e:
        print(f"✗ Failed to get listing IDs: {e}")
        return False

    # Calculate 3-day date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=2)  # 3 days total

    start_date_str = start_date.strftime('%Y%m%d')
    end_date_str = end_date.strftime('%Y%m%d')

    print(f"Test date range: {start_date_str} to {end_date_str} (3 days)")
    print()

    # Initialize API client
    try:
        api_client = AnalyticsAPIClient(config)
        print("✓ Analytics API client initialized")
        print()
    except Exception as e:
        print(f"✗ Failed to initialize API client: {e}")
        return False

    # ========================================================================
    # TEST 1: Current behavior (dimension=LISTING only)
    # ========================================================================
    print("-" * 80)
    print("TEST 1: Current Implementation (dimension=LISTING)")
    print("-" * 80)
    print()

    try:
        print("Making API call with dimension=LISTING...")

        metrics = [
            'TOTAL_IMPRESSION_TOTAL',
            'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
            'LISTING_VIEWS_TOTAL',
            'TRANSACTION'
        ]

        response1 = api_client.get_traffic_report(
            start_date=start_date_str,
            end_date=end_date_str,
            dimension="LISTING",
            metrics=metrics,
            listing_ids=test_item_ids,
            limit=200
        )

        records1 = response1.get('records', [])

        print(f"✓ API call successful")
        print(f"  Total records returned: {len(records1)}")
        print()

        if records1:
            print("Sample record structure:")
            print(json.dumps(records1[0], indent=2))
            print()

            # Count unique items
            unique_items = set()
            for record in records1:
                dimension_values = record.get('dimensionValues', [])
                if dimension_values:
                    item_id = dimension_values[0].get('value')
                    unique_items.add(item_id)

            print(f"Analysis:")
            print(f"  Unique items: {len(unique_items)}")
            print(f"  Records per item (avg): {len(records1) / len(unique_items):.1f}")
            print(f"  Expected for 3 days: 3 records per item")

            if len(records1) / len(unique_items) < 2:
                print(f"  ⚠️  APPEARS TO BE AGGREGATED (1 record per item)")
            else:
                print(f"  ✓ APPEARS TO HAVE DAILY BREAKDOWN")
        else:
            print("⚠️  No records returned")

        print()

    except Exception as e:
        print(f"✗ Test 1 failed: {e}")
        import traceback
        traceback.print_exc()
        print()

    # ========================================================================
    # TEST 2: With DAY dimension (dimension=LISTING,DAY)
    # ========================================================================
    print("-" * 80)
    print("TEST 2: With DAY Dimension (dimension=LISTING,DAY)")
    print("-" * 80)
    print()

    try:
        print("Making API call with dimension=LISTING,DAY...")

        # Manually construct the request with DAY dimension
        from ebay_analytics.utils.url_encoding import build_analytics_filter

        url = f"{api_client.BASE_URL}/traffic_report"

        filter_param = build_analytics_filter(
            marketplace_id=config.ebay_marketplace_id,
            start_date=start_date_str,
            end_date=end_date_str,
            listing_ids=test_item_ids
        )

        metrics = [
            'TOTAL_IMPRESSION_TOTAL',
            'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
            'LISTING_VIEWS_TOTAL',
            'TRANSACTION'
        ]

        params = {
            'dimension': 'LISTING,DAY',  # <-- KEY CHANGE
            'filter': filter_param,
            'metric': ','.join(metrics)
        }

        headers = {
            'X-EBAY-C-MARKETPLACE-ID': config.ebay_marketplace_id
        }

        print(f"  Request params: {params}")
        print()

        response2 = api_client.get(url, params=params, headers=headers)
        records2 = response2.get('records', [])

        print(f"✓ API call successful")
        print(f"  Total records returned: {len(records2)}")
        print()

        if records2:
            print("Sample record structure:")
            print(json.dumps(records2[0], indent=2))
            print()

            # Analyze dimensionValues structure
            sample_dims = records2[0].get('dimensionValues', [])
            print(f"DimensionValues structure:")
            print(f"  Number of dimensions: {len(sample_dims)}")
            if len(sample_dims) >= 1:
                print(f"  Dimension [0]: {sample_dims[0]}")
            if len(sample_dims) >= 2:
                print(f"  Dimension [1]: {sample_dims[1]}")
            print()

            # Count unique items and dates
            item_date_pairs = set()
            unique_items = set()
            unique_dates = set()

            for record in records2:
                dimension_values = record.get('dimensionValues', [])
                if len(dimension_values) >= 1:
                    item_id = dimension_values[0].get('value')
                    unique_items.add(item_id)

                    if len(dimension_values) >= 2:
                        date_val = dimension_values[1].get('value')
                        unique_dates.add(date_val)
                        item_date_pairs.add((item_id, date_val))

            print(f"Analysis:")
            print(f"  Unique items: {len(unique_items)}")
            print(f"  Unique dates: {len(unique_dates)}")
            print(f"  Unique (item, date) pairs: {len(item_date_pairs)}")
            print(f"  Records per item (avg): {len(records2) / len(unique_items) if unique_items else 0:.1f}")
            print(f"  Expected for 3 days: 3 records per item")
            print()

            if unique_dates:
                print(f"  Date values found: {sorted(unique_dates)}")
                print()

            # Verdict
            if len(unique_dates) >= 3:
                print("  ✓✓✓ SUCCESS: DAY dimension returns daily breakdown!")
                print(f"      Got {len(unique_dates)} unique dates for 3-day range")
            elif len(unique_dates) == 1:
                print(f"  ✗ FAILED: Still aggregated (only 1 date value)")
            else:
                print(f"  ⚠️  PARTIAL: Got {len(unique_dates)} dates (expected 3)")

        else:
            print("⚠️  No records returned")

        print()

    except Exception as e:
        print(f"✗ Test 2 failed: {e}")
        import traceback
        traceback.print_exc()
        print()

    # ========================================================================
    # TEST 3: Try dimension[]=LISTING&dimension[]=DAY
    # ========================================================================
    print("-" * 80)
    print("TEST 3: Alternative Syntax (dimension[]=LISTING&dimension[]=DAY)")
    print("-" * 80)
    print()

    try:
        print("Making API call with dimension array syntax...")

        from ebay_analytics.utils.url_encoding import build_analytics_filter

        url = f"{api_client.BASE_URL}/traffic_report"

        filter_param = build_analytics_filter(
            marketplace_id=config.ebay_marketplace_id,
            start_date=start_date_str,
            end_date=end_date_str,
            listing_ids=test_item_ids
        )

        metrics = [
            'TOTAL_IMPRESSION_TOTAL',
            'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
            'LISTING_VIEWS_TOTAL',
            'TRANSACTION'
        ]

        # Try array syntax - will be sent as dimension[]=LISTING&dimension[]=DAY
        params = [
            ('dimension', 'LISTING'),
            ('dimension', 'DAY'),
            ('filter', filter_param),
            ('metric', ','.join(metrics))
        ]

        headers = {
            'X-EBAY-C-MARKETPLACE-ID': config.ebay_marketplace_id
        }

        print(f"  Request params (array): {params}")
        print()

        # Use requests directly to send array params
        import requests
        response_raw = requests.get(
            url,
            params=params,
            headers={
                **headers,
                'Authorization': f'Bearer {config.ebay_access_token}'
            },
            timeout=30
        )

        response3 = response_raw.json()
        records3 = response3.get('records', [])

        print(f"✓ API call successful")
        print(f"  Total records returned: {len(records3)}")
        print()

        if records3:
            print("Sample record structure:")
            print(json.dumps(records3[0], indent=2))
            print()

            # Analyze dimensionValues structure
            sample_dims = records3[0].get('dimensionValues', [])
            print(f"DimensionValues structure:")
            print(f"  Number of dimensions: {len(sample_dims)}")
            for i, dim in enumerate(sample_dims):
                print(f"  Dimension [{i}]: {dim}")
            print()

            # Count unique dates
            unique_dates = set()
            for record in records3:
                dimension_values = record.get('dimensionValues', [])
                if len(dimension_values) >= 2:
                    date_val = dimension_values[1].get('value')
                    unique_dates.add(date_val)

            if len(unique_dates) >= 3:
                print(f"  ✓✓✓ SUCCESS: Got {len(unique_dates)} unique dates!")
            else:
                print(f"  ✗ Still only {len(unique_dates)} unique dates")

        print()

    except Exception as e:
        print(f"✗ Test 3 failed: {e}")
        import traceback
        traceback.print_exc()
        print()

    # ========================================================================
    # TEST 4: Check if DAY dimension exists at all
    # ========================================================================
    print("-" * 80)
    print("TEST 4: Try dimension=DAY only (to see if DAY is valid)")
    print("-" * 80)
    print()

    try:
        print("Making API call with dimension=DAY...")

        from ebay_analytics.utils.url_encoding import build_analytics_filter

        url = f"{api_client.BASE_URL}/traffic_report"

        filter_param = build_analytics_filter(
            marketplace_id=config.ebay_marketplace_id,
            start_date=start_date_str,
            end_date=end_date_str,
            listing_ids=test_item_ids
        )

        metrics = [
            'TOTAL_IMPRESSION_TOTAL',
            'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
            'LISTING_VIEWS_TOTAL',
            'TRANSACTION'
        ]

        params = {
            'dimension': 'DAY',  # Just DAY, not LISTING
            'filter': filter_param,
            'metric': ','.join(metrics)
        }

        headers = {
            'X-EBAY-C-MARKETPLACE-ID': config.ebay_marketplace_id
        }

        print(f"  Request params: {params}")
        print()

        response4 = api_client.get(url, params=params, headers=headers)
        records4 = response4.get('records', [])

        print(f"✓ API call successful - DAY dimension is valid!")
        print(f"  Total records returned: {len(records4)}")
        print()

        if records4:
            print("Sample record:")
            print(json.dumps(records4[0], indent=2))

        print()

    except Exception as e:
        error_msg = str(e)
        if 'dimension' in error_msg.lower() or 'invalid' in error_msg.lower():
            print(f"  ✗ DAY dimension NOT supported by API")
            print(f"  Error: {error_msg}")
        else:
            print(f"✗ Test 4 failed: {e}")
        print()

    # ========================================================================
    # SUMMARY
    # ========================================================================
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()

    try:
        print(f"Test 1 (LISTING only):")
        print(f"  Records: {len(records1)}")
        print(f"  Records per item: {len(records1) / len(test_item_ids):.1f}")
        print()

        print(f"Test 2 (LISTING,DAY):")
        print(f"  Records: {len(records2)}")
        print(f"  Records per item: {len(records2) / len(test_item_ids):.1f}")
        print()

        if len(records2) > len(records1):
            print("✓ DAY dimension increased record count - likely returns daily data!")
        else:
            print("✗ DAY dimension did NOT increase record count")

        print()

    except Exception as e:
        print(f"Could not generate summary: {e}")

    print("=" * 80)

    # Cleanup
    api_client.close()

    return True


if __name__ == "__main__":
    try:
        success = test_day_dimension()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
