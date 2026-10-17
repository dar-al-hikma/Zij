"""Ruled lane H5 (the owner's ruling 6, Q9): the Year-over-root wheel follows
the image table.

PN IV I.6, 3 writes the image's points "so that all of them are in the
signs in which they are at the revolution of the year"; I.6, 6 adds the
endpoint of the distribution, the distributor and its partner, the lord of
the fardar and its divider, and the lord of the orb; fn 34 reads the
endpoint as "the very degree which the distribution had reached". The image
table already takes those time lords at the revolution's moment, as
indicators #2-#4 and the governor do. The ruling: the wheel's D/P/F/f
letters and its solid arc read them there too, and the legend says so.

Chart: the harness's default (1240-05-23 14:30 LMT Florence), target
1251-10-13 -- the 11th revolution, where the target's time lords (Venus
distributor, Jupiter partner, Venus / Mercury fardar, 21 Lib 00') and the
revolution's (Jupiter, Moon, Venus / Venus, 20 Lib 42') differ.
"""
from __future__ import annotations

import pytest

from conftest import make_app, assert_no_exception

TARGET = "1251-10-13"
FLORENCE = (43.7792, 11.2463)
BIRTH = (1240, 5, 23)


def _natal(engine):
    """The default chart (14:30 LMT Florence), as app.py casts it."""
    jd = engine["civil_local_to_jd_ut"](*BIRTH, 14.5, FLORENCE[1] / 15.0)
    return engine["calculate_traditional_chart_jd"](jd, *FLORENCE)


def _bundle(engine, target=(1251, 10, 13)):
    """The bundle as app.py computes it for the default chart (14:30 LMT) at `target`."""
    offset = FLORENCE[1] / 15.0
    jd = engine["civil_local_to_jd_ut"](*BIRTH, 14.5, offset)
    chart = engine["calculate_traditional_chart_jd"](jd, *FLORENCE)
    chron = engine["calculate_chronocrats"](jd, *FLORENCE, 14, offset)
    return engine["pn4_timing_bundle"](chart, *FLORENCE, engine["CivilDate"](*BIRTH),
                                       engine["CivilDate"](*target), engine["PN4_MONTHLY_TURN_OPTIONS"][0], chron)


def _wheel_calls(monkeypatch, view, target=TARGET):
    """Run the Revolutions page at `target` on `view` and return every
    generate_multiwheel_svg call's keywords, with the ring labels."""
    # make_app first: it may reload the engine to the test's environment
    # (conftest's sync_engine_to_environment), which would drop a spy set before it.
    at = make_app(page="timing")
    import engine as module
    calls = []
    original = module.generate_multiwheel_svg

    def spy(rings, *args, **kwargs):
        calls.append(dict(kwargs, rings=[r['label'] for r in rings]))
        return original(rings, *args, **kwargs)

    monkeypatch.setattr(module, "generate_multiwheel_svg", spy)
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = target
    at.session_state["_timing_wheel_view"] = view
    at.run()
    assert_no_exception(at, f"the Revolutions page on {view}")
    return at, calls


def _markdowns(node):
    for child in getattr(node, "children", {}).values():
        if getattr(child, "type", None) == "markdown":
            yield child.value
        yield from _markdowns(child)


def _wheel_key(at):
    """The wheel's Mark / Meaning key with the sentence beneath it."""
    keys = [m for m in _markdowns(at.main) if m.startswith("| Mark | Meaning |")]
    assert len(keys) == 1, "the wheel's Mark / Meaning key, once"
    return keys[0]


def _image_time_lords(bundle):
    rows, _counts = bundle["image"]
    lords = {}
    for row in rows:
        if row["Kind"] != "time lord":
            continue
        point = row["Point"]
        if point.startswith("Endpoint of the distribution"):
            lords["endpoint"] = row["Position"]
            continue
        planet, _, name = point.partition(", ")
        lords[name] = planet
    return lords


def test_h5_the_year_over_root_wheel_letters_and_arc_are_the_image_tables(engine, monkeypatch):
    at, calls = _wheel_calls(monkeypatch, "Year over root")
    b = _bundle(engine)
    assert b["cycle"] == 11 and b["month"] == 5, "the premise: the 11th revolution, month 5"
    assert (b["current"]["distributor"], b["current_sr"]["distributor"]) == ("Venus", "Jupiter"), \
        "the premise: the target's distributor and the revolution's differ"
    lords = _image_time_lords(b)
    assert (lords["the distributor"], lords["the partner in the management"],
            lords["lord of the fardar"], lords["dividing the fardar with it"]) == ("Jupiter", "Moon", "Venus", "Venus")
    wheel = [c for c in calls if "badges" in c and len(c["rings"]) == 2]
    assert len(wheel) == 1, [c["rings"] for c in calls]
    kw = wheel[0]
    natal = kw["rings"].index("Nativity")
    badges = kw["badges"][natal]
    expected = {}
    for planet, letter in ((lords["the distributor"], "D"), (lords["the partner in the management"], "P"),
                           (lords["lord of the fardar"], "F"), (lords["dividing the fardar with it"], "f"),
                           (b["orb"], "O")):
        expected[planet] = (expected.get(planet, "") + "·" + letter).strip("·")
    assert badges == expected
    # The solid arc ends on the image's endpoint, the degree reached at the revolution's moment.
    assert engine["get_degree_string"](kw["distribution"]["end"]) == lords["endpoint"] == "20° Lib 42'"


def test_h5_the_wheel_legend_says_the_letters_are_read_at_the_revolutions_moment(monkeypatch):
    at, _calls = _wheel_calls(monkeypatch, "Year over root")
    text = _wheel_key(at)
    assert "those in force at the target date; the revolution's own moment may differ" not in text
    assert "at the revolution's moment, as the image table below takes them" in text
    assert "ending on the degree reached now" not in text
    # The moment carried from I.6, 3 to I.6, 6 is a reading, and the page says so.
    assert "carrying that moment to PN IV I.6, 6's time lords is this app's reading" in text


def _letters(cur, fardar, orb):
    """The wheel's letters, D P F f O, as the image names its time lords."""
    out = {}
    for planet, letter in (((cur or {}).get("distributor"), "D"), ((cur or {}).get("partner"), "P"),
                           ((fardar or {}).get("lord"), "F"), ((fardar or {}).get("sub_lord"), "f"), (orb, "O")):
        if planet:
            out[planet] = (out.get(planet, "") + "·" + letter).strip("·")
    return out


MONTH_CASES = {
    # 1251-10-13, month 5 of the 11th year: at the month's revolution Jupiter
    # distributes and partners, the fardar Venus / Mercury, 20 Lib 57'; at the
    # target Venus / Jupiter, 21 Lib 00'; at the year's revolution Jupiter / Moon,
    # Venus / Venus, 20 Lib 42'.
    "1251-10-13": ((1251, 10, 13), {"Jupiter": "D·P", "Venus": "F", "Mercury": "f", "Sun": "O"}, "20° Lib 57'"),
    # 1360-05-24, month 1 of the 120th year: the target lies past the
    # distribution's table, the month's revolution (the year's) does not.
    "1360-05-24": ((1360, 5, 24), {"Venus": "D", "Jupiter": "P", "Saturn": "F·O", "Sun": "f"}, "21° Cap 40'"),
}


@pytest.mark.parametrize("case", list(MONTH_CASES))
def test_h5_the_month_view_reads_its_time_lords_at_the_months_revolution(engine, monkeypatch, case):
    # Ruling 34: the Month over year and root wheel reads its time lords at the
    # month's revolution, as D2 reads the year's (PN IV IX.3, 4: the month's
    # planets "at the time of the revolution of the month"; IX.3, 8 names the
    # terminal point of the distribution, the distributor and partner, the
    # fardar lord and its divider, and the lord of the orb).
    target, premise, arc_end = MONTH_CASES[case]
    at, calls = _wheel_calls(monkeypatch, "Month over year and root", case)
    b = _bundle(engine, target)
    chart = _natal(engine)
    month_from = (b["jd_mr"] - chart["julian_day"]) / engine["PN4_DIRECTION_YEAR_DAYS"]
    at_month = engine["pn4_distribution_at_age"](b["segments"], month_from)
    # The fardar the month reads, by the rule the year's revolution follows
    # (the year's mark is the floor: the first month opens at the return).
    fardar_month = engine["pn4_fardar_at_age"](max(month_from, float(b["cycle"])), chart["sect"])
    wheel = [c for c in calls if "badges" in c and len(c["rings"]) == 3]
    assert len(wheel) == 1, [c["rings"] for c in calls]
    badges = wheel[0]["badges"][wheel[0]["rings"].index("Nativity")]
    expected = _letters(at_month, fardar_month, b["orb"])
    assert expected == premise, "the premise: the month's revolution's time lords"
    assert at_month and at_month["distributor"], "the month's revolution has a distributor"
    assert badges == expected
    assert wheel[0].get("distribution") is not None, "the month view draws the distribution's arc"
    assert engine["get_degree_string"](wheel[0]["distribution"]["end"]) == arc_end
    text = _wheel_key(at)
    assert ("On the Month over year and root view they are read at the month's revolution, the same reading: "
            "PN IV IX.3, 4 writes the month's planets \"at the time of the revolution of the month\", and PN IV "
            "IX.3, 8 names the month image's time lords with no moment for them.") in text


