"""The clocks particular places kept before 1970, cast from a table of their own.

The time-zone database keeps a full zone's history before 1970 for the place
the zone is named after, so every Minnesota place was cast at Chicago's
record. Research gives thirteen Minnesota places their own clocks for each
year from 1918 to 1969 (data/place_clocks.tsv, generated from it and never
edited by hand): summer time on other dates, a summer without it (Moorhead,
1965), and stretches whose clock the sources do not settle. A Standard-time
cast at such a place's exact atlas coordinates, in a researched year, is made
from those clocks alone; in a disputed stretch it is refused and the birth
record's offset asked for, in the sentence a place whose clock the sources
leave open already has. The caution that the zone's record is another
place's steps back there. Another pair, another year, and a caller with no
coordinates read the zone's record as before.
"""
import re
import sqlite3
from datetime import datetime, time, timedelta, timezone

import pytest

from conftest import APP_PATH, assert_no_exception, make_app
from engine import TIME_STANDARD_OPTIONS

ROOT = APP_PATH.parent
DATA = ROOT / "data" / "place_clocks.tsv"
CHICAGO = "America/Chicago"
MANUAL = TIME_STANDARD_OPTIONS[2]
SENTENCE = ("Before 1970 this zone's record is Chicago's; where the birth record gives the offset, "
            "use Manual UTC offset.")
# The atlas pairs (lat, lon) of the places these tests read, and of two the
# research does not reach.
MINNEAPOLIS = (44.97997, -93.26384)
DULUTH = (46.78327, -92.10658)
MOORHEAD = (46.87386, -96.76951)
ROCHESTER = (44.02163, -92.4699)
WINONA = (44.04996, -91.63932)
WEST_SAINT_PAUL = (44.91608, -93.10161)
STILLWATER = (45.05636, -92.80604)
CHICAGO_CITY = (41.85003, -87.65005)
MANKATO = (44.15906, -94.00915)
NOON_1965 = (1965, 5, 10, 12, 0, 0)
# Minnesota's thirteen places, by GeoNames id: name, atlas pair, the number
# of its intervals and of its disputed stretches. The table may hold other
# places beside them; its counts are read from the file.
MINNESOTA = {
    '5018739': ('Bloomington', (44.8408, -93.29828), 85, 0),
    '5022025': ('Coon Rapids', (45.11997, -93.28773), 85, 0),
    '5024719': ('Duluth', (46.78327, -92.10658), 89, 0),
    '5030005': ('Hibbing', (47.42715, -92.93769), 85, 0),
    '5031404': ('International Falls', (48.60105, -93.41098), 85, 0),
    '5037649': ('Minneapolis', (44.97997, -93.26384), 85, 0),
    '5038108': ('Moorhead', (46.87386, -96.76951), 83, 0),
    '5043473': ('Rochester', (44.02163, -92.4699), 86, 1),
    '5044407': ('Saint Cloud', (45.5608, -94.16249), 85, 0),
    '5045360': ('Saint Paul', (44.94441, -93.09327), 85, 0),
    '5048814': ('Stillwater', (45.05636, -92.80604), 86, 1),
    '5052467': ('West Saint Paul', (44.91608, -93.10161), 86, 1),
    '5053156': ('Winona', (44.04996, -91.63932), 87, 2),
}


def _file_rows():
    """The file's rows, each its cells, read here from its text."""
    lines = [line for line in DATA.read_text(encoding="utf-8").split("\n") if line and not line.startswith("#")]
    assert lines[0].split("\t")[0] == "lat" and len(lines) > 1
    return [line.split("\t") for line in lines[1:]]


@pytest.fixture(scope="module")
def tz():
    import time_zones
    return time_zones


def _place(tz, point):
    place = tz.PLACE_CLOCKS[point]
    assert place["zone"] == CHICAGO
    return place


def _ut_text(instant):
    assert instant.tzinfo is timezone.utc
    return f"{instant:%Y-%m-%d %H:%M}"


def _local_text(reading):
    return "%04d-%02d-%02d %02d:%02d" % reading[:5]


# --- the hand tables -------------------------------------------------------------
#
# Each row: (from, to) as the file writes them, the offset and abbreviation
# (empty for a disputed stretch), and (from, to) in UT, worked by hand from
# the file's rule: each end is read on the clock of the interval that ends
# there (a change to summer time at its hour of standard time, a return at
# its hour of summer time), or, where that one is disputed or there is none,
# on the clock of the one that begins there. Standard time is six hours
# behind UT; summer, war and peace time five.

# Minneapolis, every row, 1918-1969.
MINNEAPOLIS_ROWS = [
    ("1918-01-01 00:00", "1918-03-31 02:00", "-06:00", "CST", "1918-01-01 06:00", "1918-03-31 08:00"),
    ("1918-03-31 02:00", "1918-10-27 02:00", "-05:00", "CDT", "1918-03-31 08:00", "1918-10-27 07:00"),
    ("1918-10-27 02:00", "1919-01-01 00:00", "-06:00", "CST", "1918-10-27 07:00", "1919-01-01 06:00"),
    ("1919-01-01 00:00", "1919-03-30 02:00", "-06:00", "CST", "1919-01-01 06:00", "1919-03-30 08:00"),
    ("1919-03-30 02:00", "1919-10-26 02:00", "-05:00", "CDT", "1919-03-30 08:00", "1919-10-26 07:00"),
    ("1919-10-26 02:00", "1920-01-01 00:00", "-06:00", "CST", "1919-10-26 07:00", "1920-01-01 06:00"),
    ("1920-01-01 00:00", "1921-01-01 00:00", "-06:00", "CST", "1920-01-01 06:00", "1921-01-01 06:00"),
    ("1921-01-01 00:00", "1922-01-01 00:00", "-06:00", "CST", "1921-01-01 06:00", "1922-01-01 06:00"),
    ("1922-01-01 00:00", "1923-01-01 00:00", "-06:00", "CST", "1922-01-01 06:00", "1923-01-01 06:00"),
    ("1923-01-01 00:00", "1924-01-01 00:00", "-06:00", "CST", "1923-01-01 06:00", "1924-01-01 06:00"),
    ("1924-01-01 00:00", "1925-01-01 00:00", "-06:00", "CST", "1924-01-01 06:00", "1925-01-01 06:00"),
    ("1925-01-01 00:00", "1926-01-01 00:00", "-06:00", "CST", "1925-01-01 06:00", "1926-01-01 06:00"),
    ("1926-01-01 00:00", "1927-01-01 00:00", "-06:00", "CST", "1926-01-01 06:00", "1927-01-01 06:00"),
    ("1927-01-01 00:00", "1928-01-01 00:00", "-06:00", "CST", "1927-01-01 06:00", "1928-01-01 06:00"),
    ("1928-01-01 00:00", "1929-01-01 00:00", "-06:00", "CST", "1928-01-01 06:00", "1929-01-01 06:00"),
    ("1929-01-01 00:00", "1930-01-01 00:00", "-06:00", "CST", "1929-01-01 06:00", "1930-01-01 06:00"),
    ("1930-01-01 00:00", "1931-01-01 00:00", "-06:00", "CST", "1930-01-01 06:00", "1931-01-01 06:00"),
    ("1931-01-01 00:00", "1932-01-01 00:00", "-06:00", "CST", "1931-01-01 06:00", "1932-01-01 06:00"),
    ("1932-01-01 00:00", "1933-01-01 00:00", "-06:00", "CST", "1932-01-01 06:00", "1933-01-01 06:00"),
    ("1933-01-01 00:00", "1934-01-01 00:00", "-06:00", "CST", "1933-01-01 06:00", "1934-01-01 06:00"),
    ("1934-01-01 00:00", "1935-01-01 00:00", "-06:00", "CST", "1934-01-01 06:00", "1935-01-01 06:00"),
    ("1935-01-01 00:00", "1936-01-01 00:00", "-06:00", "CST", "1935-01-01 06:00", "1936-01-01 06:00"),
    ("1936-01-01 00:00", "1937-01-01 00:00", "-06:00", "CST", "1936-01-01 06:00", "1937-01-01 06:00"),
    ("1937-01-01 00:00", "1938-01-01 00:00", "-06:00", "CST", "1937-01-01 06:00", "1938-01-01 06:00"),
    ("1938-01-01 00:00", "1939-01-01 00:00", "-06:00", "CST", "1938-01-01 06:00", "1939-01-01 06:00"),
    ("1939-01-01 00:00", "1940-01-01 00:00", "-06:00", "CST", "1939-01-01 06:00", "1940-01-01 06:00"),
    ("1940-01-01 00:00", "1941-01-01 00:00", "-06:00", "CST", "1940-01-01 06:00", "1941-01-01 06:00"),
    ("1941-01-01 00:00", "1942-01-01 00:00", "-06:00", "CST", "1941-01-01 06:00", "1942-01-01 06:00"),
    ("1942-01-01 00:00", "1942-02-09 02:00", "-06:00", "CST", "1942-01-01 06:00", "1942-02-09 08:00"),
    ("1942-02-09 02:00", "1943-01-01 00:00", "-05:00", "CWT", "1942-02-09 08:00", "1943-01-01 05:00"),
    ("1943-01-01 00:00", "1944-01-01 00:00", "-05:00", "CWT", "1943-01-01 05:00", "1944-01-01 05:00"),
    ("1944-01-01 00:00", "1945-01-01 00:00", "-05:00", "CWT", "1944-01-01 05:00", "1945-01-01 05:00"),
    ("1945-01-01 00:00", "1945-08-14 18:00", "-05:00", "CWT", "1945-01-01 05:00", "1945-08-14 23:00"),
    ("1945-08-14 18:00", "1945-09-30 02:00", "-05:00", "CPT", "1945-08-14 23:00", "1945-09-30 07:00"),
    ("1945-09-30 02:00", "1946-01-01 00:00", "-06:00", "CST", "1945-09-30 07:00", "1946-01-01 06:00"),
    ("1946-01-01 00:00", "1947-01-01 00:00", "-06:00", "CST", "1946-01-01 06:00", "1947-01-01 06:00"),
    ("1947-01-01 00:00", "1948-01-01 00:00", "-06:00", "CST", "1947-01-01 06:00", "1948-01-01 06:00"),
    ("1948-01-01 00:00", "1949-01-01 00:00", "-06:00", "CST", "1948-01-01 06:00", "1949-01-01 06:00"),
    ("1949-01-01 00:00", "1950-01-01 00:00", "-06:00", "CST", "1949-01-01 06:00", "1950-01-01 06:00"),
    ("1950-01-01 00:00", "1951-01-01 00:00", "-06:00", "CST", "1950-01-01 06:00", "1951-01-01 06:00"),
    ("1951-01-01 00:00", "1952-01-01 00:00", "-06:00", "CST", "1951-01-01 06:00", "1952-01-01 06:00"),
    ("1952-01-01 00:00", "1953-01-01 00:00", "-06:00", "CST", "1952-01-01 06:00", "1953-01-01 06:00"),
    ("1953-01-01 00:00", "1954-01-01 00:00", "-06:00", "CST", "1953-01-01 06:00", "1954-01-01 06:00"),
    ("1954-01-01 00:00", "1955-01-01 00:00", "-06:00", "CST", "1954-01-01 06:00", "1955-01-01 06:00"),
    ("1955-01-01 00:00", "1956-01-01 00:00", "-06:00", "CST", "1955-01-01 06:00", "1956-01-01 06:00"),
    ("1956-01-01 00:00", "1957-01-01 00:00", "-06:00", "CST", "1956-01-01 06:00", "1957-01-01 06:00"),
    ("1957-01-01 00:00", "1957-04-28 02:00", "-06:00", "CST", "1957-01-01 06:00", "1957-04-28 08:00"),
    ("1957-04-28 02:00", "1957-09-29 02:00", "-05:00", "CDT", "1957-04-28 08:00", "1957-09-29 07:00"),
    ("1957-09-29 02:00", "1958-01-01 00:00", "-06:00", "CST", "1957-09-29 07:00", "1958-01-01 06:00"),
    ("1958-01-01 00:00", "1958-04-27 02:00", "-06:00", "CST", "1958-01-01 06:00", "1958-04-27 08:00"),
    ("1958-04-27 02:00", "1958-09-02 02:00", "-05:00", "CDT", "1958-04-27 08:00", "1958-09-02 07:00"),
    ("1958-09-02 02:00", "1959-01-01 00:00", "-06:00", "CST", "1958-09-02 07:00", "1959-01-01 06:00"),
    ("1959-01-01 00:00", "1959-04-26 02:00", "-06:00", "CST", "1959-01-01 06:00", "1959-04-26 08:00"),
    ("1959-04-26 02:00", "1959-09-27 02:00", "-05:00", "CDT", "1959-04-26 08:00", "1959-09-27 07:00"),
    ("1959-09-27 02:00", "1960-01-01 00:00", "-06:00", "CST", "1959-09-27 07:00", "1960-01-01 06:00"),
    ("1960-01-01 00:00", "1960-05-22 02:00", "-06:00", "CST", "1960-01-01 06:00", "1960-05-22 08:00"),
    ("1960-05-22 02:00", "1960-09-06 02:00", "-05:00", "CDT", "1960-05-22 08:00", "1960-09-06 07:00"),
    ("1960-09-06 02:00", "1961-01-01 00:00", "-06:00", "CST", "1960-09-06 07:00", "1961-01-01 06:00"),
    ("1961-01-01 00:00", "1961-05-28 02:00", "-06:00", "CST", "1961-01-01 06:00", "1961-05-28 08:00"),
    ("1961-05-28 02:00", "1961-09-05 02:00", "-05:00", "CDT", "1961-05-28 08:00", "1961-09-05 07:00"),
    ("1961-09-05 02:00", "1962-01-01 00:00", "-06:00", "CST", "1961-09-05 07:00", "1962-01-01 06:00"),
    ("1962-01-01 00:00", "1962-05-27 02:00", "-06:00", "CST", "1962-01-01 06:00", "1962-05-27 08:00"),
    ("1962-05-27 02:00", "1962-09-04 02:00", "-05:00", "CDT", "1962-05-27 08:00", "1962-09-04 07:00"),
    ("1962-09-04 02:00", "1963-01-01 00:00", "-06:00", "CST", "1962-09-04 07:00", "1963-01-01 06:00"),
    ("1963-01-01 00:00", "1963-05-26 02:00", "-06:00", "CST", "1963-01-01 06:00", "1963-05-26 08:00"),
    ("1963-05-26 02:00", "1963-09-03 02:00", "-05:00", "CDT", "1963-05-26 08:00", "1963-09-03 07:00"),
    ("1963-09-03 02:00", "1964-01-01 00:00", "-06:00", "CST", "1963-09-03 07:00", "1964-01-01 06:00"),
    ("1964-01-01 00:00", "1964-05-24 02:00", "-06:00", "CST", "1964-01-01 06:00", "1964-05-24 08:00"),
    ("1964-05-24 02:00", "1964-09-08 02:00", "-05:00", "CDT", "1964-05-24 08:00", "1964-09-08 07:00"),
    ("1964-09-08 02:00", "1965-01-01 00:00", "-06:00", "CST", "1964-09-08 07:00", "1965-01-01 06:00"),
    ("1965-01-01 00:00", "1965-05-23 02:00", "-06:00", "CST", "1965-01-01 06:00", "1965-05-23 08:00"),
    ("1965-05-23 02:00", "1965-09-07 02:00", "-05:00", "CDT", "1965-05-23 08:00", "1965-09-07 07:00"),
    ("1965-09-07 02:00", "1966-01-01 00:00", "-06:00", "CST", "1965-09-07 07:00", "1966-01-01 06:00"),
    ("1966-01-01 00:00", "1966-04-24 02:00", "-06:00", "CST", "1966-01-01 06:00", "1966-04-24 08:00"),
    ("1966-04-24 02:00", "1966-10-30 02:00", "-05:00", "CDT", "1966-04-24 08:00", "1966-10-30 07:00"),
    ("1966-10-30 02:00", "1967-01-01 00:00", "-06:00", "CST", "1966-10-30 07:00", "1967-01-01 06:00"),
    ("1967-01-01 00:00", "1967-04-30 02:00", "-06:00", "CST", "1967-01-01 06:00", "1967-04-30 08:00"),
    ("1967-04-30 02:00", "1967-10-29 02:00", "-05:00", "CDT", "1967-04-30 08:00", "1967-10-29 07:00"),
    ("1967-10-29 02:00", "1968-01-01 00:00", "-06:00", "CST", "1967-10-29 07:00", "1968-01-01 06:00"),
    ("1968-01-01 00:00", "1968-04-28 02:00", "-06:00", "CST", "1968-01-01 06:00", "1968-04-28 08:00"),
    ("1968-04-28 02:00", "1968-10-27 02:00", "-05:00", "CDT", "1968-04-28 08:00", "1968-10-27 07:00"),
    ("1968-10-27 02:00", "1969-01-01 00:00", "-06:00", "CST", "1968-10-27 07:00", "1969-01-01 06:00"),
    ("1969-01-01 00:00", "1969-04-27 02:00", "-06:00", "CST", "1969-01-01 06:00", "1969-04-27 08:00"),
    ("1969-04-27 02:00", "1969-10-26 02:00", "-05:00", "CDT", "1969-04-27 08:00", "1969-10-26 07:00"),
    ("1969-10-26 02:00", "1970-01-01 00:00", "-06:00", "CST", "1969-10-26 07:00", "1970-01-01 06:00"),
]
# Duluth 1964: summer time from 3 May to 27 September, as Wisconsin kept it.
DULUTH_1964 = [
    ("1964-01-01 00:00", "1964-05-03 02:00", "-06:00", "CST", "1964-01-01 06:00", "1964-05-03 08:00"),
    ("1964-05-03 02:00", "1964-09-27 02:00", "-05:00", "CDT", "1964-05-03 08:00", "1964-09-27 07:00"),
    ("1964-09-27 02:00", "1965-01-01 00:00", "-06:00", "CST", "1964-09-27 07:00", "1965-01-01 06:00"),
]
# Moorhead 1965: standard time all year.
MOORHEAD_1965 = [
    ("1965-01-01 00:00", "1966-01-01 00:00", "-06:00", "CST", "1965-01-01 06:00", "1966-01-01 06:00"),
]
# Winona 1964: two disputed stretches, the first ending in a change to
# summer time and read there on summer time, the second ending in a return
# and read there on standard time.
WINONA_1964 = [
    ("1964-01-01 00:00", "1964-04-26 02:00", "-06:00", "CST", "1964-01-01 06:00", "1964-04-26 08:00"),
    ("1964-04-26 02:00", "1964-05-24 02:00", "", "", "1964-04-26 08:00", "1964-05-24 07:00"),
    ("1964-05-24 02:00", "1964-09-08 02:00", "-05:00", "CDT", "1964-05-24 07:00", "1964-09-08 07:00"),
    ("1964-09-08 02:00", "1964-10-25 02:00", "", "", "1964-09-08 07:00", "1964-10-25 08:00"),
    ("1964-10-25 02:00", "1965-01-01 00:00", "-06:00", "CST", "1964-10-25 08:00", "1965-01-01 06:00"),
]
ROCHESTER_1959 = [
    ("1959-01-01 00:00", "1959-04-26 02:00", "-06:00", "CST", "1959-01-01 06:00", "1959-04-26 08:00"),
    ("1959-04-26 02:00", "1959-05-24 02:00", "", "", "1959-04-26 08:00", "1959-05-24 07:00"),
    ("1959-05-24 02:00", "1959-09-08 02:00", "-05:00", "CDT", "1959-05-24 07:00", "1959-09-08 07:00"),
    ("1959-09-08 02:00", "1960-01-01 00:00", "-06:00", "CST", "1959-09-08 07:00", "1960-01-01 06:00"),
]
# West Saint Paul 1965: a disputed stretch ending at midnight.
WEST_SAINT_PAUL_1965 = [
    ("1965-01-01 00:00", "1965-04-25 02:00", "-06:00", "CST", "1965-01-01 06:00", "1965-04-25 08:00"),
    ("1965-04-25 02:00", "1965-05-11 00:00", "", "", "1965-04-25 08:00", "1965-05-11 05:00"),
    ("1965-05-11 00:00", "1965-09-07 02:00", "-05:00", "CDT", "1965-05-11 05:00", "1965-09-07 07:00"),
    ("1965-09-07 02:00", "1966-01-01 00:00", "-06:00", "CST", "1965-09-07 07:00", "1966-01-01 06:00"),
]
STILLWATER_1959 = [
    ("1959-01-01 00:00", "1959-04-26 02:00", "-06:00", "CST", "1959-01-01 06:00", "1959-04-26 08:00"),
    ("1959-04-26 02:00", "1959-05-24 02:00", "", "", "1959-04-26 08:00", "1959-05-24 07:00"),
    ("1959-05-24 02:00", "1959-09-08 02:00", "-05:00", "CDT", "1959-05-24 07:00", "1959-09-08 07:00"),
    ("1959-09-08 02:00", "1960-01-01 00:00", "-06:00", "CST", "1959-09-08 07:00", "1960-01-01 06:00"),
]
HAND_TABLES = {
    "Minneapolis": (MINNEAPOLIS, None, MINNEAPOLIS_ROWS),
    "Duluth-1964": (DULUTH, 1964, DULUTH_1964),
    "Moorhead-1965": (MOORHEAD, 1965, MOORHEAD_1965),
    "Winona-1964": (WINONA, 1964, WINONA_1964),
    "Rochester-1959": (ROCHESTER, 1959, ROCHESTER_1959),
    "West-Saint-Paul-1965": (WEST_SAINT_PAUL, 1965, WEST_SAINT_PAUL_1965),
    "Stillwater-1959": (STILLWATER, 1959, STILLWATER_1959),
}


@pytest.mark.parametrize("which", sorted(HAND_TABLES))
def test_every_end_is_in_ut_as_the_hand_table_works_it(tz, which):
    point, year, expected = HAND_TABLES[which]
    intervals = [i for i in _place(tz, point)["intervals"] if year is None or i["from_local"][0] == year]
    got = [(_local_text(i["from_local"]), _local_text(i["to_local"]),
            "" if i["offset_seconds"] is None else "%s%02d:00" % ("-" if i["offset_seconds"] < 0 else "+",
                                                                 abs(i["offset_seconds"]) // 3600),
            i["abbreviation"], _ut_text(i["from"]), _ut_text(i["to"])) for i in intervals]
    assert got == expected


def test_minneapolis_is_researched_from_1918_to_1969_and_its_rows_abut_in_ut(tz):
    place = _place(tz, MINNEAPOLIS)
    assert len(MINNEAPOLIS_ROWS) == len(place["intervals"]) == 85
    assert place["years"] == frozenset(range(1918, 1970))
    assert place["geonameid"] == "5037649" and place["name"] == "Minneapolis"
    pairs = list(zip(place["intervals"], place["intervals"][1:]))
    assert len(pairs) == 84
    for a, b in pairs:
        assert a["to"] == b["from"] and a["to_local"] == b["from_local"]


def test_the_disputed_stretches_lie_between_the_clocks_either_side(tz):
    stretches = [(p["name"], i["from_local"][0], i["offsets"]) for p in tz.PLACE_CLOCKS.values()
                 if p["geonameid"] in MINNESOTA for i in p["intervals"] if i["kind"] == "disputed"]
    assert sorted((name, year) for name, year, _offsets in stretches) == [
        ("Rochester", 1959), ("Stillwater", 1959), ("West Saint Paul", 1965), ("Winona", 1964), ("Winona", 1964)]
    assert {offsets for _name, _year, offsets in stretches} == {(-21600, -18000)}
    # At every place, a stretch's clocks are those of the rows that meet it.
    beside = []
    for place in tz.PLACE_CLOCKS.values():
        intervals = place["intervals"]
        for n, interval in enumerate(intervals):
            if interval["kind"] == "disputed":
                meeting = [other["offset_seconds"] for other in intervals[max(n - 1, 0):n] + intervals[n + 1:n + 2]
                           if other["kind"] == "clock" and (other["to_local"] == interval["from_local"]
                                                            or other["from_local"] == interval["to_local"])]
                beside.append((interval["offsets"], tuple(sorted(set(meeting)))))
    assert len(beside) == sum(row[9] == "disputed" for row in _file_rows()) >= 5
    assert [got for got, expected in beside if got != expected] == []


# --- the one function that reads an end ---------------------------------------------

def _interval(kind, hours=None):
    return {"kind": kind, "offset_seconds": None if hours is None else hours * 3600}


@pytest.mark.parametrize("ending, beginning, hours", [
    (_interval("clock", -6), _interval("clock", -5), -6),      # a change to summer time: standard time's hour
    (_interval("clock", -5), _interval("clock", -6), -5),      # a return: summer time's hour
    (_interval("disputed"), _interval("clock", -5), -5),       # after a disputed stretch: the clock after it
    (_interval("clock", -6), _interval("disputed"), -6),       # into one: the clock before it
    (None, _interval("clock", -6), -6),                         # a place's first end: its own clock
    (_interval("clock", -6), None, -6),                         # its last
])
def test_an_end_is_read_on_the_clock_in_force(tz, ending, beginning, hours):
    assert tz._clock_in_force(ending, beginning) == hours * 3600


@pytest.mark.parametrize("ending, beginning", [(None, _interval("disputed")), (_interval("disputed"), None),
                                               (_interval("disputed"), _interval("disputed"))])
def test_an_end_with_no_clock_to_read_it_on_is_refused(tz, ending, beginning):
    with pytest.raises(ValueError, match="no clock on either side"):
        tz._clock_in_force(ending, beginning)


# --- the load --------------------------------------------------------------------------

def test_the_table_holds_its_places_each_at_its_atlas_pair_and_in_its_boundaries_zone(tz):
    """The places, intervals and disputed stretches the file's rows give;
    Minnesota's thirteen among them, each as it was researched; and every
    place at its atlas row's pair, in the zone the boundaries give it there,
    in no row of the list of places' zones, researched in the years its rows
    cover."""
    rows = _file_rows()
    covered = {}
    for row in rows:
        start, end = int(row[5][:4]), int(row[6][:4]) - (row[6][5:] == "01-01 00:00")
        covered.setdefault((float(row[0]), float(row[1])), set()).update(range(start, end + 1))
    assert len(tz.PLACE_CLOCKS) == len(covered) >= 13
    assert sum(len(p["intervals"]) for p in tz.PLACE_CLOCKS.values()) == len(rows) >= 1112
    assert sum(i["kind"] == "disputed" for p in tz.PLACE_CLOCKS.values() for i in p["intervals"]) == sum(
        row[9] == "disputed" for row in rows) >= 5
    minnesota = {place["geonameid"]: (place["name"], key, len(place["intervals"]),
                                      sum(i["kind"] == "disputed" for i in place["intervals"]))
                 for key, place in tz.PLACE_CLOCKS.items() if place["geonameid"] in MINNESOTA}
    assert minnesota == MINNESOTA
    from timezonefinder import TimezoneFinder
    finder = TimezoneFinder()
    places = list(tz.PLACE_CLOCKS.items())
    assert len(places) >= 13
    seen = {}
    with sqlite3.connect(f"file:{ROOT / 'atlas.db'}?mode=ro", uri=True) as atlas:
        for (lat, lon), place in places:
            row = atlas.execute("SELECT lat, lon, country, admin1 FROM cities WHERE id = ?",
                                (int(place["geonameid"]),)).fetchall()
            assert [r[:2] for r in row] == [(lat, lon)], place["name"]
            assert finder.timezone_at(lng=lon, lat=lat) == place["zone"], place["name"]
            assert (lat, lon) not in tz.PLACE_ZONES, place["name"]
            assert place["years"] == frozenset(covered[(lat, lon)]), place["name"]
            seen[place["geonameid"]] = (row[0][2:], place["zone"], place["years"])
    atlas.close()
    assert {gid: seen[gid] for gid in MINNESOTA} == {gid: (("US", "MN"), CHICAGO, frozenset(range(1918, 1970)))
                                                    for gid in MINNESOTA}


def test_every_place_year_names_documents_the_program_holds(tz):
    intervals = [(place["name"], interval) for place in tz.PLACE_CLOCKS.values() for interval in place["intervals"]]
    assert len(intervals) >= 1112
    assert len(intervals) == len(_file_rows())
    for name, interval in intervals:
        assert interval["sources"] and set(interval["sources"]) <= set(tz.PRE1970_SOURCES), name


_PAGE = "official or library scan, read on the page image"
_MIRROR = "unofficial mirror of the official text"
_RETAINED = "commercial facsimile, read on the researcher's retained copy"
SHANKS = ("SHANKSAAMN1P269", "SHANKSAAMN2P269", "SHANKSAAMN3P269", "SHANKSAAMN5P269", "SHANKSAAMN7P269")


def test_the_places_documents_are_read_as_their_checks_found_them(tz):
    """Their statuses, from the closed list: every one read on its page image
    but the two court decisions (an unofficial mirror of the official text)
    and The American Atlas (read on the researcher's retained copy), and the
    act of 1966, which the program already held."""
    used = {sid for p in tz.PLACE_CLOCKS.values() if p["geonameid"] in MINNESOTA for i in p["intervals"]
            for sid in i["sources"]}
    statuses = {sid: tz.PRE1970_SOURCES[sid][1] for sid in used}
    expected = {sid: _PAGE for sid in used}
    expected.update({"MNSC1959AMUSEMENT": _MIRROR, "MNSC1959LORD": _MIRROR,
                     "US1966TIME": "official or library scan, read in its text layer, then checked"})
    expected.update({sid: _RETAINED for sid in SHANKS})
    assert len(used) == 68 and statuses == expected


def test_the_american_atlas_is_cited_by_edition_printing_page_and_table(tz):
    for sid in SHANKS:
        title = tz.PRE1970_SOURCES[sid][0]
        table = sid[len("SHANKSAA"):-len("P269")]
        assert title == ("Shanks, The American Atlas, fifth edition (1990), sixth printing (1992), p 269, "
                         f"table {table[:2]} #{table[2:]}"), title


# What only the research's own records write, never a document's title: its
# words for its own work; the names of the columns its records keep, each
# written with an underscore as a column's name is (the place's and the
# document's ids, the dates and clocks read, the pages, the quotes and the
# witnesses, how a page was read); and the forms of its own ids (capitals, a
# hyphen, S and a number; and a packet of lines' id: two capitals naming its
# kind, an underscore, then capitals and digits in parts joined by
# underscores). A title may name a document called a register (the Federal
# Register, a state's Register and Manual, a newspaper) or a packet (a
# council's or a planning commission's meeting packet), or hold a headline's
# words; it may not hold these.
RESEARCH_OWN_COLUMNS = ("end_witnesses", "engine_id", "from_date", "geographic_scope", "geonames_id", "gnis_id",
                        "in_engine", "law_id", "local_date", "local_departures", "local_time", "offset_after",
                        "pdf_page", "place_id", "printed_page", "quote_id", "quote_source", "read_on_image",
                        "register_id", "same_as", "source_id", "source_ids", "standard_offset", "start_witnesses",
                        "status_proposed", "summer_end", "summer_rule", "summer_start", "to_date",
                        "url_or_archive_id", "vs_zone", "witness_id", "witness_ids")
RESEARCH_OWN_WORDS = ("trial", "research packet", "sister packet", "sol packet", "packet id", "packet source",
                      "wave 1 packet", "wave 2 packet", "witness", "register id", "register row", "research register",
                      "url_or_archive", "blind check", "re-check", "checker", "check round", "checked by", "sol's",
                      "sol review") + RESEARCH_OWN_COLUMNS
RESEARCH_OWN_ID = re.compile(r"\b[A-Z][A-Z_]*-S\d+\b")
RESEARCH_OWN_PACKET_ID = re.compile(r"\b(?:EC|CM|MP)_[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\b")
# A title ends in a stop only where its last word is an initial or an
# initialism, each letter followed by its stop (a judge's "J.", a vice
# chancellor's "V.C.", a signature's "R.T.", a clock's "A.M."). These titles
# do.
INITIALS_AT_THE_END = re.compile(r"(?<![\w.])(?:[A-Z]\.)+$")
TITLES_ENDING_IN_INITIALS = {
    "CA1948S017",
    # Ends in a chapter's letter and a stop, which the rule reads as an
    # initial.
    "IN1970S030",
    "NJ1935S003", "NY1921S024", "TN1946S003", "US1926S004",
}


def test_the_titles_name_documents_not_the_research_s_own_records(tz):
    used = {sid for p in tz.PLACE_CLOCKS.values() for i in p["intervals"] for sid in i["sources"]}
    assert len(used) >= 68
    assert used == {sid for row in _file_rows() for sid in row[10].split(";")}
    stopped = set()
    for sid in used:
        title = tz.PRE1970_SOURCES[sid][0]
        lowered = title.lower()
        assert [word for word in RESEARCH_OWN_WORDS if word in lowered] == [], (sid, title)
        assert not RESEARCH_OWN_ID.search(title), (sid, title)
        assert not RESEARCH_OWN_PACKET_ID.search(title), (sid, title)
        assert ":" not in sid, sid
        if title.endswith("."):
            assert INITIALS_AT_THE_END.search(title), (sid, title)
            stopped.add(sid)
    assert stopped == TITLES_ENDING_IN_INITIALS
    # A story with no address of its own is found by the page it shares.
    title = tz.PRE1970_SOURCES["STCDT19590427TCT"][0]
    assert "p 1" in title and "Dell Blasts Twin City Defiance on Time Ban" in title


def _changed(lines, change):
    """The file's text with `change` applied to its list of lines."""
    lines = list(lines)
    change(lines)
    return ("\n".join(lines) + "\n").encode("utf-8")


def _row_index(lines, name, start):
    found = [n for n, line in enumerate(lines) if not line.startswith("#")
             and line.split("\t")[3:4] == [name] and line.split("\t")[5] == start]
    assert len(found) == 1, (name, start)
    return found[0]


def _set_cell(lines, name, start, column, value):
    n = _row_index(lines, name, start)
    cells = lines[n].split("\t")
    cells[column] = value
    lines[n] = "\t".join(cells)


def _header(lines):
    return next(n for n, line in enumerate(lines) if not line.startswith("#"))


# Each a change to the file and a phrase of the sentence the import stops with.
MALFORMED = {
    "a header renamed": (lambda ls: ls.__setitem__(_header(ls), ls[_header(ls)].replace("source_ids", "sources")),
                         "its header is not the columns"),
    "a cell dropped": (lambda ls: ls.__setitem__(_header(ls) + 1, ls[_header(ls) + 1].rsplit("\t", 1)[0]),
                       "has 10 columns, not 11"),
    "a kind it does not read": (lambda ls: _set_cell(ls, "Minneapolis", "1965-05-23 02:00", 9, "summer"),
                                "a kind, offset and abbreviation"),
    "a clock with no abbreviation": (lambda ls: _set_cell(ls, "Minneapolis", "1965-05-23 02:00", 8, ""),
                                     "a kind, offset and abbreviation"),
    "a disputed stretch with an offset": (lambda ls: _set_cell(ls, "Winona", "1964-04-26 02:00", 7, "-06:00"),
                                          "a kind, offset and abbreviation"),
    "an offset without its zero": (lambda ls: _set_cell(ls, "Minneapolis", "1965-05-23 02:00", 7, "-5:00"),
                                   "is not an offset written +HH:MM"),
    "an offset of sixty minutes": (lambda ls: _set_cell(ls, "Minneapolis", "1965-05-23 02:00", 7, "-05:60"),
                                   "is not an offset written +HH:MM"),
    "a source it does not hold": (lambda ls: _set_cell(ls, "Minneapolis", "1965-05-23 02:00", 10, "NOSUCH1965"),
                                  "a source the program does not hold"),
    "a pair the atlas does not write so": (lambda ls: _set_cell(ls, "Minneapolis", "1965-05-23 02:00", 0,
                                                                "44.979970"),
                                           "not written as the atlas writes"),
    "an hour without its zero": (lambda ls: _set_cell(ls, "Minneapolis", "1965-05-23 02:00", 5, "1965-05-23 2:00"),
                                 "is not a local date and time"),
    "a row dropped": (lambda ls: ls.pop(_row_index(ls, "Minneapolis", "1965-05-23 02:00")),
                      "does not follow the place's last one"),
    "a row past its year's end": (lambda ls: (_set_cell(ls, "Minneapolis", "1964-09-08 02:00", 6, "1965-05-23 02:00"),
                                              ls.pop(_row_index(ls, "Minneapolis", "1965-01-01 00:00"))),
                                  "does not follow the place's last one"),
    "a first year begun late": (lambda ls: ls.pop(_row_index(ls, "Minneapolis", "1918-01-01 00:00")),
                                "a researched year not covered whole"),
    # A disputed stretch first is read on the clock after it, as the file's
    # header says; two that meet have no clock on either side of their end.
    "two disputed stretches that meet": (lambda ls: (_set_cell(ls, "Winona", "1964-05-24 02:00", 7, ""),
                                                     _set_cell(ls, "Winona", "1964-05-24 02:00", 8, ""),
                                                     _set_cell(ls, "Winona", "1964-05-24 02:00", 9, "disputed")),
                                         "no clock on either side"),
    "a linked zone": (lambda ls: [_set_cell(ls, "Moorhead", line.split("\t")[5], 4, "Africa/Accra")
                                  for line in list(ls) if line.split("\t")[3:4] == ["Moorhead"]],
                      "a place's record or zone"),
    "two names for one place": (lambda ls: _set_cell(ls, "Moorhead", "1965-01-01 00:00", 3, "Fargo"),
                                "a place's record or zone"),
    "an interval empty in UT": (lambda ls: (_set_cell(ls, "Minneapolis", "1965-05-23 02:00", 6, "1965-05-23 02:30"),
                                            _set_cell(ls, "Minneapolis", "1965-09-07 02:00", 5, "1965-05-23 02:30")),
                                "empty once its ends are in UT"),
}


@pytest.mark.parametrize("damage", sorted(MALFORMED))
def test_a_malformed_table_stops_the_load(tz, monkeypatch, damage):
    change, phrase = MALFORMED[damage]
    honest = DATA.read_text(encoding="utf-8").splitlines()
    data = _changed(honest, change)
    assert data != DATA.read_bytes(), "the premise: the file was changed"
    monkeypatch.setattr(tz, "_shipped_file_bytes", lambda name: data if name == "data/place_clocks.tsv" else None)
    with pytest.raises(ValueError, match=phrase.replace("+", r"\+")):
        tz._read_place_clocks()


def test_the_honest_table_loads_as_the_import_did(tz, monkeypatch):
    data = DATA.read_bytes()
    monkeypatch.setattr(tz, "_shipped_file_bytes", lambda name: data)
    assert tz._read_place_clocks() == tz.PLACE_CLOCKS


# --- the cast --------------------------------------------------------------------------

def _state(tz, point, reading, zone=CHICAGO):
    try:
        return tz.named_zone_state(zone, *reading, latitude=point[0], longitude=point[1])
    except tz.NamedZoneRefusal as refusal:
        return refusal.kind


def _instant(reading, state):
    return datetime(*reading, tzinfo=timezone.utc) - timedelta(seconds=state["offset_seconds"])


def test_minneapolis_1965_is_cast_on_its_own_standard_time_where_chicago_kept_summer_time(tz):
    assert _state(tz, MINNEAPOLIS, NOON_1965) == {"offset_seconds": -21600, "abbreviation": "CST",
                                                 "place_clock": True}
    assert tz.named_zone_state(CHICAGO, *NOON_1965) == {"offset_seconds": -18000, "abbreviation": "CDT"}


# Minneapolis 1965's summer window, at each end and a second either side:
# the reading, and what it is cast at (its abbreviation and its UT instant)
# or why it is refused.
WINDOW_EDGES = [
    ((1965, 5, 23, 1, 59, 59), ("CST", "1965-05-23 07:59:59")),
    ((1965, 5, 23, 2, 0, 0), "nonexistent"),
    ((1965, 5, 23, 2, 0, 1), "nonexistent"),
    ((1965, 5, 23, 2, 59, 59), "nonexistent"),
    ((1965, 5, 23, 3, 0, 0), ("CDT", "1965-05-23 08:00:00")),
    ((1965, 5, 23, 3, 0, 1), ("CDT", "1965-05-23 08:00:01")),
    ((1965, 9, 7, 0, 59, 59), ("CDT", "1965-09-07 05:59:59")),
    ((1965, 9, 7, 1, 0, 0), "ambiguous"),
    ((1965, 9, 7, 1, 59, 59), "ambiguous"),
    ((1965, 9, 7, 2, 0, 0), ("CST", "1965-09-07 08:00:00")),
    ((1965, 9, 7, 2, 0, 1), ("CST", "1965-09-07 08:00:01")),
    # The researched years' ends, and a year's turn inside them.
    ((1918, 1, 1, 0, 0, 0), ("CST", "1918-01-01 06:00:00")),
    ((1965, 12, 31, 23, 59, 59), ("CST", "1966-01-01 05:59:59")),
    ((1966, 1, 1, 0, 0, 0), ("CST", "1966-01-01 06:00:00")),
    ((1969, 12, 31, 23, 59, 59), ("CST", "1970-01-01 05:59:59")),
    # War time and peace time, one clock.
    ((1945, 8, 14, 17, 59, 59), ("CWT", "1945-08-14 22:59:59")),
    ((1945, 8, 14, 18, 0, 0), ("CPT", "1945-08-14 23:00:00")),
]


@pytest.mark.parametrize("reading, expected", WINDOW_EDGES, ids=[_local_text(r) + ":%02d" % r[5]
                                                                  for r, _e in WINDOW_EDGES])
def test_a_window_s_ends_and_a_second_either_side(tz, reading, expected):
    state = _state(tz, MINNEAPOLIS, reading)
    if isinstance(expected, str):
        assert state == expected
    else:
        abbreviation, instant = expected
        assert state["abbreviation"] == abbreviation and state["place_clock"] is True, state
        assert f"{_instant(reading, state):%Y-%m-%d %H:%M:%S}" == instant


@pytest.mark.parametrize("reading", [(1965, 4, 25, 12, 0, 0), (1965, 7, 4, 12, 0, 0), (1965, 10, 30, 12, 0, 0)])
def test_moorhead_1965_keeps_standard_time_all_summer(tz, reading):
    assert _state(tz, MOORHEAD, reading) == {"offset_seconds": -21600, "abbreviation": "CST", "place_clock": True}
    assert tz.named_zone_state(CHICAGO, *reading)["abbreviation"] == "CDT", "the premise: Chicago kept summer time"
    assert _state(tz, MOORHEAD, (1966, 7, 4, 12, 0, 0))["abbreviation"] == "CDT"


def test_duluth_1964_keeps_wisconsin_s_dates(tz):
    assert _state(tz, DULUTH, (1964, 5, 10, 12, 0, 0))["abbreviation"] == "CDT"
    assert _state(tz, DULUTH, (1964, 9, 20, 12, 0, 0))["abbreviation"] == "CDT"
    assert _state(tz, MINNEAPOLIS, (1964, 5, 10, 12, 0, 0))["abbreviation"] == "CST"
    assert _state(tz, MINNEAPOLIS, (1964, 9, 20, 12, 0, 0))["abbreviation"] == "CST"


# --- a disputed stretch ----------------------------------------------------------------

# Rochester 1959: the stretch from 26 April 02:00 (read on standard time) to
# 24 May 02:00 (read on summer time), and readings at and around its ends.
DISPUTED = [
    ((1959, 4, 26, 1, 59, 59), "CST"),
    ((1959, 4, 26, 2, 0, 0), "refused"),
    ((1959, 5, 1, 12, 0, 0), "refused"),
    ((1959, 5, 24, 1, 59, 59), "refused"),
    ((1959, 5, 24, 2, 0, 0), "CDT"),
    ((1959, 5, 24, 3, 0, 0), "CDT"),
]


@pytest.mark.parametrize("reading, expected", DISPUTED)
def test_a_disputed_stretch_is_refused_by_the_place_and_its_ends_are_cast(tz, reading, expected):
    if expected != "refused":
        assert _state(tz, ROCHESTER, reading)["abbreviation"] == expected
    else:
        with pytest.raises(tz.PlaceClockRefusal) as refused:
            tz.named_zone_state(CHICAGO, *reading, latitude=ROCHESTER[0], longitude=ROCHESTER[1])
        assert refused.value.kind == "clock_choice"
        assert refused.value.interval == ((1959, 4, 26, 2, 0, 0), (1959, 5, 24, 2, 0, 0))
        assert refused.value.clocks == () and refused.value.area is None


@pytest.mark.parametrize("point, reading, expected", [
    # Around the end of a stretch that ends in a return: on summer time the
    # reading falls inside it, so it is refused although standard time
    # would place it after; an hour later neither clock does.
    (WINONA, (1964, 9, 8, 1, 30, 0), "clock_choice"),
    (WINONA, (1964, 10, 25, 2, 30, 0), "clock_choice"),
    (WINONA, (1964, 10, 25, 3, 0, 0), "CST"),
    # A stretch ending at midnight.
    (WEST_SAINT_PAUL, (1965, 5, 10, 23, 59, 59), "clock_choice"),
    (WEST_SAINT_PAUL, (1965, 5, 11, 0, 0, 0), "CDT"),
])
def test_either_clock_beside_a_stretch_refuses_a_reading_it_puts_inside(tz, point, reading, expected):
    state = _state(tz, point, reading)
    assert (state if isinstance(state, str) else state["abbreviation"]) == expected


def test_a_disputed_moment_carries_no_caution_and_the_anniversary_says_why(tz, engine):
    reading = (1959, 5, 1, 12, 0, 0)
    assert tz.zone_record_place(*ROCHESTER, CHICAGO, reading) is None
    result = engine["anniversary_moment"](datetime(1958, 5, 1, 12, 0, 0), 1, time_standard="named",
                                          zone_name=CHICAGO, latitude=ROCHESTER[0], longitude=ROCHESTER[1])
    assert result.status == "unavailable"
    assert result.reason == "1959-05-01 12:00:00 falls where the sources do not settle which clock the birthplace kept"


# --- what is unchanged ---------------------------------------------------------------

@pytest.mark.parametrize("point", [(41.85004, -87.65005), (44.97998, -93.26384), (44.97997, -93.26385),
                                   (44.979971, -93.26384), MANKATO])
def test_another_pair_reads_chicago_s_record(tz, point):
    assert _state(tz, point, NOON_1965) == {"offset_seconds": -18000, "abbreviation": "CDT"}


def test_chicago_s_own_pair_casts_its_clock_and_its_unsettled_year_the_record(tz, engine):
    """Chicago's atlas pair has clocks of its own: in 1965 its state is the
    zone's record's offset and abbreviation, read from the place's clock,
    with no caution. A year the research has not settled there is cast by
    the zone's record, with the caution as before 1918 at the same pair (the
    record is Chicago's own, so none)."""
    place = _place(tz, CHICAGO_CITY)
    assert 1965 in place["years"]
    assert _state(tz, CHICAGO_CITY, NOON_1965) == {**tz.named_zone_state(CHICAGO, *NOON_1965), "place_clock": True}
    assert tz.zone_record_place(*CHICAGO_CITY, CHICAGO, NOON_1965) is None
    assert engine["zone_record_caution"](*CHICAGO_CITY, CHICAGO, NOON_1965) is None
    unsettled = [year for year in range(1918, 1970) if year not in place["years"]]
    assert unsettled
    before = (1917, 6, 1, 12, 0, 0)
    for year in unsettled:
        for reading in ((year, 1, 1, 0, 0, 0), (year, 6, 1, 12, 0, 0), (year, 12, 31, 23, 59, 59)):
            assert _state(tz, CHICAGO_CITY, reading) == tz.named_zone_state(CHICAGO, *reading)
            assert "place_clock" not in _state(tz, CHICAGO_CITY, reading)
            assert (tz.zone_record_place(*CHICAGO_CITY, CHICAGO, reading)
                    == tz.zone_record_place(*CHICAGO_CITY, CHICAGO, before))
            assert (engine["zone_record_caution"](*CHICAGO_CITY, CHICAGO, reading)
                    == engine["zone_record_caution"](*CHICAGO_CITY, CHICAGO, before))


@pytest.mark.parametrize("reading, abbreviation", [((1917, 6, 1, 12, 0, 0), "CST"), ((1917, 12, 31, 23, 59, 59), "CST"),
                                                   ((1970, 1, 1, 0, 0, 0), "CST"), ((1970, 6, 1, 12, 0, 0), "CDT")])
def test_a_year_outside_the_research_reads_chicago_s_record(tz, reading, abbreviation):
    assert _state(tz, MINNEAPOLIS, reading) == {"offset_seconds": {"CST": -21600, "CDT": -18000}[abbreviation],
                                               "abbreviation": abbreviation}
    assert _state(tz, MINNEAPOLIS, reading) == tz.named_zone_state(CHICAGO, *reading)


def test_a_caller_without_coordinates_or_in_another_zone_reads_the_record(tz):
    assert tz.named_zone_state(CHICAGO, *NOON_1965) == {"offset_seconds": -18000, "abbreviation": "CDT"}
    assert tz._clock_states((CHICAGO,), NOON_1965) == ((CHICAGO, -18000),)
    assert tz._place_clocks_at(CHICAGO, 1965, None, MINNEAPOLIS[1]) is None
    denver = tz.named_zone_state("America/Denver", *NOON_1965, latitude=MINNEAPOLIS[0], longitude=MINNEAPOLIS[1])
    assert denver == tz.named_zone_state("America/Denver", *NOON_1965)


# --- the caution -----------------------------------------------------------------------

@pytest.mark.parametrize("point, reading", [(MINNEAPOLIS, NOON_1965), (MINNEAPOLIS, (1918, 6, 1, 12, 0, 0)),
                                            (MINNEAPOLIS, (1969, 12, 31, 23, 59, 59)),
                                            (MOORHEAD, (1965, 7, 4, 12, 0, 0)), (DULUTH, (1964, 5, 10, 12, 0, 0))])
def test_the_caution_steps_back_inside_a_researched_year(tz, engine, point, reading):
    assert tz.zone_record_place(*point, CHICAGO, reading) is None
    assert engine["zone_record_caution"](*point, CHICAGO, reading) is None


@pytest.mark.parametrize("point, reading", [(MANKATO, NOON_1965), (MINNEAPOLIS, (1917, 6, 1, 12, 0, 0)),
                                            ((44.97998, -93.26384), NOON_1965)])
def test_the_caution_stays_for_an_unresearched_place_or_year(tz, engine, point, reading):
    assert tz.zone_record_place(*point, CHICAGO, reading) == "Chicago"
    assert engine["zone_record_caution"](*point, CHICAGO, reading) == SENTENCE


# --- the box and the reports -----------------------------------------------------------

def _app(point, date, clock=time(12, 0)):
    at = make_app(date=date, page="sources")
    at.session_state["manual_lat_key"] = point[0]
    at.session_state["manual_lon_key"] = point[1]
    at.session_state["time_input_key"] = clock
    at.session_state["time_standard_key"] = TIME_STANDARD_OPTIONS[1]
    return at


def _all_text(at):
    return [n.value for kind in ("info", "success", "warning", "error", "markdown", "caption")
            for n in at.get(kind)]


@pytest.fixture(scope="module")
def minneapolis_1965():
    at = _app(MINNEAPOLIS, "1965-05-10").run(timeout=300)
    assert_no_exception(at, "Minneapolis 1965")
    return at


def test_the_box_casts_minneapolis_1965_on_its_own_clock_with_no_caution(minneapolis_1965):
    at = minneapolis_1965
    box = [n.value for n in at.sidebar.info if "UTC offset" in n.value]
    assert len(box) == 1, box
    lines = box[0].split("  \n")
    assert lines[0] == "**America/Chicago** · UTC offset -06:00 (CST)", lines
    assert lines[1].startswith("UT 1965-05-10 18:00:00"), lines
    texts = _all_text(at)
    assert texts, "the premise: the run printed text"
    assert not any("this zone's record is" in text for text in texts)


def test_the_reports_of_minneapolis_1965_carry_its_own_offset_and_no_caution(minneapolis_1965):
    at = minneapolis_1965
    analysis, html, markdown = (at.session_state["_analysis_export"], at.session_state["_analysis_html"],
                                at.session_state["_analysis_markdown"])
    assert analysis["input"]["timezone"] == CHICAGO
    assert analysis["input"]["julian_day_ut"] == pytest.approx(2438891.25, abs=1e-9), "18:00 UT"
    assert "| Time zone | America/Chicago |" in markdown
    assert "Time zone note" not in markdown and "this zone's record is" not in markdown
    assert "Time zone note" not in html and "this zone's record is" not in html and "this zone&" not in html


def test_the_box_refuses_a_disputed_moment_with_the_place_s_sentence():
    at = _app(ROCHESTER, "1959-05-01").run(timeout=120)
    assert_no_exception(at, "Rochester 1959")
    sentence = ("**1959-05-01 12:00**: the sources do not settle which clock was kept at this place between "
                f"1959-04-26 02:00 and 1959-05-24 02:00. Choose {MANUAL} and enter the offset of the clock the time "
                "was recorded in.")
    errors = [n.value for n in at.sidebar.error]
    assert sentence in errors, errors
    assert [n.value for n in at.sidebar.info if "UTC offset" in n.value] == []
    texts = _all_text(at)
    assert texts, "the premise: the run printed text"
    assert not any("this zone's record is" in text for text in texts)


def test_the_box_names_a_stretch_ending_at_midnight_by_its_date():
    at = _app(WEST_SAINT_PAUL, "1965-05-10").run(timeout=120)
    assert_no_exception(at, "West Saint Paul 1965")
    errors = [n.value for n in at.sidebar.error]
    assert any("between 1965-04-25 02:00 and 1965-05-11. Choose" in e for e in errors), errors


def _picked(text, label, date="1965-05-10"):
    """The city box with `text` typed and `label` picked from its matches."""
    at = make_app(date=date, page="sources")
    at.session_state["time_input_key"] = time(12, 0)
    at.session_state["time_standard_key"] = TIME_STANDARD_OPTIONS[1]
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = text
    at.run(timeout=120)
    picker = [s for s in at.sidebar.selectbox if s.label == "Select specific location:"]
    assert len(picker) == 1 and label in picker[0].options, [s.options for s in picker]
    picker[0].select(label).run(timeout=120)
    assert_no_exception(at, label)
    return at


@pytest.mark.parametrize("text, label, pair, head, caution", [
    ("Minneapolis", "Minneapolis, MN (US)", MINNEAPOLIS, "**America/Chicago** · UTC offset -06:00 (CST)", False),
    ("Mankato", "Mankato, MN (US)", MANKATO, "**America/Chicago** · UTC offset -05:00 (CDT)", True),
])
def test_an_atlas_pick_reaches_the_place_s_clocks_by_its_pair(text, label, pair, head, caution):
    at = _picked(text, label)
    assert (at.session_state["_resolved_lat"], at.session_state["_resolved_lon"]) == pair
    box = [n.value for n in at.sidebar.info if "UTC offset" in n.value]
    assert len(box) == 1 and box[0].split("  \n")[0] == head, box
    assert (SENTENCE in box[0]) is caution, box


# --- a place's own fold and gap -------------------------------------------------------
#
# Where the hour a reading falls in was skipped or repeated by a place's own
# clocks, the refusal names the place, whose clocks moved, not the zone,
# whose record did not change then; the zone's own fold and gap name the
# zone. Either way the sentence states the change itself: when it took
# effect on the clock before it, which way and how far the clocks moved,
# and the two clocks.

LMT_OR_MANUAL = f"{TIME_STANDARD_OPTIONS[0]} or {MANUAL}"
FOLDS_AND_GAPS = [
    # (where, the pair, the reading, its kind, what the refusal names)
    ("Minneapolis's own gap", MINNEAPOLIS, (1965, 5, 23, 2, 30, 0), "nonexistent", "Minneapolis"),
    ("Minneapolis's own fold", MINNEAPOLIS, (1965, 9, 7, 1, 30, 0), "ambiguous", "Minneapolis"),
    ("Duluth's own gap", DULUTH, (1964, 5, 3, 2, 30, 0), "nonexistent", "Duluth"),
    ("the zone's gap at Mankato", MANKATO, (1965, 4, 25, 2, 30, 0), "nonexistent", CHICAGO),
    ("the zone's fold at Mankato", MANKATO, (1965, 10, 31, 1, 30, 0), "ambiguous", CHICAGO),
    ("the zone's gap at Minneapolis in 1970", MINNEAPOLIS, (1970, 4, 26, 2, 30, 0), "nonexistent", CHICAGO),
]
_IDS = [case[0] for case in FOLDS_AND_GAPS]


@pytest.mark.parametrize("where, point, reading, kind, named", FOLDS_AND_GAPS, ids=_IDS)
def test_a_fold_or_gap_carries_the_place_whose_clocks_made_it(tz, where, point, reading, kind, named):
    with pytest.raises(tz.NamedZoneRefusal) as refused:
        tz.named_zone_state(CHICAGO, *reading, latitude=point[0], longitude=point[1])
    assert refused.value.kind == kind
    assert refused.value.place == (None if named == CHICAGO else named)
    # The zone's own refusal holds what it held before: no name of a place.
    assert ("place" in vars(refused.value)) is (named != CHICAGO)


# Each case's sentences, written out by hand from the place's rows (the
# hand tables above) or the zone's record: the box's, then the anniversary's.
SENTENCES = {
    "Minneapolis's own gap": (
        "At **02:00 on 1965-05-23** the clocks in Minneapolis moved forward one hour, from CST (UTC-06:00) to CDT "
        "(UTC-05:00), so **02:30** never occurred there. Check the recorded time.",
        "1965-05-23 02:30:00 never occurred in Minneapolis: the clocks moved forward one hour at 02:00 on "
        "1965-05-23"),
    "Minneapolis's own fold": (
        "At **02:00 on 1965-09-07** the clocks in Minneapolis moved back one hour, from CDT (UTC-05:00) to CST "
        "(UTC-06:00), so **01:30** occurred twice: first at UTC-05:00, then at UTC-06:00. Choose Manual UTC offset "
        "and enter the one the birth record gives.",
        "1965-09-07 01:30:00 occurred twice in Minneapolis: the clocks moved back one hour at 02:00 on 1965-09-07; "
        "no occurrence is selected"),
    "Duluth's own gap": (
        "At **02:00 on 1964-05-03** the clocks in Duluth moved forward one hour, from CST (UTC-06:00) to CDT "
        "(UTC-05:00), so **02:30** never occurred there. Check the recorded time.",
        "1964-05-03 02:30:00 never occurred in Duluth: the clocks moved forward one hour at 02:00 on 1964-05-03"),
    "the zone's gap at Mankato": (
        "At **02:00 on 1965-04-25** the clocks in the America/Chicago time zone moved forward one hour, from CST "
        "(UTC-06:00) to CDT (UTC-05:00), so **02:30** never occurred there. Check the recorded time.",
        "1965-04-25 02:30:00 never occurred in the America/Chicago time zone: the clocks moved forward one hour at "
        "02:00 on 1965-04-25"),
    "the zone's fold at Mankato": (
        "At **02:00 on 1965-10-31** the clocks in the America/Chicago time zone moved back one hour, from CDT "
        "(UTC-05:00) to CST (UTC-06:00), so **01:30** occurred twice: first at UTC-05:00, then at UTC-06:00. "
        "Choose Manual UTC offset and enter the one the birth record gives.",
        "1965-10-31 01:30:00 occurred twice in the America/Chicago time zone: the clocks moved back one hour at "
        "02:00 on 1965-10-31; no occurrence is selected"),
    "the zone's gap at Minneapolis in 1970": (
        "At **02:00 on 1970-04-26** the clocks in the America/Chicago time zone moved forward one hour, from CST "
        "(UTC-06:00) to CDT (UTC-05:00), so **02:30** never occurred there. Check the recorded time.",
        "1970-04-26 02:30:00 never occurred in the America/Chicago time zone: the clocks moved forward one hour at "
        "02:00 on 1970-04-26"),
}


@pytest.mark.parametrize("where, point, reading, kind, named", FOLDS_AND_GAPS, ids=_IDS)
def test_the_box_states_the_change_whose_clocks_made_the_fold_or_gap(where, point, reading, kind, named):
    # The premise: every case has its sentences, and the box names the
    # option by its own label.
    assert sorted(SENTENCES) == sorted(_IDS) and MANUAL == "Manual UTC offset"
    at = _app(point, "%04d-%02d-%02d" % reading[:3], clock=time(*reading[3:])).run(timeout=120)
    assert_no_exception(at, where)
    errors = [n.value for n in at.sidebar.error]
    assert SENTENCES[where][0] in errors, errors
    assert [e for e in errors if "America/Chicago" in e] == ([] if named != CHICAGO else [SENTENCES[where][0]])


@pytest.mark.parametrize("where, point, reading, kind, named", FOLDS_AND_GAPS, ids=_IDS)
def test_the_anniversary_states_the_change_whose_clocks_made_the_fold_or_gap(engine, where, point, reading, kind,
                                                                            named):
    birth = datetime(reading[0] - 1, *reading[1:])
    result = engine["anniversary_moment"](birth, 1, time_standard="named", zone_name=CHICAGO, latitude=point[0],
                                          longitude=point[1])
    assert result.status == "unavailable"
    assert result.reason == SENTENCES[where][1]


def test_a_zone_s_change_and_a_place_s_side_by_side_name_their_own_clocks(tz):
    """At one pair, Minneapolis's, its own gap of 1965 names the place and
    the zone's of 1970 the zone; and in 1965 the zone's gap at Mankato names
    the zone where Minneapolis's own, four weeks later, names the place."""
    def where(point, reading):
        change = tz.clock_change("nonexistent", CHICAGO, *reading, latitude=point[0], longitude=point[1])
        return tz.clock_change_words(change, reading)["where"]

    assert [where(MINNEAPOLIS, (1965, 5, 23, 2, 30, 0)), where(MINNEAPOLIS, (1970, 4, 26, 2, 30, 0)),
            where(MANKATO, (1965, 4, 25, 2, 30, 0))] == [
        "Minneapolis", "the America/Chicago time zone", "the America/Chicago time zone"]
    # Minneapolis kept CST through the zone's gap of 1965: no refusal there.
    assert tz.named_zone_state(CHICAGO, 1965, 4, 25, 2, 30, 0, latitude=MINNEAPOLIS[0],
                               longitude=MINNEAPOLIS[1])["abbreviation"] == "CST"
    # And the place's change is its own: the zone's record changed nothing then.
    assert tz.clock_change("nonexistent", CHICAGO, 1965, 5, 23, 2, 30, 0) is None


# --- changes that are not an hour, and one from local mean time --------------------
#
# Caracas's record moves its clocks by half an hour (back at 03:00 on
# 2007-12-09, from -04:00 to -04:30; forward at 02:30 on 2016-05-01), under
# no abbreviation but the database's numeric one, so each clock is its offset
# alone. New York's adoption of standard time set its clocks back from local
# mean time, -04:56:02, to EST at 12:03:58 on 1883-11-18, repeating 3 minutes
# 58 seconds.
CARACAS = (10.48801, -66.87919)
NEW_YORK = (40.71427, -74.00597)
OTHER_CHANGES = [
    ("Caracas's half hour back", CARACAS, "America/Caracas", (2007, 12, 9, 2, 45, 0),
     "At **03:00 on 2007-12-09** the clocks in the America/Caracas time zone moved back 30 minutes, from UTC-04:00 "
     "to UTC-04:30, so **02:45** occurred twice: first at UTC-04:00, then at UTC-04:30. Choose Manual UTC offset "
     "and enter the one the birth record gives.",
     "2007-12-09 02:45:00 occurred twice in the America/Caracas time zone: the clocks moved back 30 minutes at "
     "03:00 on 2007-12-09; no occurrence is selected"),
    ("Caracas's half hour forward", CARACAS, "America/Caracas", (2016, 5, 1, 2, 45, 0),
     "At **02:30 on 2016-05-01** the clocks in the America/Caracas time zone moved forward 30 minutes, from "
     "UTC-04:30 to UTC-04:00, so **02:45** never occurred there. Check the recorded time.",
     "2016-05-01 02:45:00 never occurred in the America/Caracas time zone: the clocks moved forward 30 minutes at "
     "02:30 on 2016-05-01"),
    ("New York's standard time, from local mean time", NEW_YORK, "America/New_York", (1883, 11, 18, 12, 1, 30),
     "At **12:03:58 on 1883-11-18** the clocks in the America/New_York time zone moved back 3 minutes 58 seconds, "
     "from local mean time (UTC-04:56:02) to EST (UTC-05:00), so **12:01:30** occurred twice: first at "
     "UTC-04:56:02, then at UTC-05:00. Choose Manual UTC offset and enter the one the birth record gives.",
     "1883-11-18 12:01:30 occurred twice in the America/New_York time zone: the clocks moved back 3 minutes 58 "
     "seconds at 12:03:58 on 1883-11-18; no occurrence is selected"),
]
_OTHER_IDS = [case[0] for case in OTHER_CHANGES]


@pytest.mark.parametrize("where, point, zone, reading, box, reason", OTHER_CHANGES, ids=_OTHER_IDS)
def test_the_box_states_a_change_that_is_not_an_hour(where, point, zone, reading, box, reason):
    at = _app(point, "%04d-%02d-%02d" % reading[:3], clock=time(*reading[3:])).run(timeout=120)
    assert_no_exception(at, where)
    errors = [n.value for n in at.sidebar.error]
    assert box in errors, errors


@pytest.mark.parametrize("where, point, zone, reading, box, reason", OTHER_CHANGES, ids=_OTHER_IDS)
def test_the_anniversary_states_a_change_that_is_not_an_hour(engine, where, point, zone, reading, box, reason):
    birth = datetime(reading[0] - 1, *reading[1:])
    result = engine["anniversary_moment"](birth, 1, time_standard="named", zone_name=zone, latitude=point[0],
                                          longitude=point[1])
    assert result.status == "unavailable"
    assert result.reason == reason


@pytest.mark.parametrize("seconds, words", [
    (3600, "one hour"), (7200, "two hours"), (10800, "3 hours"), (1800, "30 minutes"), (60, "one minute"),
    (238, "3 minutes 58 seconds"), (5400, "one hour 30 minutes"), (3601, "one hour one second"),
    (-3600, "one hour"), (86400, "24 hours")])
def test_an_amount_is_written_in_words_with_no_zero_parts(tz, seconds, words):
    assert tz._amount_words(seconds) == words


@pytest.mark.parametrize("clock, words", [
    ((-21600, "CST"), "CST (UTC-06:00)"), ((-17762, "LMT"), "local mean time (UTC-04:56:02)"),
    ((-16200, "-0430"), "UTC-04:30"), ((3600, None), "UTC+01:00"), ((0, "GMT"), "GMT (UTC+00:00)"),
    ((19800, "IST"), "IST (UTC+05:30)")])
def test_a_clock_is_written_by_its_name_and_offset(tz, clock, words):
    assert tz._clock_words(clock) == words


def test_a_turned_back_hour_with_no_window_of_its_own_states_its_offset_alone(tz):
    """Luxembourg's 1937 correction: the clocks were put back from summer
    time, which is no window of its own, at 01:00 on 1937-10-03."""
    change = tz.clock_change("ambiguous", "Europe/Luxembourg", 1937, 10, 3, 0, 30, 0)
    words = tz.clock_change_words(change, (1937, 10, 3, 0, 30, 0))
    assert (words["time"], words["date"], words["before"], words["after"], words["amount"]) == (
        "01:00", "1937-10-03", "UTC+01:00", "WET (UTC+00:00)", "one hour")


def test_a_reading_on_another_day_than_the_change_is_written_with_its_date(tz):
    """A change at midnight back to 23:00 repeats the hour before midnight of
    the day before: the reading is written with its own date (Sao Paulo's
    summer time ended at 00:00 on 2019-02-17)."""
    reading = (2019, 2, 16, 23, 30, 0)
    change = tz.clock_change("ambiguous", "America/Sao_Paulo", *reading)
    words = tz.clock_change_words(change, reading)
    assert (words["time"], words["date"], words["reading"]) == ("00:00", "2019-02-17", "2019-02-16 23:30")


def test_a_refusal_of_another_kind_states_no_change(tz):
    assert tz.clock_change("disputed", "Europe/Stockholm", 1916, 9, 30, 23, 30, 0) is None
    assert tz.clock_change("nonexistent", "Etc/GMT+2", 1990, 6, 1, 12, 0, 0) is None
    # A reading in no stretch: nothing is said.
    assert tz.clock_change("nonexistent", CHICAGO, 1965, 6, 1, 12, 0, 0) is None
