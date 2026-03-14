#!/usr/bin/env python3
"""
Generate an eBay bulk upload CSV from the local media catalog database.

This script pulls enriched product data (DVD, CD, or VHS) from the SQLite
caching database and formats it into the official eBay Draft Listing Template
for the selected media type.

Media type is configured via MEDIA_TYPE environment variable (DVD, CD, or VHS).
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
    """Load configuration from .env file with media-type-specific defaults."""
    load_dotenv()

    # Get media type (turnkey configuration selector)
    media_type = os.getenv('MEDIA_TYPE', 'DVD').upper()

    # Define media-type-specific defaults
    MEDIA_DEFAULTS = {
        'DVD': {
            'CATEGORY_ID': '617',
            'TEMPLATE_PATH': 'docs/eBay-DVD-template.csv',
            'DESCRIPTION_TEMPLATE': 'Brand New and Sealed DVD.',
            'REGION_CODE': 'DVD: 1 (US, Canada...)',
            'SHIPPING_POLICY': 'Single DVD/VHS -Free Shipping',
            'WEIGHT_MAJOR': '0',
            'WEIGHT_MINOR': '4',
            'PACKAGE_LENGTH': '7',
            'PACKAGE_WIDTH': '5',
            'PACKAGE_DEPTH': '1',
            'PACKAGE_TYPE': 'PackageThickEnvelope',
        },
        'CD': {
            'CATEGORY_ID': '176984',
            'TEMPLATE_PATH': 'docs/eBay-CD-template.csv',
            'DESCRIPTION_TEMPLATE': 'Brand New and Sealed CD.',
            'REGION_CODE': '',  # CDs don't have region codes
            'SHIPPING_POLICY': 'Single CD - Free Shipping',
            'WEIGHT_MAJOR': '0',
            'WEIGHT_MINOR': '3',
            'PACKAGE_LENGTH': '6',
            'PACKAGE_WIDTH': '5',
            'PACKAGE_DEPTH': '0.5',
            'PACKAGE_TYPE': 'PackageThickEnvelope',
        },
        'VHS': {
            'CATEGORY_ID': '309',
            'TEMPLATE_PATH': 'docs/eBay-VHS-template.csv',
            'DESCRIPTION_TEMPLATE': 'VHS Tape in Good Condition.',
            'REGION_CODE': '',  # VHS doesn't require region codes
            'SHIPPING_POLICY': 'Single DVD/VHS -Free Shipping',
            'WEIGHT_MAJOR': '0',
            'WEIGHT_MINOR': '8',
            'PACKAGE_LENGTH': '8',
            'PACKAGE_WIDTH': '4.5',
            'PACKAGE_DEPTH': '1',
            'PACKAGE_TYPE': 'PackageThickEnvelope',
        }
    }

    # Get defaults for selected media type
    defaults = MEDIA_DEFAULTS.get(media_type, MEDIA_DEFAULTS['DVD'])

    # Helper function to get config with media-type-specific fallback
    def get_config(key, default_value=''):
        """Get config value with priority: manual override > media-specific > default"""
        # Check for manual override (e.g., EBAY_CATEGORY_ID)
        manual_override = os.getenv(key)
        if manual_override is not None:
            return manual_override

        # Check for media-specific env var (e.g., DVD_CATEGORY_ID)
        media_specific_key = f"{media_type}_{key}"
        media_specific = os.getenv(media_specific_key)
        if media_specific is not None:
            return media_specific

        # Fall back to default value
        return default_value

    # Build configuration with smart defaults
    return {
        'MEDIA_TYPE': media_type,
        'SKU_PREFIX': os.getenv('SKU_PREFIX', 'E-0313-'),
        'START_COUNT': int(os.getenv('START_COUNT', '1')),
        'EBAY_CATEGORY_ID': get_config('CATEGORY_ID', defaults['CATEGORY_ID']),
        'EBAY_CONDITION_ID': os.getenv('EBAY_CONDITION_ID', '1000'),
        'EBAY_DESCRIPTION_TEMPLATE': get_config('DESCRIPTION_TEMPLATE', defaults['DESCRIPTION_TEMPLATE']),
        'DATABASE_PATH': os.getenv('DATABASE_PATH', os.getenv('DVD_DB_PATH', 'data/dvd_catalog.db')),
        'TEMPLATE_PATH': get_config('TEMPLATE_PATH', defaults['TEMPLATE_PATH']),
        'OUTPUT_FOLDER': os.getenv('OUTPUT_FOLDER', 'output'),

        # Scheduling and Pricing
        'SCHEDULE_DAYS_AHEAD': int(os.getenv('SCHEDULE_DAYS_AHEAD', '21')),
        'PLACEHOLDER_PRICE': os.getenv('PLACEHOLDER_PRICE', '99.99'),
        'PLACEHOLDER_IMAGE_URL': os.getenv('PLACEHOLDER_IMAGE_URL', ''),

        # Region and Shipping Policies
        'REGION_CODE': get_config('REGION_CODE', defaults['REGION_CODE']),
        'POSTAL_CODE': os.getenv('POSTAL_CODE', '94043'),
        'SHIPPING_POLICY': get_config('SHIPPING_POLICY', defaults['SHIPPING_POLICY']),
        'PAYMENT_POLICY': os.getenv('PAYMENT_POLICY', 'eBay Managed Payments (281844116014)'),
        'RETURN_POLICY': os.getenv('RETURN_POLICY', 'Free return within 30d'),

        # Shipping Weight and Dimensions
        'WEIGHT_MAJOR': get_config('WEIGHT_MAJOR', defaults['WEIGHT_MAJOR']),
        'WEIGHT_MINOR': get_config('WEIGHT_MINOR', defaults['WEIGHT_MINOR']),
        'PACKAGE_LENGTH': get_config('PACKAGE_LENGTH', defaults['PACKAGE_LENGTH']),
        'PACKAGE_WIDTH': get_config('PACKAGE_WIDTH', defaults['PACKAGE_WIDTH']),
        'PACKAGE_DEPTH': get_config('PACKAGE_DEPTH', defaults['PACKAGE_DEPTH']),
        'PACKAGE_TYPE': get_config('PACKAGE_TYPE', defaults['PACKAGE_TYPE']),
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
from io import BytesIO
try:
    from PIL import Image
except ImportError:
    Image = None

def get_image_dimensions(url: str) -> tuple:
    """
    Returns (width, height) of the image in pixels, or (0, 0) on error.

    Args:
        url: Image URL to check

    Returns:
        Tuple of (width, height) in pixels
    """
    if not url or not Image:
        return (0, 0)
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            return img.size  # Returns (width, height)
    except Exception as e:
        # Silently fail and return 0,0
        pass
    return (0, 0)

def get_max_dimension(url: str) -> int:
    """
    Returns the longest side of the image in pixels.

    This is used to verify images meet eBay's requirement of at least
    500 pixels on the longest side.

    Args:
        url: Image URL to check

    Returns:
        Maximum dimension in pixels, or 0 on error
    """
    width, height = get_image_dimensions(url)
    return max(width, height)

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

    # Retrieve products filtered by media type
    # The database query inherently sorts by fetched_at DESC
    media_type = config['MEDIA_TYPE']
    print(f"Filtering products by media type: {media_type}")
    all_products = repo.get_all_products(media_type=media_type)
    
    # Filter to only keep the best entry per UPC (prioritizing max image size)
    upc_groups = defaultdict(list)
    for product in all_products:
        if product.upc:
            upc_groups[product.upc].append(product)
            
    products = []
    print(f"Resolving highest quality images for {len(upc_groups)} unique UPCs...")
    images_below_500px = []  # Track products with images that don't meet eBay requirements

    for upc, group in upc_groups.items():
        if len(group) == 1:
            products.append(group[0])
            continue

        # Multiple entries for this UPC, pick the one with the largest pixel dimensions
        best_product = None
        max_dimension = -1

        for product in group:
            transformed_url = transform_image_url(product.primary_image_url)
            dimension = get_max_dimension(transformed_url)
            # If dimension is the same, it keeps the first one it encounters (which is the most recent fetched_at)
            if dimension > max_dimension:
                max_dimension = dimension
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

        # Add media-type-specific title suffixes
        media_type = config['MEDIA_TYPE']
        if media_type in ['DVD', 'CD']:
            suffix1 = " Brand New & Sealed"
        elif media_type == 'VHS':
            suffix1 = " Good Condition"
        else:
            suffix1 = ""

        if suffix1 and len(title) + len(suffix1) <= 80:
            title += suffix1

            # Add Free Shipping suffix if there's room
            suffix2 = " Free Shipping"
            if len(title) + len(suffix2) <= 80:
                title += suffix2

        row_dict['*Title'] = title
        row_dict['ScheduleTime'] = schedule_time_str
        row_dict['*ConditionID'] = condition_id

        # Media-type-specific required fields
        if media_type == 'DVD':
            row_dict['*C:Format'] = 'DVD'
            row_dict['*C:Movie/TV Title'] = base_title
            if config['REGION_CODE']:
                row_dict['C:Region Code'] = config['REGION_CODE']
        elif media_type == 'CD':
            row_dict['*C:Format'] = 'CD'
            row_dict['*C:Release Title'] = base_title
        elif media_type == 'VHS':
            # VHS doesn't have required Format field
            row_dict['C:Movie/TV Title'] = base_title
        
        # In v4 Category templates, UPC is usually expected as simply 'UPC' or 'Product:UPC'.
        # Since 'UPC' was failing to populate in the UI, we will append it or set it natively
        row_dict['Product:UPC'] = product.upc or ''

        # Transform and validate image URL
        transformed_url = transform_image_url(product.primary_image_url)
        image_max_dim = get_max_dimension(transformed_url)
        final_image_url = transformed_url
        used_placeholder = False

        # Validate image meets eBay's 500px requirement
        # Use placeholder if:
        # - No image (dimension = 0)
        # - Image too small (dimension < 500)
        if image_max_dim < 500:
            # Use placeholder if configured
            placeholder_url = config.get('PLACEHOLDER_IMAGE_URL', '')
            if placeholder_url:
                final_image_url = placeholder_url
                used_placeholder = True

            # Track images that don't meet requirements
            if image_max_dim > 0:  # Only log actual images, not missing ones
                images_below_500px.append({
                    'upc': product.upc,
                    'title': base_title,
                    'url': transformed_url,
                    'dimension': image_max_dim,
                    'used_placeholder': used_placeholder
                })

        row_dict['PicURL'] = final_image_url
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
        
        # Parse dynamic aspects from aspects_json
        import json
        aspect_map = {}
        if product.aspects_json:
            try:
                raw_aspects = json.loads(product.aspects_json)
                for aspect in raw_aspects:
                    name = aspect.get('localizedName', '')
                    values = aspect.get('localizedValues', [])
                    if values:
                        aspect_map[name] = values
            except Exception:
                pass
        
        if media_type == 'DVD':
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

        elif media_type == 'CD':
            # CD-specific aspects from aspects_json
            row_dict['*C:Artist'] = ", ".join(aspect_map.get('Artist', []))
            row_dict['C:Genre'] = ", ".join(aspect_map.get('Genre', []))
            row_dict['C:Record Label'] = ", ".join(aspect_map.get('Record Label', []))
            row_dict['C:Style'] = ", ".join(aspect_map.get('Style', []))
            row_dict['C:Type'] = ", ".join(aspect_map.get('Type', aspect_map.get('Album Type', [])))
            row_dict['C:Release Year'] = ", ".join(aspect_map.get('Release Year', aspect_map.get('Year', [])))
            row_dict['C:Edition'] = ", ".join(aspect_map.get('Edition', []))
            row_dict['C:Format'] = ", ".join(aspect_map.get('Format', ['CD']))

        elif media_type == 'VHS':
            # VHS-specific aspects (similar to DVD but from aspects_json or dvd_aspects)
            if product.dvd_aspects:
                row_dict['C:Actor'] = ", ".join(product.dvd_aspects.actors) if product.dvd_aspects.actors else ''
                row_dict['C:Director'] = ", ".join(product.dvd_aspects.directors) if product.dvd_aspects.directors else ''
                row_dict['C:Genre'] = product.dvd_aspects.genre or ''
                row_dict['C:Sub-Genre'] = product.dvd_aspects.sub_genre or ''
                row_dict['C:Studio'] = product.dvd_aspects.studio or ''
                row_dict['C:Release Year'] = product.dvd_aspects.release_year or ''
                row_dict['C:Rating'] = product.dvd_aspects.rating or ''
                row_dict['C:Edition'] = product.dvd_aspects.edition or ''
            # VHS-specific fields from aspects_json
            row_dict['C:Signal Standard'] = ", ".join(aspect_map.get('Signal Standard', aspect_map.get('Format', [])))
            row_dict['C:Former Rental'] = ", ".join(aspect_map.get('Former Rental', []))
            
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

    # Warn about images that don't meet eBay's requirements
    if images_below_500px:
        placeholder_count = sum(1 for item in images_below_500px if item.get('used_placeholder'))

        if placeholder_count > 0:
            print(f"\n✓ INFO: {placeholder_count} product(s) with small images using placeholder:")
            for item in images_below_500px:
                if item.get('used_placeholder'):
                    print(f"  - UPC {item['upc']}: {item['title'][:50]}")
                    print(f"    Original image: {item['dimension']}px (need ≥500px)")
                    print(f"    Using placeholder image - update with real photos after listing creation")

        non_placeholder_count = len(images_below_500px) - placeholder_count
        if non_placeholder_count > 0:
            print(f"\n⚠️  WARNING: {non_placeholder_count} product(s) have images below 500px (no placeholder configured):")
            for item in images_below_500px:
                if not item.get('used_placeholder'):
                    print(f"  - UPC {item['upc']}: {item['title'][:50]}")
                    print(f"    Image dimension: {item['dimension']}px (need ≥500px)")
                    print(f"    URL: {item['url']}")
            print("\n⚠️  These products may be rejected when uploading to eBay.")

def main():
    try:
        config = load_config()
        generate_csv(config)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
