"""Lane H9 of the ruled lanes (2026-10-05): Sahl, On Nativities 1.20, 6's
"its lord eastern", for the five planets, is 1.22's easternness as Sahl writes
it (the owner's ruling 16, Q4 of the re-pass), superseding the side-of-the-Sun
reading (REL-5-2) for the election; with 1.22, 5 read in (ruling 44): Saturn,
Jupiter or Mars gone retrograde is not eastern for it.

- 1.22, 1 (Sahl I p. 304): "if there were 6° between Saturn and Jupiter and
  the Sun, then they are considered to be eastern ... but if they were less
  than that, they will not be fit" (fn 172: "6° or more degrees earlier then
  him in the zodiac").
- 1.22, 3 (p. 304): "he does not easternize until there are 18° between him
  and the Sun" -- Sahl's figure for Mars; Dykes's 15 (fn 174) is not taken.
- 1.22, 7 (p. 305): "Venus and Mercury are eastern [when] direct in course
  before rising ... and there are 12° between them and the Sun".

The boundaries, the election on a constructed chart (REL-5-2's own, with its
Venus moved), and the Releaser page's note that states the rule.
"""
from __future__ import annotations

import pytest

from conftest import assert_no_exception, make_app

SUN = 165.0        # 15 Virgo, the REL-5-2 pin's Sun


def _pdata(**positions):
    out = {}
    for name, value in positions.items():
        lon, speed = value if isinstance(value, tuple) else (value, 1.0)
        out[name] = {"longitude": float(lon), "latitude": 0.0, "distance": 1.0,
                     "speed_in_lon": float(speed), "speed_in_lat": 0.0, "speed_in_dist": 0.0}
    return out


def _chart(asc, **planets):
    """Whole-sign cusps from the Ascendant's sign, as the doctrine fixtures build them."""
    base = (asc // 30.0) * 30.0
    cusps = [(base + 30.0 * i) % 360.0 for i in range(12)]
    seven = dict(Sun=100.0, Moon=200.0, Mercury=110.0, Venus=130.0, Mars=300.0, Jupiter=250.0, Saturn=20.0)
    seven.update(planets)
    return _pdata(**seven), cusps


@pytest.mark.parametrize("planet, before, speed, eastern", [
    # Saturn and Jupiter: 6 degrees or more earlier, inclusive (1.22, 1; fn 172)
    ("Saturn", 6.0, 0.05, True), ("Saturn", 5.99, 0.05, False), ("Jupiter", 6.0, 0.1, True),
    ("Jupiter", 5.99, 0.1, False),
    # Mars: Sahl's 18 (1.22, 3), not Dykes's 15
    ("Mars", 18.0, 0.7, True), ("Mars", 17.99, 0.7, False), ("Mars", 16.0, 0.7, False),
    # Venus and Mercury: direct and 12 (1.22, 7); retrograde or stationary is not eastern
    ("Venus", 12.0, 1.1, True), ("Venus", 11.99, 1.1, False), ("Mercury", 20.0, 1.2, True),
    ("Mercury", 20.0, -0.5, False), ("Mercury", 20.0, 0.0, False), ("Venus", 30.0, -0.3, False),
    # the evening side is not eastern, however far
    ("Saturn", -40.0, 0.05, False), ("Mars", -40.0, 0.7, False), ("Venus", -30.0, 1.1, False),
    # a superior gone retrograde is not eastern (1.22, 5; ruling 44); at its station it has not gone retrograde
    ("Saturn", 120.0, -0.05, False), ("Jupiter", 150.0, -0.1, False), ("Mars", 150.0, -0.3, False),
    ("Saturn", 120.0, 0.0, True), ("Mars", 150.0, 0.0, True), ("Jupiter", 150.0, 0.1, True),
])
def test_1_20_6_eastern_is_1_22_as_sahl_writes_it(engine, planet, before, speed, eastern):
    got, fact, morning = engine["sahl_eastern_1_20_6"](planet, (SUN - before) % 360.0, SUN, speed)
    assert got is eastern, (planet, before, speed, fact)
    assert morning is (before > 0), (planet, before, morning)
    assert fact.startswith(engine["SAHL_1_20_6_EASTERN_SENTENCE"][planet] + ": "), fact


@pytest.mark.parametrize("planet, before, speed, shown", [
    ("Saturn", 5.99, 0.05, "5.9° earlier"), ("Mars", 17.99, 0.7, "17.9° earlier"), ("Venus", 11.99, 1.1, "11.9° earlier"),
    ("Saturn", 6.0, 0.05, "6.0° earlier"), ("Mars", 18.0, 0.7, "18.0° earlier"),
])
def test_1_20_6_prints_the_distance_cut_never_rounded_onto_the_figure(engine, planet, before, speed, shown):
    _eastern, fact, _morning = engine["sahl_eastern_1_20_6"](planet, (SUN - before) % 360.0, SUN, speed)
    assert shown + " in the zodiac than the Sun" in fact, fact


def test_1_20_6_reads_no_easternness_for_the_lights(engine):
    for light in ("Sun", "Moon"):
        with pytest.raises(ValueError):
            engine["sahl_eastern_1_20_6"](light, 100.0, SUN, 1.0)


def test_rel_5_2_pin_stands_and_a_retrograde_venus_does_not_keep_the_sun(engine):
    """REL-5-2's chart: day, Scorpio rising, the Sun at 15 Virgo in the
    eleventh with no lord of his degree looking; Venus (bound, day triplicity
    and face of 15 Virgo) in Leo holds a share at the Ascendant's degree.
    Direct and 35 degrees earlier, she is eastern by 1.22, 7 and house-master
    by 1.20, 6. Retrograde at the same place she is not ("direct in course"),
    so 1.20, 6 does not reach her and the Sun's row says so."""
    data, cusps = _chart(225.0, Sun=SUN, Venus=130.0, Mercury=145.0)
    r = engine["sahl_releaser"](data, 225.0, cusps, "Diurnal", 15.0, 15.0, 15.0)
    sun = next(c for c in r["candidates"] if c["Candidate"] == "the Sun")
    assert r["releaser"] == "the Sun" and r["house_master"] == "Venus", r["verdict"]
    assert "is eastern with a share in the Ascendant (1.22, 7: direct, 35.0° earlier in the zodiac than the Sun" in sun["Verdict"]
    assert r["ranking"][0]["Rank"].startswith("house-master by 1.20, 6: eastern (1.22, 7: direct, 35.0° earlier"), r["ranking"]
    data, cusps = _chart(225.0, Sun=SUN, Venus=(130.0, -0.4), Mercury=145.0)
    r = engine["sahl_releaser"](data, 225.0, cusps, "Diurnal", 15.0, 15.0, 15.0)
    sun = next(c for c in r["candidates"] if c["Candidate"] == "the Sun")
    assert r["releaser"] != "the Sun", r["verdict"]
    assert ("Venus, its bound lord, holds a share in the Ascendant but is not eastern (1.22, 7: retrograde, 35.0° "
            "earlier in the zodiac than the Sun; it asks direct and 12° or more earlier), so 1.20, 6 does not reach it"
            ) in sun["Verdict"], sun["Verdict"]


def test_an_evening_venus_is_western_not_eastern_by_1_22_7_and_8(engine):
    """REL-5-2's chart with Venus at 185 (5 Libra), direct, 20 degrees later in
    the zodiac than the Sun: in aversion to him, with her share at the
    Ascendant's degree. Ruling 56 (owner, 2026-10-06; reading (c) of the blind
    reading S122): 1.22, 7's "or in front of the Sun ([he being] in the west)"
    names the evening side ("in front of the Sun" is a later degree than the
    Sun throughout Sahl I -- Fifty Aphorisms #42, 82 with fn 49, Sahl I p. 86;
    "he" is the Sun); the 12° 7 calls eastern is the morning's, and on the
    evening side 1.22, 8 makes an inferior "western [risers]" at 15° (Sahl I
    Figure 54; BA II.2, PN I p. 21). So she is not eastern for 1.20, 6, it does
    not keep the Sun, and the day chart ends with no releaser."""
    assert engine["sahl_eastern_1_20_6"]("Venus", 185.0, SUN, 1.2) == (
        False, "1.22, 7: direct, 20.0° later in the zodiac than the Sun; it asks direct and 12° or more earlier", False)
    data, cusps = _chart(225.0, Sun=SUN, Venus=(185.0, 1.2), Mercury=145.0)
    r = engine["sahl_releaser"](data, 225.0, cusps, "Diurnal", 15.0, 15.0, 15.0)
    assert r["releaser"] is None and r["house_master"] is None, r["verdict"]
    sun = next(c for c in r["candidates"] if c["Candidate"] == "the Sun")["Verdict"]
    assert sun.startswith("house 11, but no lord of its bound, house, exaltation, triplicity or face looks at it"), sun
    assert "1.20, 6" not in sun and "Venus" not in sun, sun


def test_mars_below_eighteen_does_not_keep_the_meeting(engine):
    """A day chart, Aries rising (Mars its house lord, so he holds a share at
    the Ascendant's degree); the Sun at 22 Sagittarius in the ninth, falling;
    the meeting at 5 Scorpio in the eighth, one of 1.15, 6's places, its
    lords Mars (bound, house, face) and Venus (water's day triplicity lord),
    both in Sagittarius, in aversion to it. Mars 16 degrees earlier in the
    zodiac than the Sun is not eastern by 1.22, 3 (18), so 1.20, 6 does not
    keep the meeting; 20 degrees earlier he is, and he is its house-master."""
    sun = 262.0
    for before, kept in ((16.0, False), (20.0, True)):
        data, cusps = _chart(5.0, Sun=sun, Mars=(sun - before, 0.7), Venus=250.0, Mercury=275.0, Moon=100.0,
                             Jupiter=120.0, Saturn=60.0)
        assert [p for _r, p in engine["_sahl_dignity_lords"](215.0, "Diurnal")] == ["Mars", "Mars", "Venus", "Mars"]
        r = engine["sahl_releaser"](data, 5.0, cusps, "Diurnal", 15.0, 215.0, 15.0)
        sun_row, meeting = (next(c for c in r["candidates"] if c["Candidate"] == label)["Verdict"]
                            for label in ("the Sun", "the meeting (the last New Moon)"))
        assert "falling" in sun_row, sun_row
        if kept:
            assert r["releaser"] == "the meeting (the last New Moon)" and r["house_master"] == "Mars", (before, r["verdict"])
            assert ("Mars, its bound lord, is eastern with a share in the Ascendant (1.22, 3: direct, 20.0° earlier in the "
                    "zodiac than the Sun; it asks 18° or more earlier, not retrograde (1.22, 5)) -- house-master by 1.20, 6"
                    ) in meeting, meeting
        else:
            assert r["releaser"] != "the meeting (the last New Moon)", (before, r["verdict"])
            assert ("Mars, its bound lord, holds a share in the Ascendant but is not eastern (1.22, 3: direct, 16.0° "
                    "earlier in the zodiac than the Sun; it asks 18° or more earlier, not retrograde (1.22, 5)), so 1.20, 6 "
                    "does not reach it") in meeting, meeting


def test_the_releaser_page_states_the_rule_with_1_22s_sentences():
    at = make_app(date="1240-05-23", page="releaser")
    at.run(timeout=300)
    assert_no_exception(at, "releaser")
    text = " ".join(str(m.value) for m in at.main.markdown)
    assert "For the five planets, \"eastern\" in 1.20, 6 is read by those degrees, as Sahl writes them" in text
    for quoted in ("then they are considered to be eastern ... but if they were less than that, they will not be fit",
                   "he does not easternize until there are 18° between him and the Sun",
                   "Venus and Mercury are eastern [when] direct in course before rising"):
        assert quoted in text, quoted
    assert "so a retrograde or stationary Venus or Mercury is not eastern here" in text
    # the side 1.22, 7's parenthesis names, as ruling 56 reads it (the evening side; western there by 1.22, 8)
    assert ("1.22, 7's \"or in front of the Sun ([he being] in the west)\" names the evening side: in Sahl I \"in front "
            "of the Sun\" is a later degree than the Sun") in text
    assert "with fn 49: \"in a later degree than the Sun, so as to set after him\", Sahl I p. 86), and \"he\" is the Sun" in text
    assert ("for the evening side 1.22, 8 gives 15°: \"if there were 15° between them and the Sun, they will have gone out "
            "of the rays and become western [risers]\" (Sahl I pp. 305-306, with Sahl I Figure 54), as BA II.2 has 12° "
            "\"in the dawn rising\" and 15° \"in the west\" (PN I p. 21). So a Venus or Mercury later in the zodiac than "
            "the Sun is western, not eastern, for 1.20, 6.") in text
    assert "this app's reading, so a Venus or Mercury later" not in text and "is read here on the morning side" not in text
    assert ("Nor is Saturn, Jupiter or Mars gone retrograde: \"[once eastern], the stars will increase in power and be "
            "fit until they go retrograde: for when they go retrograde they are corrupted\" (1.22, 5)") in text
    assert "is not read into" not in text and "they will not be fit at that time to be the house-master" in text
    assert "in 1.20, 7-34 (the house-master's years) it is read by the side of the Sun" in text


def test_a_retrograde_superior_past_its_figure_is_not_eastern_for_1_20_6(engine):
    """Ruling 44: 1.22, 5 -- "[once eastern], the stars will increase in power
    and be fit until they go retrograde: for when they go retrograde they are
    corrupted" (Sahl I p. 305) -- is read into 1.20, 6. A day chart, Aries
    rising (5 Aries: Jupiter its bound lord, so he holds a share at the
    Ascendant's degree); the Sun at 10 Sagittarius in the ninth, falling; the
    meeting at 16 Aquarius in the eleventh, one of 1.15, 6's places, its lords
    Jupiter (bound), Saturn (house, air's day triplicity lord) and Mercury
    (face), none looking at it: Jupiter in Cancer, Saturn in Pisces, Mercury
    in Capricorn. Jupiter is 150 degrees earlier in the zodiac than the Sun,
    well past 1.22, 1's 6. Retrograde, he is not eastern for 1.20, 6 and does
    not keep the meeting; direct at the same place, he does."""
    for speed, kept in ((-0.1, False), (0.1, True)):
        data, cusps = _chart(5.0, Sun=250.0, Jupiter=(100.0, speed), Saturn=(345.0, 0.03), Mercury=(272.0, 1.2),
                             Venus=230.0, Mars=40.0, Moon=60.0)
        assert [p for _r, p in engine["_sahl_dignity_lords"](316.0, "Diurnal")] == ["Jupiter", "Saturn", "Saturn",
                                                                                    "Mercury"]
        r = engine["sahl_releaser"](data, 5.0, cusps, "Diurnal", 15.0, 316.0, 15.0)
        sun_row, meeting = (next(c for c in r["candidates"] if c["Candidate"] == label)["Verdict"]
                            for label in ("the Sun", "the meeting (the last New Moon)"))
        assert "falling" in sun_row, sun_row
        if kept:
            assert r["releaser"] == "the meeting (the last New Moon)" and r["house_master"] == "Jupiter", r["verdict"]
        else:
            assert r["releaser"] != "the meeting (the last New Moon)", r["verdict"]
            assert ("Jupiter, its bound lord, holds a share in the Ascendant but is not eastern (1.22, 1: retrograde, "
                    "150.0° earlier in the zodiac than the Sun; it asks 6° or more earlier, not retrograde (1.22, 5))"
                    ) in meeting, meeting
