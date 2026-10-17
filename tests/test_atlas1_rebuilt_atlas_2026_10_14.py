"""The rebuilt atlas, pinned (SC-04 of the security sweep; ATLAS1's rebuild,
rulings 172 and 179 S-01; the name tables by 179 S-04 (a)).

Nothing recorded what atlas.db should hold: no row count, schema or dump
date, and no test held any place's coordinates absolutely, so a changed row
was a "binary files differ" line that passed the whole suite. The file's
SHA-256 is pinned in test_shipped_data_hashes_2026_10_13.py; here are its
row count, schema and the dump it was built from (its own metadata table),
a digest of every place's coordinates, five places' coordinates exactly as
the dump gives them, and the country and region name tables' coverage.

A deliberate rebuild updates these pins in the same commit and says why.
"""
import contextlib
import hashlib
import importlib.resources
import sqlite3

import pytest

from conftest import APP_PATH

ATLAS = APP_PATH.parent / "atlas.db"

ROWS = 236191
DUMP_DATE = "2026-10-14"
SOURCE_SHA256 = "46fd044a7e0d2d097daa96d9075c8c818e8b0e337bf58724a4f94637dd351ad2"
# sha256 over "id\tlat\tlon\n" for every row in id order, each number by repr
COORDINATES_DIGEST = "de43724d2ba38bb7ce360dc14da48f2d46722cb98befb6e6c800d4b9e9542665"

# (id, name, country, lat, lon) as GeoNames' dump gives them
PLACES = [
    (2643743, "London", "GB", 51.50853, -0.12574),
    (5128581, "New York City", "US", 40.71427, -74.00597),
    (2147714, "Sydney", "AU", -33.86785, 151.20732),           # the southern hemisphere
    (1850147, "Tokyo", "JP", 35.6895, 139.69171),              # the eastern hemisphere
    (1808588, "Hekou", "CN", 22.53851, 104.01109),             # C-01's border row
]

SCHEMA = {
    "cities": [("id", "INTEGER", 0, 1), ("name", "TEXT", 0, 0), ("ascii_name", "TEXT", 0, 0),
               ("admin1", "TEXT", 0, 0), ("country", "TEXT", 0, 0), ("lat", "REAL", 0, 0), ("lon", "REAL", 0, 0),
               ("population", "INTEGER", 0, 0), ("geonames_zone", "INTEGER", 0, 0)],
    "geonames_zones": [("id", "INTEGER", 0, 1), ("name", "TEXT", 1, 0)],
    "country_names": [("country", "TEXT", 0, 1), ("name", "TEXT", 1, 0)],
    "admin1_names": [("country", "TEXT", 1, 1), ("admin1", "TEXT", 1, 2), ("name", "TEXT", 0, 0),
                     ("ascii_name", "TEXT", 0, 0)],
    "metadata": [("key", "TEXT", 0, 1), ("value", "TEXT", 1, 0)],
}
INDEXES = {"idx_name": "CREATE INDEX idx_name ON cities(name COLLATE NOCASE)",
           "idx_ascii": "CREATE INDEX idx_ascii ON cities(ascii_name COLLATE NOCASE)"}


@contextlib.contextmanager
def atlas():
    with contextlib.closing(sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True)) as conn:
        yield conn


def coordinates_digest(conn):
    h = hashlib.sha256()
    for gid, lat, lon in conn.execute("SELECT id, lat, lon FROM cities ORDER BY id"):
        h.update(f"{gid}\t{lat!r}\t{lon!r}\n".encode("utf-8"))
    return h.hexdigest()


def test_the_atlas_has_its_schema():
    with atlas() as conn:
        tables = sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
        assert tables == sorted(SCHEMA)
        for table, columns in SCHEMA.items():
            got = [(r[1], r[2], r[3], r[5]) for r in conn.execute(f"PRAGMA table_info({table})")]
            assert got == columns, table
        indexes = dict(conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"))
    assert indexes == INDEXES


def test_the_atlas_records_the_dump_it_was_built_from():
    with atlas() as conn:
        meta = dict(conn.execute("SELECT key, value FROM metadata"))
        count = conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
    assert count == ROWS == int(meta["rows"])
    assert meta["dump_date"] == DUMP_DATE
    assert meta["source_url"] == "https://download.geonames.org/export/dump/cities500.zip"
    assert meta["source_sha256"] == SOURCE_SHA256 and meta["source_bytes"] == "13881894"
    assert meta["source_last_modified"]
    for prefix, name in (("country_info", "countryInfo.txt"), ("admin1_codes", "admin1CodesASCII.txt")):
        assert meta[f"{prefix}_url"] == f"https://download.geonames.org/export/dump/{name}"
        assert len(meta[f"{prefix}_sha256"]) == 64 and int(meta[f"{prefix}_bytes"]) > 0
    # built with the app's interpreter (its Unicode tables fold the names)
    assert meta["python_version"].startswith("3.14.") and meta["unicodedata_version"] == "16.0.0"
    assert meta["tzdata_version"] == "2026.5"
    assert meta["dropped_ids"] == "3785489"


def test_every_place_s_coordinates_are_the_dump_s():
    with atlas() as conn:
        assert coordinates_digest(conn) == COORDINATES_DIGEST


@pytest.mark.parametrize("gid, name, country, lat, lon", PLACES, ids=[p[1] for p in PLACES])
def test_a_pinned_place_has_the_dump_s_coordinates_exactly(gid, name, country, lat, lon):
    with atlas() as conn:
        assert conn.execute("SELECT name, country, lat, lon FROM cities WHERE id = ?", (gid,)).fetchone() == \
            (name, country, lat, lon)


def test_the_pins_read_a_coordinate_moved_by_a_hundredth_of_a_degree(tmp_path):
    """A copy with London moved 0.01 degree north: the coordinates digest and
    London's own pin both move (the file's SHA-256 pin does too)."""
    copy = tmp_path / "atlas.db"
    copy.write_bytes(ATLAS.read_bytes())
    with contextlib.closing(sqlite3.connect(copy)) as conn:
        conn.execute("UPDATE cities SET lat = lat + 0.01 WHERE id = 2643743")
        conn.commit()
        assert coordinates_digest(conn) != COORDINATES_DIGEST
        assert conn.execute("SELECT lat FROM cities WHERE id = 2643743").fetchone()[0] != PLACES[0][3]
    assert hashlib.sha256(copy.read_bytes()).hexdigest() != hashlib.sha256(ATLAS.read_bytes()).hexdigest()


def test_every_row_passed_the_builder_s_checks():
    zones = frozenset(importlib.resources.files("tzdata").joinpath("zones").read_text(encoding="utf-8").split())
    with atlas() as conn:
        bad = conn.execute("SELECT COUNT(*) FROM cities WHERE lat < -90 OR lat > 90 OR lon < -180 OR lon > 180 "
                           "OR population < 0 OR length(country) != 2 OR typeof(admin1) != 'text'").fetchone()[0]
        names = {r[0] for r in conn.execute("SELECT name FROM geonames_zones")}
        unzoned = conn.execute("SELECT COUNT(*) FROM cities WHERE geonames_zone IS NOT NULL AND geonames_zone "
                               "NOT IN (SELECT id FROM geonames_zones)").fetchone()[0]
        dropped = conn.execute("SELECT COUNT(*) FROM cities WHERE id = 3785489").fetchone()[0]
    assert bad == 0 and unzoned == 0 and dropped == 0
    assert names and names <= zones


def test_the_name_tables_cover_every_country_and_pair_of_the_atlas():
    """Item 12 (the atlas-names check, section 10): every country and every
    (country, admin1) pair the places carry, a blank code and "00" apart,
    with GeoNames' names as given; nothing in the app reads them yet."""
    with atlas() as conn:
        pairs = conn.execute("SELECT country, admin1, COUNT(*) FROM cities GROUP BY 1, 2").fetchall()
        countries = dict(conn.execute("SELECT country, name FROM country_names"))
        regions = {(c, a): (n, s) for c, a, n, s in conn.execute("SELECT * FROM admin1_names")}
    assert set(countries) == {c for c, _a, _n in pairs}
    assert len(countries) == 246
    assert set(regions) == {(c, a) for c, a, _n in pairs} and len(regions) == 3880
    unnamed = [(c, a, n) for c, a, n in pairs if regions[(c, a)][0] is None]
    assert len(unnamed) == 96 and sum(n for *_k, n in unnamed) == 462
    assert ("AW", "") in regions and ("AW", "00") in regions
    assert countries["BQ"] == "Bonaire, Saint Eustatius and Saba "      # GeoNames' trailing space kept
    assert all(name and not set(name) & set('\t\n\r"') for name in countries.values())


def test_the_app_reads_neither_name_table():
    text = "\n".join(p.read_text(encoding="utf-8") for p in (APP_PATH, APP_PATH.parent / "engine.py",
                                                            APP_PATH.parent / "time_zones.py"))
    assert "country_names" not in text and "admin1_names" not in text and "geonames_zone" not in text
