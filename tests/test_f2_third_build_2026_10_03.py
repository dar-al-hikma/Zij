"""Hostile pass of 2026-10-03, fix lane F2 (the counts of the year), third
build: the three breaks the re-check found after the second build (its items
31-33), each as the test the check wrote, adapted to the way the owner took
the break.

31  The revolution of year n reads the fardar that governs year n. A return
    can fall minutes before the 365.2425-day year mark, so the fardar read
    at the return's own elapsed years took the expiring lord at every
    boundary; the governor's #5 and indicator #4 named the wrong year's
    lord, against the Fardar page's Active mark.
32  The Releaser page's "PN IV testimony #3" line names what the governor
    counts: the releaser's distribution at the revolution's moment, not at
    the target date.
33  The governor prose and the comments read "#2, #3 and #4": indicator #2
    has been read at the revolution's moment since the second build's
    addition.

Chart throughout: the harness's default, 1240-05-23 14:30 LMT Florence,
unless stated.
"""
from __future__ import annotations

import pathlib
import re

from conftest import find_table, make_app
from test_f2_second_build_2026_10_03 import _bundle_at
from test_hostile_l4_2026_10_03 import FLORENCE, _chart

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _page_at(page, date):
    at = make_app(page=page)
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = date
    at.run(timeout=300)
    return at


# --- 31: the revolution of year n reads the fardar governing year n --------

def test_a_return_minutes_before_its_year_mark_reads_the_years_own_fardar(engine):
    # The 18th return, 1258-05-23 22:10 UT, opens at 17.99996 elapsed years:
    # minutes before Mercury's 18-31 opens. The revolution of year 18 reads
    # Mercury, as the Fardar page marks on every date of that year.
    b = _bundle_at(engine, (1258, 5, 24))
    assert b["cycle"] == 18 and b["revolution_window"][0] < 18.0, "premise: the return falls before the mark"
    assert b["fardar"]["lord"] == "Mercury", "premise: the target's fardar is Mercury"
    assert b["fardar_sr"]["lord"] == "Mercury", b["fardar_sr"]
    assert b["fardar_sr"] == engine["pn4_fardar_at_age"](18.0, "Diurnal")
    assert b["year_rows"][3]["Ruler"].startswith("Mercury"), b["year_rows"][3]
    assert b["year_rows"][3]["Active point"].startswith("at the revolution's moment, 17.999 years elapsed")
    assert "year 18" in b["year_rows"][3]["Active point"], b["year_rows"][3]["Active point"]
    gov_rows, gov = b["governor"]
    assert next(r["Planet"] for r in gov_rows if r["#"] == 5) == "Mercury"
    # The Fardar page's Active lord, indicator #4 and the governor's #5 agree.
    active = [r for r in b["fardar_rows"] if r["Active"] == "yes"]
    assert len(active) == 1 and active[0]["Lord"] == "Mercury"


def test_the_same_on_the_pages(engine):
    at = _page_at("timing", "1258-05-24")
    yr = find_table(at, "Indicators of the year, in Abu Ma'shar's order (PN IV II.1, 5-24)").value
    assert yr.iloc[3]["Ruler"].startswith("Mercury"), yr.iloc[3]["Ruler"]
    gov = find_table(at, "The governor (PN IV IX.9, 1-10; IX.2, 4-7)").value
    assert gov[gov["#"] == 5]["Planet"].iloc[0] == "Mercury"
    ix9 = next(m.value for m in at.main.markdown if m.value.startswith("**IX.9:**"))
    assert "Venus is primary with 3" not in ix9, ix9
    fd = _page_at("fardar", "1258-05-24")
    fardar = find_table(fd, "The *fardar* (PN IV IV.1)").value
    assert fardar[fardar["Active"] == "yes"]["Lord"].iloc[0] == "Mercury"


def test_a_return_after_its_year_mark_reads_the_fardar_at_its_own_moment(engine):
    # A birth on 1300-12-25 (14:30 LMT, Florence): the 10th return falls
    # twelve minutes AFTER 10.0 elapsed years. Venus's 10-20 has opened by
    # the return, and the return's own moment and the year's mark agree.
    _jd, chart, chron = _chart(engine, (1300, 12, 25), local_hour=14.5)
    b = engine["pn4_timing_bundle"](
        chart, FLORENCE[0], FLORENCE[1], engine["CivilDate"](1300, 12, 25), engine["CivilDate"](1310, 12, 26),
        engine["PN4_MONTHLY_TURN_OPTIONS"][0], chron)
    rev_from = b["revolution_window"][0]
    assert b["cycle"] == 10 and rev_from > 10.0, "premise: the return falls after the mark"
    assert b["fardar_sr"] == engine["pn4_fardar_at_age"](rev_from, chart["sect"])
    assert b["fardar_sr"]["lord"] == "Venus" and b["fardar_sr"]["from"] == 10.0
    assert b["year_rows"][3]["Active point"].startswith("at the revolution's moment, 10.000 years elapsed")
    assert b["year_rows"][3]["Ruler"].startswith("Venus")


def test_the_pages_say_the_fardar_the_revolution_reads_is_its_years():
    counts = {page: _page_at(page, "1258-05-24") for page in ("fardar", "timing")}
    fardar_line = next(c.value for c in counts["fardar"].main.caption if c.value.startswith("Each table's count"))
    assert "the revolution's year" in fardar_line and "year mark" in fardar_line, fardar_line
    assert len(fardar_line) <= 400, len(fardar_line)
    prose = "\n".join(m.value for m in counts["timing"].main.markdown)
    assert "The fardar lord is the one governing the revolution's year" in prose, prose[:200]


# --- 32: the Releaser page's testimony #3 is what the governor counts -----

def test_testimony_3_on_the_releaser_page_names_the_governors_planet(engine):
    # The 16th return: the releaser's distribution has shifted between the
    # return and 1257-01-25, so the two readings differ.
    b = _bundle_at(engine, (1257, 1, 25))
    assert b["cycle"] == 16
    assert b["releaser_sr"]["distributor"] != b["pn4_releaser"]["distributor"], "premise: the distribution shifted"
    gov_rows, _gov = b["governor"]
    assert next(r["Planet"] for r in gov_rows if r["#"] == 3) == b["releaser_sr"]["distributor"]
    rel = next(m.value for m in _page_at("releaser", "1257-01-25").main.markdown
               if m.value.startswith("**PN IV testimony #3:**"))
    assert f"distributor **{b['releaser_sr']['distributor']}**" in rel, rel
    assert "at the revolution's moment" in rel, rel
    assert f"{engine['pn4_elapsed_text'](b['revolution_window'][0])} years elapsed" in rel, rel
    # The target date's reading stays beside it, as the releaser's Now.
    assert f"**{b['pn4_releaser']['distributor']}**" in rel and "now" in rel.lower(), rel


def test_testimony_3_prints_no_rounded_elapsed(engine):
    rel = next(m.value for m in _page_at("releaser", "1257-01-25").main.markdown
               if m.value.startswith("**PN IV testimony #3:**"))
    assert "elapsed age 16.68" not in rel, rel
    assert re.search(r"\b16\.6\d\d years", rel), rel


# --- 33: "#2, #3 and #4" --------------------------------------------------

def test_the_governor_prose_names_indicator_2_too():
    at = _page_at("timing", "1251-10-13")
    prose = [m.value for m in at.main.markdown if "above are read the same way" in m.value]
    assert len(prose) == 1, prose
    assert "indicators #2, #3 and #4 above" in prose[0] and "#3 and #4 above" not in prose[0].replace("#2, #3 and #4", ""), prose[0]


def test_no_comment_reads_the_stale_range():
    from conftest import source_files
    files = source_files()                            # every source module, not the pair
    assert len(files) >= 2, files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"indicators #3 and #4\b", text), path.name
