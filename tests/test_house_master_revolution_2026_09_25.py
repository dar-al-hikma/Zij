"""Sahl, On Nativities 1.23, 3-4 (Sahl I p. 308): the house-master in the
revolution of the year its direction points out.

- 1.23, 4 asks of the revolution only whether the governor is burned there
  ("and then the governor is burned at the revolution"), and, only "if it is
  not burned at the revolution", whether "it is burned in one of the stakes
  of the Ascendant of the year", which Dykes's fn 183 reads as "later in the
  year". No sentence of 1.23, 2-4 asks whether an infortune shares the
  house-master's sign in the revolution: that row is gone, from the table,
  the page and both exports. 1.23, 10 asks the governor's look at the
  Ascendant of the year only jointly with the two lords' burning and the
  year's lord's own look, and only when nothing of 2-9 holds: no row shows
  that look alone.
- "Burned" is the app's Burned band, a declared operational reading: its
  widths Gr. Intr. VII.2's, Sahl's one-degree heart excluded (The
  Introduction Ch. 3, 87; Fifty Aphorisms #40, 79) -- the reading 1.21, 13
  already carries for the house-master's years. Under the rays is not burned.
- 4 opens "if your calculation of this [by direction] and the revolution
  both indicate burning": both its questions are asked only in a revolution's
  year that the house-master's direction reaches at the degree of burning
  (the Sun's degree), the year matched by the revolution's age (the
  completed solar returns) against the direction's "In the year of age";
  in any other year the rows say 4 is not asked, and why (owner's ruling).
- The year searched runs from this revolution to the next: its end is
  pinned by a spell still burned there and by one in its last days.
- 1.23, 2's natal look "relative to burning" is the ranking's "Under the
  rays" cell, now shown for a releaser that is its own house-master too.

Every expected value below was worked out from the sentence and the reading
before the engine was run: the ephemeris facts are the Sun's conjunctions
with Saturn (12 March 2025 near 22 Pisces; 25 May 2001 near 4 Gemini) and the New
Moons of June 2024 to May 2025 and of 30 May 2022.
"""
from datetime import datetime

import pytest

from conftest import assert_no_exception, make_app, FLORENCE

REMOVED = "With an infortune in its sign"
NOW = "Burned at the revolution"
LATER = "Burned later in the year, in a stake of the Ascendant of the year"
LOOK = "Looking at the Ascendant of the year"
FACTS = [NOW, LATER]
# A year whose direction reaches the degree of burning: 1.23, 4 is asked.
BURNING = [{"Target": "the Sun's degree (burning)", "Degree": "-", "Arc (years)": "-"}]


def _chart(engine, when):
    return engine["calculate_traditional_chart"](when, *FLORENCE)


def _reads(rows, fact):
    return next(r["Reads"] for r in rows if r["Fact"] == fact)


@pytest.fixture(scope="module")
def year_2024(engine):
    """A revolution cast at 2024-06-01 12:00 UT, its year running a mean
    tropical year to the next; the natal chart any other."""
    sr = _chart(engine, datetime(2024, 6, 1, 12))
    natal = _chart(engine, datetime(1990, 6, 1, 12))
    return natal, sr, sr["julian_day"] + 365.2422


@pytest.fixture(scope="module")
def natal_1990(engine):
    return _chart(engine, datetime(1990, 6, 1, 12))


def _revolution_year(engine, natal, age):
    """The revolution opening `age` for the 1990 chart, and the next one."""
    jd0, sun0 = natal["julian_day"], natal["planetary_data"]["Sun"]["longitude"]
    jd_sr = engine["pn4_solar_revolution_jd"](jd0, sun0, age)
    return (engine["calculate_traditional_chart_jd"](jd_sr, *FLORENCE),
            engine["pn4_solar_revolution_jd"](jd0, sun0, age + 1))


# ---------------------------------------------------------------- the table

def test_the_table_is_three_facts_and_the_sign_sharing_row_is_gone(engine, year_2024):
    natal, sr, jd_next = year_2024
    rows = engine["sahl_house_master_in_revolution"]("Saturn", natal, sr, BURNING, jd_next=jd_next)
    assert [r["Fact"] for r in rows] == ["Saturn in the revolution"] + FACTS
    assert [r["Source"] for r in rows] == ["1.23, 3", "1.23, 4", "1.23, 4; fn 183"]
    assert not any("infortune" in r["Fact"] or r["Fact"] == LOOK or "10" in r["Source"] for r in rows)


@pytest.mark.parametrize("delta,expected", [
    (4.0, "yes: Burned, western, 4.0 from the Sun"),                 # inside Saturn's 6
    (-4.0, "yes: Burned, eastern, 4.0 from the Sun"),
    (10.0, "no: Under the rays, western, 10.0 from the Sun"),         # under the rays is not burned
    (0.5, "no: Cazimi, in the heart, western, 0.5 from the Sun"),    # Sahl's one degree
    (40.0, "no: 40.0 from the Sun, western"),
])
def test_burned_at_the_revolution_is_the_burned_band_only(engine, year_2024, delta, expected):
    natal, sr, jd_next = year_2024
    rev = {p: dict(v) for p, v in sr["planetary_data"].items()}
    rev["Sun"]["longitude"], rev["Saturn"]["longitude"] = 100.0, 100.0 + delta
    rows = engine["sahl_house_master_in_revolution"]("Saturn", natal, dict(sr, planetary_data=rev), BURNING, jd_next=jd_next)
    assert _reads(rows, NOW) == expected
    # 4's second case is asked only "if it is not burned at the revolution"
    assert (_reads(rows, LATER) == "not asked: the first case holds, burned at the revolution") == expected.startswith("yes")


@pytest.mark.parametrize("ascendant,where", [
    (75.0, 'yes (UT dates): 2025-03-05 to 2025-03-19 in Pisces, house 10 -- a stake'),
    (345.0, 'yes (UT dates): 2025-03-05 to 2025-03-19 in Pisces, house 1 -- a stake -- the Ascendant itself, "worse"'),
    (45.0, 'no, burned outside the stakes (UT dates): 2025-03-05 to 2025-03-19 in Pisces, house 11'),
])
def test_burned_later_in_the_year_in_a_stake_of_the_year(engine, year_2024, ascendant, where):
    """Saturn is 83 degrees from the Sun at the revolution; the Sun reaches
    him on 12 March 2025 near 22 Pisces, and he is within 6 degrees from
    about the 5th to the 19th, the heart between. Pisces is the tenth from a
    Gemini Ascendant of the year, the first from a Pisces one, the eleventh
    from a Taurus one."""
    natal, sr, jd_next = year_2024
    rows = engine["sahl_house_master_in_revolution"]("Saturn", natal, dict(sr, ascendant=ascendant), BURNING, jd_next=jd_next)
    assert _reads(rows, NOW) == "no: 82.7 from the Sun, eastern"
    assert _reads(rows, LATER) == where


def test_not_burned_in_the_year(engine, year_2024):
    """Mars meets the Sun in November 2023 and January 2026, neither in
    this year."""
    natal, sr, jd_next = year_2024
    rows = engine["sahl_house_master_in_revolution"]("Mars", natal, sr, BURNING, jd_next=jd_next)
    assert _reads(rows, LATER) == "no: not burned between this revolution and the next"


def test_the_moon_is_burned_once_a_month_the_heart_not_splitting_a_spell(engine, year_2024):
    """Thirteen New Moons, 6 June 2024 to 27 May 2025: one entry each,
    though the heart parts each into two spells of the Burned phase."""
    _natal, sr, jd_next = year_2024
    spells = engine["sahl_burnings_in_year"]("Moon", sr["julian_day"], jd_next)
    assert len(spells) == 13
    assert [f"{engine['pn4_datetime_from_jd'](s['start']):%Y-%m}" for s in spells][:2] == ["2024-06", "2024-07"]
    assert all(s["end"] - s["start"] < 2.5 for s in spells)


def test_a_burning_under_way_at_the_revolution_is_the_first_case_not_the_second(engine):
    """At 2025-03-08 Saturn is about 3.4 degrees ahead of the Sun, which is
    closing on him (western: he sets after the Sun), burned at the
    revolution: the first case holds, and the second is not asked."""
    natal = _chart(engine, datetime(1990, 6, 1, 12))
    sr = _chart(engine, datetime(2025, 3, 8, 12))
    rows = engine["sahl_house_master_in_revolution"]("Saturn", natal, sr, BURNING, jd_next=sr["julian_day"] + 365.2422)
    assert _reads(rows, NOW) == "yes: Burned, western, 3.4 from the Sun"
    assert _reads(rows, LATER) == "not asked: the first case holds, burned at the revolution"
    # and the search itself leaves out the rest of that burning, across the heart
    spells = engine["sahl_burnings_in_year"]("Saturn", sr["julian_day"], sr["julian_day"] + 365.2422)
    assert spells == []


def test_in_the_heart_at_the_revolution_then_burned_is_later(engine):
    """At the conjunction itself Saturn is in the heart -- not burned -- and
    the burning that follows it is a burning after the revolution."""
    natal = _chart(engine, datetime(1990, 6, 1, 12))
    sr = _chart(engine, datetime(2025, 3, 12, 12))
    rows = engine["sahl_house_master_in_revolution"]("Saturn", natal, dict(sr, ascendant=75.0),
                                                     BURNING, jd_next=sr["julian_day"] + 365.2422)
    assert _reads(rows, NOW).startswith("no: Cazimi, in the heart")
    assert _reads(rows, LATER).startswith("yes (UT dates): 2025-03-1") and _reads(rows, LATER).endswith(
        "to 2025-03-19 in Pisces, house 10 -- a stake")


def test_the_sun_as_house_master_is_not_read_for_burning(engine, year_2024):
    natal, sr, jd_next = year_2024
    rows = engine["sahl_house_master_in_revolution"]("Sun", natal, sr, BURNING, jd_next=jd_next)
    assert [r["Fact"] for r in rows] == ["Sun in the revolution"] + FACTS
    assert _reads(rows, NOW) == _reads(rows, LATER) == "not read: the house-master is the Sun"


@pytest.mark.parametrize("planet,this_year", [
    ("Sun", BURNING),                               # not read: the house-master is the Sun
    ("Saturn", None),                               # not asked: the direction is refused
    ("Saturn", []),                                 # not asked: no target this year
    ("Saturn", [{"Target": "Mars's body"}]),        # not asked: an infortune only
])
def test_the_later_row_is_fn_183s_reading_in_every_branch(engine, year_2024, planet, this_year):
    """"Later in the year" is fn 183's reading of 4's second case, so the row
    names it wherever it stands, asked or not."""
    natal, sr, jd_next = year_2024
    rows = engine["sahl_house_master_in_revolution"](planet, natal, sr, this_year, jd_next=jd_next)
    assert [r["Source"] for r in rows if r["Fact"] == LATER] == ["1.23, 4; fn 183"]


# ---------------------------------------------------------------- the year's end

def test_a_spell_still_burned_at_the_next_revolution(engine, natal_1990):
    """Age 10 of the 1990 chart: the revolution of 31 May 2000 (its
    Ascendant Aquarius) to that of 1 June 2001. The Sun reaches Saturn near
    4 Gemini on 25 May 2001, so Saturn is within 6 degrees from about 18
    May, a week before, through the next revolution and past it (the Sun
    gains under a degree a day): Gemini is the fifth from Aquarius."""
    sr, jd_next = _revolution_year(engine, natal_1990, 10)
    rows = engine["sahl_house_master_in_revolution"]("Saturn", natal_1990, sr, BURNING, jd_next=jd_next)
    assert _reads(rows, NOW) == "no: 17.6 from the Sun, eastern"
    assert _reads(rows, LATER) == ("no, burned outside the stakes (UT dates): 2001-05-18 to past the next "
                                   "revolution in Gemini, house 5")


def test_a_spell_in_the_last_days_of_the_year(engine, natal_1990):
    """Age 31 of the 1990 chart: the revolution of 1 June 2021 (its
    Ascendant Pisces) to that of 1 June 2022, 05:43 UT. The New Moon of 30
    May 2022, near 9 Gemini, burns the Moon from the evening of the 29th to
    the 31st, two days before the year ends: Gemini is the fourth from
    Pisces, a stake."""
    sr, jd_next = _revolution_year(engine, natal_1990, 31)
    rows = engine["sahl_house_master_in_revolution"]("Moon", natal_1990, sr, BURNING, jd_next=jd_next)
    later = _reads(rows, LATER)
    assert later.startswith("yes (UT dates): 2021-06-")
    assert later.endswith("; 2022-04-30 to 2022-05-01 in Taurus, house 3; "
                          "2022-05-29 to 2022-05-31 in Gemini, house 4 -- a stake")
    assert later.count(" to ") == 13


# ---------------------------------------------------------------- 1.23, 2's natal look at burning

@pytest.mark.parametrize("planet,offset,cell", [
    ("Moon", 40.0, "no"),
    ("Moon", 10.0, 'Under the rays: "deceptive, subtractive, corrupting" (1.20, 5)'),
    ("Moon", 3.0, 'Burned: "deceptive, subtractive, corrupting" (1.20, 5)'),
    ("Sun", 0.0, "not read: the Sun"),
])
def test_the_releaser_that_is_its_own_house_master_shows_its_phase(engine, year_2024, planet, offset, cell):
    """1.16, 1-2: a luminary both releaser and house-master. Its ranking row
    carries the natal phase like every other lord's: the Moon 40 degrees
    from the Sun is not under the rays, at 10 she is (12 by default), at 3
    she is burned (6); the Sun has no phase of his own."""
    natal, _sr, _jd = year_2024
    data = {p: dict(v) for p, v in natal["planetary_data"].items()}
    data["Sun"]["longitude"] = 20.0
    data["Moon"]["longitude"] = 20.0 + offset
    rows = engine["_sahl_rank_house_master"]({"both_at_once": True, "self_planet": planet}, data, natal["houses"])
    assert rows[0]["Under the rays"] == cell


# ---------------------------------------------------------------- everywhere

def test_the_removed_rows_are_in_neither_source():
    from conftest import app_source, engine_source
    for gone in (REMOVED, LOOK, "1.23, 3-4 and 10"):
        assert gone not in engine_source() and gone not in app_source()


def _default_bundle(engine, target):
    """The default chart (1240-05-23, 14:30 local mean time, Florence): its
    house-master is Jupiter, directed to Saturn's square (right) at arc
    3.57, Mars's body at 24.38, the Sun's degree (burning) at 33.43 and
    Saturn's body at 86.44."""
    from datetime import date, timedelta
    c = engine["calculate_traditional_chart"](datetime(1240, 5, 23, 14, 30) - timedelta(hours=FLORENCE[1] / 15), *FLORENCE)
    return c, engine["pn4_timing_bundle"](c, *FLORENCE, date(1240, 5, 23), target, engine["PN4_MONTHLY_TURN_OPTIONS"][0])


# ---------------------------------------------------------------- 1.23, 4 gated on the direction

def test_four_is_asked_in_the_year_the_direction_reaches_burning(engine):
    """Age 33: the direction reaches the Sun's degree at arc 33.43, so the
    revolution of 23 May 1273 (its Ascendant Libra) is asked 4's questions.
    Jupiter stands 133 degrees from the Sun there, and the Sun reaches him
    in January 1274 in Aquarius, the fifth from Libra: no stake."""
    from datetime import date
    c, b = _default_bundle(engine, date(1273, 6, 15))
    assert b["house_master"] == "Jupiter" and b["cycle"] == 33
    assert [r["Target"] for r in b["hm_this_year"]] == ["the Sun's degree (burning)"]
    assert [r["Fact"] for r in b["hm_revolution"]] == ["Jupiter in the revolution"] + FACTS
    assert _reads(b["hm_revolution"], NOW) == "no: 133.0 from the Sun, eastern"
    assert _reads(b["hm_revolution"], LATER) == ("no, burned outside the stakes (UT dates): 1274-01-13 to "
                                                 "1274-01-29 in Aquarius, house 5")
    # the year searched is the bundle's own: this revolution to the next
    assert b["hm_revolution"] == engine["sahl_house_master_in_revolution"]("Jupiter", c, b["sr"], b["hm_this_year"],
                                                                           jd_next=b["jd_sr_next"])


@pytest.mark.parametrize("target,cycle,reached", [
    ((1243, 6, 15), 3, "Saturn's square (right)"),
    ((1264, 6, 15), 24, "Mars's body"),
])
def test_four_is_not_asked_where_the_direction_reaches_an_infortune_only(engine, target, cycle, reached):
    from datetime import date
    _c, b = _default_bundle(engine, date(*target))
    assert b["cycle"] == cycle and [r["Target"] for r in b["hm_this_year"]] == [reached]
    why = f"not asked: this year the direction reaches {reached}, not the degree of burning"
    assert [r["Fact"] for r in b["hm_revolution"]] == ["Jupiter in the revolution"] + FACTS
    assert _reads(b["hm_revolution"], NOW) == _reads(b["hm_revolution"], LATER) == why
    # 1.23, 3's place is kept in every year
    assert b["hm_revolution"][0]["Source"] == "1.23, 3" and "(natal 20° Ari 52')" in b["hm_revolution"][0]["Reads"]


def test_four_is_not_asked_in_a_year_with_no_target(engine):
    from datetime import date
    _c, b = _default_bundle(engine, date(1270, 6, 1))
    assert b["cycle"] == 30 and b["hm_this_year"] == []
    assert _reads(b["hm_revolution"], NOW) == _reads(b["hm_revolution"], LATER) == \
        "not asked: the direction reaches no target in this year"
    assert _reads(b["hm_revolution"], "Jupiter in the revolution") == "11° Lib 07' (natal 20° Ari 52')"


def test_the_year_is_the_revolutions_age_not_the_civil_age(engine):
    """At noon UT on the 33rd birthday, 1273-05-23, the 33rd revolution
    (13:09 UT) has not come: the revolution in force opens age 32, which
    the direction does not reach, so 4 is not asked; the next day it is."""
    from datetime import date
    _c, b = _default_bundle(engine, date(1273, 5, 23))
    assert (b["age"], b["cycle"]) == (33, 32) and b["hm_this_year"] == []
    assert _reads(b["hm_revolution"], NOW) == "not asked: the direction reaches no target in this year"
    _c, b = _default_bundle(engine, date(1273, 5, 24))
    assert (b["age"], b["cycle"]) == (33, 33)
    assert _reads(b["hm_revolution"], NOW) == "no: 133.0 from the Sun, eastern"


@pytest.mark.parametrize("this_year,reads", [
    (None, "not asked: the direction is refused at this latitude"),
    ([], "not asked: the direction reaches no target in this year"),
    ([{"Target": "Mars's body"}, {"Target": "Saturn's opposition"}],
     "not asked: this year the direction reaches Mars's body, Saturn's opposition, not the degree of burning"),
    ([{"Target": "Mars's body"}, {"Target": "the Sun's degree (burning)"}], "no: 82.7 from the Sun, eastern"),
])
def test_two_targets_in_one_year_and_a_refused_direction(engine, year_2024, this_year, reads):
    natal, sr, jd_next = year_2024
    rows = engine["sahl_house_master_in_revolution"]("Saturn", natal, sr, this_year, jd_next=jd_next)
    assert _reads(rows, NOW) == reads


def _page(target):
    at = make_app(page="releaser")
    at.session_state["_target_date"] = target
    at.run(timeout=300)
    assert_no_exception(at, f"the releaser page, {target}")
    return at


@pytest.fixture(scope="module")
def releaser_1273():
    return _page("1273-06-15")


def test_the_page_draws_the_three_facts_and_not_the_removed_rows(releaser_1273):
    at = releaser_1273
    tables = [df.value for df in at.main.dataframe]
    cells = [str(v) for t in tables for v in t.astype(str).values.ravel()]
    assert not any(REMOVED in v or LOOK in v for v in cells)
    facts = next(t for t in tables if "Fact" in t.columns and NOW in list(t["Fact"]))
    assert list(facts["Fact"]) == ["Jupiter in the revolution"] + FACTS
    assert list(facts["Reads"])[1] == "no: 133.0 from the Sun, eastern"
    shown = [m.value for m in at.main.markdown]
    assert any(m.startswith("**The revolution's year (age 33) is one the direction points out:** the Sun's degree "
                            "(burning) at") and m.endswith("It reaches the degree of burning, so 1.23, 4 asks of the "
                                                            "revolution:") for m in shown)


@pytest.mark.parametrize("target,caption", [
    ("1270-06-01", "The revolution's year (age 30) is not one the direction points out, so 1.23, 4 is not asked. "
                   "The house-master in the revolution (1.23, 3):"),
    ("1264-06-15", "None of these is the degree of burning, so 1.23, 4 is not asked: it asks only \"if your "
                   "calculation of this [by direction] and the revolution both indicate burning\". The house-master "
                   "in the revolution (1.23, 3):"),
])
def test_the_page_says_when_four_is_not_asked(target, caption):
    at = _page(target)
    shown = [m.value for m in at.main.markdown]
    assert any(m.endswith(caption) for m in shown), caption
    facts = next(df.value for df in at.main.dataframe if "Fact" in df.value.columns and NOW in list(df.value["Fact"]))
    assert all(r.startswith("not asked: ") for r in list(facts["Reads"])[1:])


def test_the_page_notes_carry_the_readings(releaser_1273):
    at = releaser_1273
    text = " ".join(m.value for m in at.main.markdown)
    assert ("\"Burned\" is this app's Burned band, a declared operational reading and not a definition any "
            "sentence here supplies: its widths are Gr. Intr. VII.2's, and the heart it leaves out is Sahl's one "
            "degree (The Introduction Ch. 3, 87; Fifty Aphorisms #40, 79).") in text
    assert ("so both its questions are asked only in a revolution's year that the direction above reaches at the "
            "Sun's degree, the degree of burning") in text
    assert ("The year is matched by the revolution's age, the completed years it opens, against the direction's "
            "year of age, the completed years its arc falls in") in text
    assert "is asked only when the first does not hold" in text
    assert "is read with fn 183, \"burned in one of them *later* in the year\"" in text
    assert "its dates in UT" in text
    assert "no fact here reads harm by the infortunes" in text
    assert "10's look" not in text


def test_neither_export_carries_the_removed_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(page="sources")
    at.session_state["_target_date"] = "1273-06-15"
    at.run(timeout=300)
    assert_no_exception(at, "sources, 1273")
    md, page = at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]
    for text in (md, page):
        assert REMOVED not in text and LOOK not in text
        assert LATER in text and "1.23, 4; fn 183" in text and "1274-01-13 to 1274-01-29 in Aquarius, house 5" in text
