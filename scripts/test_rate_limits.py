#!/usr/bin/env python3
"""
Temporary test script to verify eBay getRateLimits API.

This script tests Phase 1 of the rate limit adaptation plan:
- Calls the eBay Developer Analytics API getRateLimits endpoint
- Displays current rate limit information for sell.analytics.traffic_report
- Verifies authentication and API access work correctly

Run: python scripts/test_rate_limits.py
"""

import sys
import os
from pathlib import Path
import requests
from datetime import datetime
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ebay_analytics.config import Config


def get_rate_limits(access_token: str) -> dict:
    """
    Query eBay's getRateLimits API to get actual quota information.

    Args:
        access_token: eBay OAuth access token

    Returns:
        Dict containing full API response
    """
    url = "https://api.ebay.com/developer/analytics/v1_beta/rate_limit/"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Query specifically for sell.analytics API
    params = {
        "api_name": "sell.analytics",
        "api_context": "sell"
    }

    print(f"📡 Calling eBay getRateLimits API...")
    print(f"   URL: {url}")
    print(f"   Params: {params}")
    print()

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        print(f"📥 Response Status: {response.status_code}")
        print()

        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error Response:")
            print(f"   Status: {response.status_code}")
            print(f"   Headers: {dict(response.headers)}")
            try:
                error_data = response.json()
                print(f"   Body: {json.dumps(error_data, indent=2)}")
            except:
                print(f"   Body: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return None


def parse_reset_time(reset_str: str) -> str:
    """Parse ISO 8601 timestamp and calculate time remaining."""
    try:
        reset_dt = datetime.fromisoformat(reset_str.replace('Z', '+00:00'))
        now_dt = datetime.now(reset_dt.tzinfo)
        delta = reset_dt - now_dt

        hours = delta.total_seconds() / 3600
        minutes = delta.total_seconds() / 60

        if hours >= 1:
            return f"{hours:.1f} hours"
        else:
            return f"{minutes:.1f} minutes"
    except:
        return "unknown"


def display_rate_limits(data: dict):
    """
    Display rate limit information in a readable format.

    Args:
        data: Response from getRateLimits API
    """
    if not data:
        print("❌ No data to display")
        return

    print("=" * 80)
    print("EBAY API RATE LIMITS - CURRENT STATUS")
    print("=" * 80)
    print()

    rate_limits = data.get("rateLimits", [])

    if not rate_limits:
        print("⚠️  No rate limit data found in response")
        print()
        print("Full Response:")
        print(json.dumps(data, indent=2))
        return

    # Find sell.analytics data
    for api_info in rate_limits:
        api_name = api_info.get("apiName", "unknown")
        api_context = api_info.get("apiContext", "unknown")

        print(f"API: {api_name} (context: {api_context})")
        print("-" * 80)

        resources = api_info.get("resources", [])

        for resource in resources:
            resource_name = resource.get("name", "unknown")
            print(f"\n📊 Resource: {resource_name}")
            print()

            rates = resource.get("rates", [])

            if not rates:
                print("   ⚠️  No rate data available")
                continue

            for idx, rate in enumerate(rates, 1):
                count = rate.get("count", 0)
                limit = rate.get("limit", 0)
                remaining = rate.get("remaining", 0)
                reset = rate.get("reset", "unknown")
                time_window = rate.get("timeWindow", 0)

                # Calculate percentage used
                if limit > 0:
                    pct_used = (count / limit) * 100
                else:
                    pct_used = 0

                # Determine limit type
                if time_window == 86400:
                    limit_type = "Daily Limit (24 hours)"
                elif time_window == 300:
                    limit_type = "Short-Duration Limit (5 minutes)"
                elif time_window == 60:
                    limit_type = "Per-Minute Limit"
                else:
                    limit_type = f"Custom Limit ({time_window} seconds)"

                # Time until reset
                time_remaining = parse_reset_time(reset)

                print(f"   Rate Limit #{idx}: {limit_type}")
                print(f"   ┌─────────────────────────────────────────────")
                print(f"   │ Quota:      {limit:,} calls per window")
                print(f"   │ Used:       {count:,} calls ({pct_used:.1f}%)")
                print(f"   │ Remaining:  {remaining:,} calls")
                print(f"   │ Resets at:  {reset}")
                print(f"   │ Resets in:  {time_remaining}")
                print(f"   │ Window:     {time_window:,} seconds")
                print(f"   └─────────────────────────────────────────────")
                print()

                # Visual bar
                bar_length = 50
                filled = int(bar_length * pct_used / 100)
                bar = "█" * filled + "░" * (bar_length - filled)
                print(f"   Usage: [{bar}] {pct_used:.1f}%")
                print()

    print("=" * 80)


def main():
    """Main test function."""
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "EBAY RATE LIMITS TEST SCRIPT" + " " * 30 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    try:
        # Load configuration
        print("1️⃣  Loading configuration...")
        config = Config()
        access_token = config.ebay_access_token
        print(f"   ✓ Access token loaded (length: {len(access_token)} chars)")
        print()

        # Query rate limits
        print("2️⃣  Querying eBay API for rate limits...")
        print()
        data = get_rate_limits(access_token)

        if data:
            print("   ✓ Successfully retrieved rate limit data")
            print()

            # Display the results
            print("3️⃣  Parsing and displaying results...")
            print()
            display_rate_limits(data)

            # Save raw response for inspection
            output_file = Path(__file__).parent.parent / "docs" / "rate_limits_response.json"
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✓ Raw response saved to: {output_file}")
            print()

        else:
            print("❌ Failed to retrieve rate limit data")
            print()
            print("Troubleshooting:")
            print("1. Check your EBAY_ACCESS_TOKEN is valid and not expired")
            print("2. Ensure the token has the correct scope: https://api.ebay.com/oauth/api_scope")
            print("3. Verify your eBay app has access to the Developer Analytics API")
            print()
            return 1

        print()
        print("✅ Test completed successfully!")
        print()
        return 0

    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        print()
        print("Make sure your .env file contains:")
        print("  EBAY_ACCESS_TOKEN=your_token_here")
        print()
        return 1

    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
