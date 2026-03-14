#!/usr/bin/env python3
"""
Generate an eBay bulk upload CSV from the local DVD database.

This script pulls enriched DVD product data from the SQLite caching database
and formats it into the official eBay Draft Listing Template.
"""

import os
import sys
import csv
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path to import dvd_listings
sys.path.insert(0, str(Path(__file__).parent.parent))

from dvd_listings.db.repository import CatalogRepository

def load_config():
    """Load configuration from .env file."""
    load_dotenv()
    
    # Required/Default config
    return {
        'SKU_PREFIX': os.getenv('SKU_PREFIX', 'E-0313-'),
        'START_COUNT': int(os.getenv('START_COUNT', '1')),
        'EBAY_CATEGORY_ID': os.getenv('EBAY_CATEGORY_ID', '617'), # 617 is DVDs
        'EBAY_CONDITION_ID': os.getenv('EBAY_CONDITION_ID', '1000'), # 1000 is Brand New
        'EBAY_DESCRIPTION_TEMPLATE': os.getenv('EBAY_DESCRIPTION_TEMPLATE', 'Brand New and Sealed DVD.'),
        'DATABASE_PATH': os.getenv('DATABASE_PATH', os.getenv('DVD_DB_PATH', 'data/dvd_catalog.db')),
        'TEMPLATE_PATH': os.getenv('TEMPLATE_PATH', 'docs/eBay-category-listing-template.csv'),
        'OUTPUT_FOLDER': os.getenv('OUTPUT_FOLDER', 'output'),
        
        
        # Scheduling and Pricing
        'SCHEDULE_DAYS_AHEAD': int(os.getenv('SCHEDULE_DAYS_AHEAD', '21')),
        'PLACEHOLDER_PRICE': os.getenv('PLACEHOLDER_PRICE', '99.99'),
        
        # Region and Shipping Policies
        'REGION_CODE': os.getenv('REGION_CODE', 'DVD: 1 (US, Canada...)'),
        'POSTAL_CODE': os.getenv('POSTAL_CODE', '94043'),
        'SHIPPING_POLICY': os.getenv('SHIPPING_POLICY', 'Single DVD/VHS -Free Shipping'),
        'PAYMENT_POLICY': os.getenv('PAYMENT_POLICY', 'eBay Managed Payments (281844116014)'),
        'RETURN_POLICY': os.getenv('RETURN_POLICY', 'Free return within 30d'),
        
        # Shipping Weight and Dimensions
        'WEIGHT_MAJOR': os.getenv('DEFAULT_WEIGHT_MAJOR', '0'),
        'WEIGHT_MINOR': os.getenv('DEFAULT_WEIGHT_MINOR', '4'),
        'PACKAGE_LENGTH': os.getenv('DEFAULT_PACKAGE_LENGTH', '7'),
        'PACKAGE_WIDTH': os.getenv('DEFAULT_PACKAGE_WIDTH', '5'),
        'PACKAGE_DEPTH': os.getenv('DEFAULT_PACKAGE_DEPTH', '1'),
        'PACKAGE_TYPE': os.getenv('DEFAULT_PACKAGE_TYPE', 'PackageThickEnvelope'),
    }

def read_template(template_path: str):
    """
    Read the eBay draft template file.
    Extracts the Info header and the main column header row.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")
        
    info_headers = []
    headers = []
    
    with open(template_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if not row:
                continue
            
            if i == 0:
                # The first row is the 'Info' metadata row
                info_headers.append(row)
            elif i == 1:
                # The second row contains the headers
                headers = row
                break # Stop reading after finding the header
                
    if not headers:
        raise ValueError("Could not find column headers in the template.")
            
    # Append dynamically generated columns that eBay still supports
    new_columns = [
        'Product:UPC',
        'WeightMajor', 'WeightMinor', 'WeightUnit', 
        'PackageLength', 'PackageWidth', 'PackageDepth', 'PackageType'
    ]
    for col in new_columns:
        if col not in headers:
            headers.append(col)
            
    return info_headers, headers

import re
import requests
from collections import defaultdict

def get_image_size(url: str) -> int:
    """Returns the Content-Length of the image URL to determine the highest resolution."""
    if not url:
        return 0
    try:
        response = requests.head(url, timeout=5)
        if response.status_code == 200:
            return int(response.headers.get('Content-Length', 0))
    except Exception:
        pass
    return 0

def transform_image_url(url: str) -> str:
    if not url:
        return ''
    # 1. Replace anything like s-l[number].jpg with s-l1600.jpg
    url = re.sub(r's-l\d+\.jpg$', 's-l1600.jpg', url, flags=re.IGNORECASE)
    # 2. Replace $_[1-56].JPG with $_57.JPG
    url = re.sub(r'\$_(?:[1-9]|[1-4][0-9]|5[0-6])\.JPG$', '$_57.JPG', url, flags=re.IGNORECASE)
    return url

def generate_csv(config):
    """Generate the eBay Draft CSV from database records."""
    db_path = config['DATABASE_PATH']
    template_path = config['TEMPLATE_PATH']
    
    output_folder = config['OUTPUT_FOLDER']
    os.makedirs(output_folder, exist_ok=True)
    
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_filename = f'bulk_listing_creation_{timestamp}.csv'
    output_path = os.path.join(output_folder, output_filename)
    
    print(f"Loading database from: {db_path}")
    repo = CatalogRepository(db_path)
    
    # Retrieve all products (active)
    # The database query inherently sorts by fetched_at DESC
    all_products = repo.get_all_products()
    
    # Filter to only keep the best entry per UPC (prioritizing max image size)
    upc_groups = defaultdict(list)
    for product in all_products:
        if product.upc:
            upc_groups[product.upc].append(product)
            
    products = []
    print(f"Resolving highest quality images for {len(upc_groups)} unique UPCs...")
    for upc, group in upc_groups.items():
        if len(group) == 1:
            products.append(group[0])
            continue
            
        # Multiple entries for this UPC, pick the one with the largest Image Size
        best_product = None
        max_size = -1
        
        for product in group:
            transformed_url = transform_image_url(product.primary_image_url)
            size = get_image_size(transformed_url)
            # If size is the same, it keeps the first one it encounters (which is the most recent fetched_at)
            if size > max_size:
                max_size = size
                best_product = product
                
        if best_product:
            products.append(best_product)
            
    # Sort the unique products by fetched_at from earliest to latest
    # Provide a fallback datetime if fetched_at is None (e.g., datetime.min)
    from datetime import datetime
    products.sort(key=lambda p: p.fetched_at if p.fetched_at else datetime.min)
            
    print(f"Found {len(all_products)} records, filtered down to {len(products)} unique UPCs.")
    
    if not products:
        print("No products found to export.")
        return
        
    print(f"Loading template from: {template_path}")
    info_headers, column_headers = read_template(template_path)
    
    sku_prefix = config['SKU_PREFIX']
    start_count = config['START_COUNT']
    category_id = config['EBAY_CATEGORY_ID']
    condition_id = config['EBAY_CONDITION_ID']
    description = config['EBAY_DESCRIPTION_TEMPLATE']
    
    # Needs to match exactly the column name in the template
    action_col = next((col for col in column_headers if col.startswith('*Action')), '*Action(SiteID=US|Country=US|Currency=USD|Version=1193|CC=UTF-8)')
    
    # ScheduleTime: Current Time + SCHEDULE_DAYS_AHEAD
    from datetime import timedelta
    schedule_days_ahead = config['SCHEDULE_DAYS_AHEAD']
    schedule_time = datetime.now() + timedelta(days=schedule_days_ahead)
    schedule_time_str = schedule_time.strftime('%Y-%m-%d %H:%M:%S')

    # Map index to output
    rows_to_write = []
    for i, product in enumerate(products):
        # Default empty row
        row_dict = {col: '' for col in column_headers}
        
        # Provide values per mapping table
        row_dict[action_col] = 'Add'
        row_dict['CustomLabel'] = f"{sku_prefix}{str(start_count + i).zfill(3)}"
        row_dict['*Category'] = category_id
        
        # Build Title with constraints (max 80 chars)
        base_title = product.title or ''
        title = base_title
        
        # 1) check existing title has room for " Brand New & Sealed"
        suffix1 = " Brand New & Sealed"
        if len(title) + len(suffix1) <= 80:
            title += suffix1
            
            # 2) check again for room for " Free Shipping"
            suffix2 = " Free Shipping"
            if len(title) + len(suffix2) <= 80:
                title += suffix2

        row_dict['*Title'] = title
        row_dict['*C:Movie/TV Title'] = base_title
        row_dict['ScheduleTime'] = schedule_time_str
        row_dict['*ConditionID'] = condition_id
        row_dict['*C:Format'] = 'DVD'
        row_dict['C:Region Code'] = config['REGION_CODE']
        
        # In v4 Category templates, UPC is usually expected as simply 'UPC' or 'Product:UPC'.
        # Since 'UPC' was failing to populate in the UI, we will append it or set it natively
        row_dict['Product:UPC'] = product.upc or ''
        row_dict['PicURL'] = transform_image_url(product.primary_image_url)
        row_dict['*Description'] = description
        row_dict['*Format'] = 'FixedPrice'
        row_dict['*Duration'] = 'GTC'
        row_dict['*StartPrice'] = config['PLACEHOLDER_PRICE']
        
        # Enable Best Offer
        row_dict['BestOfferEnabled'] = '1'
        
        row_dict['*Quantity'] = '1'
        row_dict['*Location'] = config['POSTAL_CODE']
        row_dict['*DispatchTimeMax'] = '1'
        row_dict['ShippingProfileName'] = config['SHIPPING_POLICY']
        row_dict['PaymentProfileName'] = config['PAYMENT_POLICY']
        row_dict['ReturnProfileName'] = config['RETURN_POLICY']
        
        # Custom Item Specifics directly mapped from DVDAspects
        if product.dvd_aspects:
            row_dict['C:Actor'] = ", ".join(product.dvd_aspects.actors) if product.dvd_aspects.actors else ''
            row_dict['C:Director'] = ", ".join(product.dvd_aspects.directors) if product.dvd_aspects.directors else ''
            row_dict['C:Genre'] = product.dvd_aspects.genre or ''
            row_dict['C:Sub-Genre'] = product.dvd_aspects.sub_genre or ''
            row_dict['C:Studio'] = product.dvd_aspects.studio or ''
            row_dict['C:Release Year'] = product.dvd_aspects.release_year or ''
            row_dict['C:Rating'] = product.dvd_aspects.rating or ''
            row_dict['C:Edition'] = product.dvd_aspects.edition or ''
            
        # Optional Shipping Measurements appended to CSV output
        row_dict['WeightMajor'] = config['WEIGHT_MAJOR']
        row_dict['WeightMinor'] = config['WEIGHT_MINOR']
        row_dict['WeightUnit'] = 'oz'
        row_dict['PackageLength'] = config['PACKAGE_LENGTH']
        row_dict['PackageWidth'] = config['PACKAGE_WIDTH']
        row_dict['PackageDepth'] = config['PACKAGE_DEPTH']
        row_dict['PackageType'] = config['PACKAGE_TYPE']
        
        # Make a simple list matching the order of column_headers
        row_list = [row_dict.get(col, '') for col in column_headers]
        rows_to_write.append(row_list)
        
    print(f"Writing to {output_path}...")
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        # Write #INFO headers
        for info_row in info_headers:
            writer.writerow(info_row)
        # Write column headers
        writer.writerow(column_headers)
        # Write data rows
        for row in rows_to_write:
            writer.writerow(row)
            
    print(f"Success! Exported {len(rows_to_write)} records to {output_path}.")

def main():
    try:
        config = load_config()
        generate_csv(config)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
