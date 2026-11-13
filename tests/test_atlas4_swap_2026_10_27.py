"""The atlas lookup's reading of a file's version and of its name tables.

A file whose metadata names the indexed search but that lacks its tables is
refused with the plain sentence of a changed atlas, never an SQLite error.
The country and region names the qualifiers compare with are folded once
for each file read, so one process reading two atlases answers each from
its own tables.
"""
import contextlib
import hashlib
import sqlite3

import pytest


@pytest.fixture
def tz():
    import time_zones
    return time_zones


def _old_atlas(path, country_name):
    """A file of the earlier lookup's schema holding Florence alone, its
    country named `country_name`: the base a file naming the indexed search
    without its tables is made from."""
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.executescript("""
            CREATE TABLE cities (id INTEGER PRIMARY KEY, name TEXT, ascii_name TEXT, admin1 TEXT, country TEXT,
                                 lat REAL, lon REAL, population INTEGER, geonames_zone INTEGER);
            CREATE TABLE country_names (country TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE admin1_names (country TEXT NOT NULL, admin1 TEXT NOT NULL, name TEXT, ascii_name TEXT,
                                       PRIMARY KEY (country, admin1));
            INSERT INTO cities VALUES (3176959, 'Florence', 'Florence', '16', 'IT', 43.77925, 11.24626, 367150, NULL);
            INSERT INTO admin1_names VALUES ('IT', '16', 'Tuscany', 'Tuscany');
        """)
        conn.execute("INSERT INTO country_names VALUES ('IT', ?)", (country_name,))
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO metadata VALUES ('rows', '1')")
        conn.commit()
    return path


def _recorded(monkeypatch, tz, path):
    monkeypatch.setitem(tz.SHIPPED_DATA_SHA256, "atlas.db", hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(tz, "_ATLAS_SEEN", {})
    monkeypatch.setattr(tz, "ATLAS_FOLDED_NAMES", {})


FLORENCE = [("Florence", "16", "IT", 43.77925, 11.24626)]


@pytest.mark.parametrize("missing", ["atlas_keys", "atlas_prefix_results", "places"])
def test_a_file_naming_the_indexed_search_without_its_tables_is_refused_plainly(tz, tmp_path, monkeypatch, missing):
    path = _old_atlas(tmp_path / "atlas.db", "Italy")
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.execute("INSERT INTO metadata VALUES ('app_search_version', '2')")
        for table in {"atlas_keys", "atlas_prefix_results", "places"} - {missing}:
            conn.execute(f"CREATE TABLE {table} (x)")
        conn.commit()
    _recorded(monkeypatch, tz, path)
    with pytest.raises(tz.ShippedDataChanged) as refused:
        tz.atlas_rows(path, "Florence")
    assert str(refused.value) == "atlas.db names the indexed search but does not hold its tables, so it is not read"


def _renamed(path, country_name):
    """The file at `path` with Italy's name in its table of countries
    written `country_name`."""
    with contextlib.closing(sqlite3.connect(path)) as conn:
        assert conn.execute("UPDATE country_names SET name = ? WHERE country = 'IT'", (country_name,)).rowcount == 1
        conn.commit()
    return path


def test_two_atlases_read_in_one_process_answer_each_from_its_own_names(tz, tmp_path, monkeypatch, small_atlas):
    """Two copies of the small atlas, Italy named Italia in the second's
    table of countries, the check passed by for both, as a process reading
    a second file would hold: the second's qualifier is compared with its
    own country names, not the first's."""
    from conftest import small_atlas_copy
    first = small_atlas_copy(small_atlas, tmp_path / "one" / "atlas.db")
    second = _renamed(small_atlas_copy(small_atlas, tmp_path / "two" / "atlas.db"), "Italia")
    monkeypatch.setattr(tz, "_atlas_checked", lambda db_path: None)
    monkeypatch.setattr(tz, "ATLAS_FOLDED_NAMES", {})
    assert tz.atlas_rows(first, "Florence, Italy") == FLORENCE
    assert tz.atlas_rows(second, "Florence, Italia") == tz.atlas_rows(first, "Florence, Italy")
    assert tz.atlas_rows(second, "Florence, Italy") == []
    assert tz.atlas_rows(first, "Florence, Italia") == []
    assert len(tz.ATLAS_FOLDED_NAMES) == 2


def test_a_file_changed_in_place_is_read_afresh(tz, tmp_path, monkeypatch, small_atlas):
    from conftest import small_atlas_copy
    path = small_atlas_copy(small_atlas, tmp_path / "atlas.db")
    monkeypatch.setattr(tz, "_atlas_checked", lambda db_path: None)
    monkeypatch.setattr(tz, "ATLAS_FOLDED_NAMES", {})
    before = tz.atlas_rows(path, "Florence, Italy")
    assert before == FLORENCE
    _renamed(path, "Italia")
    assert tz.atlas_rows(path, "Florence, Italia") == before
    assert tz.atlas_rows(path, "Florence, Italy") == []
