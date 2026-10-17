"""D1's reach: named mean times before standard time (the owner's ruling 35).

D1 refuses a named-zone cast where the zone's record holds only its reference
city's local mean time. After that first record many zones hold a named mean
time (PMT, RMT, MMT ...). Ruling 35: such a time is cast, with a label, only
where it was the area's civil clock -- the research's group (a), keyed on the
name the place lookup returns and on the period, so its doubtful early
stretches are refused; group (b) (the reference city's clock only) and group (c)
(unclear) are refused as D1 refuses LMT; D1's test becomes "the abbreviation is
LMT", which closes the sixteen zones whose record has a later LMT line at
another offset and keeps Lisbon 1884-1912 and Lagos 1908-14 refused; an
anniversary before a zone's first rule, or in a refused period, is unavailable;
Sicily and Sardinia to 1893 and the canton of Geneva to 1894 are refused by
coordinates.

The groups here are transcribed from the research's section 3 as the test's
own expectation; the engine keeps its own list. Linked names (Amsterdam,
Monaco, Kinshasa ...) are refused before 1970 by ruling 1 whatever their target
holds, and are not repeated here.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from timezonefinder import TimezoneFinder

from conftest import assert_no_exception, make_app

STD = "Standard time (named zone)"


ARGENTINA = tuple(f"America/Argentina/{c}" for c in (
    "Buenos_Aires", "Catamarca", "Cordoba", "Jujuy", "La_Rioja", "Mendoza", "Rio_Gallegos", "Salta",
    "San_Juan", "San_Luis", "Tucuman", "Ushuaia"))

# Group (a): the named mean time was the area's civil clock. The value is the
# first local date from which it is cast; None casts the whole stretch.
# Chile 1890-1910 and Bermuda before its 1917 Act are the doubtful early
# stretches; Monrovia's -0:43:08 (1882-1919) is unsourced.
GROUP_A = {
    "Europe/Paris": None, "Europe/Dublin": None,
    "America/Santiago": (1916, 7, 1), "America/Punta_Arenas": (1916, 7, 1), "America/Coyhaique": (1916, 7, 1),
    "America/Montevideo": None, "America/Jamaica": None, "Atlantic/Bermuda": (1917, 4, 2),
    "Asia/Ho_Chi_Minh": None,
    **{name: None for name in ARGENTINA},
    "Africa/Monrovia": (1919, 3, 1), "Europe/Riga": None, "Asia/Tbilisi": None, "Africa/Algiers": None,
    "Europe/Rome": None, "Europe/Zurich": None,
    "Pacific/Auckland": None,
}
# Ruling 66 (the time-zone cross-check): of group (a), only the stretches the
# database's notes establish are cast -- Jamaica's from 1899-03-01, Zurich's and
# Algiers's not at all -- and Easter's, from group (c), from 1891-01-01. Ruling
# 81: Monrovia's from 1970-01-01, Rome's (without coordinates) from 1887-01-01,
# Riga's and Tbilisi's not at all.
CAST = {**{name: start for name, start in GROUP_A.items()
           if name not in ("Europe/Zurich", "Africa/Algiers", "Europe/Riga", "Asia/Tbilisi")},
        "America/Jamaica": (1899, 3, 1), "Africa/Monrovia": (1970, 1, 1), "Europe/Rome": (1887, 1, 1),
        "Pacific/Easter": (1891, 1, 1)}
# Group (b): only the reference city's clock.
GROUP_B = ("Asia/Kolkata", "Europe/Moscow", "Asia/Tehran")
# Group (c): unclear.
GROUP_C = (
    "Europe/Athens", "Europe/Brussels", "Europe/Bucharest", "Europe/Chisinau", "Europe/Helsinki",
    "Europe/Istanbul", "Europe/Kyiv", "Europe/Minsk", "Europe/Prague", "Europe/Simferopol", "Europe/Sofia",
    "Europe/Tallinn", "Europe/Vilnius", "Europe/Warsaw",
    "Asia/Irkutsk", "Asia/Yekaterinburg",
    "Atlantic/Azores", "Atlantic/Madeira", "Atlantic/Stanley",
    "Africa/Tunis",
    "Asia/Baghdad", "Asia/Bangkok", "Asia/Colombo", "Asia/Dhaka", "Asia/Jakarta", "Asia/Jerusalem",
    "Asia/Makassar", "Asia/Pontianak", "Asia/Singapore", "Asia/Yangon",
    "Indian/Maldives",
    "Pacific/Port_Moresby", "Pacific/Bougainville", "Pacific/Easter",
    "America/Asuncion", "America/Bogota", "America/Caracas", "America/Costa_Rica", "America/Grand_Turk",
    "America/Guayaquil", "America/Havana", "America/La_Paz", "America/Managua", "America/Martinique",
    "America/Panama", "America/Paramaribo", "America/Port-au-Prince", "America/Santo_Domingo",
)
# The sixteen zones whose record has a later line again called LMT, at an
# offset other than the first one's.
LATER_LMT = (
    "Africa/Sao_Tome", "America/Adak", "America/Anchorage", "America/Juneau", "America/Lima",
    "America/Metlakatla", "America/Nome", "America/Sitka", "America/Yakutat", "Asia/Manila",
    "Pacific/Apia", "Pacific/Guam", "Pacific/Kosrae", "Pacific/Pago_Pago", "Pacific/Palau",
    "Pacific/Rarotonga",
)

# A city's mean time is named xMT; the composite summer forms the database
# names with them are BST (Bermuda's, La Paz's), IST (Dublin's), LST (Riga's),
# MST and MDST (Moscow's), each a whole hour or two on its mean time.
XMT = re.compile(r"^[A-Z]+MT$")
NOT_MEAN = {"GMT", "LMT", "WEMT", "CEMT"}
COMPOSITE = {"BST", "IST", "LST", "MST", "MDST"}
UTC = timezone.utc


def test_the_groups_are_the_researchs_counts():
    assert len(GROUP_A) == 28 and len(GROUP_B) == 3 and len(GROUP_C) == 48 and len(LATER_LMT) == 16
    assert len(set(GROUP_A) | set(GROUP_B) | set(GROUP_C) | set(LATER_LMT)) == 95


def _verdict(engine, name, local, lat=None, lon=None):
    kwargs = {}
    if lat is not None:
        kwargs.update(latitude=lat, longitude=lon)
    try:
        state = engine["named_zone_state"](name, *local, **kwargs)
    except engine["NamedZoneRefusal"] as refusal:
        return ("refused", refusal.kind)
    return ("cast", state["abbreviation"], bool(state.get("civil_mean_time")))


def _state(zone, stamp):
    moment = datetime.fromtimestamp(stamp, UTC).astimezone(zone)
    return (int(moment.utcoffset().total_seconds()), moment.tzname(), int(moment.dst().total_seconds()))


def _transitions(zone, first=1840, last=1975):
    """Every change of the zone's (offset, name, summer) state between the
    two years, to the second: (UT seconds of the first new second, old, new)."""
    out = []
    stamp = int(datetime(first, 1, 1, tzinfo=UTC).timestamp())
    end = int(datetime(last, 1, 1, tzinfo=UTC).timestamp())
    step = 5 * 86400
    old = _state(zone, stamp)
    while stamp < end:
        nxt = _state(zone, stamp + step)
        if nxt != old:
            lo, hi = stamp, stamp + step
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if _state(zone, mid) == old:
                    lo = mid
                else:
                    hi = mid
            out.append((hi, old, _state(zone, hi)))
            old = _state(zone, hi)
            stamp = hi
            continue
        stamp += step
    return out


def _local(stamp, offset):
    moment = datetime.fromtimestamp(stamp + offset, UTC).replace(tzinfo=None)
    return (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)


def _named(state, standard_before):
    offset, abbr, summer = state
    if abbr in NOT_MEAN:
        return False
    if XMT.match(abbr):
        return True
    return (abbr in COMPOSITE and summer and standard_before is not None and XMT.match(standard_before[1])
            and standard_before[1] not in NOT_MEAN and (offset - standard_before[0]) in (3600, 7200))


def _expected(name, state, named, local, first=False):
    """The ruling's verdict on a state; `first` is the record's first
    stretch, refused with D1's own kind, a later LMT line with its own."""
    if state[1] == "LMT":
        return ("refused", "before_rules" if first else "later_lmt")
    if named:
        start = CAST.get(name, "refused")
        if start != "refused" and (start is None or local[:3] >= start):
            return ("cast", state[1], True)
        return ("refused", "mean_time")
    return ("cast", state[1], False)


def _edges(name):
    """The last second of each state next to a named or LMT state, and the
    first second of the state after it, unambiguous both, plus the middle of
    each named or LMT stretch: (local reading, expected verdict)."""
    zone = ZoneInfo(name)
    changes = _transitions(zone)
    # Each state with the standard (not summer) state in force before it,
    # which says whether a summer form stands on a named mean time.
    standard, named = None, []
    for stamp, old, new in changes:
        if not old[2]:
            standard = old
        named.append((_named(old, standard), _named(new, standard if new[2] else None)))
    cases = []
    for index, ((stamp, old, new), (old_named, new_named)) in enumerate(zip(changes, named)):
        if not (old_named or new_named or old[1] == "LMT" or new[1] == "LMT"):
            continue
        before = _local(stamp - 1 - (old[0] - min(old[0], new[0])), old[0])
        after = _local(stamp + (max(old[0], new[0]) - new[0]), new[0])
        cases.append((before, _expected(name, old, old_named, before, first=index == 0)))
        cases.append((after, _expected(name, new, new_named, after)))
        if new_named or new[1] == "LMT":
            end = changes[index + 1][0] if index + 1 < len(changes) else stamp + 86400 * 365
            middle = _local((stamp + end) // 2, new[0])
            cases.append((middle, _expected(name, new, new_named, middle)))
    return cases


EDGE_ZONES = (*GROUP_A, *GROUP_B, *GROUP_C, *LATER_LMT, "Europe/Lisbon", "Africa/Lagos")


@pytest.mark.parametrize("name", EDGE_ZONES)
def test_the_edges_and_middle_of_every_named_stretch(engine, name):
    """Each named mean time or LMT stretch of the zone, at its first and last
    unambiguous second, its middle, and the seconds either side: the verdict
    the ruling gives that state on that date."""
    cases = _edges(name)
    assert len(cases) >= 2, cases
    wrong = [(local, want, _verdict(engine, name, local)) for local, want in cases
             if _verdict(engine, name, local) != want]
    assert wrong == []


def test_bermudas_mean_time_is_cast_from_its_1917_act(engine):
    """Bermuda's BMT has no change of state at its start date (the Act of
    1917-04-02 that gives the offset), so the edges above do not reach it."""
    assert _verdict(engine, "Atlantic/Bermuda", (1917, 4, 1, 23, 59, 59)) == ("refused", "mean_time")
    assert _verdict(engine, "Atlantic/Bermuda", (1917, 4, 2, 0, 0, 0)) == ("cast", "BMT", True)


def test_lisbon_1884_to_1912_stays_refused(engine):
    """Lisbon's record repeats its first state, LMT -0:36:45, from 1884 to
    1912: refused throughout, as before."""
    for local in ((1884, 1, 1, 0, 0, 0), (1884, 1, 1, 0, 36, 45), (1900, 6, 1, 12, 0, 0),
                  (1911, 12, 31, 23, 23, 14)):
        assert _verdict(engine, "Europe/Lisbon", local) == ("refused", "before_rules"), local
    assert _verdict(engine, "Europe/Lisbon", (1912, 1, 1, 0, 0, 0)) == ("cast", "WET", False)


def test_lagos_1908_to_1914_stays_refused(engine):
    """Lagos returns to its own LMT from 1908 to 1914 after GMT from 1905:
    the GMT stretch is cast, the return refused, as before -- as a later
    line of LMT, not as a reading before the zone kept any time."""
    assert _verdict(engine, "Africa/Lagos", (1908, 6, 30, 23, 59, 59)) == ("cast", "GMT", False)
    assert _verdict(engine, "Africa/Lagos", (1905, 6, 1, 12, 0, 0)) == ("refused", "before_rules")
    for local in ((1908, 7, 1, 0, 13, 35), (1910, 6, 1, 12, 0, 0), (1913, 12, 31, 23, 59, 59)):
        assert _verdict(engine, "Africa/Lagos", local) == ("refused", "later_lmt"), local
    assert _verdict(engine, "Africa/Lagos", (1914, 1, 1, 0, 16, 25)) == ("cast", "+0030", False)


def test_no_named_mean_time_or_lmt_is_cast_unlabelled_anywhere(engine):
    names = sorted(n for n in TimezoneFinder().timezone_names if not n.startswith("Etc/"))
    assert len(names) == 418
    labelled, unlabelled = set(), []
    for name in names:
        for year in range(1840, 1970):
            for month in (1, 7):
                verdict = _verdict(engine, name, (year, month, 1, 12, 0, 0))
                if verdict[0] != "cast":
                    continue
                abbr = verdict[1]
                if abbr == "LMT" or (XMT.match(abbr) and abbr not in NOT_MEAN and not verdict[2]):
                    unlabelled.append((name, year, month, abbr))
                if verdict[2]:
                    labelled.add(name)
    assert unlabelled == []
    # Ruling 81 (a): Monrovia's cast stretch, 1970-1972, lies past this sweep's years.
    cast = {name for name, start in CAST.items() if start is None or start < (1970, 1, 1)}
    # The pre-1970 windows' three named mean times (Swedish time, Amsterdam's
    # AMT, Monaco's Paris mean time) are cast labelled in their windows.
    cast |= {"Europe/Stockholm", "Europe/Amsterdam", "Europe/Monaco"}
    assert labelled == cast, sorted(labelled ^ cast)


# --- Rome's and Zurich's exceptions, by coordinates ---------------------------------------------

SICILY = {"Palermo": (38.1112, 13.3524), "Messina": (38.1938, 15.5542), "Lipari": (38.4814, 14.9397),
          "Stromboli": (38.7918, 15.2112), "Ustica": (38.7105, 13.1913), "Pantelleria": (36.8315, 11.9450),
          "Lampedusa": (35.5111, 12.5963), "Siracusa": (37.0316, 15.2124), "Capo Peloro": (38.2679, 15.6531)}
SARDINIA = {"Cagliari": (39.2172, 9.1133), "Olbia": (40.9233, 9.5027), "La Maddalena": (41.2128, 9.4055),
            "Carloforte": (39.1455, 8.3064)}
ROME_ELSEWHERE = {"Reggio Calabria": (38.1035, 15.6398), "Villa San Giovanni": (38.2181, 15.6385),
                  "Punta Pezzo": (38.2312, 15.6355), "Scilla": (38.2507, 15.7190), "Tropea": (38.6753, 15.8949),
                  "Rome": (41.9028, 12.4964), "Milan": (45.4642, 9.1896), "Venice": (45.4372, 12.3346)}
GENEVA = {"Geneva": (46.2018, 6.1466), "Versoix": (46.2912, 6.1565), "Hermance": (46.3022, 6.2437),
          "Celigny": (46.3506, 6.1949), "Sauverny": (46.3116, 6.1206)}
SWISS_ELSEWHERE = {"Coppet": (46.3164, 6.1928), "Mies": (46.3060, 6.1723), "Chavannes-des-Bois": (46.3147, 6.1326),
                   "Founex": (46.3338, 6.1944), "Nyon": (46.3821, 6.2403), "Lausanne": (46.5218, 6.6327),
                   "Bern": (46.9485, 7.4522), "Zurich": (47.3744, 8.5410)}


def test_the_places_are_in_the_zones_named():
    finder = TimezoneFinder()
    for places, zone in ((SICILY, "Europe/Rome"), (SARDINIA, "Europe/Rome"), (ROME_ELSEWHERE, "Europe/Rome"),
                         (GENEVA, "Europe/Zurich"), (SWISS_ELSEWHERE, "Europe/Zurich")):
        assert {p: finder.timezone_at(lat=a, lng=b) for p, (a, b) in places.items()} == {p: zone for p in places}


@pytest.mark.parametrize("place", sorted(SICILY) + sorted(SARDINIA))
def test_sicily_and_sardinia_are_refused_under_rome_mean_time(engine, place):
    lat, lon = {**SICILY, **SARDINIA}[place]
    for local in ((1866, 12, 12, 0, 0, 0), (1880, 6, 1, 12, 0, 0), (1893, 10, 31, 23, 49, 55)):
        assert _verdict(engine, "Europe/Rome", local, lat, lon) == ("refused", "mean_time_exception"), local
    assert _verdict(engine, "Europe/Rome", (1866, 12, 11, 23, 59, 59), lat, lon) == ("refused", "before_rules")
    assert _verdict(engine, "Europe/Rome", (1893, 11, 1, 0, 0, 0), lat, lon) == ("cast", "CET", False)


@pytest.mark.parametrize("place", sorted(ROME_ELSEWHERE))
def test_the_rest_of_romes_zone_takes_rome_mean_time_from_its_dates(engine, place):
    lat, lon = ROME_ELSEWHERE[place]
    for local in ((1866, 12, 12, 0, 0, 0), (1880, 6, 1, 12, 0, 0), (1893, 10, 31, 23, 49, 55)):
        # Ruling 61 (a): Venice's public clocks took Rome's time on 1880-05-01. Ruling 81 (b): Milan's on
        # 1866-12-12; the rest of the mainland's by 1886, so from 1887-01-01.
        if place == "Venice" and local[:3] < (1880, 5, 1):
            want = ("refused", "mean_time_city")
        elif place not in ("Milan", "Venice") and local[:3] < (1887, 1, 1):
            want = ("refused", "mean_time")
        else:
            want = ("cast", "RMT", True)
        assert _verdict(engine, "Europe/Rome", local, lat, lon) == want, local


@pytest.mark.parametrize("place", sorted(GENEVA))
def test_the_canton_of_geneva_is_refused_under_bern_mean_time(engine, place):
    lat, lon = GENEVA[place]
    for local in ((1853, 7, 16, 0, 0, 0), (1880, 6, 1, 12, 0, 0), (1894, 5, 31, 23, 59, 59)):
        assert _verdict(engine, "Europe/Zurich", local, lat, lon) == ("refused", "mean_time_exception"), local
    assert _verdict(engine, "Europe/Zurich", (1853, 7, 15, 23, 55, 37), lat, lon) == ("refused", "before_rules")
    assert _verdict(engine, "Europe/Zurich", (1894, 6, 1, 0, 30, 14), lat, lon) == ("cast", "CET", False)


@pytest.mark.parametrize("place", sorted(SWISS_ELSEWHERE))
def test_the_rest_of_switzerland_is_refused_under_bern_mean_time(engine, place):
    lat, lon = SWISS_ELSEWHERE[place]
    for local in ((1853, 7, 16, 0, 0, 0), (1880, 6, 1, 12, 0, 0), (1894, 5, 31, 23, 59, 59)):
        # Ruling 66: Zurich's 1853 is postal and telegraph time; no note dates the civil clock.
        assert _verdict(engine, "Europe/Zurich", local, lat, lon) == ("refused", "mean_time"), local


# --- The page: the label and the refusals ----------------------------------------------------------

def _app(day, hhmm, lat, lon):
    at = make_app(date=day, page="chart")
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hhmm)
    at.session_state["time_standard_key"] = STD
    at.run()
    assert_no_exception(at, f"{day} {hhmm} {lat},{lon}")
    return at


def _box(at):
    return "\n".join([n.value for n in at.sidebar.info] + [n.value for n in at.sidebar.error])


def _refused_on_the_page(at, day, parts):
    errors = [e.value for e in at.sidebar.error]
    assert len(errors) == 1, errors
    for part in (day, "Choose LMT (Local Mean Time), which takes the birthplace's own longitude, or Manual UTC "
                 "offset.", *parts):
        assert part in errors[0], (part, errors[0])
    infos = "\n".join(n.value for n in at.sidebar.info)
    assert "UTC offset" not in infos, infos
    assert any(day in e.value for e in at.main.error), "the recovery panel carries the sentence"
    assert "_analysis_export" not in at.session_state
    return errors[0]


@pytest.mark.parametrize("place, day, lat, lon, zone, offset, abbr", (
    ("Lyon", "1900-06-01", 45.7640, 4.8357, "Europe/Paris", "+00:09:21", "PMT"),
    ("Cordoba", "1900-06-01", -31.4201, -64.1888, "America/Argentina/Cordoba", "-04:16:48", "CMT"),
    ("Monrovia", "1971-06-01", 6.3, -10.8, "Africa/Monrovia", "-00:44:30", "MMT"),
    ("Milan", "1880-06-01", 45.4642, 9.1916, "Europe/Rome", "+00:49:56", "RMT"),
), ids=("Lyon", "Cordoba", "Monrovia", "Milan"))
def test_group_a_is_cast_with_the_label(place, day, lat, lon, zone, offset, abbr):
    at = _app(day, (12, 0), lat, lon)
    text = _box(at)
    assert not at.sidebar.error, text
    assert f"**{zone}** · UTC offset {offset} ({abbr})" in text, text
    assert f"{abbr}, a named mean time, was then the civil clock across this area." in text, text


SUMMER = "IST, summer time kept on DMT (a named mean time), was then the civil clock across this area"
PLAIN = "DMT, a named mean time, was then the civil clock across this area"


def test_a_summer_form_names_the_mean_time_it_was_kept_on(engine):
    """Dublin's IST of summer 1916 is summer time on Dublin Mean Time, not a
    mean time of its own; DMT before it is the mean time itself. So are
    Riga's LST on RMT and Bermuda's BST on BMT."""
    state = engine["named_zone_state"]
    assert state("Europe/Dublin", 1916, 7, 1, 12, 0, 0)["label"] == SUMMER
    assert state("Europe/Dublin", 1916, 4, 1, 12, 0, 0)["label"] == PLAIN
    with pytest.raises(engine["NamedZoneRefusal"]) as riga:  # ruling 66: Riga's early period is refused
        state("Europe/Riga", 1918, 6, 1, 12, 0, 0)
    assert (riga.value.kind, riga.value.kept_on) == ("mean_time", "RMT")
    assert state("Atlantic/Bermuda", 1918, 6, 1, 12, 0, 0)["label"].startswith("BST, summer time kept on BMT (")
    assert state("Europe/Paris", 1900, 6, 1, 12, 0, 0)["label"] == \
        "PMT, a named mean time, was then the civil clock across this area"
    assert "label" not in state("Europe/Paris", 1912, 1, 1, 12, 0, 0)


def test_the_box_names_dublins_summer_time_and_mean_time():
    summer, plain = _app("1916-07-01", (12, 0), 53.3498, -6.2603), _app("1916-04-01", (12, 0), 53.3498, -6.2603)
    assert "UTC offset +00:34:39 (IST)" in _box(summer) and f"{SUMMER}." in _box(summer), _box(summer)
    assert "UTC offset -00:25:21 (DMT)" in _box(plain) and f"{PLAIN}." in _box(plain), _box(plain)
    assert "a named mean time, was" not in _box(summer).replace(SUMMER, ""), _box(summer)


def _calculation_rows(at):
    for frame in at.dataframe:
        rows = frame.value.to_dict("records")
        if rows and rows[0].get("Quantity") == "Local time":
            return {row["Quantity"]: row["Value"] for row in rows}
    raise AssertionError("no Calculation table on the page")


LYON_LABEL = "PMT, a named mean time, was then the civil clock across this area"


def test_the_calculation_table_and_the_three_exports_carry_the_label():
    """Lyon 1900: the Calculation table gives the civil clock then under the
    time standard, and the JSON's input block, the Markdown and the HTML
    carry it beside the zone and the offset."""
    at = _app("1900-06-01", (12, 0), 45.7640, 4.8357)
    rows = _calculation_rows(at)
    assert rows["Time standard"] == "Europe/Paris" and rows["Civil clock then"] == LYON_LABEL, rows
    export = at.session_state["_analysis_export"]
    assert export["input"]["timezone"] == "Europe/Paris"
    assert export["input"]["civil_clock"] == LYON_LABEL, export["input"]
    assert export["input"]["utc_offset_hours"] == pytest.approx((9 * 60 + 21) / 3600.0)
    markdown, page = at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]
    assert f"| Civil clock then | {LYON_LABEL} |" in markdown
    assert "Civil clock then" in page and LYON_LABEL in page


def test_a_chart_at_standard_time_carries_no_label():
    at = _app("1912-06-01", (12, 0), 45.7640, 4.8357)
    assert "Civil clock then" not in _calculation_rows(at)
    export = at.session_state["_analysis_export"]
    assert export["input"]["timezone"] == "Europe/Paris" and "civil_clock" not in export["input"]
    assert "Civil clock then" not in at.session_state["_analysis_markdown"]
    assert "Civil clock then" not in at.session_state["_analysis_html"]


@pytest.mark.parametrize("place, day, lat, lon, zone, abbr", (
    ("Bombay", "1880-06-01", 19.0760, 72.8777, "Asia/Kolkata", "MMT"),
    ("St Petersburg", "1900-06-01", 59.9311, 30.3609, "Europe/Moscow", "MMT"),
    ("Tabriz", "1920-06-01", 38.0800, 46.2919, "Asia/Tehran", "TMT"),
    ("Athens", "1900-06-01", 37.9838, 23.7275, "Europe/Athens", "AMT"),
    ("Valparaiso", "1900-06-01", -33.0472, -71.6127, "America/Santiago", "SMT"),
    ("Bermuda", "1900-06-01", 32.2949, -64.7814, "Atlantic/Bermuda", "BMT"),
), ids=("Bombay", "StPetersburg", "Tabriz", "Athens", "Valparaiso", "Bermuda"))
def test_an_unvouched_named_mean_time_is_refused_on_the_page(place, day, lat, lon, zone, abbr):
    at = _app(day, (12, 0), lat, lon)
    sentence = _refused_on_the_page(at, day, (zone, abbr, "no standard-time zone"))
    assert "a link to" not in sentence, sentence


@pytest.mark.parametrize("day, lat, lon, zone, abbr, area, until", (
    ("1880-06-01", 38.1112, 13.3524, "Europe/Rome", "RMT", "Sicily", "1893"),
    ("1880-06-01", 39.2172, 9.1133, "Europe/Rome", "RMT", "Sardinia", "1893"),
    ("1880-06-01", 46.2018, 6.1466, "Europe/Zurich", "BMT", "the canton of Geneva", "1894"),
), ids=("Palermo", "Cagliari", "Geneva"))
def test_rome_and_zurichs_exceptions_are_refused_on_the_page(day, lat, lon, zone, abbr, area, until):
    at = _app(day, (12, 0), lat, lon)
    _refused_on_the_page(at, day, (zone, abbr, area, until))


LATER_LMT_SENTENCE = ("falls where {zone}'s record holds local mean time (LMT), a time taken from one place's "
                      "meridian and not a standard time, so there is no standard-time zone to cast it in.")


@pytest.mark.parametrize("day, lat, lon, zone", (
    ("1880-06-01", 57.0531, -135.3300, "America/Sitka"),
    # Lagos kept GMT from 1905 to 1908 before its record returned to LMT, so
    # "before it kept any standard time" would be false there.
    ("1910-06-01", 6.5244, 3.3792, "Africa/Lagos"),
    # Sao Tome's later LMT is Lisbon's mean time, not its own reference
    # city's, so "the local mean time of its reference city" would be false.
    ("1900-06-01", 0.3365, 6.7273, "Africa/Sao_Tome"),
), ids=("Sitka", "Lagos", "SaoTome"))
def test_a_later_lmt_line_is_refused_on_the_page_with_a_sentence_of_its_own(day, lat, lon, zone):
    at = _app(day, (12, 0), lat, lon)
    sentence = _refused_on_the_page(at, day, (zone, LATER_LMT_SENTENCE.format(zone=zone)))
    assert "kept any standard time" not in sentence and "reference city" not in sentence, sentence


def test_lisbon_1900_keeps_d1s_sentence_on_the_page():
    """Lisbon's record holds its first state, Lisbon's own LMT, until 1912:
    D1's sentence is true of it, and it keeps it."""
    at = _app("1900-06-01", (12, 0), 38.7223, -9.1393)
    _refused_on_the_page(at, "1900-06-01", ("is before Europe/Lisbon kept any standard time", "reference city"))


def test_only_lagos_returns_to_its_first_lmt(engine):
    """The one entry of LMT_RETURNS is the only zone the place lookup answers
    (linked names apart, refused before 1970 by ruling 1) whose record, after
    keeping another state, holds its first state again when that state is
    LMT (1 Jan and 1 Jul, 1800-1969); its date is the first day of the
    return. (Antarctica/Davis and Antarctica/Macquarie return to their
    uninhabited "-00", which is not LMT.)"""
    returns = {}
    linked = engine["LINKED_ZONES"]
    for name in sorted(n for n in TimezoneFinder().timezone_names if not n.startswith("Etc/") and n not in linked):
        zone = ZoneInfo(name)
        first = datetime(1, 1, 1, tzinfo=zone)
        first = (first.utcoffset(), first.tzname())
        left = False
        for year in range(1800, 1970):
            for month in (1, 7):
                moment = datetime(year, month, 1, 12, tzinfo=zone)
                state = (moment.utcoffset(), moment.tzname())
                if state != first:
                    left = True
                elif left and name not in returns:
                    returns[name] = (year, month)
    assert returns == {"Africa/Lagos": (1908, 7), "Antarctica/Davis": (1965, 1), "Antarctica/Macquarie": (1919, 7)}
    assert {n for n in returns if datetime(1, 1, 1, tzinfo=ZoneInfo(n)).tzname() == "LMT"} == {"Africa/Lagos"}
    assert engine["LMT_RETURNS"] == {"Africa/Lagos": (1908, 7, 1)}
    assert _verdict(engine, "Africa/Lagos", (1908, 6, 30, 23, 59, 59))[0] == "cast"


# --- Anniversaries ------------------------------------------------------------------------------------

def _anniversary(engine, birth, years, zone, lat=None, lon=None):
    kwargs = {"time_standard": "named", "zone_name": zone}
    if lat is not None:
        kwargs.update(latitude=lat, longitude=lon)
    return engine["anniversary_moment"](engine["CivilMoment"](*birth), years, **kwargs)


@pytest.mark.parametrize("birth, zone, lat, lon", (
    ((1867, 6, 1, 12, 0, 0), "Europe/Rome", 45.4642, 9.1896),
    ((1912, 6, 1, 12, 0, 0), "Europe/Lisbon", 38.7223, -9.1393),
), ids=("Milan-1866", "Lisbon-1911"))
def test_an_anniversary_before_a_zones_first_rule_is_unavailable(engine, birth, zone, lat, lon):
    past = _anniversary(engine, birth, -1, zone, lat, lon)
    assert isinstance(past, engine["UnresolvedResult"]) and past.status == "unavailable", past
    assert zone in past.reason, past.reason


@pytest.mark.parametrize("birth, zone, lat, lon, word", (
    ((1906, 6, 1, 12, 0, 0), "Asia/Kolkata", 19.0760, 72.8777, "MMT"),
    ((1901, 6, 1, 12, 0, 0), "America/Sitka", 57.0531, -135.3300, "local mean time (LMT)"),
    ((1894, 6, 1, 12, 0, 0), "Europe/Rome", 38.1112, 13.3524, "Sicily"),
    ((1910, 6, 1, 12, 0, 0), "America/Santiago", -33.0472, -71.6127, "SMT"),
), ids=("Bombay-1905", "Sitka-1900", "Palermo-1893", "Valparaiso-1909"))
def test_an_anniversary_in_a_refused_period_is_unavailable(engine, birth, zone, lat, lon, word):
    past = _anniversary(engine, birth, -1, zone, lat, lon)
    assert isinstance(past, engine["UnresolvedResult"]) and past.status == "unavailable", past
    assert word in past.reason and zone in past.reason, past.reason
    renewed = _anniversary(engine, birth, 1, zone, lat, lon)
    assert not isinstance(renewed, engine["UnresolvedResult"]), renewed


@pytest.mark.parametrize("birth, zone, lat, lon, abbr", (
    ((1911, 6, 1, 12, 0, 0), "Europe/Paris", 45.7640, 4.8357, "PMT"),
    ((1894, 6, 1, 12, 0, 0), "Europe/Rome", 45.4642, 9.1896, "RMT"),
), ids=("Lyon-1910", "Milan-1893"))
def test_an_anniversary_in_a_group_a_stretch_is_cast_with_the_label(engine, birth, zone, lat, lon, abbr):
    past = _anniversary(engine, birth, -1, zone, lat, lon)
    assert not isinstance(past, engine["UnresolvedResult"]), past
    assert past["civil_mean_time"] is True, past
    assert f"{abbr}, a named mean time, was then the civil clock across this area" in \
        engine["_anniversary_description"](past)


def test_the_gestation_moons_carry_the_birthplace_to_the_anniversary(engine):
    birth = engine["CivilMoment"](1894, 6, 1, 12, 0, 0)
    jd = engine["swe"].julday(1894, 6, 1, 11.0, engine["swe"].GREG_CAL)
    context = {"local_moment": birth, "time_standard": STD, "timezone": "Europe/Rome",
               "utc_offset_hours": 1.0, "latitude": 38.1112, "longitude": 13.3524}
    moons = engine["gestation_moons"](jd, context)
    assert isinstance(moons["past"]["result"], engine["UnresolvedResult"]), moons["past"]
    assert "Sicily" in moons["past"]["result"].reason
    assert not isinstance(moons["renewed"]["result"], engine["UnresolvedResult"])
