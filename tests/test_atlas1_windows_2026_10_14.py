"""The pre-1970 windows: a linked zone's own clocks, cast where the sources establish them.

The time-zone database keeps 106 zone names only as links to another place's
record before 1970, and the app refuses them there. Outside researchers read
the laws and gazettes of nineteen of those places; a blind reproduction
checked each window against the documents, and the owner adopted them as a
hand-kept, sourced table beside the list of linked zones. Inside a window the
window gives the offset and the label, never the package's record (which is
the linked target's); outside every window the name is refused as before.

Every expected value below is written here: the windows are copied from the
rulings and the return tables they adopted, not read from the table under
test.
"""
from datetime import datetime, time, timedelta, timezone

import pytest

from conftest import assert_no_exception, make_app

UTC = timezone.utc
STD = "Standard time (named zone)"


def u(*parts):
    return datetime(*parts, tzinfo=UTC)


# zone: [(from UT, to UT, offset seconds, label)], half-open, as the rulings and
# the returns give them.
ROWS = {
    "Europe/Stockholm": [(u(1879, 1, 2), u(1899, 12, 31, 22, 59, 46), 3614, "Swedish time"),
                         (u(1899, 12, 31, 22, 59, 46), u(1916, 5, 14, 22), 3600, "CET"),
                         (u(1916, 5, 14, 22), u(1916, 9, 30, 22), 7200, "CEST"),
                         (u(1916, 9, 30, 23), u(1970, 1, 1), 3600, "CET")],
    "Europe/Oslo": [(u(1895, 1, 2), u(1916, 1, 1), 3600, "CET"), (u(1917, 1, 1), u(1940, 1, 1), 3600, "CET"),
                    (u(1946, 1, 1), u(1959, 1, 1), 3600, "CET"), (u(1966, 1, 1), u(1970, 1, 1), 3600, "CET")],
    "Europe/Copenhagen": [(u(1894, 1, 2), u(1916, 1, 1), 3600, "CET"), (u(1917, 1, 1), u(1940, 1, 1), 3600, "CET"),
                          (u(1949, 1, 1), u(1970, 1, 1), 3600, "CET")],
    "Europe/Amsterdam": [(u(1909, 5, 2), u(1916, 4, 30, 23, 40, 28), 1172, "Amsterdam mean solar time"),
                         (u(1958, 8, 4), u(1970, 1, 1), 3600, "CET")],
    "Europe/Luxembourg": [(u(1904, 6, 2), u(1916, 1, 1), 3600, "CET"), (u(1937, 10, 3), u(1937, 10, 3, 2), 0, "WET"),
                          (u(1937, 10, 3, 2), u(1938, 1, 1), 0, "WET")],
    "Atlantic/Reykjavik": [(u(1920, 1, 1), u(1921, 1, 1), -3600, "-01"), (u(1922, 1, 1), u(1939, 1, 1), -3600, "-01"),
                           (u(1968, 4, 8), u(1970, 1, 1), 0, "GMT")],
    "Europe/Monaco": [(u(1892, 6, 2), u(1911, 3, 15), 561, "PMT"), (u(1911, 4, 1), u(1916, 1, 1), 0, "WET")],
    "Europe/Bratislava": [(u(1946, 5, 6, 1), u(1946, 10, 6, 1), 7200, "CEST"),
                          (u(1946, 10, 6, 1), u(1946, 10, 7, 1), 7200, "CEST"),
                          (u(1946, 10, 7, 1), u(1946, 12, 1, 2), 3600, "CET"),
                          (u(1946, 12, 1, 2), u(1947, 2, 23, 2), 0, "winter time")],
    "Africa/Brazzaville": [(u(1949, 5, 2), u(1950, 1, 1), 3600, "WAT")],
    "Africa/Bangui": [(u(1949, 5, 2), u(1950, 1, 1), 3600, "WAT")],
    "Africa/Libreville": [(u(1949, 5, 2), u(1950, 1, 1), 3600, "WAT")],
    "Pacific/Chuuk": [(u(1941, 6, 17), u(1942, 1, 1), 32400, "+09")],
    "Pacific/Pohnpei": [(u(1941, 6, 17), u(1942, 1, 1), 32400, "+09")],
    "Pacific/Majuro": [(u(1941, 6, 17), u(1942, 1, 1), 32400, "+09")],
    "Pacific/Saipan": [(u(1941, 6, 17), u(1942, 1, 1), 32400, "+09")],
    "America/St_Thomas": [(u(1967, 12, 24, 4), u(1968, 1, 1), -14400, "AST")],
    "Africa/Djibouti": [(u(1949, 3, 1), u(1950, 1, 1), 10800, "EAT")],
    "Indian/Mahe": [(u(1907, 1, 2), u(1908, 1, 1), 14400, "+04")],
    "America/Blanc-Sablon": [(u(1966, 3, 16, 4), u(1970, 1, 1), -14400, "AST")],
}

# The named mean times among them, and the windows whose start is a dated
# change of the clock rather than a review clip (no chosen-start sentence).
MEAN_TIMES = {("Europe/Stockholm", 0), ("Europe/Amsterdam", 0), ("Europe/Monaco", 0)}
DATED_STARTS = {("Europe/Stockholm", 1), ("Europe/Stockholm", 2), ("Europe/Stockholm", 3),
                ("Europe/Luxembourg", 1), ("Europe/Luxembourg", 2),
                ("Europe/Bratislava", 0), ("Europe/Bratislava", 1), ("Europe/Bratislava", 2),
                ("Europe/Bratislava", 3)}


@pytest.fixture(scope="module")
def tz():
    import time_zones
    return time_zones


def _state(tz, zone, moment, **kw):
    try:
        return tz.named_zone_state(zone, *moment, **kw)
    except tz.NamedZoneRefusal as refusal:
        return ("refused", refusal.kind)


def _local(instant, offset):
    t = (instant + timedelta(seconds=offset)).replace(tzinfo=None)
    return (t.year, t.month, t.day, t.hour, t.minute, t.second)


# --- item 1: the table -----------------------------------------------------------

def test_the_table_holds_the_rulings_windows_and_nothing_else(tz):
    got = {zone: [(w["from"], w["to"], w["offset_seconds"], w["abbreviation"]) for w in windows]
           for zone, windows in tz.PRE1970_WINDOWS.items()}
    assert got == ROWS
    assert sum(len(w) for w in got.values()) == 36 and len(got) == 19
    assert {(z, i) for z, ws in tz.PRE1970_WINDOWS.items() for i, w in enumerate(ws) if w["mean_time"]} == MEAN_TIMES
    assert {(z, i) for z, ws in tz.PRE1970_WINDOWS.items() for i, w in enumerate(ws)
            if not w["chosen"]} == DATED_STARTS
    assert [(z, i) for z, ws in tz.PRE1970_WINDOWS.items() for i, w in enumerate(ws)
            if w["turned_back_from"] is not None] == [("Europe/Luxembourg", 1)]
    assert tz.PRE1970_WINDOWS["Europe/Luxembourg"][1]["turned_back_from"] == 3600
    # The one refused stretch: Stockholm's hour, +01:00 by the statute's
    # wording and +02:00 by the newspaper.
    assert {z: [(s["from"], s["to"], s["offsets"]) for s in v] for z, v in tz.PRE1970_DISPUTED.items()} == {
        "Europe/Stockholm": [(u(1916, 9, 30, 22), u(1916, 9, 30, 23), (3600, 7200))]}


def test_every_window_zone_is_a_linked_zone(tz):
    assert set(tz.PRE1970_WINDOWS) <= set(tz.LINKED_ZONES)
    assert set(tz.PRE1970_DISPUTED) <= set(tz.PRE1970_WINDOWS)
    assert set(tz.PRE1970_REFUSAL_NOTES) <= set(tz.LINKED_ZONES)
    assert not set(tz.PRE1970_REFUSAL_NOTES) & set(tz.PRE1970_WINDOWS)
    assert {c["zone"] for c in tz.PRE1970_CONFLICTS} <= set(tz.LINKED_ZONES)


def test_no_two_windows_of_one_zone_overlap(tz):
    table = tz.PRE1970_WINDOWS
    assert len(table) == 19
    for zone, windows in table.items():
        spans = [(w["from"], w["to"]) for w in windows]
        assert spans, zone
        assert all(lo < hi for lo, hi in spans), zone
        assert spans == sorted(spans), zone
        assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), zone
        assert all(hi <= datetime(1970, 1, 1, tzinfo=UTC) for lo, hi in spans), zone
    # The refused hour lies between Stockholm's summer time and its CET.
    stretches = tz.PRE1970_DISPUTED["Europe/Stockholm"]
    assert len(stretches) == 1
    spans = [(w["from"], w["to"]) for w in table["Europe/Stockholm"]]
    assert len(spans) == 4
    assert all(hi <= stretches[0]["from"] or lo >= stretches[0]["to"] for lo, hi in spans)


def test_every_source_named_is_defined_and_read_as_the_reproductions_found_it(tz):
    named = set()
    table = tz.PRE1970_WINDOWS
    assert len(table) == 19
    for windows in table.values():
        assert windows
        for w in windows:
            assert w["sources"], w
            named |= set(w["sources"]) | set(w["note_sources"])
    for stretches in tz.PRE1970_DISPUTED.values():
        for s in stretches:
            named |= set(s["sources"])
    for c in tz.PRE1970_CONFLICTS:
        named |= set(c["sources"])
    for _note, ids in tz.PRE1970_REFUSAL_NOTES.values():
        named |= set(ids)
    assert named <= set(tz.PRE1970_SOURCES), sorted(named - set(tz.PRE1970_SOURCES))
    assert set(tz.PRE1970_SOURCES) <= named, sorted(set(tz.PRE1970_SOURCES) - named)
    statuses = {sid: status for sid, (_title, status) in tz.PRE1970_SOURCES.items()}
    assert set(statuses.values()) <= set(tz.PRE1970_READ_STATUSES)
    # No status claims the bare original: each says how the document was read.
    assert not [s for s in tz.PRE1970_READ_STATUSES if s.split(",")[0].strip().lower() in ("original", "original: read")]
    assert statuses["DJ1949"] == "official electronic transcription"
    assert statuses["SEY1906"] == statuses["SEY1971"] == "commercial facsimile, read on the researcher's retained copy"
    for sid in ("HC2461942", "BP211949"):
        assert statuses.get(sid, "commercial facsimile").startswith("commercial facsimile"), sid
    assert statuses["AEF1949MARCH"] == statuses["NBS1950"] == "official or library scan, read on the page image"
    for sid in ("QC1966ACT", "QC1969ACT"):
        assert statuses[sid] == "official or library scan, read on the researcher's retained copy", sid
    for sid in ("SE1979", "SE1926", "SE1899", "SE1899SKR38", "SE1878PROP22"):
        assert statuses[sid] == "official electronic transcription", sid
    for sid in ("SE1878LAW", "SE1899LAW", "SE1916LAW", "SEDN1916"):
        assert statuses[sid] == "citation only, through the time-zone database's quotation", sid
    # One id per document: round 3b's duplicates are folded.
    for duplicate in ("JP1941NOTICE11", "JP1934NOTICE42", "LANATURE1951", "NBS1950_66_73", "MILNE1899_R3B"):
        assert duplicate not in tz.PRE1970_SOURCES, duplicate
    # Every source's status, by value, as its reproduction found it.
    assert statuses == STATUSES
    # The Swedish-time row rests on the five documents round 1's reproduction read.
    assert tz.PRE1970_WINDOWS["Europe/Stockholm"][0]["sources"] == (
        "SE1979", "SE1926", "SE1899", "SE1899SKR38", "SE1878PROP22")


# Each source's read status, written out from the reproductions: round 1's
# 2.3 and 3.3; round 2's R2b.4 and round 2b's read_status column; round 3's
# section 5; round 3b's 2.1 and ruling 171.
_PAGE = "official or library scan, read on the page image"
_RETAINED = "official or library scan, read on the researcher's retained copy"
_EARLIER = "original scan, read in an earlier round and not re-read"
_TRANSCRIPTION = "official electronic transcription"
_QUOTED = "citation only, through the time-zone database's quotation"
STATUSES = {
    **{sid: _PAGE for sid in ("NL1908", "NL1908START", "NLOBS1909", "NL1916", "CS54", "CS84", "CS181", "CS213",
                              "LU1929", "LU1937", "IS1968BILL", "MC1911", "AEF1949MARCH", "NBS1950", "NATURE1951",
                              "JAPAN1941TIME", "JAPAN1922SCOPE", "JAPAN_PILOT_TIME", "JAPAN1934TIME",
                              "FR1967ATLANTIC", "AMIGOE1964DEC29")},
    **{sid: _RETAINED for sid in ("QC1966ACT", "QC1969ACT", "MILNE1899")},
    **{sid: _EARLIER for sid in ("NO1894", "NL1958", "LU1904", "MC1892", "VAT1966")},
    **{sid: _TRANSCRIPTION for sid in ("SE1979", "SE1926", "SE1899", "SE1899SKR38", "SE1878PROP22", "DJ1949")},
    **{sid: _QUOTED for sid in ("SE1878LAW", "SE1899LAW", "SE1916LAW", "SEDN1916")},
    "NBS1935": "library scan, read in its text layer",
    "SEY1906": "commercial facsimile, read on the researcher's retained copy",
    "SEY1971": "commercial facsimile, read on the researcher's retained copy",
    "IS1968": "official consolidated text",
    "DK1893": "unofficial mirror of the official text",
    "NLGENT": "secondary page",
    "ISALMANAC": "secondary page",
    "NO2018": "text read in an earlier round and not re-verified",
    "DK2023": "text read in an earlier round and not re-verified",
    "US1966TIME": "official or library scan, read in its text layer, then checked",
    "QC1978T6": "official or library scan, read in its text layer on the researcher's retained copy",
    "WALLIS1948LEAD": "search-engine copy only",
    "TZ2026E": "the time-zone release's own files",
}


# (zone, window index): phrases its note must carry, from the reproductions;
# every window's note is here.
NOTES = {
    ("Europe/Stockholm", 0): ("1879-01-02", "narrower reading", "SET", "NBS1935"),
    ("Europe/Stockholm", 1): ("SE1899LAW", "23:59:46 to 23:59:59 twice"),
    ("Europe/Stockholm", 2): ("refused", "22:00 UT"),
    ("Europe/Stockholm", 3): ("both readings",),
    ("Europe/Oslo", 0): ("1 January 1895", "1979 retrospective"),
    ("Europe/Oslo", 1): ("1959-65 only",),
    ("Europe/Oslo", 2): ("NO2018", "1943-45"),
    ("Europe/Oslo", 3): ("ended with 1965",),
    ("Europe/Copenhagen", 0): ("DK2023",),
    ("Europe/Copenhagen", 1): ("1940-48",),
    ("Europe/Copenhagen", 2): ("none brought back by 1979",),
    ("Europe/Amsterdam", 0): ("Amsterdam mean solar time, the laws' words, \"de middelbare zonnetijd van Amsterdam\"",
                              "20 minutes", "1909-04-30T23:40:28Z", "0.13 s",
                              "AMT, the abbreviation the return and ruling 106 give, is IANA's"),
    ("Europe/Amsterdam", 1): ("second day after issue", "1958-08-03"),
    ("Europe/Luxembourg", 0): ("from 1 June", "1916 summer time"),
    ("Europe/Luxembourg", 1): ("correction", "02:00 UT", "ambiguous"),
    ("Europe/Luxembourg", 2): ("unreviewed change of 1938",),
    ("Atlantic/Reykjavik", 0): ("1919 and 1921",),
    ("Atlantic/Reykjavik", 1): ("no summer time after 1921 before 1939",),
    ("Atlantic/Reykjavik", 2): ("7 April 1968 at 01:00",),
    ("Europe/Monaco", 0): ("EN-08", "Vatican"),
    ("Europe/Monaco", 1): ("law of 9 March 1911", "later French summer-time laws"),
    ("Europe/Bratislava", 0): ("territorial clause", "Czech lands"),
    ("Europe/Bratislava", 1): ("correction", "a day early"),
    ("Europe/Bratislava", 2): ("1946-10-07 02:00 to 02:59:59 twice",),
    ("Europe/Bratislava", 3): ("GMT", "is_dst"),
    # La Nature's own dates, and the 16 July decree only as a "perhaps".
    ("Africa/Brazzaville", 0): ("start clip", "One witness", "N-2a", "N-2b",
                                "names decrees of 18 July 1948 and 27 January 1949",
                                "perhaps decree 48-1136 of 16 July 1948"),
    ("Africa/Bangui", 0): ("start clip", "One witness"),
    ("Africa/Libreville", 0): ("start clip", "One witness"),
    ("Pacific/Chuuk", 0): ("N-2a", "pilot", "+10"),
    ("Pacific/Pohnpei", 0): ("N-2a", "+11"),
    ("Pacific/Majuro", 0): ("N-2a", "+12"),
    ("Pacific/Saipan", 0): ("N-2a", "150 degrees E", "N-2b"),
    ("America/St_Thomas", 0): ("23 December 1967",),
    ("Africa/Djibouti", 0): ("electronic transcription", "N-2c"),
    ("Indian/Mahe", 0): ("retained scans", "N-2d", "SEY1971"),
    ("America/Blanc-Sablon", 0): ("Shanks & Pottenger", "N-2e", "N-2d", "20:00"),
}


# Each conflict row's text, by a phrase of what the sources disagree on and
# a phrase of how it is built: a row changed, dropped or emptied fails here
# on its content, not only on the moved-code pin.
CONFLICTS = {
    ("Europe/Stockholm", "1916-09-30 22:00-23:00 UT"): (
        "statute's wording against the newspaper practice on the hour of the autumn change", "Refused"),
    ("Europe/Stockholm", "1879"): (
        "lists Sweden under 1879 among the zone system's adopters, against the 1878 law's mean time of three "
        "degrees west of Stockholm, 14 s from Central European time", "Swedish time is cast"),
    ("Europe/Oslo", "1940-1945"): ("NO2018 gives summer time in 1943-45, SE1979 in 1940-45",
                                   "1940 to 1946 stays refused"),
    ("Europe/Amsterdam", "1909-1916"): (
        "Greenwich time plus 19 m 32.13 s, and the 1916 law's midnight at +00:19:32, against van Gent's rounded 20 "
        "minutes usually applied", "+00:19:32, as ruling 106 rules"),
    ("Europe/Luxembourg", "1929-04-20 23:00 UT on"): (
        "makes Central European time the legal time again, where the database labels the stretch WEST, a summer "
        "time", "the label only, the offset agrees"),
    ("Europe/Luxembourg", "1937-10-03 00:00-02:00 UT"): (
        "change at 01:00 summer time against the record's 02:00 UT", "a WET window from 00:00 UT"),
    ("Europe/Bratislava", "1946-10-06 01:00 UT to 1946-10-07 01:00 UT"): (
        "ends summer time on 7 October; the record ends it on 6 October", "a CEST window for the day"),
    ("Atlantic/Reykjavik", "1919 and 1921"): (
        "summer time in 1917-18 and again from 1939; the almanac and the database have summers from 20 February "
        "to 16 November 1919 and from 20 March to 23 June 1921", "No window in 1919 or 1921"),
    ("Pacific/Saipan", "1934 on"): (
        "puts the Saipan branch on 150 degrees E, +10, and NBS1935 gives the Marianas +10, against the record's "
        "+09 from 1901 to 1944; NBS1950 gives the Marianas +09", "rests on the 1941 notice alone"),
    ("America/Blanc-Sablon", "1966-1969"): (
        "Shanks & Pottenger, as the database's notes report, have this region keeping AST and ADT; the 1966 and "
        "1969 acts put it on Atlantic standard time with no summer clause", "AST all year in the window"),
}


def test_every_window_carries_its_note_and_the_conflicts_are_recorded(tz):
    table = tz.PRE1970_WINDOWS
    notes = [(zone, i, w["note"]) for zone, windows in table.items() for i, w in enumerate(windows)]
    assert len(notes) == 36
    assert [(zone, i) for zone, i, note in notes if len(note) <= 40] == []
    assert set(NOTES) == {(zone, i) for zone, i, _note in notes}
    assert not [zone for zone, _i, note in notes if "the decree of 16 July 1948 it names" in note]
    for (zone, i), phrases in NOTES.items():
        assert phrases
        for phrase in phrases:
            assert phrase in table[zone][i]["note"], (zone, i, phrase)
    assert "22:00 UT" in tz.PRE1970_DISPUTED["Europe/Stockholm"][0]["note"]
    assert "newspaper the database follows" in tz.PRE1970_DISPUTED["Europe/Stockholm"][0]["note"]
    conflicts = {(c["zone"], c["when"]): c for c in tz.PRE1970_CONFLICTS}
    expected = {("Europe/Stockholm", "1916-09-30 22:00-23:00 UT"): "SEDN1916",
                ("Europe/Stockholm", "1879"): "NBS1935",
                ("Europe/Oslo", "1940-1945"): "NO2018",
                ("Europe/Amsterdam", "1909-1916"): "NLGENT",
                ("Europe/Luxembourg", "1929-04-20 23:00 UT on"): "LU1929",
                ("Europe/Luxembourg", "1937-10-03 00:00-02:00 UT"): "LU1937",
                ("Europe/Bratislava", "1946-10-06 01:00 UT to 1946-10-07 01:00 UT"): "CS181",
                ("Atlantic/Reykjavik", "1919 and 1921"): "IS1968BILL",
                ("Pacific/Saipan", "1934 on"): "JAPAN1934TIME",
                ("America/Blanc-Sablon", "1966-1969"): "QC1966ACT"}
    assert len(expected) == 10
    assert set(conflicts) == set(expected)
    for key, source in expected.items():
        assert source in conflicts[key]["sources"], key
    assert set(CONFLICTS) == set(conflicts)
    for key, (conflict, built) in CONFLICTS.items():
        assert conflict in conflicts[key]["conflict"], (key, conflict)
        assert built in conflicts[key]["built"], (key, built)
    notes = tz.PRE1970_REFUSAL_NOTES
    assert set(notes) == {"America/Curacao", "Pacific/Wallis", "Asia/Phnom_Penh", "Europe/Vatican"}
    assert "AMIGOE1964DEC29" in notes["America/Curacao"][1] and "no window" in notes["America/Curacao"][0]
    assert "7 h 16 m 56 s" in notes["Asia/Phnom_Penh"][0] and "+7:16:35" in notes["Asia/Phnom_Penh"][0]
    assert "unconfirmed" in notes["Pacific/Wallis"][0]
    assert "finding 14" in notes["Europe/Vatican"][0]


def test_the_locators_are_not_corpus_locators(tz):
    """A page is written "p 522", with no full stop: the register's bare-page
    check takes "p. 522" for a page of the corpus's volumes."""
    import re
    texts = [title for title, _status in tz.PRE1970_SOURCES.values()]
    texts += [w["note"] for ws in tz.PRE1970_WINDOWS.values() for w in ws]
    assert len(texts) > 36
    for text in texts:
        assert not re.search(r"\bpp?\.\s*\d", text), text
        assert not re.search(r"\d{1,2}\.\d{1,2}\s*,\s*\d", text), text


# --- item 2: the reading ---------------------------------------------------------

def _expect(zone, i):
    lo, hi, off, label = ROWS[zone][i]
    return off, label


# Where the default (inside: cast at the window's own state; outside: refused
# 'linked') does not hold, the reading's true outcome, written out:
# (zone, local reading) -> expected.
AT_BOUNDS = {
    # Stockholm: Swedish time to CET shows 23:59:46-59 twice; CET to summer
    # time skips 23:00-23:59:59; summer time's end and CET's start meet the
    # refused hour; the last CET window's end is 01:00 local on 1970-01-01,
    # read from the record (CET) on either side.
    ("Europe/Stockholm", (1899, 12, 31, 23, 59, 59)): ("refused", "ambiguous"),
    ("Europe/Stockholm", (1900, 1, 1, 0, 0, 0)): ("cast", 3600, "CET"),
    ("Europe/Stockholm", (1899, 12, 31, 23, 59, 46)): ("refused", "ambiguous"),
    ("Europe/Stockholm", (1899, 12, 31, 23, 59, 45)): ("cast", 3614, "Swedish time"),
    ("Europe/Stockholm", (1916, 5, 14, 23, 0, 0)): ("refused", "nonexistent"),
    ("Europe/Stockholm", (1916, 5, 14, 23, 59, 59)): ("refused", "nonexistent"),
    ("Europe/Stockholm", (1916, 9, 30, 23, 59, 59)): ("refused", "disputed"),
    ("Europe/Stockholm", (1916, 10, 1, 0, 0, 0)): ("refused", "disputed"),
    ("Europe/Stockholm", (1970, 1, 1, 0, 59, 59)): ("cast", 3600, "CET"),
    ("Europe/Stockholm", (1970, 1, 1, 1, 0, 0)): ("cast", 3600, "CET"),
    ("Europe/Oslo", (1970, 1, 1, 0, 59, 59)): ("cast", 3600, "CET"),
    ("Europe/Oslo", (1970, 1, 1, 1, 0, 0)): ("cast", 3600, "CET"),
    ("Europe/Copenhagen", (1970, 1, 1, 0, 59, 59)): ("cast", 3600, "CET"),
    ("Europe/Copenhagen", (1970, 1, 1, 1, 0, 0)): ("cast", 3600, "CET"),
    ("Europe/Amsterdam", (1970, 1, 1, 0, 59, 59)): ("cast", 3600, "CET"),
    ("Europe/Amsterdam", (1970, 1, 1, 1, 0, 0)): ("cast", 3600, "CET"),
    ("Atlantic/Reykjavik", (1970, 1, 1, 0, 0, 0)): ("cast", 0, "GMT"),
    # Luxembourg: the corrected hours start where the clocks went back from
    # summer time (no window), so the hour before 01:00 was shown twice; the
    # two WET windows meet with one state.
    ("Europe/Luxembourg", (1937, 10, 3, 0, 0, 0)): ("refused", "ambiguous"),
    ("Europe/Luxembourg", (1937, 10, 3, 2, 0, 0)): ("cast", 0, "WET"),
    ("Europe/Luxembourg", (1937, 10, 3, 1, 59, 59)): ("cast", 0, "WET"),
    # Bratislava: the two summer-time windows meet with one state; each change
    # back shows an hour twice.
    ("Europe/Bratislava", (1946, 10, 6, 3, 0, 0)): ("cast", 7200, "CEST"),
    ("Europe/Bratislava", (1946, 10, 6, 2, 59, 59)): ("cast", 7200, "CEST"),
    ("Europe/Bratislava", (1946, 10, 7, 2, 59, 59)): ("refused", "ambiguous"),
    ("Europe/Bratislava", (1946, 10, 7, 3, 0, 0)): ("cast", 3600, "CET"),
    ("Europe/Bratislava", (1946, 10, 7, 2, 0, 0)): ("refused", "ambiguous"),
    ("Europe/Bratislava", (1946, 10, 7, 1, 59, 59)): ("cast", 7200, "CEST"),
    ("Europe/Bratislava", (1946, 12, 1, 2, 59, 59)): ("refused", "ambiguous"),
    ("Europe/Bratislava", (1946, 12, 1, 3, 0, 0)): ("cast", 0, "winter time"),
    ("Europe/Bratislava", (1946, 12, 1, 2, 0, 0)): ("refused", "ambiguous"),
    ("Europe/Bratislava", (1946, 12, 1, 1, 59, 59)): ("cast", 3600, "CET"),
}


def _bound_cases():
    cases = []
    for zone, rows in ROWS.items():
        for i, (lo, hi, off, label) in enumerate(rows):
            for instant, side in ((lo, "first inside"), (lo - timedelta(seconds=1), "before"),
                                  (hi - timedelta(seconds=1), "last inside"), (hi, "after")):
                local = _local(instant, off)
                default = ("cast", off, label) if "inside" in side else ("refused", "linked")
                cases.append(pytest.param(zone, local, AT_BOUNDS.get((zone, local), default),
                                          id=f"{zone}-{i}-{side}"))
    return cases


@pytest.mark.parametrize("zone, local, expected", _bound_cases())
def test_each_bound_of_every_window_read_from_both_sides(tz, zone, local, expected):
    got = _state(tz, zone, local)
    if expected[0] == "cast":
        assert isinstance(got, dict), (zone, local, got)
        assert (got["offset_seconds"], got["abbreviation"]) == expected[1:], (zone, local, got)
    else:
        assert got == expected, (zone, local, got)


@pytest.mark.parametrize("local, expected", [
    ((1916, 9, 30, 22, 59, 59), ("cast", 7200, "CEST")),
    ((1916, 9, 30, 23, 0, 0), ("refused", "disputed")),
    ((1916, 9, 30, 23, 30, 0), ("refused", "disputed")),
    ((1916, 10, 1, 0, 30, 0), ("refused", "disputed")),
    ((1916, 10, 1, 0, 59, 59), ("refused", "disputed")),
    ((1916, 10, 1, 1, 0, 0), ("cast", 3600, "CET")),
])
def test_the_refused_hour_read_from_both_sides(tz, local, expected):
    got = _state(tz, "Europe/Stockholm", local)
    assert (got if expected[0] == "refused" else ("cast", got["offset_seconds"], got["abbreviation"])) == expected


@pytest.mark.parametrize("zone, local, expected", [
    # Stockholm's 14-second fold, Swedish time to CET.
    ("Europe/Stockholm", (1899, 12, 31, 23, 59, 45), ("cast", 3614, "Swedish time")),
    ("Europe/Stockholm", (1899, 12, 31, 23, 59, 46), ("refused", "ambiguous")),
    ("Europe/Stockholm", (1899, 12, 31, 23, 59, 52), ("refused", "ambiguous")),
    ("Europe/Stockholm", (1899, 12, 31, 23, 59, 59), ("refused", "ambiguous")),
    ("Europe/Stockholm", (1900, 1, 1, 0, 0, 0), ("cast", 3600, "CET")),
    # Stockholm's gap, CET to summer time.
    ("Europe/Stockholm", (1916, 5, 14, 22, 59, 59), ("cast", 3600, "CET")),
    ("Europe/Stockholm", (1916, 5, 14, 23, 0, 0), ("refused", "nonexistent")),
    ("Europe/Stockholm", (1916, 5, 14, 23, 30, 0), ("refused", "nonexistent")),
    ("Europe/Stockholm", (1916, 5, 14, 23, 59, 59), ("refused", "nonexistent")),
    ("Europe/Stockholm", (1916, 5, 15, 0, 0, 0), ("cast", 7200, "CEST")),
    # Bratislava's two changes back.
    ("Europe/Bratislava", (1946, 10, 7, 1, 59, 59), ("cast", 7200, "CEST")),
    ("Europe/Bratislava", (1946, 10, 7, 2, 30, 0), ("refused", "ambiguous")),
    ("Europe/Bratislava", (1946, 10, 7, 3, 0, 0), ("cast", 3600, "CET")),
    ("Europe/Bratislava", (1946, 12, 1, 1, 59, 59), ("cast", 3600, "CET")),
    ("Europe/Bratislava", (1946, 12, 1, 2, 30, 0), ("refused", "ambiguous")),
    ("Europe/Bratislava", (1946, 12, 1, 3, 0, 0), ("cast", 0, "winter time")),
    # Bratislava's spring change has no window before it: refused as linked.
    ("Europe/Bratislava", (1946, 5, 6, 2, 30, 0), ("refused", "linked")),
    ("Europe/Bratislava", (1947, 2, 23, 2, 30, 0), ("refused", "linked")),
    # Luxembourg's hour put back from summer time, which is no window.
    ("Europe/Luxembourg", (1937, 10, 2, 23, 59, 59), ("refused", "linked")),
    ("Europe/Luxembourg", (1937, 10, 3, 0, 30, 0), ("refused", "ambiguous")),
    ("Europe/Luxembourg", (1937, 10, 3, 0, 59, 59), ("refused", "ambiguous")),
    ("Europe/Luxembourg", (1937, 10, 3, 1, 0, 0), ("cast", 0, "WET")),
])
def test_each_fold_and_gap(tz, zone, local, expected):
    got = _state(tz, zone, local)
    assert (got if expected[0] == "refused" else ("cast", got["offset_seconds"], got["abbreviation"])) == expected


def test_chuuk_1941_is_cast_at_the_windows_offset_not_the_packages(tz):
    from zoneinfo import ZoneInfo
    assert tz.named_zone_state("Pacific/Chuuk", 1941, 9, 1, 12, 0, 0)["offset_seconds"] == 9 * 3600
    # The package holds the linked target's record there, Port Moresby's +10.
    package = datetime(1941, 9, 1, 12, tzinfo=ZoneInfo("Pacific/Chuuk")).utcoffset()
    assert package == timedelta(hours=10), package
    assert tz.named_zone_state("Pacific/Pohnpei", 1941, 9, 1, 12, 0, 0)["offset_seconds"] == 9 * 3600
    assert tz.named_zone_state("Pacific/Majuro", 1941, 9, 1, 12, 0, 0)["offset_seconds"] == 9 * 3600
    assert tz.named_zone_state("Pacific/Saipan", 1941, 9, 1, 12, 0, 0)["offset_seconds"] == 9 * 3600


def test_inside_a_window_the_package_is_never_read(tz, monkeypatch):
    import zoneinfo

    def no_database(name):
        raise zoneinfo.ZoneInfoNotFoundError(name)
    monkeypatch.setattr(tz, "ZoneInfo", no_database)
    assert tz.named_zone_state("Europe/Stockholm", 1950, 6, 1, 12, 0, 0) == {
        "offset_seconds": 3600, "abbreviation": "CET"}
    assert tz.named_zone_state("Pacific/Chuuk", 1941, 9, 1, 12, 0, 0)["offset_seconds"] == 32400
    # Outside the windows the refusal is the list's, as before.
    assert _state(tz, "Europe/Stockholm", (1870, 6, 1, 12, 0, 0)) == ("refused", "linked")


def test_a_name_without_windows_is_refused_as_before(tz):
    assert "Africa/Accra" not in tz.PRE1970_WINDOWS
    assert _state(tz, "Africa/Accra", (1950, 6, 1, 12, 0, 0)) == ("refused", "linked")
    assert _state(tz, "Africa/Accra", (1300, 2, 29, 12, 0, 0)) == ("refused", "linked")
    assert _state(tz, "Europe/Vatican", (1950, 6, 1, 12, 0, 0)) == ("refused", "linked")


# Linked names with no window (87), and the window zones at moments outside
# their windows: refused 'linked', as they were before the windows.
WINDOW_ZONES = sorted(ROWS)
OUTSIDE = [(1850, 6, 1, 12, 0, 0), (1878, 12, 31, 23, 59, 59), (1960, 6, 1, 12, 0, 0)]


def test_every_names_refusal_is_unchanged_outside_its_windows(tz):
    others = sorted(set(tz.LINKED_ZONES) - set(ROWS))
    assert len(others) == 87
    for name in others:
        for moment in OUTSIDE + [(1969, 12, 31, 23, 59, 59), (1941, 9, 1, 12, 0, 0), (1916, 6, 1, 12, 0, 0)]:
            assert _state(tz, name, moment) == ("refused", "linked"), (name, moment)
    assert len(WINDOW_ZONES) == 19
    for name in WINDOW_ZONES:
        for moment in ((1850, 6, 1, 12, 0, 0), (1878, 12, 31, 23, 59, 59)):
            assert _state(tz, name, moment) == ("refused", "linked"), (name, moment)
    # 1960 lies inside three zones' windows only (Oslo's summer times of
    # 1959-65 keep it out of Oslo's).
    cast_1960 = {name for name in WINDOW_ZONES if isinstance(_state(tz, name, OUTSIDE[2]), dict)}
    assert cast_1960 == {"Europe/Stockholm", "Europe/Copenhagen", "Europe/Amsterdam"}


def test_an_impossible_date_is_refused_never_raised(tz):
    assert _state(tz, "Europe/Stockholm", (1900, 2, 29, 12, 0, 0)) == ("refused", "julian")
    assert _state(tz, "Europe/Stockholm", (1300, 2, 29, 12, 0, 0)) == ("refused", "julian")
    # The calendar's first moment, which no positive offset can carry back.
    assert _state(tz, "Europe/Stockholm", (1, 1, 1, 0, 0, 0)) == ("refused", "linked")
    assert _state(tz, "Pacific/Chuuk", (1, 1, 1, 0, 0, 0)) == ("refused", "linked")
    assert _state(tz, "America/Blanc-Sablon", (1, 1, 1, 0, 0, 0)) == ("refused", "linked")


# --- item 3: the seam with the local 1970 cut ------------------------------------

def test_the_seam_at_blanc_sablon(tz):
    window = tz.named_zone_state("America/Blanc-Sablon", 1969, 12, 31, 19, 59, 59)
    assert (window["offset_seconds"], window["abbreviation"]) == (-14400, "AST")
    assert "1966-03-16 04:00 UT" in window["label"]          # the window's, not the record's
    assert _state(tz, "America/Blanc-Sablon", (1969, 12, 31, 20, 0, 0)) == ("refused", "linked")
    assert _state(tz, "America/Blanc-Sablon", (1969, 12, 31, 23, 59, 59)) == ("refused", "linked")
    record = tz.named_zone_state("America/Blanc-Sablon", 1970, 1, 1, 0, 0, 0)
    assert record == {"offset_seconds": -14400, "abbreviation": "AST"}


def test_the_seam_east_of_greenwich(tz, monkeypatch):
    """Stockholm's last window ends at 01:00 local on 1970-01-01: 1969's
    readings come from the window, 1970's from the record."""
    import zoneinfo
    assert tz.named_zone_state("Europe/Stockholm", 1969, 12, 31, 23, 30, 0) == {
        "offset_seconds": 3600, "abbreviation": "CET"}
    assert tz.named_zone_state("Europe/Stockholm", 1970, 1, 1, 0, 30, 0) == {
        "offset_seconds": 3600, "abbreviation": "CET"}

    def no_database(name):
        raise zoneinfo.ZoneInfoNotFoundError(name)
    monkeypatch.setattr(tz, "ZoneInfo", no_database)
    assert tz.named_zone_state("Europe/Stockholm", 1969, 12, 31, 23, 30, 0)["offset_seconds"] == 3600
    assert _state(tz, "Europe/Stockholm", (1970, 1, 1, 0, 30, 0)) == ("refused", "unknown")


def test_atikokan_stays_refused_at_the_seam(tz):
    assert _state(tz, "America/Atikokan", (1969, 12, 31, 20, 0, 0)) == ("refused", "linked")


def test_a_1970_births_year_before_follows_the_windows(engine):
    birth = engine["CivilMoment"](1970, 3, 1, 12, 0, 0)
    past = engine["anniversary_moment"](birth, -1, time_standard="named", zone_name="Europe/Stockholm")
    assert isinstance(past, dict), past
    assert (past["offset_hours"], past["abbreviation"], past["standard"]) == (1.0, "CET", "Europe/Stockholm")
    late = engine["CivilMoment"](1970, 12, 31, 21, 0, 0)
    refused = engine["anniversary_moment"](late, -1, time_standard="named", zone_name="America/Blanc-Sablon")
    assert isinstance(refused, engine["UnresolvedResult"]) and refused.status == "unavailable"
    assert refused.reason == (
        "1969-12-31 21:00:00 is before 1970, and this app casts America/Blanc-Sablon before 1970 only inside the "
        "stretches it takes from the sources; this moment is outside them: the time-zone database keeps "
        "America/Blanc-Sablon only as a link to America/Puerto_Rico, another place's record")
    monaco = engine["anniversary_moment"](birth, -1, time_standard="named", zone_name="Europe/Monaco")
    assert isinstance(monaco, engine["UnresolvedResult"]) and monaco.status == "unavailable"
    assert "this app casts Europe/Monaco before 1970 only inside the stretches" in monaco.reason


# --- item 4: the sentences -------------------------------------------------------

# Ruling 187 (4): Amsterdam's 1909-1916 label is the laws' words, "de
# middelbare zonnetijd van Amsterdam"; AMT is IANA's abbreviation.
AMSTERDAM = (52.3676, 4.9041)
AMSTERDAM_LABEL = ("Amsterdam mean solar time, a named mean time, was then the civil clock across this area; the date "
                   "it is cast from here, 1909-05-02 00:00 UT, is this app's choice: the day after its law took effect")


def test_the_casts_say_what_they_are(tz):
    assert tz.named_zone_state("Europe/Stockholm", 1950, 6, 1, 12, 0, 0) == {
        "offset_seconds": 3600, "abbreviation": "CET"}
    assert tz.named_zone_state("Europe/Stockholm", 1890, 6, 1, 12, 0, 0) == {
        "offset_seconds": 3614, "abbreviation": "Swedish time", "civil_mean_time": True,
        "label": ("Swedish time, a named mean time, was then the civil clock across this area; the date it is cast "
                  "from here, 1879-01-02 00:00 UT, is this app's choice: the day after its law took effect")}
    assert tz.named_zone_state("Europe/Monaco", 1900, 6, 1, 12, 0, 0) == {
        "offset_seconds": 561, "abbreviation": "PMT", "civil_mean_time": True,
        "label": ("PMT, a named mean time, was then the civil clock across this area; the date it is cast from "
                  "here, 1892-06-02 00:00 UT, is this app's choice: the day after its law took effect")}
    assert tz.named_zone_state("Europe/Amsterdam", 1912, 6, 1, 12, 0, 0) == {
        "offset_seconds": 1172, "abbreviation": "Amsterdam mean solar time", "civil_mean_time": True,
        "label": AMSTERDAM_LABEL}
    assert tz.named_zone_state("Pacific/Chuuk", 1941, 9, 1, 12, 0, 0) == {
        "offset_seconds": 32400, "abbreviation": "+09",
        "label": ("The clock here was then +09; the date it is cast from here, 1941-06-17 00:00 UT, is this app's "
                  "choice: the day after the official gazette printed its rule")}
    assert tz.named_zone_state("Europe/Oslo", 1930, 6, 1, 12, 0, 0)["label"] == (
        "The clock here was then CET; the date it is cast from here, 1917-01-01 00:00 UT, is this app's choice: "
        "the first day of a year the sources show without summer time")
    assert tz.named_zone_state("Europe/Monaco", 1912, 6, 1, 12, 0, 0)["label"] == (
        "The clock here was then WET; the date it is cast from here, 1911-04-01 00:00 UT, is this app's choice: "
        "the first day after the month its ordinance took effect in")
    # St Thomas's start follows an order, not a law.
    assert tz.named_zone_state("America/St_Thomas", 1967, 12, 28, 12, 0, 0)["label"] == (
        "The clock here was then AST; the date it is cast from here, 1967-12-24 04:00 UT, is this app's choice: "
        "the day after its order took effect")
    assert tz.named_zone_state("Europe/Bratislava", 1946, 12, 15, 12, 0, 0) == {
        "offset_seconds": 0, "abbreviation": "winter time"}
    # No invented label is printed.
    labels = {w["abbreviation"] for ws in tz.PRE1970_WINDOWS.values() for w in ws}
    assert "AMT" not in labels and not [w for w in tz.PRE1970_WINDOWS["Europe/Amsterdam"] if "AMT" in w["abbreviation"]]
    assert "SET" not in labels and not [w for w in tz.PRE1970_WINDOWS["Europe/Bratislava"]
                                        if w["abbreviation"] == "GMT"]


def _app(date, hms, lat, lon):
    at = make_app(date=date, page="chart")
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hms)
    at.session_state["time_standard_key"] = STD
    at.run()
    assert_no_exception(at, f"{date} {hms} {lat},{lon}")
    return at


STOCKHOLM, BRATISLAVA, CHUUK, MONACO = (59.3293, 18.0686), (48.1486, 17.1077), (7.4256, 151.7800), (43.7384, 7.4246)

# kind: (the page's moment, coordinates, the anniversary's birth and years,
# the zone, what both say).
KINDS = {
    "linked": ("1870-06-01", (12, 0, 0), STOCKHOLM, (1871, 6, 1, 12, 0, 0), -1, "Europe/Stockholm",
               ("is before 1970, and this app casts Europe/Stockholm before 1970 only inside the stretches it takes "
                "from the sources; this moment is outside them", "only as a link to Europe/Berlin, another place's "
                "record")),
    "disputed": ("1916-09-30", (23, 30, 0), STOCKHOLM, (1917, 9, 30, 23, 30, 0), -1, "Europe/Stockholm",
                 ("falls where the sources disagree on when Europe/Stockholm's clocks were turned back",)),
    "ambiguous": ("1946-10-07", (2, 30, 0), BRATISLAVA, (1947, 10, 7, 2, 30, 0), -1, "Europe/Bratislava",
                  ("happens twice in Europe/Bratislava",)),
    "nonexistent": ("1916-05-14", (23, 30, 0), STOCKHOLM, (1917, 5, 14, 23, 30, 0), -1, "Europe/Stockholm",
                    ("does not exist in Europe/Stockholm",)),
    "julian": ("1300-02-29", (12, 0, 0), STOCKHOLM, (1304, 2, 29, 12, 0, 0), -4, "Europe/Stockholm",
               ("is a Julian-calendar date that",)),
}


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_the_box_and_the_anniversary_say_the_same_for_each_refusal_kind(engine, kind):
    date, hms, (lat, lon), birth, years, zone, shared = KINDS[kind]
    moment = tuple(int(x) for x in date.split("-")) + hms
    import time_zones
    assert _state(time_zones, zone, moment) == ("refused", kind)
    at = _app(date, hms, lat, lon)
    errors = [e.value for e in at.sidebar.error]
    assert len(errors) == 1, errors
    reason = engine["anniversary_moment"](engine["CivilMoment"](*birth), years, time_standard="named",
                                          zone_name=zone).reason
    assert shared
    for phrase in shared:
        assert phrase in errors[0], (kind, phrase, errors[0])
        assert phrase in reason, (kind, phrase, reason)
    assert ("Choose LMT (Local Mean Time)" in errors[0] and "Manual UTC offset" in errors[0]
            or "Check the recorded time" in errors[0]), errors[0]


@pytest.mark.parametrize("date, hms, place, box, strip", [
    ("1950-06-01", (12, 0, 0), STOCKHOLM, "**Europe/Stockholm** · UTC offset +01:00 (CET)  \nUT 1950-06-01 11:00:00",
     "· Europe/Stockholm +01:00 ·"),
    ("1890-06-01", (12, 0, 0), STOCKHOLM,
     "**Europe/Stockholm** · UTC offset +01:00:14 (Swedish time)  \nSwedish time, a named mean time, was then the "
     "civil clock across this area; the date it is cast from here, 1879-01-02 00:00 UT, is this app's choice: the "
     "day after its law took effect.  \nUT 1890-06-01 10:59:46", "· Europe/Stockholm +01:00:14 (Swedish time) ·"),
    ("1900-06-01", (12, 0, 0), MONACO,
     "**Europe/Monaco** · UTC offset +00:09:21 (PMT)  \nPMT, a named mean time, was then the civil clock across this "
     "area; the date it is cast from here, 1892-06-02 00:00 UT, is this app's choice: the day after its law took "
     "effect.  \nUT 1900-06-01 11:50:39", "· Europe/Monaco +00:09:21 (PMT) ·"),
    ("1941-09-01", (12, 0, 0), CHUUK,
     "**Pacific/Chuuk** · UTC offset +09:00 (+09)  \nThe clock here was then +09; the date it is cast from here, "
     "1941-06-17 00:00 UT, is this app's choice: the day after the official gazette printed its rule.  \nUT "
     "1941-09-01 03:00:00", "· Pacific/Chuuk +09:00 ·"),
    ("1912-06-01", (12, 0, 0), AMSTERDAM,
     "**Europe/Amsterdam** · UTC offset +00:19:32 (Amsterdam mean solar time)  \nAmsterdam mean solar time, a named "
     "mean time, was then the civil clock across this area; the date it is cast from here, 1909-05-02 00:00 UT, is "
     "this app's choice: the day after its law took effect.  \nUT 1912-06-01 11:40:28",
     "· Europe/Amsterdam +00:19:32 (Amsterdam mean solar time) ·"),
])
def test_the_box_and_the_strip_of_a_window_cast(date, hms, place, box, strip):
    at = _app(date, hms, *place)
    assert not at.sidebar.error, [e.value for e in at.sidebar.error]
    infos = "\n".join(n.value for n in at.sidebar.info)
    assert box in infos, infos
    captions = "\n".join(c.value for c in at.main.caption)
    assert strip in captions, captions


# --- the refusal outside the windows, true in every margin a clip leaves -------

# (page date, time, coordinates, the anniversary's birth, zone, linked target).
# Reykjavik 1968-04-07 and Chuuk 1941-06-10 fall in margins the sources
# establish (the law in force that morning; the notice in force from April)
# that the windows' clipped starts leave out; Stockholm 1870 is before every
# window.
OUTSIDE_THE_WINDOWS = {
    "Reykjavik 1968-04-07": ("1968-04-07", (64.1466, -21.9426), (1969, 4, 7, 12, 0, 0), "Atlantic/Reykjavik",
                             "Africa/Abidjan"),
    "Chuuk 1941-06-10": ("1941-06-10", CHUUK, (1942, 6, 10, 12, 0, 0), "Pacific/Chuuk", "Pacific/Port_Moresby"),
    "Stockholm 1870": ("1870-06-01", STOCKHOLM, (1871, 6, 1, 12, 0, 0), "Europe/Stockholm", "Europe/Berlin"),
}


@pytest.mark.parametrize("case", sorted(OUTSIDE_THE_WINDOWS))
def test_the_refusal_outside_the_windows_says_only_what_is_true(engine, case):
    date, (lat, lon), birth, zone, target = OUTSIDE_THE_WINDOWS[case]
    clause = (f"this app casts {zone} before 1970 only inside the stretches it takes from the sources; this moment "
              "is outside them")
    at = _app(date, (12, 0, 0), lat, lon)
    assert [e.value for e in at.sidebar.error] == [
        f"**{date} 12:00** is before 1970, and {clause}, so there is no standard-time zone to cast it in: the "
        f"time-zone database holds {zone} only as a link to {target}, another place's record. Choose LMT (Local "
        "Mean Time), which takes the birthplace's own longitude, or Manual UTC offset."]
    reason = engine["anniversary_moment"](engine["CivilMoment"](*birth), -1, time_standard="named",
                                          zone_name=zone).reason
    assert reason == (f"{date} 12:00:00 is before 1970, and {clause}: the time-zone database keeps {zone} only as "
                      f"a link to {target}, another place's record")
    assert "the clocks the sources establish" not in reason


# --- a standard-time window's cast on the page, the strip and the exports ------

BRAZZAVILLE, REYKJAVIK, OSLO = (-4.2634, 15.2429), (64.1466, -21.9426), (59.9139, 10.7522)
# (page date, coordinates, zone, offset, the label the row and the exports
# carry, or None where there is none). Ruling 187 (2): every clipped
# standard-time window's sentence takes one form, the clock named after "The
# clock here was then", whether the abbreviation is letters or a number.
STANDARD_CASTS = {
    "Chuuk 1941": ("1941-09-01", CHUUK, "Pacific/Chuuk", "+09:00", "+09",
                   "The clock here was then +09; the date it is cast from here, 1941-06-17 00:00 UT, is this "
                   "app's choice: the day after the official gazette printed its rule"),
    "Reykjavik 1925": ("1925-06-01", REYKJAVIK, "Atlantic/Reykjavik", "-01:00", "-01",
                       "The clock here was then -01; the date it is cast from here, 1922-01-01 00:00 UT, is this "
                       "app's choice: the first day of a year the sources show without summer time"),
    "Brazzaville 1949": ("1949-09-01", BRAZZAVILLE, "Africa/Brazzaville", "+01:00", "WAT",
                         "The clock here was then WAT; the date it is cast from here, 1949-05-02 00:00 UT, is this "
                         "app's choice: the day after the official gazette printed its rule"),
    "Oslo 1930": ("1930-06-01", OSLO, "Europe/Oslo", "+01:00", "CET",
                  "The clock here was then CET; the date it is cast from here, 1917-01-01 00:00 UT, is this app's "
                  "choice: the first day of a year the sources show without summer time"),
    "Stockholm 1950": ("1950-06-01", STOCKHOLM, "Europe/Stockholm", "+01:00", "CET", None),
}


@pytest.mark.parametrize("case", sorted(STANDARD_CASTS))
def test_a_standard_time_windows_cast_names_its_clock_where_a_clock_belongs(case):
    """The label a clipped standard-time window carries opens with its clock,
    so the "Civil clock then" row, the exports' line and the JSON key name a
    clock; a dated window carries none, as any named-zone cast. The strip
    prints the offset alone for both, as for any named-zone cast."""
    date, (lat, lon), zone, offset, abbreviation, label = STANDARD_CASTS[case]
    at = _app(date, (12, 0, 0), lat, lon)
    assert not at.sidebar.error, [e.value for e in at.sidebar.error]
    ut = {"Chuuk 1941": "1941-09-01 03:00:00", "Reykjavik 1925": "1925-06-01 13:00:00",
          "Brazzaville 1949": "1949-09-01 11:00:00", "Oslo 1930": "1930-06-01 11:00:00",
          "Stockholm 1950": "1950-06-01 11:00:00"}[case]
    box = f"**{zone}** · UTC offset {offset} ({abbreviation})  \n" + (f"{label}.  \n" if label else "") + f"UT {ut}"
    assert [n.value for n in at.sidebar.info] == [box + " · Gregorian calendar"]
    captions = [c.value for c in at.main.caption]
    assert captions and captions[0].startswith(f"Unsaved chart · {date} 12:00:00 · {zone} {offset} · "), captions
    rows = {}
    for frame in at.dataframe:
        records = frame.value.to_dict("records")
        if records and records[0].get("Quantity") == "Local time":
            rows = {row["Quantity"]: row["Value"] for row in records}
    assert rows["Time standard"] == zone
    export = at.session_state["_analysis_export"]
    markdown, page = at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]
    if label is None:
        assert "Civil clock then" not in rows and "civil_clock" not in export["input"]
        assert "Civil clock then" not in markdown and "Civil clock then" not in page
    else:
        assert rows["Civil clock then"] == label
        assert export["input"]["civil_clock"] == label
        assert f"| Civil clock then | {label} |" in markdown.splitlines()
        assert f"<tr><td>Civil clock then</td><td>{label.replace(chr(39), '&#x27;')}</td></tr>" in page
    assert "was then the clock here" not in "\n".join([str(export), markdown, page, *map(str, rows.values())])


def test_the_anniversarys_description_joins_the_label_as_a_sentence(engine):
    moment = engine["anniversary_moment"](engine["CivilMoment"](1942, 9, 1, 12, 0, 0), -1, time_standard="named",
                                          zone_name="Pacific/Chuuk")
    text = engine["_anniversary_description"](moment)
    assert text.endswith("; UT 1941-09-01 03:00:00; the clock here was then +09; the date it is cast from here, "
                         "1941-06-17 00:00 UT, is this app's choice: the day after the official gazette printed its "
                         "rule"), text
    assert "; The" not in text and "was then the clock" not in text


def test_amsterdams_label_is_the_laws_words_wherever_it_prints():
    """Ruling 187 (4): the box, the strip, the "Civil clock then" row, JSON
    `civil_clock` and the Markdown and HTML lines all carry the laws' words,
    and AMT, IANA's abbreviation, is printed in none of them."""
    at = _app("1912-06-01", (12, 0, 0), *AMSTERDAM)
    assert not at.sidebar.error, [e.value for e in at.sidebar.error]
    infos = [n.value for n in at.sidebar.info]
    assert infos == ["**Europe/Amsterdam** · UTC offset +00:19:32 (Amsterdam mean solar time)  \n"
                     f"{AMSTERDAM_LABEL}.  \nUT 1912-06-01 11:40:28 · Gregorian calendar"]
    captions = [c.value for c in at.main.caption]
    assert captions and captions[0].startswith(
        "Unsaved chart · 1912-06-01 12:00:00 · Europe/Amsterdam +00:19:32 (Amsterdam mean solar time) · "), captions
    rows = {}
    for frame in at.dataframe:
        records = frame.value.to_dict("records")
        if records and records[0].get("Quantity") == "Local time":
            rows = {row["Quantity"]: row["Value"] for row in records}
    assert rows["Civil clock then"] == AMSTERDAM_LABEL
    export = at.session_state["_analysis_export"]
    markdown, page = at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]
    assert export["input"]["civil_clock"] == AMSTERDAM_LABEL
    assert f"| Civil clock then | {AMSTERDAM_LABEL} |" in markdown.splitlines()
    assert f"<tr><td>Civil clock then</td><td>{AMSTERDAM_LABEL.replace(chr(39), '&#x27;')}</td></tr>" in page
    shown = "\n".join([*infos, captions[0], str(export), markdown, page, *map(str, rows.values())])
    assert "AMT" not in shown


def test_amsterdams_anniversary_says_the_laws_words(engine):
    moment = engine["anniversary_moment"](engine["CivilMoment"](1913, 6, 1, 12, 0, 0), -1, time_standard="named",
                                          zone_name="Europe/Amsterdam")
    text = engine["_anniversary_description"](moment)
    assert text.endswith(f"; UT 1912-06-01 11:40:28; {AMSTERDAM_LABEL}"), text
    assert "AMT" not in text
