"""
Data models for eBay catalog products.

These models represent the structure of product data returned from
the eBay Catalog API and stored in the local database.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import json


@dataclass
class DVDAspects:
    """DVD-specific product aspects extracted from catalog data."""

    actors: List[str] = field(default_factory=list)
    directors: List[str] = field(default_factory=list)
    studio: Optional[str] = None
    release_year: Optional[str] = None
    format: Optional[str] = None  # DVD, Blu-ray, etc.
    genre: Optional[str] = None
    rating: Optional[str] = None  # MPAA rating
    region_code: Optional[str] = None
    sub_genre: Optional[str] = None
    edition: Optional[str] = None  # Special edition, Director's cut, etc.

    @classmethod
    def from_aspects_array(cls, aspects: List[Dict[str, Any]]) -> 'DVDAspects':
        """
        Parse DVD aspects from eBay Catalog API aspects array.

        Args:
            aspects: Array of aspect objects from API response
                    [{'localizedName': 'Actors', 'localizedValues': ['Tom Hanks']}, ...]

        Returns:
            DVDAspects instance
        """
        aspect_map = {}
        for aspect in aspects:
            name = aspect.get('localizedName', '')
            values = aspect.get('localizedValues', [])
            if values:
                aspect_map[name] = values

        return cls(
            actors=aspect_map.get('Actors', aspect_map.get('Actor', [])),
            directors=aspect_map.get('Directors', aspect_map.get('Director', [])),
            studio=aspect_map.get('Studio', [None])[0],
            release_year=aspect_map.get('Release Year', [None])[0],
            format=aspect_map.get('Format', [None])[0],
            genre=aspect_map.get('Genre', [None])[0],
            rating=aspect_map.get('Rating', aspect_map.get('MPAA Rating', [None]))[0],
            region_code=aspect_map.get('Region Code', [None])[0],
            sub_genre=aspect_map.get('Sub-Genre', [None])[0],
            edition=aspect_map.get('Edition', [None])[0],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'actors': self.actors,
            'directors': self.directors,
            'studio': self.studio,
            'release_year': self.release_year,
            'format': self.format,
            'genre': self.genre,
            'rating': self.rating,
            'region_code': self.region_code,
            'sub_genre': self.sub_genre,
            'edition': self.edition,
        }


@dataclass
class CatalogProduct:
    """Represents a product from eBay's catalog."""

    # Identifiers
    epid: str
    upc: str
    all_gtins: List[str] = field(default_factory=list)

    # Product info
    title: str = ""
    brand: Optional[str] = None

    # Media type (DVD, CD, VHS)
    media_type: str = "DVD"

    # Images
    primary_image_url: Optional[str] = None
    additional_images: List[str] = field(default_factory=list)

    # DVD-specific aspects
    dvd_aspects: Optional[DVDAspects] = None

    # Full aspects for flexibility
    aspects_json: Optional[str] = None

    # Category info
    primary_category_id: Optional[str] = None
    category_name: Optional[str] = None

    # URLs
    product_api_url: Optional[str] = None
    product_web_url: Optional[str] = None

    # Metadata
    fetched_at: Optional[datetime] = None
    cache_expires_at: Optional[datetime] = None

    @classmethod
    def from_api_response(
        cls,
        product_summary: Dict[str, Any],
        media_type: str = 'DVD'
    ) -> 'CatalogProduct':
        """
        Create CatalogProduct from eBay Catalog API product summary.

        Args:
            product_summary: Product summary object from API search results
            media_type: Media type (DVD, CD, VHS) - defaults to DVD

        Returns:
            CatalogProduct instance
        """
        # Extract GTINs
        all_gtins = []
        all_gtins.extend(product_summary.get('gtin', []))
        all_gtins.extend(product_summary.get('upc', []))
        all_gtins.extend(product_summary.get('ean', []))
        all_gtins.extend(product_summary.get('isbn', []))
        all_gtins = list(set(all_gtins))  # Remove duplicates

        # Primary UPC (first UPC or first GTIN)
        upc_raw = (
            product_summary.get('upc', [None])[0]
            or product_summary.get('gtin', [None])[0]
            or ''
        )

        # Normalize UPC to 12-digit format (strip leading zeros for consistency)
        if upc_raw:
            upc = upc_raw.lstrip('0').zfill(12) if upc_raw.lstrip('0') else '0'.zfill(12)
        else:
            upc = ''

        # Extract images
        primary_image = product_summary.get('image', {})
        primary_image_url = primary_image.get('imageUrl') if primary_image else None

        additional_images = [
            img.get('imageUrl')
            for img in product_summary.get('additionalImages', [])
            if img.get('imageUrl')
        ]

        # Parse DVD aspects
        aspects_array = product_summary.get('aspects', [])
        dvd_aspects = DVDAspects.from_aspects_array(aspects_array) if aspects_array else None

        # Store full aspects as JSON for flexibility
        aspects_json = json.dumps(aspects_array) if aspects_array else None

        # Media type is passed as parameter (from MEDIA_TYPE env var)
        # No auto-detection - user explicitly sets what they're looking up

        return cls(
            epid=product_summary.get('epid', ''),
            upc=upc,
            all_gtins=all_gtins,
            title=product_summary.get('title', ''),
            brand=product_summary.get('brand'),
            media_type=media_type,
            primary_image_url=primary_image_url,
            additional_images=additional_images,
            dvd_aspects=dvd_aspects,
            aspects_json=aspects_json,
            product_api_url=product_summary.get('productHref'),
            product_web_url=product_summary.get('productWebUrl'),
            fetched_at=datetime.now(),
        )

    def to_db_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database storage.

        Returns:
            Dictionary with database column names as keys
        """
        return {
            'epid': self.epid,
            'upc': self.upc,
            'all_gtins': json.dumps(self.all_gtins),
            'title': self.title,
            'brand': self.brand,
            'media_type': self.media_type,
            'primary_image_url': self.primary_image_url,
            'additional_images': json.dumps(self.additional_images),
            'actors': json.dumps(self.dvd_aspects.actors) if self.dvd_aspects else None,
            'directors': json.dumps(self.dvd_aspects.directors) if self.dvd_aspects else None,
            'studio': self.dvd_aspects.studio if self.dvd_aspects else None,
            'release_year': self.dvd_aspects.release_year if self.dvd_aspects else None,
            'format': self.dvd_aspects.format if self.dvd_aspects else None,
            'genre': self.dvd_aspects.genre if self.dvd_aspects else None,
            'rating': self.dvd_aspects.rating if self.dvd_aspects else None,
            'region_code': self.dvd_aspects.region_code if self.dvd_aspects else None,
            'aspects_json': self.aspects_json,
            'primary_category_id': self.primary_category_id,
            'category_name': self.category_name,
            'product_api_url': self.product_api_url,
            'product_web_url': self.product_web_url,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
            'cache_expires_at': self.cache_expires_at.isoformat() if self.cache_expires_at else None,
            'fetch_source': 'catalog_api',
        }

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> 'CatalogProduct':
        """
        Create CatalogProduct from database row.

        Args:
            row: Database row as dictionary

        Returns:
            CatalogProduct instance
        """
        # Parse JSON fields
        all_gtins = json.loads(row.get('all_gtins', '[]'))
        additional_images = json.loads(row.get('additional_images', '[]'))

        # Reconstruct DVD aspects
        dvd_aspects = None
        if row.get('actors') or row.get('directors') or row.get('studio'):
            dvd_aspects = DVDAspects(
                actors=json.loads(row.get('actors', '[]')),
                directors=json.loads(row.get('directors', '[]')),
                studio=row.get('studio'),
                release_year=row.get('release_year'),
                format=row.get('format'),
                genre=row.get('genre'),
                rating=row.get('rating'),
                region_code=row.get('region_code'),
            )

        # Parse datetime fields
        fetched_at = None
        if row.get('fetched_at'):
            fetched_at = datetime.fromisoformat(row['fetched_at'])

        cache_expires_at = None
        if row.get('cache_expires_at'):
            cache_expires_at = datetime.fromisoformat(row['cache_expires_at'])

        return cls(
            epid=row.get('epid', ''),
            upc=row.get('upc', ''),
            all_gtins=all_gtins,
            title=row.get('title', ''),
            brand=row.get('brand'),
            media_type=row.get('media_type', 'DVD'),
            primary_image_url=row.get('primary_image_url'),
            additional_images=additional_images,
            dvd_aspects=dvd_aspects,
            aspects_json=row.get('aspects_json'),
            primary_category_id=row.get('primary_category_id'),
            category_name=row.get('category_name'),
            product_api_url=row.get('product_api_url'),
            product_web_url=row.get('product_web_url'),
            fetched_at=fetched_at,
            cache_expires_at=cache_expires_at,
        )
