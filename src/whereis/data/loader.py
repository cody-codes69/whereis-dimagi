"""Download + load the GeoNames cities15000 dump into SQLite.

Idempotent: safe to re-run; will skip loading if the table already looks populated.
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

from ..config import settings
from ..db import engine, raw_connection
from ..models import Base

GEONAMES_COLUMNS = (
    "geonameid",
    "name",
    "asciiname",
    "alternatenames",
    "latitude",
    "longitude",
    "feature_class",
    "feature_code",
    "country_code",
    "cc2",
    "admin1",
    "admin2",
    "admin3",
    "admin4",
    "population",
    "elevation",
    "dem",
    "timezone",
    "modification_date",
)


def _download_dump(dest: Path) -> Path:
    """Download cities15000.zip if not already present and extract the .txt."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    txt_path = dest.with_suffix(".txt")
    if txt_path.exists() and txt_path.stat().st_size > 0:
        return txt_path
    print(f"[loader] downloading {settings.geonames_dump_url} ...", file=sys.stderr)
    with urlopen(settings.geonames_dump_url) as resp:  # noqa: S310
        payload = resp.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        member = settings.geonames_dump_file
        zf.extract(member, dest.parent)
    return txt_path


def _create_schema() -> None:
    Base.metadata.create_all(engine)
    with raw_connection() as cx:
        cx.executescript(
            """
            -- Clean up R*Tree leftovers from an earlier revision; see module docstring.
            DROP TABLE IF EXISTS places_rtree;
            DROP TABLE IF EXISTS places_rtree_rowid;
            DROP TABLE IF EXISTS places_rtree_node;
            DROP TABLE IF EXISTS places_rtree_parent;

            CREATE VIRTUAL TABLE IF NOT EXISTS places_fts USING fts5(
                name, asciiname, alternatenames,
                content='places', content_rowid='geonameid', tokenize='unicode61'
            );
            """
        )


def _already_loaded(cx) -> bool:  # noqa: ANN001
    row = cx.execute("SELECT COUNT(*) FROM places").fetchone()
    return row and row[0] > 1000


def load(data_dir: Path | None = None, force: bool = False) -> int:
    """Load the cities dump. Returns number of rows inserted."""
    data_dir = data_dir or settings.db_path.parent
    _create_schema()

    with raw_connection() as cx:
        if not force and _already_loaded(cx):
            n = cx.execute("SELECT COUNT(*) FROM places").fetchone()[0]
            print(f"[loader] places already populated ({n} rows), skipping.", file=sys.stderr)
            return 0

    txt_path = _download_dump(data_dir / settings.geonames_dump_file)

    inserted = 0
    with raw_connection() as cx, txt_path.open(encoding="utf-8", newline="") as fh:
        cx.execute("BEGIN")
        cx.execute("DELETE FROM places")
        cx.execute("DELETE FROM places_fts")
        reader = csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
        for row in reader:
            if len(row) < len(GEONAMES_COLUMNS):
                continue
            rec = dict(zip(GEONAMES_COLUMNS, row, strict=False))
            try:
                gid = int(rec["geonameid"])
                lat = float(rec["latitude"])
                lng = float(rec["longitude"])
                pop = int(rec["population"] or 0)
            except ValueError:
                continue
            cx.execute(
                "INSERT INTO places (geonameid, name, asciiname, alternatenames, country_code, admin1, lat, lng, population, timezone) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    gid,
                    rec["name"],
                    rec["asciiname"],
                    rec["alternatenames"],
                    rec["country_code"],
                    rec["admin1"],
                    lat,
                    lng,
                    pop,
                    rec["timezone"],
                ),
            )
            cx.execute(
                "INSERT INTO places_fts(rowid, name, asciiname, alternatenames) VALUES (?, ?, ?, ?)",
                (gid, rec["name"], rec["asciiname"], rec["alternatenames"]),
            )
            inserted += 1
        cx.execute("COMMIT")
    print(f"[loader] inserted {inserted} places.", file=sys.stderr)
    return inserted


def cli() -> None:
    force = "--force" in sys.argv
    load(force=force)


if __name__ == "__main__":
    cli()
