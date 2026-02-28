"""
Report generator service.

Generates CSV reports matching eBay's Listings Traffic Report format (29 columns).
Queries database, calculates derivative metrics, and exports to CSV.
"""

import csv
from typing import List, Dict, Any
from pathlib import Path
from ..db.repository import TrafficRepository, MetadataRepository
from ..db.schema import get_connection
from ..config import Config


class ReportGenerator:
    """Service for generating CSV traffic reports."""

    # 29 column headers matching eBay's format
    CSV_HEADERS = [
        "Listing title",
        "eBay item ID",
        "Item Start Date",
        "Category",
        "Current promoted listings status",
        "Quantity available",
        "Total impressions",
        "Click-through rate = Page views from eBay site/Total impressions",
        "Quantity sold",
        "% Top 20 Search Impressions",
        "Sales conversion rate = Quantity sold/Total page views",
        "Top 20 search slot impressions from promoted listings",
        "% change in top 20 search slot impressions from promoted listings",
        "Top 20 search slot organic impressions",
        "% change in top 20 search slot impressions",
        "Rest of search slot impressions",
        "Total Search Impressions",
        "Non-search promoted listings impressions",
        "% Change in non-search promoted listings impressions",
        "Non-search organic impressions",
        "% Change in non-search organic impressions",
        "Total Promoted Listings impressions (applies to eBay site only)",
        "Total Promoted Offsite impressions (applies to off-eBay only)",
        "Total organic impressions on eBay site",
        "Total page views",
        "Page views via promoted listings impressions on eBay site",
        "Page views via promoted listings Impressions from outside eBay (search engines, affilliates)",
        "Page views via organic impressions on eBay site",
        "Page views from organic impressions outside eBay (Includes page views from search engines)"
    ]

    def __init__(self, config: Config):
        """
        Initialize report generator.

        Args:
            config: Configuration object
        """
        self.config = config
        self.db_path = config.db_path

    def generate_report(
        self,
        start_date: str,
        end_date: str,
        output_path: str
    ) -> Dict[str, Any]:
        """
        Generate CSV report for date range.

        Args:
            start_date: Start date in YYYYMMDD format
            end_date: End date in YYYYMMDD format
            output_path: Path to output CSV file

        Returns:
            Statistics dictionary
        """
        print(f"\n{'='*60}")
        print(f"REPORT GENERATION")
        print(f"{'='*60}\n")

        # Convert YYYYMMDD to YYYY-MM-DD for database query
        start_date_db = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        end_date_db = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"

        print(f"Date range: {start_date_db} to {end_date_db}")
        print(f"Output file: {output_path}")
        print()

        # Query data from database
        print(f"📊 Querying database...")
        rows = self._query_report_data(start_date_db, end_date_db)
        print(f"   Retrieved {len(rows)} rows")
        print()

        if not rows:
            print(f"⚠ No data found for date range")
            return {
                'rows_generated': 0,
                'output_path': output_path
            }

        # Generate CSV
        print(f"📝 Writing CSV...")
        self._write_csv(rows, output_path)
        print(f"   ✓ CSV written successfully")
        print()

        print(f"✓ Report generation completed")
        print(f"  Output: {output_path}")
        print(f"  Rows: {len(rows)}")
        print(f"{'='*60}\n")

        return {
            'rows_generated': len(rows),
            'output_path': output_path
        }

    def _query_report_data(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Query report data with calculations.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of row dictionaries with all 29 columns
        """
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        # SQL query matching the 29-column format
        query = """
            SELECT
                m.title AS listing_title,
                m.item_id AS ebay_item_id,
                m.start_date AS item_start_date,
                m.category_name AS category,
                m.promoted_status AS current_promoted_status,

                -- Quantity available (0 for sold items)
                CASE
                    WHEN t.listing_status = 'sold' THEN 0
                    ELSE COALESCE(m.quantity_available, 0)
                END AS quantity_available,

                t.total_impressions AS total_impressions,

                -- CALCULATED: Click-through rate
                -- IMPORTANT: Using sum of view sources (CORRECT) instead of total_page_views (INCORRECT)
                CASE
                    WHEN t.total_impressions > 0
                    THEN ROUND((CAST((COALESCE(t.views_source_direct, 0) +
                                      COALESCE(t.views_source_off_ebay, 0) +
                                      COALESCE(t.views_source_other_ebay, 0) +
                                      COALESCE(t.views_source_search_results, 0) +
                                      COALESCE(t.views_source_store, 0)) AS REAL) / t.total_impressions) * 100, 2)
                    ELSE NULL
                END AS click_through_rate,

                t.transactions AS quantity_sold,

                NULL AS pct_top_20_search_impressions,

                -- CALCULATED: Sales conversion rate
                -- IMPORTANT: Using sum of view sources (CORRECT) instead of total_page_views (INCORRECT)
                CASE
                    WHEN (COALESCE(t.views_source_direct, 0) +
                          COALESCE(t.views_source_off_ebay, 0) +
                          COALESCE(t.views_source_other_ebay, 0) +
                          COALESCE(t.views_source_search_results, 0) +
                          COALESCE(t.views_source_store, 0)) > 0
                    THEN ROUND((CAST(t.transactions AS REAL) /
                                (COALESCE(t.views_source_direct, 0) +
                                 COALESCE(t.views_source_off_ebay, 0) +
                                 COALESCE(t.views_source_other_ebay, 0) +
                                 COALESCE(t.views_source_search_results, 0) +
                                 COALESCE(t.views_source_store, 0))) * 100, 2)
                    ELSE NULL
                END AS sales_conversion_rate,

                NULL AS top_20_promoted_impressions,
                NULL AS pct_change_top_20_promoted,
                NULL AS top_20_organic_impressions,
                NULL AS pct_change_top_20_organic,
                NULL AS rest_of_search_impressions,

                t.total_search_impressions AS total_search_impressions,

                -- CALCULATED: Non-search promoted impressions
                COALESCE(t.promoted_total_impressions, 0) - COALESCE(t.promoted_search_impressions, 0) AS non_search_promoted_impressions,

                NULL AS pct_change_non_search_promoted,

                -- CALCULATED: Non-search organic impressions
                COALESCE(t.organic_total_impressions, 0) - COALESCE(t.organic_search_impressions, 0) AS non_search_organic_impressions,

                NULL AS pct_change_non_search_organic,

                t.promoted_total_impressions AS total_promoted_impressions,
                NULL AS total_promoted_offsite_impressions,
                t.organic_total_impressions AS total_organic_impressions,

                -- CORRECTED: Sum of view sources (matches seller portal)
                -- Original t.total_page_views was INCORRECT and didn't match sum of sources
                (COALESCE(t.views_source_direct, 0) +
                 COALESCE(t.views_source_off_ebay, 0) +
                 COALESCE(t.views_source_other_ebay, 0) +
                 COALESCE(t.views_source_search_results, 0) +
                 COALESCE(t.views_source_store, 0)) AS total_page_views,

                t.promoted_page_views AS page_views_promoted_ebay,
                NULL AS page_views_promoted_offsite,
                t.organic_page_views AS page_views_organic_ebay,
                NULL AS page_views_organic_offsite

            FROM daily_traffic_facts t
            JOIN listings_metadata m ON t.item_id = m.item_id
            WHERE t.report_date BETWEEN ? AND ?
            ORDER BY t.listing_status DESC, t.report_date DESC, t.item_id
        """

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()
        conn.close()

        # Convert to list of dictionaries
        result = []
        for row in rows:
            result.append(dict(row))

        return result

    def _write_csv(self, rows: List[Dict[str, Any]], output_path: str) -> None:
        """
        Write rows to CSV file.

        Args:
            rows: List of row dictionaries
            output_path: Path to output CSV file
        """
        # Ensure output directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Write headers
            writer.writerow(self.CSV_HEADERS)

            # Write data rows
            for row in rows:
                csv_row = self._format_row_for_csv(row)
                writer.writerow(csv_row)

    def _format_row_for_csv(self, row: Dict[str, Any]) -> List[Any]:
        """
        Format database row for CSV output (29 columns).

        Args:
            row: Row dictionary from database

        Returns:
            List of values in correct column order
        """
        return [
            row.get('listing_title', ''),
            row.get('ebay_item_id', ''),
            self._format_date(row.get('item_start_date')),
            row.get('category', ''),
            row.get('current_promoted_status', ''),
            row.get('quantity_available', 0),
            row.get('total_impressions', 0),
            self._format_percentage(row.get('click_through_rate')),
            row.get('quantity_sold', 0),
            self._format_percentage(row.get('pct_top_20_search_impressions')),  # NULL
            self._format_percentage(row.get('sales_conversion_rate'), use_dash=True),
            row.get('top_20_promoted_impressions', ''),  # NULL
            self._format_percentage(row.get('pct_change_top_20_promoted')),  # NULL
            row.get('top_20_organic_impressions', ''),  # NULL
            self._format_percentage(row.get('pct_change_top_20_organic')),  # NULL
            row.get('rest_of_search_impressions', ''),  # NULL
            row.get('total_search_impressions', 0),
            row.get('non_search_promoted_impressions', 0),
            self._format_percentage(row.get('pct_change_non_search_promoted')),  # NULL
            row.get('non_search_organic_impressions', 0),
            self._format_percentage(row.get('pct_change_non_search_organic')),  # NULL
            row.get('total_promoted_impressions', 0),
            row.get('total_promoted_offsite_impressions', 0),  # NULL
            row.get('total_organic_impressions', 0),
            row.get('total_page_views', 0),
            row.get('page_views_promoted_ebay', 0),
            row.get('page_views_promoted_offsite', 0),  # NULL
            row.get('page_views_organic_ebay', 0),
            row.get('page_views_organic_offsite', 0)  # NULL
        ]

    def _format_percentage(
        self,
        value: Any,
        use_dash: bool = False
    ) -> str:
        """
        Format percentage value for CSV.

        Args:
            value: Percentage value or None
            use_dash: Use '-' for None/0 instead of empty string

        Returns:
            Formatted string (e.g., '12.34%' or '-' or '')
        """
        if value is None:
            return '-' if use_dash else ''

        try:
            val = float(value)
            if val == 0 and use_dash:
                return '-'
            return f"{val:.2f}%"
        except (ValueError, TypeError):
            return '-' if use_dash else ''

    def _format_date(self, date_str: Any) -> str:
        """
        Format date for CSV (convert YYYY-MM-DD to YYYY/M/D format).

        Args:
            date_str: Date string in YYYY-MM-DD format

        Returns:
            Formatted date string
        """
        if not date_str:
            return ''

        try:
            # Convert YYYY-MM-DD to YYYY/M/D (no leading zeros on month/day)
            parts = str(date_str).split('-')
            if len(parts) == 3:
                year, month, day = parts
                return f"{year}/{int(month)}/{int(day)}"
        except (ValueError, IndexError):
            pass

        return str(date_str)


if __name__ == "__main__":
    # Test report generator
    from ..config import load_config, DateRangeParser

    print("Testing ReportGenerator...\n")

    try:
        config = load_config()
        generator = ReportGenerator(config)

        print("✓ ReportGenerator initialized")
        print()

        # Test date range
        start, end = DateRangeParser.get_date_range_last_n_days(7)
        output_path = "reports/test_report.csv"

        print(f"Test date range: {start} to {end}")
        print(f"Output path: {output_path}")
        print()

        # Note: Requires data in database
        # Uncomment below to test with real data

        # print("Generating report...")
        # stats = generator.generate_report(start, end, output_path)
        # print(f"\nGeneration results:")
        # print(f"  Rows: {stats['rows_generated']}")
        # print(f"  File: {stats['output_path']}")

        print("✓ ReportGenerator test completed")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
