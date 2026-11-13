"""The Fixed stars page's finder, its record, its compact lists and what they read.

Each altitude here is also computed in the test itself, by spherical trigonometry from the
chart's ARMC, obliquity and latitude; each clock reading is compared with zoneinfo's where
zoneinfo can speak. Janus is the outside witness for the places: its reading of the invented chart
stands in tests/fixtures/janus_fixed_stars_1977.tsv, and the stars this engine may not agree with to
two seconds of arc are each named below with the bound measured.
"""
from __future__ import annotations

import ast
import dataclasses
import html
import json
import math
import re
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from conftest import APP_PATH, assert_no_exception, engine_source, make_app, sync_engine_to_environment
from test_fixed_stars_page import axis_lists, choose_population, opener_rows, sahl_rows, tab_named, walk

JANUS = Path(__file__).parent / "fixtures" / "janus_fixed_stars_1977.tsv"
INVENTED = (datetime(1977, 12, 16, 15, 8), 45.74525, -87.06458)
MINUS = "−"
SIGNS = ("Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn",
         "Aquarius", "Pisces")


def fixed_stars_app(**kwargs):
    return make_app(page="fixed-stars", **kwargs)


def invented_app():
    """The invented chart, entered as a typed offset of 0 at its UT."""
    at = fixed_stars_app(date="1977-12-16")
    at.session_state["time_input_key"] = INVENTED[0].time()
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = INVENTED[1:]
    return at


def invented_chart(engine):
    return engine["calculate_traditional_chart"](*INVENTED)


def chart_at(engine, year, lat, lon=10.0, month=6):
    """A chart in `year`, its moment on no particular date of any person."""
    jd = engine["civil_local_to_jd_ut"](year, month, 15, 12.0, 0.0)
    return engine["calculate_traditional_chart_jd"](jd, lat, lon)


def placed(engine, jd=2451545.0):
    stars, missing = engine["fixed_star_places"](jd)
    assert missing == {} and stars
    return stars


def star_named(engine, stars, name):
    return next(s for s in stars if s.catalogue_name == name or s.name == name)


def dialog_of(at):
    """The record's block, if a dialog stands in the run; a dialog is not under at.main."""
    found = [node for node in walk(at._tree) if getattr(node, "type", None) == "dialog"]
    assert len(found) <= 1
    return found[0] if found else None


def drawn_text(node):
    """What the st.html under a node prints, tags gone."""
    bodies = [n.proto.body for n in walk(node) if getattr(n, "type", None) == "html"]
    return html.unescape(re.sub(r"<[^>]+>", "\n", "\n".join(bodies)))


def facts_of(at):
    """The record's labelled facts, as {label: [value, lines...]}."""
    bodies = [n.proto.body for n in walk(dialog_of(at)) if getattr(n, "type", None) == "html"]
    facts = {}
    for label, value in re.findall(r"<dt>([^<]*)</dt><dd>(.*?)</dd>", "".join(bodies)):
        facts[html.unescape(label)] = [html.unescape(t) for t in re.findall(r"[^<>]+(?=<|$)", value)]
    return facts


def find_star(at, query):
    """A query committed as a reader commits it: the Find button, and Enter is the same submit."""
    next(t for t in at.main.text_input if t.label == "Find a star").set_value(query)
    next(b for b in at.main.button if b.label == "Find").click().run(timeout=120)
    assert_no_exception(at, query)
    return at


def _title(node):
    return node.proto.dialog.title


# --- The Greek form ----------------------------------------------------------------------------

def test_all_twenty_four_letters_and_the_superscripts(engine):
    form = engine["fixed_star_greek_form"]
    letters = {"al": "α", "be": "β", "ga": "γ", "de": "δ", "ep": "ε", "ze": "ζ", "et": "η", "th": "θ", "io": "ι", "ka": "κ",
               "la": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "omi": "ο", "pi": "π", "rh": "ρ", "si": "σ", "ta": "τ", "up": "υ",
               "ph": "φ", "ch": "χ", "ps": "ψ", "ome": "ω"}
    assert len(letters) == 24
    for key, letter in letters.items():
        assert form(f"{key}And") == f"{letter} And"
        assert form(f"{key}-1And") == f"{letter}¹ And"
    for digit, mark in zip("123456789", "¹²³⁴⁵⁶⁷⁸⁹"):
        assert form(f"ps-{digit}Aur") == f"ψ{mark} Aur"
    assert len(engine["FIXED_STAR_CONSTELLATIONS"]) == 88
    for abbreviation in engine["FIXED_STAR_CONSTELLATIONS"]:
        assert form(f"al{abbreviation}") == f"α {abbreviation}"


def test_the_examples_print_as_written(engine):
    stars = placed(engine)
    for name, label, forms in (
            ("Alpheratz", "Alpheratz · α And", ("Alpheratz", "Sirrah", "alAnd", "α And", "alpha And", "alpha Andromedae")),
            ("Acamar", "Acamar · θ¹ Eri", ("Acamar", "th-1Eri", "θ¹ Eri", "theta 1 Eridani")),
            ("Rigel", "Rigel · β Ori", ("Rigel", "beOri", "β Ori", "beta Orionis")),
            ("pi-1Peg", "π¹ Peg", ("pi-1Peg", "π¹ Peg"))):
        star = star_named(engine, stars, name)
        assert engine["fixed_star_label"](star) == label
        for written in forms:
            assert engine["fixed_star_find"](written) == (engine["fixed_star_identity"](star),), written


def test_every_key_is_greek_or_its_label_with_no_false_parse(engine):
    stars = placed(engine)
    assert len(stars) == 1852
    letters = engine["FIXED_STAR_GREEK_LETTERS"]
    greek = [s for s in stars if engine["fixed_star_greek_form"](s.designation)]
    assert len(greek) == 987
    labels = [s.designation for s in stars if not engine["fixed_star_greek_form"](s.designation)]
    assert len(labels) == 865                         # 118 of the shipped file and the 747 added
    superscript = dict(zip("¹²³⁴⁵⁶⁷⁸⁹", "123456789"))
    by_letter = {symbol: key for key, (symbol, _word) in letters.items()}
    for star in greek:
        written = engine["fixed_star_greek_form"](star.designation)
        head, constellation = written.split(" ")
        component = superscript.get(head[1:], "")
        assert star.designation == f"{by_letter[head[0]]}{'-' + component if component else ''}{constellation}", written
    assert {re.match(r"[a-z]+", s.designation)[0] for s in greek if not s.designation.startswith("omi")} | {"omi"} == set(letters)
    for label in ("3Aqr", "M31", "SgrA*", "PSRB1257+12", "P_Pup", "zePscA", "kaC1GrB", "dCen", "GCRS00", "Apex", "VC"):
        assert label in labels, label
    for star in stars:
        assert engine["fixed_star_designation_form"](star) == (engine["fixed_star_greek_form"](star.designation) or star.designation)


def test_a_component_family_is_kept_apart(engine):
    stars = placed(engine)
    identities = {}
    for star in stars:
        parts = engine["_fixed_star_bayer"](star.designation)
        if parts:
            identities.setdefault((parts[0], parts[2]), []).append(star)
    families = {family: members for family, members in identities.items() if len(members) > 1}
    assert len(families) == 25 and sum(map(len, families.values())) == 63
    for members in families.values():
        forms = [engine["fixed_star_greek_form"](star.designation) for star in members]
        assert len(set(forms)) == len(forms), forms
        assert len({engine["fixed_star_identity"](star) for star in members}) == len(members)
        for star in members:
            answered = engine["fixed_star_find"](engine["fixed_star_greek_form"](star.designation))
            assert answered == (engine["fixed_star_identity"](star),), star.designation


def test_a_form_is_printed_once(engine):
    for star in placed(engine):
        parts = engine["fixed_star_label"](star).split(" · ")
        assert len(parts) == len(set(parts)), parts
        assert star.designation not in parts or engine["fixed_star_greek_form"](star.designation) is None
        for shown in engine["fixed_star_other_names_shown"](star):
            assert shown not in parts, (shown, parts)


# --- The identity ------------------------------------------------------------------------------

def test_the_identity_is_private_unique_and_a_plain_string(engine):
    stars = placed(engine)
    identities = [engine["fixed_star_identity"](star) for star in stars]
    assert all(isinstance(identity, str) and identity for identity in identities)
    assert len(set(identities)) == len(stars) == 1852
    kuma = [s for s in stars if s.name == "Kuma"]
    assert len(kuma) == 2 and engine["fixed_star_shown_name"](kuma[0]) == engine["fixed_star_shown_name"](kuma[1])
    assert engine["fixed_star_identity"](kuma[0]) != engine["fixed_star_identity"](kuma[1])


# --- The population ----------------------------------------------------------------------------

def test_the_two_rows_that_are_no_star_leave_and_the_others_stay(engine):
    stars = placed(engine)
    assert len(stars) == 1852
    for name in ("Test", "AA11_page_B73"):
        assert name not in {s.name for s in stars} | {s.catalogue_name for s in stars}
        assert engine["fixed_star_find"](name) == ()
    for name in ("ZerL2000", "Propus"):
        assert engine["fixed_star_find"](name), name
    assert "Propus etaGem" in star_named(engine, stars, "Propus").other_names


def test_the_two_are_in_no_list_table_or_export():
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Full Catalogue")
    table = tab_named(at, "Star list").dataframe[0].value
    assert len(table) == 1852
    assert not {"Test", "AA11_page_B73"} & set(table["Name"])
    export = json.dumps(at.session_state["_fixed_stars_export"], ensure_ascii=False)
    assert '"Name": "Test"' not in export and "AA11_page_B73" not in export
    assert "ZerL2000" in export


# --- The finder --------------------------------------------------------------------------------

def test_every_form_of_every_identity_finds_it(engine):
    """Computed at test time, over the whole catalogue."""
    stars = placed(engine)
    checked = 0
    for star in stars:
        identity = engine["fixed_star_identity"](star)
        for form in engine["fixed_star_search_forms"](star):
            found = engine["fixed_star_find"](form)
            assert identity in found, (form, identity)
            if len(found) == 1:
                assert found == (identity,), form
            checked += 1
    assert checked > 5000


def test_an_exact_form_never_opens_another_and_exact_comes_first(engine):
    stars = placed(engine)
    finder = engine["fixed_star_finder"]()
    zaniah = star_named(engine, stars, "Zaniah")
    assert engine["fixed_star_find"]("eta Vir") == (engine["fixed_star_identity"](zaniah),)
    rigel = star_named(engine, stars, "Rigel")
    assert engine["fixed_star_find"]("Rigel") == (engine["fixed_star_identity"](rigel),)
    assert "Rigel Kentaurus" in star_named(engine, stars, "Toliman").other_names
    # Every form that is exact for several gives exactly those several.
    shared = {form: found for form, found in finder["forms"].items() if len(found) > 1}
    assert shared
    for form, found in shared.items():
        assert engine["fixed_star_find"](form) == found


@pytest.mark.parametrize("written", ["th-1Eri", "th1Eri", "θ1 Eri", "θ¹ Eri", "theta 1 Eri", "theta 1 Eridani", "TH-1ERI"])
def test_the_forms_of_one_component_star_find_it_alone(engine, written):
    assert [engine["fixed_star_finder"]()["stars"][i].name for i in engine["fixed_star_find"](written)] == ["Acamar"]


def test_spaces_and_case_and_unicode_forms_are_normalized(engine):
    found = engine["fixed_star_find"]("alpha And")
    assert len(found) == 1
    for written in ("α  And", "ALPHA AND", "alpha-and", "α And", " alpha   andromedae "):
        assert engine["fixed_star_find"](written) == found, written


@pytest.mark.parametrize("empty", ["", "   ", "--", "·"])
def test_a_query_of_nothing_finds_nothing(engine, empty):
    assert engine["fixed_star_find"](empty) == ()


def test_no_fuzzy_match(engine):
    for written in ("zzqx", "Siriuss", "Rgel", "Test", "AA11_page_B73", "Copula"):
        assert engine["fixed_star_find"](written) == (), written


def test_the_index_is_built_once_for_the_catalogue(engine):
    first = engine["fixed_star_finder"]()
    assert engine["fixed_star_finder"]() is first
    assert engine["_fixed_star_finder_read"].cache_info().misses <= 1


JANUS_OTHER_NAMES = {"Algenubi": "epLeo", "Denebokab": "deAql", "Giedi a1": "al-1Cap", "Giedi a2": "al-2Cap",
                     "Hyades": "deTau", "Praesepe": "M44", "Terebellum": "omeSgr", "Vertex-S": "M31"}


@pytest.mark.parametrize("name, designation", sorted(JANUS_OTHER_NAMES.items()))
def test_janus_s_other_names_answer_and_print_among_the_others(engine, name, designation):
    found = engine["fixed_star_find"](name)
    assert len(found) == 1, name
    star = engine["fixed_star_finder"]()["stars"][found[0]]
    assert star.designation == designation
    # Praesepe and Terebellum are now the names those two read by; a form is printed once.
    assert name in (star.name, *star.other_names)
    assert name in (engine["fixed_star_shown_name"](star), *engine["fixed_star_other_names_shown"](star))


def test_the_page_opens_one_gives_a_choice_for_several_and_says_none():
    at = fixed_stars_app().run(timeout=120)
    assert dialog_of(at) is None
    # One identity: its record, at once.
    find_star(at, "Sirrah")
    assert _title(dialog_of(at)) == "Alpheratz · α And"
    assert len(at.main.selectbox) == 0 or "stars found" not in " ".join(s.label for s in at.main.selectbox)
    # The flag was popped: the next run brings nothing back, and the query stands.
    at.run(timeout=120)
    assert dialog_of(at) is None
    assert next(t for t in at.main.text_input if t.label == "Find a star").value == "Sirrah"
    # None.
    find_star(at, "zzqx")
    assert dialog_of(at) is None
    assert "No stars found." in [c.value for c in at.main.caption]
    # Several: the count is of identities, and the record waits for the choice.
    find_star(at, "Proxima Centauri")
    assert dialog_of(at) is None
    choice = next(s for s in at.main.selectbox if "stars found" in s.label)
    assert choice.label == "2 stars found"
    assert sorted(choice.options) == ["Proxima Centauri · V645 Cen", "Toliman · α Cen"]
    next(b for b in at.main.button if b.label == "Open record").click().run(timeout=120)
    assert _title(dialog_of(at)) == choice.options[0]
    find_star(at, "Proxima Centauri")
    next(s for s in at.main.selectbox if "stars found" in s.label).set_value("Toliman")
    next(b for b in at.main.button if b.label == "Open record").click().run(timeout=120)
    assert _title(dialog_of(at)) == "Toliman · α Cen"


@pytest.mark.parametrize("query, title", [("eta Vir", "Zaniah · η Vir"), ("Rigel", "Rigel · β Ori"), ("beta Orionis", "Rigel · β Ori"),
                                          ("α  And", "Alpheratz · α And"), ("θ¹ Eri", "Acamar · θ¹ Eri"), ("Hyades", "Secunda Hyadum · δ Tau")])
def test_the_page_opens_the_star_asked_for(query, title):
    at = fixed_stars_app().run(timeout=120)
    find_star(at, query)
    assert _title(dialog_of(at)) == title


def test_the_page_gives_a_choice_for_a_short_query_and_nothing_for_an_empty_one():
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "al")
    choice = next(s for s in at.main.selectbox if "stars found" in s.label)
    assert int(choice.label.split()[0]) == len(choice.options) > 100
    assert dialog_of(at) is None
    find_star(at, "")
    assert dialog_of(at) is None
    assert "No stars found." not in [c.value for c in at.main.caption]
    assert not [s for s in at.main.selectbox if "stars found" in s.label]
    for query in ("Test", "AA11_page_B73"):
        find_star(at, query)
        assert "No stars found." in [c.value for c in at.main.caption], query


@pytest.mark.parametrize("query, options", [("Deneb Kaitos", ["Diphda · β Cet", "ι Cet"]),
                                             ("Rutilicus", ["Kornephoros · β Her", "ζ Her"])])
def test_a_name_two_stars_hold_gives_the_choice_of_both(query, options):
    at = fixed_stars_app().run(timeout=120)
    find_star(at, query)
    choice = next(s for s in at.main.selectbox if "stars found" in s.label)
    assert choice.label == "2 stars found"
    assert sorted(choice.options) == sorted(options)


def test_two_stars_that_print_alike_are_told_apart_in_the_choice():
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "Kuma")
    choice = next(s for s in at.main.selectbox if "stars found" in s.label)
    assert len(choice.options) == 2 and len(set(choice.options)) == 2


def test_the_finder_stands_above_both_tabs_and_finds_outside_the_population():
    at = fixed_stars_app().run(timeout=120)
    forms = [n for n in walk(at.main) if getattr(n, "type", None) == "form"]
    assert len(forms) == 1
    assert [t.label for t in forms[0].text_input] == ["Find a star"]
    assert forms[0].text_input[0].placeholder == "Name, other name or designation"
    assert "Find a star" not in [t.label for tab in at.main.tabs for t in tab.text_input]
    # Sahl's 28 are shown; this one is not of them.
    find_star(at, "ζ Dor")
    assert _title(dialog_of(at)) == "ζ Dor"


# --- Altitude and the foot point, by a second method -------------------------------------------

def spherical_altitude(longitude, latitude, obliquity, armc, geo_lat):
    """Altitude in degrees from the chart's own ARMC, obliquity and latitude."""
    lam, bet, eps, phi = map(math.radians, (longitude, latitude, obliquity, geo_lat))
    sin_dec = math.sin(bet) * math.cos(eps) + math.cos(bet) * math.sin(eps) * math.sin(lam)
    dec = math.asin(sin_dec)
    ra = math.atan2(math.sin(lam) * math.cos(eps) - math.tan(bet) * math.sin(eps), math.cos(lam))
    hour = math.radians(armc) - ra
    return math.degrees(math.asin(math.sin(phi) * sin_dec + math.cos(phi) * math.cos(dec) * math.cos(hour)))


PLACES = [(1, 43.77), (1, -33.0), (3000, 43.77), (3000, -33.0), (2000, 0.0), (2000, 66.0), (2000, -66.0), (2000, 90.0), (2000, -90.0)]


@pytest.mark.parametrize("year, lat", PLACES)
def test_altitude_agrees_with_spherical_trigonometry(engine, year, lat):
    chart = chart_at(engine, year, lat)
    frame = engine["fixed_star_frame"](chart)
    stars = placed(engine, chart["julian_day"])
    assert len(stars) == 1852
    for star in stars[::7]:
        expected = spherical_altitude(star.longitude, star.latitude, chart["obliquity"], chart["armc"], chart["geo_lat"])
        assert abs(engine["fixed_star_altitude"](star, frame) - expected) < 1e-9, star.name
        foot = spherical_altitude(star.longitude, 0.0, chart["obliquity"], chart["armc"], chart["geo_lat"])
        assert abs(engine["fixed_star_foot_point_altitude"](star, frame) - foot) < 1e-9, star.name
        # And at the moment of a crossing, on the same model: the ARMC moved at the sidereal rate.
        later = (chart["armc"] + engine["FIXED_STAR_SIDEREAL_RATE"] * 1234.5) % 360.0
        foot = spherical_altitude(star.longitude, 0.0, chart["obliquity"], later, chart["geo_lat"])
        assert abs(engine["fixed_star_foot_point_altitude"](star, frame, 1234.5) - foot) < 1e-9, star.name


# The star's crossing is reckoned from its apparent right ascension and declination, its altitude
# from its apparent longitude and latitude through the chart's true obliquity: this is what the two
# routes differ by, measured over the catalogue at these places.
CROSSING_ALTITUDE_BOUND = 0.002


@pytest.mark.parametrize("year, lat", [p for p in PLACES if abs(p[1]) < 90.0])
def test_a_star_at_its_own_crossing_stands_at_altitude_zero(engine, year, lat):
    chart = chart_at(engine, year, lat)
    frame = engine["fixed_star_frame"](chart)
    checked = 0
    for star in placed(engine, chart["julian_day"]):
        for axis in ("Ascendant", "Descendant"):
            seconds = engine["fixed_star_crossing_seconds"](star.right_ascension, star.declination, chart["armc"], lat, axis)
            if seconds is not None:
                assert abs(engine["fixed_star_altitude"](star, frame, seconds)) < CROSSING_ALTITUDE_BOUND, (star.name, axis)
                checked += 1
    assert checked > 500


def test_the_foot_point_of_a_star_on_the_ecliptic_rises_with_it_and_one_far_from_it_does_not(engine):
    chart = chart_at(engine, 2000, 43.77)
    frame = engine["fixed_star_frame"](chart)
    stars = placed(engine, chart["julian_day"])
    regulus = star_named(engine, stars, "Regulus")
    assert abs(regulus.latitude) < 0.6
    seconds = engine["fixed_star_crossing_seconds"](regulus.right_ascension, regulus.declination, chart["armc"], 43.77, "Ascendant")
    assert abs(engine["fixed_star_foot_point_altitude"](regulus, frame, seconds)) < 0.6
    vega = star_named(engine, stars, "Vega")
    assert abs(vega.latitude) > 60
    seconds = engine["fixed_star_crossing_seconds"](vega.right_ascension, vega.declination, chart["armc"], 43.77, "Ascendant")
    assert abs(engine["fixed_star_foot_point_altitude"](vega, frame, seconds)) > 20


def test_the_foot_point_keeps_the_star_s_longitude_at_latitude_zero(engine):
    chart = chart_at(engine, 2000, 43.77)
    frame = engine["fixed_star_frame"](chart)
    vega = star_named(engine, placed(engine, chart["julian_day"]), "Vega")
    moved = dataclasses.replace(vega, latitude=-vega.latitude)
    assert engine["fixed_star_foot_point_altitude"](moved, frame) == engine["fixed_star_foot_point_altitude"](vega, frame)
    assert engine["fixed_star_altitude"](moved, frame) != engine["fixed_star_altitude"](vega, frame)


def test_the_horizon_is_read_by_no_function_this_engine_does_not_own():
    source = engine_source()
    start = source.index("# --- A star against the horizon, and its crossings on the chart's clock")
    end = source.index("def pn4_revolution_image(")
    block = source[start:end]
    assert "fixed_star_altitude" in block
    for name in ("swe.sidtime", "swe.houses", "swe.azalt", "swe.calc_ut", "ECL_NUT"):
        assert name not in block, name


def _a_star(engine, stars, frame, wanted):
    """The first star whose states at this chart are `wanted`."""
    for star in stars:
        sentence = engine["fixed_star_horizon_sentence"](star, frame)
        if wanted in sentence:
            return star, sentence
    raise AssertionError(wanted)


def test_the_horizon_sentence_tells_the_star_from_its_foot_point(engine):
    chart = chart_at(engine, 2000, 66.0)
    frame = engine["fixed_star_frame"](chart)
    stars = placed(engine, chart["julian_day"])
    for wanted in ("The star is above the horizon; its foot point is below it.",
                   "The star is below the horizon; its foot point is above it.",
                   "The star and its foot point are both above the horizon.",
                   "The star and its foot point are both below the horizon.",
                   "The star is always above the horizon", "The star is always below the horizon"):
        star, _sentence = _a_star(engine, stars, frame, wanted)
        altitude = spherical_altitude(star.longitude, star.latitude, chart["obliquity"], chart["armc"], chart["geo_lat"])
        assert (altitude > 0) == ("star is above" in wanted or "both above" in wanted or "always above" in wanted), wanted


def test_a_star_on_the_horizon_and_a_star_that_never_crosses(engine):
    chart = chart_at(engine, 2000, 43.77)
    frame = engine["fixed_star_frame"](chart)
    star = star_named(engine, placed(engine, chart["julian_day"]), "Vega")
    seconds = engine["fixed_star_crossing_seconds"](star.right_ascension, star.declination, chart["armc"], 43.77, "Ascendant")
    at_rising = {**frame, "armc": chart["armc"] + engine["FIXED_STAR_SIDEREAL_RATE"] * seconds}
    assert engine["fixed_star_horizon_sentence"](star, at_rising).startswith("The star is on the horizon;")
    polar = {**frame, "latitude": 90.0}
    assert engine["fixed_star_horizon_sentence"](star, polar).startswith(("The star is always above", "The star and its foot point are both always"))
    assert engine["fixed_star_foot_point_position"](star, polar) in ("Always above the horizon", "Always below the horizon")


def test_the_foot_point_s_position_says_where_and_which_side(engine):
    chart = chart_at(engine, 2000, 43.77)
    frame = engine["fixed_star_frame"](chart)
    seen = set()
    for star in placed(engine, chart["julian_day"]):
        position = engine["fixed_star_foot_point_position"](star, frame)
        seen.add(position)
        altitude = engine["fixed_star_foot_point_altitude"](star, frame)
        assert position.startswith("Above" if altitude > 0 else "Below"), position
    assert seen == {"Above the horizon, east", "Above the horizon, west", "Below the horizon, east", "Below the horizon, west"}


# --- Janus, the outside witness ----------------------------------------------------------------

def _janus_rows():
    rows = []
    for line in JANUS.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        name, house, longitude, latitude, right_ascension, declination, _azimuth, altitude = line.split("\t")
        def dms(*parts):
            return int(parts[0]) + int(parts[1]) / 60.0 + int(parts[2]) / 3600.0
        deg, minute, second, sign = longitude.split()
        lat_d, lat_h, lat_m, lat_s = latitude.split()
        dec_d, dec_h, dec_m, dec_s = declination.split()
        alt_sign, *alt = altitude.split()
        rows.append({"name": name, "house": int(house), "longitude": SIGNS.index(sign) * 30 + dms(deg, minute, second),
                     "latitude": dms(lat_d, lat_m, lat_s) * (1 if lat_h == "N" else -1),
                     "right_ascension": dms(*right_ascension.split()),
                     "declination": dms(dec_d, dec_m, dec_s) * (1 if dec_h == "N" else -1),
                     "altitude": dms(*alt) * (1 if alt_sign == "+" else -1)})
    return rows


JANUS_BOUND = 2.0     # seconds of arc
# Past that bound, each with the most it was measured at, on all five measures.
JANUS_KNOWN = {
    "Porrima": (5.3, "a fast mover: the two catalogues carry its proper motion differently"),
    "Rigel Kentaurus": (3.6, "a fast mover: the two catalogues carry its proper motion differently"),
    "Polaris": (3.8, "near the pole a small arc is a large right ascension: 3.73 in right ascension, under 1 elsewhere"),
}
# Janus reads these at another point than this catalogue's row for the object; the catalogue's point
# stands, so only the names are asserted.
JANUS_CLUSTERS = ("Capulus", "Spiculum", "Aculeus", "Acumen", "Facies")
# Two rows answer the name; Janus's position is this one's.
JANUS_SHARED = {"Menkar": "alCet"}


def _arc(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0) * 3600.0


def test_janus_reads_every_star_the_catalogue_names(engine):
    rows = _janus_rows()
    assert len(rows) == 136 and "Copula" in {row["name"] for row in rows}
    chart = invented_chart(engine)
    frame = engine["fixed_star_frame"](chart)
    stars = {engine["fixed_star_identity"](star): star for star in placed(engine, chart["julian_day"])}
    forms = engine["fixed_star_finder"]()["forms"]
    within = beyond = 0
    for row in rows:
        name = row["name"]
        if name == "Copula":
            assert engine["fixed_star_find"](name) == ()
            continue
        found = forms.get(engine["fixed_star_normalized"](name))
        assert found, name
        if name in JANUS_CLUSTERS:
            assert len(found) == 1, name
            continue
        if name in JANUS_SHARED:
            found = [i for i in found if stars[i].designation == JANUS_SHARED[name]]
        assert len(found) == 1, name
        star = stars[found[0]]
        if name in JANUS_OTHER_NAMES:
            assert star.designation == JANUS_OTHER_NAMES[name] and name in (star.name, *star.other_names)
        measures = [_arc(star.longitude, row["longitude"]), _arc(star.latitude, row["latitude"]),
                    _arc(star.right_ascension, row["right_ascension"]), _arc(star.declination, row["declination"]),
                    _arc(engine["fixed_star_altitude"](star, frame), row["altitude"])]
        bound = JANUS_KNOWN[name][0] if name in JANUS_KNOWN else JANUS_BOUND
        assert max(measures) <= bound, (name, [round(m, 2) for m in measures])
        if name in JANUS_KNOWN:
            assert max(measures) > JANUS_BOUND, f"{name} no longer needs its own bound"
            beyond += 1
        else:
            within += 1
        assert engine["get_house_number"](star.longitude, chart["houses"]) == row["house"], name
    assert within == 127 and beyond == 3


# --- The clocks --------------------------------------------------------------------------------

CHICAGO = {"zone": "America/Chicago", "latitude": 41.88, "longitude": -87.63}


def _jd(engine, *moment):
    year, month, day, hour, minute, second = moment
    return engine["civil_to_jd"](year, month, day, hour + minute / 60.0 + second / 3600.0)


def _zoneinfo_reading(engine, jd, zone):
    """The same instant by zoneinfo, the second method for a zone's clock."""
    utc = engine["CivilMoment"].from_jd(jd)
    moment = datetime(utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second, tzinfo=timezone.utc).astimezone(ZoneInfo(zone))
    return moment.strftime("%Y-%m-%d %H:%M:%S"), moment.utcoffset().total_seconds() / 3600.0


@pytest.mark.parametrize("moment", [(2021, 3, 14, 7, 59, 59), (2021, 3, 14, 8, 0, 0), (2021, 3, 14, 8, 0, 1),
                                    (2021, 11, 7, 6, 30, 0), (2021, 11, 7, 6, 59, 59), (2021, 11, 7, 7, 0, 0), (2021, 11, 7, 7, 30, 0),
                                    (2021, 7, 1, 12, 0, 0), (2021, 1, 1, 5, 59, 59), (2021, 1, 1, 6, 0, 0)])
@pytest.mark.parametrize("guess", [-6.0, -5.0, 3.0])
def test_a_zone_s_clock_at_an_instant_whatever_the_chart_s_offset(engine, moment, guess):
    jd = _jd(engine, *moment)
    reading = engine["fixed_star_clock_reading"](jd, {**CHICAGO, "offset_hours": guess})
    assert reading is not None
    local, hours = reading
    assert (local.isoformat(), hours) == _zoneinfo_reading(engine, jd, "America/Chicago")


def test_a_clock_of_one_offset_keeps_it_at_every_instant(engine):
    for year in (1, 1977, 3000):
        jd = engine["civil_to_jd"](year, 3, 1, 23.5)
        local, hours = engine["fixed_star_clock_reading"](jd, {"offset_hours": 5.125})
        assert hours == 5.125
        assert local.isoformat() == engine["CivilMoment"].from_jd(jd + 5.125 / 24.0).isoformat()
        assert local.day == 2 and local.hour == 4 and local.minute == 37 and local.second == 30


@pytest.mark.parametrize("year, month, day", [(1, 3, 1), (3000, 6, 15), (1240, 5, 23)])
def test_the_chart_s_own_instant_reads_back_its_digits_at_the_ends_of_the_range(engine, year, month, day):
    for offset in (0.75, -5.0, 11.25 / 15.0):
        jd = engine["civil_local_to_jd_ut"](year, month, day, 14.5, offset)
        local, hours = engine["fixed_star_clock_reading"](jd, {"offset_hours": offset})
        assert hours == offset
        assert (local.year, local.month, local.day, local.hour, local.minute, local.second) == (year, month, day, 14, 30, 0)


def test_a_crossing_s_instant_is_the_chart_s_plus_the_unrounded_interval(engine):
    chart = invented_chart(engine)
    frame = engine["fixed_star_frame"](chart)
    star = star_named(engine, placed(engine, chart["julian_day"]), "Regulus")
    crossings = engine["fixed_star_crossings"](star, frame, {"offset_hours": -6.0})
    assert [c["event"] for c in crossings] == ["Rising", "Upper culmination", "Setting", "Lower culmination"]
    for crossing in crossings:
        seconds = engine["fixed_star_crossing_seconds"](star.right_ascension, star.declination, frame["armc"], frame["latitude"], crossing["axis"])
        assert seconds != round(seconds), "the premise: an interval with a fraction"
        assert crossing["seconds"] == seconds
        assert crossing["instant"] == chart["julian_day"] + seconds / 86400.0
        assert crossing["reading"][0].isoformat() == engine["CivilMoment"].from_jd(crossing["instant"] - 6.0 / 24.0).isoformat()
        assert crossing["foot_point_altitude"] == engine["fixed_star_foot_point_altitude"](star, frame, seconds)


def test_a_star_that_never_crosses_has_no_clock_time(engine):
    chart = chart_at(engine, 2000, 66.0)
    frame = engine["fixed_star_frame"](chart)
    star = next(s for s in placed(engine, chart["julian_day"])
                if engine["fixed_star_semi_arc"](s.declination, 66.0) is None)
    crossings = engine["fixed_star_crossings"](star, frame, {"offset_hours": 0.0})
    assert [c["seconds"] is None for c in crossings] == [True, False, True, False]
    assert "reading" not in crossings[0] and "reading" in crossings[1]


def named_zone_app(moment):
    """An invented chart in a named zone, with its place typed in."""
    at = fixed_stars_app(date=moment.strftime("%Y-%m-%d"))
    at.session_state["time_input_key"] = moment.time()
    at.session_state["time_standard_key"] = "Standard time (named zone)"
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = CHICAGO["latitude"], CHICAGO["longitude"]
    return at


def test_on_the_page_a_crossing_across_a_clock_change_prints_the_offset_at_its_own_instant(engine):
    at = named_zone_app(datetime(2021, 3, 14, 1, 30, 0))
    at.run(timeout=120)
    assert_no_exception(at, "the named zone")
    strip = at.main.caption[0].value
    assert "2021-03-14 01:30:00" in strip and "-06:00" in strip
    choose_population(at, "Sahl's 28")
    rows = opener_rows(tab_named(at, "Star list"), "zij-open-sahl-")
    offsets = set()
    midnight = False
    for row in rows[:12]:
        next(b for b in at.main.button if b.key == row["key"]).click().run(timeout=120)
        facts = facts_of(at)
        for event in ("Rising", "Upper culmination", "Setting", "Lower culmination"):
            if len(facts[event]) < 2:
                continue
            local, offset = facts[event][0], facts[event][1]
            offsets.add(offset)
            midnight = midnight or not local.startswith("2021-03-14")
            # Each is the zone's own at that local reading: the two sides of the change.
            hours = {"UTC-06:00": -6.0, "UTC-05:00": -5.0}[offset]
            when = datetime.strptime(local, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=hours)))
            assert when.astimezone(ZoneInfo("America/Chicago")).utcoffset() == timedelta(hours=hours), (event, local, offset)
    assert offsets == {"UTC-06:00", "UTC-05:00"}
    assert midnight, "a crossing across local midnight prints its own day"


def test_on_the_page_the_lower_and_upper_culminations_keep_their_names():
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "Sirius")
    facts = facts_of(at)
    assert {"Rising", "Upper culmination", "Setting", "Lower culmination"} <= set(facts)
    text = drawn_text(dialog_of(at))
    assert "Anti-culmination" not in text and "\nCulmination" not in text


@pytest.mark.parametrize("standard, offset, printed", [("Manual UTC offset", -5.0, "UTC-05:00"), ("LMT (Local Mean Time)", None, "UTC+00:44:59")])
def test_the_page_s_clock_reads_back_its_strip(engine, standard, offset, printed):
    """A star crossing at the chart's own moment would read the strip's digits and offset: here, each
    crossing's reading less its interval reads them."""
    at = fixed_stars_app()
    at.session_state["time_standard_key"] = standard
    if offset is not None:
        at.session_state["utc_offset_key"] = offset
    at.run(timeout=120)
    find_star(at, "Sirius")
    facts = facts_of(at)
    assert facts["Upper culmination"][1] == printed
    assert printed.removeprefix("UTC") in at.main.caption[0].value
    interval = facts["MC, crossing (min:s)"][0]
    sign = -1 if interval.startswith(MINUS) else 1
    minutes, seconds = interval.lstrip(f"+{MINUS}").split(":")
    moment = engine["CivilMoment"]
    local = facts["Upper culmination"][0]
    year, month, day = map(int, local[:10].split("-"))
    hour, minute, second = map(int, local[11:].split(":"))
    back = engine["civil_to_jd"](year, month, day, hour + minute / 60.0 + second / 3600.0) - sign * (int(minutes) * 60 + int(seconds)) / 86400.0
    # The printed interval is rounded to the second, so the two agree to within that second.
    strip = moment(*map(int, re.split(r"[- :]", at.main.caption[0].value.split(" · ")[1])))
    assert abs(back - strip.jd()) * 86400.0 <= 1.5


# --- The record --------------------------------------------------------------------------------

def test_the_record_holds_its_twenty_fields_and_no_empty_card_for_the_five_to_come(engine):
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "Sirius")
    block = dialog_of(at)
    assert block.proto.dialog.width and _title(block) == "Sirius · α CMa"
    facts = facts_of(at)
    for label in ("Catalogue designation", "Longitude", "Latitude", "Right ascension (h m s)", "Declination", "V magnitude",
                  "Altitude", "Foot-point altitude at the chart", "Foot-point longitude", "Foot-point position",
                  "Rising", "Upper culmination", "Setting", "Lower culmination",
                  "Ascendant, crossing (min:s)", "Ascendant, longitude offset", "MC, crossing (min:s)", "IC, longitude offset"):
        assert label in facts, label
    assert facts["Catalogue designation"][0] == "alCMa"
    text = drawn_text(block)
    assert "Nature (Rhetorius, per Dykes)" in text and "Sahl I pp. 391–392" in text and "Jupiter-Mars" in text
    for absent in ("Azimuth", "azimuth", "Co-rising", "Co-culminating", "Co-setting", "Co-anti", "co-degree", "Co-degrees", "⋯"):
        assert absent not in text, absent
    for group in ("Place at the chart", "Star and foot point", "Crossings in the chart's clock", "Measures at the axes"):
        assert group in text, group


def test_nothing_in_the_record_is_a_control_but_the_native_close():
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "Sirius")
    kinds = {getattr(n, "type", None) for n in walk(dialog_of(at))}
    assert not kinds & {"button", "selectbox", "checkbox", "toggle", "radio", "text_input", "download_button", "popover", "tabs"}, kinds


@pytest.mark.parametrize("name, words", [
    ("Alphecca", "Venus-Mercury (Sahl, following al-Andarzaghar, classifies it as Jupiter-Mercury, fn 73)"),
    ("Menkalinan", "Jupiter-Saturn (Sahl, following al-Andarzaghar, classifies it with Jupiter-Mars, fn 75)"),
    ("Antares", "Jupiter-Mars (Sahl, following al-Andarzaghar, adds it again as Mars-Venus, 2.2, 66, 70, fn 74)")])
def test_a_nature_s_alternatives_and_footnote_stand_beside_it_in_the_record(name, words):
    at = fixed_stars_app().run(timeout=120)
    find_star(at, name)
    assert words in drawn_text(dialog_of(at))


def test_no_nature_is_a_dash_with_its_help_beside_it():
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "ζ Dor")
    text = drawn_text(dialog_of(at))
    assert "\n—\n" in text
    assert "Rhetorius's natures, from Dykes's table at Sahl I pp. 391–392; a dash marks other catalogue objects." in text


def test_a_star_with_no_magnitude_prints_the_word_in_the_record_and_never_nan(engine, monkeypatch):
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "Great Attractor")
    assert facts_of(at)["V magnitude"] == ["Unavailable"]
    sync_engine_to_environment()
    real = engine["fixed_star_places"]

    def with_a_nan(jd):
        stars, missing = real(jd)
        return tuple(dataclasses.replace(s, magnitude=float("nan")) if s.name == "Sirius" else s for s in stars), missing
    monkeypatch.setitem(engine, "fixed_star_places", with_a_nan)
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "Sirius")
    assert facts_of(at)["V magnitude"] == ["Unavailable"]
    rows = at.session_state["_fixed_stars_export"]["results"]["Fixed stars"]["Star list: Curated List"][0]["rows"]
    assert next(r for r in rows if r["Name"] == "Sirius")["V magnitude"] is None
    assert "nan" not in at.session_state["_fixed_stars_markdown"].lower().split("sirius")[1][:120]
    assert "<td>nan</td>" not in at.session_state["_fixed_stars_html"]
    json.loads(json.dumps(at.session_state["_fixed_stars_export"], allow_nan=False, default=str))


def test_a_record_opens_the_same_from_every_opener(engine):
    at = fixed_stars_app().run(timeout=120)
    # The first star of an axis list, then the same star from the Star list, the table and the finder.
    row = next(rows[0] for rows in axis_lists(at).values() if rows)
    identity = row["identity"]
    next(b for b in at.main.button if b.key == row["key"]).click().run(timeout=120)
    from_list = drawn_text(dialog_of(at)), _title(dialog_of(at))
    star = engine["fixed_star_finder"]()["stars"][identity]
    find_star(at, engine["fixed_star_label"](star).split(" · ")[-1])
    assert (drawn_text(dialog_of(at)), _title(dialog_of(at))) == from_list
    # A row of Sahl's opens its own star; a second run brings nothing back.
    choose_population(at, "Sahl's 28")
    sahl = sahl_rows(at)[0]
    next(b for b in at.main.button if b.key == sahl["key"]).click().run(timeout=120)
    assert _title(dialog_of(at)).split(" · ")[0] == sahl["name"]
    at.run(timeout=120)
    assert dialog_of(at) is None


def test_every_row_s_button_opens_its_own_star(engine):
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Full Catalogue")
    rows = [row for rows in axis_lists(at).values() for row in rows]
    assert rows
    # Some list must hold two rows or more: in a list of one, a row that opened its neighbour could not show.
    assert any(len(listed) > 1 for listed in axis_lists(at).values())
    stars = engine["fixed_star_finder"]()["stars"]
    for row in rows:
        assert engine["fixed_star_shown_name"](stars[row["identity"]]) == row["name"]
        assert engine["fixed_star_second_form"](stars[row["identity"]]) == row["second"]
    for row in rows:
        next(b for b in at.main.button if b.key == row["key"]).click().run(timeout=120)
        assert _title(dialog_of(at)) == engine["fixed_star_label"](stars[row["identity"]]).replace("_", "\\_").replace("*", "\\*")


def test_two_stars_that_print_alike_open_their_own_records(engine):
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "Kuma")
    choice = next(s for s in at.main.selectbox if "stars found" in s.label)
    seen = []
    assert len(choice.options) == 2
    for identity in engine["fixed_star_find"]("Kuma"):
        next(s for s in at.main.selectbox if "stars found" in s.label).set_value(identity)
        next(b for b in at.main.button if b.label == "Open record").click().run(timeout=120)
        seen.append(facts_of(at)["Longitude"][0])
    assert len(set(seen)) == 2, seen


def test_the_table_s_selection_opens_once_and_a_later_run_brings_nothing_back(engine, monkeypatch):
    """The selection stays on a table after its record closes. AppTest has no click on a canvas, so what
    a click gives the page is handed to it by Streamlit's own call: the rows selected."""
    sync_engine_to_environment()
    import streamlit
    real, selected = streamlit.dataframe, []

    def dataframe(data, **kwargs):
        real(data, **kwargs)
        return types.SimpleNamespace(selection=types.SimpleNamespace(rows=list(selected)))
    monkeypatch.setattr(streamlit, "dataframe", dataframe)
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Full Catalogue")
    assert dialog_of(at) is None
    frame = tab_named(at, "Star list").dataframe[0].value
    selected[:] = [5]
    at.run(timeout=120)
    assert _title(dialog_of(at)).startswith(frame["Name"][5])
    at.run(timeout=120)
    assert dialog_of(at) is None, "the same selection is no new choice"
    selected[:] = [7]
    at.run(timeout=120)
    assert _title(dialog_of(at)).startswith(frame["Name"][7])
    selected[:] = []
    at.run(timeout=120)
    assert dialog_of(at) is None, "a row deselected opens nothing"
    selected[:] = [7]
    at.run(timeout=120)
    assert _title(dialog_of(at)).startswith(frame["Name"][7]), "deselect, select: the same row again"


def test_the_table_prints_forms_over_numbers_that_sort(monkeypatch):
    """A cell holds the number and prints its form, so the grid sorts a column by value. The sort itself
    is the browser's, and is measured there."""
    sync_engine_to_environment()
    import streamlit
    real, given = streamlit.dataframe, []

    def dataframe(data, **kwargs):
        given.append(data)
        return real(data, **kwargs)
    monkeypatch.setattr(streamlit, "dataframe", dataframe)
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Full Catalogue")
    frame = tab_named(at, "Star list").dataframe[0].value
    for column in ("Longitude", "Latitude (°)", "Right ascension (h m s)", "Declination (°)", "V magnitude"):
        assert frame[column].dtype.kind == "f", column
    assert list(frame["Longitude"]) == sorted(frame["Longitude"])
    assert frame["Longitude"].between(0, 360).all() and frame["Right ascension (h m s)"].between(0, 360).all()
    drawn = given[-1].to_html()
    assert re.search(r">\d\d° [A-Z][a-z]{2} \d\d'<", drawn) and re.search(r">\d\dh \d\dm \d\ds<", drawn)
    assert ">Unavailable<" in drawn and ">nan<" not in drawn and ">None<" not in drawn


# --- The two lists stand level -----------------------------------------------------------------

def test_both_lists_of_an_axis_carry_the_same_head_lines():
    at = fixed_stars_app().run(timeout=120)
    heads = [n.proto.body for n in walk(tab_named(at, "Axes")) if getattr(n, "type", None) == "html" and "zij-list-head" in n.proto.body]
    assert len(heads) == 8
    shape = re.compile(r'^<div class="zij-list-head"><div class="zij-list-title"><strong>[^<]+</strong><span class="zij-locator">\d+ entr(y|ies)</span></div>'
                       r'<div class="zij-locator">[^<]+</div></div>$')
    for head in heads:
        assert shape.match(head), head
    for at_axis in range(0, 8, 2):
        assert "Crossing within ±4 min" in heads[at_axis] and "Longitude within 1°" in heads[at_axis + 1]


def test_each_list_s_first_child_after_its_head_is_a_row():
    """Nothing stands between a head and its list, so the two lists' rows start level: a
    spacer in one list's markup would pass the head's lines above. (A stylesheet's padding
    on one head shows only in a browser.)"""
    at = fixed_stars_app().run(timeout=120)
    lists = [node for node in walk(tab_named(at, "Axes"))
             if any(getattr(kid, "type", None) == "html" and "zij-list-head" in kid.proto.body
                    for kid in getattr(node, "children", {}).values())]
    assert len(lists) == 8
    for block in lists:
        head, after, *_rest = block.children.values()
        assert "zij-list-head" in head.proto.body
        assert opener_rows(after, "zij-open-") or type(after).__name__ == "Info", type(after).__name__


def test_the_measure_that_admits_a_row_is_bold_and_never_rises_stays_a_word(engine):
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Full Catalogue")
    words = set()
    for (_axis, kind), rows in axis_lists(at).items():
        for row in rows:
            assert row["admits"] == ["Crossing (min:s)" if kind == "crossing" else "Longitude offset"], row
            words.add(row["values"]["Crossing (min:s)"])
    assert {"Never rises"} & words, "the premise: a longitude list holds a star that never rises"
    import house_style
    css = house_style.PAGE_STYLE
    assert re.search(r"\.zij-admits\{color:light-dark\([^)]*\);font-weight:600;\}", css), "bold, not colour alone"


def test_the_axis_heading_keeps_its_label(engine):
    at = fixed_stars_app().run(timeout=120)
    captions = [c.value for c in tab_named(at, "Axes").caption]
    assert len(captions) == 4 and all(c.startswith("Longitude: ") for c in captions)


# --- The export --------------------------------------------------------------------------------

def _export(at):
    return at.session_state["_fixed_stars_export"]


def test_the_export_keeps_the_raw_key_beside_the_greek_form(engine):
    at = fixed_stars_app().run(timeout=120)
    rows = _export(at)["results"]["Fixed stars"]["Star list: Curated List"][0]["rows"]
    alpheratz = next(r for r in rows if r["Name"] == "Alpheratz")
    assert alpheratz["Designation"] == "α And" and alpheratz["Catalogue designation"] == "alAnd"
    assert "Sirrah" in alpheratz["Other names"]


def test_the_export_follows_the_control_and_never_the_tab_the_query_or_the_record():
    at = fixed_stars_app().run(timeout=120)
    first = _export(at)
    find_star(at, "Sirrah")
    assert _export(at) is first, "a query and a record leave the payload as built"
    find_star(at, "al")
    assert _export(at) is first
    choose_population(at, "Full Catalogue")
    assert list(_export(at)["results"]["Fixed stars"])[-2] == "Star list: Full Catalogue"
    assert len(_export(at)["results"]["Fixed stars"]) == 10
    assert len(_export(at)["results"]["Fixed stars"]["Star list: Full Catalogue"][0]["rows"]) == 1852


def test_the_payload_is_built_once_for_its_chart_and_again_for_another():
    at = fixed_stars_app().run(timeout=120)
    key, first = at.session_state["_fixed_stars_payload"]["key"], _export(at)
    at.run(timeout=120)
    assert at.session_state["_fixed_stars_payload"]["key"] == key and _export(at) is first
    at.session_state["date_input_key"] = "1240-05-24"
    at.run(timeout=120)
    assert at.session_state["_fixed_stars_payload"]["key"] != key and _export(at) is not first
    assert _export(at)["input"] != first["input"], "the payload follows the chart"
    at.session_state["manual_lat_key"] = 40.0
    second = _export(at)
    at.run(timeout=120)
    assert _export(at) is not second, "and the place"


# --- States ------------------------------------------------------------------------------------

def test_the_last_valid_chart_holds_the_page_and_the_record_follows_it():
    at = fixed_stars_app().run(timeout=120)
    before = at.main.caption[0].value
    find_star(at, "Sirius")
    longitude = facts_of(at)["Longitude"]
    at.session_state["date_input_key"] = "not a date"
    at.run(timeout=120)
    assert dialog_of(at) is None
    assert any(w.value.startswith("Results have not updated.") for w in at.main.warning)
    assert at.main.caption[0].value == before
    find_star(at, "Sirius")
    assert facts_of(at)["Longitude"] == longitude


def test_no_chart_draws_no_finder_no_export_and_opens_nothing():
    at = fixed_stars_app().run(timeout=120)
    next(b for b in at.main.button if b.key.startswith("zij-open-")).click()
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = ""
    at.run(timeout=120)
    assert_no_exception(at, "no chart")
    assert dialog_of(at) is None
    assert not [t for t in at.main.text_input if t.label == "Find a star"]
    assert not [n for n in walk(at.main) if getattr(n, "type", None) == "popover"]
    assert "_fixed_stars_open" not in at.session_state


def test_no_catalogue_entries_stands_alone(engine, monkeypatch):
    sync_engine_to_environment()
    monkeypatch.setitem(engine, "fixed_star_places", lambda jd: ((), {}))
    at = fixed_stars_app().run(timeout=120)
    assert_no_exception(at, "nothing placed")
    assert [i.value for i in at.main.info] == ["No catalogue entries could be placed."]
    assert not [t for t in at.main.text_input if t.label == "Find a star"]
    assert "No crossings within ±4 min." not in str([i.value for i in at.main.info])


def test_a_star_the_catalogue_cannot_place_is_found_and_says_so(engine, monkeypatch):
    sync_engine_to_environment()
    real = engine["fixed_star_places"]

    def without_sirius(jd):
        stars, _missing = real(jd)
        return tuple(s for s in stars if s.name != "Sirius"), {"Sirius": "refused"}
    monkeypatch.setitem(engine, "fixed_star_places", without_sirius)
    at = fixed_stars_app().run(timeout=120)
    assert [w.value for w in at.main.warning] == ["Not in the catalogue attached, so not placed: Sirius."]
    find_star(at, "Sirius")
    assert _title(dialog_of(at)) == "Sirius · α CMa"
    assert facts_of(at)["Longitude"] == ["Unavailable"]
    assert "Rising" not in facts_of(at)


# --- The page's words --------------------------------------------------------------------------

THE_WORD = re.compile(r"\bangles?\b", re.IGNORECASE)
CUT = ("Greek and Latin designations are accepted.", "Each time keeps its local day and offset.", "Culmination\n",
       "Anti-culmination", "Calculation unavailable", "Not defined", "Crossing unavailable", "Close record", "Star record",
       "Show full catalogue", "Outside the source-nature set.")


def test_the_page_and_the_record_say_nothing_cut_and_nothing_of_the_word():
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "Sirius")
    drawn = "\n".join(str(getattr(n, "proto", "")) for n in walk(at._tree)) + drawn_text(dialog_of(at))
    assert "Find a star" in drawn and "Place at the chart" in drawn and "Rising" in drawn, "the page's own body"
    assert not THE_WORD.search(drawn)
    for words in CUT:
        assert words not in drawn, words


def test_the_seven_helps_stand_word_for_word_where_they_belong():
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "ζ Dor")
    source = "\n".join(str(getattr(n, "proto", "")) for n in walk(at.main))
    about = next(e for e in tab_named(at, "Axes").expander if e.label == "About the two measures")
    assert len(about.markdown) == 4
    assert "0:00 is at the chart" in about.markdown[2].value
    assert "to the whole catalogue with its nonstellar entries; the finder reaches every star." in source
    assert "Exports all eight axis lists and the selected star list in longitude order; changing tabs does not change the export." in source
    assert "a dash marks other catalogue objects." in source
    assert "a dash marks other catalogue objects." in drawn_text(dialog_of(at))


def test_the_new_strings_stay_clear_of_the_page_rules():
    from test_prose_counts import BUILD_PROCESS_MARKERS, COURSE_MARKERS
    at = fixed_stars_app().run(timeout=120)
    find_star(at, "Sirius")
    drawn = drawn_text(at.main) + drawn_text(dialog_of(at))
    assert "Crossings in the chart's clock" in drawn
    assert BUILD_PROCESS_MARKERS.findall(drawn) == []
    assert COURSE_MARKERS.findall(drawn) == []
    assert "’" not in drawn.replace("′", "")


# --- The stylesheet ----------------------------------------------------------------------------

def test_the_page_s_stylesheet_keys_only_what_is_stable():
    import house_style
    css = re.sub(r"url\(data:[^)]*\)", "", house_style.PAGE_STYLE)
    assert "st-emotion-cache" not in css
    assert "st-key-zij-" in css and ".zij-facts" in css and ".zij-nature" in css
    assert "IBM Plex" not in css


def test_nothing_on_the_page_uses_st_dialog_or_a_style_of_its_own():
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    page = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "page_fixed_stars")
    calls = [ast.unparse(node.func) for node in ast.walk(page) if isinstance(node, ast.Call)]
    assert "st.dialog" not in calls and "_star_finder" in calls
    assert "_star_record_opening" in calls
    opening = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_star_record_opening")
    assert "_pinned_dialog(_label_text(fixed_star_label(star)), width='large')" in ast.unparse(opening)
