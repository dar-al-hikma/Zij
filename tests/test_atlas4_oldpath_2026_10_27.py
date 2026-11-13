"""The atlas is read through its indexed search alone.

A file whose metadata does not name the indexed search's version 2 (a file
with no metadata table, or one naming another version) is refused with one
plain sentence and never read: no query of its places is made, though the
file holds the table the earlier lookup read. The names only that lookup
reached are gone from the module and from what it gives the engine.
"""
import contextlib
import hashlib
import sqlite3

import pytest

REFUSED = "atlas.db does not name the indexed search, so it is not read"
REMOVED = ("_like_prefix", "_atlas_coarse", "_atlas_prefixes", "_atlas_looked_up")


@pytest.fixture
def tz():
    import time_zones
    return time_zones


def _earlier_schema(path, version=None, metadata=True):
    """A file of the earlier lookup's schema holding Florence alone, with a
    metadata table naming `version` (none where it is None), or with no
    metadata table at all."""
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.executescript("""
            CREATE TABLE cities (id INTEGER PRIMARY KEY, name TEXT, ascii_name TEXT, admin1 TEXT, country TEXT,
                                 lat REAL, lon REAL, population INTEGER, geonames_zone INTEGER);
            CREATE TABLE country_names (country TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE admin1_names (country TEXT NOT NULL, admin1 TEXT NOT NULL, name TEXT, ascii_name TEXT,
                                       PRIMARY KEY (country, admin1));
            INSERT INTO cities VALUES (3176959, 'Florence', 'Florence', '16', 'IT', 43.77925, 11.24626, 367150, NULL);
            INSERT INTO country_names VALUES ('IT', 'Italy');
            INSERT INTO admin1_names VALUES ('IT', '16', 'Tuscany', 'Tuscany');
        """)
        if metadata:
            conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO metadata VALUES ('rows', '1')")
            if version is not None:
                conn.execute("INSERT INTO metadata VALUES ('app_search_version', ?)", (version,))
        conn.commit()
    return path


@pytest.fixture
def statements(tz, monkeypatch):
    """Every statement a connection the lookup opens runs, in order."""
    seen, real = [], sqlite3.connect

    def connect(*args, **kwargs):
        conn = real(*args, **kwargs)
        conn.set_trace_callback(seen.append)
        return conn
    monkeypatch.setattr(tz.sqlite3, "connect", connect)
    return seen


def _refused_unread(tz, monkeypatch, path, statements, metadata):
    monkeypatch.setitem(tz.SHIPPED_DATA_SHA256, "atlas.db", hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(tz, "_ATLAS_SEEN", {})
    monkeypatch.setattr(tz, "ATLAS_FOLDED_NAMES", {})
    for text in ("Florence", "Florence, Italy", "St. Florence", "Florence (IT)"):
        statements.clear()
        with pytest.raises(tz.ShippedDataChanged) as refused:
            tz.atlas_rows(path, text)
        assert str(refused.value) == REFUSED, text
        assert statements, text
        assert not [s for s in statements if "cities" in s or "country_names" in s or "admin1_names" in s], (
            text, statements)
        assert [s for s in statements if not s.startswith("PRAGMA")] == [
            "SELECT name FROM sqlite_master WHERE type = 'table'"] + (
            ["SELECT value FROM metadata WHERE key = 'app_search_version'"]
            if metadata else []), (text, statements)


def test_a_file_without_a_metadata_table_is_refused_and_never_read(tz, tmp_path, monkeypatch, statements):
    path = _earlier_schema(tmp_path / "atlas.db", metadata=False)
    _refused_unread(tz, monkeypatch, path, statements, metadata=False)


@pytest.mark.parametrize("version", [None, "1", "3", "02", "two"])
def test_a_file_naming_another_version_is_refused_and_never_read(tz, tmp_path, monkeypatch, statements, version):
    path = _earlier_schema(tmp_path / "atlas.db", version)
    _refused_unread(tz, monkeypatch, path, statements, metadata=True)


def test_the_engine_is_given_no_name_of_the_earlier_lookup(tz):
    assert not set(REMOVED) & set(tz.__all__)
    assert not [name for name in REMOVED if hasattr(tz, name)]
