"""
Configuration for DVD Listing Automation.

Extends the base ebay_analytics Config with DVD-specific settings.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path to import ebay_analytics
sys.path.insert(0, str(Path(__file__).parent.parent))

from ebay_analytics.config import Config as BaseConfig


class DVDConfig(BaseConfig):
    """Configuration manager for DVD listing automation."""

    # DVD-specific configuration properties

    @property
    def dvd_catalog_batch_size(self) -> int:
        """Get batch size for catalog API requests (default: 20)."""
        return int(os.getenv('DVD_CATALOG_BATCH_SIZE', '20'))

    @property
    def dvd_cache_expiry_days(self) -> int:
        """Get cache expiry period in days (default: 30)."""
        return int(os.getenv('DVD_CACHE_EXPIRY_DAYS', '30'))

    @property
    def dvd_db_path(self) -> str:
        """Get DVD catalog database path (default: data/dvd_catalog.db)."""
        return os.getenv('DVD_DB_PATH', 'data/dvd_catalog.db')

    @property
    def dvd_use_cache(self) -> bool:
        """Check if catalog cache should be used (default: True)."""
        value = os.getenv('DVD_USE_CACHE', 'true').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def dvd_auto_export(self) -> bool:
        """Check if results should be auto-exported to CSV (default: False)."""
        value = os.getenv('DVD_AUTO_EXPORT', 'false').lower()
        return value in ('true', '1', 'yes', 'on')

    @property
    def dvd_export_path(self) -> str:
        """Get default export path for CSV results (default: data/dvd_exports)."""
        return os.getenv('DVD_EXPORT_PATH', 'data/dvd_exports')


def load_dvd_config(env_file: str = None) -> DVDConfig:
    """
    Load DVD configuration from .env file.

    Args:
        env_file: Optional path to .env file

    Returns:
        DVDConfig object

    Raises:
        ValueError: If required configuration is missing

    Example:
        >>> config = load_dvd_config()
        >>> print(config.dvd_catalog_batch_size)
        20
    """
    return DVDConfig(env_file)


if __name__ == "__main__":
    """Test DVD configuration loading."""
    print("Testing DVD Configuration...")
    print("=" * 60)

    try:
        config = load_dvd_config()

        print("✓ Configuration loaded successfully")
        print()
        print("eBay API Settings:")
        print(f"  Marketplace: {config.ebay_marketplace_id}")
        print(f"  Access Token: {'*' * 20}{'...' if config.ebay_access_token else 'NOT SET'}")
        print()
        print("DVD Catalog Settings:")
        print(f"  Batch Size: {config.dvd_catalog_batch_size}")
        print(f"  Cache Expiry: {config.dvd_cache_expiry_days} days")
        print(f"  Database Path: {config.dvd_db_path}")
        print(f"  Use Cache: {config.dvd_use_cache}")
        print(f"  Auto Export: {config.dvd_auto_export}")
        print(f"  Export Path: {config.dvd_export_path}")
        print()
        print("API Rate Limiting:")
        print(f"  Max Retries: {config.api_max_retries}")
        print(f"  Retry Delay: {config.api_retry_delay}s")
        print(f"  Timeout: {config.api_timeout}s")
        print(f"  Delay Between Batches: {config.api_call_delay_between_batches}s")

        print()
        print("✓ Configuration test completed successfully")

    except ValueError as e:
        print(f"✗ Configuration error: {e}")
        print("\nMake sure your .env file is set up correctly.")
