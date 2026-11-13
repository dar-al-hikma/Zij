"""Which places the search counts as a seat of government.

A seat is a country's capital (GeoNames' PPLC), its seat of government
where that is elsewhere (PPLG), or a first-order region's seat (PPLA); the
seat of a lower region is ranked by its population like any other place. The builder's table of short prefixes is written in the
same order as the search ranks a range, so a short text and its full
search give the same options.
"""
import contextlib
import sqlite3

import pytest

import build_atlas as builder
import time_zones as zones
from test_atlas4_builder_2026_10_23 import country_info, make, place

PLACES = [
    place(1, "York", admin1="NE", pop=7864, code="PPLA2"),
    place(2, "New York City", admin1="NY", pop=8000000),
    place(3, "La Paz", country="BO", admin1="04", pop=2000000, code="PPLG"),
    place(4, "La Paz", country="MX", admin1="03", pop=200000, code="PPLA"),
    place(5, "Lapwing", admin1="NE", pop=10, code="PPLA2"),
    place(6, "Laredo", admin1="TX", pop=300000),
    place(7, "Govseat", country="BO", admin1="04", pop=1, code="PPLG"),
    place(8, "Govseat", admin1="TX", pop=1000000),
    place(9, "Lowseat", admin1="TX", pop=5, code="PPLA3"),
    place(10, "Lowseat", admin1="NE", pop=50),
    place(11, "Capseat", country="MX", admin1="09", pop=1, code="PPLC"),
    place(12, "Capseat", admin1="TX", pop=900000),
]
ALTERNATES = [(1, 1, "en", "New York", "", "", "", "", "", ""),
              (2, 2, "en", "New York", "", "", "", "", "", "")]
COUNTRIES = country_info([("US", "United States"), ("BO", "Bolivia"), ("MX", "Mexico")])
ADMIN1 = ("US.NE\tNebraska\tNebraska\t1\nUS.NY\tNew York\tNew York\t2\nUS.TX\tTexas\tTexas\t3\n"
          "BO.04\tLa Paz\tLa Paz\t4\nMX.03\tBaja California Sur\tBaja California Sur\t5\n"
          "MX.09\tMexico City\tMexico City\t6\n")


@pytest.fixture(scope="module")
def atlas(tmp_path_factory):
    """Built at a work budget of nothing, so that every short prefix of
    every name is in the builder's table."""
    root = tmp_path_factory.mktemp("seats")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builder, "APP_CACHE_THRESHOLD", 0)
        path, _summary = make(root, places=PLACES, alternates=ALTERNATES, countries=COUNTRIES, admin1=ADMIN1)
    return path


@pytest.fixture
def conn(atlas, monkeypatch):
    monkeypatch.setitem(zones.SHIPPED_DATA_SHA256, "atlas.db", builder.digest(atlas))
    with contextlib.closing(sqlite3.connect(atlas.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA trusted_schema = OFF")
        yield connection


def ids(conn, text, use_short=True):
    return [r["geonameid"] for r in zones._atlas_search_matches(conn.cursor(), text, use_short)]


def test_a_lower_region_s_seat_found_by_another_name_does_not_come_before_a_more_populous_match(conn):
    # both are exact matches by another of their names; York is the seat
    # of a county (PPLA2), New York City the more populous
    assert ids(conn, "New York") == [2, 1]
    assert ids(conn, "Lowseat") == [10, 9]


def test_a_seat_of_government_that_is_not_the_capital_counts_as_a_seat(conn):
    assert ids(conn, "Govseat") == [7, 8]
    # two seats: the more populous first
    assert ids(conn, "La Paz") == [3, 4]
    assert ids(conn, "Capseat") == [11, 12]


@pytest.mark.parametrize("text, expected", [("La", [3, 4, 6, 5]), ("Lo", [10, 9]), ("G", [7, 8]),
                                            ("Ne", [2, 1]), ("Y", [1])])
def test_the_builder_s_short_prefix_rows_are_in_the_search_s_order(conn, text, expected):
    key = text.lower()
    held = [gid for (gid,) in conn.execute(
        "SELECT k.geonameid FROM atlas_prefix_results c JOIN atlas_keys k ON k.id = c.key_id "
        "WHERE c.kind = 0 AND c.scope = '' AND c.prefix = ? ORDER BY c.rank", (key,))]
    assert held == expected
    assert ids(conn, text) == ids(conn, text, False) == expected


def test_every_short_prefix_s_rows_equal_the_full_range_search(conn):
    prefixes = {(kind, key[:length]) for mask, key in conn.execute("SELECT kinds, key FROM atlas_keys")
                for kind in range(4) if mask & (1 << kind)
                for length in range(1, min(4, len(key)) + 1)}
    scopes = [r[0] for r in conn.execute("SELECT DISTINCT scope FROM atlas_prefix_results")]
    assert len(prefixes) > 50 and len(scopes) > 5
    held = 0
    for kind, prefix in sorted(prefixes):
        for scope in scopes:
            cached = conn.execute("SELECT COUNT(*) FROM atlas_prefix_results WHERE kind = ? AND scope = ? "
                                  "AND prefix = ?", (kind, scope, prefix)).fetchone()[0]
            full = zones._atlas_key_matches(conn.cursor(), kind, prefix, scope, False)
            assert cached in (0, len(full)), (kind, prefix, scope)
            held += bool(cached)
            assert zones._atlas_key_matches(conn.cursor(), kind, prefix, scope) == full, (kind, prefix, scope)
    # every prefix of the whole atlas and of each country is in the table
    assert held > 100
