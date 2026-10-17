"""Label lists split by outcome when a connection is undecided.

``evaluate_with_connection_uncertainty`` runs an evaluator once for each way
an undecided connection could go and merges the outcomes with
``_connection_merge``. Testimony lists already merged well; a plain list of
strings had no rule, so one label on which the outcomes disagreed turned the
whole list into a single ``UnresolvedResult``. The Planetary Condition's
``Positive Labels`` did that on 1957-08-17, 15:48 LMT, Florence (Venus and
Jupiter, one degree either side of the Virgo-Libra boundary), and app.py's
``_condition_rows`` then raised ``TypeError: 'UnresolvedResult' object is not
iterable`` on every page -- about one chart in six hundred.

The owner's ruling (option 1): split each label list by label. A label in
every outcome is settled and stays; a label in only some goes to the list's
``Unresolved ...`` channel as an ``UnresolvedResult`` carrying the reason and
source of the connection it turns on; nothing is dropped. Counts hold the
known subtotal of what holds in every outcome, with a numeric Unresolved
column beside them, blank when nothing is open; Net and the verdict stay
unresolved when the outcomes disagree, and such a row stays unranked.

The rule, in ``_connection_merge``: a field named in ``_LABEL_CHANNELS``
whose outcomes are lists of strings that differ is split, into the channel
``"Unresolved " + field``. The fields and their consumers:

* ``Positive Labels`` / ``Negative Labels`` (Planetary Condition, Gr. Intr.
  VII.6): the table's two label cells, the row's details, the export. The
  channels existed (Mercury's sect).
* ``labels`` (Corruption of the Moon, Sahl, The Introduction Ch. 3,
  103-112): the table's Defects cell and the export. New channel; the cell
  used to collapse to one UnresolvedResult with a Status column.
* ``facts`` (a Strength or Weakness testimony, Ch. 3, 78-100): the tick
  grids' row detail and the export's testimony cell. New channel.

Lists of strings with no channel, which still collapse to one
UnresolvedResult when the outcomes disagree:

* ``Labels`` of Strength and Weakness: rebuilt from the confirmed
  testimonies by the merge's own testimony rule, so never shown collapsed.
* ``clauses`` of each Corruption of the Moon testimony: rendered nowhere.

Order is first-seen across the outcomes, which run in a fixed order; never a
set's.

The consumers whose columns this touches, each one type on the page and in
the export: the Planetary Condition table (every count its known subtotal,
Verdict text), its details line (the engine's own counts, possible totals and
all), the Dignities page's Topical readings Net (the known subtotal, with
Unresolved beside it when a row has one), and Dignity Evaluation's Ranking
score and Acc (the known subtotal, with Unresolved when Mercury's sect leaves
the domain contribution open).
"""
import hashlib
import json
import logging
import random
import re
from datetime import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from conftest import LOCAL_TIME, PAGES, assert_no_exception, make_app, table_nodes

FIXTURE = Path(__file__).parent / "fixtures" / "label_merge_ordinary_2026_09_25.json"
_ARROW_FALLBACK = "Serialization of dataframe to Arrow table was unsuccessful"

FLORENCE_DATE, FLORENCE_TIME = "1957-08-17", time(15, 48)
# Ruling 64: where a label still opens on an unresolved connection under
# ruling 60 -- Venus 25 Sagittarius retrograde, her separation from Saturn
# unresolved, strikes Mercury 0 Capricorn over the cusp (Florence, LMT).
OPEN_DATE, OPEN_TIME = "1575-12-30", time(10, 0)


class _Fallbacks(logging.Handler):
    """Every Arrow fallback Streamlit logs while a page is drawn."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.messages = []

    def emit(self, record):
        if _ARROW_FALLBACK in record.getMessage():
            detail = str(record.exc_info[1]) if record.exc_info else ""
            self.messages.append(f"{record.getMessage()} {detail}".strip())


def _render(date, page, hhmm=None, lat=None, lon=None, depth="Course text and supplement", patch=None):
    """One page, run; with the Arrow fallbacks it logged."""
    at = make_app(date=date, page=page)
    if hhmm is not None:
        at.session_state["time_input_key"] = hhmm
    if lat is not None:
        at.session_state["manual_lat_key"] = lat
        at.session_state["manual_lon_key"] = lon
    at.session_state["_reading_depth"] = depth
    at.session_state["_target_date"] = "2026-09-17"
    if patch is not None:
        patch()
    logger = logging.getLogger("streamlit.dataframe_util")
    handler, level = _Fallbacks(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        at.run(timeout=300)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    return at, handler.messages


def _export_tables(at):
    for page, headings in at.session_state["_analysis_export"]["results"].items():
        for heading, entries in headings.items():
            for entry in entries:
                yield f"{page} / {heading}", entry["rows"]


# The export tables whose columns this branch types. The export keeps an
# UnresolvedResult as a structured object wherever the engine returns one,
# so many other tables mix it with text in one column by design (the
# Aspects table's Connection, the Syzygy's Value, ...): those are not this
# branch's, and the sweep reports them without failing on them.
OWNED = ("Configurations / Planetary Condition", "Configurations / Corruption of the Moon",
         "Dignities and places / Topical Planets in Houses",
         "Dignities and places / Planetary Dignity Evaluation (Hellenistic/Rhetorius reconstruction)")


def _export_faults(at, owned=OWNED):
    """Each export table pyarrow cannot type, column by column."""
    faults = []
    for name, rows in _export_tables(at):
        if owned is not None and name not in owned:
            continue
        try:
            pa.Table.from_pandas(pd.DataFrame(rows))
        except (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError) as error:
            faults.append(f"{name}: {error}")
    return faults


def _every_page(date, hhmm=None, lat=None, lon=None, patch=None, owned=OWNED):
    """Render every page and read the export; return what went wrong."""
    problems, export_faults, last = [], [], None
    for page in PAGES:
        at, fallbacks = _render(date, page, hhmm, lat, lon, patch=patch)
        if len(at.exception):
            problems.append(f"{page}: " + "; ".join(e.value.splitlines()[-1] for e in at.exception if e.value))
            continue
        problems.extend(f"{page}: {message}" for message in fallbacks)
        last = at
    if last is not None:
        export_faults = _export_faults(last, owned)
    return problems + export_faults, last


# --- 1. The merge rule itself ---------------------------------------------

def test_the_merge_splits_a_label_list_label_by_label_in_a_fixed_order(engine):
    """Two outcomes sharing some labels and differing on others: the shared
    ones are settled, in first-seen order, and the rest go to the channel,
    each with the connection's reason and source; the channel's own entries
    are kept; the other fields merge as before."""
    Unresolved = engine["UnresolvedResult"]
    sect = Unresolved("Mercury's sect is unassigned", "Gr. Intr. VII.1, 37", status="unassigned")
    first = {"Positive Labels": ["Halb (10)", "Received by Venus", "Bright degree (11)", "Swift (9)"],
             "Unresolved Positive Labels": (sect,),
             "Negative Labels": ["Burned path (40)"], "Count": 4}
    second = {"Positive Labels": ["Halb (10)", "Bright degree (11)", "Receives Venus", "Swift (9)", "Swift (9)"],
              "Unresolved Positive Labels": (sect,),
              "Negative Labels": ["Burned path (40)"], "Count": 5}
    key = ("Abu Ma'shar", (("Jupiter", 181.9), ("Venus", 177.1)), 4.8, 1.0, "why")
    connection = Unresolved("an ordinary connection is unresolved", "Sahl, The Introduction Ch. 3, 20–21")
    context = ([{key: False}, {key: True}], {key: connection})

    merged = engine["_connection_merge"]([first, second], context)

    assert merged["Positive Labels"] == ["Halb (10)", "Bright degree (11)", "Swift (9)"]
    assert merged["Negative Labels"] == ["Burned path (40)"]
    channel = merged["Unresolved Positive Labels"]
    assert channel[0] is sect
    opened = channel[1:]
    # First-seen order across the outcomes: the first outcome's, then what
    # the second adds.
    assert [result.reason.split(":")[0] for result in opened] == ["Received by Venus", "Swift (9)", "Receives Venus"]
    for result in opened:
        assert isinstance(result, Unresolved) and result.status == "unresolved"
        assert "an unresolved connection between Venus and Jupiter" in result.reason, result.reason
        assert "an ordinary connection is unresolved" in result.reason, result.reason
        assert result.source == "Sahl, The Introduction Ch. 3, 20–21"
    assert opened[0].alternatives == (("holds", True), ("does not hold", False))
    # A field outside the rule merges as before.
    assert isinstance(merged["Count"], Unresolved)
    # The same outcomes give the same answer every time.
    again = engine["_connection_merge"]([first, second], context)
    assert repr(again) == repr(merged)
    # A list with no channel still collapses, and gains none.
    plain = engine["_connection_merge"]([{"clauses": ["a", "b"]}, {"clauses": ["a"]}])
    assert isinstance(plain["clauses"], Unresolved)
    assert "Unresolved clauses" not in plain


def test_every_channel_is_the_fields_name_after_unresolved(engine):
    for field, channel in engine["_LABEL_CHANNELS"].items():
        assert channel == f"Unresolved {field}"


# --- 1b. The Planetary Condition's counts, by hand -------------------------
#
# Two outcomes for one planet, built by hand, differing by a reception label
# (good fortune), a strength label, a dissolved enclosure (a misfortune entry
# kept in Positive Labels), a weakness label and a Moon defect (the second
# outcome has three, the first two). Worked out before the engine was asked:
#
#   outcome 1: Positive  GF1, Received by Venus | S1, S2 | dissolved
#              Negative  W1, W2 | M1 | D1, D2
#              votes +GF1 +S1 +S2 +dissolved +reception = 5,
#                    -W1 -W2 -M1 -Corruption = 4        Net +1, Indeterminate
#   outcome 2: Positive  GF1 | S1
#              Negative  W1 | M1 | D1, D2, D3
#              votes +GF1 +S1 = 2, -W1 -M1 -Corruption = 3  Net -1, Indeterminate
#
#   settled by section: Good Fortune 1 (GF1), Strength 1 (S1), Weakness 1
#   (W1), Misfortune 1 (M1), Moon Defects 2 (D1, D2)
#   open: Received by Venus, S2, dissolved, W2, D3 = 5, plus the one
#   Mercury-sect testimony both outcomes already hold open: Unresolved 6
#   settled votes: +GF1 +S1, -W1 -M1 -Corruption (one vote, held by both):
#   Known Net -1. Were the corruptions to vote one by one, D1 and D2 would
#   both settle and Known Net would read -2.
#   Net is open (+1 or -1); Condition is Indeterminate either way.

def _condition_outcome(first, good_fortune=None):
    Unresolved = __import__("engine").UnresolvedResult
    sect = Unresolved("Domain/hayz (13)", "Gr. Intr. VII.1, 37", status="unassigned")
    if first:
        positive = ["GF1 (1)", "Received by Venus (middling, via house)", "S1 (21)", "S2 (22)",
                    "Enclosure by the infortunes dissolved by Sun (60-61)"]
        negative = ["W1 (30)", "W2 (31)", "M1 (47)", "D1 (64)", "D2 (65)"]
        n_good, n_strength, n_weak, n_moon, net = 2, 2, 2, 2, 1
    else:
        positive = ["GF1 (1)", "S1 (21)"]
        negative = ["W1 (30)", "M1 (47)", "D1 (64)", "D2 (65)", "D3 (66)"]
        n_good, n_strength, n_weak, n_moon, net = 1, 1, 1, 3, -1
    misfortune = (len(negative) - n_weak - n_moon) + (len(positive) - n_good - n_strength)
    return {"Moon": {
        "Good Fortune": n_good if good_fortune is None else good_fortune, "Strength": n_strength,
        "Weakness": n_weak, "Misfortune": misfortune, "Moon Defects": n_moon,
        "Positive Score": len(positive), "Negative Score": len(negative), "Net": net,
        "Condition": "Indeterminate",
        "Known Good Fortune": n_good, "Known Weakness": n_weak, "Known Net": net,
        "Known Strength": n_strength, "Known Misfortune": misfortune, "Known Moon Defects": n_moon,
        "Unresolved Count": 1,
        "Positive Labels": positive, "Unresolved Positive Labels": (sect,),
        "Negative Labels": negative, "Unresolved Negative Labels": (),
    }}


def _connection_context(engine):
    key = ("Abu Ma'shar", (("Moon", 10.0), ("Venus", 20.0)), 0.5, 1.0, "why")
    connection = engine["UnresolvedResult"]("the encounter history does not establish whether exact contact "
                                            "was completed", "Sahl, The Introduction Ch. 3, 7–10")
    return [{key: False}, {key: True}], {key: connection}


def test_the_condition_finisher_counts_what_every_outcome_holds(engine):
    outcomes = [_condition_outcome(True), _condition_outcome(False)]
    context = _connection_context(engine)
    merged = engine["_connection_merge"](outcomes, context)
    moon = engine["_abu_mashar_condition_known"](merged, outcomes, context)["Moon"]

    known = {name: moon[f"Known {name}"] for name in
             ("Good Fortune", "Strength", "Weakness", "Misfortune", "Moon Defects", "Net")}
    assert known == {"Good Fortune": 1, "Strength": 1, "Weakness": 1, "Misfortune": 1, "Moon Defects": 2,
                     "Net": -1}, known
    assert all(type(value) is int for value in known.values()), known
    assert moon["Unresolved Count"] == 6
    assert moon["Positive Labels"] == ["GF1 (1)", "S1 (21)"]
    assert moon["Negative Labels"] == ["W1 (30)", "M1 (47)", "D1 (64)", "D2 (65)"]
    assert [value.reason.split(":")[0] for value in moon["Unresolved Positive Labels"][1:]] == [
        "Received by Venus (middling, via house)", "S2 (22)", "Enclosure by the infortunes dissolved by Sun (60-61)"]
    assert [value.reason.split(":")[0] for value in moon["Unresolved Negative Labels"]] == ["W2 (31)", "D3 (66)"]
    # Net stays open, with its known subtotal and both totals; the verdict
    # is the same either way and so is settled.
    net = moon["Net"]
    assert isinstance(net, engine["UnresolvedResult"])
    assert net.reason.startswith("known subtotal -1; the rest depends on an unresolved connection between "
                                 "Moon and Venus"), net.reason
    assert [value for _name, value in net.alternatives] == [1, -1]
    assert moon["Condition"] == "Indeterminate"
    # The engine's own counts that differ name the settled subtotal.
    for name, subtotal in (("Good Fortune", 1), ("Strength", 1), ("Weakness", 1), ("Misfortune", 1),
                           ("Moon Defects", 2), ("Positive Score", 2)):
        assert moon[name].reason.startswith(f"known subtotal {subtotal}; "), (name, moon[name].reason)
    # Equal in both outcomes (5 and 5), so left as the engine gave it.
    assert moon["Negative Score"] == 5


def test_an_unassigned_mercury_and_an_undecided_connection_keep_both_causes(engine):
    """Both causes on one planet: each outcome's Good Fortune is already
    open under Mercury's sect, and the outcomes differ. In a chart this needs
    Mercury exactly on the Sun and an undecided connection that changes one
    of his own labels; it is built by hand here. The reason names both, and
    the possible totals are listed within each outcome."""
    Unresolved = engine["UnresolvedResult"]

    def sect_open(subtotal):
        return Unresolved(f"known subtotal {subtotal}; the domain testimony depends on Mercury sect",
                          "Gr. Intr. VII.1, 37", status="unassigned",
                          alternatives=(("if Mercury is diurnal", subtotal + 1), ("if Mercury is nocturnal", subtotal)))
    outcomes = [_condition_outcome(True, sect_open(2)), _condition_outcome(False, sect_open(1))]
    context = _connection_context(engine)
    merged = engine["_connection_merge"](outcomes, context)
    moon = engine["_abu_mashar_condition_known"](merged, outcomes, context)["Moon"]
    value = moon["Good Fortune"]
    assert value.reason == ("known subtotal 1; the domain testimony depends on Mercury sect; and the rest depends "
                            "on an unresolved connection between Moon and Venus (the encounter history does not "
                            "establish whether exact contact was completed)"), value.reason
    assert value.alternatives == (("permitted outcome 1, if Mercury is diurnal", 3),
                                  ("permitted outcome 1, if Mercury is nocturnal", 2),
                                  ("permitted outcome 2, if Mercury is diurnal", 2),
                                  ("permitted outcome 2, if Mercury is nocturnal", 1))
    assert value.display_alternatives is True
    assert "Gr. Intr. VII.1, 37" in value.source and "Sahl, The Introduction Ch. 3" in value.source
    assert moon["Known Good Fortune"] == 1


# --- 2. The Florence chart ------------------------------------------------

@pytest.fixture(scope="module")
def florence_condition():
    """The engine's Planetary Condition for the Florence chart."""
    import engine as E
    lat, lon = 43.7792, 11.2463
    jd = E.civil_local_to_jd_ut(1957, 8, 17, 15 + 48 / 60, lon / 15)
    chart = E.calculate_traditional_chart_jd(jd, lat, lon)
    p, sect = chart["planetary_data"], chart["sect"]
    essential = E.evaluate_essential_dignities(p, sect)
    accidental = E.evaluate_accidental_dignities(p, chart["houses"], sect, chart["julian_day"],
                                                 armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=lat)
    sim = E._simulate_forward(p, chart["julian_day"])
    return E, E.evaluate_abu_mashar_condition(p, chart["houses"], sect, essential, accidental,
                                              chart["julian_day"], chart["ascendant"], sim)


@pytest.fixture(scope="module")
def open_label_condition():
    """The engine's Planetary Condition for OPEN_DATE, OPEN_TIME (LMT, Florence)."""
    import engine as E
    lat, lon = 43.7792, 11.2463
    jd = E.civil_local_to_jd_ut(1575, 12, 30, 10.0, lon / 15)
    chart = E.calculate_traditional_chart_jd(jd, lat, lon)
    p, sect = chart["planetary_data"], chart["sect"]
    essential = E.evaluate_essential_dignities(p, sect)
    accidental = E.evaluate_accidental_dignities(p, chart["houses"], sect, chart["julian_day"],
                                                 armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=lat)
    sim = E._simulate_forward(p, chart["julian_day"])
    return E, E.evaluate_abu_mashar_condition(p, chart["houses"], sect, essential, accidental,
                                              chart["julian_day"], chart["ascendant"], sim)


def test_florence_label_lists_are_lists_and_the_open_label_carries_its_connection(florence_condition,
                                                                                 open_label_condition):
    E, condition = florence_condition
    venus, jupiter = condition["Venus"], condition["Jupiter"]
    for row in condition.values():
        assert isinstance(row["Positive Labels"], list) and isinstance(row["Negative Labels"], list)
    assert "Receives Jupiter into its own house" in venus["Positive Labels"]               # ruling 60 (ruling 64)
    assert "Mutual reception with Mars" in venus["Positive Labels"]
    assert venus["Unresolved Positive Labels"] == () and jupiter["Unresolved Positive Labels"] == ()   # ruling 64
    assert (venus["Known Good Fortune"], venus["Unresolved Count"]) == (11, 0)              # ruling 64
    assert (jupiter["Known Good Fortune"], jupiter["Unresolved Count"]) == (8, 0)           # ruling 64
    assert venus["Good Fortune"] == 11                                                       # ruling 64
    assert venus["Net"] == venus["Known Net"] == 1
    # The open label, at a chart where one still opens (ruling 64).
    E, condition = open_label_condition
    venus, mercury = condition["Venus"], condition["Mercury"]
    assert "Mutual reception with Jupiter" in venus["Positive Labels"]
    (opened,) = venus["Unresolved Positive Labels"]
    assert opened.reason.startswith("Receives Mercury into its own triplicity: holds under one permitted completion")
    assert "between Mercury and Venus" in opened.reason
    (opened,) = mercury["Unresolved Positive Labels"]
    assert opened.reason.startswith("Received by Venus (middling (140), via triplicity): holds under one")
    # Known subtotals: the settled labels; Unresolved: the open one.
    assert (venus["Known Good Fortune"], venus["Unresolved Count"]) == (5, 1)
    assert (mercury["Known Good Fortune"], mercury["Unresolved Count"]) == (6, 1)
    # The engine's own Good Fortune names the subtotal and keeps both totals.
    assert venus["Good Fortune"].reason.startswith("known subtotal 5; the rest depends on an unresolved connection")
    assert [value for _name, value in venus["Good Fortune"].alternatives] == [6, 5]
    # Reception votes once, and Venus is received either way: Net is settled.
    assert venus["Net"] == venus["Known Net"] == -3


def test_florence_renders_every_page_and_the_export():
    problems, at = _every_page(FLORENCE_DATE, FLORENCE_TIME)
    assert not problems, "\n".join(problems)


def test_florence_shows_settled_and_open_labels_on_the_page_and_in_the_export():
    at, fallbacks = _render(FLORENCE_DATE, "configurations", FLORENCE_TIME)
    assert_no_exception(at, "configurations, Florence")
    assert not fallbacks, fallbacks
    frame = next(node for heading, node in table_nodes(at) if heading == "Planetary Condition").value
    venus = frame[frame["Planet"] == "Venus"].iloc[0]
    assert venus["Good Fortune"] == 11 and pd.isna(venus["Unresolved"]), venus.to_dict()     # ruling 64
    cell = venus["Good Fortune / Strength"]
    assert "Mutual reception with Mars" in cell
    assert "Receives Jupiter into its own house" in cell and "Unresolved —" not in cell, cell  # ruling 64
    # The open label on the page and in the export, at a chart where one still opens (ruling 64).
    at, fallbacks = _render(OPEN_DATE, "configurations", OPEN_TIME)
    assert_no_exception(at, "configurations, 1575-12-30")
    assert not fallbacks, fallbacks
    frame = next(node for heading, node in table_nodes(at) if heading == "Planetary Condition").value
    venus = frame[frame["Planet"] == "Venus"].iloc[0]
    assert venus["Good Fortune"] == 5 and venus["Unresolved"] == 1, venus.to_dict()
    cell = venus["Good Fortune / Strength"]
    assert "Mutual reception with Jupiter" in cell
    assert ("Unresolved — Receives Mercury into its own triplicity: holds under one permitted completion of an "
            "unresolved connection between Mercury and Venus") in cell, cell
    assert any("An open label is listed with the others" in node.value for node in at.main.caption)

    rows = at.session_state["_analysis_export"]["results"]["Configurations"]["Planetary Condition"][0]["rows"]
    exported = next(row for row in rows if row["Planet"] == "Venus")
    assert exported["Good Fortune / Strength"] == cell
    assert exported["Unresolved"] == 1
    pa.Table.from_pandas(pd.DataFrame(rows))

    box = [node for node in at.main.selectbox if node.key == "planetary_condition_detail"][0]
    box.select("Venus")
    at.run(timeout=300)
    assert_no_exception(at, "the Planetary Condition detail for Venus")
    line = next(node.value for node in at.main.markdown if node.value.startswith("**Venus.**"))
    assert "Good Fortune Unresolved — known subtotal 5; the rest depends on an unresolved connection" in line, line
    bullets = next(node.value for node in at.main.markdown if node.value.startswith("**Good Fortune / Strength**"))
    assert "- Mutual reception with Jupiter" in bullets
    assert "- Unresolved — Receives Mercury into its own triplicity: holds under one" in bullets, bullets


# --- 2b. A testimony's facts, and the Moon's defects ----------------------

def test_a_testimonys_facts_split_into_settled_and_open(tmp_path, monkeypatch):
    """1240-03-31 (Florence, 14:30 LMT), whose Weakness testimony 93 for
    Venus turns on an undecided connection: its facts used to collapse to
    one UnresolvedResult; the open facts now follow the settled ones, each
    with the connection it turns on, in the export and in the row detail."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at, fallbacks = _render("1240-03-31", "configurations")
    assert_no_exception(at, "configurations 1240-03-31")
    assert not fallbacks, fallbacks
    rows = at.session_state["_analysis_export"]["results"]["Configurations"]["Weakness of the Planets"][0]["rows"]
    testimonies = [t for row in rows for t in row["Testimonies"] if t.get("Unresolved facts")]
    assert testimonies, "no testimony with open facts"
    for testimony in testimonies:
        assert isinstance(testimony["facts"], list)
        for fact in testimony["Unresolved facts"]:
            assert fact["result_type"] == "UnresolvedResult"
            assert "holds under some permitted completions of an unresolved connection between" in fact["reason"]
            assert fact["source"].startswith("Sahl, The Introduction Ch. 3")
    opened = [fact["display"] for t in testimonies for fact in t["Unresolved facts"]]

    # The Markdown and HTML reports' testimony cell (_export_cell) carries
    # the open facts after the settled ones.
    report = at.session_state["_analysis_markdown"]
    for text in opened:
        assert text in report, text

    # The row detail under the grid prints each open fact as a caption.
    index = next(i for i, row in enumerate(rows) if any(t.get("Unresolved facts") for t in row["Testimonies"]))
    at.session_state["weakness_of_the_planets_grid"] = {"selection": {"rows": [index], "columns": []}}
    at.run(timeout=300)
    assert_no_exception(at, "the Weakness row detail on 1240-03-31")
    captions = [node.value for node in at.main.caption]
    for text in opened:
        assert text in captions, (text, captions)


def _moon_outcome(extra):
    """One outcome of Sahl's Corruption of the Moon, built by hand: 103 by one
    clause, 112 by two (slow and waning), and 110 only when ``extra``."""
    testimonies = {n: {"matched": False, "clauses": []} for n in range(103, 113)}
    testimonies[103] = {"matched": True, "clauses": ["Burned, within 12 degrees of the Sun"]}
    testimonies[112] = {"matched": True, "clauses": ["Slow in course", "Waning in light"]}
    labels = ["Burned, within 12 degrees of the Sun (103)", "Slow in course (112)", "Waning in light (112)"]
    if extra:
        testimonies[110] = {"matched": True, "clauses": ["In the burned path"]}
        labels.append("In the burned path (110)")
    return {"testimonies": testimonies, "unique_testimony_count": sum(t["matched"] for t in testimonies.values()),
            "matching_instances": len(labels), "labels": labels}


def test_the_moons_defects_split_on_the_page_and_in_the_export(monkeypatch):
    """No chart in hand leaves one of Sahl's ten Moon defects open, so the
    evaluator is made to return the merge of two outcomes that differ by one
    defect: the settled defects and the open one share the Defects cell;
    Count counts the settled TESTIMONIES (103 and 112: two), not their
    clauses (three), and Unresolved the open testimony (110)."""
    at = make_app(date="1240-05-23", page="configurations")
    import engine

    def two_outcomes(*_args, **_kwargs):
        return engine._connection_merge([_moon_outcome(False), _moon_outcome(True)])
    monkeypatch.setattr(engine, "evaluate_corruption_of_the_moon", two_outcomes)
    logger = logging.getLogger("streamlit.dataframe_util")
    handler = _Fallbacks()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        at.run(timeout=300)
    finally:
        logger.removeHandler(handler)
    assert_no_exception(at, "configurations with an open Moon defect")
    assert not handler.messages, handler.messages
    (row,) = at.session_state["_analysis_export"]["results"]["Configurations"]["Corruption of the Moon"][0]["rows"]
    assert row["Count"] == 2 and type(row["Count"]) is int, row
    assert row["Unresolved"] == 1, row
    assert isinstance(row["Defects"], str)
    assert row["Defects"].startswith("Burned, within 12 degrees of the Sun (103), Slow in course (112), "
                                     "Waning in light (112), Unresolved — In the burned path (110): holds under "
                                     "one permitted completion of an unresolved connection"), row
    assert row["Defects"].endswith("[3 settled clauses across 2 of the ten testimonies]"), row
    assert "Status" not in row
    frame = next(node for heading, node in table_nodes(at) if heading == "Corruption of the Moon").value
    assert frame["Count"].tolist() == [2] and frame["Unresolved"].tolist() == [1]


def test_the_ii3_refinements_pass_the_display_boundary():
    """Found by the sweep (its chart 284): PN IV II.3, 9-12's reception row
    read from both completions of an undecided connection is an
    UnresolvedResult, and the Timing page drew the refinements' frame raw --
    an Arrow fallback, and the result's repr in the Reads cell."""
    date, hhmm, lat, lon = sweep_chart(284)
    at, fallbacks = _render(date, "timing", hhmm, lat, lon)
    assert_no_exception(at, f"timing {date}")
    assert not fallbacks, fallbacks
    frame = next(node.value for node in at.main.dataframe
                 if "Refinement" in node.value.columns and "Reads" in node.value.columns)
    reads = frame[frame["Refinement"] == "Received, or not (root; revolution)"]["Reads"].iloc[0]
    assert reads.startswith("Unresolved — the result depends on an unresolved connection"), reads
    assert "UnresolvedResult(" not in reads


# --- 3. The Dignities page's two columns under an unassigned Mercury ------

def _mercury_on_the_sun():
    """Mercury moved onto the Sun's longitude, the one case in which his
    sect is unassigned; applied after make_app, which reloads the engine."""
    import engine
    original = engine.calculate_traditional_chart_jd

    def patched(*args, **kwargs):
        chart = original(*args, **kwargs)
        chart['planetary_data']['Mercury']['longitude'] = chart['planetary_data']['Sun']['longitude']
        return chart
    engine.calculate_traditional_chart_jd = patched
    return lambda: setattr(engine, "calculate_traditional_chart_jd", original)


@pytest.fixture
def conjunction_dignities():
    restore = []
    at, fallbacks = _render("1240-05-23", "dignities", patch=lambda: restore.append(_mercury_on_the_sun()))
    try:
        yield at, fallbacks
    finally:
        for undo in restore:
            undo()


def test_dignities_page_logs_no_arrow_fallback_under_an_unassigned_mercury(conjunction_dignities):
    at, fallbacks = conjunction_dignities
    assert_no_exception(at, "dignities with Mercury on the Sun")
    assert not fallbacks, fallbacks


def test_dignity_evaluation_and_topical_net_are_one_type_in_the_export(conjunction_dignities):
    at, _fallbacks = conjunction_dignities
    results = at.session_state["_analysis_export"]["results"]["Dignities and places"]
    dignity = results["Planetary Dignity Evaluation (Hellenistic/Rhetorius reconstruction)"][0]["rows"]
    for name in ("Ranking score", "Acc"):
        assert {type(row[name]).__name__ for row in dignity} == {"int"}, name
    mercury = next(row for row in dignity if row["Planet"] == "Mercury")
    assert mercury["Unresolved"] == 1 and dignity[-1]["Planet"] == "Mercury"
    assert "Domain/hayz unassigned" in mercury["Accidental Conditions"]
    topical = results["Topical Planets in Houses"][0]["rows"]
    assert {type(row["Net"]).__name__ for row in topical} == {"int"}
    assert {type(row["Lean"]).__name__ for row in topical} == {"str"}
    assert next(row for row in topical if row["Planet"] == "Mercury")["Unresolved"] == 2
    for rows in (dignity, topical):
        pa.Table.from_pandas(pd.DataFrame(rows))


def test_the_planetary_condition_export_types_under_an_open_verdict():
    """Mercury on the Sun on 1240-07-22: his verdict is Good or
    Indeterminate by his sect, so Verdict must be text in every row (the
    open one as its sentence) and the whole table must type in pyarrow."""
    restore = []
    try:
        at, fallbacks = _render("1240-07-22", "configurations",
                                patch=lambda: restore.append(_mercury_on_the_sun()))
    finally:
        for undo in restore:
            undo()
    assert_no_exception(at, "configurations 1240-07-22 with Mercury on the Sun")
    assert not fallbacks, fallbacks
    rows = at.session_state["_analysis_export"]["results"]["Configurations"]["Planetary Condition"][0]["rows"]
    assert {type(row["Verdict"]).__name__ for row in rows} == {"str"}
    mercury = next(row for row in rows if row["Planet"] == "Mercury")
    assert mercury["Verdict"].startswith("Unassigned — the heuristic class is evaluated under both"), mercury
    assert rows[-1]["Planet"] == "Mercury"
    for name in ("Good Fortune", "Strength", "Weakness", "Misfortune", "Net"):
        assert {type(row[name]).__name__ for row in rows} == {"int"}, name
    pa.Table.from_pandas(pd.DataFrame(rows))


# --- 4. Ordinary charts read as main did ----------------------------------

ORDINARY = ("1240-05-23", "1240-05-25", "1240-05-26", "1240-09-18", "1240-10-05", "1240-01-04",
            "1239-06-14", "1700-02-28")
TOUCHED = {
    "Configurations": ("Planetary Condition", "Corruption of the Moon", "Strength of the Planets",
                       "Weakness of the Planets"),
    # The export files the dignity grid under the page's own heading (the
    # hostile pass of 2026-10-03, L5-10).
    "Dignities and places": ("Planetary Dignity Evaluation (Hellenistic/Rhetorius reconstruction)",
                             "Topical Planets in Houses"),
}
TOUCHED_PAGE = {"configurations": ("Planetary Condition", "Corruption of the Moon", "Strength of the Planets",
                                   "Weakness of the Planets"),
                "dignities": ("Planetary Dignity Evaluation",)}


# The two export tables whose testimony facts carry an unrounded witness,
# "Speed in longitude: 0.96 (unrounded: 0.9553848190007698)": the fixture
# keeps their rows, and compares them word for word and printed number for
# printed number, the witness alone within WITNESS_BOUND. Every other
# table is kept as a SHA-256 of its exact JSON, and must carry no witness
# and no float printed to ten places or more, which a hash cannot hold
# across builds.
WITNESSED = ("export / Strength of the Planets", "export / Weakness of the Planets")
_WITNESS = re.compile(r"\(unrounded: (-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\)")
_LONG_FLOAT = re.compile(r"-?\d+\.\d{10,}")
# Degrees, or degrees a day. The witnesses differed between two builds of
# the same source and the same pyswisseph by up to 2.7e-6 (GCC 13 and
# GCC 16), and by up to 1.5e-5 under -O3 -ffast-math; moving the chart one
# minute moves at least three witnesses of every chart by more than this.
WITNESS_BOUND = 2e-5
# The largest witness difference measured between two builds: the stock
# build against the -O3 -ffast-math one, 1.4639e-5 (the comment above's
# 1.5e-5, read to five figures). The bound is held above it and within
# twice it (test_the_bound_stays_within_twice_the_largest_measured_build_difference).
LARGEST_MEASURED_BUILD_DIFFERENCE = 1.4639e-5


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _digest(value):
    """SHA-256 of the exact JSON."""
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def ordinary_snapshot(date):
    """The cells this branch could change, for one chart: every touched
    table's export rows and its drawn frame, as JSON reads them back."""
    shown = {}
    for page, headings in TOUCHED_PAGE.items():
        at, _fallbacks = _render(date, page)
        assert_no_exception(at, f"{date} {page}")
        for heading, node in table_nodes(at):
            if heading in headings or heading == "Answer key: testimonies in words":
                frame = node.value
                shown.setdefault(f"page / {heading}", []).append(
                    [list(map(str, frame.columns)), frame.astype(str).values.tolist()])
        for table in at.main.table:
            frame = table.value
            if "Net" in frame.columns and "Standing" in frame.columns:
                shown["page / Rhetorius / PN IV readings"] = [list(map(str, frame.columns)),
                                                              frame.astype(str).values.tolist()]
        export = at.session_state["_analysis_export"]["results"]
        for export_page, export_headings in TOUCHED.items():
            for heading in export_headings:
                for entry in export.get(export_page, {}).get(heading, []):
                    shown[f"export / {heading}"] = json.loads(json.dumps(entry["rows"], default=str))
    return shown


def ordinary_record(date):
    """What the fixture keeps of one chart: the witnessed tables' rows, and
    every other table's digest."""
    shown = ordinary_snapshot(date)
    unportable = [name for name, value in shown.items()
                  if name not in WITNESSED and (_WITNESS.search(_json(value)) or _LONG_FLOAT.search(_json(value)))]
    assert not unportable, f"{date}: these tables carry an unrounded number; add them to WITNESSED: {unportable}"
    return {"digests": {name: _digest(value) for name, value in shown.items() if name not in WITNESSED},
            "rows": {name: value for name, value in shown.items() if name in WITNESSED}}


def write_ordinary_fixture(path=FIXTURE):
    """Write the fixture from this build: ``python3 tests/test_label_merge_2026_09_25.py --write``."""
    record = {date: ordinary_record(date) for date in ORDINARY}
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def row_differences(actual, expected, where=""):
    """Every place `actual` reads otherwise than `expected`: keys, row
    counts and order, types, every word and every printed number exact; an
    unrounded witness may differ by WITNESS_BOUND. Empty when they agree."""
    if type(actual) is not type(expected):
        return [f"{where}: {actual!r} is not {expected!r}"]
    if isinstance(expected, dict):
        if sorted(actual) != sorted(expected):
            return [f"{where}: keys {sorted(actual)} are not {sorted(expected)}"]
        return [d for key in expected for d in row_differences(actual[key], expected[key], f"{where}/{key}")]
    if isinstance(expected, list):
        if len(actual) != len(expected):
            return [f"{where}: {len(actual)} entries, not {len(expected)}"]
        return [d for i, (a, e) in enumerate(zip(actual, expected)) for d in row_differences(a, e, f"{where}/{i}")]
    if isinstance(expected, str):
        if _WITNESS.sub("(unrounded: #)", actual) != _WITNESS.sub("(unrounded: #)", expected):
            return [f"{where}: {actual!r} is not {expected!r}"]
        return [f"{where}: the witness {a} is not {e} within {WITNESS_BOUND}"
                for a, e in zip(_WITNESS.findall(actual), _WITNESS.findall(expected))
                if not abs(float(a) - float(e)) <= WITNESS_BOUND]
    return [] if actual == expected else [f"{where}: {actual!r} is not {expected!r}"]


@pytest.mark.parametrize("date", ORDINARY)
def test_on_ordinary_charts_every_touched_cell_equals_mains(date):
    """The fixture was written from main by ``write_ordinary_fixture``
    (``tests/fixtures/label_merge_ordinary_2026_09_25.json``); on charts
    where nothing is open, not a cell may differ, but for an unrounded
    witness within WITNESS_BOUND (ruling 142)."""
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))[date]
    actual = ordinary_record(date)
    assert sorted(actual["digests"]) == sorted(expected["digests"])
    assert sorted(actual["rows"]) == sorted(expected["rows"]) == sorted(WITNESSED)
    differ = [name for name in expected["digests"] if actual["digests"][name] != expected["digests"][name]]
    differ += [d for name in WITNESSED for d in row_differences(actual["rows"][name], expected["rows"][name], name)]
    assert not differ, f"{date}: these tables no longer read as main did: {differ[:20]}"


def _witnesses(rows):
    """Each witness of the rows by planet, testimony, fact and place."""
    return {(row["Planet"], testimony["n"], fact.split(":")[0], i): float(number)
            for row in rows for testimony in row["Testimonies"] for fact in testimony["facts"]
            for i, number in enumerate(_WITNESS.findall(fact))}


@pytest.mark.parametrize("date", ORDINARY)
def test_a_chart_a_minute_off_moves_every_solar_distance_witness_past_the_bound(date):
    """The bound's other side: it is not so wide that a chart drawn a minute
    off reads as the same chart. Every signed distance from the Sun (the
    witness of testimonies 84 and 93 in these charts) moves past it."""
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))[date]["rows"]
    assert LOCAL_TIME.minute < 59 and LOCAL_TIME.second == 0
    later = time(LOCAL_TIME.hour, LOCAL_TIME.minute + 1)
    at, _fallbacks = _render(date, "configurations", hhmm=later)
    assert_no_exception(at, f"{date} configurations at {later}")
    export = at.session_state["_analysis_export"]["results"]["Configurations"]
    before, after = {}, {}
    for name in WITNESSED:
        before.update({(name,) + key: value for key, value in _witnesses(expected[name]).items()
                       if key[2].startswith("Signed distance from the Sun")})
        rows = json.loads(json.dumps(export[name.removeprefix("export / ")][0]["rows"], default=str))
        after.update({(name,) + key: value for key, value in _witnesses(rows).items()})
    assert before, f"{date}: no signed distance from the Sun among the witnesses"
    assert not set(before) - set(after), f"{date}: the chart a minute off lacks {sorted(set(before) - set(after))}"
    within = [(key, abs(after[key] - value)) for key, value in before.items()
              if not abs(after[key] - value) > WITNESS_BOUND]
    assert not within, f"{date}: a minute's move left these witnesses within {WITNESS_BOUND}: {within}"


def test_the_bound_stays_within_twice_the_largest_measured_build_difference():
    """The bound's own pin. The minute pin above holds it below the smallest
    one-minute move of a solar distance (about 1.8e-4), nearly nine times
    it; this holds it near what was measured: above the largest difference
    between two builds, and no more than twice that."""
    assert LARGEST_MEASURED_BUILD_DIFFERENCE < WITNESS_BOUND <= 2 * LARGEST_MEASURED_BUILD_DIFFERENCE, WITNESS_BOUND


def _printed_numbers(text):
    """Each number the text prints outside its witnesses, as (start, end)."""
    witnessed = [m.span(1) for m in _WITNESS.finditer(text)]
    return [m.span() for m in re.finditer(r"\d+", text)
            if not any(a <= m.start() < b for a, b in witnessed)]


def _leaves(value, where=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, where + (key,))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _leaves(item, where + (i,))
    else:
        yield where, value


def _with(value, where, new):
    if not where:
        return new
    copy = list(value) if isinstance(value, list) else dict(value)
    copy[where[0]] = _with(value[where[0]], where[1:], new)
    return copy


def _mutations(rows):
    """Each one-place change to `rows`: (what, the changed rows, whether the
    comparison must call it a difference)."""
    for i in range(len(rows)):
        yield "row", rows[:i] + rows[i + 1:], True
    for where, leaf in _leaves(rows):
        if isinstance(leaf, int):
            yield "count", _with(rows, where, leaf + 1), True
            continue
        for start, end in _printed_numbers(leaf):
            last = str((int(leaf[end - 1]) + 1) % 10)
            yield "number", _with(rows, where, leaf[:end - 1] + last + leaf[end:]), True
        for word in re.finditer(r"[A-Za-z]+", leaf):
            yield "word", _with(rows, where, leaf[:word.start()] + word.group() + "x" + leaf[word.end():]), True
        for witness in _WITNESS.finditer(leaf):
            for step, kind in ((WITNESS_BOUND * 1.01, "witness out"), (WITNESS_BOUND * 0.99, "witness in")):
                moved = repr(float(witness.group(1)) + step)
                yield kind, _with(rows, where, leaf[:witness.start(1)] + moved + leaf[witness.end(1):]), kind == "witness out"


def test_the_witnessed_rows_catch_one_printed_number_one_word_one_row():
    """On the fixture's own rows: each printed digit moved by one, each word
    changed, each row dropped, each count moved, each witness moved past the
    bound is a difference; each witness moved within it is not."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tried = dict.fromkeys(("row", "count", "number", "word", "witness out", "witness in"), 0)
    leaves = [leaf for record in fixture.values() for name in WITNESSED for _where, leaf in _leaves(record["rows"][name])]
    assert {type(leaf) for leaf in leaves} == {int, str}
    wrong = [(date, name) for date, record in fixture.items() for name in WITNESSED
             if row_differences(json.loads(json.dumps(record["rows"][name])), record["rows"][name])]
    for date, record in fixture.items():
        for name in WITNESSED:
            rows = record["rows"][name]
            for kind, changed, differs in _mutations(rows):
                tried[kind] += 1
                if bool(row_differences(changed, rows)) != differs:
                    wrong.append((date, name, kind, changed))
    assert not wrong, wrong[:5]
    assert min(tried.values()) > 0, tried


# --- 5. The guard sweep ---------------------------------------------------

SWEEP_SIZE = 300


def sweep_chart(index):
    """A seeded random date, time and place (LMT, so any longitude works)."""
    rng = random.Random(20260925 * 1000 + index)
    year, month, day = rng.randint(1000, 2600), rng.randint(1, 12), rng.randint(1, 28)
    return (f"{year:04d}-{month:02d}-{day:02d}", time(rng.randint(0, 23), rng.randint(0, 59)),
            round(rng.uniform(-60.0, 62.0), 4), round(rng.uniform(-180.0, 180.0), 4))


@pytest.mark.sweep
@pytest.mark.parametrize("index", range(SWEEP_SIZE))
def test_sweep_every_page_and_the_export(index):
    """No exception, no Arrow fallback on any page, and the export tables
    this branch types (OWNED) one type per column, for SWEEP_SIZE charts.
    Marked ``sweep`` (registered in pytest.ini): it runs on CI with
    the rest; deselect locally with -m "not sweep"."""
    date, hhmm, lat, lon = sweep_chart(index)
    problems, _at = _every_page(date, hhmm, lat, lon)
    assert not problems, f"{date} {hhmm} {lat} {lon}:\n" + "\n".join(problems)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: python3 tests/test_label_merge_2026_09_25.py --write")
    write_ordinary_fixture()
