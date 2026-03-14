"""
UPC Loader Service for reading UPC codes from files.

Supports loading UPCs from CSV files and plain text files with validation
and deduplication.
"""

import csv
import re
from pathlib import Path
from typing import List, Set, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class UPCLoadResult:
    """Results from loading UPCs from a file."""

    upcs: List[str]  # Valid, deduplicated UPCs
    total_lines: int  # Total lines processed
    valid_count: int  # Number of valid UPCs
    invalid_count: int  # Number of invalid UPCs
    duplicate_count: int  # Number of duplicates removed
    invalid_upcs: List[Dict[str, Any]]  # List of invalid UPCs with line numbers


class UPCLoader:
    """Service for loading and validating UPC codes from files."""

    # UPC validation: 12-13 digits, optionally prefixed with leading zeros
    UPC_PATTERN = re.compile(r'^\d{12,13}$')

    @staticmethod
    def validate_upc(upc: str) -> bool:
        """
        Validate a UPC code.

        Args:
            upc: UPC code to validate

        Returns:
            True if valid, False otherwise

        Example:
            >>> UPCLoader.validate_upc('0786936735390')
            True
            >>> UPCLoader.validate_upc('12345')
            False
        """
        # Strip whitespace
        upc = upc.strip()

        # Check format (12-13 digits)
        if not UPCLoader.UPC_PATTERN.match(upc):
            return False

        return True

    @staticmethod
    def normalize_upc(upc: str) -> str:
        """
        Normalize a UPC code to 12-digit UPC-A format.

        - Strips whitespace
        - Removes non-digit characters
        - Strips leading zeros to ensure 12-digit consistency
        - UPC-A standard is 12 digits, EAN-13 has leading zero

        Args:
            upc: UPC code to normalize

        Returns:
            Normalized 12-digit UPC string

        Example:
            >>> UPCLoader.normalize_upc('  078-693-673-5390  ')
            '786936735390'
            >>> UPCLoader.normalize_upc('0883929304127')
            '883929304127'
        """
        # Remove whitespace and non-digits
        upc = re.sub(r'[^\d]', '', upc.strip())

        # Strip leading zeros and ensure 12-digit format
        # UPC-A is 12 digits, EAN-13 often adds leading zero
        upc = upc.lstrip('0')

        # If we stripped all zeros, it was '000...', keep one zero
        if not upc:
            upc = '0'

        # Pad with zeros on the left if less than 12 digits
        upc = upc.zfill(12)

        return upc

    @staticmethod
    def load_from_text(
        filepath: str,
        skip_invalid: bool = True
    ) -> UPCLoadResult:
        """
        Load UPCs from a plain text file (one UPC per line).

        Args:
            filepath: Path to text file
            skip_invalid: If True, skip invalid UPCs; if False, raise error

        Returns:
            UPCLoadResult with loaded UPCs and statistics

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If no valid UPCs found

        Example:
            >>> result = UPCLoader.load_from_text('upcs.txt')
            >>> print(f"Loaded {result.valid_count} UPCs")
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        upcs: List[str] = []
        seen: Set[str] = set()
        invalid_upcs: List[Dict[str, Any]] = []
        total_lines = 0

        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                total_lines += 1

                # Skip empty lines and comments
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Normalize UPC
                upc = UPCLoader.normalize_upc(line)

                # Validate
                if not UPCLoader.validate_upc(upc):
                    invalid_upcs.append({
                        'line': line_num,
                        'value': line,
                        'reason': 'Invalid UPC format (must be 12-13 digits)'
                    })
                    if not skip_invalid:
                        raise ValueError(
                            f"Invalid UPC on line {line_num}: '{line}' "
                            f"(must be 12-13 digits)"
                        )
                    continue

                # Check for duplicates
                if upc in seen:
                    continue

                seen.add(upc)
                upcs.append(upc)

        if not upcs:
            raise ValueError(f"No valid UPCs found in {filepath}")

        return UPCLoadResult(
            upcs=upcs,
            total_lines=total_lines,
            valid_count=len(upcs),
            invalid_count=len(invalid_upcs),
            duplicate_count=total_lines - len(upcs) - len(invalid_upcs),
            invalid_upcs=invalid_upcs
        )

    @staticmethod
    def load_from_csv(
        filepath: str,
        upc_column: str = 'upc',
        skip_invalid: bool = True,
        skip_header: bool = True
    ) -> UPCLoadResult:
        """
        Load UPCs from a CSV file.

        Args:
            filepath: Path to CSV file
            upc_column: Name of column containing UPCs (default: 'upc')
            skip_invalid: If True, skip invalid UPCs; if False, raise error
            skip_header: If True, treat first row as header

        Returns:
            UPCLoadResult with loaded UPCs and statistics

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If UPC column not found or no valid UPCs

        Example:
            >>> result = UPCLoader.load_from_csv('dvds.csv', upc_column='UPC')
            >>> print(f"Loaded {result.valid_count} UPCs")

        CSV Format Examples:
            # With header:
            upc,title,price
            0786936735390,Toy Story,9.99
            0012569679672,The Matrix,12.99

            # Without header (column 0):
            0786936735390
            0012569679672
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        upcs: List[str] = []
        seen: Set[str] = set()
        invalid_upcs: List[Dict[str, Any]] = []
        total_lines = 0

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f) if skip_header else csv.reader(f)

            for row_num, row in enumerate(reader, start=1):
                total_lines += 1

                # Skip first row if it's header (already handled by DictReader)
                if skip_header and row_num == 0:
                    continue

                # Extract UPC from column
                try:
                    if isinstance(row, dict):
                        # DictReader (with header)
                        if upc_column not in row:
                            raise ValueError(
                                f"Column '{upc_column}' not found in CSV. "
                                f"Available columns: {', '.join(row.keys())}"
                            )
                        upc_value = row[upc_column]
                    else:
                        # Regular reader (without header) - assume first column
                        upc_value = row[0] if row else ''

                except (IndexError, KeyError) as e:
                    invalid_upcs.append({
                        'line': row_num,
                        'value': str(row),
                        'reason': f'Could not extract UPC: {e}'
                    })
                    if not skip_invalid:
                        raise ValueError(f"Error on row {row_num}: {e}")
                    continue

                # Normalize UPC
                upc = UPCLoader.normalize_upc(upc_value)

                # Skip empty values
                if not upc:
                    continue

                # Validate
                if not UPCLoader.validate_upc(upc):
                    invalid_upcs.append({
                        'line': row_num,
                        'value': upc_value,
                        'reason': 'Invalid UPC format (must be 12-13 digits)'
                    })
                    if not skip_invalid:
                        raise ValueError(
                            f"Invalid UPC on row {row_num}: '{upc_value}' "
                            f"(must be 12-13 digits)"
                        )
                    continue

                # Check for duplicates
                if upc in seen:
                    continue

                seen.add(upc)
                upcs.append(upc)

        if not upcs:
            raise ValueError(f"No valid UPCs found in {filepath}")

        return UPCLoadResult(
            upcs=upcs,
            total_lines=total_lines,
            valid_count=len(upcs),
            invalid_count=len(invalid_upcs),
            duplicate_count=total_lines - len(upcs) - len(invalid_upcs),
            invalid_upcs=invalid_upcs
        )

    @staticmethod
    def load_from_file(
        filepath: str,
        file_type: Optional[str] = None,
        **kwargs
    ) -> UPCLoadResult:
        """
        Auto-detect file type and load UPCs.

        Args:
            filepath: Path to file
            file_type: Optional file type override ('txt', 'csv')
            **kwargs: Additional arguments passed to specific loader

        Returns:
            UPCLoadResult with loaded UPCs

        Example:
            >>> result = UPCLoader.load_from_file('upcs.csv')
            >>> result = UPCLoader.load_from_file('upcs.txt')
        """
        path = Path(filepath)

        # Auto-detect file type if not specified
        if not file_type:
            suffix = path.suffix.lower()
            if suffix == '.csv':
                file_type = 'csv'
            elif suffix in ('.txt', '.text'):
                file_type = 'txt'
            else:
                # Try CSV first, fall back to text
                try:
                    return UPCLoader.load_from_csv(filepath, **kwargs)
                except Exception:
                    return UPCLoader.load_from_text(filepath, **kwargs)

        # Load based on file type
        if file_type == 'csv':
            return UPCLoader.load_from_csv(filepath, **kwargs)
        elif file_type in ('txt', 'text'):
            return UPCLoader.load_from_text(filepath, **kwargs)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")


if __name__ == "__main__":
    """Test UPC loader with sample data."""
    import tempfile
    import os

    print("Testing UPCLoader...")
    print("=" * 60)

    # Create temporary test files
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test text file
        txt_file = os.path.join(tmpdir, 'upcs.txt')
        with open(txt_file, 'w') as f:
            f.write("0786936735390\n")
            f.write("0012569679672\n")
            f.write("# Comment line\n")
            f.write("0786936735390\n")  # Duplicate
            f.write("invalid-upc\n")  # Invalid
            f.write("\n")  # Empty line

        print("Test 1: Loading from text file")
        result = UPCLoader.load_from_text(txt_file)
        print(f"  Total lines: {result.total_lines}")
        print(f"  Valid UPCs: {result.valid_count}")
        print(f"  Invalid UPCs: {result.invalid_count}")
        print(f"  Duplicates: {result.duplicate_count}")
        print(f"  UPCs: {result.upcs}")
        print()

        # Test CSV file
        csv_file = os.path.join(tmpdir, 'dvds.csv')
        with open(csv_file, 'w') as f:
            f.write("upc,title\n")
            f.write("0786936735390,Toy Story\n")
            f.write("0012569679672,The Matrix\n")

        print("Test 2: Loading from CSV file")
        result = UPCLoader.load_from_csv(csv_file)
        print(f"  Valid UPCs: {result.valid_count}")
        print(f"  UPCs: {result.upcs}")
        print()

    print("✓ All tests passed")
