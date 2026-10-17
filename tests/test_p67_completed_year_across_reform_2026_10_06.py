"""Lane P67 (wave 5): the completed year across the Gregorian reform.

The civil age counts completed civil anniversaries (PN IV II.3, 1, PN IV p. 185:
"for every year the native has completed, cast out one sign from it"). No source
anticipates the reform of 1582, and the owner's ruling settles how the count
crosses it: the age counts on canonical civil dates -- the digits a day is
written in by its own epoch, Julian before 1582-10-15 and Gregorian from it --
and an anniversary whose digits fall in the reform gap (1582-10-05 to 1582-10-14,
digits the parser reads as Julian, so each names the Julian Day of a Gregorian
day ten days later) is treated as 29 February is in a common year: the first
canonical day the count turns. A birth on 1581-10-10 completes its first year
on 1582-10-15. One day carries one age, whichever spelling of it is given, and
the Age and Date targets agree.

Before this lane the count compared the digits as typed: 1582-10-05 (the Julian
Day of 1582-10-15) counted 0 and 1582-10-15 counted 1, and Age 1 for a birth on
1581-10-10 chose 1582-10-10, five days after the first canonical day of the
age (the second hostile pass's R2-06).

The parser's reading of gap digits as Julian is not changed here; its two
pinned tests stand as they are.

The expectations below are written out literally or counted here from the
Julian Day, not read from the engine's own tables.
"""
import random

import pytest

from conftest import assert_no_exception, find_table, make_app

DEPTHS = ("Course text", "Course text and supplement")
REFORM_JD = 2299160.5      # 1582-10-15 00:00 UT, the first Gregorian day


def _canonical(engine, cd):
    """The digits the day is written in by its own epoch, counted here from
    the Julian Day through the ephemeris's own calendar conversion."""
    swe = engine["swe"]
    jd = cd.jd()
    cal = swe.GREG_CAL if jd >= REFORM_JD else swe.JUL_CAL
    y, m, d, _ = swe.revjul(jd, cal)
    return (int(y), int(m), int(d))


def _gap_days(engine):
    CD = engine["CivilDate"]
    return [CD(1582, 10, d) for d in range(5, 15)]


# --- the pins --------------------------------------------------------------

def test_a_birth_on_1581_10_10_completes_its_first_year_on_1582_10_15(engine):
    CD = engine["CivilDate"]
    got = engine["pn4_birthday"](CD(1581, 10, 10), 1)
    assert got == CD(1582, 10, 15), got
    assert got.calendar_name() == "Gregorian"


def test_one_day_carries_one_age_whichever_spelling_is_given(engine):
    CD, completed = engine["CivilDate"], engine["pn4_completed_years"]
    gap = _gap_days(engine)
    assert len(gap) == 10
    # Each gap spelling is the Julian Day of the Gregorian day ten days on.
    assert [round(g.jd() - CD(1582, 10, g.day + 10).jd(), 6) for g in gap] == [0.0] * 10
    births = (CD(1581, 10, 10), CD(1581, 10, 5), CD(1581, 10, 14), CD(1581, 10, 16), CD(1500, 10, 12),
              CD(1582, 10, 4), CD(1582, 10, 10), CD(1582, 10, 15), CD(1581, 10, 20))
    for b in births:
        for g in gap:
            twin = CD(1582, 10, g.day + 10)
            assert completed(b, g) == completed(b, twin), (b, g, twin)
    # and the birth's own spelling, where it is a gap spelling
    for t in (CD(1583, 10, 15), CD(1583, 10, 19), CD(1583, 10, 20), CD(1583, 10, 25), CD(1600, 1, 1)):
        assert completed(CD(1582, 10, 10), t) == completed(CD(1582, 10, 20), t), t
    # 1582-10-10 spelled as typed is 1582-10-20: a birth on 1581-10-10 is one year old on it.
    assert completed(CD(1581, 10, 10), CD(1582, 10, 10)) == 1


@pytest.mark.parametrize("birth", [(1581, 10, 5), (1581, 10, 14)], ids=["1581-10-05", "1581-10-14"])
def test_births_whose_anniversary_falls_in_the_gap(engine, birth):
    CD, completed, birthday = engine["CivilDate"], engine["pn4_completed_years"], engine["pn4_birthday"]
    b = CD(*birth)
    assert birthday(b, 1) == CD(1582, 10, 15)
    # Counted here, day by day on the Julian Day: the count over canonical days
    # never falls, and the first day it reads 1 is the first Gregorian day.
    counts = []
    for jd in range(int(CD(1582, 9, 1).jd() - 0.5), int(CD(1582, 11, 30).jd() - 0.5)):
        day = CD(*_canonical(engine, CD.from_jd(jd + 0.5)))
        counts.append((day, completed(b, day)))
    assert len(counts) == 80      # 1582-09-01 to 1582-11-29, the ten gap days absent
    assert all(a[1] <= z[1] for a, z in zip(counts, counts[1:]))
    first = next(day for day, n in counts if n == 1)
    assert first == CD(1582, 10, 15), first
    assert first == birthday(b, 1)


@pytest.mark.parametrize("depth", DEPTHS)
def test_age_mode_and_date_mode_agree_on_the_timing_page(tmp_path, monkeypatch, depth):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    seen = {}
    for mode, key, value in (("Age", "_target_age", 1), ("Date", "_target_date", "1582-10-15")):
        at = make_app(date="1581-10-10", page="timing")
        at.session_state["_reading_depth"] = depth
        at.session_state["_target_mode"] = mode
        at.session_state[key] = value
        at.run()
        assert_no_exception(at, f"{mode} {value}")
        rev = find_table(at, "The revolution of the year").value
        seen[mode] = (at.session_state["_target_date"], int(at.session_state["_target_age"]),
                      [frame.value.to_dict("records") for frame in at.main.dataframe],
                      dict(zip(rev["Item"], rev["Value"])))
    age, date = seen["Age"], seen["Date"]
    assert (age[0], age[1]) == ("1582-10-15", 1) == (date[0], date[1]), (age[:2], date[:2])
    assert age[3]["Count of the year"].startswith("1 completed civil years")
    assert age[3] == date[3]
    assert age[2] == date[2]


# --- the guards: what the ruling does not move --------------------------------

# (birth, age, the anniversary as written out by hand)
FEB29 = (
    ((1300, 2, 29), 1, "1301-03-01"), ((1300, 2, 29), 2, "1302-03-01"), ((1300, 2, 29), 4, "1304-02-29"),
    ((1300, 2, 29), 282, "1582-03-01"), ((1300, 2, 29), 283, "1583-03-01"), ((1300, 2, 29), 284, "1584-02-29"),
    ((1300, 2, 29), 300, "1600-02-29"), ((1300, 2, 29), 400, "1700-03-01"),
    ((1580, 2, 29), 1, "1581-03-01"), ((1580, 2, 29), 2, "1582-03-01"), ((1580, 2, 29), 3, "1583-03-01"),
    ((1580, 2, 29), 4, "1584-02-29"),
    ((1904, 2, 29), 1, "1905-03-01"), ((1904, 2, 29), 4, "1908-02-29"), ((1904, 2, 29), 96, "2000-02-29"),
    ((1904, 2, 29), 100, "2004-02-29"),
    ((2000, 2, 29), 1, "2001-03-01"), ((2000, 2, 29), 4, "2004-02-29"), ((2000, 2, 29), 100, "2100-03-01"),
)


def test_29_february_births_are_unchanged(engine):
    CD, completed, birthday = engine["CivilDate"], engine["pn4_completed_years"], engine["pn4_birthday"]
    assert [str(birthday(CD(*b), a)) for b, a, _ in FEB29] == [text for _, _, text in FEB29]
    for birth, a, text in FEB29:
        b, day = CD(*birth), birthday(CD(*birth), a)
        assert completed(b, day) == a, (birth, a, text)
        assert completed(b, CD.from_jd(day.jd() - 1)) == a - 1, (birth, a, text)


def test_ordinary_anniversaries_are_unchanged(engine):
    """A seeded sample of births and ages whose dates and anniversaries are
    not gap spellings: the anniversary is the same month and day, the count
    turns on it and not the day before, and the count of a target is the
    digit comparison written out here."""
    CD, completed, birthday = engine["CivilDate"], engine["pn4_completed_years"], engine["pn4_birthday"]
    valid = engine["civil_is_valid"]
    rng = random.Random(67)

    def gap(y, m, d):
        return (y, m) == (1582, 10) and 5 <= d <= 14

    sample = []
    while len(sample) < 400:
        y, m, d = rng.randint(1, 2900), rng.randint(1, 12), rng.randint(1, 28)
        a = rng.choice((0, 1, 2, 17, 42, rng.randint(0, 99)))
        ty, tm, td = y + rng.randint(0, 120), rng.randint(1, 12), rng.randint(1, 31)
        if gap(y, m, d) or gap(y + a, m, d) or y + a > 2999 or not valid(ty, tm, td) or gap(ty, tm, td):
            continue
        sample.append(((y, m, d), a, (ty, tm, td)))
    assert len(sample) == 400
    for (y, m, d), a, (ty, tm, td) in sample:
        b = CD(y, m, d)
        day = birthday(b, a)
        assert day == CD(y + a, m, d), (b, a, day)
        assert completed(b, day) == a
        assert completed(b, CD.from_jd(day.jd() - 1)) == max(a - 1, 0), (b, a)
        want = max(ty - y - ((tm, td) < (m, d)), 0)
        assert completed(b, CD(ty, tm, td)) == want, (b, (ty, tm, td))


# --- after the blind check: the Chronocrator Matrix, and the birth's spelling -----

# (birth, target as typed, the same two days spelled canonically): each pair is one
# birth and one target day, so the two give one civil age and one lord of the year.
TWINS = (
    ((1581, 10, 10), (1582, 10, 5), (1581, 10, 10), (1582, 10, 15)),
    ((1581, 10, 20), (1582, 10, 10), (1581, 10, 20), (1582, 10, 20)),
    ((1582, 10, 10), (1583, 10, 15), (1582, 10, 20), (1583, 10, 15)),
)


@pytest.mark.parametrize("typed_birth, typed_target, birth, target", TWINS,
                         ids=["target-1582-10-05", "target-1582-10-10", "birth-1582-10-10"])
def test_the_matrix_profection_counts_the_civil_age_for_either_spelling(engine, typed_birth, typed_target, birth, target):
    CD, completed, lords = engine["CivilDate"], engine["pn4_completed_years"], engine["calculate_time_lords"]
    asc = 315.0      # 15 Aquarius: the profected sign is counted here from the age
    signs = ("Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius",
             "Capricorn", "Aquarius", "Pisces")
    age = completed(CD(*birth), CD(*target))
    assert age == completed(CD(*typed_birth), CD(*typed_target))
    typed = lords(asc, CD(*typed_birth), CD(*typed_target))[0]
    canon = lords(asc, CD(*birth), CD(*target))[0]
    assert typed == canon, (typed, canon)
    assert canon["Details"] == f"Age {age} (1 Sign / Year)"
    assert canon["Active Point"] == signs[(10 + age) % 12]


@pytest.mark.parametrize("typed_birth, typed_target, birth, target", TWINS,
                         ids=["target-1582-10-05", "target-1582-10-10", "birth-1582-10-10"])
def test_the_matrix_on_the_page_agrees_with_the_header(tmp_path, monkeypatch, typed_birth, typed_target, birth, target):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    seen = []
    for b, t in ((typed_birth, typed_target), (birth, target)):
        at = make_app(date="%04d-%02d-%02d" % b, page="fardar")
        at.session_state["_reading_depth"] = DEPTHS[1]
        at.session_state["_target_mode"] = "Date"
        at.session_state["_target_date"] = "%04d-%02d-%02d" % t
        at.run()
        assert_no_exception(at, f"{b} {t}")
        age = int(at.session_state["_target_age"])
        header = [m.value for m in at.main.markdown if "completed" in m.value and "-- age **" in m.value]
        assert len(header) == 1, header
        assert f"-- age **{age}** completed" in header[0]
        matrix = find_table(at, "Chronocrator Matrix").value
        row = matrix[matrix["Technique"] == "Annual Profection"].iloc[0]
        assert row["Details"] == f"Age {age} (1 Sign / Year)", (b, t, age, row["Details"])
        seen.append((age, row["Active Point"], row["Active Ruler"]))
    assert seen[0] == seen[1], seen


def test_a_birth_typed_in_the_gap_has_its_twin_s_anniversaries(engine):
    CD, birthday, completed = engine["CivilDate"], engine["pn4_birthday"], engine["pn4_completed_years"]
    typed, twin = CD(1582, 10, 10), CD(1582, 10, 20)
    assert birthday(typed, 1) == CD(1583, 10, 20)
    assert birthday(typed, 1) == birthday(twin, 1)
    assert completed(typed, birthday(typed, 1)) == 1
