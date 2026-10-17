"""The time-standard options named by their labels.

Every refusal of a named-zone cast that tells the reader which option of the
Time standard box to choose names it by the label the box shows, taken from
TIME_STANDARD_OPTIONS, as the area refusals' remedy already did; so do the
box's help, the expander "The three time standards", and the Manual UTC
offset box's two refusals (the box blank, the offset outside its range). The
old wordings, "a manual offset", "Manual:" and a bare "choose LMT.", are gone
from them.

The readings below reach every kind the app's named-zone refusal block
handles. The block's kinds are read from the source, so a kind added there
without a reading here fails the first test.
"""
from __future__ import annotations

import ast
import re
from datetime import time

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, ui_source
from engine import TIME_STANDARD_OPTIONS

LMT, NAMED, MANUAL = TIME_STANDARD_OPTIONS
OLD_WORDS = ("a manual offset", "Manual:", "manual offset", "local mean time) for")

BY_LONGITUDE = f" Choose {LMT}, which takes the birthplace's own longitude, or {MANUAL}."
EITHER = f" Choose {LMT} or {MANUAL}."
CLOCK_CHOICE = f" Choose {MANUAL} and enter the offset of the clock the time was recorded in."

# kind: (how it is reached, the reading, a phrase only that kind's sentence carries, the remedy it ends with).
# A reading by coordinates is (date, (hh, mm), lat, lon); by the place search, (date, (hh, mm), search, label).
READINGS = {
    "none": ("coordinates", ("2000-06-21", (12, 0), 0.0, -30.0),
             "There is no standard-time zone at these coordinates", f"; choose {LMT} or {MANUAL}."),
    "julian": ("coordinates", ("1300-02-29", (12, 0), 43.7792, 11.2463),
               "is a Julian-calendar date that no standard-time zone can place.", EITHER),
    "before_rules -00": ("coordinates", ("1950-06-01", (12, 0), -68.5764, 77.9689),
                         "the time-zone database marks the place uninhabited then", BY_LONGITUDE),
    "before_rules": ("coordinates", ("1850-06-01", (12, 0), 40.7128, -74.0060),
                     "is before America/New_York kept any standard time", BY_LONGITUDE),
    "linked in the windows": ("coordinates", ("1870-06-01", (12, 0), 59.3293, 18.0686),
                              "only inside the stretches it takes from the sources", BY_LONGITUDE),
    "linked": ("coordinates", ("1950-06-01", (12, 0), 5.5600, -0.2050),
               "which it says agrees with this birthplace's clocks only from 1970.", BY_LONGITUDE),
    "disputed": ("coordinates", ("1916-09-30", (23, 30), 59.3293, 18.0686),
                 "falls where the sources disagree on when Europe/Stockholm's clocks were turned back", BY_LONGITUDE),
    "later_lmt": ("coordinates", ("1910-06-01", (12, 0), 6.4550, 3.3841),
                  "a time taken from one place's meridian and not a standard time", BY_LONGITUDE),
    "mean_time": ("coordinates", ("1900-06-01", (12, 0), 22.5726, 88.3639),
                  "do not show it to have been this birthplace's clock then", BY_LONGITUDE),
    "mean_time_exception": ("coordinates", ("1890-06-01", (12, 0), 38.1157, 13.3615),
                            "but Sicily kept its own time until 1893", BY_LONGITUDE),
    "mean_time_city": ("coordinates", ("1875-06-01", (12, 0), 45.4408, 12.3155),
                       "but Venice set its public clocks to it only on 1880-05-01", BY_LONGITUDE),
    "outside_clock": ("coordinates", ("1915-06-01", (12, 0), 48.5734, 7.7521),
                      "say nothing of what Alsace-Moselle kept then", BY_LONGITUDE),
    "mean_time_outside": ("coordinates", ("1900-06-01", (12, 0), 48.5734, 7.7521),
                          "say nothing of Alsace-Moselle, so", BY_LONGITUDE),
    "ambiguous": ("coordinates", ("2020-11-01", (1, 30), 40.7128, -74.0060),
                  "happens twice in America/New_York", f" Choose {LMT} or {MANUAL}, or enter a time the clocks showed once."),
    "nonexistent": ("coordinates", ("2020-03-08", (2, 30), 40.7128, -74.0060),
                    "does not exist in America/New_York", " Check the recorded time."),
    "clock_choice": ("search", ("2026-03-27", (12, 0), "Nablus", "Nablus, WE (PS)"),
                     "at this place the sources leave the clock to the record", CLOCK_CHOICE),
    "unsettled": ("search", ("2026-01-15", (12, 0), "Longwa", "Longwa, 10 (MM)"),
                  "the sources this app holds do not settle which clock this place keeps", CLOCK_CHOICE),
}


def _code(text):
    """The lines that are not comments: a comment may speak of a manual offset."""
    return "\n".join(line for line in text.split("\n") if not line.lstrip().startswith("#"))


def _refusal_block():
    src = ui_source()
    start = src.index("except engine.NamedZoneRefusal as _refusal:")
    return _code(src[start:src.index("time_standard_box.error(chart_error)", start)])


def _offset_box_source():
    """The Manual UTC offset box's refusals: from the refusal's start to the box."""
    src = ui_source()
    start = src.index("utc_offset_refusal = None")
    return _code(src[start:src.index("utc_offset_manual = st.sidebar.number_input(", start)])


def _help_and_expander_source():
    src = ui_source()
    box = src[src.index('time_standard = st.sidebar.selectbox('):src.index("utc_offset_manual = None")]
    start = src.index('with st.sidebar.expander("The three time standards"')
    return _code(box + src[start:src.index('if st.session_state.get("_loaded_without_standard")', start)])


def _render(how, reading):
    day, hhmm, *where = reading
    if how == "coordinates":
        at = make_app(date=day, page="chart")
        at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = where
        at.session_state["time_input_key"] = time(*hhmm)
        at.session_state["time_standard_key"] = NAMED
        at.run()
    else:
        search, label = where
        at = make_app(date=day, page="sources")
        at.session_state["time_input_key"] = time(*hhmm)
        at.session_state["time_standard_key"] = NAMED
        at.session_state["manual_coords_key"] = False
        at.session_state["location_input_key"] = search
        at.run()
        picker = [s for s in at.sidebar.selectbox if s.label == "Select specific location:"][0]
        assert label in picker.options, picker.options
        picker.select(label).run()
    assert_no_exception(at, f"{day} {hhmm} {where}")
    return at


def _no_option_but_by_its_label(text):
    """What is left of a remedy once each label is taken out names no option."""
    rest = text
    for label in TIME_STANDARD_OPTIONS:
        rest = rest.replace(label, "")
    return not re.search(r"LMT|[Mm]anual|named zone|[Ll]ocal [Mm]ean [Tt]ime", rest)


def test_every_kind_the_refusal_block_handles_has_a_reading():
    block = _refusal_block()
    kinds = set(re.findall(r"_refusal\.kind == '(\w+)'", block))
    for group in re.findall(r"_refusal\.kind in \(([^)]*)\)", block):
        kinds |= set(re.findall(r"'(\w+)'", group))
    assert "else:" in block   # the last arm: a reading that does not exist
    read = {kind.split()[0] for kind in READINGS} - {"nonexistent"}
    assert kinds - {"sea", "unknown"} == read, (sorted(kinds), sorted(read))
    assert {"none", "sea", "unknown"} <= kinds


@pytest.mark.parametrize("kind", sorted(READINGS))
def test_each_refusal_names_the_options_by_their_labels(kind):
    how, reading, phrase, remedy = READINGS[kind]
    at = _render(how, reading)
    errors = [e.value for e in at.sidebar.error]
    assert len(errors) == 1, errors
    sentence = errors[0]
    assert phrase in sentence, (kind, sentence)
    assert sentence.endswith(remedy), (kind, remedy, sentence)
    assert [old for old in OLD_WORDS if old in sentence] == [], (kind, sentence)
    # the remedy, from its verb on, names each option only by its label
    remedy_said = sentence[sentence.rindex("hoose") - 1:] if "hoose" in sentence else ""
    assert remedy_said == (remedy.lstrip(" ;") if "hoose" in remedy else ""), (kind, remedy_said)
    assert _no_option_but_by_its_label(remedy_said), (kind, remedy_said)
    # the chart page's recovery panel carries the same sentence (the place search reads on another page)
    panel = [e.value for e in at.main.error]
    assert how == "search" or sentence in panel, (kind, panel)


def test_the_help_and_the_expander_name_the_options_by_their_labels():
    at = make_app(page="chart")
    at.run()
    assert_no_exception(at, "chart")
    box = at.sidebar.selectbox(key="time_standard_key")
    assert tuple(box.options) == TIME_STANDARD_OPTIONS
    assert box.help == (f"{LMT} for charts before standard time was adopted (late 19th century); {NAMED}: the zone at "
                        f"the birthplace; {MANUAL}: type the offset the birth record states, east positive.")
    exp = next(n for n in at.sidebar if getattr(n, "type", None) == "status" and n.label == "The three time standards")
    text = "\n".join(m.value for m in exp.markdown)
    lines = [ln for ln in text.split("\n") if ln.startswith("- ")]
    assert [old for old in OLD_WORDS if old in box.help or old in text] == []
    # each item's head is its label, and nothing after a head names an option otherwise
    heads = [f"- {label}" for label in TIME_STANDARD_OPTIONS]
    assert [(ln[:len(head)], _no_option_but_by_its_label(ln[len(head):])) for ln, head in zip(lines, heads)] == [
        (head, True) for head in heads], lines
    assert len(lines) == len(heads), lines
    clauses = box.help.split("; ")
    assert [(c[:len(label)], _no_option_but_by_its_label(c[len(label):])) for c, label in zip(clauses, TIME_STANDARD_OPTIONS)
            ] == [(label, True) for label in TIME_STANDARD_OPTIONS], clauses
    assert len(clauses) == len(TIME_STANDARD_OPTIONS), clauses


def test_the_labels_come_from_the_options_and_are_not_typed():
    """The sentences, the help and the expander take each label from
    TIME_STANDARD_OPTIONS, so none can drift from the box."""
    typed = [(name, word) for name, src in (("the refusal block", _refusal_block()),
                                            ("the help and expander", _help_and_expander_source()))
             for word in TIME_STANDARD_OPTIONS + OLD_WORDS if word in src]
    assert typed == []
    assert "TIME_STANDARD_OPTIONS[0]" in _help_and_expander_source()
    assert "TIME_STANDARD_OPTIONS[2]" in _help_and_expander_source()
    assert "_LMT_OR_MANUAL" in _refusal_block() and "_CHOOSE_BY_LONGITUDE" in _refusal_block()
    offset_box = _offset_box_source()
    assert [word for word in TIME_STANDARD_OPTIONS + OLD_WORDS + ("choose LMT",) if word in offset_box] == []
    assert offset_box.count("or choose {TIME_STANDARD_OPTIONS[0]}.") == 2, offset_box


# The Manual UTC offset box's two refusals: (the seed in the box, the sentence the page shows).
OFFSET_REFUSALS = {
    "blank": (None, f"The UTC offset box is blank. Type an offset from -14 to +14 hours, or choose {LMT}."),
    "out of range": (14.25, "The UTC offset 14.25 is outside the box's range of -14 to +14 hours. "
                            f"Type an offset inside it, or choose {LMT}."),
}


@pytest.mark.parametrize("case", sorted(OFFSET_REFUSALS))
def test_the_offset_box_refusals_name_lmt_by_its_label(case):
    seed, expected = OFFSET_REFUSALS[case]
    at = make_app(date="1982-06-01", page="chart")
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = seed
    at.run()
    assert_no_exception(at, f"manual offset {seed!r}")
    assert [e.value for e in at.sidebar.error] == [expected]
    assert [e.value for e in at.main.error] == [expected], "the chart page's recovery panel carries the same sentence"
    assert [old for old in OLD_WORDS if old in expected] == []


def _string_parts(tree):
    """Every string a page could print: each constant, and each literal part of an f-string."""
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def test_no_sentence_of_the_app_says_a_bare_choose_lmt():
    """A remedy that names LMT names it by its label: "choose LMT." with nothing
    after the short form is gone from every string of the app."""
    bare = [text for text in _string_parts(ast.parse(APP_PATH.read_text()))
            if re.search(r"[Cc]hoose LMT(?! \(Local Mean Time\))", text)]
    assert bare == []
