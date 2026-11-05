"""Download the Olist dataset, verify it, and load it into the analytics database.

Each run replaces the data in one transaction, so a failed run leaves the
previous data in place.
"""

import csv
import hashlib
import os
import shutil
import sys
import urllib.request
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

DATASET_URL = "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"
SEED_DIR = Path(__file__).resolve().parent
DATA_DIR = SEED_DIR / "data"
ARCHIVE_PATH = DATA_DIR / "olist.zip"
SCHEMA_PATH = SEED_DIR / "schema.sql"

# Two categories are used by products but missing from the source translations.
MISSING_CATEGORY_TRANSLATIONS = (
    ("pc_gamer", "pc_gamer"),
    ("portateis_cozinha_e_preparadores_de_alimentos", "portable_kitchen_food_preparers"),
)

GEOLOCATION_FILE = "olist_geolocation_dataset.csv"
GEOLOCATION_SHA256 = "b514f6fc991b9566aeba02aa5d67e2c3630f034b60a0e05aa0d082a3b66d88d6"
GEOLOCATION_RAW_ROWS = 1_000_163
GEOLOCATION_ZIP_PREFIXES = 19_015


@dataclass(frozen=True)
class TableSpec:
    table: str
    filename: str
    sha256: str
    source_rows: int
    renames: dict[str, str] = field(default_factory=dict)
    added_rows: int = 0

    @property
    def expected_rows(self) -> int:
        return self.source_rows + self.added_rows


# Parents come before children so foreign keys hold during the load.
TABLES = (
    TableSpec(
        "customers",
        "olist_customers_dataset.csv",
        "983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2",
        99_441,
    ),
    TableSpec(
        "sellers",
        "olist_sellers_dataset.csv",
        "1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e",
        3_095,
    ),
    TableSpec(
        "product_categories",
        "product_category_name_translation.csv",
        "a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278",
        71,
        added_rows=len(MISSING_CATEGORY_TRANSLATIONS),
    ),
    TableSpec(
        "products",
        "olist_products_dataset.csv",
        "3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc",
        32_951,
        renames={
            "product_name_lenght": "product_name_length",
            "product_description_lenght": "product_description_length",
        },
    ),
    TableSpec(
        "orders",
        "olist_orders_dataset.csv",
        "8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf",
        99_441,
    ),
    TableSpec(
        "order_items",
        "olist_order_items_dataset.csv",
        "0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279",
        112_650,
    ),
    TableSpec(
        "order_payments",
        "olist_order_payments_dataset.csv",
        "4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0",
        103_886,
    ),
    TableSpec(
        "order_reviews",
        "olist_order_reviews_dataset.csv",
        "012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7",
        99_224,
    ),
)

EXPECTED_HASHES = {spec.filename: spec.sha256 for spec in TABLES} | {
    GEOLOCATION_FILE: GEOLOCATION_SHA256
}

CREATE_GEOLOCATION_STAGING = """
CREATE TEMP TABLE geolocation_raw (
  geolocation_zip_code_prefix TEXT NOT NULL,
  geolocation_lat DOUBLE PRECISION NOT NULL,
  geolocation_lng DOUBLE PRECISION NOT NULL,
  geolocation_city TEXT NOT NULL,
  geolocation_state TEXT NOT NULL
) ON COMMIT DROP
"""

# A zip prefix has many raw points, some far outside Brazil. Medians resist
# those outliers, and one row per prefix stops joins from multiplying rows.
REDUCE_GEOLOCATION = """
INSERT INTO geolocation (zip_code_prefix, latitude, longitude, city, state)
SELECT
  geolocation_zip_code_prefix,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY geolocation_lat),
  percentile_cont(0.5) WITHIN GROUP (ORDER BY geolocation_lng),
  mode() WITHIN GROUP (ORDER BY geolocation_city),
  mode() WITHIN GROUP (ORDER BY geolocation_state)
FROM geolocation_raw
GROUP BY geolocation_zip_code_prefix
"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_mismatches(directory: Path, expected: dict[str, str]) -> list[str]:
    """Return the names of files that are missing or differ from their hash."""
    return [
        name
        for name, sha256 in expected.items()
        if not (directory / name).is_file() or sha256_of(directory / name) != sha256
    ]


def download_archive(url: str, destination: Path) -> None:
    """Download to a temporary name so an interrupted run leaves no partial file."""
    partial = destination.with_suffix(".part")
    request = urllib.request.Request(url, headers={"User-Agent": "querypilot-seed"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as file:
        shutil.copyfileobj(response, file)
    partial.replace(destination)


def extract_files(archive: Path, names: list[str], directory: Path) -> None:
    """Extract only known names, so paths inside the archive are never trusted."""
    with zipfile.ZipFile(archive) as bundle:
        for name in names:
            with bundle.open(name) as source, (directory / name).open("wb") as target:
                shutil.copyfileobj(source, target)


def ensure_dataset(directory: Path, archive: Path, url: str, expected: dict[str, str]) -> None:
    """Make the verified CSVs available, reusing earlier downloads when valid."""
    directory.mkdir(parents=True, exist_ok=True)
    if not hash_mismatches(directory, expected):
        print("Dataset already present and verified.")
        return
    if not archive.is_file():
        print(f"Downloading {url}")
        download_archive(url, archive)
    extract_files(archive, list(expected), directory)
    mismatched = hash_mismatches(directory, expected)
    if mismatched:
        raise ValueError(
            f"Checksum mismatch for {', '.join(mismatched)}. The source may have "
            f"changed. Delete {archive} to retry, or review the pinned hashes."
        )
    print("Dataset downloaded and verified.")


def read_rows(path: Path, renames: dict[str, str]) -> tuple[list[str], Iterator[list[str | None]]]:
    """Return column names and rows, with empty CSV fields as NULL.

    The source mixes line endings and has a byte order mark in one file, so a
    CSV parser handles it more safely than a server-side COPY of the raw file.
    """
    with path.open(encoding="utf-8-sig", newline="") as file:
        header = next(csv.reader(file))
    columns = [renames.get(column, column) for column in header]

    def rows() -> Iterator[list[str | None]]:
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            next(reader)
            for row in reader:
                yield [value or None for value in row]

    return columns, rows()


def copy_file(cursor: psycopg.Cursor, table: str, path: Path, renames: dict[str, str]) -> None:
    columns, rows = read_rows(path, renames)
    column_list = ", ".join(columns)
    with cursor.copy(f"COPY {table} ({column_list}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)


def row_count(cursor: psycopg.Cursor, table: str) -> int:
    result = cursor.execute(f"SELECT count(*) FROM {table}").fetchone()
    assert result is not None
    return int(result[0])


def verify_count(cursor: psycopg.Cursor, table: str, expected: int) -> None:
    actual = row_count(cursor, table)
    if actual != expected:
        raise ValueError(f"{table}: expected {expected} rows, loaded {actual}")
    print(f"  {table}: {actual:,} rows")


def load_tables(cursor: psycopg.Cursor, directory: Path) -> None:
    for spec in TABLES:
        copy_file(cursor, spec.table, directory / spec.filename, spec.renames)
        if spec.table == "product_categories":
            cursor.executemany(
                "INSERT INTO product_categories VALUES (%s, %s)",
                MISSING_CATEGORY_TRANSLATIONS,
            )
        verify_count(cursor, spec.table, spec.expected_rows)


def load_geolocation(cursor: psycopg.Cursor, directory: Path) -> None:
    cursor.execute(CREATE_GEOLOCATION_STAGING)
    copy_file(cursor, "geolocation_raw", directory / GEOLOCATION_FILE, {})
    verify_count(cursor, "geolocation_raw", GEOLOCATION_RAW_ROWS)
    cursor.execute(REDUCE_GEOLOCATION)
    verify_count(cursor, "geolocation", GEOLOCATION_ZIP_PREFIXES)


def load_database(connection: psycopg.Connection, directory: Path) -> None:
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        load_tables(cursor, directory)
        load_geolocation(cursor, directory)
    # ANALYZE after commit gives the planner statistics for the new tables.
    connection.execute("ANALYZE")


def connection_settings() -> dict[str, str]:
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ["POSTGRES_PORT"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "dbname": os.environ["ANALYTICS_DB_NAME"],
    }


def is_seeded(connection: psycopg.Connection) -> bool:
    """The load is one transaction, so any seeded table means all of them are there."""
    result = connection.execute("SELECT to_regclass('public.orders')").fetchone()
    return result is not None and result[0] is not None


def main() -> int:
    with psycopg.connect(**connection_settings(), autocommit=True) as connection:
        if is_seeded(connection) and not os.environ.get("SEED_FORCE"):
            print("Dataset already loaded. Set SEED_FORCE=1 to reload it.")
            return 0
        ensure_dataset(DATA_DIR, ARCHIVE_PATH, DATASET_URL, EXPECTED_HASHES)
        load_database(connection, DATA_DIR)
    print("Seed complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
