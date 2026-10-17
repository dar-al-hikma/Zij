"""Lane GV: the Sun as PN IV's governor of the year (the owner's ruling 95).

PN IV IX.9, 11 (PN IV pp. 667-668) defines the governor's "suitable condition
in its essence" for two classes only: "the three superior ones were
easternizing from the Sun, in their *halb*, not retrograde, and not made
unfortunate, and the inferior ones westernizing from him, in the same
condition as well, and they are in their *halb*". The Sun is of neither:
PN IV I.8, 20 (PN IV p. 169), "just as the Sun is in the middle of the
superior and inferior planets", and PN IV VII.1, 16 with Dykes's n. 8
(PN IV p. 478), "these three inferior planets" -- "Venus, Mercury, and the
Moon."

Ruling 95 (2026-10-06, adopting the reading of ruling 89, option (a)): when
the Sun governs the year, the side row reads "not applicable: the Sun is
neither of the superior nor of the inferior ones (PN IV I.8, 20)"; the test's
verdict reads "not judged", never "no" and never a "yes" resting on the
remaining cells; the Sun's halb cell goes with the row; "not retrograde" and
the infortunes' looks may stay as facts, not as criteria. Other governors
are unchanged.

The charts are the reading's: A (diurnal root and revolution; the page's own
default birth), B (nocturnal both), C (diurnal, the Sun in his own house and
in a good division), D and E (the Sun's centre below the horizon in a
diurnal chart, where the old halb cell read "not met").
"""
from __future__ import annotations

import html as H
import random

import pytest

from conftest import FLORENCE, assert_no_exception, make_app
from corpus_paths import CORPUS_DIR, corpus_file, page_marker
from skip_guard import needs_corpus

_corpus = needs_corpus()

RULED = "not applicable: the Sun is neither of the superior nor of the inferior ones (PN IV I.8, 20)"
GOVERNOR = "The governor (PN IV IX.9, 1-10; IX.2, 4-7)"

# name: (birth, local hour LMT, target, the root's and the revolution's sect)
CHARTS = {
    "A": ((1240, 5, 23), 14.5, (1286, 5, 24), ("Diurnal", "Diurnal")),
    "B": ((1240, 5, 23), 23.0, (1282, 5, 24), ("Nocturnal", "Nocturnal")),
    "C": ((1240, 8, 5), 12.0, (1249, 8, 6), ("Diurnal", "Diurnal")),
}


def _bundle(engine, birth, local_hour, target, lat=FLORENCE[0], lon=FLORENCE[1]):
    """The bundle as app.py computes it, LMT (the sidebar's default standard)."""
    offset = lon / 15.0
    jd = engine["civil_local_to_jd_ut"](*birth, local_hour, offset)
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    chron = engine["calculate_chronocrats"](jd, lat, lon, int(local_hour), offset)
    bundle = engine["pn4_timing_bundle"](chart, lat, lon, engine["CivilDate"](*birth), engine["CivilDate"](*target),
                                         engine["PN4_MONTHLY_TURN_OPTIONS"][0], chron)
    return chart, bundle


def _row11(rows):
    hits = [r for r in rows if r["Test"].startswith("IX.9, 11")]
    assert len(hits) == 1, rows
    return hits[0]


def _sun_governs(engine, name):
    birth, hour, target, sects = CHARTS[name]
    chart, b = _bundle(engine, birth, hour, target)
    assert b["governor"][1]["primary"] == ["Sun"], "the premise: the Sun is the primary"
    assert (chart["sect"], b["sr"]["sect"]) == sects, "the premise: the sects"
    return chart, b


def _assert_the_ruled_row(row):
    crit = row["Criteria"]
    assert RULED in crit, crit
    for gone in ("western of the Sun", "eastern of the Sun", "in its halb met", "in its halb not met"):
        assert gone not in crit, (gone, crit)
    # The facts that may stay, for each chart, and not as criteria.
    assert crit.count("not retrograde") == 2 and crit.count("infortunes looking:") == 2, crit
    assert "not retrograde met" not in crit and "not made unfortunate" not in crit, crit


def _assert_not_judged(row):
    assert row["Met"].startswith("not judged"), row["Met"]
    assert row["Met"] != "no" and not row["Met"].startswith("yes"), row["Met"]


# --- D1: the side row does not apply to the Sun ----------------------------------------------

@pytest.mark.parametrize("name", list(CHARTS))
def test_the_side_row_reads_not_applicable_for_the_sun(engine, name):
    _chart, b = _sun_governs(engine, name)
    _assert_the_ruled_row(_row11(b["governor_condition"]))


# --- D2: the Sun's essence test is not judged ------------------------------------------------

@pytest.mark.parametrize("name", list(CHARTS))
def test_the_suns_essence_test_is_not_judged(engine, name):
    _chart, b = _sun_governs(engine, name)
    _assert_not_judged(_row11(b["governor_condition"]))


def test_the_suns_essence_test_is_not_judged_on_a_seeded_sample(engine):
    """The reading's sample (seed 89), shortened: births 1100-1900 CE, |latitude|
    to 60, a revolution 1-80 years on. Whatever the halb and motion would have
    read, the Sun's IX.9, 11 is neither "no" nor "yes"."""
    rng = random.Random(89)
    sects = set()
    for _ in range(16):
        jd = rng.uniform(2122820.5, 2415020.5)
        lat, lon = rng.uniform(-60.0, 60.0), rng.uniform(-180.0, 180.0)
        root = engine["calculate_traditional_chart_jd"](jd, lat, lon)
        k = rng.randint(1, 80)
        jd_sr = engine["pn4_revolution_jd"](root["planetary_data"]["Sun"]["longitude"], jd + k * 365.2422)
        sr = engine["calculate_traditional_chart_jd"](jd_sr, lat, lon)
        sects.add((root["sect"], sr["sect"]))
        row = _row11(engine["pn4_governor_condition"]("Sun", root, sr))
        _assert_the_ruled_row(row)
        _assert_not_judged(row)
    assert len({s for pair in sects for s in pair}) == 2, "the premise: both sects in the sample"


# --- D3: the Sun's halb cell goes with the row, so the horizon cannot decide it -------------

@pytest.mark.parametrize("jd, lat, lon", [(2174110.649316, 43.7792, 11.2463),      # D: Florence, 1240-05-23 04:20 LMT
                                          (2451716.430556, 66.0, 25.0)],          # E: 66 N, 2000-06-21 local midnight
                         ids=["D", "E"])
def test_the_suns_halb_cell_is_gone_where_his_centre_is_below_a_diurnal_horizon(engine, jd, lat, lon):
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    assert chart["sect"] == "Diurnal", "the premise"
    sun = chart["planetary_data"]["Sun"]
    assert engine["_sin_altitude"](sun["longitude"], sun["latitude"], sun["distance"], chart["obliquity"],
                                   chart["armc"], chart["geo_lat"]) < 0, "the premise: his centre is below"
    row = _row11(engine["pn4_governor_condition"]("Sun", chart, chart))
    # No halb cell of his own: the row names halb once, and only as not applicable.
    assert "in its halb met" not in row["Criteria"] and "in its halb not met" not in row["Criteria"], row["Criteria"]
    assert row["Criteria"].count("in its halb") == 1, row["Criteria"]
    assert row["Criteria"].split("in its halb", 1)[1].startswith(": not applicable"), row["Criteria"]
    assert RULED in row["Criteria"]
    _assert_not_judged(row)


# --- The page and the exports ----------------------------------------------------------------

def test_the_revolutions_page_and_its_exports_print_the_ruled_row():
    """Chart A is the page's own default birth (1240-05-23 14:30 LMT, Florence)."""
    at = make_app(page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1286-05-24"
    at.run(timeout=300)
    assert_no_exception(at, "the Sun as governor")
    shown = [df.value for df in at.main.dataframe
             if "Test" in df.value.columns and any(str(t).startswith("IX.9, 11") for t in df.value["Test"])]
    assert len(shown) == 1, "the premise: one condition table"
    page_row = shown[0][shown[0]["Test"].astype(str).str.startswith("IX.9, 11")].iloc[0]
    _assert_the_ruled_row(page_row)
    _assert_not_judged(page_row)
    assert any(m.value.startswith("**IX.9, 11-13, the condition of the primary planet (Sun)") for m in at.main.markdown)
    entries = at.session_state["_analysis_export"]["results"]["Prediction"][GOVERNOR]
    exported = [r for e in entries for r in e["rows"] if str(r.get("Test", "")).startswith("IX.9, 11")]
    assert len(exported) == 1 and exported[0]["Criteria"] == page_row["Criteria"] and exported[0]["Met"] == page_row["Met"]
    assert RULED in at.session_state["_analysis_markdown"]
    assert H.escape(RULED) in at.session_state["_analysis_html"]
    for export in (at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]):
        assert "western of the Sun not met (-)" not in export


# --- Other governors are unchanged ------------------------------------------------------------

# Chart C's root and revolution, each other planet read as the governor: the
# IX.9, 11 cells as they stood before ruling 95 (the reading's attack that
# held: the superiors read "eastern of the Sun", the inferiors -- Venus,
# Mercury and the Moon -- "western of the Sun").
OTHERS_ON_C = {
    "Saturn": ("no", "root: eastern of the Sun met (eastern); in its halb met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: none); revolution: eastern of the Sun not met (western); in its halb met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: Mars by opposition)"),
    "Jupiter": ("no", "root: eastern of the Sun met (eastern); in its halb not met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: Saturn by trine, Mars by square); revolution: eastern of the Sun not met (western); in its halb not met (by altitude); not retrograde not met; not made unfortunate: not judged (infortunes looking: Saturn by sextile, Mars by trine)"),
    "Mars": ("no", "root: eastern of the Sun met (eastern); in its halb not met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: none); revolution: eastern of the Sun met (eastern); in its halb met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: Saturn by opposition)"),
    "Venus": ("no", "root: western of the Sun not met (eastern); in its halb not met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: Mars in it); revolution: western of the Sun met (western); in its halb not met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: none)"),
    "Mercury": ("no", "root: western of the Sun met (western); in its halb not met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: Mars by sextile); revolution: western of the Sun not met (eastern); in its halb met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: Saturn by square, Mars by square)"),
    "Moon": ("no", "root: western of the Sun not met (eastern); in its halb met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: Mars by trine); revolution: western of the Sun not met (eastern); in its halb met (by altitude); not retrograde met; not made unfortunate: not judged (infortunes looking: none)"),
}


@pytest.mark.parametrize("planet", list(OTHERS_ON_C))
def test_another_governors_essence_row_is_unchanged(engine, planet):
    chart, b = _sun_governs(engine, "C")
    row = _row11(engine["pn4_governor_condition"](planet, chart, b["sr"]))
    assert (row["Met"], row["Criteria"]) == OTHERS_ON_C[planet]
    assert RULED not in row["Criteria"]


# --- The three sentences, as printed ----------------------------------------------------------

def _page(text, n):
    start = text.index(page_marker("PN IV", n))
    return text[start:text.index(page_marker("PN IV", n + 1), start)]


@_corpus
def test_the_three_sentences_the_row_rests_on_are_as_printed():
    text = corpus_file("pn4/pn4_complete/persian_nativities_iv.md").read_text(encoding="utf-8")
    # PN IV IX.9, 11, the two classes (PN IV pp. 667-668).
    assert "**11** So if the indicators indicated his survival" in _page(text, 667)
    assert "and that is if the three superior ones were easternizing from" in _page(text, 667)
    assert ("the Sun, in their *halb*, not retrograde, and not made unfortunate,<sup>325</sup> and the inferior ones "
            "westernizing from him, in the same condition as well, and they are in their *halb*)") in _page(text, 668)
    # PN IV I.8, 20 (PN IV p. 169).
    assert ("**20** And just as the Sun is in the middle of the superior and inferior planets, this period of the "
            "years of the native becomes a turning point") in _page(text, 169)
    # PN IV VII.1, 16 and n. 8 (PN IV p. 478).
    p478 = _page(text, 478)
    assert "**16** And for these three inferior planets,<sup>8</sup>" in p478
    assert "<sup>8</sup> Venus, Mercury, and the Moon." in p478
