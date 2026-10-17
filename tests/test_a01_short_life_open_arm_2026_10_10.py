"""Sahl, On Nativities 1.18, 4: a verdict that turns on the arm not read is
open (ruling 145, A-01 of the third outside pass).

1.18, 4: "The retrogradation of the lord of the Lot of Fortune, and the
presence of an infortune in a stake, is a testimony, if it was inimical to
the Ascendant or did not have a testimony in the Ascendant." The engine reads
the second arm (no dignity of its own at the Ascendant's degree) and not
"inimical". Where the lord of the Lot is retrograde and every infortune in a
stake has a dignity at the Ascendant's degree, the either/or turns on the
unread arm: row 4 is an UnresolvedResult, the count a range (the known
subtotal, or one more), and the headline gives 1.18, 8-10's sentence at each
end. Where nothing is open the count stays an int and the sentence a string.

The reproduction's chart: 1916-02-25 11:58:41 UT, 24.225479 N, 136.078554 E
(Libra rising, night; Saturn retrograde in Cancer in the tenth, lord of the
Capricorn Lot, with exaltation and face at the Ascendant's degree). The other
charts were found by a scan of the engine itself (every 37 h 13 min from
1950-01-01 00:00 UT at five places, each chart's Ascendant, Lot and both
infortunes kept at least a degree from a sign's edge, the Ascendant's rulers
the same half a degree either side, the Lot's lord moving at least 0.02
degrees a day), not by editing a chart.

Every app run here uses its own XDG directory (tmp_path).
"""
import html
from datetime import datetime, time

import pytest

from conftest import assert_no_exception, make_app

REPRO = ((1916, 2, 25, 11, 58, 41), 24.225479, 136.078554)
# The Lot's lord (the Sun) direct, Saturn in the fourth without a dignity at
# the Leo Ascendant: 4 settled "no"; 1 and 3 met, count 2.
DIRECT = ((1985, 3, 20, 14, 30), 51.5, -0.12)
# Saturn retrograde, lord of the Lot; Mars in a stake (the fourth) with no
# dignity at the Ascendant's degree: settled "yes".
ONE_BAD = ((1950, 1, 13, 9, 44), 40.7, -74.0)
# Saturn retrograde, lord of the Lot; both infortunes in stakes, Saturn with a
# dignity at the Ascendant's degree and Mars without: settled "yes".
MIXED = ((1950, 4, 4, 1, 0), 24.225479, 136.078554)
# Saturn retrograde, lord of the Lot; Saturn and Mars both in a stake and
# both with a dignity at the Ascendant's degree: open, 0 or 1.
BOTH_DIGNIFIED = ((1950, 5, 3, 12, 7), 40.7, -74.0)
# Open with a known subtotal: 1 or 2 (1.18, 8 or 9), 2 or 3 (1.18, 9 or 10),
# 3 or 4 (1.18, 10 at both ends).
KNOWN_1 = ((1950, 1, 13, 9, 44), 30.0, 31.2)
KNOWN_2 = ((1950, 3, 8, 16, 19), 40.7, -74.0)
KNOWN_3 = ((1960, 6, 27, 5, 10), 24.225479, 136.078554)

S0 = 'no testimony of a short upbringing (1.18, 1-4)'
S1 = ('"the releaser will be weak and not fit, except through the reception of that releaser, '
      '[which indicates] fitness" (1.18, 8)')
S2 = ('"if ... there were two testimonies of what I mentioned, and the native did not have a releaser, '
      'one will not know his lifespan except by revolving [his] years" (1.18, 9; fn 130)')
S3 = '"if ... there were three testimonies of what I mentioned, then he will not be brought up" (1.18, 10)'


def _short_life(engine, case):
    when, lat, lon = case
    chart = engine["calculate_traditional_chart"](datetime(*when), lat, lon)
    return engine["sahl_short_life_testimonies"](chart, chart["lot_of_fortune"])


def _ends(value):
    return [v for _name, v in value.alternatives]


# --- the engine -----------------------------------------------------------

def test_reproduction_row_4_is_open_and_the_count_is_0_or_1(engine):
    out = _short_life(engine, REPRO)
    row4 = out["rows"][3]
    assert row4["Source"] == "1.18, 4"
    met = row4["Met"]
    assert engine["is_unresolved"](met), met
    assert met.reason.startswith("met if Saturn is inimical to the Ascendant, not met otherwise"), met.reason
    assert met.source == "1.18, 4"
    assert _ends(met) == ["yes", "no"]
    # The Fact keeps its disclosure.
    assert row4["Fact"].endswith('("inimical to the Ascendant" not read)'), row4["Fact"]
    count = out["count"]
    assert engine["is_unresolved"](count), count
    assert _ends(count) == [0, 1]
    assert count.reason.startswith("known subtotal 0;"), count.reason
    sentence = out["sentence"]
    assert engine["is_unresolved"](sentence), sentence
    assert _ends(sentence) == [S0, S1]
    assert sentence.reason.startswith("the count is 0 or 1"), sentence.reason


def test_both_infortunes_dignified_is_open_and_names_both(engine):
    out = _short_life(engine, BOTH_DIGNIFIED)
    met = out["rows"][3]["Met"]
    assert engine["is_unresolved"](met), met
    assert met.reason.startswith("met if Saturn or Mars is inimical to the Ascendant"), met.reason
    assert "Saturn and Mars have a dignity at the Ascendant's degree" in met.reason
    assert _ends(out["count"]) == [0, 1]


@pytest.mark.parametrize("case, ends, sentences", [
    (KNOWN_1, [1, 2], [S1, S2]),
    (KNOWN_2, [2, 3], [S2, S3]),
])
def test_an_open_range_that_crosses_into_1_18_9_or_10(engine, case, ends, sentences):
    out = _short_life(engine, case)
    assert engine["is_unresolved"](out["rows"][3]["Met"])
    assert _ends(out["count"]) == ends
    assert out["count"].reason.startswith(f"known subtotal {ends[0]};")
    assert _ends(out["sentence"]) == sentences


def test_a_range_of_3_or_4_gives_1_18_10_once(engine):
    out = _short_life(engine, KNOWN_3)
    assert engine["is_unresolved"](out["rows"][3]["Met"])
    assert _ends(out["count"]) == [3, 4]
    assert out["sentence"] == S3


@pytest.mark.parametrize("case", [ONE_BAD, MIXED], ids=["one-undignified", "one-dignified-one-not"])
def test_an_infortune_in_a_stake_without_a_dignity_settles_yes(engine, case):
    out = _short_life(engine, case)
    assert out["rows"][3]["Met"] == "yes"
    assert type(out["count"]) is int
    assert out["count"] == sum(1 for r in out["rows"][:4] if r["Met"] == "yes")
    assert isinstance(out["sentence"], str)


def test_mixed_chart_premise(engine):
    """MIXED has both infortunes in stakes, Saturn dignified at the
    Ascendant's degree and Mars not: the arm that is read meets the
    either/or."""
    when, lat, lon = MIXED
    chart = engine["calculate_traditional_chart"](datetime(*when), lat, lon)
    asc = chart["ascendant"]
    houses = {q: engine["get_wsh_house"](chart["planetary_data"][q]["longitude"], asc) for q in ("Saturn", "Mars")}
    assert set(houses.values()) <= {1, 4, 7, 10}, houses
    assert "infortunes in a stake without a dignity at the Ascendant's degree: Mars (" in \
        _short_life(engine, MIXED)["rows"][3]["Fact"]


def test_lord_of_the_lot_direct_is_a_settled_no_with_its_count_and_sentence_exact(engine):
    out = _short_life(engine, DIRECT)
    assert out["rows"][3]["Met"] == "no"
    assert type(out["count"]) is int and out["count"] == 2
    assert out["sentence"] == S2


# --- the page and the reports ---------------------------------------------

def _releaser_page(case, xdg, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    (y, mo, d, *hms), lat, lon = case
    at = make_app(page="releaser", timeout=300)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["date_input_key"] = f"{y:04d}-{mo:02d}-{d:02d}"
    at.session_state["time_input_key"] = time(*hms)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    at.run()
    assert_no_exception(at, "the releaser page")
    return at


def _headline(at):
    hits = [m.value for m in at.main.markdown if m.value.startswith("**The short-life testimonies")]
    assert len(hits) == 1, hits
    return hits[0]


def _row4_cell(at):
    frames = [df.value for df in at.main.dataframe if "Testimony" in df.value.columns]
    assert len(frames) == 1
    rows = frames[0][frames[0]["Testimony"].str.startswith("4.")]
    assert len(rows) == 1
    return rows.iloc[0]["Met"]


def _export_row4(at):
    found = [r for page in at.session_state["_analysis_export"]["results"].values()
             for entries in page.values() for e in entries for r in e["rows"]
             if isinstance(r, dict) and str(r.get("Testimony", "")).startswith("4. The lord of the Lot")]
    assert len(found) == 1, found
    return found[0]


OPEN_TEXT = "Unresolved — met if Saturn is inimical to the Ascendant, not met otherwise"
HEAD = "The short-life testimonies (1.18, 1-10, Masha'allah, fn 125): "
TAIL = 'Shown beside the releaser; they do not disqualify it here. 5-7 are "equivalent" and not counted (fn 126, 129).'
# The headline, as the page prints it and as the reports print the line over
# the short-life table: the range and both ends' sentences where 4 is open.
OPEN_HEAD = HEAD + "0 or 1 of the four counted (4 is open)"
OPEN_REST = "at 0, " + S0 + "; at 1, " + S1 + ". " + TAIL
OPEN_LINE = OPEN_HEAD + " — " + OPEN_REST
SETTLED_HEAD = HEAD + "2 of the four counted"
SETTLED_LINE = SETTLED_HEAD + " -- " + S2 + ". " + TAIL


def _export_entry(at):
    found = [e for page in at.session_state["_analysis_export"]["results"].values()
             for entries in page.values() for e in entries
             if any(isinstance(r, dict) and str(r.get("Testimony", "")).startswith("4. The lord of the Lot")
                    for r in e["rows"])]
    assert len(found) == 1, found
    return found[0]


def _reports_carry_the_line(at, line):
    md = at.session_state["_analysis_markdown"].splitlines()
    assert f"**{line}**" in md, [m for m in md if "short-life" in m]
    assert f"<p class='label'>{html.escape(line)}</p>" in at.session_state["_analysis_html"]


def test_page_shows_the_reproduction_open(tmp_path, monkeypatch):
    at = _releaser_page(REPRO, tmp_path, monkeypatch)
    head = _headline(at)
    assert head == f"**{OPEN_HEAD}** — {OPEN_REST}", head
    assert "-- no testimony" not in head and ": 0 of the four" not in head
    assert _row4_cell(at).startswith(OPEN_TEXT)


def test_reports_show_the_reproduction_open(tmp_path, monkeypatch):
    """The JSON, Markdown and HTML reports carry row 4 open, as the page's
    row table does, and the page's headline over the table: the range, typed
    in the JSON, and the sentence at each end."""
    at = _releaser_page(REPRO, tmp_path, monkeypatch)
    open_text = OPEN_TEXT
    met = _export_row4(at)["Met"]
    assert met["result_type"] == "UnresolvedResult" and met["display"].startswith(open_text), met
    md = [line for line in at.session_state["_analysis_markdown"].splitlines() if line.startswith("| 4. The lord of the Lot")]
    assert len(md) == 1 and f"| {open_text}" in md[0], md
    assert f"<td>{open_text}" in at.session_state["_analysis_html"]
    label = _export_entry(at)["label"]
    assert label["result_type"] == "UnresolvedResult", label
    assert [a["value"] for a in label["alternatives"]] == [0, 1], label
    assert [type(a["value"]) for a in label["alternatives"]] == [int, int]
    assert label["display"] == OPEN_LINE, label["display"]
    assert "0 or 1 of the four counted" in label["display"] and S0 in label["display"] and S1 in label["display"]
    _reports_carry_the_line(at, OPEN_LINE)


def test_page_keeps_a_settled_count_exactly(tmp_path, monkeypatch):
    at = _releaser_page(DIRECT, tmp_path, monkeypatch)
    assert _headline(at) == f"**{SETTLED_HEAD}** -- {S2}. {TAIL}"
    assert _row4_cell(at) == "no"
    assert _export_row4(at)["Met"] == "no"


def test_reports_carry_a_settled_count_exactly(tmp_path, monkeypatch):
    """Where nothing is open the reports' line over the table is the page's
    headline as a string: the int count and 1.18, 9's sentence, exactly."""
    at = _releaser_page(DIRECT, tmp_path, monkeypatch)
    assert _export_entry(at)["label"] == SETTLED_LINE
    _reports_carry_the_line(at, SETTLED_LINE)
