"""
Command-line interface for eBay Seller Analytics.

Provides commands for database initialization, data syncing, and report generation.
"""

import click
from datetime import datetime, timedelta
from pathlib import Path

from .config import load_config, DateRangeParser
from .db.schema import init_database, verify_schema
from .services.metadata_sync import MetadataSyncService
from .services.sold_items_sync import SoldItemsSyncService
from .services.traffic_sync import TrafficSyncService
from .services.report_generator import ReportGenerator


@click.group()
@click.version_option(version='1.0.0', prog_name='eBay Seller Analytics')
def cli():
    """eBay Seller Analytics - Traffic Report Generator"""
    pass


@cli.command()
@click.option(
    '--db-path',
    default='data/ebay_analytics.db',
    help='Path to SQLite database file'
)
def init_db(db_path):
    """Initialize database schema."""
    click.echo(f"\n🗄️  Initializing database at: {db_path}\n")

    try:
        conn = init_database(db_path)
        conn.close()

        click.echo("\n✓ Database initialization completed successfully")

    except Exception as e:
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option(
    '--marketplace',
    default=None,
    help='eBay marketplace ID (default: from config)'
)
def sync_metadata(marketplace):
    """Sync listing metadata from Inventory API."""
    try:
        config = load_config()

        if marketplace:
            # Override config marketplace
            import os
            os.environ['EBAY_MARKETPLACE_ID'] = marketplace
            config = load_config()

        service = MetadataSyncService(config)
        stats = service.sync_metadata()
        service.close()

        click.echo(f"✓ Synced {stats['items_updated']} listings")

    except Exception as e:
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option(
    '--days-back',
    type=int,
    default=None,
    help='Number of days to look back (default: from config, max: 90)'
)
@click.option(
    '--marketplace',
    default=None,
    help='eBay marketplace ID (default: from config)'
)
def sync_sold_items(days_back, marketplace):
    """Sync sold items from Fulfillment API."""
    try:
        config = load_config()

        if marketplace:
            import os
            os.environ['EBAY_MARKETPLACE_ID'] = marketplace
            config = load_config()

        service = SoldItemsSyncService(config)
        stats = service.sync_sold_items(days_back=days_back)
        service.close()

        click.echo(f"✓ Synced {stats['unique_items']} unique sold items")
        click.echo(f"  New items cached: {stats['new_items_cached']}")

    except Exception as e:
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option(
    '--start-date',
    required=True,
    help='Start date in YYYYMMDD format (e.g., 20260201)'
)
@click.option(
    '--end-date',
    required=True,
    help='End date in YYYYMMDD format (e.g., 20260225)'
)
@click.option(
    '--marketplace',
    default=None,
    help='eBay marketplace ID (default: from config)'
)
@click.option(
    '--include-sold/--no-include-sold',
    default=True,
    help='Include sold listings (default: True)'
)
def sync_traffic(start_date, end_date, marketplace, include_sold):
    """Sync traffic data from Analytics API."""
    try:
        # Validate date format
        DateRangeParser.parse_compact_date(start_date)
        DateRangeParser.parse_compact_date(end_date)

        config = load_config()

        if marketplace:
            import os
            os.environ['EBAY_MARKETPLACE_ID'] = marketplace
            config = load_config()

        service = TrafficSyncService(config)
        stats = service.sync_traffic(
            start_date=start_date,
            end_date=end_date,
            include_sold=include_sold
        )
        service.close()

        click.echo(f"✓ Synced {stats['total_records']} total records")
        click.echo(f"  Active listings: {stats['active_listings']}")
        click.echo(f"  Sold listings: {stats['sold_listings']}")

    except ValueError as e:
        click.echo(f"\n✗ Invalid date format: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option(
    '--start-date',
    required=True,
    help='Start date in YYYYMMDD format (e.g., 20260201)'
)
@click.option(
    '--end-date',
    required=True,
    help='End date in YYYYMMDD format (e.g., 20260225)'
)
@click.option(
    '--output',
    required=True,
    help='Output CSV file path (e.g., reports/traffic_report.csv)'
)
def generate_report(start_date, end_date, output):
    """Generate CSV traffic report."""
    try:
        # Validate date format
        DateRangeParser.parse_compact_date(start_date)
        DateRangeParser.parse_compact_date(end_date)

        config = load_config()
        generator = ReportGenerator(config)

        stats = generator.generate_report(
            start_date=start_date,
            end_date=end_date,
            output_path=output
        )

        click.echo(f"✓ Generated report with {stats['rows_generated']} rows")
        click.echo(f"  Output: {stats['output_path']}")

    except ValueError as e:
        click.echo(f"\n✗ Invalid date format: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option(
    '--start-date',
    default=None,
    help='Start date in YYYYMMDD format (default: 7 days ago)'
)
@click.option(
    '--end-date',
    default=None,
    help='End date in YYYYMMDD format (default: today)'
)
@click.option(
    '--output',
    default=None,
    help='Output CSV file path (default: reports/traffic_report_<timestamp>.csv)'
)
@click.option(
    '--days-back-sold',
    type=int,
    default=90,
    help='Days to look back for sold items (default: 90)'
)
def full_sync(start_date, end_date, output, days_back_sold):
    """Run full sync: metadata + sold items + traffic + report."""
    try:
        config = load_config()

        # Calculate default dates if not provided
        if not start_date or not end_date:
            start, end = DateRangeParser.get_date_range_last_n_days(7)
            start_date = start_date or start
            end_date = end_date or end

        # Generate default output path if not provided
        if not output:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output = f"reports/traffic_report_{timestamp}.csv"

        click.echo(f"\n{'='*60}")
        click.echo(f"FULL SYNC")
        click.echo(f"{'='*60}\n")
        click.echo(f"Date range: {start_date} to {end_date}")
        click.echo(f"Output: {output}")
        click.echo(f"Sold items lookback: {days_back_sold} days")
        click.echo()

        # Step 1: Sync metadata
        click.echo(f"📦 Step 1/4: Syncing metadata...")
        meta_service = MetadataSyncService(config)
        meta_stats = meta_service.sync_metadata()
        meta_service.close()
        click.echo(f"   ✓ Synced {meta_stats['items_updated']} listings\n")

        # Step 2: Sync sold items
        click.echo(f"🛒 Step 2/4: Syncing sold items...")
        sold_service = SoldItemsSyncService(config)
        sold_stats = sold_service.sync_sold_items(days_back=days_back_sold)
        sold_service.close()
        click.echo(f"   ✓ Synced {sold_stats['unique_items']} sold items\n")

        # Step 3: Sync traffic
        click.echo(f"📊 Step 3/4: Syncing traffic data...")
        traffic_service = TrafficSyncService(config)
        traffic_stats = traffic_service.sync_traffic(
            start_date=start_date,
            end_date=end_date,
            include_sold=True
        )
        traffic_service.close()
        click.echo(f"   ✓ Synced {traffic_stats['total_records']} traffic records\n")

        # Step 4: Generate report
        click.echo(f"📝 Step 4/4: Generating report...")
        generator = ReportGenerator(config)
        report_stats = generator.generate_report(
            start_date=start_date,
            end_date=end_date,
            output_path=output
        )
        click.echo(f"   ✓ Generated report with {report_stats['rows_generated']} rows\n")

        click.echo(f"{'='*60}")
        click.echo(f"✓ FULL SYNC COMPLETED")
        click.echo(f"{'='*60}\n")
        click.echo(f"Report: {output}")

    except Exception as e:
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option(
    '--db-path',
    default='data/ebay_analytics.db',
    help='Path to SQLite database file'
)
def verify(db_path):
    """Verify database schema."""
    click.echo(f"\n🔍 Verifying database schema...\n")

    try:
        is_valid = verify_schema(db_path)

        if is_valid:
            click.echo("\n✓ Database schema is valid")
        else:
            click.echo("\n✗ Database schema is invalid", err=True)
            raise click.Abort()

    except Exception as e:
        click.echo(f"\n✗ Error: {e}", err=True)
        raise click.Abort()


if __name__ == '__main__':
    cli()
