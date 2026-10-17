"""PN IV IX.7, 32 is cited only for the small days; the Chronocrator Matrix's
one-degree-a-year row is withdrawn (ruling 146 (4), B-10 of the third outside
pass).

IX.7, 32 grades method 7, the small days (59' 08" a day from the revolution's
Ascendant): "there is an approximation in it, but the correct [approach] is
that this way of directing is like the direction of the Sun every day". The
Fardar page quoted it over the Matrix's "Symbolic direction (1°/yr, not a
distribution)" row, said Abu Ma'shar "names the shortcut himself", and said
"the ascensional method he prefers" is the jar bakhtar -- the ascensions are
Dykes's fn 178, not Abu Ma'shar's preference. The quote and both sentences
are dropped; the Days page keeps its citation of IX.7, 32 as it stands.

The row advanced the natal Ascendant one zodiacal degree a year through the
Egyptian bounds. A search of every volume found no passage that teaches that
reckoning: every degree-a-year direction of the Ascendant through the bounds
is by ascensions (the distribution, built as the jar bakhtar). So the row is
withdrawn: not computed, not on the page, not in the JSON, Markdown or HTML
export, and the page says nothing of it (ruling 24's sentence about what the
row counted goes with it). The profection row is unchanged.

Every app run uses its own XDG directory (tmp_path).
"""
import json
from datetime import date

import pytest

from conftest import assert_no_exception, make_app

TARGET = "2026-10-09"
PROFECTION = {"Technique": "Annual Profection", "Active Point": "Aries", "Active Ruler": "Mars",
              "Details": "Age 786 (1 Sign / Year)"}
MATRIX_HELP = "The lord of the year by annual profection."
DROPPED = ("IX.7, 32", "names the shortcut himself", "The ascensional method he prefers",
           "An approximation, by the author's own grading.", "there is an approximation in it")
ROW_MARKS = ("Symbolic direction", "1°/yr", "symbolically directed", "directed symbolically",
             "one degree per year", "The symbolic row's years")
HTML_MARKS = ("Symbolic direction", "1°/yr", "1&deg;/yr", "symbolically directed", "directed symbolically",
              "one degree per year", "The symbolic row&#x27;s years", "The symbolic row's years")
DAYS_CITATION = ("Abu Ma'shar grades it himself -- \"there is an approximation in it, but the correct "
                 "[approach] is that this way of directing is like the direction of the Sun every day ... "
                 "[with] no harm in the work\" (IX.7, 32); that exact form is not built, nor is Dykes's "
                 "fn 178, which would direct by ascensions.")
MD_BLOCK = ("#### Chronocrator Matrix\n\n*The lord of the year by annual profection.*\n\n"
            "| Technique | Active Point | Active Ruler | Details |\n|---|---|---|---|\n"
            "| Annual Profection | Aries | Mars | Age 786 (1 Sign / Year) |\n\n")
HTML_BLOCK = ("<h3>Chronocrator Matrix</h3><p class='cite'>The lord of the year by annual profection.</p>"
              "<div class='wrap'><table><thead><tr><th>Technique</th><th>Active Point</th>"
              "<th>Active Ruler</th><th>Details</th></tr></thead><tbody><tr><td>Annual Profection</td>"
              "<td>Aries</td><td>Mars</td><td>Age 786 (1 Sign / Year)</td></tr></tbody></table></div><h3>")


def _run(page, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / page))
    at = make_app(page=page)
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = TARGET
    at.run(timeout=120)
    assert_no_exception(at, page)
    return at


def _page_text(at):
    """Everything a reader can see or hover on the page, the notes included."""
    parts = []
    for kind in ("markdown", "caption", "text", "info", "warning", "error", "success"):
        parts += [str(n.value) for n in getattr(at, kind)]
    for kind in ("title", "header", "subheader"):
        for n in getattr(at, kind):
            parts += [str(n.value), str(getattr(n, "help", "") or "")]
    parts += [str(e.label) for e in at.expander]
    parts += [df.value.to_csv() for df in at.dataframe]
    return "\n".join(parts)


@pytest.fixture(scope="module")
def fardar(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        yield _run("fardar", tmp_path_factory.mktemp("b10"), mp)
    finally:
        mp.undo()


def _matrix_frames(at):
    heads = [s for s in at.subheader if s.value == "Chronocrator Matrix"]
    assert len(heads) == 1
    return [df.value for df in at.dataframe if "Technique" in df.value.columns]


def test_b10_the_fardar_page_no_longer_quotes_ix_7_32(fardar):
    text = _page_text(fardar)
    for phrase in DROPPED:
        assert phrase not in text, phrase


def test_b10_the_days_page_keeps_its_ix_7_32_citation(tmp_path, monkeypatch):
    days = _run("days", tmp_path, monkeypatch)
    assert any(DAYS_CITATION in str(m.value) for m in days.markdown), \
        [m.value for m in days.markdown if "IX.7, 32" in str(m.value)]


def test_b10_the_matrix_on_the_page_is_the_profection_row_alone(fardar):
    frames = _matrix_frames(fardar)
    assert len(frames) == 1
    assert frames[0].to_dict("records") == [PROFECTION]
    head = next(s for s in fardar.subheader if s.value == "Chronocrator Matrix")
    assert head.help == MATRIX_HELP
    text = _page_text(fardar)
    for mark in ROW_MARKS:
        assert mark not in text, mark


def test_b10_the_matrix_in_the_json_export_is_the_profection_row_alone(fardar):
    analysis = fardar.session_state["_analysis_export"]
    entries = analysis["results"]["Prediction"]["Chronocrator Matrix"]
    assert len(entries) == 1
    assert entries[0]["rows"] == [PROFECTION]
    assert entries[0]["citation"] == MATRIX_HELP
    dumped = json.dumps(analysis, ensure_ascii=False)
    for mark in ROW_MARKS:
        assert mark not in dumped, mark


def test_b10_the_matrix_in_the_markdown_export_is_the_profection_row_alone(fardar):
    md = fardar.session_state["_analysis_markdown"]
    assert md.count("#### Chronocrator Matrix") == 1
    assert MD_BLOCK in md
    for mark in ROW_MARKS:
        assert mark not in md, mark


def test_b10_the_matrix_in_the_html_export_is_the_profection_row_alone(fardar):
    page = fardar.session_state["_analysis_html"]
    assert page.count("<h3>Chronocrator Matrix</h3>") == 1
    assert HTML_BLOCK in page
    for mark in HTML_MARKS:
        assert mark not in page, mark


def test_b10_calculate_time_lords_returns_the_profection_row_only(engine):
    rows = engine["calculate_time_lords"](15.0, date(1240, 5, 23), date(2026, 10, 3))
    assert rows == [{"Technique": "Annual Profection", "Active Point": "Libra", "Active Ruler": "Venus",
                     "Details": "Age 786 (1 Sign / Year)"}]
