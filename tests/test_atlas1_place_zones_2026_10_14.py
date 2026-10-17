"""The zone a place takes (ATLAS1's rebuild: C-01, C-17 and the disputed
clocks; rulings 150, 157 (1), 172, 179 S-03 and S-06, 180 (2) and (3), 190).

The app derived every zone from the coordinates alone, so a border town the
boundaries put a few hundred metres over the line (Hekou, a Chinese county
seat) was cast in another country's clock, and two atlas places (La Aguada
at sea, Liberpolis in land the boundaries give no country) could not be cast
at all. Now one function, time_zones.place_zone, answers for all three places
in app.py that cast a named zone (the sidebar, a saved record's cast, Here &
Now), and the anniversaries of a chart read it too: the derived zone stands,
except where the hand-kept list, data/place_zones.tsv, or an area rule says
otherwise, each with its source. The list is keyed on the place's
coordinates as the atlas gives them, so the zone never travels with the
atlas choice: a saved record restored by its coordinates casts as its pick.

"Serves" is read as the pass's reproduction read it (REPRO_C_D.md's country
check, 19 rows): a zone serves a country when, at the 2026 instants, it gives
an offset some zone the pinned tzdata's zone.tab or zone1970.tab lists for
that country gives.
"""
import ast
import contextlib
import csv
import importlib.resources
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from timezonefinder import TimezoneFinder

from conftest import APP_PATH, assert_no_exception, make_app, source_files, sync_engine_to_environment, ui_source

ROOT = APP_PATH.parent
ATLAS = ROOT / "atlas.db"
LIST = ROOT / "data" / "place_zones.tsv"
NAMED = "Standard time (named zone)"
MANUAL = "Manual UTC offset"
INSTANTS = [datetime(2026, 1, 15, 12, tzinfo=timezone.utc), datetime(2026, 7, 15, 12, tzinfo=timezone.utc)]


@pytest.fixture(scope="module")
def tz():
    import time_zones
    return time_zones


@pytest.fixture(scope="module")
def finder():
    return TimezoneFinder()


@pytest.fixture(scope="module")
def atlas_rows():
    with contextlib.closing(sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True)) as conn:
        return {r[0]: r for r in conn.execute(
            "SELECT c.id, c.name, c.admin1, c.country, c.lat, c.lon, z.name FROM cities c "
            "LEFT JOIN geonames_zones z ON z.id = c.geonames_zone")}


def _zones_of():
    zones = defaultdict(set)
    tab = importlib.resources.files("tzdata") / "zoneinfo"
    for name in ("zone.tab", "zone1970.tab"):
        for line in (tab / name).read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                cols = line.split("\t")
                for cc in cols[0].split(","):
                    zones[cc].add(cols[2])
    return zones


ZONES_OF = _zones_of()
_OFFSETS = {}


def _offsets(zone):
    if zone not in _OFFSETS:
        _OFFSETS[zone] = tuple(i.astimezone(ZoneInfo(zone)).utcoffset() for i in INSTANTS)
    return _OFFSETS[zone]


def serves(zone, country):
    """REPRO_C_D's reading: at each 2026 instant the zone's offset is one some
    zone of the country gives. A country zone.tab lists no zone for (Kosovo)
    is served by no zone and fails no zone."""
    if country not in ZONES_OF:
        return True
    own = [_offsets(z) for z in ZONES_OF[country]]
    mine = _offsets(zone)
    return all(any(o[k] == mine[k] for o in own) for k in range(len(INSTANTS)))


def _list_rows():
    lines = [line for line in LIST.read_text(encoding="utf-8").split("\n") if line and not line.startswith("#")]
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"))) for line in lines[1:]]


def _answer(tz, finder, lat, lon, moment=None):
    try:
        return tz.place_zone(lat, lon, finder, moment)
    except tz.NamedZoneRefusal as refusal:
        return ("refused", refusal.kind, refusal.area, refusal.clocks, refusal.interval)


# --- The list ----------------------------------------------------------------

def test_the_list_holds_atlas_places_with_both_zones_a_rule_a_reason_and_a_source(tz, finder, atlas_rows):
    rows = _list_rows()
    assert len(rows) == 403
    assert len(tz.PLACE_ZONES) == 403
    # build 2's fix round 1 (rulings 198 (1), 201 (1)): the five places no clock record settles left "kept"
    # for three area rules of their own, and the West Bank's 40 rows no rule reached joined its rule;
    # its fix round 2 (ruling 202): four more left "kept", for 'paracels' and two rules of their own
    assert Counter(r["rule"] for r in rows) == {"area:west_bank": 325, "kept": 33, "area:saskatchewan": 20,
                                                "geonames": 9, "area:xinjiang": 4, "unsettled": 1,
                                                "area:cyprus_boundary": 1, "area:sokhumi": 1, "area:golan": 3,
                                                "area:abu_musa": 1, "area:paracels": 2, "area:dhekelia": 1,
                                                "area:kashmir": 2}
    for r in rows:
        gid = int(r["geonameid"])
        assert gid in atlas_rows, r
        _id, name, _admin1, country, lat, lon, geonames_zone = atlas_rows[gid]
        # the place exactly as the atlas gives it, and both zones as the sources give them
        assert (r["name"], r["country"], float(r["lat"]), float(r["lon"])) == (name, country, lat, lon), r
        assert r["lat"] == repr(lat) and r["lon"] == repr(lon), r
        assert r["derived_zone"] == finder.timezone_at(lng=lon, lat=lat), r
        assert r["geonames_zone"] == (geonames_zone or ""), r
        assert r["rule"] in tz.PLACE_ZONE_RULES, r
        assert r["reason"].strip() and r["source"].strip(), r
        if r["rule"] == "geonames":
            assert r["zone"] == r["geonames_zone"] and country in [c for c in ZONES_OF if r["zone"] in ZONES_OF[c]], r
            assert f"GeoNames record {gid}" in r["source"], r
        elif r["rule"] == "kept":
            assert r["zone"] == r["derived_zone"], r
        elif r["rule"] == "unsettled":
            assert len(r["zone"].split()) == 2, r
        elif r["rule"] in UNRECORDED_AREAS:
            assert r["source"].startswith("no clock record is in hand: the only source is "), r
        else:
            assert "DISPUTED_CLOCKS_RAW.md" in r["source"], r
            assert "cluster C" in r["source"] or "the West Bank as one area" in r["source"], r


def test_every_true_exception_names_the_source_it_is_kept_on(tz):
    """The derived zone is kept against C-01's rule only with a clock record:
    the outside research's register. (The five the reproduction's finding
    alone kept, and the four it kept with GeoNames' record agreeing, a data
    record and not a clock record, are refused now: the next tests.)"""
    kept = [r for r in _list_rows() if r["reason"] == "C-01: true exception"]
    assert [r["name"] for r in kept] == ["Akrotiri"]
    (akrotiri,) = kept
    assert akrotiri["rule"] == "kept" and "cluster C00132" in akrotiri["source"], akrotiri
    assert "gives the same zone" not in akrotiri["source"], akrotiri


UNRECORDED_AREAS = {"area:golan", "area:abu_musa", "area:paracels", "area:dhekelia", "area:kashmir"}
UNRECORDED = {167167: "golan", 167444: "golan", 171200: "golan", 400747: "abu_musa", 11496092: "paracels"}
# ruling 202: GeoNames' record gives the derived zone too; the second clock is the zone zone.tab gives the country
UNRECORDED_ALIKE = {12196125: ("dhekelia", "Europe/London"), 12524521: ("kashmir", "Asia/Kolkata"),
                    13527012: ("kashmir", "Asia/Kolkata"), 12166277: ("paracels", "Asia/Ho_Chi_Minh")}


def _zone_tab_zones(country):
    tab = importlib.resources.files("tzdata") / "zoneinfo" / "zone.tab"
    return [line.split("\t")[2] for line in tab.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and line.split("\t")[0] == country]


def test_the_five_places_no_clock_record_settles_are_refused_as_the_areas_are(tz, finder, atlas_rows):
    """Ruling 198 (1): Mas‘adah, Majdal Shams, Buq‘ātā (SY), Abū Mūsá (AE) and
    Hoàng Sa 11496092 (VN), whose only source is the reproduction's finding,
    are refused naming the zone their coordinates give and their coded
    country's, with the offset each gives; a moment both give alike is cast
    (190 (b)). Before, each was kept and cast in the derived zone."""
    rows = {int(r["geonameid"]): r for r in _list_rows() if r["rule"] in UNRECORDED_AREAS}
    assert {gid: r["rule"][5:] for gid, r in rows.items()} == UNRECORDED | {g: a for g, (a, _z) in UNRECORDED_ALIKE.items()}
    for gid, area in UNRECORDED.items():
        r, (_id, _n, _a, country, lat, lon, geonames_zone) = rows[gid], atlas_rows[gid]
        derived = finder.timezone_at(lng=lon, lat=lat)
        clocks = tz.PLACE_ZONE_AREAS[area]["clocks"]
        # the zone the coordinates give, then the coded country's (GeoNames' record, a zone of that country)
        assert clocks == (derived, geonames_zone) and geonames_zone in ZONES_OF[country] and r["zone"] == derived
        assert "boundary" not in tz.PLACE_ZONE_AREAS[area] and tz.PLACE_ZONE_AREAS[area]["unsettled"] == ()
        assert r["reason"] == "C-01: no clock record settles the clock"
        assert "no clock record is in hand" in r["source"] and f"GeoNames record {gid} gives {geonames_zone}" in r["source"]
        refused = _answer(tz, finder, lat, lon, (2026, 1, 15, 12, 0, 0))
        assert refused[:3] == ("refused", "clock_choice", area) and refused[4] is None, (gid, refused)
        assert [z for z, _o in refused[3]] == list(clocks) and refused[3][0][1] != refused[3][1][1]
        # without a moment the rule gives the zone it casts in
        assert tz.place_zone(lat, lon, finder) == derived


def test_the_four_places_kept_on_geonames_alone_are_refused_as_the_five(tz, finder, atlas_rows):
    """Ruling 202: Dhekelia (GB), Abbaspur and Fārward Kahūta (IN) and Hoàng
    Sa 12166277 (VN), kept on the reproduction's finding with GeoNames'
    record giving the derived zone too, a data record and not a clock record,
    are refused as the five are: naming the zone their coordinates give and
    the zone zone.tab gives their coded country, with the offset each gives;
    a moment both give alike is cast (190 (b)). Before, each was kept and cast
    in the derived zone at every moment."""
    rows = {int(r["geonameid"]): r for r in _list_rows()}
    agree = {"dhekelia": (1944, 7, 15, 12, 0, 0), "kashmir": (1947, 1, 15, 12, 0, 0), "paracels": (1970, 1, 15, 12, 0, 0)}
    for gid, (area, own) in UNRECORDED_ALIKE.items():
        r, (_id, _n, _a, country, lat, lon, geonames_zone) = rows[gid], atlas_rows[gid]
        derived = finder.timezone_at(lng=lon, lat=lat)
        assert r["rule"] == f"area:{area}" and r["zone"] == derived == geonames_zone and _zone_tab_zones(country) == [own]
        assert tz.PLACE_ZONE_AREAS[area]["clocks"] == (derived, own) and not serves(derived, country)
        assert "boundary" not in tz.PLACE_ZONE_AREAS[area] and tz.PLACE_ZONE_AREAS[area]["unsettled"] == ()
        assert r["reason"] == "C-01: no clock record settles the clock"
        assert r["source"].startswith("no clock record is in hand: the only source is ")
        assert f"GeoNames record {gid} gives the same zone, a data record, not a clock record" in r["source"]
        assert f"zone.tab gives {country} {own}" in r["source"] and "202" in r["source"]
        refused = _answer(tz, finder, lat, lon, (2026, 1, 15, 12, 0, 0))
        assert refused[:3] == ("refused", "clock_choice", area) and refused[4] is None, (gid, refused)
        assert [z for z, _o in refused[3]] == [derived, own] and refused[3][0][1] != refused[3][1][1]
        assert tz.place_zone(lat, lon, finder, agree[area]) == derived
        assert tz.place_zone(lat, lon, finder) == derived


def test_no_listed_exception_lies_inside_an_area_s_boundary(tz):
    """Area rules come first; no row of another rule is overridden by one."""
    boundaries = {a["boundary"] for a in tz.PLACE_ZONE_AREAS.values() if "boundary" in a}
    assert boundaries == {"Asia/Hebron", "Asia/Urumqi"}
    assert [r for r in _list_rows() if not r["rule"].startswith("area:") and r["derived_zone"] in boundaries] == []


def test_the_list_file_is_read_as_it_is_written(tz):
    raw = LIST.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n") and b'"' not in raw
    assert set(tz.PLACE_ZONES) == {(float(r["lat"]), float(r["lon"])) for r in _list_rows()}


# --- C-01 ------------------------------------------------------------------------

def _city_app(text, date="2000-01-15", at_time=time(12, 0), standard=NAMED, offset=None):
    at = make_app(date=date, page="sources")
    at.session_state["time_input_key"] = at_time
    at.session_state["time_standard_key"] = standard
    if offset is not None:
        at.session_state["utc_offset_key"] = offset
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = text
    return at.run()


def _pick(at, label):
    picker = [s for s in at.sidebar.selectbox if s.label == "Select specific location:"][0]
    assert label in picker.options, picker.options
    picker.select(label).run()
    assert_no_exception(at, label)
    return at


def _zone_box(at):
    return "\n".join(n.value for n in at.sidebar.info if "UTC offset" in n.value)


def _errors(at):
    return [e.value for e in at.sidebar.error]


def test_hekou_is_cast_in_its_own_country_s_clock():
    """C-01's pin: at base the sidebar named Asia/Bangkok, UT 05:00."""
    at = _pick(_city_app("Hekou"), "Hekou, 29 (CN)")
    assert at.session_state["_resolved_lat"] == 22.53851 and at.session_state["_resolved_lon"] == 104.01109
    box = _zone_box(at)
    assert "**Asia/Shanghai** · UTC offset +08:00" in box and "UT 2000-01-15 04:00:00" in box, box
    assert "Asia/Bangkok" not in box


def test_no_atlas_place_is_cast_in_another_country_s_clock_unless_the_list_names_it(tz, finder, atlas_rows):
    """Every atlas row: the zone it takes serves its own country, or the list
    names the row (a kept exception, an area, a refusal). And every row whose
    derived zone is another country's is in the list: C-01's whole class."""
    unlisted, derived_class = [], []
    assert len(atlas_rows) == 236191
    for gid, (_id, name, _a, country, lat, lon, _g) in atlas_rows.items():
        listed = (lat, lon) in tz.PLACE_ZONES
        answer = _answer(tz, finder, lat, lon)
        if isinstance(answer, tuple):
            assert listed, (gid, name, answer)
            continue
        assert answer and not answer.startswith("Etc/"), (gid, name, answer)
        if not serves(answer, country) and not listed:
            unlisted.append((gid, name, country, answer))
        if not serves(finder.timezone_at(lng=lon, lat=lat), country):
            derived_class.append(gid)
    assert unlisted == []
    assert len(derived_class) == 19
    assert all((atlas_rows[g][4], atlas_rows[g][5]) in tz.PLACE_ZONES for g in derived_class)


def test_timezone_at_is_asked_in_one_place():
    calls = []
    files = source_files()
    assert len(files) == 4
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                            and node.func.attr == "timezone_at":
                        calls.append((path.name, fn.name))
        top = [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        assert not [n for t in top for n in ast.walk(t) if isinstance(n, ast.Attribute) and n.attr == "timezone_at"]
    assert calls == [("time_zones.py", "place_zone")]
    # the three places in app.py that cast a named zone each call it
    tree = ast.parse(ui_source())
    for name in ("_here_and_now", "_cast_zone"):
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
        assert "place_zone" in ast.unparse(fn), name
    assert ui_source().count("engine.place_zone(lat, lon, _zone_finder(), (local_dt.year") == 1


@pytest.mark.parametrize("gid, name, zone", [
    (1516393, "Altai", "Asia/Ulaanbaatar"),               # Govi-Altai
    (1515007, "Uliastay", "Asia/Ulaanbaatar"),            # Zavkhan
    (3520271, "Ciudad Río Bravo", "America/Matamoros"),   # Tamaulipas, the US-border strip
])
def test_a_one_country_place_takes_the_zone_zone_tab_s_comment_names(tz, finder, atlas_rows, gid, name, zone):
    """Ruling 180 (3)'s rows. zone.tab gives Asia/Hovd to "Bayan-Olgii, Hovd,
    Uvs" and America/Matamoros to "Coahuila, Nuevo Leon, Tamaulipas (US
    border)": the zone it names for these rows is the derived zone, and
    GeoNames' (Hovd; Monterrey) is not used. (The ruling's premise was the
    reverse; these held at base too: the build's report says so.)"""
    _id, n, _a, country, lat, lon, geonames_zone = atlas_rows[gid]
    assert n == name and tz.place_zone(lat, lon, finder) == zone == finder.timezone_at(lng=lon, lat=lat)
    assert geonames_zone in ("Asia/Hovd", "America/Monterrey") and (lat, lon) not in tz.PLACE_ZONES
    comments = (importlib.resources.files("tzdata") / "zoneinfo" / "zone.tab").read_text(encoding="utf-8")
    assert "MN\t+4801+09139\tAsia/Hovd\tBayan-Olgii, Hovd, Uvs" in comments
    assert "MX\t+2550-09730\tAmerica/Matamoros\tCoahuila, Nuevo Leon, Tamaulipas (US border)" in comments


def test_the_one_country_rows_of_ruling_180_3_are_75_and_none_is_switched(tz, finder, atlas_rows):
    mn = [r for r in atlas_rows.values() if r[3] == "MN" and r[6] == "Asia/Hovd"
          and finder.timezone_at(lng=r[5], lat=r[4]) == "Asia/Ulaanbaatar"]
    mx = [r for r in atlas_rows.values() if r[3] == "MX" and r[6] == "America/Monterrey"
          and finder.timezone_at(lng=r[5], lat=r[4]) == "America/Matamoros"]
    assert (len(mn), len(mx)) == (41, 34) and {r[2] for r in mn} == {"09", "10"} and {r[2] for r in mx} == {"07", "28"}
    assert not [r for r in mn + mx if (r[4], r[5]) in tz.PLACE_ZONES]


# --- C-17 --------------------------------------------------------------------------

def test_no_atlas_place_s_zone_is_none_or_an_ocean_band(tz, finder, atlas_rows):
    """At base La Aguada (Etc/GMT+4) and Liberpolis (Etc/GMT-1) failed this."""
    bad = []
    for gid, (_id, name, _a, _c, lat, lon, _g) in atlas_rows.items():
        answer = _answer(tz, finder, lat, lon)
        if not isinstance(answer, tuple) and (not answer or answer.startswith("Etc/")):
            bad.append((gid, name, answer))
    assert not bad, bad


def test_la_aguada_is_left_out_and_liberpolis_takes_geonames_zone(tz, finder, atlas_rows):
    assert 3785489 not in atlas_rows
    _id, name, _a, country, lat, lon, geonames_zone = atlas_rows[13405691]
    assert (name, country, geonames_zone) == ("Liberpolis", "HR", "Europe/Zagreb")
    assert finder.timezone_at(lng=lon, lat=lat) == "Etc/GMT-1"
    assert tz.place_zone(lat, lon, finder, (2000, 1, 15, 12, 0, 0)) == "Europe/Zagreb"


# --- The areas (item 6) -------------------------------------------------------------

def _place(atlas_rows, gid):
    return atlas_rows[gid][4], atlas_rows[gid][5]


AREA_CASES = [
    # (id, moment, expected: a zone, or (kind, area, interval or None))
    pytest.param(282615, (2026, 1, 15, 12, 0, 0), "Asia/Hebron", id="nablus-equal-offsets"),
    pytest.param(282615, (2026, 3, 27, 12, 0, 0), ("clock_choice", "west_bank", None), id="nablus-clocks-differ"),
    pytest.param(282615, (1966, 7, 1, 12, 0, 0), ("clock_choice", "west_bank", ((1, 1, 1, 0, 0, 0), (1967, 6, 5, 0, 0, 0))),
                 id="nablus-before-1967"),
    pytest.param(282615, (1967, 12, 1, 12, 0, 0), "Asia/Hebron", id="nablus-after-1967-equal"),
    pytest.param(282615, (1996, 1, 15, 12, 0, 0), ("clock_choice", "west_bank", ((1995, 1, 1, 0, 0, 0), (1997, 1, 1, 0, 0, 0))),
                 id="nablus-1995-96"),
    pytest.param(7303419, (2026, 3, 27, 12, 0, 0), ("clock_choice", "west_bank", None), id="east-jerusalem-differ"),
    pytest.param(7303419, (2026, 1, 15, 12, 0, 0), "Asia/Jerusalem", id="east-jerusalem-equal"),
    pytest.param(293397, (2026, 3, 27, 12, 0, 0), "Asia/Jerusalem", id="tel-aviv-outside"),
    pytest.param(9887822, (2026, 3, 27, 12, 0, 0), "Asia/Jerusalem", id="merav-kept"),
    pytest.param(1280849, (2026, 1, 15, 12, 0, 0), ("clock_choice", "xinjiang", None), id="kashgar"),
    pytest.param(8521718, (1990, 7, 1, 12, 0, 0), ("clock_choice", "xinjiang", None), id="bole-listed"),
    pytest.param(1280625, (2026, 1, 15, 12, 0, 0), ("clock_choice", "xinjiang", None), id="mangnai-boundary"),
    pytest.param(1804430, (2026, 1, 15, 12, 0, 0), "Asia/Shanghai", id="lanzhou-outside"),
    pytest.param(8550587, (2026, 1, 15, 12, 0, 0), "Asia/Shanghai", id="duobagou-kept"),
    pytest.param(146189, (2017, 1, 15, 12, 0, 0), ("clock_choice", "cyprus_boundary", None), id="pergamos-split-winter"),
    pytest.param(146189, (2016, 7, 15, 12, 0, 0), "Asia/Famagusta", id="pergamos-summer-before"),
    pytest.param(146189, (2018, 1, 15, 12, 0, 0), "Asia/Famagusta", id="pergamos-winter-after"),
    pytest.param(18918, (2017, 1, 15, 12, 0, 0), "Asia/Nicosia", id="protaras-kept"),
    pytest.param(146286, (2017, 1, 15, 12, 0, 0), "Asia/Famagusta", id="morfou-kept"),
    pytest.param(146268, (2017, 1, 15, 12, 0, 0), "Asia/Nicosia", id="nicosia-outside"),
    pytest.param(6089404, (1972, 4, 29, 12, 0, 0), ("clock_choice", "saskatchewan", ((1, 1, 1, 0, 0, 0), (1972, 4, 30, 0, 0, 0))),
                 id="north-battleford-before"),
    pytest.param(6089404, (1972, 4, 30, 1, 0, 0), ("clock_choice", "saskatchewan", None), id="north-battleford-the-night"),
    pytest.param(6089404, (1972, 4, 30, 12, 0, 0), "America/Swift_Current", id="north-battleford-after"),
    pytest.param(6065592, (1960, 7, 1, 12, 0, 0), ("clock_choice", "saskatchewan", ((1, 1, 1, 0, 0, 0), (1972, 4, 30, 0, 0, 0))),
                 id="maple-creek-south-west"),
    pytest.param(6119109, (1960, 7, 1, 12, 0, 0), "America/Regina", id="regina-outside"),
    pytest.param(6160603, (1960, 7, 1, 12, 0, 0), "America/Swift_Current", id="swift-current-outside"),
    pytest.param(611847, (2009, 12, 31, 12, 0, 0), ("clock_choice", "sokhumi", ((1, 1, 1, 0, 0, 0), (2010, 1, 1, 0, 0, 0))),
                 id="sokhumi-before-2010"),
    pytest.param(611847, (2010, 1, 1, 12, 0, 0), "Europe/Moscow", id="sokhumi-from-2010"),
    pytest.param(611847, (2014, 10, 26, 2, 30, 0), ("clock_choice", "sokhumi", ((2014, 10, 26, 1, 0, 0), (2014, 10, 26, 3, 0, 0))),
                 id="sokhumi-the-2014-hour"),
    pytest.param(611847, (2014, 10, 26, 3, 30, 0), "Europe/Moscow", id="sokhumi-after-the-hour"),
    pytest.param(614622, (2026, 1, 15, 12, 0, 0), "Asia/Tbilisi", id="gagra-outside"),
    pytest.param(1733782, (1975, 1, 15, 12, 0, 0), "Asia/Kuching", id="labuan-no-change"),
    # ruling 201 (1): the West Bank rows both sources put in Asia/Jerusalem, and Gaza's, outside the rule
    pytest.param(282993, (2026, 3, 27, 12, 0, 0), ("clock_choice", "west_bank", None), id="ma-ale-adummim-differ"),
    pytest.param(282993, (2026, 1, 15, 12, 0, 0), "Asia/Jerusalem", id="ma-ale-adummim-equal"),
    pytest.param(282993, (1960, 7, 1, 12, 0, 0), ("clock_choice", "west_bank", ((1, 1, 1, 0, 0, 0), (1967, 6, 5, 0, 0, 0))),
                 id="ma-ale-adummim-before-1967"),
    pytest.param(284375, (2026, 3, 27, 12, 0, 0), ("clock_choice", "west_bank", None), id="battir-differ"),
    pytest.param(281133, (2026, 3, 27, 12, 0, 0), "Asia/Gaza", id="gaza-outside"),
    # ruling 198 (1): the five places no clock record settles; a moment both clocks give alike is cast
    pytest.param(167444, (2026, 1, 15, 12, 0, 0), ("clock_choice", "golan", None), id="majdal-shams-differ"),
    pytest.param(167444, (2020, 1, 15, 12, 0, 0), "Asia/Jerusalem", id="majdal-shams-equal"),
    pytest.param(400747, (2026, 1, 15, 12, 0, 0), ("clock_choice", "abu_musa", None), id="abu-musa-differ"),
    pytest.param(400747, (1978, 1, 15, 12, 0, 0), "Asia/Tehran", id="abu-musa-equal"),
    pytest.param(11496092, (2026, 1, 15, 12, 0, 0), ("clock_choice", "paracels", None), id="hoang-sa-differ"),
    pytest.param(11496092, (1970, 1, 15, 12, 0, 0), "Asia/Shanghai", id="hoang-sa-equal"),
    # ruling 202: the four kept on GeoNames alone; a moment both clocks give alike is cast
    pytest.param(12166277, (2026, 1, 15, 12, 0, 0), ("clock_choice", "paracels", None), id="hoang-sa-12166277-differ"),
    pytest.param(12166277, (1970, 1, 15, 12, 0, 0), "Asia/Shanghai", id="hoang-sa-12166277-equal"),
    pytest.param(12196125, (2026, 1, 15, 12, 0, 0), ("clock_choice", "dhekelia", None), id="dhekelia-differ"),
    pytest.param(12196125, (1944, 7, 15, 12, 0, 0), "Asia/Nicosia", id="dhekelia-equal"),
    pytest.param(12524521, (2026, 1, 15, 12, 0, 0), ("clock_choice", "kashmir", None), id="abbaspur-differ"),
    pytest.param(12524521, (1947, 1, 15, 12, 0, 0), "Asia/Karachi", id="abbaspur-equal"),
    pytest.param(13527012, (2026, 1, 15, 12, 0, 0), ("clock_choice", "kashmir", None), id="farward-kahuta-differ"),
    pytest.param(146839, (2026, 1, 15, 12, 0, 0), "Asia/Nicosia", id="akrotiri-kept"),
    pytest.param(1521368, (2020, 1, 15, 12, 0, 0), "Asia/Qyzylorda", id="baikonur-no-change"),
    pytest.param(1513886, (1985, 1, 15, 12, 0, 0), "Asia/Tashkent", id="jizzakh-no-change"),
]


@pytest.mark.parametrize("gid, moment, expected", AREA_CASES)
def test_an_area_rule_inside_and_outside_and_on_each_side_of_its_dates(tz, finder, atlas_rows, gid, moment, expected):
    lat, lon = _place(atlas_rows, gid)
    answer = _answer(tz, finder, lat, lon, moment)
    if isinstance(expected, str):
        assert answer == expected, (gid, answer)
    else:
        kind, area, interval = expected
        assert answer[:3] == ("refused", kind, area) and answer[4] == interval, (gid, answer)
        # both clocks are named with the offset each gives at that moment
        assert [z for z, _o in answer[3]] == list(tz.PLACE_ZONE_AREAS[area]["clocks"])


def test_every_area_row_of_the_list_is_refused_where_its_clocks_differ_and_cast_where_they_agree(tz, finder):
    """Every place the list gives an area: at a moment its two clocks differ
    (or its rule leaves unsettled) a Standard-time cast is refused; at one
    they agree it is made, in the row's zone."""
    differ = {"west_bank": (2026, 3, 27, 12, 0, 0), "xinjiang": (2026, 1, 15, 12, 0, 0),
              "cyprus_boundary": (2017, 1, 15, 12, 0, 0), "saskatchewan": (1965, 1, 15, 12, 0, 0),
              "sokhumi": (2005, 1, 15, 12, 0, 0), "golan": (2026, 1, 15, 12, 0, 0),
              "abu_musa": (2026, 1, 15, 12, 0, 0), "paracels": (2026, 1, 15, 12, 0, 0),
              "dhekelia": (2026, 1, 15, 12, 0, 0), "kashmir": (2026, 1, 15, 12, 0, 0)}
    agree = {"west_bank": (2026, 1, 15, 12, 0, 0), "xinjiang": None, "cyprus_boundary": (2018, 1, 15, 12, 0, 0),
             "saskatchewan": (2000, 1, 15, 12, 0, 0), "sokhumi": (2026, 1, 15, 12, 0, 0),
             "golan": (2020, 1, 15, 12, 0, 0), "abu_musa": (1978, 1, 15, 12, 0, 0),
             "paracels": (1970, 1, 15, 12, 0, 0), "dhekelia": (1944, 7, 15, 12, 0, 0),
             "kashmir": (1947, 1, 15, 12, 0, 0)}
    assert set(differ) == set(agree) == set(tz.PLACE_ZONE_AREAS)
    rows = [r for r in _list_rows() if r["rule"].startswith("area:")]
    assert len(rows) == 360
    for r in rows:
        area, lat, lon = r["rule"][5:], float(r["lat"]), float(r["lon"])
        refused = _answer(tz, finder, lat, lon, differ[area])
        assert isinstance(refused, tuple) and refused[1:3] == ("clock_choice", area), r
        if agree[area] is not None:
            assert tz.place_zone(lat, lon, finder, agree[area]) == r["zone"], r


def test_a_point_inside_a_boundary_but_not_in_the_list_is_reached_too(tz, finder):
    """The West Bank's and Xinjiang's rules reach the zones zone.tab names for
    them, at any coordinates: a point typed, not picked."""
    assert finder.timezone_at(lng=35.255, lat=32.222) == "Asia/Hebron" and (32.222, 35.255) not in tz.PLACE_ZONES
    assert _answer(tz, finder, 32.222, 35.255, (2026, 3, 27, 12, 0, 0))[1:3] == ("clock_choice", "west_bank")
    assert _answer(tz, finder, 43.8, 87.6, (2026, 1, 15, 12, 0, 0))[1:3] == ("clock_choice", "xinjiang")


def test_the_west_bank_rule_reaches_every_west_bank_row_geonames_codes_ps(tz, finder, atlas_rows):
    """Ruling 201 (1): one rule for the whole area. Every atlas row GeoNames
    codes PS in the West Bank (admin1 WE) is reached, by its list row or by
    Asia/Hebron's boundary: refused where the two clocks differ, cast where
    they agree; the 40 both sources put in Asia/Jerusalem (39 settlements and
    Battir) included, which no rule reached before. Gaza's rows (GZ) are not
    the West Bank and keep their zone."""
    west_bank = [r for r in atlas_rows.values() if r[3] == "PS" and r[2] == "WE"]
    gaza = [r for r in atlas_rows.values() if r[3] == "PS" and r[2] == "GZ"]
    assert len(west_bank) == 423
    assert len(gaza) == 25
    by = Counter()
    for gid, name, _a, _c, lat, lon, geonames_zone in west_bank:
        row = tz.PLACE_ZONES.get((lat, lon))
        derived = finder.timezone_at(lng=lon, lat=lat)
        by["listed" if row else "boundary"] += 1
        assert (row and row["rule"] == "area:west_bank") or (not row and derived == "Asia/Hebron"), (gid, name)
        assert _answer(tz, finder, lat, lon, (2026, 3, 27, 12, 0, 0))[1:3] == ("clock_choice", "west_bank"), gid
        assert tz.place_zone(lat, lon, finder, (2026, 1, 15, 12, 0, 0)) == derived, gid
        if derived == geonames_zone == "Asia/Jerusalem":
            by["both Jerusalem"] += 1
            assert "201 (1)" in row["source"] and "cluster C" not in row["source"], row
    assert by == {"listed": 325, "boundary": 98, "both Jerusalem": 40}
    for gid, _n, _a, _c, lat, lon, _g in gaza:
        assert tz.place_zone(lat, lon, finder, (2026, 3, 27, 12, 0, 0)) == "Asia/Gaza", gid


def test_the_area_rules_come_before_the_list_s_own_rows(tz, finder, monkeypatch):
    """N-13: the step order, held by behaviour. A 'kept' or 'geonames' row
    planted at a point inside an area's reach (Asia/Hebron's boundary) is
    answered by the area rule, not cast by the list: the rule's refusal
    where the clocks differ, the derived zone where they agree, never the
    row's zone."""
    lat, lon = 32.222, 35.255
    assert finder.timezone_at(lng=lon, lat=lat) == "Asia/Hebron" and (lat, lon) not in tz.PLACE_ZONES
    for rule in ("kept", "geonames"):
        planted = dict(tz.PLACE_ZONES)
        planted[(lat, lon)] = {"geonameid": "1", "name": "Planted", "country": "PS", "lat": repr(lat),
                               "lon": repr(lon), "derived_zone": "Asia/Hebron", "geonames_zone": "Asia/Jerusalem",
                               "rule": rule, "zone": "Asia/Jerusalem", "reason": "a plant", "source": "a plant"}
        monkeypatch.setattr(tz, "PLACE_ZONES", planted)
        refused = _answer(tz, finder, lat, lon, (2026, 3, 27, 12, 0, 0))
        assert refused[:3] == ("refused", "clock_choice", "west_bank"), (rule, refused)
        assert tz.place_zone(lat, lon, finder, (2026, 1, 15, 12, 0, 0)) == "Asia/Hebron", rule
        assert tz.place_zone(lat, lon, finder) == "Asia/Hebron", rule


def test_an_unsettled_place_is_refused_naming_both_clocks(tz, finder, atlas_rows):
    lat, lon = _place(atlas_rows, 13645768)                 # Longwa, MM: both sources give Asia/Kolkata
    answer = _answer(tz, finder, lat, lon, (2026, 1, 15, 12, 0, 0))
    assert answer[:2] == ("refused", "unsettled") and answer[3] == (("Asia/Kolkata", 19800), ("Asia/Yangon", 23400))


# The zone review's exceptions CSV (outside git: process/outside_tasks_sol_2026-10-06/LARGE_FILES.md) as
# the regression corpus: a seeded sample (20261014) of its 15,026 atlas rows, with the review's class and
# zones and what this build gives (no moment; 2026-01-15 12:00; 1960-07-01 12:00), and every row the
# build changes. The full comparison is in the build's report.
CSV_SAMPLE = [
    (78776, 'refused', 'Asia/Aden', 'Asia/Aden', 'Asia/Aden', 'Asia/Aden', 'Asia/Aden'),
    (149039, 'refused', 'Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam'),
    (159045, 'refused', 'Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam', 'Africa/Dar_es_Salaam'),
    (219414, 'refused', 'Africa/Lubumbashi', 'Africa/Lubumbashi', 'Africa/Lubumbashi', 'Africa/Lubumbashi', 'Africa/Lubumbashi'),
    (283366, 'differ', 'Asia/Jerusalem', 'Asia/Hebron', 'Asia/Jerusalem', 'Asia/Jerusalem', 'refused:clock_choice'),
    (283636, 'differ', 'Asia/Jerusalem', 'Asia/Hebron', 'Asia/Jerusalem', 'Asia/Jerusalem', 'refused:clock_choice'),
    (285279, 'differ', 'Asia/Jerusalem', 'Asia/Hebron', 'Asia/Jerusalem', 'Asia/Jerusalem', 'refused:clock_choice'),
    (285629, 'refused', 'Asia/Kuwait', 'Asia/Kuwait', 'Asia/Kuwait', 'Asia/Kuwait', 'Asia/Kuwait'),
    (724112, 'refused', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava'),
    (787016, 'refused', 'Europe/Skopje', 'Europe/Skopje', 'Europe/Skopje', 'Europe/Skopje', 'Europe/Skopje'),
    (793121, 'refused', 'Europe/Skopje', 'Europe/Skopje', 'Europe/Skopje', 'Europe/Skopje', 'Europe/Skopje'),
    (1055429, 'refused', 'Indian/Antananarivo', 'Indian/Antananarivo', 'Indian/Antananarivo', 'Indian/Antananarivo', 'Indian/Antananarivo'),
    (1064131, 'refused', 'Indian/Antananarivo', 'Indian/Antananarivo', 'Indian/Antananarivo', 'Indian/Antananarivo', 'Indian/Antananarivo'),
    (1090918, 'refused', 'Indian/Comoro', 'Indian/Comoro', 'Indian/Comoro', 'Indian/Comoro', 'Indian/Comoro'),
    (1735162, 'refused', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur'),
    (1767716, 'refused', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur'),
    (1887974, 'refused', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur'),
    (2226515, 'refused', 'Africa/Douala', 'Africa/Douala', 'Africa/Douala', 'Africa/Douala', 'Africa/Douala'),
    (2239953, 'refused', 'Africa/Luanda', 'Africa/Luanda', 'Africa/Luanda', 'Africa/Luanda', 'Africa/Luanda'),
    (2353688, 'refused', 'Africa/Ouagadougou', 'Africa/Ouagadougou', 'Africa/Ouagadougou', 'Africa/Ouagadougou', 'Africa/Ouagadougou'),
    (2395914, 'refused', 'Africa/Porto-Novo', 'Africa/Porto-Novo', 'Africa/Porto-Novo', 'Africa/Porto-Novo', 'Africa/Porto-Novo'),
    (2396651, 'refused', 'Africa/Libreville', 'Africa/Libreville', 'Africa/Libreville', 'Africa/Libreville', 'Africa/Libreville'),
    (2421690, 'refused', 'Africa/Conakry', 'Africa/Conakry', 'Africa/Conakry', 'Africa/Conakry', 'Africa/Conakry'),
    (2623745, 'refused', 'Europe/Copenhagen', 'Europe/Copenhagen', 'Europe/Copenhagen', 'Europe/Copenhagen', 'Europe/Copenhagen'),
    (2625001, 'refused', 'Europe/Copenhagen', 'Europe/Copenhagen', 'Europe/Copenhagen', 'Europe/Copenhagen', 'Europe/Copenhagen'),
    (2670671, 'refused', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm'),
    (2687487, 'refused', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm'),
    (2708136, 'refused', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm'),
    (2710742, 'refused', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm'),
    (2713516, 'refused', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm', 'Europe/Stockholm'),
    (2747357, 'refused', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam'),
    (2750396, 'refused', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam'),
    (2751021, 'refused', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam'),
    (2754111, 'refused', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam'),
    (2756673, 'refused', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam'),
    (2756688, 'refused', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam'),
    (2760049, 'refused', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam', 'Europe/Amsterdam'),
    (2960060, 'refused', 'Europe/Luxembourg', 'Europe/Luxembourg', 'Europe/Luxembourg', 'Europe/Luxembourg', 'Europe/Luxembourg'),
    (3042068, 'refused', 'Europe/Vaduz', 'Europe/Vaduz', 'Europe/Vaduz', 'Europe/Vaduz', 'Europe/Vaduz'),
    (3057807, 'refused', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava'),
    (3058278, 'refused', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava'),
    (3059206, 'refused', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava'),
    (3060808, 'refused', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava'),
    (3061192, 'refused', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava', 'Europe/Bratislava'),
    (3135137, 'refused', 'Europe/Oslo', 'Europe/Oslo', 'Europe/Oslo', 'Europe/Oslo', 'Europe/Oslo'),
    (3143120, 'refused', 'Europe/Oslo', 'Europe/Oslo', 'Europe/Oslo', 'Europe/Oslo', 'Europe/Oslo'),
    (3187184, 'refused', 'Europe/Ljubljana', 'Europe/Ljubljana', 'Europe/Ljubljana', 'Europe/Ljubljana', 'Europe/Ljubljana'),
    (3187935, 'refused', 'Europe/Ljubljana', 'Europe/Ljubljana', 'Europe/Ljubljana', 'Europe/Ljubljana', 'Europe/Ljubljana'),
    (3189310, 'refused', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb'),
    (3195308, 'refused', 'Europe/Sarajevo', 'Europe/Sarajevo', 'Europe/Sarajevo', 'Europe/Sarajevo', 'Europe/Sarajevo'),
    (3195410, 'refused', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb'),
    (3203298, 'refused', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb'),
    (3216349, 'refused', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb'),
    (3217860, 'refused', 'Europe/Ljubljana', 'Europe/Ljubljana', 'Europe/Ljubljana', 'Europe/Ljubljana', 'Europe/Ljubljana'),
    (3528555, 'differ', 'America/Mexico_City', 'America/Merida', 'America/Mexico_City', 'America/Mexico_City', 'America/Mexico_City'),
    (3575479, 'refused', 'America/St_Kitts', 'America/St_Kitts', 'America/St_Kitts', 'America/St_Kitts', 'America/St_Kitts'),
    (3580713, 'refused', 'America/Cayman', 'America/Cayman', 'America/Cayman', 'America/Cayman', 'America/Cayman'),
    (12500969, 'refused', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb', 'Europe/Zagreb'),
    (12625526, 'refused', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur'),
    (13118227, 'refused', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur', 'Asia/Kuala_Lumpur'),
]
CSV_CHANGED = [
    (1337357, "Asia/Kolkata", "Asia/Thimphu"), (1808588, "Asia/Bangkok", "Asia/Shanghai"),
    (3624436, "America/Panama", "America/Costa_Rica"), (611847, "Asia/Tbilisi", "Europe/Moscow"),
    (13405691, "Etc/GMT-1", "Europe/Zagreb"), (7302858, "Asia/Yangon", "Asia/Kolkata"),
    (10370337, "Asia/Dushanbe", "Asia/Bishkek"), (878023, "Africa/Blantyre", "Africa/Dar_es_Salaam"),
    (878087, "Africa/Blantyre", "Africa/Dar_es_Salaam"), (878242, "Africa/Blantyre", "Africa/Dar_es_Salaam"),
]


def _short(tz, finder, lat, lon, moment):
    answer = _answer(tz, finder, lat, lon, moment)
    return f"refused:{answer[1]}" if isinstance(answer, tuple) else answer


@pytest.mark.parametrize("gid, kind, app_zone, geonames_zone, static, at_2026, at_1960", CSV_SAMPLE,
                         ids=[str(r[0]) for r in CSV_SAMPLE])
def test_a_seeded_sample_of_the_review_s_rows_casts_as_built(tz, finder, atlas_rows, gid, kind, app_zone,
                                                             geonames_zone, static, at_2026, at_1960):
    lat, lon = _place(atlas_rows, gid)
    assert finder.timezone_at(lng=lon, lat=lat) == app_zone
    assert (_short(tz, finder, lat, lon, None), _short(tz, finder, lat, lon, (2026, 1, 15, 12, 0, 0)),
            _short(tz, finder, lat, lon, (1960, 7, 1, 12, 0, 0))) == (static, at_2026, at_1960)


@pytest.mark.parametrize("gid, app_zone, zone", CSV_CHANGED, ids=[str(r[0]) for r in CSV_CHANGED])
def test_every_review_row_this_build_changes_takes_its_listed_zone(tz, finder, atlas_rows, gid, app_zone, zone):
    lat, lon = _place(atlas_rows, gid)
    assert finder.timezone_at(lng=lon, lat=lat) == app_zone
    assert tz.place_zone(lat, lon, finder, (2026, 1, 15, 12, 0, 0)) == zone


# --- The sentences, and the manual offset that casts with either clock ----------

SENTENCES = [
    # (search, label, date, time, the box's sentence)
    ("Nablus", "Nablus, WE (PS)", "2026-03-27", time(12, 0),
     "**2026-03-27 12:00**: at this place the sources leave the clock to the record, and its two clocks differ at "
     "this moment: Palestinian civil time (Asia/Hebron) gives UTC+02:00 and Israeli civil time (Asia/Jerusalem) "
     "gives UTC+03:00. Choose Manual UTC offset and enter the offset of the clock the time was recorded in."),
    ("Nablus", "Nablus, WE (PS)", "1960-07-01", time(12, 0),
     "**1960-07-01 12:00**: the sources do not settle which clock was kept at this place before 1967-06-05: "
     "Palestinian civil time (Asia/Hebron) gives UTC+03:00 and Israeli civil time (Asia/Jerusalem) gives "
     "UTC+02:00 at this moment. Choose Manual UTC offset and enter the offset of the clock the time was recorded in."),
    ("Kashgar", "Kashgar, 13 (CN)", "2000-01-15", time(12, 0),
     "**2000-01-15 12:00**: at this place the sources leave the clock to the record, and its two clocks differ at "
     "this moment: Beijing time (Asia/Shanghai) gives UTC+08:00 and Xinjiang time (Asia/Urumqi) gives UTC+06:00. "
     "Choose Manual UTC offset and enter the offset of the clock the time was recorded in."),
    ("Pérgamos", "Pérgamos, 03 (CY)", "2017-01-15", time(12, 0),
     "**2017-01-15 12:00**: at this place the sources leave the clock to the record, and its two clocks differ at "
     "this moment: the southern clock (Asia/Nicosia) gives UTC+02:00 and the northern clock (Asia/Famagusta) "
     "gives UTC+03:00. Choose Manual UTC offset and enter the offset of the clock the time was recorded in."),
    ("North Battleford", "North Battleford, 11 (CA)", "1965-01-15", time(12, 0),
     "**1965-01-15 12:00**: the sources do not settle which clock was kept at this place before 1972-04-30: the "
     "Central clock (America/Regina) gives UTC-06:00 and the Mountain clock (America/Swift_Current) gives "
     "UTC-07:00 at this moment. Choose Manual UTC offset and enter the offset of the clock the time was recorded in."),
    ("Sokhumi", "Sokhumi, 02 (GE)", "2000-01-15", time(12, 0),
     "**2000-01-15 12:00**: the sources do not settle which clock was kept at this place before 2010-01-01: "
     "Moscow time (Europe/Moscow) gives UTC+03:00 and Tbilisi time (Asia/Tbilisi) gives UTC+04:00 at this "
     "moment. Choose Manual UTC offset and enter the offset of the clock the time was recorded in."),
    ("Sokhumi", "Sokhumi, 02 (GE)", "2014-10-26", time(2, 30),
     "**2014-10-26 02:30**: the sources do not settle which clock was kept at this place between 2014-10-26 "
     "01:00 and 03:00: Moscow time (Europe/Moscow) gives UTC+03:00 and Tbilisi time (Asia/Tbilisi) gives "
     "UTC+04:00 at this moment. Choose Manual UTC offset and enter the offset of the clock the time was recorded in."),
    ("Longwa", "Longwa, 10 (MM)", "2026-01-15", time(12, 0),
     "**2026-01-15 12:00**: the sources this app holds do not settle which clock this place keeps: Asia/Kolkata "
     "gives UTC+05:30 and Asia/Yangon gives UTC+06:30 at this moment. Choose Manual UTC offset and enter the offset "
     "of the clock the time was recorded in."),
    # ruling 198 (1): a place no clock record settles, its two zones named bare (no source names the clocks)
    ("Majdal Shams", "Majdal Shams, 03 (SY)", "2026-01-15", time(12, 0),
     "**2026-01-15 12:00**: at this place the sources leave the clock to the record, and its two clocks differ at "
     "this moment: Asia/Jerusalem gives UTC+02:00 and Asia/Damascus gives UTC+03:00. Choose Manual UTC offset and "
     "enter the offset of the clock the time was recorded in."),
    ("Abū Mūsá", "Abū Mūsá (AE)", "2026-01-15", time(12, 0),
     "**2026-01-15 12:00**: at this place the sources leave the clock to the record, and its two clocks differ at "
     "this moment: Asia/Tehran gives UTC+03:30 and Asia/Dubai gives UTC+04:00. Choose Manual UTC offset and enter "
     "the offset of the clock the time was recorded in."),
    # ruling 202: a place kept on GeoNames alone, its second clock the zone zone.tab gives its coded country
    ("Dhekelia", "Dhekelia (GB)", "2026-01-15", time(12, 0),
     "**2026-01-15 12:00**: at this place the sources leave the clock to the record, and its two clocks differ at "
     "this moment: Asia/Nicosia gives UTC+02:00 and Europe/London gives UTC+00:00. Choose Manual UTC offset and "
     "enter the offset of the clock the time was recorded in."),
    ("Abbaspur", "Abbaspur, 12 (IN)", "2026-01-15", time(12, 0),
     "**2026-01-15 12:00**: at this place the sources leave the clock to the record, and its two clocks differ at "
     "this moment: Asia/Karachi gives UTC+05:00 and Asia/Kolkata gives UTC+05:30. Choose Manual UTC offset and "
     "enter the offset of the clock the time was recorded in."),
    # ruling 201 (1): a West Bank row both sources put in Asia/Jerusalem
    ("Ma‘ale Adummim", "Ma‘ale Adummim, WE (PS)", "2026-03-27", time(12, 0),
     "**2026-03-27 12:00**: at this place the sources leave the clock to the record, and its two clocks differ at "
     "this moment: Palestinian civil time (Asia/Hebron) gives UTC+02:00 and Israeli civil time (Asia/Jerusalem) "
     "gives UTC+03:00. Choose Manual UTC offset and enter the offset of the clock the time was recorded in."),
]


@pytest.mark.parametrize("search, label, date, at_time, sentence", SENTENCES, ids=[f"{s[0]}-{s[2]}" for s in SENTENCES])
def test_a_refused_place_names_both_clocks_and_the_manual_offset_casts_there(search, label, date, at_time, sentence):
    at = _pick(_city_app(search, date=date, at_time=at_time), label)
    assert _errors(at) == [sentence], _errors(at)
    # ruling 201 (2): the option is named by its own label, as the time-standard box shows it
    standard = [s for s in at.sidebar.selectbox if s.label == "Time standard"][0]
    assert f"Choose {MANUAL} and" in sentence and standard.options[2] == MANUAL
    assert not _zone_box(at)
    # the manual offset casts there, with either clock's offset
    at = _pick(_city_app(search, date=date, at_time=at_time, standard=MANUAL, offset=2.0), label)
    assert _errors(at) == [] and "**Manual offset** UTC+02:00" in "\n".join(n.value for n in at.sidebar.info)


def test_no_refusal_sentence_turns_on_a_claim():
    """Sol's warning: the sentences name clocks and offsets, never a state's
    claim (no "occupied", "annexed", "disputed territory", "belongs")."""
    names = next(ast.literal_eval(n.value) for n in ast.parse(ui_source()).body
                 if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["AREA_CLOCK_NAMES"])
    text = " ".join(s[4] for s in SENTENCES) + " " + json.dumps(names, ensure_ascii=False)
    assert set(names) == {"west_bank", "xinjiang", "cyprus_boundary", "saskatchewan", "sokhumi"}
    for word in ("occup", "annex", "territor", "belong", "sovereign", "claim", "illegal", "state of"):
        assert word not in text.lower(), word


# --- The zone does not travel with the atlas choice (item 13) --------------------

def _lifted_cast_zone(finder):
    import engine
    namespace = dict(vars(engine))
    namespace.update({"engine": engine, "_zone_finder": lambda: finder})
    source = ui_source()
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == "_cast_zone":
            exec(ast.get_source_segment(source, node), namespace)
    return namespace["_cast_zone"]


def test_every_listed_place_picked_saved_and_loaded_casts_as_its_pick(tz, finder, tmp_path, monkeypatch):
    """Every list row: picked from the atlas by its own name (the label whose
    pair is the row's), saved through the store, loaded again: the loaded
    record casts the same zone and offset as the pick, at three moments, and
    the app's own _cast_zone of the saved record agrees (151 (1))."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sync_engine_to_environment()
    import engine
    cast_zone = _lifted_cast_zone(finder)
    records, hidden = {}, []
    for r in _list_rows():
        rows = tz.atlas_rows(ATLAS, r["name"])
        pairs = [(lat, lon) for _n, _a, _c, lat, lon in rows]
        lat, lon = float(r["lat"]), float(r["lon"])
        if (lat, lon) not in pairs:
            # one the search's 20-row limit hides under its own name (the
            # KNOWN line of the unreachable places): its pair is the atlas's
            hidden.append(r["name"])
        for date, clock in (("2026-03-27", "12:00:00"), ("1965-01-15", "12:00:00"), ("2000-01-15", "12:00:00")):
            records[f"{r['geonameid']} {date}"] = {
                "date_string": date, "time_string": clock, "time_standard": NAMED, "utc_offset": None,
                "location_query": r["name"], "lat": lat, "lon": lon}
    assert hidden == ["Manda"], hidden           # 878087: Mandalay and others more populous
    assert len(records) == 3 * 403
    engine.write_saved_charts(records)
    loaded = engine.load_saved_charts()
    assert set(loaded) == set(records)
    for name, record in records.items():
        back = loaded[name]
        assert (back["lat"], back["lon"]) == (record["lat"], record["lon"]), name
        moment = tuple(int(x) for x in record["date_string"].split("-")) + (12, 0, 0)
        assert _answer(tz, finder, back["lat"], back["lon"], moment) == \
            _answer(tz, finder, record["lat"], record["lon"], moment), name
        assert cast_zone(back) == cast_zone(record), name


ROUND_TRIPS = [("Hekou", "Hekou, 29 (CN)", "2000-01-15"), ("Liberpolis", "Liberpolis, 10 (HR)", "2000-01-15"),
               ("East Jerusalem", "East Jerusalem, WE (PS)", "2026-01-15"),
               ("Sokhumi", "Sokhumi, 02 (GE)", "2012-01-15"), ("Pérgamos", "Pérgamos, 03 (CY)", "2018-01-15")]


def _load(name):
    fresh = make_app(date="1240-05-23", page="sources").run()
    fresh.sidebar.selectbox(key="chart_picker").select(name).run()
    assert_no_exception(fresh, "the load")
    return fresh


@pytest.mark.parametrize("search, label, date", ROUND_TRIPS, ids=[f"{r[0]}-{r[2]}" for r in ROUND_TRIPS])
def test_a_listed_place_saved_from_the_atlas_loads_into_the_same_cast(tmp_path, monkeypatch, search, label, date):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _pick(_city_app(search, date=date), label)
    before = (_zone_box(at), _errors(at))
    assert before[0] and not before[1], before
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value("Round trip").run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    assert_no_exception(at, "the save")
    fresh = _load("Round trip")
    assert (_zone_box(fresh), _errors(fresh)) == before


REFUSED_TRIPS = [("East Jerusalem", "East Jerusalem, WE (PS)", "2026-03-27"), ("Longwa", "Longwa, 10 (MM)", "2026-01-15"),
                 ("Kashgar", "Kashgar, 13 (CN)", "2026-01-15")]


@pytest.mark.parametrize("search, label, date", REFUSED_TRIPS, ids=[f"{r[0]}-{r[2]}" for r in REFUSED_TRIPS])
def test_a_refused_place_s_record_loads_into_the_same_refusal(tmp_path, monkeypatch, search, label, date):
    """A refused cast cannot be saved from the sidebar; a record holding the
    pick's own place and moment (written to the store as Save writes one)
    loads into the same refusal."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _pick(_city_app(search, date=date), label)
    before = (_zone_box(at), _errors(at))
    assert before[1] and not before[0], before
    sync_engine_to_environment()
    import engine
    engine.write_saved_charts({"Refused": {
        "date_string": date, "time_string": "12:00:00", "time_standard": NAMED, "utc_offset": None,
        "location_query": label, "lat": at.session_state["_resolved_lat"], "lon": at.session_state["_resolved_lon"]}})
    fresh = _load("Refused")
    assert (_zone_box(fresh), _errors(fresh)) == before
