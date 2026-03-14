#!/usr/bin/env python3
"""
Test script to verify token validity and check rate limit headers.

This script:
1. Tests if the access token works with the Sell Analytics API
2. Checks HTTP response headers for rate limit information
3. Tries the Developer Analytics getRateLimits API

Run: poetry run python scripts/test_token_and_limits.py
"""

import sys
import os
from pathlib import Path
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ebay_analytics.config import Config


def test_traffic_report_api(access_token: str) -> dict:
    """
    Test the actual traffic_report API that we use.
    This verifies the token works for the Sell Analytics API.
    """
    url = "https://api.ebay.com/sell/analytics/v1/traffic_report"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Get yesterday's date in PST
    pst = ZoneInfo("America/Los_Angeles")
    yesterday = datetime.now(pst) - timedelta(days=1)
    date_str = yesterday.strftime("%Y%m%d")  # YYYYMMDD format

    # Build correct filter format (marketplace + date range)
    from urllib.parse import quote
    marketplace_filter = quote(f"marketplace_ids:{{EBAY_US}}", safe='')
    date_filter = quote(f"date_range:[{date_str}..{date_str}]", safe='')
    full_filter = f"{marketplace_filter},{date_filter}"

    # Simple query with minimal parameters
    params = {
        "dimension": "LISTING",
        "filter": full_filter,
        "metric": "LISTING_IMPRESSION_TOTAL",
        "limit": "1"  # Only get 1 record to minimize API usage
    }

    # Add marketplace header
    headers["X-EBAY-C-MARKETPLACE-ID"] = "EBAY_US"

    print(f"📡 Testing Sell Analytics API (traffic_report)...")
    print(f"   URL: {url}")
    print(f"   Date: {date_str}")
    print()

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        print(f"📥 Response Status: {response.status_code}")
        print()

        # Check for rate limit headers
        print("📊 Rate Limit Headers:")
        rate_limit_headers = {
            k: v for k, v in response.headers.items()
            if 'rate' in k.lower() or 'limit' in k.lower() or 'quota' in k.lower()
        }

        if rate_limit_headers:
            for header, value in rate_limit_headers.items():
                print(f"   {header}: {value}")
        else:
            print("   ⚠️  No rate limit headers found in response")

        print()
        print("📋 All Response Headers:")
        for header, value in response.headers.items():
            print(f"   {header}: {value}")
        print()

        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS - Token is valid for Sell Analytics API!")
            print(f"   Records returned: {len(data.get('records', []))}")
            return {"success": True, "headers": dict(response.headers), "data": data}
        else:
            print(f"❌ Error Response:")
            try:
                error_data = response.json()
                print(f"   {json.dumps(error_data, indent=2)}")
            except:
                print(f"   {response.text}")
            return {"success": False, "status": response.status_code, "headers": dict(response.headers)}

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return {"success": False, "error": str(e)}


def test_developer_analytics_api(access_token: str) -> dict:
    """
    Test the Developer Analytics API getRateLimits endpoint.
    """
    url = "https://api.ebay.com/developer/analytics/v1_beta/rate_limit/"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    params = {
        "api_name": "sell.analytics",
        "api_context": "sell"
    }

    print(f"📡 Testing Developer Analytics API (getRateLimits)...")
    print(f"   URL: {url}")
    print()

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        print(f"📥 Response Status: {response.status_code}")
        print()

        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS - Token works for Developer Analytics API!")
            return {"success": True, "data": data}
        elif response.status_code == 401:
            print(f"❌ Authentication Failed (401)")
            print(f"   The token may not have access to the Developer Analytics API.")
            print(f"   This API may require a different scope or authentication method.")
            return {"success": False, "status": 401}
        else:
            print(f"⚠️  Response Status: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   {json.dumps(error_data, indent=2)}")
            except:
                print(f"   {response.text}")
            return {"success": False, "status": response.status_code}

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return {"success": False, "error": str(e)}


def main():
    """Main test function."""
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 15 + "EBAY TOKEN & RATE LIMITS TEST SCRIPT" + " " * 27 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    try:
        # Load configuration
        print("1️⃣  Loading configuration...")
        config = Config()
        access_token = config.ebay_access_token
        print(f"   ✓ Access token loaded (length: {len(access_token)} chars)")
        print()

        print("=" * 80)
        print("TEST 1: Sell Analytics API (traffic_report)")
        print("=" * 80)
        print()

        result1 = test_traffic_report_api(access_token)

        print()
        print("=" * 80)
        print("TEST 2: Developer Analytics API (getRateLimits)")
        print("=" * 80)
        print()

        result2 = test_developer_analytics_api(access_token)

        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print()

        if result1.get("success"):
            print("✅ Sell Analytics API: WORKING")
            print("   Your token can fetch traffic data successfully")
        else:
            print("❌ Sell Analytics API: FAILED")
            print("   You need to fix your access token before syncing data")

        print()

        if result2.get("success"):
            print("✅ Developer Analytics API: WORKING")
            print("   You can query rate limits via getRateLimits API")

            # Save the rate limit data
            if result2.get("data"):
                output_file = Path(__file__).parent.parent / "docs" / "rate_limits_response.json"
                with open(output_file, 'w') as f:
                    json.dump(result2["data"], f, indent=2)
                print(f"   Raw response saved to: {output_file}")
        else:
            print("⚠️  Developer Analytics API: NOT ACCESSIBLE")
            print("   You may need a different scope or authentication method")
            print("   However, this doesn't prevent traffic data syncing from working")

        print()

        if result1.get("success"):
            print("📌 RECOMMENDATION:")
            print()
            print("Since the Sell Analytics API works, we should implement an")
            print("alternative approach for rate limit monitoring:")
            print()
            print("1. Track API calls in-memory during script execution")
            print("2. Parse rate limit info from response headers (if available)")
            print("3. Use conservative delays to stay under limits")
            print("4. Implement wait-and-resume based on 429 error response headers")
            print()
            print("The getRateLimits API is optional - we can implement smart")
            print("rate limiting without it by being conservative and tracking")
            print("our own usage.")

        print()
        return 0 if result1.get("success") else 1

    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
