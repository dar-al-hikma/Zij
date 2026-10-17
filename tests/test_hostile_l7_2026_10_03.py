"""Hostile lane L7 (2026-10-03): tests that cannot fail, the mutation scan, and what the pages say.

The ``xfail(strict=True)`` tests assert the RIGHT behaviour and fail today: each
is one finding of the lane's report (ids L7-NN). The plain tests are the attacks
that held, pinned so they stay held, and the three tools' mechanism checks:

* the test scanner (development-only)        -- static scan of the suite for tests that cannot fail
* the mutation scan (development-only)    -- one mutation of a worktree COPY against one test file
* the page-text scanner (development-only)   -- the sieve over rendered text and exports

No network; every path is relative to this file or comes through conftest;
corpus-reading tests use tests/corpus_paths.py and do not skip when it is present.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (EXECUTABLE_DIR, assert_no_exception, find_table, make_app, table_nodes)
from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import needs_corpus


def _render(page, depth="Course text", date="1240-05-23", **state):
    at = make_app(date=date, page=page)
    at.session_state["_reading_depth"] = depth
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "2026-10-03"
    for k, v in state.items():
        at.session_state[k] = v
    at.run(timeout=120)
    assert_no_exception(at, page)
    return at


def _markdowns(at):
    return [m.value for m in at.main.markdown]


def _cells(at, heading):
    df = find_table(at, heading).value
    return df


def _images(node, found=None):
    found = [] if found is None else found
    for child in getattr(node, "children", {}).values():
        if type(child).__name__ == "Image":
            found.append(child)
        else:
            _images(child, found)
    return found


# =============================================================================
# Part C -- what the pages say (findings L7-01 .. L7-10, L7-15 .. L7-17)
# =============================================================================

def test_l7_01_lot_formula_names_no_internal_identifier():
    at = _render("lots")
    df = _cells(at, "Classical Lots")
    offenders = [v for v in df["Formula"] if re.search(r"[a-z]+_[a-z]+", str(v))]
    assert not offenders, offenders


def test_l7_02_no_app_test_in_page_cells():
    at = _render("dignities")
    df = _cells(at, "Topical House Lords (Masha'allah)")
    col = [c for c in df.columns if "assessment" in c.lower()][0]
    offenders = [v for v in df[col] if "app test" in str(v)]
    assert not offenders, offenders[:3]


def test_l7_03_past_the_table_age_is_rounded():
    at = _render("timing")
    offenders = []
    for heading, node in table_nodes(at):
        for col in node.value.columns:
            for v in node.value[col]:
                m = re.search(r"age (\d+\.\d{5,}) is past", str(v))
                if m:
                    offenders.append((heading, col, m.group(0)))
    assert not offenders, offenders


def test_l7_04_export_carries_no_internal_key_in_fact_labels():
    at = _render("configurations", "Course text and supplement")
    md = at.session_state["_analysis_markdown"]
    html = at.session_state["_analysis_html"]
    assert "triplicity_day" not in md and "triplicity_night" not in md
    assert "triplicity_day" not in html and "triplicity_night" not in html


def test_l7_05_sources_readings_print_no_python_booleans():
    at = _render("sources")
    captions = [c.value for c in at.main.caption]
    assert not [c for c in captions if re.search(r"\b(?:True|False)\b", c)], captions[:3]
    df = _cells(at, "Readings in force")
    for col in ("In force", "Default"):
        assert not [v for v in df[col] if str(v) in ("True", "False")], list(df[col])


def test_l7_06_indicator_15_cells_are_readable():
    at = _render("timing")
    df = _cells(at, "Indicator 15: relationship details")
    for col in ("Motion", "Applicant", "Receiver"):
        bad = [v for v in df[col] if (isinstance(v, float) and math.isnan(v)) or str(v) == "nan"]
        assert not bad, (col, len(bad))
    for v in df["Distance"]:
        assert len(str(v).split(".")[-1]) <= 2, v


def test_l7_07_exports_label_rows_in_words():
    at = _render("chart")
    md = at.session_state["_analysis_markdown"]
    labels = re.findall(r"^\| ([a-z]+_[a-z0-9_]+) \|", md, re.M)
    assert not labels, sorted(set(labels))


def test_l7_08_timing_prose_parentheses_balance():
    at = _render("timing")
    node = [m for m in _markdowns(at) if "is the significator (latitude 0" in m]
    assert node, "the sentence moved; update the anchor"
    for s in node:
        assert s.count("(") == s.count(")"), s


def test_l7_09_pages_do_not_call_themselves_the_engine():
    timing = _render("timing")
    texts = _markdowns(timing) + [c.value for c in timing.main.caption]
    assert not [t for t in texts if re.search(r"\b(?:the|this) engine\b", t)], [t[:80] for t in texts if "engine" in t]
    findings = _render("findings", "Course text and supplement")
    assert not [t for t in _markdowns(findings) if re.search(r"\bfixtures?\b", t)]


def test_l7_10_strip_svg_carries_no_python_none():
    import base64
    at = _render("timing")
    svgs = []
    for im in _images(at.main):
        url = im.proto.imgs[0].url
        if url.startswith("data:image/svg+xml;base64,"):
            svgs.append(base64.b64decode(url.split(",", 1)[1]).decode("utf-8"))
    assert svgs, "no SVG image on the Timing page"
    assert not [s for s in svgs if '="None"' in s]


def test_l7_15_reference_page_names_the_volume_of_every_page_number():
    at = _render("reference", "Course text and supplement")
    offenders = []
    for heading, node in table_nodes(at):
        for col in node.value.columns:
            for v in node.value[col]:
                s = str(v)
                for m in re.finditer(r"\bpp?\. ?\d+", s):
                    window = s[max(0, m.start() - 80): m.end() + 40]
                    if not re.search(r"Sahl|Gr\. Intr|PN IV|ITA|Holden|Rhetorius|Dykes|Riley|Carmen|Mathesis|Morin|Valens|Abu Bakr|his volume|Ch\. 57", window):
                        offenders.append((heading, s[:80]))
    assert not offenders, offenders


def test_l7_16_findings_page_names_the_volume_of_figure_57():
    # The eyesight-degrees note renders when a point stands in one of the spans: Petoskey does.
    from datetime import time
    at = _render("findings", "Course text and supplement", date="1982-11-19", time_input_key=time(5, 18),
                 time_standard_key="Standard time (named zone)", manual_lat_key=45.3733, manual_lon_key=-84.9553)
    # Premise: the sentence this pin is about was drawn ("... is the ordinal degree, as
    # [Sahl I] Figure 57 is read"). Without it the loop below has nothing to check and
    # passes on a page that never shows the note (re-pass N-04), as L7-08 and L7-17 assert theirs.
    eyesight = [s for s in _markdowns(at) if re.search(r"Fig(?:ure|\.) ?57 is read", s)]
    assert eyesight, "premise: the eyesight note's Figure 57 sentence rendered; the sentence moved, update the anchor"
    offenders = []
    for s in _markdowns(at):
        for m in re.finditer(r"Fig(?:ure|\.) ?57\b", s):
            window = s[max(0, m.start() - 60): m.end() + 30]
            if not re.search(r"Sahl|Gr\. Intr|PN IV|his volume|Sahl I", window):
                offenders.append(window)
    assert not offenders, offenders


def test_l7_17_fardar_page_names_the_volume_of_figure_146():
    # The planetary-years note with Figure 146 renders on the arctic chart (2000-06-21, 70N 25E, UTC+2).
    at = _render("fardar", "Course text and supplement", date="2000-06-21", time_standard_key="Manual UTC offset",
                 utc_offset_key=2.0, manual_lat_key=70.0, manual_lon_key=25.0)
    node = [m for m in _markdowns(at) if "Figure 146 (" in m]
    assert node, "the sentence moved; update the anchor"
    for s in node:
        m = re.search(r"Figure 146 \(([^)]*)\)", s)
        assert m and re.search(r"Gr\. Intr|Great Introduction", m.group(1)), m.group(0)


# =============================================================================
# Part A -- tests that cannot fail (L7-11) and the static scanner
# =============================================================================

def test_l7_11_the_portions_fixture_chart_has_portions(engine):
    from datetime import datetime
    birth, lat, lon = datetime(1975, 9, 5, 3, 0), 51.5, -0.12
    chart = engine["calculate_traditional_chart"](birth, lat, lon)
    b = engine["pn4_timing_bundle"](chart, lat, lon, birth.date(), datetime(2027, 6, 1).date(),
                                    engine["PN4_MONTHLY_TURN_OPTIONS"][0], {"Hour Lord": "Venus", "Approximate": False})
    assert b["moon_portions"], "the fixture's Moon makes no connection in its year, so `if b['moon_portions']:` is never entered"


def test_held_readings_set_by_one_test_file_do_not_leak(engine):
    """Attack that held: test_f9_topical_tables sets SOFTENED_INFORTUNE and
    its autouse fixture restores the thread's readings."""
    assert engine["reading"]("SOFTENED_INFORTUNE") == engine["SOFTENED_INFORTUNE"]


# =============================================================================
# Part B -- the mutation scanner's mechanism
# =============================================================================


# =============================================================================
# Part C -- the sieve's mechanism and the attacks that held on rendered text
# =============================================================================


def test_held_exports_print_no_unresolved_result_or_dataframe_repr():
    at = _render("timing", "Course text and supplement")
    for key in ("_analysis_markdown", "_analysis_html"):
        text = at.session_state[key]
        for forbidden in ("UnresolvedResult(", "<class", "Timestamp(", "numpy.", "dtype"):
            assert forbidden not in text, (key, forbidden)
    js = json.dumps(at.session_state["_analysis_export"])
    assert "UnresolvedResult(" not in js and "NaN" not in js


# =============================================================================
# Part D -- the citation discipline
# =============================================================================

@needs_corpus()
def test_held_sampled_register_locators_resolve_to_the_sentences_they_quote():
    """Two of the twenty sampled `ok` locators that needed the corpus to
    settle: PN IV VI.2, 1 does carry 'a year for every degree', and
    Gr. Intr. VI.20, 8 does give 22 degrees for the spines of Capricorn."""
    pn4 = corpus_file("pn4/pn4_complete/persian_nativities_iv.md").read_text(encoding="utf-8")
    s1 = [ln for ln in pn4.split("\n") if ln.startswith("**1** Now, every one of the seven planets")]
    assert s1 and "a year for every degree" in s1[0]
    gi = corpus_file("gr_intr/abu_mashar_great_introduction.md").read_text(encoding="utf-8")
    chapter = gi[gi.index("### Chapter VI.20"):gi.index("### Chapter VI.21")]
    assert re.search(r"^8 The \[6\] spines of Capricorn are 22°", chapter, re.M)


# --- skip_guard --------------------------------------------------------------

def _run_guarded_probe(tmp_path, body):
    """Run `body` as a test module under a conftest that wires tests/skip_guard.py
    the way tests/conftest.py does, in a directory of its own."""
    (tmp_path / "conftest.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(EXECUTABLE_DIR / 'tests')!r})\n"
        "from skip_guard import pytest_runtest_logreport, pytest_collectreport, pytest_sessionfinish  # noqa\n")
    (tmp_path / "test_probe.py").write_text(textwrap.dedent(body))
    env = dict(os.environ)
    env.setdefault("CORPUS_DIR", str(CORPUS_DIR))
    p = subprocess.run([sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider", "--rootdir", str(tmp_path)],
                       capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=120)
    return p.returncode, p.stdout + p.stderr


def test_held_skip_guard_catches_fixture_skips_importorskip_and_plain_skips(tmp_path):
    code, out = _run_guarded_probe(tmp_path, '''
        import pytest

        @pytest.fixture
        def skipping():
            pytest.skip("fixture decided to skip")

        def test_fixture(skipping):
            assert True

        def test_importorskip():
            pytest.importorskip("no_such_module_l7")

        def test_plain():
            pytest.skip("flaky today")
    ''')
    assert code != 0 and "SKIP GUARD: 3 skip(s) not allowed" in out, out[-600:]


def test_l7_14_skip_guard_catches_an_xfail_that_never_runs(tmp_path):
    code, out = _run_guarded_probe(tmp_path, '''
        import pytest

        @pytest.mark.xfail(run=False, reason="never run: too slow")
        def test_never_runs():
            assert False
    ''')
    assert code != 0 and "SKIP GUARD" in out, out[-600:]


