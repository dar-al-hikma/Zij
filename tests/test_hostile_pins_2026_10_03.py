"""Pins for the survivors of the mutation scan of 2026-10-03 (hostile pass, lane L7).

The maintainers' mutation scan applies one literal change at a time to a copy
of engine.py or app.py and runs a fast, relevant selection of test files
against it. Nine mutations survived every selection: the engine was right, and
no test would have noticed if it stopped being. Each pin below names its
witness outside the engine -- a corpus sentence, a published figure, an
arithmetic identity -- and PASSES today. This file is in every selection the
scan runs, so a mutation of any of these behaviours is now killed here; it
holds no tool-mechanism test, since a test that checks a mutation's original
text is present would detect every mutation by its text and tell the scan
nothing.
"""
from __future__ import annotations

import re

import pytest

from conftest import assert_no_exception, make_app
from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import needs_corpus

# The two pins that read a corpus sentence skip where the corpus is absent (CI),
# as every corpus test does; with the corpus present the skip guard forbids it.
_corpus = needs_corpus()


def _render(page, depth="Course text", date="1240-05-23", **state):
    at = make_app(date=date, page=page)
    at.session_state["_reading_depth"] = depth
    for key, value in state.items():
        at.session_state[key] = value
    at.run(timeout=120)
    assert_no_exception(at, f"{page} at {depth}")
    return at

def test_pin_profection_counts_one_sign_a_year_from_the_ascendant(engine):
    """L7-18 (survivor profection-off-by-one): Fardar page, Chronocrator Matrix
    row 1. Ascendant 15 Aries, born 1240-05-23, target 2026-10-03: 786
    completed years, 786 mod 12 = 6, the seventh sign from Aries is Libra,
    whose lord is Venus (Sahl, The Introduction Ch. 1; PN IV I.1 for the
    turning a sign a year)."""
    from datetime import date
    rows = engine["calculate_time_lords"](15.0, date(1240, 5, 23), date(2026, 10, 3))
    prof = rows[0]
    assert prof["Technique"] == "Annual Profection"
    assert prof["Active Point"] == "Libra" and prof["Active Ruler"] == "Venus"
    assert prof["Details"] == "Age 786 (1 Sign / Year)"


def test_pin_profection_turns_on_the_birthday_itself(engine):
    """L7-19 (survivor profection-birthday): the first birthday is age 1, the
    day before it still age 0."""
    from datetime import date
    on = engine["calculate_time_lords"](15.0, date(1240, 5, 23), date(1241, 5, 23))[0]
    before = engine["calculate_time_lords"](15.0, date(1240, 5, 23), date(1241, 5, 22))[0]
    assert on["Details"] == "Age 1 (1 Sign / Year)" and on["Active Point"] == "Taurus"
    assert before["Details"] == "Age 0 (1 Sign / Year)" and before["Active Point"] == "Aries"


def test_pin_lot_of_exaltation_takes_the_sect_light(engine):
    """L7-21 (survivor lot-sect-light): Sahl, On Nativities 4.1, 6 pairs the
    sect light with its own exaltation degree -- the Sun's 19th of Aries
    (18.0) by day, the Moon's 3rd of Taurus (32.0) by night (Gr. Intr. V.5,
    Figure 38). Ascendant 100, Sun 50, Moon 200."""
    day = {r["Lot Name"]: r["Position"] for r in engine["calculate_classical_lots"](100.0, 50.0, 200.0, "Diurnal")}
    night = {r["Lot Name"]: r["Position"] for r in engine["calculate_classical_lots"](100.0, 50.0, 200.0, "Nocturnal")}
    deg = engine["get_degree_string"]
    assert day["Lot of Exaltation"] == deg((100.0 + 18.0 - 50.0) % 360.0)
    assert night["Lot of Exaltation"] == deg((100.0 + 32.0 - 200.0) % 360.0)


@_corpus
def test_pin_questions_13_7_rank_is_house_triplicity_bound_face(engine):
    """L7-22 (survivor dignity-order-q13): Sahl, On Questions Ch. 13, 7 --
    'the triplicity is below the house, and likewise the bound below the
    triplicity, and the face below the bound' -- read from the corpus."""
    order = engine["DIGNITY_ORDER"]["Questions Ch. 13, 7 (a planet's rank)"]
    assert order == ["house", "triplicity", "bound", "face"]
    text = corpus_file("sahl_on_questions.md").read_text(encoding="utf-8")
    m = re.search(r"the triplicity is below the house, and likewise the bound below the triplicity, and the face below the bound", text)
    assert m, "On Questions 13, 7 no longer reads as the engine's order assumes"


@_corpus
def test_pin_eyesight_rule_74_names_the_sentence_that_says_darkness(engine):
    """L7-23 (survivor locator-eye-74): the eyesight rule label cites On
    Nativities 6.2, 74, and sentence 74 of the corpus is the one with 'darkness
    in his eyes'. A drift to 75 is caught here and nowhere else in the suite."""
    label = engine["_EYE_RULE_74"]
    assert label.startswith("74: ") and "darkness in his eyes" in label
    text = corpus_file("on_nativities.md").read_text(encoding="utf-8")
    assert re.search(r"\b74 And likewise if the Moon was in the middle of Taurus[^\n]*?darkness in his eyes", text)
    assert not re.search(r"\b75 [^\n]{0,200}darkness in his eyes", text)


def _eye_rule_label_is_its_sentence(label, number):
    """A label of the shape N: "quote" names sentence N of On Nativities 6.2,
    and that sentence, in the corpus, says the quoted words exactly. The number
    is the label's own, so a drift of the number looks up the wrong sentence;
    a word changed in the quote is not in the sentence."""
    m = re.fullmatch(r'(\d+): "(.*)"', label, re.S)
    assert m, label
    assert m.group(1) == str(number), label
    text = corpus_file("on_nativities.md").read_text(encoding="utf-8")
    chapter = re.search(r"^## Chapter \[6\.2:\][^\n]*\n(.*?)(?=^#)", text, re.M | re.S)
    assert chapter, "premise: On Nativities 6.2 in the corpus"
    n = int(m.group(1))
    sentence = re.search(rf"^{n} (.*?)(?=(?<![\d.]){n + 1} )", chapter.group(1), re.M | re.S)
    assert sentence, f"no sentence {n} opens a line of 6.2"
    assert m.group(2) in sentence.group(1), (label, sentence.group(1)[:200])


@_corpus
def test_pin_eyesight_rule_60_names_the_sentence_it_quotes(engine):
    """L7-23 (re-pass, partly: the 74 pin's neighbours of the same shape). The
    label cites On Nativities 6.2, 60 (Sahl I p. 549), "The [degrees] indicative
    of chronic illness are:"; a drift to 61, or a word changed, fails here."""
    label = engine["_EYE_RULE_60"]
    assert label.startswith("60: ") and "indicative of chronic illness" in label
    _eye_rule_label_is_its_sentence(label, 60)


@_corpus
def test_pin_eyesight_rule_69_names_the_sentence_it_quotes(engine):
    """L7-23 (re-pass, partly). The label cites On Nativities 6.2, 69 (Sahl I
    p. 551), "Now as for the degrees which indicate the corruption of vision
    especially ..."; a drift to 70, or "vision" made "sight", fails here."""
    label = engine["_EYE_RULE_69"]
    assert label.startswith("69: ") and "corruption of vision" in label
    _eye_rule_label_is_its_sentence(label, 69)


@_corpus
def test_pin_the_lord_of_the_third_in_the_second_keeps_its_wording(engine):
    """L7-24 (survivor quote-masha-3.10.2): a Masha'allah lords cell is pinned
    by three anchor words, so a dropped word survived. On Nativities 3.10, 2
    reads "his siblings will contend with him in his assets, and sorrows will
    enter upon them, and they will seek him"; the cell keeps every word it
    shares with that sentence and adds only its own three ("over" for "in",
    "come" for "enter", and "out"). A word dropped, or one more of the
    paraphrase's own, fails here. The words are compared in order as well as
    as sets: from "his siblings" on, the cell is the sentence with exactly
    these edits -- the three "will"s and the "and" before "sorrows" (a
    semicolon) dropped, "over" for "in", "come" for "will enter", "out" added
    -- so a repeated word dropped ("seek him out" -> "seek out"), which the
    sets cannot see, fails too (re-pass L7-24)."""
    cell = engine["MASHAALLAH_LORDS"][2][3]
    assert cell["cite"] == "3.10, 2"
    text = corpus_file("on_nativities.md").read_text(encoding="utf-8")
    chapter = re.search(r"^### Chapter \[3\.10:\][^\n]*\n(.*?)(?=^#)", text, re.M | re.S).group(1)
    sentence = re.search(r"(?<![\d.])2 (If the lord of the third was in the second .*?)(?= 3 )", chapter, re.S).group(1)
    words = lambda t: set(re.findall(r"[a-z]+", t.lower()))
    cell_words, sahl = words(cell["text"]), words(sentence)
    assert cell_words & sahl == {"his", "siblings", "contend", "with", "him", "assets", "sorrows",
                                 "upon", "them", "and", "they", "seek"}, sorted(cell_words & sahl)
    assert cell_words - sahl == {"over", "come", "out"}, sorted(cell_words - sahl)
    import difflib
    in_order = lambda t: re.findall(r"[a-z]+", t.lower())
    sahl_seq, cell_seq = in_order(sentence), in_order(cell["text"])
    assert sahl_seq.count("siblings") == 1, "premise: one 'siblings' in 3.10, 2"
    sahl_seq = sahl_seq[sahl_seq.index("siblings") - 1:]                 # from "his siblings"
    edits = [(tag, sahl_seq[i1:i2], cell_seq[j1:j2]) for tag, i1, i2, j1, j2
             in difflib.SequenceMatcher(None, sahl_seq, cell_seq, autojunk=False).get_opcodes() if tag != "equal"]
    assert edits == [("delete", ["will"], []), ("replace", ["in"], ["over"]), ("delete", ["and"], []),
                     ("replace", ["will", "enter"], ["come"]), ("delete", ["will"], []),
                     ("insert", [], ["out"])], edits


def test_pin_the_suns_mean_motion_is_59_08(engine):
    """L7-24 (survivor pn4-sun-motion): 59'08\" a day (Gr. Intr. VII.8;
    PN IV IX.7) is 0.98556 degrees; both constants are that to four places."""
    expected = (59.0 + 8.0 / 60.0) / 60.0
    assert abs(engine["PN4_MEAN_SOLAR_DAY_MOTION"] - expected) < 1e-4
    assert abs(engine["AVERAGE_DAILY_MOTION"]["Sun"] - expected) < 1e-4


def test_pin_the_revolution_seed_uses_the_mean_year(engine):
    """L7-24b (survivor mean-year-revolution-search): the solar-return search
    is seeded age x 365.2425 days from the natal instant; a seed off by the
    Julian year would still converge, which is why no behavioural test sees
    it -- pinned by the constant's presence beside the direction year."""
    from conftest import engine_source
    assert engine["PN4_DIRECTION_YEAR_DAYS"] == 365.2425
    assert "jd_natal + float(age) * 365.2425)" in engine_source()


def test_pin_supplement_captions_say_supplement():
    """L7-26 (survivor page-supplement-display): at the fuller depth the
    witness tables on the Findings page are captioned as the supplement they
    are; the word is the reader's only sign that the table is not course text."""
    at = _render("findings", "Course text and supplement")
    captions = [c.value for c in at.main.caption]
    supplement = [c for c in captions if c.startswith("Supplement · display only · ")]
    assert len(supplement) >= 4, [c[:60] for c in captions if "display only" in c]
    assert any(c.startswith("Supplement · display only · Abu Bakr, On Nativities II.1.0") for c in captions), \
        [c[:70] for c in captions if "Abu Bakr" in c]
    plain = _render("findings", "Course text")
    assert not [c for c in plain.main.caption if c.value.startswith("Supplement ·")], "a supplement caption at course depth"
