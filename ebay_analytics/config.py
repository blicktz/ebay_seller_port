"""
Configuration loader for eBay Seller Analytics.

Loads configuration from .env file and provides validation and type conversion.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv


class Config:
    """Configuration manager for eBay Analytics."""

    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize configuration from .env file.

        Args:
            env_file: Path to .env file (defaults to .env in current directory)
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        self._validate_required_config()

    def _validate_required_config(self):
        """Validate that all required configuration is present."""
        required_vars = ['EBAY_ACCESS_TOKEN']

        missing = []
        for var in required_vars:
            if not os.getenv(var):
                missing.append(var)

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\\n"
                f"Please set these in your .env file or environment."
            )

    # eBay API Configuration
    @property
    def ebay_access_token(self) -> str:
        """Get eBay API access token."""
        return os.getenv('EBAY_ACCESS_TOKEN', '')

    @property
    def ebay_marketplace_id(self) -> str:
        """Get eBay marketplace ID (default: EBAY_US)."""
        return os.getenv('EBAY_MARKETPLACE_ID', 'EBAY_US')

    # Database Configuration
    @property
    def db_path(self) -> str:
        """Get database file path."""
        return os.getenv('DB_PATH', 'data/ebay_analytics.db')

    # Sold Listings Configuration
    @property
    def sold_items_lookback_days(self) -> int:
        """Get number of days to look back for sold items (default: 90)."""
        return int(os.getenv('SOLD_ITEMS_LOOKBACK_DAYS', '90'))

    @property
    def sync_sold_items_enabled(self) -> bool:
        """Check if sold items syncing is enabled (default: True)."""
        value = os.getenv('SYNC_SOLD_ITEMS_ENABLED', 'true').lower()
        return value in ('true', '1', 'yes', 'on')

    # Date Range Configuration
    @property
    def default_start_date(self) -> Optional[str]:
        """Get default start date in YYYYMMDD format."""
        return os.getenv('DEFAULT_START_DATE')

    @property
    def default_end_date(self) -> Optional[str]:
        """Get default end date in YYYYMMDD format."""
        return os.getenv('DEFAULT_END_DATE')

    # API Configuration
    @property
    def api_max_retries(self) -> int:
        """Get maximum API retry attempts (default: 3)."""
        return int(os.getenv('API_MAX_RETRIES', '3'))

    @property
    def api_retry_delay(self) -> float:
        """Get API retry delay in seconds (default: 2.0)."""
        return float(os.getenv('API_RETRY_DELAY', '2.0'))

    @property
    def api_timeout(self) -> int:
        """Get API request timeout in seconds (default: 30)."""
        return int(os.getenv('API_TIMEOUT', '30'))

    @property
    def api_rate_limit_max_calls(self) -> int:
        """Get maximum API calls allowed in time window (default: 50)."""
        return int(os.getenv('API_RATE_LIMIT_MAX_CALLS', '50'))

    @property
    def api_rate_limit_window(self) -> int:
        """Get rate limit time window in seconds (default: 60)."""
        return int(os.getenv('API_RATE_LIMIT_WINDOW', '60'))

    @property
    def api_call_delay_seconds(self) -> float:
        """Get delay between API calls in seconds for day-by-day syncing (default: 5.0)."""
        return float(os.getenv('API_CALL_DELAY_SECONDS', '5.0'))

    @property
    def user_timezone(self) -> str:
        """Get user's timezone for date conversion (default: America/Los_Angeles for PST/PDT)."""
        return os.getenv('USER_TIMEZONE', 'America/Los_Angeles')

    # Batching Configuration
    @property
    def sold_items_batch_size(self) -> int:
        """Get batch size for sold items queries (default: 200)."""
        return int(os.getenv('SOLD_ITEMS_BATCH_SIZE', '200'))


class DateRangeParser:
    """Utility for parsing and converting date ranges."""

    @staticmethod
    def parse_compact_date(date_str: str) -> datetime:
        """
        Parse YYYYMMDD format date string to datetime.

        Args:
            date_str: Date in YYYYMMDD format (e.g., '20260225')

        Returns:
            datetime object

        Raises:
            ValueError: If date format is invalid
        """
        try:
            return datetime.strptime(date_str, '%Y%m%d')
        except ValueError as e:
            raise ValueError(f"Invalid date format '{date_str}'. Expected YYYYMMDD format.") from e

    @staticmethod
    def parse_iso_date(date_str: str) -> datetime:
        """
        Parse ISO 8601 format date string to datetime.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            datetime object

        Raises:
            ValueError: If date format is invalid
        """
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError as e:
            raise ValueError(f"Invalid date format '{date_str}'. Expected YYYY-MM-DD format.") from e

    @staticmethod
    def to_compact_format(dt: datetime) -> str:
        """
        Convert datetime to YYYYMMDD format.

        Args:
            dt: datetime object

        Returns:
            Date string in YYYYMMDD format
        """
        return dt.strftime('%Y%m%d')

    @staticmethod
    def to_iso_format(dt: datetime) -> str:
        """
        Convert datetime to YYYY-MM-DD format.

        Args:
            dt: datetime object

        Returns:
            Date string in YYYY-MM-DD format
        """
        return dt.strftime('%Y-%m-%d')

    @staticmethod
    def to_iso8601_with_time(dt: datetime) -> str:
        """
        Convert datetime to ISO 8601 format with timezone (for Fulfillment API).

        Args:
            dt: datetime object (timezone-aware or naive)

        Returns:
            Date string in ISO 8601 UTC format (e.g., '2026-02-25T00:00:00.000Z')
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            # Convert timezone-aware datetime to UTC before formatting
            dt = dt.astimezone(timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')

    @staticmethod
    def get_date_range_last_n_days(days: int = 7) -> Tuple[str, str]:
        """
        Get date range for the last N days in YYYYMMDD format.

        Args:
            days: Number of days to look back

        Returns:
            Tuple of (start_date, end_date) in YYYYMMDD format
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        return (
            DateRangeParser.to_compact_format(start_date),
            DateRangeParser.to_compact_format(end_date)
        )

    @staticmethod
    def build_compact_range_string(start: str, end: str) -> str:
        """
        Build date range string for Analytics API filter.

        Args:
            start: Start date in YYYYMMDD format
            end: End date in YYYYMMDD format

        Returns:
            Date range string in format [YYYYMMDD..YYYYMMDD]

        Example:
            >>> build_compact_range_string('20260201', '20260225')
            '[20260201..20260225]'
        """
        return f"[{start}..{end}]"

    @staticmethod
    def build_iso8601_range_string(start_dt: datetime, end_dt: datetime) -> str:
        """
        Build ISO 8601 date range string for Fulfillment API filter.

        Args:
            start_dt: Start datetime
            end_dt: End datetime

        Returns:
            Date range string in format [ISO8601..ISO8601]

        Example:
            '[2026-02-01T00:00:00.000Z..2026-02-25T23:59:59.999Z]'
        """
        start_str = DateRangeParser.to_iso8601_with_time(start_dt)
        # Set end time to end of day
        end_dt_eod = end_dt.replace(hour=23, minute=59, second=59, microsecond=999000)
        end_str = DateRangeParser.to_iso8601_with_time(end_dt_eod)

        return f"[{start_str}..{end_str}]"


def load_config(env_file: Optional[str] = None) -> Config:
    """
    Load configuration from .env file.

    Args:
        env_file: Optional path to .env file

    Returns:
        Config object

    Raises:
        ValueError: If required configuration is missing
    """
    return Config(env_file)


if __name__ == "__main__":
    # Test configuration loading
    print("Testing configuration loading...")

    try:
        config = load_config()
        print(f"✓ Configuration loaded successfully")
        print(f"  Marketplace: {config.ebay_marketplace_id}")
        print(f"  Database: {config.db_path}")
        print(f"  Sold items lookback: {config.sold_items_lookback_days} days")
        print(f"  Sold items enabled: {config.sync_sold_items_enabled}")
        print(f"  API max retries: {config.api_max_retries}")

        print("\\nTesting date range parser...")
        start, end = DateRangeParser.get_date_range_last_n_days(7)
        print(f"  Last 7 days: {start} to {end}")

        range_str = DateRangeParser.build_compact_range_string(start, end)
        print(f"  Compact range: {range_str}")

        dt = DateRangeParser.parse_compact_date(start)
        iso_str = DateRangeParser.to_iso_format(dt)
        print(f"  ISO format: {iso_str}")

        iso8601 = DateRangeParser.to_iso8601_with_time(dt)
        print(f"  ISO 8601 with time: {iso8601}")

    except ValueError as e:
        print(f"✗ Configuration error: {e}")
