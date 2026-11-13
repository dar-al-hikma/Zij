"""The rebuilt atlas, pinned.

Nothing recorded what atlas.db should hold: no row count, schema or dump
date, and no test held any place's coordinates absolutely, so a changed row
was a "binary files differ" line that passed the whole suite. The file's
SHA-256 is pinned in test_shipped_data_hashes_2026_10_13.py; here are its
row count, schema and the dump it was built from (its own metadata table),
a digest of every place's coordinates, five places' coordinates exactly as
the dump gives them, and the country and region name tables' coverage.

A deliberate rebuild updates these pins in the same commit and says why.
The atlas is now built by build_atlas.py from GeoNames' allCountries file,
every populated place with its other names; these pins were moved to it
from the cities500 atlas, and the tables the search reads were added. The
source file's size is pinned as the complete atlas's metadata records it,
beside its address, SHA-256 and date.
"""
import contextlib
import hashlib
import importlib.resources
import sqlite3

import pytest

from conftest import APP_PATH, small_atlas_copy, source_files

ATLAS = APP_PATH.parent / "atlas.db"

# every populated place of the dump, less the five on the drop list
ROWS = 5232024
DUMP_DATE = "2026-10-22"
SOURCE_SHA256 = "5f939a816e33115b2a2cc97eb94a037af2542eafb9882cf37390a38ac414ec7a"
# sha256 over "id\tlat\tlon\n" for every row in id order, each number by repr
COORDINATES_DIGEST = "2017299b2045829b61dfd160ba5bd3bcfdf7d1b7521c633b7da3424f2031fc21"

# (id, name, country, lat, lon) as GeoNames' dump gives them
PLACES = [
    (2643743, "London", "GB", 51.50853, -0.12574),
    (5128581, "New York City", "US", 40.71427, -74.00597),
    (2147714, "Sydney", "AU", -33.86785, 151.20732),           # the southern hemisphere
    (1850147, "Tokyo", "JP", 35.6895, 139.69171),              # the eastern hemisphere
    (1808588, "Hekou", "CN", 22.53851, 104.01109),             # a border row
]

SCHEMA = {
    "places": [("geonameid", "INTEGER", 0, 1), ("name", "TEXT", 1, 0), ("ascii_name", "TEXT", 0, 0),
               ("feature_code", "TEXT", 0, 0), ("country_code", "TEXT", 0, 0), ("country_name", "TEXT", 0, 0),
               ("admin1_code", "TEXT", 0, 0), ("admin1_name", "TEXT", 0, 0), ("admin2_code", "TEXT", 0, 0),
               ("lat", "REAL", 0, 0), ("lon", "REAL", 0, 0), ("population", "INTEGER", 0, 0),
               ("historical", "INTEGER", 0, 0), ("geonames_zone", "INTEGER", 0, 0)],
    "names": [("geonameid", "INTEGER", 0, 0), ("name", "TEXT", 0, 0), ("lang", "TEXT", 0, 0),
              ("is_preferred", "INTEGER", 0, 0), ("is_short", "INTEGER", 0, 0), ("is_colloquial", "INTEGER", 0, 0),
              ("is_historic", "INTEGER", 0, 0)],
    "geonames_zones": [("id", "INTEGER", 0, 1), ("name", "TEXT", 1, 0)],
    "atlas_keys": [("id", "INTEGER", 0, 1), ("geonameid", "INTEGER", 1, 0), ("kinds", "INTEGER", 1, 0),
                   ("key", "TEXT", 1, 0), ("matched", "TEXT", 0, 0), ("historic_name", "INTEGER", 1, 0),
                   ("country", "TEXT", 1, 0), ("region", "TEXT", 1, 0)],
    "atlas_prefix_results": [("kind", "INTEGER", 1, 1), ("scope", "TEXT", 1, 2), ("prefix", "TEXT", 1, 3),
                             ("rank", "INTEGER", 1, 4), ("key_id", "INTEGER", 1, 0)],
    "country_names": [("country", "TEXT", 0, 1), ("name", "TEXT", 1, 0)],
    "admin1_names": [("country", "TEXT", 1, 1), ("admin1", "TEXT", 1, 2), ("name", "TEXT", 0, 0),
                     ("ascii_name", "TEXT", 0, 0)],
    "metadata": [("key", "TEXT", 0, 1), ("value", "TEXT", 1, 0)],
    # what ANALYZE writes for the query planner
    "sqlite_stat1": [("tbl", "", 0, 0), ("idx", "", 0, 0), ("stat", "", 0, 0)],
    "sqlite_stat4": [("tbl", "", 0, 0), ("idx", "", 0, 0), ("neq", "", 0, 0), ("nlt", "", 0, 0),
                     ("ndlt", "", 0, 0), ("sample", "", 0, 0)],
}
INDEXES = {"names_place": "CREATE INDEX names_place ON names(geonameid)",
           "atlas_key_range": "CREATE INDEX atlas_key_range ON atlas_keys(kinds, key)",
           "atlas_country_range": "CREATE INDEX atlas_country_range ON atlas_keys(country, kinds, key)",
           "atlas_region_range": "CREATE INDEX atlas_region_range ON atlas_keys(country, region, kinds, key)"}
# the table the lookup has always read, a view over the places
CITIES_VIEW = ("CREATE VIEW cities AS SELECT geonameid AS id, name, ascii_name, admin1_code AS admin1,\n"
               "  country_code AS country, lat, lon, population, geonames_zone FROM places")


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
        views = dict(conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'view'"))
    assert indexes == INDEXES
    assert views == {"cities": CITIES_VIEW}


def test_the_atlas_records_the_dump_it_was_built_from():
    with atlas() as conn:
        meta = dict(conn.execute("SELECT key, value FROM metadata"))
        count = conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
    assert count == ROWS == int(meta["rows"])
    assert meta["dump_date"] == DUMP_DATE
    assert meta["source_url"] == "https://download.geonames.org/export/dump/allCountries.zip"
    assert meta["source_sha256"] == SOURCE_SHA256
    assert meta["source_bytes"] == "422207981"
    assert meta["source_last_modified"]
    for prefix, name in (("country_info", "countryInfo.txt"), ("admin1_codes", "admin1CodesASCII.txt"),
                         ("alternate_names", "alternateNamesV2.zip")):
        assert meta[f"{prefix}_url"] == f"https://download.geonames.org/export/dump/{name}"
        assert len(meta[f"{prefix}_sha256"]) == 64 and int(meta[f"{prefix}_bytes"]) > 0
    # built with the app's interpreter (its Unicode tables fold the names)
    assert meta["python_version"].startswith("3.14.") and meta["unicodedata_version"] == "16.0.0"
    assert meta["tzdata_version"] == "2026.5"
    assert meta["dropped_ids"] == "3785489 5854945 11695318 12564634 13110512"
    # the search the lookup reads this atlas through
    assert meta["app_search_version"] == "2"


def test_every_place_s_coordinates_are_the_dump_s():
    with atlas() as conn:
        assert coordinates_digest(conn) == COORDINATES_DIGEST


@pytest.mark.parametrize("gid, name, country, lat, lon", PLACES, ids=[p[1] for p in PLACES])
def test_a_pinned_place_has_the_dump_s_coordinates_exactly(gid, name, country, lat, lon):
    with atlas() as conn:
        assert conn.execute("SELECT name, country, lat, lon FROM cities WHERE id = ?", (gid,)).fetchone() == \
            (name, country, lat, lon)


def test_the_pins_read_a_coordinate_moved_by_a_hundredth_of_a_degree(tmp_path, shipped_atlas, small_atlas):
    """A copy with London moved 0.01 degree north: the coordinates digest and
    London's own pin both move (the file's SHA-256 pin does too). The copy is
    of the small atlas made from the shipped one, so each digest is held
    against the undamaged small atlas's as well as against the pin."""
    copy = small_atlas_copy(small_atlas, tmp_path / "atlas.db")
    with contextlib.closing(sqlite3.connect(copy)) as conn:
        undamaged = coordinates_digest(conn)
        assert conn.execute("SELECT lat FROM cities WHERE id = 2643743").fetchone()[0] == PLACES[0][3]
        conn.execute("UPDATE places SET lat = lat + 0.01 WHERE geonameid = 2643743")
        conn.commit()
        assert coordinates_digest(conn) != COORDINATES_DIGEST
        assert coordinates_digest(conn) != undamaged
        assert conn.execute("SELECT lat FROM cities WHERE id = 2643743").fetchone()[0] != PLACES[0][3]
    with open(copy, "rb") as f:
        moved = hashlib.sha256(f.read()).hexdigest()
    assert moved != shipped_atlas.sha256
    assert moved != small_atlas.sha256


def test_every_row_passed_the_builder_s_checks():
    zones = frozenset(importlib.resources.files("tzdata").joinpath("zones").read_text(encoding="utf-8").split())
    with atlas() as conn:
        bad = conn.execute("SELECT COUNT(*) FROM cities WHERE lat < -90 OR lat > 90 OR lon < -180 OR lon > 180 "
                           "OR population < 0 OR length(country) != 2 OR typeof(admin1) != 'text'").fetchone()[0]
        names = {r[0] for r in conn.execute("SELECT name FROM geonames_zones")}
        unzoned = conn.execute("SELECT COUNT(*) FROM cities WHERE geonames_zone IS NOT NULL AND geonames_zone "
                               "NOT IN (SELECT id FROM geonames_zones)").fetchone()[0]
        dropped = conn.execute("SELECT COUNT(*) FROM cities WHERE id IN (3785489, 5854945, 11695318, 12564634, "
                               "13110512)").fetchone()[0]
    assert bad == 0 and unzoned == 0 and dropped == 0
    assert names and names <= zones


def test_the_name_tables_cover_every_country_and_pair_of_the_atlas():
    """Item 12 (the atlas-names check, section 10): every country and every
    (country, admin1) pair the places carry, a blank code and "00" apart,
    with GeoNames' names as given; the atlas search reads them for a typed
    region or country. (246 countries and 3,880 pairs on the cities500
    atlas, 96 pairs of 462 places unnamed.)"""
    with atlas() as conn:
        pairs = conn.execute("SELECT country, admin1, COUNT(*) FROM cities GROUP BY 1, 2").fetchall()
        countries = dict(conn.execute("SELECT country, name FROM country_names"))
        regions = {(c, a): (n, s) for c, a, n, s in conn.execute("SELECT * FROM admin1_names")}
    assert set(countries) == {c for c, _a, _n in pairs}
    assert len(countries) == 248
    assert set(regions) == {(c, a) for c, a, _n in pairs} and len(regions) == 4251
    unnamed = [(c, a, n) for c, a, n in pairs if regions[(c, a)][0] is None]
    assert len(unnamed) == 415 and sum(n for *_k, n in unnamed) == 28899
    assert ("AW", "") in regions and ("AW", "00") in regions
    assert countries["BQ"] == "Bonaire, Saint Eustatius and Saba "      # GeoNames' trailing space kept
    assert all(name and not set(name) & set('\t\n\r"') for name in countries.values())


def test_the_app_reads_neither_name_table():
    # Every module of the program: time_zones.py alone may hold the two names, as the next test holds it.
    text = "\n".join(p.read_text(encoding="utf-8") for p in source_files() if p.name != "time_zones.py")
    assert "engine.py" in {p.name for p in source_files()}, "the premise: the list holds the moved text's home"
    assert "country_names" not in text and "admin1_names" not in text and "geonames_zone" not in text
    assert "geonames_zone" not in (APP_PATH.parent / "time_zones.py").read_text(encoding="utf-8")


def test_the_name_tables_are_read_by_the_qualifiers_alone():
    """In time_zones.py the name tables are read by the atlas search's
    qualifiers alone (_atlas_holding), and the zones' table by nothing."""
    import ast
    zones = (APP_PATH.parent / "time_zones.py").read_text(encoding="utf-8")
    assert "geonames_zone" not in zones
    readers = {n.name for n in ast.parse(zones).body if isinstance(n, ast.FunctionDef)
               and ("country_names" in ast.get_source_segment(zones, n) or "admin1_names" in ast.get_source_segment(zones, n))}
    assert readers == {"_atlas_holding"}
    assert zones.count("FROM country_names") == 1 and zones.count("FROM admin1_names") == 1
