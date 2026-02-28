"""
Test script to investigate available view metrics from eBay Analytics API.

This script tests different metric combinations to identify which metrics
are available and which combination gives us the full view count matching
the seller portal.
"""

from ebay_analytics.config import load_config
from ebay_analytics.api.analytics import AnalyticsAPIClient
from ebay_analytics.db.repository import MetadataRepository
import json

def test_view_metrics():
    """Test different view metric combinations."""

    print("="*70)
    print("TESTING ANALYTICS API VIEW METRICS")
    print("="*70)
    print()

    # Load config
    config = load_config()
    client = AnalyticsAPIClient(config)
    meta_repo = MetadataRepository(config.db_path)

    # Get a few active listings for testing
    active_ids = meta_repo.get_active_listing_ids()[:10]  # Test with 10 listings

    print(f"Testing with {len(active_ids)} sample listings for Feb 24, 2026")
    print(f"Sample item IDs: {active_ids[:3]}")
    print()

    # Test different metric combinations
    metric_tests = [
        {
            'name': 'Current (Total only)',
            'metrics': [
                'TOTAL_IMPRESSION_TOTAL',
                'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
                'LISTING_VIEWS_TOTAL',
                'TRANSACTION'
            ]
        },
        {
            'name': 'Test: Source Breakdown (Official API)',
            'metrics': [
                'LISTING_VIEWS_TOTAL',
                'LISTING_VIEWS_SOURCE_DIRECT',
                'LISTING_VIEWS_SOURCE_OFF_EBAY',
                'LISTING_VIEWS_SOURCE_OTHER_EBAY',
                'LISTING_VIEWS_SOURCE_SEARCH_RESULTS_PAGE',
                'LISTING_VIEWS_SOURCE_STORE'
            ]
        },
        {
            'name': 'Test: Just Off-eBay Traffic',
            'metrics': [
                'LISTING_VIEWS_TOTAL',
                'LISTING_VIEWS_SOURCE_OFF_EBAY'
            ]
        },
        {
            'name': 'Test: All Impressions',
            'metrics': [
                'LISTING_IMPRESSION_TOTAL',
                'LISTING_IMPRESSION_SEARCH_RESULTS_PAGE',
                'LISTING_IMPRESSION_STORE'
            ]
        }
    ]

    for test in metric_tests:
        print(f"\n{'='*70}")
        print(f"TEST: {test['name']}")
        print(f"{'='*70}")
        print(f"Metrics to request: {test['metrics']}")
        print()

        try:
            # Make API call
            response = client.get_traffic_report(
                start_date='20260224',
                end_date='20260224',
                listing_ids=active_ids,
                metrics=test['metrics']
            )

            if 'records' in response and len(response['records']) > 0:
                record = response['records'][0]
                print(f"✓ API call successful!")
                print(f"  Records returned: {len(response['records'])}")
                print()
                print(f"  Sample record structure:")
                print(f"    Dimension values: {record.get('dimensionValues', [])}")
                print(f"    Metric values: {record.get('metricValues', [])}")
                print()

                # Show first record's metrics
                metric_values = record.get('metricValues', [])
                if metric_values:
                    print(f"  Metric values for first listing:")
                    for idx, metric_name in enumerate(test['metrics']):
                        if idx < len(metric_values):
                            value = metric_values[idx].get('value', 0)
                            print(f"    {metric_name}: {value}")
                print()

            else:
                print(f"  ⚠ API returned no records")
                print()

        except Exception as e:
            print(f"  ✗ ERROR: {str(e)}")
            print()

    print("="*70)
    print("TESTING COMPLETE")
    print("="*70)
    print()
    print("Next steps:")
    print("1. Review which metric combination works")
    print("2. Check if any combination gives breakdown by traffic source")
    print("3. Update analytics.py to use the correct metrics")

    client.close()

if __name__ == "__main__":
    test_view_metrics()
