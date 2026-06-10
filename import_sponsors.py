"""Import the 80-Days-to-Stay H-1B sponsor dataset into the h1b_sponsors table.

Usage: python import_sponsors.py [path-to-csv]
Downloads the CSV from GitHub if no local path is given.
"""

import csv
import io
import sys
import urllib.request

import database

CSV_URL = (
    "https://raw.githubusercontent.com/nikbearbrown/80-Days-to-Stay/"
    "refs/heads/main/80_Days_CSV/mapped_student_employment_targets_v3.csv"
)


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            content = f.read()
    else:
        print(f"Downloading {CSV_URL} ...")
        with urllib.request.urlopen(CSV_URL) as resp:
            content = resp.read().decode("utf-8")

    rows = list(csv.DictReader(io.StringIO(content)))
    print(f"Parsed {len(rows)} rows")

    database.init_db()
    count = database.import_sponsors(rows)
    stats = database.sponsor_counts()
    print(f"Imported {count} companies ({stats['with_h1b']} with H-1B sponsorship history)")


if __name__ == "__main__":
    main()
