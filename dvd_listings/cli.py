"""
Command-line interface for DVD listing automation.

Provides commands for:
- Initializing the catalog database
- Looking up UPCs from files
- Viewing cached products
- Exporting results
- Managing the cache
"""

import click
import sys
from pathlib import Path
from datetime import datetime

from .config import load_dvd_config
from .db.schema import init_database, get_database_info, clean_expired_cache
from .db.repository import CatalogRepository
from .services.catalog_lookup import CatalogLookupService


@click.group()
@click.version_option(version='0.1.0')
def cli():
    """
    DVD Listing Automation Tool

    Automates the process of looking up DVD product information
    from eBay's Catalog API using UPC codes.
    """
    pass


@cli.command('init-db')
@click.option(
    '--db-path',
    default=None,
    help='Database path (defaults to DVD_DB_PATH from .env)'
)
def init_db_command(db_path):
    """Initialize the DVD catalog database."""
    try:
        config = load_dvd_config()
        db_path = db_path or config.dvd_db_path

        click.echo(f"Initializing database: {db_path}")
        init_database(db_path)

        click.echo()
        click.echo(click.style("✓ Database initialized successfully", fg='green'))

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command('lookup-upcs')
@click.option(
    '--file',
    '-f',
    'file_path',
    required=True,
    type=click.Path(exists=True),
    help='Path to file containing UPCs (CSV or text)'
)
@click.option(
    '--file-type',
    type=click.Choice(['csv', 'txt'], case_sensitive=False),
    help='File type (auto-detected if not specified)'
)
@click.option(
    '--upc-column',
    default='upc',
    help='Column name for UPCs in CSV (default: upc)'
)
@click.option(
    '--batch-size',
    default=None,
    type=int,
    help='Number of UPCs per API request (default from config)'
)
@click.option(
    '--force-refresh',
    is_flag=True,
    help='Ignore cache and fetch fresh data'
)
@click.option(
    '--export',
    type=click.Path(),
    help='Export results to CSV file'
)
def lookup_upcs_command(file_path, file_type, upc_column, batch_size, force_refresh, export):
    """
    Look up UPCs from a file using eBay Catalog API.

    Supports both CSV and text files. For CSV files, specify the
    column name containing UPCs. For text files, one UPC per line.

    Examples:

      # Look up UPCs from CSV file:
      dvd-cli lookup-upcs --file upcs.csv

      # Look up from text file and export results:
      dvd-cli lookup-upcs --file upcs.txt --export results.csv

      # Force refresh (ignore cache):
      dvd-cli lookup-upcs --file upcs.csv --force-refresh
    """
    try:
        config = load_dvd_config()

        # Create service
        service = CatalogLookupService(
            config=config,
            db_path=config.dvd_db_path,
            batch_size=batch_size or config.dvd_catalog_batch_size
        )

        click.echo(click.style("DVD Catalog Lookup", fg='cyan', bold=True))
        click.echo("=" * 60)
        click.echo()

        # Perform lookup
        summary = service.lookup_from_file(
            filepath=file_path,
            file_type=file_type,
            upc_column=upc_column,
            force_refresh=force_refresh
        )

        # Display summary
        click.echo()
        click.echo(service.get_summary_report(summary))

        # Export if requested
        if export or config.dvd_auto_export:
            export_path = export or Path(config.dvd_export_path) / f"dvd_catalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            click.echo()
            click.echo(f"Exporting results to: {export_path}")
            count = service.export_results_to_csv(str(export_path))
            click.echo(click.style(f"✓ Exported {count} products", fg='green'))

    except FileNotFoundError as e:
        click.echo(click.style(f"✗ File not found: {e}", fg='red'), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg='red'), err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command('show-cache')
@click.option(
    '--upc',
    help='Show details for specific UPC'
)
@click.option(
    '--limit',
    default=10,
    type=int,
    help='Number of products to show (default: 10)'
)
def show_cache_command(upc, limit):
    """View cached product data."""
    try:
        config = load_dvd_config()
        repo = CatalogRepository(config.dvd_db_path)

        if upc:
            # Show all products for this UPC (may be multiple editions)
            products = repo.get_products_by_upc(upc)
            if products:
                if len(products) == 1:
                    product = products[0]
                    click.echo(click.style(f"Product: {product.title}", fg='cyan', bold=True))
                    click.echo(f"  UPC: {product.upc}")
                    click.echo(f"  ePID: {product.epid}")
                    click.echo(f"  Brand: {product.brand or 'N/A'}")

                    if product.dvd_aspects:
                        click.echo(f"  Format: {product.dvd_aspects.format or 'N/A'}")
                        click.echo(f"  Genre: {product.dvd_aspects.genre or 'N/A'}")
                        click.echo(f"  Release Year: {product.dvd_aspects.release_year or 'N/A'}")
                        if product.dvd_aspects.actors:
                            click.echo(f"  Actors: {', '.join(product.dvd_aspects.actors[:3])}")
                        if product.dvd_aspects.directors:
                            click.echo(f"  Directors: {', '.join(product.dvd_aspects.directors)}")
                        click.echo(f"  Studio: {product.dvd_aspects.studio or 'N/A'}")
                        click.echo(f"  Rating: {product.dvd_aspects.rating or 'N/A'}")

                    click.echo(f"  Fetched: {product.fetched_at}")
                    click.echo(f"  Expires: {product.cache_expires_at}")
                else:
                    click.echo(click.style(f"Found {len(products)} editions for UPC {upc}:", fg='cyan', bold=True))
                    click.echo()
                    for idx, product in enumerate(products, 1):
                        click.echo(click.style(f"Edition {idx}: {product.title}", fg='yellow', bold=True))
                        click.echo(f"  ePID: {product.epid}")
                        click.echo(f"  Brand: {product.brand or 'N/A'}")
                        if product.dvd_aspects:
                            click.echo(f"  Release Year: {product.dvd_aspects.release_year or 'N/A'}")
                            if product.dvd_aspects.actors:
                                click.echo(f"  Actors: {', '.join(product.dvd_aspects.actors[:3])}")
                        click.echo()
            else:
                click.echo(click.style(f"✗ UPC not found in cache: {upc}", fg='yellow'))
        else:
            # Show recent products
            products = repo.get_all_products(limit=limit)

            if products:
                click.echo(click.style(f"Recent Products (showing {len(products)}):", fg='cyan', bold=True))
                click.echo()
                for product in products:
                    click.echo(f"  {product.upc} - {product.title}")
            else:
                click.echo(click.style("No products in cache", fg='yellow'))

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command('list-not-found')
@click.option(
    '--output',
    type=click.Path(),
    help='Export not-found UPCs to file'
)
def list_not_found_command(output):
    """List UPCs that were not found in eBay catalog."""
    try:
        config = load_dvd_config()
        repo = CatalogRepository(config.dvd_db_path)

        not_found = repo.get_not_found_upcs()

        if not_found:
            click.echo(click.style(f"UPCs Not Found ({len(not_found)}):", fg='yellow', bold=True))
            for upc in not_found:
                click.echo(f"  {upc}")

            if output:
                with open(output, 'w') as f:
                    for upc in not_found:
                        f.write(f"{upc}\n")
                click.echo()
                click.echo(click.style(f"✓ Saved to {output}", fg='green'))
        else:
            click.echo(click.style("No UPCs marked as not found", fg='green'))

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command('export-results')
@click.option(
    '--output',
    '-o',
    required=True,
    type=click.Path(),
    help='Output CSV file path'
)
def export_results_command(output):
    """Export cached products to CSV file."""
    try:
        config = load_dvd_config()
        service = CatalogLookupService(config=config, db_path=config.dvd_db_path)

        count = service.export_results_to_csv(output)

        if count > 0:
            click.echo(click.style(f"✓ Exported {count} products to {output}", fg='green'))
        else:
            click.echo(click.style("No products to export", fg='yellow'))

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command('stats')
def stats_command():
    """Show database statistics."""
    try:
        config = load_dvd_config()
        info = get_database_info(config.dvd_db_path)

        if not info['exists']:
            click.echo(click.style("Database not initialized", fg='yellow'))
            click.echo("Run 'dvd-cli init-db' to create the database")
            return

        click.echo(click.style("DVD Catalog Statistics", fg='cyan', bold=True))
        click.echo("=" * 60)
        click.echo(f"Products cached: {info['product_count']}")
        click.echo(f"Total lookups: {info['lookup_count']}")
        click.echo(f"Not found: {info['not_found_count']}")
        click.echo(f"Expired entries: {info.get('expired_count', 0)}")
        if info.get('last_fetch'):
            click.echo(f"Last fetch: {info['last_fetch']}")

        # Get detailed stats from repository
        repo = CatalogRepository(config.dvd_db_path)
        stats = repo.get_statistics()

        if stats.get('genre_distribution'):
            click.echo()
            click.echo("Top Genres:")
            for genre, count in stats['genre_distribution']:
                click.echo(f"  {genre}: {count}")

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg='red'), err=True)
        sys.exit(1)


@cli.command('clean-cache')
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be deleted without actually deleting'
)
def clean_cache_command(dry_run):
    """Remove expired entries from cache."""
    try:
        config = load_dvd_config()

        if dry_run:
            click.echo("DRY RUN - No changes will be made")
            click.echo()

        count = clean_expired_cache(config.dvd_db_path, dry_run=dry_run)

        if count > 0:
            if dry_run:
                click.echo(click.style(f"Would delete {count} expired entries", fg='yellow'))
            else:
                click.echo(click.style(f"✓ Deleted {count} expired entries", fg='green'))
        else:
            click.echo(click.style("No expired entries found", fg='green'))

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg='red'), err=True)
        sys.exit(1)


def main():
    """Entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()
