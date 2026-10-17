"""Linked zones before 1970 (the owner's ruling 1 on the re-pass, Q1, L1-N1).

The time-zone database keeps some places only as a link to another place's
record ("L Europe/Berlin Europe/Stockholm"), vouching for their clocks only
from 1970. Before 1970 such a zone is refused under the named standard, with a
sentence naming the zone and pointing to LMT (Local Mean Time) or Manual UTC offset, as D1 refuses
a birth before a zone's first rule. A plain alias of one zone (Asia/Calcutta
for Asia/Kolkata) is not refused. The list is engine.LINKED_ZONES, derived from
the pinned tzdata package by the maintainers' derivation tool (its test is
development-only); the refusal reads the name and the date only, so it is the
same on every machine.
"""
from __future__ import annotations

import hashlib
import importlib.resources
import zoneinfo
from collections import defaultdict
from datetime import time
from pathlib import Path

import pytest
from timezonefinder import TimezoneFinder

from conftest import assert_no_exception, make_app

STD = "Standard time (named zone)"

# The re-pass's three cities: the zone timezonefinder answers there, the place
# whose record the database holds for it, and a date before 1970. Stockholm's
# date is before its pre-1970 windows (1879 on), which now cast its 1947.
CITIES = (
    ("Stockholm", 59.3293, 18.0686, "1870-06-01", "Europe/Stockholm", "Europe/Berlin"),
    ("Reykjavik", 64.1466, -21.9426, "1950-01-15", "Atlantic/Reykjavik", "Africa/Abidjan"),
    ("Amsterdam", 52.3676, 4.9041, "1930-01-15", "Europe/Amsterdam", "Europe/Brussels"),
)


def _app(date, hhmm, lat, lon):
    at = make_app(date=date, page="chart")
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hhmm)
    at.session_state["time_standard_key"] = STD
    at.run()
    assert_no_exception(at, f"{date} {hhmm} {lat},{lon}")
    return at


def _kind(engine, name, y, m, d, hh=12, mm=0, ss=0):
    try:
        engine["named_zone_state"](name, y, m, d, hh, mm, ss)
    except engine["NamedZoneRefusal"] as refusal:
        return refusal.kind
    return None


@pytest.mark.parametrize("city, lat, lon, date, zone, target", CITIES, ids=[c[0] for c in CITIES])
def test_a_linked_zone_before_1970_is_refused_with_a_sentence_naming_it(city, lat, lon, date, zone, target):
    at = _app(date, (12, 0), lat, lon)
    errors = [e.value for e in at.sidebar.error]
    assert len(errors) == 1, errors
    sentence = errors[0]
    for part in (date, "before 1970", zone, f"a link to {target}", "another place's record",
                 "Choose LMT (Local Mean Time), which takes the birthplace's own longitude, or Manual UTC offset.",
                 "no standard-time zone"):
        assert part in sentence, (part, sentence)
    # D1's sentence (a zone's first rule, its reference city) is not the one given.
    assert "kept any standard time" not in sentence and "reference city" not in sentence, sentence
    # No offset is announced, the page's recovery panel carries the sentence,
    # and nothing is cast: no strip, no export.
    infos = "\n".join(n.value for n in at.sidebar.info)
    assert "UTC offset" not in infos, infos
    assert any(date in e.value and zone in e.value for e in at.main.error), "the recovery panel carries it"
    captions = "\n".join(c.value for c in at.main.caption)
    assert zone not in captions, captions
    assert "_analysis_export" not in at.session_state


def test_from_1970_a_linked_zone_is_cast_by_the_database():
    at = _app("1980-01-15", (12, 0), 59.3293, 18.0686)
    infos = "\n".join(n.value for n in at.sidebar.info)
    assert not at.sidebar.error, [e.value for e in at.sidebar.error]
    assert "**Europe/Stockholm** · UTC offset +01:00 (CET)" in infos, infos


# The linked names whose pre-1970 windows reach 1969-12-31 23:59:59, local:
# cast there from the window, not refused (rulings 82, 104 and 106).
CAST_AT_THE_LAST_SECOND = {"Europe/Stockholm", "Europe/Oslo", "Europe/Copenhagen", "Europe/Amsterdam",
                           "Atlantic/Reykjavik"}


def test_every_listed_zone_is_refused_before_1970_and_read_from_1970(engine):
    linked = engine["LINKED_ZONES"]
    assert len(linked) == 106, len(linked)
    before = {name: _kind(engine, name, 1969, 12, 31, 23, 59, 59) for name in linked}
    assert {n for n, k in before.items() if k is None} == CAST_AT_THE_LAST_SECOND
    assert {k for n, k in before.items() if n not in CAST_AT_THE_LAST_SECOND} == {"linked"}
    # A Julian-only day is refused for the same reason where the name has no
    # windows: the database keeps nothing of the place's own then either. A
    # name with windows reads the day against them, and no instant carries it.
    julian = {name: _kind(engine, name, 1300, 2, 29) for name in linked}
    windows = set(engine["PRE1970_WINDOWS"])
    assert len(windows) == 19
    assert {k for n, k in julian.items() if n not in windows} == {"linked"}, julian
    assert {k for n, k in julian.items() if n in windows} == {"julian"}, julian
    after = {name: _kind(engine, name, 1970, 1, 1, 0, 0, 0) for name in linked}
    assert set(after.values()) == {None}, {n: k for n, k in after.items() if k is not None}
    # From 1970 the state is the database's, which is the target's.
    states = {name: (engine["named_zone_state"](name, 1985, 7, 1, 12, 0, 0),
                     engine["named_zone_state"](target, 1985, 7, 1, 12, 0, 0)) for name, target in linked.items()}
    assert [n for n, (mine, theirs) in states.items() if mine != theirs] == []


@pytest.mark.parametrize("alias, zone", (("Asia/Calcutta", "Asia/Kolkata"), ("Europe/Kiev", "Europe/Kyiv"),
                                         ("US/Eastern", "America/New_York")))
def test_a_plain_alias_of_one_zone_is_not_refused(engine, alias, zone):
    """An old or second name for a zone with its own row is that zone: it is
    not on the list, and before 1970 it is read as its zone is."""
    assert alias not in engine["LINKED_ZONES"] and zone not in engine["LINKED_ZONES"]
    state = engine["named_zone_state"]
    assert state(alias, 1950, 6, 1, 12, 0, 0) == state(zone, 1950, 6, 1, 12, 0, 0)


def test_the_refusal_reads_the_name_and_the_date_not_the_machines_database(engine, monkeypatch):
    """A database that kept Stockholm's own record (one built with backzone)
    or none at all gives the same refusal: the decision is the shipped list's."""
    import time_zones                                 # where named_zone_state reads ZoneInfo
    def no_database(name):
        raise zoneinfo.ZoneInfoNotFoundError(name)
    monkeypatch.setattr(time_zones, "ZoneInfo", no_database)
    assert _kind(engine, "Europe/Stockholm", 1870, 6, 1) == "linked"
    assert _kind(engine, "Africa/Accra", 1947, 6, 1) == "linked"
    assert _kind(engine, "Europe/Stockholm", 1980, 6, 1) == "unknown"
    # Inside a pre-1970 window the state is the window's: no database is read.
    assert _kind(engine, "Europe/Stockholm", 1947, 6, 1) is None


def _tzif(name):
    """The compiled record zoneinfo reads for `name`: the first file on its
    search path, else the tzdata package's (zoneinfo's own order)."""
    for root in zoneinfo.TZPATH:
        path = Path(root, name)
        if path.is_file():
            return path.read_bytes()
    return importlib.resources.files("tzdata").joinpath("zoneinfo", *name.split("/")).read_bytes()


def _one_record_one_zone(group, linked):
    """Ruling 68: a group of names sharing one record offends only where a name
    escapes the list -- two or more names off it, or the one name off it not the
    listed names' target. A group whose every name is listed (a database built
    with backzone can give two listed names one record of their own, apart
    from their target's) is refused whole before 1970, and passes."""
    own = [n for n in group if n not in linked]
    if not own:
        return True
    return len(own) == 1 and all(linked[n] == own[0] for n in group if n in linked)


def test_every_zone_timezonefinder_answers_has_a_record_of_its_own_here_or_is_listed(engine):
    """Read off the database zoneinfo reads (the pinned tzdata package alone,
    ruling 71): names whose compiled records are the same file are one record
    under several names. In every such group at most one name is off the list,
    and every listed name in it is linked to that one (ruling 68: a group whose
    every name is listed passes). A name the list misses (a newer release's
    merge, an old alias timezonefinder starts answering) makes a group with two
    names off it."""
    linked = engine["LINKED_ZONES"]
    names = sorted(n for n in TimezoneFinder().timezone_names if not n.startswith("Etc/"))
    groups = defaultdict(list)
    for name in names:
        groups[hashlib.sha256(_tzif(name)).hexdigest()].append(name)
    offenders = [group for group in groups.values() if len(group) > 1 and not _one_record_one_zone(group, linked)]
    assert offenders == []
    assert len(names) == 418 and set(linked) <= set(names), "timezonefinder answers every listed name"


def test_an_anniversary_before_1970_in_a_linked_zone_is_unavailable(engine):
    """The gestation Moons repeat the birth's date a year either side; under a
    linked zone the year before 1970 would be cast at the other place's clocks,
    so it is unavailable with the reason, and the year after is cast. Where a
    pre-1970 window holds the year before (Stockholm's CET), it is cast from
    the window; Monaco's windows end in 1916."""
    birth = engine["CivilMoment"](1970, 3, 1, 12, 0, 0)
    past = engine["anniversary_moment"](birth, -1, time_standard="named", zone_name="Europe/Monaco")
    assert isinstance(past, engine["UnresolvedResult"]), past
    assert "before 1970" in past.reason and "Europe/Paris" in past.reason, past.reason
    renewed = engine["anniversary_moment"](birth, 1, time_standard="named", zone_name="Europe/Monaco")
    assert renewed["standard"] == "Europe/Monaco" and renewed["offset_hours"] == 1.0, renewed
    stockholm = engine["anniversary_moment"](birth, -1, time_standard="named", zone_name="Europe/Stockholm")
    assert stockholm["standard"] == "Europe/Stockholm" and stockholm["offset_hours"] == 1.0, stockholm
