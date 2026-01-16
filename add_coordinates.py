#!/usr/bin/env python3
"""
Add latitude/longitude coordinates to zipcodes.db using pgeocode.

This is a one-time operation to pre-compute coordinates so we don't need
pgeocode (and its heavy dependencies numpy/pandas) at runtime.

Requires: pgeocode (install temporarily: pip install pgeocode)
"""
import sqlite3
import sys
from pathlib import Path

try:
    import pgeocode
except ImportError:
    print("Error: pgeocode not installed")
    print("Install it temporarily: pip install pgeocode")
    sys.exit(1)


def add_coordinates_to_db(db_path: str):
    """Add lat/lon columns to database and populate with pgeocode."""

    db_file = Path(db_path)
    if not db_file.exists():
        print(f"Error: Database not found: {db_path}")
        sys.exit(1)

    print("Initializing pgeocode...")
    nomi = pgeocode.Nominatim('de')

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Add lat/lon columns if they don't exist
    try:
        cursor.execute("ALTER TABLE zipcodes ADD COLUMN latitude REAL")
        cursor.execute("ALTER TABLE zipcodes ADD COLUMN longitude REAL")
        print("Added latitude and longitude columns")
    except sqlite3.OperationalError:
        print("Columns already exist, updating values...")

    # Get all zipcodes
    cursor.execute("SELECT zipcode FROM zipcodes")
    zipcodes = [row[0] for row in cursor.fetchall()]
    total = len(zipcodes)

    print(f"Fetching coordinates for {total} zipcodes...")

    success_count = 0
    fail_count = 0

    for i, zipcode in enumerate(zipcodes, 1):
        if i % 100 == 0:
            print(f"  Progress: {i}/{total} ({i*100//total}%)")

        try:
            result = nomi.query_postal_code(zipcode)

            if result is not None and not result.empty:
                lat = result.latitude
                lon = result.longitude

                # Check for valid coordinates (not NaN)
                if (lat is not None and lon is not None and
                    str(lat) != 'nan' and str(lon) != 'nan'):
                    cursor.execute(
                        "UPDATE zipcodes SET latitude = ?, longitude = ? WHERE zipcode = ?",
                        (float(lat), float(lon), zipcode)
                    )
                    success_count += 1
                else:
                    fail_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"  Error for zipcode {zipcode}: {e}")
            fail_count += 1

    # Commit changes
    conn.commit()

    # Create index on coordinates for faster queries
    try:
        cursor.execute("CREATE INDEX idx_coordinates ON zipcodes(latitude, longitude)")
        print("Created index on coordinates")
    except sqlite3.OperationalError:
        print("Index already exists")

    conn.close()

    print(f"\n✅ Coordinate update complete!")
    print(f"   Success: {success_count}/{total} ({success_count*100//total}%)")
    print(f"   Failed: {fail_count}/{total}")

    # Show database size
    db_size = db_file.stat().st_size
    print(f"   Database size: {db_size / 1024:.1f} KB")


if __name__ == "__main__":
    db_file = "zipcodes.db"
    print(f"Adding coordinates to {db_file}...")
    print("This requires pgeocode (with numpy/pandas) to be installed temporarily")
    print()
    add_coordinates_to_db(db_file)
    print()
    print("You can now uninstall pgeocode and use the lightweight runtime!")
