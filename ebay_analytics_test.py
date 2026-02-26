#!/usr/bin/env python3
"""
eBay Sell Analytics API - Hello World Test Script

This script verifies connection to the eBay Sell Analytics API using a
Production User Access Token and retrieves a 7-day traffic report.
"""

import os
import json
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv


def get_date_range():
    """Calculate date range for the last 7 days in YYYYMMDD format."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    return f"{start_str}..{end_str}"


def fetch_traffic_report(access_token, marketplace_id="EBAY_US"):
    """
    Fetch traffic report from eBay Sell Analytics API.

    Args:
        access_token (str): eBay Production User Access Token
        marketplace_id (str): eBay marketplace ID (default: EBAY_US)

    Returns:
        tuple: (status_code, response_data)
    """
    # API endpoint
    url = "https://api.ebay.com/sell/analytics/v1/traffic_report"

    # Request headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Language": "en-US"
    }

    # Query parameters
    params = {
        "dimension": "DAY",
        "filter": f"marketplace_ids:{{{marketplace_id}}},date_range:[{get_date_range()}]",
        "metric": "CLICK_THROUGH_RATE,TOTAL_IMPRESSION_TOTAL,LISTING_VIEWS_TOTAL"
    }

    # Make the request
    try:
        response = requests.get(url, headers=headers, params=params)
        return response.status_code, response
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None, None


def main():
    """Main function to test eBay Analytics API connection."""
    # Load environment variables from .env file
    load_dotenv()

    print("=" * 60)
    print("eBay Sell Analytics API - Hello World Test")
    print("=" * 60)
    print()

    # Get access token from environment variable
    access_token = os.getenv("EBAY_ACCESS_TOKEN")

    if not access_token:
        print("Error: EBAY_ACCESS_TOKEN environment variable not set.")
        print("Please set your eBay Production Access Token:")
        print("  export EBAY_ACCESS_TOKEN='your_token_here'")
        print()
        print("Or create a .env file with:")
        print("  EBAY_ACCESS_TOKEN=your_token_here")
        return

    # Get marketplace ID (default to EBAY_US)
    marketplace_id = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")

    print(f"Marketplace: {marketplace_id}")
    print(f"Using date range: {get_date_range()}")
    print(f"Requesting traffic report...")
    print()

    # Fetch the traffic report
    status_code, response = fetch_traffic_report(access_token, marketplace_id)

    if status_code is None:
        return

    # Print status code
    print(f"HTTP Status Code: {status_code}")
    print()

    # Handle response
    if status_code == 200:
        print("Success! Connection verified.")
        print()
        print("=" * 60)
        print("Traffic Report Data:")
        print("=" * 60)

        try:
            data = response.json()
            print(json.dumps(data, indent=2))

            # Print summary if records exist
            if "records" in data:
                print()
                print("=" * 60)
                print(f"Summary: {len(data['records'])} day(s) of data retrieved")
                print("=" * 60)
        except json.JSONDecodeError:
            print("Response is not valid JSON:")
            print(response.text)
    else:
        print("Error: Request failed.")
        print()
        try:
            error_data = response.json()
            print("Error Details:")
            print(json.dumps(error_data, indent=2))
        except json.JSONDecodeError:
            print("Error Response:")
            print(response.text)


if __name__ == "__main__":
    main()
