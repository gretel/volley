#!/usr/bin/env python3
"""
Convert German-Zip-Codes.csv to SQLite database.

Data source: https://gist.github.com/jbspeakr/4565964
Original CSV contains German zipcodes with city names, phone prefixes, and states.
"""
import sqlite3
import csv
import sys
from pathlib import Path


def convert_csv_to_db(csv_path: str, db_path: str):
    """Convert CSV file to SQLite database."""

    # Check if CSV exists
    if not Path(csv_path).exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    # Remove existing database if present
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()
        print(f"Removed existing database: {db_path}")

    # Create database connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table
    cursor.execute("""
        CREATE TABLE zipcodes (
            zipcode TEXT PRIMARY KEY,
            city TEXT NOT NULL,
            additional TEXT,
            prefix TEXT NOT NULL,
            state TEXT NOT NULL
        )
    """)

    # Create index on prefix for fast phone prefix lookups
    cursor.execute("CREATE INDEX idx_prefix ON zipcodes(prefix)")

    # Read and insert CSV data
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        rows_inserted = 0

        for row in reader:
            try:
                cursor.execute(
                    "INSERT INTO zipcodes (zipcode, city, additional, prefix, state) VALUES (?, ?, ?, ?, ?)",
                    (
                        row['Plz'],
                        row['Ort'],
                        row['Zusatz'],
                        row['Vorwahl'],
                        row['Bundesland']
                    )
                )
                rows_inserted += 1
            except sqlite3.IntegrityError:
                # Skip duplicate zipcodes (keep first occurrence)
                print(f"Warning: Duplicate zipcode {row['Plz']}, skipping")
                continue

    # Add metadata table with source attribution
    cursor.execute("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        ('source', 'https://gist.github.com/jbspeakr/4565964')
    )
    cursor.execute(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        ('description', 'German zipcodes with city names, phone prefixes, and states')
    )

    # Commit and close
    conn.commit()
    conn.close()

    print(f"✅ Successfully created database: {db_path}")
    print(f"   Inserted {rows_inserted} zipcodes")

    # Display some stats
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(DISTINCT zipcode) FROM zipcodes")
    zipcode_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT prefix) FROM zipcodes")
    prefix_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT state) FROM zipcodes")
    state_count = cursor.fetchone()[0]

    print(f"   Unique zipcodes: {zipcode_count}")
    print(f"   Unique prefixes: {prefix_count}")
    print(f"   States: {state_count}")

    conn.close()


if __name__ == "__main__":
    csv_file = "German-Zip-Codes.csv"
    db_file = "zipcodes.db"

    print(f"Converting {csv_file} to {db_file}...")
    convert_csv_to_db(csv_file, db_file)
