"""D1's reach with the time-zone cross-check applied (the owner's rulings 66,
61 (a), (b), (d) and 68).

Ruling 66 applies ruling 35's test strictly: a named mean time is cast, with its
label, only for the stretches the time-zone database's own notes establish as
the area's civil clock, and every other stretch is refused as D1 refuses LMT.
The notes read are the IANA release the pinned tzdata package is built from
(ruling 71). Ruling 61: (a) Venice before 1880 and Turin and Bologna in
December 1866 refused by coordinates from the notes' own dates; (b) St John's
mean time (the database's NST before 1935) classed by ruling 35's test; (d)
where a zone's record holds the uninhabited "-00", the refusal says the record
holds no time there. Ruling 68: the linked-zone guard passes a group whose
every member is listed.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from timezonefinder import TimezoneFinder

from test_d1r_mean_time_reach_2026_10_06 import _app, _box, _calculation_rows, _refused_on_the_page, _verdict
from test_linked_zones_2026_10_05 import _one_record_one_zone

NO_SUCH_SENTENCES = ("kept any standard time", "reference city")


def _anniversary(engine, birth, years, zone, lat=None, lon=None):
    kwargs = {"time_standard": "named", "zone_name": zone}
    if lat is not None:
        kwargs.update(latitude=lat, longitude=lon)
    return engine["anniversary_moment"](engine["CivilMoment"](*birth), years, **kwargs)


# --- Ruling 61 (a), with ruling 66's "Rome by city adoption dates" ------------------------------------
# europe:1734-1736: "Milano set the public watches on the Rome time on the same day (12th December
# 1866), Torino and Bologna on the 1st January 1867, Venezia the 1st May 1880".

VENICE = (45.4372, 12.3346)
CITY_DATES = {"Turin": ((45.0703, 7.6869), (1867, 1, 1)), "Bologna": ((44.4949, 11.3426), (1867, 1, 1)),
              "Venice": (VENICE, (1880, 5, 1))}


def test_venice_before_may_1880_is_refused_by_coordinates(engine):
    lat, lon = VENICE
    for local in ((1866, 12, 12, 0, 0, 0), (1875, 6, 1, 12, 0, 0), (1880, 4, 30, 23, 59, 59)):
        assert _verdict(engine, "Europe/Rome", local, lat, lon) == ("refused", "mean_time_city"), local
    assert _verdict(engine, "Europe/Rome", (1880, 5, 1, 0, 0, 0), lat, lon) == ("cast", "RMT", True)


# The cities' areas against places on either side of their borders (coordinates from OpenStreetMap's
# gazetteer): inside, refused the day before the city's date and cast on it; outside, cast at Rome's mean
# time from its first day, as before.
CITY_PLACES = {
    "Venice": {"Piazza San Marco": (45.4343, 12.3387), "Giudecca": (45.4261, 12.3183), "Tronchetto": (45.4409, 12.3050),
               "Murano": (45.4585, 12.3530), "Lido": (45.4165, 12.3706), "Malamocco": (45.3720, 12.3384)},
    "Turin": {"Turin": (45.0703, 7.6869), "Superga": (45.0805, 7.7671), "Mirafiori Sud": (45.0178, 7.6328)},
    "Bologna": {"Bologna": (44.4949, 11.3426), "Borgo Panigale": (44.5195, 11.2762), "San Luca": (44.4791, 11.2982),
                "Corticella": (44.5462, 11.3565)},
}
AROUND_THE_CITIES = {
    "Mestre": (45.4943, 12.2418), "Marghera": (45.4758, 12.2248), "Fusina": (45.4191, 12.2578),
    "Campalto": (45.4864, 12.2950), "Tessera": (45.5029, 12.3276), "Burano": (45.4854, 12.4175),
    "Pellestrina": (45.2723, 12.3008), "Punta Sabbioni": (45.4477, 12.4276), "Chioggia": (45.2179, 12.2271),
    "Moncalieri": (45.0005, 7.6848), "Collegno": (45.0775, 7.5724), "Grugliasco": (45.0680, 7.5776),
    "Nichelino": (44.9955, 7.6466), "Venaria Reale": (45.1348, 7.6269), "Settimo Torinese": (45.1372, 7.7713),
    "San Mauro Torinese": (45.1044, 7.7620), "Pino Torinese": (45.0395, 7.7771), "Pecetto Torinese": (45.0169, 7.7499),
    "Beinasco": (45.0221, 7.5794), "Borgaro Torinese": (45.1521, 7.6580),
    "Casalecchio di Reno": (44.4760, 11.2757), "San Lazzaro di Savena": (44.4716, 11.4049),
    "Castel Maggiore": (44.5757, 11.3648), "Granarolo dell'Emilia": (44.5532, 11.4432),
    "Calderara di Reno": (44.5631, 11.2717), "Zola Predosa": (44.4897, 11.2183), "Pianoro": (44.3856, 11.3435),
    "Sasso Marconi": (44.3996, 11.2476), "Castenaso": (44.5089, 11.4698),
}


def test_the_places_either_side_of_the_cities_borders_are_in_romes_zone():
    finder = TimezoneFinder()
    places = {**{p: c for city in CITY_PLACES.values() for p, c in city.items()}, **AROUND_THE_CITIES}
    assert {p: finder.timezone_at(lat=a, lng=b) for p, (a, b) in places.items()} == {p: "Europe/Rome" for p in places}


@pytest.mark.parametrize("city", sorted(CITY_PLACES))
def test_the_places_inside_each_city_are_refused_until_its_date(engine, city):
    _place, since = CITY_DATES[city]
    before = (date(*since) - timedelta(days=1)).timetuple()[:3]
    places = sorted(CITY_PLACES[city].items())
    assert places
    for place, (lat, lon) in places:
        assert _verdict(engine, "Europe/Rome", (*before, 12, 0, 0), lat, lon) == ("refused", "mean_time_city"), place
        assert _verdict(engine, "Europe/Rome", (*since, 12, 0, 0), lat, lon) == ("cast", "RMT", True), place


@pytest.mark.parametrize("city", ("Turin", "Bologna"))
def test_turin_and_bologna_in_december_1866_are_refused_by_coordinates(engine, city):
    (lat, lon), _since = CITY_DATES[city]
    for local in ((1866, 12, 12, 0, 0, 0), (1866, 12, 20, 12, 0, 0), (1866, 12, 31, 23, 59, 59)):
        assert _verdict(engine, "Europe/Rome", local, lat, lon) == ("refused", "mean_time_city"), local
    assert _verdict(engine, "Europe/Rome", (1867, 1, 1, 0, 0, 0), lat, lon) == ("cast", "RMT", True)


def test_venice_before_1880_is_refused_on_the_page_naming_its_date():
    at = _app("1875-06-01", (12, 0), *VENICE)
    sentence = _refused_on_the_page(at, "1875-06-01", ("Europe/Rome", "RMT", "Venice", "1880-05-01"))
    assert "kept its own time" not in sentence, sentence


def test_an_anniversary_in_venice_before_1880_is_unavailable(engine):
    past = _anniversary(engine, (1880, 6, 1, 12, 0, 0), -1, "Europe/Rome", *VENICE)
    assert isinstance(past, engine["UnresolvedResult"]) and past.status == "unavailable", past
    assert "Venice" in past.reason and "1880-05-01" in past.reason, past.reason
    renewed = _anniversary(engine, (1880, 6, 1, 12, 0, 0), 1, "Europe/Rome", *VENICE)
    assert renewed["civil_mean_time"] is True, renewed


# --- Ruling 66: Zurich's postal and telegraph 1853 ----------------------------------------------------
# europe:3797-3814: the 1853-07-16 transition models "postal and telegraph time" and "legal civil time
# probably changed at still some other transition date"; no note dates it.

SWISS = {"Bern": (46.9485, 7.4522), "Zurich": (47.3744, 8.5410), "Lausanne": (46.5218, 6.6327)}


@pytest.mark.parametrize("place", sorted(SWISS))
def test_bern_mean_time_is_refused_throughout(engine, place):
    lat, lon = SWISS[place]
    for local in ((1853, 7, 16, 0, 0, 0), (1880, 6, 1, 12, 0, 0), (1894, 5, 31, 23, 59, 59)):
        assert _verdict(engine, "Europe/Zurich", local, lat, lon) == ("refused", "mean_time"), local
        assert _verdict(engine, "Europe/Zurich", local) == ("refused", "mean_time"), local


def test_bern_1880_is_refused_on_the_page():
    at = _app("1880-06-01", (12, 0), *SWISS["Bern"])
    sentence = _refused_on_the_page(at, "1880-06-01", ("Europe/Zurich", "BMT", "no standard-time zone"))
    assert "kept its own time" not in sentence, sentence


# --- Ruling 66: Algiers's whole-zone reach ----------------------------------------------------------------
# africa:91 "See Europe/Paris for PMT-related transitions"; europe:1409-1410 "There are similar
# problems in Algiers, Monaco and Tunis": no note says the zone's area kept Paris mean time.

ALGIERS = (36.7538, 3.0588)


def test_paris_mean_time_in_algiers_is_refused(engine):
    for local in ((1891, 3, 16, 0, 0, 0), (1900, 6, 1, 12, 0, 0), (1911, 3, 10, 12, 0, 0)):
        assert _verdict(engine, "Africa/Algiers", local, *ALGIERS) == ("refused", "mean_time"), local
    at = _app("1900-06-01", (12, 0), *ALGIERS)
    _refused_on_the_page(at, "1900-06-01", ("Africa/Algiers", "PMT", "no standard-time zone"))


# --- Ruling 66: Monrovia's 1919 ---------------------------------------------------------------------------
# africa:428 "The Nautical Almanac for the Year 1970, p 264, is the source for -0:44:30."; africa:430-431
# "In 1972 Liberia was the last country to switch from a UT offset that was not a multiple of 15 or 20
# minutes." Nothing dates the -0:44:30 before the Almanac's year.

MONROVIA = (6.3, -10.8)


def test_monrovia_before_the_almanac_of_1970_is_refused(engine):
    for local in ((1919, 3, 1, 0, 0, 0), (1950, 6, 1, 12, 0, 0), (1969, 12, 31, 12, 0, 0)):
        assert _verdict(engine, "Africa/Monrovia", local, *MONROVIA) == ("refused", "mean_time"), local
    assert _verdict(engine, "Africa/Monrovia", (1970, 1, 1, 0, 0, 0), *MONROVIA) == ("cast", "MMT", True)
    assert _verdict(engine, "Africa/Monrovia", (1972, 1, 6, 12, 0, 0), *MONROVIA) == ("cast", "MMT", True)


# --- Ruling 66: the early periods of Riga, Tbilisi and Jamaica ---------------------------------------
# northamerica:3784-3786 Milne records Kingston mean time "from an unspecified official document, and says
# 'This time is used throughout the island'" (Milne, Geogr J. 1899 Feb: northamerica:1259): cast from the
# first day after the month of its source. (Riga and Tbilisi: ruling 81 (c), below.)

KINGSTON = (17.9714, -76.7920)


def test_the_early_period_of_jamaica_is_refused(engine):
    for local in ((1890, 6, 1, 12, 0, 0), (1899, 2, 28, 23, 59, 59)):
        assert _verdict(engine, "America/Jamaica", local, *KINGSTON) == ("refused", "mean_time"), local
    assert _verdict(engine, "America/Jamaica", (1899, 3, 1, 0, 0, 0), *KINGSTON) == ("cast", "KMT", True)


def test_riga_summer_1918_is_refused_naming_the_mean_time_it_was_kept_on():
    at = _app("1918-06-01", (12, 0), 56.9496, 24.1052)
    sentence = _refused_on_the_page(at, "1918-06-01", ("Europe/Riga", "holds LST, summer time kept on RMT, a mean time"))
    assert "holds LST, a mean time" not in sentence, sentence


def test_kingston_before_1899_is_refused_and_after_it_is_cast_on_the_page():
    _refused_on_the_page(_app("1895-06-01", (12, 0), 17.9714, -76.7920), "1895-06-01",
                         ("America/Jamaica", "KMT", "no standard-time zone"))
    at = _app("1905-06-01", (12, 0), 17.9714, -76.7920)
    assert not at.sidebar.error, _box(at)
    assert "KMT, a named mean time, was then the civil clock across this area;" in _box(at), _box(at)


# --- Ruling 66: Easter weighed by the same threshold --------------------------------------------------
# southamerica:1099-1102: Shanks & Pottenger "also says Pacific/Easter standardized on 109W22 in 1890" --
# the island's standard time on its own meridian, on a single secondary source, as Argentina's is
# (southamerica:207-213); the year only, so cast from the first day after it.

HANGA_ROA = (-27.1500, -109.4333)


def test_easter_mean_time_is_cast_from_the_year_after_its_standardization(engine):
    for local in ((1890, 1, 1, 0, 0, 0), (1890, 12, 31, 23, 59, 59)):
        assert _verdict(engine, "Pacific/Easter", local, *HANGA_ROA) == ("refused", "mean_time"), local
    for local in ((1891, 1, 1, 0, 0, 0), (1910, 6, 1, 12, 0, 0), (1932, 8, 31, 12, 0, 0)):
        assert _verdict(engine, "Pacific/Easter", local, *HANGA_ROA) == ("cast", "EMT", True), local
    at = _app("1910-06-01", (12, 0), *HANGA_ROA)
    assert not at.sidebar.error, _box(at)
    assert "EMT, a named mean time, was then the civil clock across this area;" in _box(at), _box(at)


# --- Ruling 61 (b): St John's mean time under the name NST --------------------------------------------
# northamerica:1464-1467 (St_Johns) and 1477-1480 (Goose_Bay) hold -3:30:52, St John's mean time, as NST
# to 1935-03-30; the Newfoundland notes (northamerica:1404-1436) date only summer-time rules and say
# nothing of who kept it before 1935.

NEWFOUNDLAND = {"America/St_Johns": (47.5615, -52.7126), "America/Goose_Bay": (53.3017, -60.3261)}


@pytest.mark.parametrize("zone", sorted(NEWFOUNDLAND))
def test_st_johns_mean_time_under_nst_is_refused(engine, zone):
    place = NEWFOUNDLAND[zone]
    summer = (1920, 7, 1, 12, 0, 0) if zone == "America/St_Johns" else (1918, 7, 1, 12, 0, 0)
    for local in ((1884, 6, 1, 12, 0, 0), (1900, 6, 1, 12, 0, 0), summer, (1935, 3, 29, 12, 0, 0)):
        assert _verdict(engine, zone, local, *place) == ("refused", "mean_time"), local
    assert _verdict(engine, zone, (1935, 4, 1, 12, 0, 0), *place) == ("cast", "NST", False)


def test_st_johns_1900_is_refused_on_the_page():
    at = _app("1900-06-01", (12, 0), *NEWFOUNDLAND["America/St_Johns"])
    sentence = _refused_on_the_page(at, "1900-06-01", ("America/St_Johns", "holds NST, a mean time taken from one "
                                                       "place's meridian"))
    assert "a link to" not in sentence, sentence


# --- Ruling 61 (d) with D1R's check R5: the record holds "-00" -----------------------------------------
# theory.html:584-588 and antarctica:13: "-00" is the database's abbreviation "for locations while
# uninhabited", with an offset that is "in some sense undefined".

UNINHABITED = (
    ("1930-06-01", 63.7467, -68.5170, "America/Iqaluit"),      # at the record's start
    ("1930-06-01", -2.8106, -171.6747, "Pacific/Kanton"),      # at the record's start
    ("2000-06-01", -72.0114, 2.5350, "Antarctica/Troll"),      # at the record's start
    ("1965-06-01", -68.5765, 77.9674, "Antarctica/Davis"),     # a return, 1964-1969
    ("1930-06-01", -54.6208, 158.8556, "Antarctica/Macquarie"),  # a return, 1919-1948
    ("1994-06-01", -78.4644, 106.8340, "Antarctica/Vostok"),   # a return, 1994
)


@pytest.mark.parametrize("day, lat, lon, zone", UNINHABITED, ids=[u[3].split("/")[1] for u in UNINHABITED])
def test_a_record_holding_no_time_says_so_on_the_page(day, lat, lon, zone):
    at = _app(day, (12, 0), lat, lon)
    sentence = _refused_on_the_page(at, day, (zone, "holds no time", "uninhabited"))
    for wrong in NO_SUCH_SENTENCES:
        assert wrong not in sentence, sentence


@pytest.mark.parametrize("birth, zone", (
    ((1966, 6, 1, 12, 0, 0), "Antarctica/Davis"),
    ((1931, 6, 1, 12, 0, 0), "Antarctica/Macquarie"),
    ((2001, 6, 1, 12, 0, 0), "Antarctica/Troll"),
), ids=("Davis-1965", "Macquarie-1930", "Troll-2000"))
def test_an_anniversary_where_the_record_holds_no_time_says_so(engine, birth, zone):
    past = _anniversary(engine, birth, -1, zone)
    assert isinstance(past, engine["UnresolvedResult"]) and past.status == "unavailable", past
    assert "holds no time" in past.reason and "uninhabited" in past.reason, past.reason
    for wrong in NO_SUCH_SENTENCES:
        assert wrong not in past.reason, past.reason


# --- Ruling 68: the linked-zone guard -----------------------------------------------------------------

def test_a_group_whose_every_member_is_listed_passes_the_guard(engine):
    linked = engine["LINKED_ZONES"]
    assert _one_record_one_zone(["Africa/Bamako", "Africa/Dakar"], linked) is True
    # What the guard protects is unchanged: two names off the list, or the one off-list name not the
    # listed names' target, still fail it; the database's own shape still passes.
    assert _one_record_one_zone(["Europe/Berlin", "Europe/Stockholm"], {}) is False
    assert _one_record_one_zone(["Europe/Oslo", "Europe/Stockholm"], {"Europe/Oslo": "Europe/Berlin"}) is False
    assert _one_record_one_zone(["Europe/Berlin", "Europe/Oslo", "Europe/Stockholm"], linked) is True


# === Ruling 81 (the owner on this lane's open points) ======================================================

# --- (b) Rome by city adoption dates, option (ii) ---------------------------------------------------------
# europe:1729-1737: Rome's time reached the public clocks city by city, "the last city was Cagliari in
# 1886". Outside Milan, Turin, Bologna and Venice the mainland is cast only from 1887-01-01, the first day
# after that year; Milan from 1866-12-12, "on the same day", by coordinates.

MAINLAND = {"Florence": (43.7698, 11.2556), "Naples": (40.8359, 14.2488), "Rome": (41.8933, 12.4829),
            "Genoa": (44.4073, 8.9339), "Viterbo": (42.4930, 11.9488), "Reggio Calabria": (38.1035, 15.6398),
            "Verona": (45.4425, 10.9857)}
MILAN = {"Duomo": (45.4642, 9.1916), "Baggio": (45.4614, 9.0898), "Lambrate": (45.4824, 9.2411),
         "Niguarda": (45.5155, 9.1942)}
AROUND_MILAN = {"Sesto San Giovanni": (45.5348, 9.2372), "Monza": (45.5845, 9.2749), "Corsico": (45.4316, 9.1097),
                "Cinisello Balsamo": (45.5576, 9.2217), "San Donato Milanese": (45.4181, 9.2716), "Rho": (45.5310, 9.0463),
                "Segrate": (45.4907, 9.2948), "Assago": (45.4052, 9.1313), "Bresso": (45.5372, 9.1890),
                "Cologno Monzese": (45.5286, 9.2782)}
BEFORE_1887 = ((1866, 12, 12, 0, 0, 0), (1880, 6, 1, 12, 0, 0), (1886, 12, 31, 23, 59, 59))
FROM_1887 = ((1887, 1, 1, 0, 0, 0), (1893, 10, 31, 23, 49, 55))


@pytest.mark.parametrize("place", sorted({**MAINLAND, **AROUND_MILAN, **AROUND_THE_CITIES}))
def test_the_mainland_outside_the_four_cities_takes_rome_mean_time_only_from_1887(engine, place):
    lat, lon = {**MAINLAND, **AROUND_MILAN, **AROUND_THE_CITIES}[place]
    for local in BEFORE_1887:
        assert _verdict(engine, "Europe/Rome", local, lat, lon) == ("refused", "mean_time"), local
    for local in FROM_1887:
        assert _verdict(engine, "Europe/Rome", local, lat, lon) == ("cast", "RMT", True), local


def test_without_coordinates_rome_mean_time_is_cast_only_from_1887(engine):
    for local in BEFORE_1887:
        assert _verdict(engine, "Europe/Rome", local) == ("refused", "mean_time"), local
    for local in FROM_1887:
        assert _verdict(engine, "Europe/Rome", local) == ("cast", "RMT", True), local


def test_milan_is_cast_from_1866_12_12_by_coordinates(engine):
    places = sorted(MILAN.items())
    assert places
    for place, (lat, lon) in places:
        for local in ((1866, 12, 12, 0, 0, 0), (1870, 6, 1, 12, 0, 0), (1893, 10, 31, 23, 49, 55)):
            assert _verdict(engine, "Europe/Rome", local, lat, lon) == ("cast", "RMT", True), (place, local)
        assert _verdict(engine, "Europe/Rome", (1866, 12, 11, 23, 59, 59), lat, lon) == ("refused", "before_rules")
    # Outside Milan's area, its neighbour Sesto San Giovanni waits for 1887.
    assert _verdict(engine, "Europe/Rome", (1870, 6, 1, 12, 0, 0), *AROUND_MILAN["Sesto San Giovanni"]) == \
        ("refused", "mean_time")


def test_florence_1880_is_refused_and_1890_cast_saying_the_date_is_this_apps_choice():
    sentence = _refused_on_the_page(_app("1880-06-01", (12, 0), *MAINLAND["Florence"]), "1880-06-01",
                                    ("Europe/Rome", "holds RMT, a mean time taken from one place's meridian",
                                     "do not show it to have been this birthplace's clock then"))
    assert "kept its own time" not in sentence and "public clocks" not in sentence, sentence
    at = _app("1890-06-01", (12, 0), *MAINLAND["Florence"])
    assert not at.sidebar.error, _box(at)
    assert ("RMT, a named mean time, was then the civil clock across this area; the date it is cast from here, "
            "1887-01-01, is this app's choice") in _box(at), _box(at)


def test_the_venice_outline_takes_or_leaves_whole_islands(engine):
    """Murano and the Vignole are Venice's; Sant'Erasmo and the Lazzaretto Nuovo are not: in 1882 the first
    are cast at RMT (Venice's date, 1880-05-01), the second refused (the mainland's, 1887-01-01)."""
    venice = {"Murano, north shore": (45.4628, 12.3560), "Murano": (45.4585, 12.3530), "Vignole": (45.4410, 12.3790)}
    not_venice = {"Sant'Erasmo": (45.4590, 12.4155), "Sant'Erasmo, west": (45.4470, 12.4050),
                  "Sant'Erasmo, north": (45.4700, 12.4200), "Lazzaretto Nuovo": (45.4566, 12.3865)}
    venice, not_venice = sorted(venice.items()), sorted(not_venice.items())
    assert venice and not_venice
    for place, (lat, lon) in venice:
        assert _verdict(engine, "Europe/Rome", (1882, 6, 1, 12, 0, 0), lat, lon) == ("cast", "RMT", True), place
    for place, (lat, lon) in not_venice:
        assert _verdict(engine, "Europe/Rome", (1882, 6, 1, 12, 0, 0), lat, lon) == ("refused", "mean_time"), place


# --- (c) Riga and Tbilisi, refused throughout ---------------------------------------------------------------

@pytest.mark.parametrize("zone, place, last", (
    ("Europe/Riga", (56.9496, 24.1052), (1926, 5, 10, 12, 0, 0)),
    ("Asia/Tbilisi", (41.7151, 44.8271), (1924, 5, 1, 12, 0, 0)),
), ids=("Riga", "Tbilisi"))
def test_riga_and_tbilisi_are_refused_throughout(engine, zone, place, last):
    for local in ((1880, 6, 1, 12, 0, 0), (1920, 1, 1, 0, 0, 0), (1922, 6, 1, 12, 0, 0), last):
        assert _verdict(engine, zone, local, *place) == ("refused", "mean_time"), local
        assert _verdict(engine, zone, local) == ("refused", "mean_time"), local


# --- Ruling 66's row 101: a start date of this app's choosing says so -----------------------------------

@pytest.mark.parametrize("day, place, label", (
    ("1905-06-01", (17.9714, -76.7920),
     "KMT, a named mean time, was then the civil clock across this area; the date it is cast from here, 1899-03-01, "
     "is this app's choice: the first day after February 1899, the month the database gives for its source"),
    ("1910-06-01", HANGA_ROA,
     "EMT, a named mean time, was then the civil clock across this area; the date it is cast from here, 1891-01-01, "
     "is this app's choice: the first day after 1890, the only date the database's source gives"),
    ("1890-06-01", (43.7698, 11.2556),
     "RMT, a named mean time, was then the civil clock across this area; the date it is cast from here, 1887-01-01, "
     "is this app's choice: the first day after 1886, the year the database's notes give for the last city's "
     "public clocks"),
), ids=("Kingston", "HangaRoa", "Florence"))
def test_a_start_date_of_this_apps_choosing_says_so(engine, day, place, label):
    at = _app(day, (12, 0), *place)
    assert not at.sidebar.error, _box(at)
    assert f"{label}." in _box(at), _box(at)
    assert _calculation_rows(at)["Civil clock then"] == label


def test_a_start_the_notes_date_to_the_day_says_nothing_of_a_choice(engine):
    for zone, local, lat, lon in (("Europe/Paris", (1900, 6, 1, 12, 0, 0), 45.7640, 4.8357),
                                  ("Europe/Rome", (1880, 6, 1, 12, 0, 0), *MILAN["Duomo"]),
                                  ("Atlantic/Bermuda", (1920, 1, 1, 12, 0, 0), 32.2949, -64.7814)):
        state = engine["named_zone_state"](zone, *local, latitude=lat, longitude=lon)
        assert state["label"].endswith("was then the civil clock across this area"), state
    assert "this app's choice" in engine["named_zone_state"]("America/Jamaica", 1905, 6, 1, 12, 0, 0)["label"]


# --- (e) Alsace-Moselle and the Austrian provinces, by today's borders --------------------------------

ALSACE_MOSELLE = {"Strasbourg": (48.5846, 7.7507), "Metz": (49.1197, 6.1764), "Colmar": (48.0778, 7.3580),
                  "Mulhouse": (47.7467, 7.3390), "Thionville": (49.3579, 6.1676), "Sarreguemines": (49.1095, 7.0709),
                  "Saverne": (48.7420, 7.3626), "Haguenau": (48.8387, 7.8318), "Thann": (47.8101, 7.1021),
                  "Sarrebourg": (48.7342, 7.0557)}
AROUND_ALSACE_MOSELLE = {"Nancy": (48.6937, 6.1834), "Belfort": (47.6380, 6.8629), "Epinal": (48.1748, 6.4504),
                         "Saint-Die-des-Vosges": (48.2872, 6.9474), "Luneville": (48.5916, 6.4920),
                         "Pont-a-Mousson": (48.9026, 6.0548), "Longwy": (49.5146, 5.7679), "Briey": (49.2481, 5.9371),
                         "Gerardmer": (48.0706, 6.8777), "Montbeliard": (47.5102, 6.7978), "Baccarat": (48.4487, 6.7381)}
AUSTRIAN = {"Trento": (46.0674, 11.1214), "Rovereto": (45.8865, 11.0452), "Riva del Garda": (45.8867, 10.8458),
            "Bolzano": (46.4981, 11.3548), "Merano": (46.6714, 11.1646), "Bressanone": (46.7164, 11.6578),
            "Trieste": (45.6496, 13.7773), "Muggia": (45.5986, 13.7710), "Gorizia": (45.9441, 13.6252),
            "Monfalcone": (45.8049, 13.5331), "Grado": (45.6781, 13.3979), "Duino": (45.7734, 13.6045)}
AROUND_AUSTRIAN = {"Verona": (45.4425, 10.9857), "Cortina d'Ampezzo": (46.5685, 12.1323), "Belluno": (46.1392, 12.2160),
                   "Udine": (46.0635, 13.2358), "Aquileia": (45.7696, 13.3698), "Cervignano del Friuli": (45.8301, 13.3324),
                   "Brescia": (45.5398, 10.2201), "Sondrio": (46.1709, 9.8699), "Bormio": (46.4677, 10.3775),
                   "Vicenza": (45.5473, 11.5466), "Feltre": (46.0464, 11.9324), "Limone sul Garda": (45.8141, 10.7915),
                   "Livigno": (46.5382, 10.1360)}


def test_the_places_either_side_of_the_new_borders_are_in_the_zones_named():
    finder = TimezoneFinder()
    for places, zone in ((ALSACE_MOSELLE, "Europe/Paris"), (AROUND_ALSACE_MOSELLE, "Europe/Paris"),
                         (AUSTRIAN, "Europe/Rome"), (AROUND_AUSTRIAN, "Europe/Rome"), (MAINLAND, "Europe/Rome"),
                         (MILAN, "Europe/Rome"), (AROUND_MILAN, "Europe/Rome")):
        assert {p: finder.timezone_at(lat=a, lng=b) for p, (a, b) in places.items()} == {p: zone for p in places}


@pytest.mark.parametrize("place", sorted(ALSACE_MOSELLE))
def test_alsace_moselle_is_refused_under_paris_mean_time(engine, place):
    lat, lon = ALSACE_MOSELLE[place]
    for local in ((1891, 3, 16, 0, 0, 0), (1900, 6, 1, 12, 0, 0), (1911, 3, 10, 12, 0, 0)):
        assert _verdict(engine, "Europe/Paris", local, lat, lon) == ("refused", "mean_time_outside"), local
    # Rulings 97 and 102: WET is refused here too, to 1921-01-01.
    assert _verdict(engine, "Europe/Paris", (1912, 6, 1, 12, 0, 0), lat, lon) == ("refused", "outside_clock")


@pytest.mark.parametrize("place", sorted(AROUND_ALSACE_MOSELLE))
def test_the_places_around_alsace_moselle_are_cast_at_paris_mean_time(engine, place):
    lat, lon = AROUND_ALSACE_MOSELLE[place]
    for local in ((1891, 3, 16, 0, 0, 0), (1900, 6, 1, 12, 0, 0), (1911, 3, 10, 12, 0, 0)):
        assert _verdict(engine, "Europe/Paris", local, lat, lon) == ("cast", "PMT", True), local


@pytest.mark.parametrize("place", sorted(AUSTRIAN))
def test_the_austrian_provinces_are_refused_under_rome_mean_time(engine, place):
    lat, lon = AUSTRIAN[place]
    for local in ((1866, 12, 12, 0, 0, 0), (1880, 6, 1, 12, 0, 0), (1890, 6, 1, 12, 0, 0), (1893, 10, 31, 23, 49, 55)):
        assert _verdict(engine, "Europe/Rome", local, lat, lon) == ("refused", "mean_time_outside"), local
    # Ruling 102: CET is refused here too, to 1921-01-01.
    assert _verdict(engine, "Europe/Rome", (1894, 6, 1, 12, 0, 0), lat, lon) == ("refused", "outside_clock")


@pytest.mark.parametrize("place", sorted(AROUND_AUSTRIAN))
def test_the_places_around_the_austrian_provinces_take_the_mainlands_dates(engine, place):
    lat, lon = AROUND_AUSTRIAN[place]
    assert _verdict(engine, "Europe/Rome", (1880, 6, 1, 12, 0, 0), lat, lon) == ("refused", "mean_time")
    assert _verdict(engine, "Europe/Rome", (1890, 6, 1, 12, 0, 0), lat, lon) == ("cast", "RMT", True)


@pytest.mark.parametrize("day, place, zone, abbr, area, country", (
    ("1900-06-01", ALSACE_MOSELLE["Strasbourg"], "Europe/Paris", "PMT", "Alsace-Moselle", "France"),
    ("1890-06-01", AUSTRIAN["Trieste"], "Europe/Rome", "RMT", "Trieste and Gorizia", "Italy"),
    ("1890-06-01", AUSTRIAN["Bolzano"], "Europe/Rome", "RMT", "Trentino and South Tyrol", "Italy"),
), ids=("Strasbourg", "Trieste", "Bolzano"))
def test_the_places_outside_the_country_are_refused_on_the_page(day, place, zone, abbr, area, country):
    sentence = _refused_on_the_page(_app(day, (12, 0), *place), day, (
        zone, f"holds {abbr}, a mean time taken from one place's meridian",
        f"the time-zone database's notes speak of {country}'s clocks and say nothing of {area}"))
    assert "kept its own time" not in sentence, sentence


def test_an_anniversary_in_alsace_moselle_under_paris_mean_time_is_unavailable(engine):
    past = _anniversary(engine, (1901, 6, 1, 12, 0, 0), -1, "Europe/Paris", *ALSACE_MOSELLE["Strasbourg"])
    assert isinstance(past, engine["UnresolvedResult"]) and past.status == "unavailable", past
    assert "Alsace-Moselle" in past.reason and "France" in past.reason, past.reason
