#!/usr/bin/env python3
"""Test that lookups work without pgeocode (lightweight version)."""

import sqlite3
from pathlib import Path


def test_zipcode_lookup():
    """Test zipcode to coordinates lookup from database."""
    print("Testing zipcode lookups from database (no pgeocode)...")

    db_path = Path(__file__).parent / "zipcodes.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    test_cases = [
        '22765',  # Hamburg
        '10115',  # Berlin
        '80331',  # München
        '50667',  # Köln
    ]

    for zipcode in test_cases:
        cursor.execute("SELECT city, latitude, longitude FROM zipcodes WHERE zipcode = ?", (zipcode,))
        result = cursor.fetchone()
        if result:
            city, lat, lon = result
            print(f"  ✅ {zipcode}: {city}, lat={lat:.4f}, lon={lon:.4f}")
        else:
            print(f"  ❌ {zipcode}: Not found")

    conn.close()


def test_prefix_lookup():
    """Test phone prefix to zipcode lookup."""
    print("\nTesting phone prefix lookups from database...")

    db_path = Path(__file__).parent / "zipcodes.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    test_cases = [
        '0241',  # Aachen
        '040',   # Hamburg
        '030',   # Berlin
        '089',   # München
    ]

    for prefix in test_cases:
        cursor.execute("SELECT zipcode, city, latitude, longitude FROM zipcodes WHERE prefix = ? LIMIT 1", (prefix,))
        result = cursor.fetchone()
        if result:
            zipcode, city, lat, lon = result
            if lat and lon:
                print(f"  ✅ {prefix}: {city} ({zipcode}) -> lat={lat:.4f}, lon={lon:.4f}")
            else:
                print(f"  ⚠️  {prefix}: {city} ({zipcode}) -> No coordinates")
        else:
            print(f"  ❌ {prefix}: Not found")

    conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Volley Lightweight Lookup Tests (No pgeocode/numpy/pandas)")
    print("=" * 60)

    test_zipcode_lookup()
    test_prefix_lookup()

    print("\n" + "=" * 60)
    print("All tests completed! ✨")
    print("=" * 60)
