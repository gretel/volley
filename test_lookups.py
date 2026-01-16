#!/usr/bin/env python3
"""Test script for zipcode and phone prefix lookups."""

import sqlite3
from pathlib import Path
import pgeocode

def test_zipcode_lookup():
    """Test zipcode to coordinates lookup."""
    print("Testing zipcode lookups with pgeocode...")
    nomi = pgeocode.Nominatim('de')

    test_cases = [
        '22765',  # Hamburg
        '10115',  # Berlin
        '80331',  # München
        '50667',  # Köln
    ]

    for zipcode in test_cases:
        result = nomi.query_postal_code(zipcode)
        if result is not None and not result.empty:
            print(f"  ✅ {zipcode}: {result.place_name}, lat={result.latitude:.4f}, lon={result.longitude:.4f}")
        else:
            print(f"  ❌ {zipcode}: Not found")

def test_prefix_lookup():
    """Test phone prefix to zipcode lookup."""
    print("\nTesting phone prefix lookups with SQLite...")

    db_path = Path(__file__).parent / "zipcodes.db"
    if not db_path.exists():
        print(f"  ❌ Database not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    test_cases = [
        '0241',  # Aachen
        '040',   # Hamburg
        '030',   # Berlin
        '089',   # München
    ]

    for prefix in test_cases:
        cursor.execute("SELECT zipcode, city FROM zipcodes WHERE prefix = ? LIMIT 1", (prefix,))
        result = cursor.fetchone()
        if result:
            zipcode, city = result
            print(f"  ✅ {prefix}: {city} ({zipcode})")
        else:
            print(f"  ❌ {prefix}: Not found")

    conn.close()

def test_combined():
    """Test combined prefix -> zipcode -> coordinates lookup."""
    print("\nTesting combined prefix -> zipcode -> coordinates...")

    db_path = Path(__file__).parent / "zipcodes.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    nomi = pgeocode.Nominatim('de')

    test_prefixes = ['0241', '040', '030']

    for prefix in test_prefixes:
        # Get zipcode from prefix
        cursor.execute("SELECT zipcode, city FROM zipcodes WHERE prefix = ? LIMIT 1", (prefix,))
        result = cursor.fetchone()

        if result:
            zipcode, city = result
            # Get coordinates from zipcode
            coords = nomi.query_postal_code(zipcode)
            if coords is not None and not coords.empty:
                print(f"  ✅ {prefix} -> {city} ({zipcode}) -> lat={coords.latitude:.4f}, lon={coords.longitude:.4f}")
            else:
                print(f"  ⚠️  {prefix} -> {city} ({zipcode}) -> No coordinates")
        else:
            print(f"  ❌ {prefix}: Not found")

    conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Volley Lookup Tests")
    print("=" * 60)

    test_zipcode_lookup()
    test_prefix_lookup()
    test_combined()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
