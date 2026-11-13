"""The sky's second stage on the engine's side: the minute it prints, the foot it is
handed, the degree that rises with a star, and Turn's speeds. Turn itself lives in
the browser: tests/js/sky_host.test.mjs."""
import json
import math
import re
from pathlib import Path

import pytest

import engine
import sky

HERE = Path(__file__).resolve().parent
TOWER = json.loads((HERE / "fixtures" / "sky_co_rising_tower.json").read_text(encoding="utf-8"))
# A degree's agreement over a circle's wrap.
_apart = lambda a, b: abs((a - b + 180.0) % 360.0 - 180.0)
JULIAN_DAYS = (1538599.0, 2174111.07, 2451545.0, 2524759.0)
LATITUDES = (-65.0, -51.5, -33.9, -12.0, 0.0, 12.0, 30.0, 43.77925, 51.5, 60.0, 65.0)


def _view_prints(longitude):
    """The view's own rule (vendor/sphere-world.js, fmtZod), which rounds."""
    total = round((longitude % 360.0) * 60) % 21600
    return total // 60 % 30, total // 1800, total % 60


def _app_prints(longitude):
    degree, minute = engine._whole_minutes(longitude)
    return degree % 30, degree // 30, minute


@pytest.mark.parametrize("longitude", [192.0 + 16 / 60 + 40 / 3600, 192.0 + 16 / 60 + 29 / 3600, 192.0 + 16 / 60, 30.0 + 1 / 60, 60.0 - 1e-10,
                                       29.0 + 59 / 60 + 59.9 / 3600, 359.9999999, 0.0, 1e-9, 359.0 + 59.5 / 60])
def test_the_view_prints_what_the_app_prints_once_it_is_cut(longitude):
    assert _view_prints(engine.longitude_at_whole_minute(longitude)) == _app_prints(longitude)


def test_the_cut_matters_at_half_a_minute_on_and_holds_over_the_circle():
    uncut = [_view_prints(n * 0.0137) != _app_prints(n * 0.0137) for n in range(26000)]
    assert sum(uncut) > 10000, "the view alone rounds about half of them away"
    for n in range(26000):
        assert _view_prints(engine.longitude_at_whole_minute(n * 0.0137)) == _app_prints(n * 0.0137)


def test_each_row_carries_the_engines_foot_and_degree():
    stars = engine.fixed_star_places(2451545.0)[0]
    co = lambda star: engine.fixed_star_co_rising_degree(star.right_ascension, star.declination, 43.0, 23.44)
    places = sky.sources(stars, engine.fixed_star_identity, engine.fixed_star_label, engine.longitude_at_whole_minute, co)
    rows = {row["id"]: row for row in places["stars"] + places["objects"]}
    assert len(rows) == 1852
    nones = 0
    for star in stars:
        row = rows[places["ids"][engine.fixed_star_identity(star)]]
        assert row["lat"] == star.latitude
        assert row["lon"] == engine.longitude_at_whole_minute(star.longitude)
        assert engine.get_degree_string(row["lon"]) == engine.get_degree_string(star.longitude)
        if co(star) is None:
            nones += 1
            assert row["co"] is None
        else:
            assert engine.get_degree_string(row["co"]) == engine.get_degree_string(co(star))
    assert 0 < nones < 1852


def test_the_envelope_hands_the_ascendant_at_its_minute_and_the_speeds():
    stars = engine.fixed_star_places(2451545.0)[0]
    places = sky.sources(stars, engine.fixed_star_identity, engine.fixed_star_label, engine.longitude_at_whole_minute, lambda star: None)
    frame = {"julian_day": 2451545.0, "latitude": 43.0, "armc": 100.0, "obliquity": 23.44, "axes": {"Ascendant": 192.0 + 16 / 60 + 40 / 3600}}
    data = sky.envelope(places, frame, [], {}, "x", "orbit", "dark", None, engine.longitude_at_whole_minute, engine.FIXED_STAR_SIDEREAL_RATE)
    assert _view_prints(data["axes"]["asc"]) == (12, 6, 16)
    assert data["observer"]["lst"] == 100.0


def test_turns_five_speeds_are_the_engines_rate_and_the_towers_words():
    speeds = sky.speeds(engine.FIXED_STAR_SIDEREAL_RATE)
    assert [speed["minutes"] for speed in speeds] == [1, 2, 10, 60, 104]
    assert [round(speed["rate"], 3) for speed in speeds] == [0.251, 0.501, 2.507, 15.041, 26.0]
    for speed in speeds[:4]:
        assert speed["rate"] == speed["minutes"] * 60.0 * engine.FIXED_STAR_SIDEREAL_RATE


@pytest.mark.parametrize("julian_day", JULIAN_DAYS)
def test_with_the_degree_on_the_ascendant_the_star_is_rising(julian_day):
    """The first witness, the engine's own: with this degree rising the star's time to
    the Ascendant is nothing, by its own function, and by two others that owe it nothing."""
    obliquity = engine.swe.calc_ut(julian_day, engine.swe.ECL_NUT, engine.swe.FLG_MOSEPH)[0][0]
    stars = engine.fixed_star_places(julian_day)[0]
    assert len(stars) == 1852
    checked = 0
    for latitude in LATITUDES:
        for star in stars:
            degree = engine.fixed_star_co_rising_degree(star.right_ascension, star.declination, latitude, obliquity)
            semi_arc = engine.fixed_star_semi_arc(star.declination, latitude)
            assert (degree is None) == (semi_arc is None)
            if degree is None:
                continue
            armc = engine._oblique_ascension(degree, obliquity, latitude) - 90.0
            seconds = engine.fixed_star_crossing_seconds(star.right_ascension, star.declination, armc, latitude, "Ascendant")
            assert abs(seconds) < 1e-9, (star.name, latitude, seconds)
            hour = math.radians(armc - star.right_ascension)
            phi, delta = math.radians(latitude), math.radians(star.declination)
            assert abs(math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.cos(hour)) < 1e-13
            assert math.sin(hour) <= 1e-9, "east of the meridian"
            assert _apart(engine.swe.houses_armc(armc % 360.0, latitude, obliquity, b"O")[1][0], degree) < 1e-10
            checked += 1
    assert checked > 14000


def test_there_is_no_degree_for_a_star_that_does_not_rise_or_outside_the_domain():
    assert engine.fixed_star_semi_arc(80.0, 43.0) is None
    assert engine.fixed_star_co_rising_degree(100.0, 80.0, 43.0, 23.44) is None
    assert engine.fixed_star_co_rising_degree(100.0, -80.0, 43.0, 23.44) is None
    # This star rises at 70 north, but there the inverse is not one degree.
    assert engine.fixed_star_semi_arc(5.0, 70.0) is not None
    assert engine._lon_with_oblique_ascension(100.0, 23.44, 70.0) is None
    assert engine.fixed_star_co_rising_degree(100.0, 5.0, 70.0, 23.44) is None
    assert engine.fixed_star_co_rising_degree(100.0, 5.0, 66.0, 23.44) is not None
    assert engine.fixed_star_co_rising_degree(100.0, 5.0, 66.56, 23.44) is None


def test_a_star_on_the_equator_at_the_equator_rises_with_its_right_ascensions_degree():
    assert _apart(engine.fixed_star_co_rising_degree(0.0, 0.0, 0.0, 23.44), 0.0) < 1e-12
    assert _apart(engine.fixed_star_co_rising_degree(90.0, 0.0, 0.0, 23.44), 90.0) < 1e-12


# The largest difference, in seconds of arc, at each of the frozen dates, of the
# Tower's degree from its own places and the engine's degree from its own: the two
# astronomies part as they do at those dates, and the rule does not.
TOWER_OWN_PLACES_CEILING = {-500: 13.0, 1000: 0.9, 1240: 0.55, 1600: 0.2, 2000: 0.2, 2200: 0.25}


@pytest.mark.parametrize("date", TOWER["dates"], ids=lambda date: str(date["year"]))
def test_the_second_witness_the_towers_own_degree(date):
    """The Tower's Astro.coRising, run once under Node and frozen in the fixture."""
    assert TOWER["core_sha256"] == "e4c72b872b6b43ede77af46f531217869dbfdabcf8141b769f7d0beaf647547c"
    same, none_here = [], 0
    for _id, latitude, ra, dec, rise in date["rows"]:
        degree = engine.fixed_star_co_rising_degree(ra, dec, latitude, date["obliquity"])
        if degree is None and rise is not None:
            # Above the polar circle the engine says none: the Tower gives a branch.
            assert abs(latitude) + date["obliquity"] >= 90.0
            none_here += 1
            continue
        assert (degree is None) == (rise is None), (_id, latitude)
        if degree is not None:
            same.append(_apart(degree, rise))
    assert len(same) > 200
    assert max(same) < 1e-9, "the same inputs give the same degree"
    assert none_here < 20

    stars = engine.fixed_star_places(date["jd"])[0]
    places = sky.sources(stars, engine.fixed_star_identity, engine.fixed_star_label, engine.longitude_at_whole_minute, lambda star: None)
    by_id = {places["ids"][engine.fixed_star_identity(star)]: star for star in stars}
    obliquity = engine.swe.calc_ut(date["jd"], engine.swe.ECL_NUT, engine.swe.FLG_MOSEPH)[0][0]
    apart = []
    for _id, latitude, _ra, _dec, rise in date["rows"]:
        star = by_id.get(_id)
        mine = star and engine.fixed_star_co_rising_degree(star.right_ascension, star.declination, latitude, obliquity)
        if mine is not None and mine is not False and rise is not None and star is not None:
            apart.append(_apart(mine, rise) * 3600.0)
    assert len(apart) > 200
    assert max(apart) < TOWER_OWN_PLACES_CEILING[date["year"]]


def test_the_core_itself_is_not_here():
    root = HERE.parent
    assert not list(root.glob("**/astro-core*.js"))
    assert "Astro.coRising" not in (root / "sky_host.js").read_text(encoding="utf-8")


def test_the_co_rising_words_are_plain_astronomy():
    words = json.loads((HERE.parent / "sky_words.json").read_text(encoding="utf-8"))
    text = " ".join(words[key] for key in ("tw.coRising", "tw.lblCo", "zij.noCoRising")).casefold()
    for word in ("very degree", "persian", "abū", "nativit", "sahl", "indicat", "reading", "signif"):
        assert word not in text


def test_turns_words_are_the_towers_and_its_lines_are_plain():
    words = json.loads((HERE.parent / "sky_words.json").read_text(encoding="utf-8"))
    assert {key: words[key] for key in ("ui.turn", "ui.hold", "tw.speed", "tw.perSec", "tw.hourPerSec", "tw.foot", "tw.coRising", "zij.return", "zij.moment", "zij.noCoRising")} == {
        "ui.turn": "Turn the sphere", "ui.hold": "Hold the sphere", "tw.speed": "Speed", "tw.perSec": "{n} chart min/s", "tw.hourPerSec": "1 chart h/s",
        "tw.foot": "Foot point and arc", "tw.coRising": "Co-rising degree", "zij.return": "Return to the chart",
        "zij.moment": "The lists below stay at the chart's moment.", "zij.noCoRising": "No co-rising degree is given at this latitude for {name}."}


def test_reverses_word_is_the_engines_own_and_not_the_towers():
    """Reverse is the engine's word, not one of the Tower's: the owner ruled it so, and the
    Tower's words above stay as they are. Its button is the wrapper's, with no Python control."""
    words = json.loads((HERE.parent / "sky_words.json").read_text(encoding="utf-8"))
    assert words["zij.reverse"] == "Reverse"
    tower = (HERE.parent / "vendor" / "tower-view.js").read_text(encoding="utf-8")
    assert "zij.reverse" not in tower and '"Reverse"' not in tower
    assert "reverse" not in (HERE.parent / "app.py").read_text(encoding="utf-8").lower().split("def _sky_block")[1].split("\ndef ")[0]


def test_a_pressed_reverse_takes_the_bars_colours_inverted():
    """Reverse's word is fixed, so its press shows in its look: the bar's own ground and ink, swapped.
    The selector is the class the button carries (sky_host.js) and the state it sets (aria-pressed).
    What it looks like, only a browser sees, in the development browser check's part reverse."""
    css = (HERE.parent / "sky_host.css").read_text(encoding="utf-8")
    host = (HERE.parent / "sky_host.js").read_text(encoding="utf-8")
    assert 'reverseButton.className = "zs-reverse"' in host and 'reverseButton.setAttribute("aria-pressed"' in host
    rule = re.search(r'\.zs-turn \.zs-reverse\[aria-pressed="true"\]\{([^}]*)\}', css)
    assert rule, "a pressed Reverse has no rule of its own"
    held = dict(part.split(":") for part in rule.group(1).split(";"))
    assert held == {"color": "var(--zs-ground)", "background": "var(--zs-ink)", "border-color": "var(--zs-ink)"}


def test_the_sky_that_cannot_stand_says_so_and_names_no_cause():
    words = json.loads((HERE.parent / "sky_words.json").read_text(encoding="utf-8"))
    assert words["zij.unable"] == "The sky cannot be drawn in this window."


def test_nothing_of_turn_goes_to_python():
    source = (HERE.parent / "sky_host.js").read_text(encoding="utf-8")
    assert source.count("inst.trigger(") == 1, "the record's two doors, and no other"
    assert "localStorage" not in source and "sessionStorage" not in source and "location" not in source


def test_ensis_is_another_name_of_eta_ori_in_find_a_star():
    finder = engine.fixed_star_finder()
    stars = engine.fixed_star_places(2451545.0)[0]
    eta = next(star for star in stars if star.designation == "HIP 25281")
    assert engine.fixed_star_find("Ensis", finder) == (engine.fixed_star_identity(eta),)
    assert "Ensis" in eta.other_names
    assert engine.fixed_star_label(eta).split(" · ")[0] == "η Ori"
    assert "Ensis" in engine.FIXED_STAR_NOT_LISTED
