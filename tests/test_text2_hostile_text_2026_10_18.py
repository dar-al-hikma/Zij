"""Text a person typed, or a file holds, drawn so a reader can tell it apart,
and bounded before anything is built on it.

- The saved charts' picker, and each question that names one saved chart
  (Delete it? Replace it? Open the readings it was saved under?), draw each
  name under a label in which no two names are drawn alike and none is drawn
  blank: a directional control or an invisible character is drawn as its
  code point in brackets. "Alice" and RIGHT-TO-LEFT OVERRIDE + "ecilA" + POP
  DIRECTIONAL FORMATTING were drawn alike, and a name of ZERO WIDTH SPACE was
  drawn blank. A zero-width non-joiner or joiner is left as it is only
  between two letters of one script it shapes (a Persian, a Hindi, a
  Malayalam name); "Al", a joiner and "ice" is marked. Two names whose
  labels are alike once composed, or but for a joiner that shapes nothing,
  are counted. The name itself is kept as typed.
- A chart's name holds at most CHART_NAME_MAX_CHARS characters, and any
  other text a record or the preferences keep at most CHART_TEXT_MAX_CHARS.
  An 8 MiB name was listed, and opening it built every export on it; where
  memory was bounded the export ran out of it. Such a record is now listed
  shortened, can be deleted, and is not loaded, with a sentence; the store is
  not condemned for it. The name box takes no more, and the save refuses a
  longer name itself.
- The atlas builder refuses a place whose name, ASCII name or region code
  holds a control, a format character, a line or paragraph separator or a
  lone surrogate, and every place of the shipped atlas passes.
- The banners that name a folder print it as code spans a backtick cannot
  end, and the Markdown export escapes every "www.", whatever stands before
  it.

Everything runs against a tmp_path data folder, never the reader's own.
"""
import ast
import json
import os
import random
import re
import sqlite3
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import APP_PATH, EXECUTABLE_DIR, assert_no_exception, make_app, sync_engine_to_environment, ui_source

import build_atlas as builder

LMT = "LMT (Local Mean Time)"
RECORD = {"date_string": "1977-12-16", "time_string": "10:30:00", "time_standard": LMT,
          "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
RLO, PDF, ZWSP, ZWNJ, ZWJ = "\u202e", "\u202c", "\u200b", "\u200c", "\u200d"
HONEST = "Alice"
SPOOF = RLO + "ecilA" + PDF
BLANK = ZWSP
TRAILING = HONEST + ZWSP
PERSIAN = "\u0645\u06cc" + ZWNJ + "\u062e\u0648\u0627\u0647\u0645"          # mi<ZWNJ>khaham
DEVANAGARI = "\u0915\u094d" + ZWJ + "\u0937"                                 # KA VIRAMA ZWJ SSA
ARABIC_JOINED = "\u0644" + ZWJ + "\u0627"                                    # LAM ZWJ ALEF
HEBREW = "\u05d3\u05d5\u05d3"                                                # a name written right to left
MARKS_TYPED = "[U+202E]ecilA[U+202C]"                                        # the mark's own text, typed


# --- the harness ---------------------------------------------------------------

@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A disposable data folder; preferences stay off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def prefs_on(tmp_path, monkeypatch):
    """A disposable data folder with the preferences file live."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    return tmp_path


def _store_path():
    return Path(os.environ["XDG_DATA_HOME"]) / "Zij" / "saved_charts.json"


def _put_store(charts):
    """Write the store; the bytes written."""
    data = json.dumps(charts, ensure_ascii=False).encode("utf-8")
    _store_path().parent.mkdir(parents=True, exist_ok=True)
    _store_path().write_bytes(data)
    return data


def _put_prefs(prefs):
    (_store_path().parent / "preferences.json").write_text(json.dumps(prefs), encoding="utf-8")


def _launch():
    """A session that seeds nothing, as a launch is."""
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    return at


def _picker(at):
    return at.sidebar.selectbox(key="chart_picker")


def _labels(at):
    """The picker's labels, as the browser is sent them."""
    return list(_picker(at).options)


def _label_of(at, name):
    picker = _picker(at)
    return picker.format_func(name)


def _sidebar(at, kind):
    return [e.value for e in getattr(at.sidebar, kind)]


def _button(at, label=None, help=None):
    hits = [b for b in at.sidebar.button if (label is None or b.label == label) and (help is None or b.help == help)]
    assert len(hits) == 1, [(b.label, b.help) for b in at.sidebar.button]
    return hits[0]


def _name_box(at):
    return next(t for t in at.sidebar.text_input if t.label == "Chart name (for saving)")


def _ask_to_delete(at, name):
    _picker(at).select(name).run()
    _button(at, help="Delete the selected saved chart").click().run()
    return at


def _drawn(label):
    """Whether a label draws something: a character that is not a space, a
    separator or a format character."""
    return any(not (unicodedata.category(ch)[0] in "ZC" or ch.isspace()) for ch in label)


def _lift(*names, **given):
    """The top-level definitions of app.py named, functions and assignments,
    run in source order with `given` as their globals."""
    source = ui_source()
    namespace = {"re": re, "unicodedata": unicodedata, **given}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef):
            hit = node.name in names
        elif isinstance(node, ast.Assign):
            hit = any(isinstance(t, ast.Name) and t.id in names for t in node.targets)
        else:
            hit = False
        if hit:
            exec(compile(ast.Module([node], []), str(APP_PATH), "exec"), namespace)
    missing = [name for name in names if name not in namespace]
    assert not missing, f"app.py defines no {missing}"
    return namespace


LABEL_NAMES = ("_MARKED_CATEGORIES", "_DRAWN_BLANK", "_JOINERS", "_LABEL_NOTE", "_LABEL_PREFIX_CHARS",
               "_SHAPED_BY_JOINERS", "_is_letter", "_shaping_script", "_between_letters", "_drawn_as_mark",
               "_DRAWN_BLANK_TEXT", "_marked", "_record_label", "_drawn_alike", "_record_labels")


@pytest.fixture(scope="module")
def labels():
    import engine
    return _lift(*LABEL_NAMES, chart_name_too_long=engine.chart_name_too_long,
                 CHART_NAME_MAX_CHARS=engine.CHART_NAME_MAX_CHARS)


# --- 1. names a reader can tell apart ----------------------------------------

def test_the_reproductions_pairs_are_drawn_apart_and_none_is_blank(scratch):
    names = (HONEST, SPOOF, BLANK, TRAILING, PERSIAN)
    _put_store({name: RECORD for name in names})
    at = _launch().run()
    assert_no_exception(at, "the launch")
    labels = {name: _label_of(at, name) for name in names}
    assert sorted(labels.values()) == sorted(_labels(at)[1:]), "the picker is not sent these labels"
    assert len(set(labels.values())) == len(names), f"two names are drawn alike: {labels}"
    assert [label for label in labels.values() if not _drawn(label)] == [], f"a name is drawn blank: {labels}"
    assert labels[SPOOF] == "[U+202E]ecilA[U+202C]"
    assert labels[BLANK] == "[U+200B]"
    assert labels[TRAILING] == "Alice[U+200B]"
    assert labels[HONEST] == HONEST
    assert labels[PERSIAN] == PERSIAN, "a non-joiner between two Persian letters was marked"


# Each character the label marks, by kind: the directional controls (the
# embeddings, overrides and isolates, their pops, and the three marks), the
# zero-width and other format and default-ignorable characters, the controls,
# the separators and the spaces a reader cannot tell from the plain one.
MARKED = {
    "LRE": "\u202a", "RLE": "\u202b", "PDF": "\u202c", "LRO": "\u202d", "RLO": "\u202e",
    "LRI": "\u2066", "RLI": "\u2067", "FSI": "\u2068", "PDI": "\u2069",
    "LRM": "\u200e", "RLM": "\u200f", "ALM": "\u061c",
    "ZWSP": "\u200b", "WORD JOINER": "\u2060", "BOM": "\ufeff", "SOFT HYPHEN": "\u00ad",
    "INVISIBLE TIMES": "\u2062", "MONGOLIAN VOWEL SEPARATOR": "\u180e",
    "COMBINING GRAPHEME JOINER": "\u034f", "VARIATION SELECTOR-16": "\ufe0f", "VARIATION SELECTOR-17": "\U000e0100",
    "TAG LATIN SMALL A": "\U000e0061", "HANGUL FILLER": "\u3164", "HALFWIDTH HANGUL FILLER": "\uffa0",
    "HANGUL CHOSEONG FILLER": "\u115f", "KHMER VOWEL INHERENT AQ": "\u17b4", "BRAILLE PATTERN BLANK": "\u2800",
    "NUL": "\x00", "TAB": "\t", "LINE FEED": "\n", "DELETE": "\x7f", "NEXT LINE": "\x85",
    "LINE SEPARATOR": "\u2028", "PARAGRAPH SEPARATOR": "\u2029",
    "NO-BREAK SPACE": "\u00a0", "EN SPACE": "\u2002", "NARROW NO-BREAK SPACE": "\u202f",
    "IDEOGRAPHIC SPACE": "\u3000", "PRIVATE USE": "\ue000", "UNASSIGNED": "\u0378",
}


@pytest.mark.parametrize("kind", sorted(MARKED))
def test_each_character_that_draws_nothing_or_moves_the_text_is_drawn_as_a_mark(labels, kind):
    ch = MARKED[kind]
    name = "Al" + ch + "ice"
    label = labels["_record_label"](name)
    assert label == f"Al[U+{ord(ch):04X}]ice", f"{kind}: {label!r}"
    assert ch not in label


def test_the_picker_marks_every_kind_in_one_list(scratch):
    names = ["Al" + ch + "ice" for ch in MARKED.values()] + [HONEST]
    _put_store({name: RECORD for name in names})
    at = _launch().run()
    assert_no_exception(at, "a list of every kind")
    shown = _labels(at)[1:]
    assert len(set(shown)) == len(names) and HONEST in shown
    for ch in MARKED.values():
        assert f"Al[U+{ord(ch):04X}]ice" in shown, f"U+{ord(ch):04X} is not drawn as its mark: {shown}"
        assert [label for label in shown if ch in label] == []


@pytest.mark.parametrize("name", [PERSIAN, DEVANAGARI, ARABIC_JOINED, HEBREW, "Smith [draft]", "O'Brien & co",
                                  "Jean-Luc Picard", "\u5c71\u7530 \u592a\u90ce", "Zo\u00eb", "Jos\u00e9 Mar\u00eda"],
                         ids=["persian-zwnj", "devanagari-zwj", "arabic-zwj", "hebrew", "brackets",
                              "apostrophe", "hyphen", "cjk", "diaeresis", "accents"])
def test_an_honest_name_is_drawn_as_it_is(labels, name):
    assert labels["_record_label"](name) == name


@pytest.mark.parametrize("name, label", [
    ("Al" + ZWJ + "\u2063", "Al[U+200D][U+2063]"),     # a joiner before no letter
    (ZWNJ + "\u062e", "[U+200C]\u062e"),               # a non-joiner after no letter
    ("\u0645" + ZWNJ, "\u0645[U+200C]"),               # a non-joiner at the end
    ("\u0645" + ZWNJ + ZWNJ + "\u062e", "\u0645[U+200C][U+200C]\u062e"),
    ("a " + ZWNJ + " b", "a [U+200C] b"),
])
def test_a_joiner_that_stands_between_no_two_letters_is_marked(labels, name, label):
    assert labels["_record_label"](name) == label


@pytest.mark.parametrize("name, label", [
    (" Alice", "[U+0020]Alice"), ("Alice ", "Alice[U+0020]"), ("Al  ice", "Al [U+0020]ice"),
    (" ", "[U+0020]"), ("   ", "[U+0020][U+0020][U+0020]"), ("Al ice", "Al ice"),
])
def test_a_plain_space_is_marked_only_where_it_cannot_be_seen(labels, name, label):
    assert labels["_record_label"](name) == label


def test_the_marks_own_text_typed_is_drawn_apart_from_the_mark(labels, scratch):
    assert labels["_record_label"](MARKS_TYPED) == "[U+005B]U+202E]ecilA[U+005B]U+202C]"
    assert labels["_record_label"](MARKS_TYPED) != labels["_record_label"](SPOOF)
    _put_store({SPOOF: RECORD, MARKS_TYPED: RECORD})
    at = _launch().run()
    assert len(set(_labels(at))) == 3


def test_no_two_names_share_a_label(labels):
    """Every label reads back to one name: a few hundred thousand names made
    of the characters a label treats specially, and of the marks' own text."""
    record_label = labels["_record_label"]
    alphabet = ["[", "]", "U", "+", "2", "0", "E", "\u2026", " ", ZWNJ, ZWJ, RLO, ZWSP, "\u0645", "a", "\u0301",
                "\u00a0", "[U+202E]", "[\u2026 1 characters]", "[\u2026 no name]"]
    rng = random.Random(1801)
    seen = {}
    for _ in range(200_000):
        name = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 6)))
        label = record_label(name)
        assert seen.setdefault(label, name) == name, f"{name!r} and {seen[label]!r} are both drawn {label!r}"


def test_a_name_too_long_to_keep_is_drawn_short_and_apart(labels, engine):
    limit = engine["CHART_NAME_MAX_CHARS"]
    at_bound, past = "A" * limit, "A" * (limit + 1)
    assert labels["_record_label"](at_bound) == at_bound
    assert labels["_record_label"](past) == "A" * 40 + f" [\u2026 {limit + 1:,} characters]"
    # Names alike in their first characters and their length are counted.
    same = ["B" * 40 + tail for tail in ("x" * 300, "y" * 300, "z" * 300)]
    drawn = labels["_record_labels"](same + [past, at_bound, ""])
    assert len(set(drawn.values())) == 6, drawn
    assert drawn[same[1]] == "B" * 40 + " [\u2026 340 characters, 2 of 3]"
    assert drawn[past] == "A" * 40 + f" [\u2026 {limit + 1:,} characters]"
    assert drawn[""] == "[\u2026 no name]"
    # A typed name that reads like a shortened one is drawn apart from it.
    assert labels["_record_label"](drawn[past]) != drawn[past]


def test_the_delete_question_names_the_record_by_its_label(scratch):
    _put_store({HONEST: RECORD, SPOOF: RECORD, BLANK: RECORD})
    at = _ask_to_delete(_launch().run(), SPOOF)
    assert "Delete '[U+202E]ecilA[U+202C]'?" in _sidebar(at, "warning"), _sidebar(at, "warning")
    at = _ask_to_delete(_launch().run(), BLANK)
    assert "Delete '[U+200B]'?" in _sidebar(at, "warning"), _sidebar(at, "warning")
    _button(at, label="Delete").click().run()
    assert_no_exception(at, "the delete")
    assert set(json.loads(_store_path().read_text(encoding="utf-8"))) == {HONEST, SPOOF}


def test_the_replace_question_names_the_record_by_its_label(scratch):
    _put_store({SPOOF: RECORD})
    at = make_app().run()
    _name_box(at).set_value(SPOOF).run()
    _button(at, label="Save this chart").click().run()
    assert_no_exception(at, "the save")
    assert "'[U+202E]ecilA[U+202C]' exists. Replace it?" in _sidebar(at, "warning"), _sidebar(at, "warning")


def test_the_readings_question_names_the_record_by_its_label(scratch):
    _put_store({SPOOF: {**RECORD, "readings": {"_connection_rule": "Abu Ma'shar"}}})
    at = _launch()
    at.session_state["_connection_rule"] = "Sahl"
    at.run()
    _picker(at).select(SPOOF).run()
    assert_no_exception(at, "the load")
    assert "'[U+202E]ecilA[U+202C]' was saved under other readings." in _sidebar(at, "info"), _sidebar(at, "info")


def test_the_name_is_kept_as_typed_everywhere_but_the_labels(scratch):
    data = _put_store({SPOOF: RECORD, HONEST: {**RECORD, "date_string": "1990-01-01"}})
    at = _launch().run()
    _picker(at).select(SPOOF).run()
    assert_no_exception(at, "the load")
    assert at.session_state["chart_picker"] == SPOOF
    assert at.session_state["date_input_key"] == "1977-12-16", "the choice did not reach its own record"
    assert at.session_state["_analysis_export"]["chart"] == SPOOF
    assert SPOOF in at.session_state["_analysis_html"]
    assert _store_path().read_bytes() == data


# A joiner is left as it is only between two letters of one script it
# shapes: the joining scripts and those written with a virama.
HINDI_ZWJ = "लक्" + ZWJ + "ष्मी"           # Lakshmi, a half KA
HINDI_ZWNJ = "लक्" + ZWNJ + "ष्मी"         # Lakshmi, the virama shown
MALAYALAM_ZWNJ = "ലക്" + ZWNJ + "ഷ്മി"     # Lakshmi, the virama shown
MALAYALAM_ZWJ = "അരുണ്" + ZWJ + "കുമാര്"  # a chillu N
NASSER = "ناصر"                                           # NUN ALEF SAD REH
NASSER_ZWNJ = "نا" + ZWNJ + "صر"                           # a non-joiner after the alef
JOSE_COMPOSED, JOSE_APART = "José", "José"


@pytest.mark.parametrize("name", [PERSIAN, HINDI_ZWJ, HINDI_ZWNJ, MALAYALAM_ZWNJ, MALAYALAM_ZWJ, NASSER_ZWNJ],
                         ids=["persian-zwnj", "hindi-zwj", "hindi-zwnj", "malayalam-zwnj", "malayalam-zwj",
                              "arabic-zwnj-after-alef"])
def test_a_joiner_between_two_letters_of_a_script_it_shapes_is_left_as_it_is(labels, name):
    assert labels["_record_label"](name) == name
    assert labels["_record_labels"]([name, HONEST]) == {name: name, HONEST: HONEST}


@pytest.mark.parametrize("name, label", [
    ("Al" + ZWJ + "ice", "Al[U+200D]ice"),
    ("Al" + ZWNJ + "ice", "Al[U+200C]ice"),
    ("Al" + ZWNJ + "иce", "Al[U+200C]иce"),                 # Latin, Cyrillic
    ("דו" + ZWNJ + "ד", "דו[U+200C]ד"),  # Hebrew joins nothing
    ("م" + ZWNJ + "a", "م[U+200C]a"),                       # Arabic, then Latin
    ("م" + ZWNJ + "क", "م[U+200C]क"),             # Arabic, then Devanagari
    ("क्" + ZWJ + "ഷ", "क्[U+200D]ഷ"),  # Devanagari, then Malayalam
])
def test_a_joiner_between_letters_of_no_one_script_it_shapes_is_marked(labels, name, label):
    assert labels["_record_label"](name) == label


def test_alice_and_alice_with_a_joiner_are_drawn_apart_without_a_count(scratch):
    names = (HONEST, "Al" + ZWJ + "ice", "Al" + ZWNJ + "ice")
    _put_store({name: RECORD for name in names})
    at = _launch().run()
    assert_no_exception(at, "the launch")
    assert {name: _label_of(at, name) for name in names} == {
        HONEST: HONEST, names[1]: "Al[U+200D]ice", names[2]: "Al[U+200C]ice"}
    assert sorted(_labels(at)[1:]) == sorted(["Alice", "Al[U+200D]ice", "Al[U+200C]ice"])
    at = _ask_to_delete(at, names[1])
    assert "Delete 'Al[U+200D]ice'?" in _sidebar(at, "warning"), _sidebar(at, "warning")


def test_two_names_alike_but_for_a_joiner_that_shapes_nothing_are_counted(scratch):
    _put_store({NASSER: RECORD, NASSER_ZWNJ: {**RECORD, "date_string": "1990-01-01"}, PERSIAN: RECORD})
    at = _launch().run()
    assert_no_exception(at, "the launch")
    counted = {NASSER: f"{NASSER} [… 1 of 2]", NASSER_ZWNJ: f"{NASSER_ZWNJ} [… 2 of 2]"}
    assert {name: _label_of(at, name) for name in counted} == counted
    assert _label_of(at, PERSIAN) == PERSIAN, "the Persian name is marked or counted"
    assert sorted(_labels(at)[1:]) == sorted([*counted.values(), PERSIAN])
    _picker(at).select(NASSER_ZWNJ).run()
    assert_no_exception(at, "the selection")
    assert at.session_state["date_input_key"] == "1990-01-01", "the choice did not reach its own record"


def test_two_spellings_alike_once_composed_are_counted_and_each_alone_is_not(scratch):
    _put_store({JOSE_COMPOSED: RECORD, JOSE_APART: {**RECORD, "date_string": "1990-01-01"}})
    at = _launch().run()
    assert_no_exception(at, "the launch")
    counted = {JOSE_APART: f"{JOSE_APART} [… 1 of 2]", JOSE_COMPOSED: f"{JOSE_COMPOSED} [… 2 of 2]"}
    assert {name: _label_of(at, name) for name in counted} == counted
    _picker(at).select(JOSE_APART).run()
    assert at.session_state["date_input_key"] == "1990-01-01", "the choice did not reach its own record"
    at = _ask_to_delete(at, JOSE_COMPOSED)
    assert any(w.startswith("Delete ") and "2 of 2" in w for w in _sidebar(at, "warning")), _sidebar(at, "warning")
    for alone in (JOSE_COMPOSED, JOSE_APART):
        _put_store({alone: RECORD, HONEST: RECORD})
        at = _launch().run()
        assert _label_of(at, alone) == alone, "a name alone is counted or not drawn as typed"
        assert sorted(_labels(at)[1:]) == sorted([alone, HONEST])


def _seen_as(label):
    """How a label draws, by the test's own model: composed, and without the
    characters that draw nothing (a label leaves only the joiners raw)."""
    return unicodedata.normalize("NFC", "".join(ch for ch in label if unicodedata.category(ch) != "Cf"))


def test_no_two_labels_in_one_list_are_drawn_alike(labels):
    """Lists of names made of accents apart and composed, joiners, Arabic,
    Persian and Latin letters, and the marks' and notes' own text: no two
    labels in a list draw alike."""
    alphabet = ["a", "e", "é", "́", ZWJ, ZWNJ, "ا", "ن", "ی", "क", "्",
                " ", "[", "…", "[… 1 of 2]", "[U+200D]", "A" * 60]
    rng = random.Random(1802)
    alike = []
    for _ in range(2_000):
        names = {"".join(rng.choice(alphabet) for _ in range(rng.randint(0, 5))) for _ in range(40)}
        drawn = labels["_record_labels"](names)
        seen = {}
        for name, label in drawn.items():
            seen.setdefault(_seen_as(label), []).append((name, label))
        alike += [group for group in seen.values() if len(group) > 1]
    assert alike[:5] == [], f"{len(alike)} lists hold names drawn alike"


# The scripts a joiner shapes, written out here so that one swapped for
# another is seen, not only a count changed. Read from the Unicode Character
# Database 16.0: the scripts with a letter whose Joining_Type is dual, right
# or left (ArabicShaping.txt), 13; and those with a character whose
# Indic_Syllabic_Category is Virama or Invisible_Stacker
# (IndicSyllabicCategory.txt), 41.
JOINING = ("ADLAM", "ARABIC", "CHORASMIAN", "HANIFI ROHINGYA", "MANDAIC", "MANICHAEAN", "MONGOLIAN", "NKO",
           "OLD UYGHUR", "PHAGS-PA", "PSALTER PAHLAVI", "SOGDIAN", "SYRIAC")
VIRAMA = ("BALINESE", "BENGALI", "BHAIKSUKI", "BRAHMI", "CHAKMA", "DEVANAGARI", "DIVES AKURU", "DOGRA", "GRANTHA",
          "GUJARATI", "GUNJALA GONDI", "GURMUKHI", "JAVANESE", "KAITHI", "KANNADA", "KAWI", "KHAROSHTHI", "KHMER",
          "KHOJKI", "MALAYALAM", "MASARAM GONDI", "MEETEI MAYEK", "MODI", "MYANMAR", "NANDINAGARI", "NEWA", "ORIYA",
          "SAURASHTRA", "SHARADA", "SIDDHAM", "SINHALA", "SOYOMBO", "SUNDANESE", "SYLOTI NAGRI", "TAI THAM", "TAKRI",
          "TAMIL", "TELUGU", "TIRHUTA", "TULU-TIGALARI", "ZANABAZAR SQUARE")


def test_the_scripts_written_out_are_the_counted_ones():
    assert (len(JOINING), len(VIRAMA), len(set(JOINING + VIRAMA))) == (13, 41, 54)


def test_the_scripts_a_joiner_shapes_are_read_exactly_from_the_letters_names(labels):
    """The letters' names give each letter's script exactly as the Unicode
    Character Database's script property does, for the scripts a joiner
    shapes. fontTools carries that property, and the app does not: it is a
    development pin (requirements-dev.txt), and so imported here, not
    skipped without."""
    from fontTools import unicodedata as fonttools
    shaping_script = labels["_shaping_script"]
    def spelled(script):
        return re.sub(r"[ _-]", " ", script.strip().upper())
    named = {spelled(fonttools.script_name(code)): code for code in fonttools.Scripts.NAMES}
    codes = {named[spelled(script)] for script in labels["_SHAPED_BY_JOINERS"]}
    assert len(codes) == len(labels["_SHAPED_BY_JOINERS"]) == 54
    assert sorted(labels["_SHAPED_BY_JOINERS"]) == sorted(f"{script} " for script in JOINING + VIRAMA)
    def misread(ch):
        """(code point, name, script, script read from the name) where the
        name's reading differs from the script, or None."""
        script = shaping_script(ch)
        got = named[spelled(script)] if script else None
        want = fonttools.script(ch)
        if want in ("Zyyy", "Zinh") and got is not None and got in fonttools.script_extension(ch):
            return None     # a letter of many scripts, these among them (the tatweel)
        if (want if want in codes else None) == got:
            return None
        return (f"U+{ord(ch):04X}", unicodedata.name(ch, ""), want, got)

    letters = [chr(point) for point in range(0x110000) if unicodedata.category(chr(point)).startswith("L")]
    assert len(letters) > 140_000
    assert [found for found in map(misread, letters) if found] == []


def test_a_long_name_another_window_deleted_or_replaced_is_named_by_its_label(scratch):
    """The sentence that says another window moved a record names a name
    past the bound by its label, as every other sentence does."""
    name = "A" * 300
    label = f"'{'A' * 40} [… 300 characters]'"
    for moved, after in (("deleted", {HONEST: RECORD}),
                         ("replaced", {name: {**RECORD, "date_string": "1990-01-01"}, HONEST: RECORD})):
        _put_store({name: RECORD, HONEST: RECORD})
        at = _launch().run()
        at = _ask_to_delete(at, name)
        _put_store(after)
        _button(at, label="Delete").click().run()
        assert_no_exception(at, f"the delete of a record another window {moved}")
        said = [w for w in _sidebar(at, "warning") if "by another window" in w]
        assert said and said[0].startswith(f"{label} was {moved} by another window since this one read it."), (
            [w[:200] for w in _sidebar(at, "warning")])
        assert "A" * 41 not in "".join(_sidebar(at, "warning"))


def test_a_long_name_another_window_saved_is_named_by_its_label():
    """The sentence that says another window saved, under the name this one
    is saving, a record this one never listed names a name past the bound by
    its label too. The page cannot reach it with such a name -- the name box
    and the save stop at the bound -- so the reading of the store is run by
    itself, on a store another window has written since."""
    import engine
    name = "A" * 300
    session = {"saved_charts": {HONEST: RECORD}, "_store_digest": "as read"}
    stands = SimpleNamespace(state="readable", digest="written since", copy=None,
                             charts={HONEST: RECORD, name: RECORD})
    lifted = _lift(*LABEL_NAMES, "_chart_label", "_named_chart", "_as_typed", "_code_spans", "_code_span",
                   "_PLAIN_TEXT", "_NOT_PLAIN", "_BACKTICKS", "_store_as_it_stands",
                   st=SimpleNamespace(session_state=session),
                   engine=SimpleNamespace(saved_charts_as_they_stand=lambda keep_aside=False: stands),
                   chart_name_too_long=engine.chart_name_too_long, CHART_NAME_MAX_CHARS=engine.CHART_NAME_MAX_CHARS,
                   _isolated=engine._isolated)
    assert lifted["_store_as_it_stands"](name) == (None, None, None)
    label = f"'{'A' * 40} [… 300 characters]'"
    assert session["_store_moved_notice"] == f"{label} was saved by another window since this one read the list."
    assert session["saved_charts"] == stands.charts


# --- 2. text bounded before it is expanded ---------------------------------------

EIGHT_MIB = 8 * 1024 * 1024


def test_an_8_mib_name_is_listed_selected_refused_and_deleted(scratch, engine):
    name = "A" * EIGHT_MIB
    data = _put_store({name: RECORD, HONEST: RECORD})
    at = _launch().run()
    assert_no_exception(at, "the launch")
    label = _label_of(at, name)
    assert label in _labels(at) and len(label) < 100, label[:120]
    assert not _sidebar(at, "error"), "the store was condemned"
    _picker(at).select(name).run()
    assert_no_exception(at, "the selection")
    sentence = f"'{'A' * 40} [\u2026 {EIGHT_MIB:,} characters]' could not be loaded: its name is longer than 200 characters."
    assert sentence in _sidebar(at, "warning"), [w[:200] for w in _sidebar(at, "warning")]
    assert at.session_state["_analysis_export"]["chart"] == "Unsaved chart"
    for key in ("_analysis_html", "_analysis_markdown"):
        assert "A" * 1000 not in at.session_state[key], f"{key} is built on the name"
    assert _store_path().read_bytes() == data, "the record was not left in the file as it is"
    _button(at, help="Delete the selected saved chart").click().run()
    assert f"Delete '{'A' * 40} [\u2026 {EIGHT_MIB:,} characters]'?" in _sidebar(at, "warning")
    _button(at, label="Delete").click().run()
    assert_no_exception(at, "the delete")
    assert set(json.loads(_store_path().read_text(encoding="utf-8"))) == {HONEST}


def test_a_picker_set_on_a_long_name_by_anything_but_the_loader_names_no_chart(scratch):
    """The strip and the exports name the record the picker names only when
    it is one the boxes can hold: never one whose name is past the bound."""
    name = "A" * 201
    _put_store({name: RECORD})
    at = make_app()
    at.session_state["chart_picker"] = name
    at.run()
    assert_no_exception(at, "a picker set on the long name")
    assert at.session_state["_analysis_export"]["chart"] == "Unsaved chart"


def test_the_store_holding_a_long_name_is_not_condemned(engine):
    charts = {"A" * EIGHT_MIB: dict(RECORD)}
    assert engine["_validate_chart_mapping"](charts) is charts


def test_a_short_control_name_loads_as_before(scratch):
    name = "A" * 16
    _put_store({name: RECORD})
    at = _launch().run()
    _picker(at).select(name).run()
    assert_no_exception(at, "the selection")
    assert at.session_state["_analysis_export"]["chart"] == name
    assert not [w for w in _sidebar(at, "warning") if "could not be loaded" in w]


def test_a_name_at_the_bound_loads_and_one_past_it_does_not(scratch, engine):
    limit = engine["CHART_NAME_MAX_CHARS"]
    assert limit == 200
    at_bound, past = "N" * limit, "N" * (limit + 1)
    _put_store({at_bound: RECORD, past: RECORD})
    at = _launch().run()
    _picker(at).select(at_bound).run()
    assert_no_exception(at, "the name at the bound")
    assert at.session_state["_analysis_export"]["chart"] == at_bound
    _picker(at).select(past).run()
    assert_no_exception(at, "the name past the bound")
    assert at.session_state["_analysis_export"]["chart"] == "Unsaved chart"
    assert any(w.endswith("could not be loaded: its name is longer than 200 characters.")
               for w in _sidebar(at, "warning"))


TEXT_FIELDS = [("date_string", "date"), ("time_string", "time"), ("time_standard", "time standard"),
               ("utc_offset", "UTC offset"), ("lat", "latitude"), ("lon", "longitude"), ("location_query", "place"),
               ("target_mode", "target"), ("target_date", "target date"), ("target_age", "target age")]


@pytest.mark.parametrize("field, label", TEXT_FIELDS, ids=[f for f, _l in TEXT_FIELDS])
def test_each_text_field_past_its_bound_is_refused_by_name(engine, field, label):
    limit = engine["CHART_TEXT_MAX_CHARS"]
    assert limit == 1000
    value = {"date_string": "1977-12-16", "time_string": "10:30:00", "lat": "43.7792", "lon": "11.2463",
             "utc_offset": "1", "target_age": "40", "target_date": "2020-01-01"}.get(field, "x")
    past = {**RECORD, field: value + " " * (limit + 1 - len(value))}
    assert engine["chart_record_fault"](past) == (label, "longer than 1,000 characters")
    within = {**RECORD, field: value + " " * (limit - len(value))}
    fault = engine["chart_record_fault"](within)
    assert fault is None or "1,000" not in fault[1], fault


@pytest.mark.parametrize("field", ["location_query", "time_standard"])
def test_a_text_field_past_its_bound_is_refused_on_selection_and_one_at_it_loads(scratch, field):
    _put_store({"Past": {**RECORD, field: "P" * 1001}, "At": {**RECORD, field: "P" * 1000}})
    at = _launch().run()
    _picker(at).select("Past").run()
    assert_no_exception(at, "the record past the bound")
    label = {"location_query": "place", "time_standard": "time standard"}[field]
    assert f"'Past' could not be loaded: its {label} is longer than 1,000 characters." in (
        _sidebar(at, "warning")), _sidebar(at, "warning")
    _picker(at).select("At").run()
    assert_no_exception(at, "the record at the bound")
    assert not [w for w in _sidebar(at, "warning") if w.startswith("'At' could not be loaded")]
    # An unoffered time standard loads and is named; the chart is cast under
    # the box's, so it is the record, modified.
    assert at.session_state["_analysis_export"]["chart"] in ("At", "At (modified)")


def test_the_name_box_takes_no_more_than_the_bound_and_a_name_at_it_saves(scratch):
    at = make_app().run()
    box = _name_box(at)
    assert box.proto.max_chars == 200
    box.set_value("S" * 250).run()
    _button(at, label="Save this chart").click().run()
    assert_no_exception(at, "the save")
    assert list(json.loads(_store_path().read_text(encoding="utf-8"))) == ["S" * 200]


def test_the_save_refuses_a_longer_name_itself(scratch, monkeypatch):
    """Were the box's bound lost, the save would still hold to it."""
    from streamlit.elements.widgets import text_widgets
    monkeypatch.setattr(text_widgets.TextInputSerde, "deserialize",
                        lambda self, ui_value: ui_value if ui_value is not None else self.value)
    at = make_app().run()
    _name_box(at).set_value("S" * 201).run()
    _button(at, label="Save this chart").click().run()
    assert_no_exception(at, "the save")
    assert "That name is longer than 200 characters; choose a shorter one." in _sidebar(at, "error")
    assert not _store_path().exists()


def test_keep_both_keeps_the_new_name_within_the_bound(scratch):
    name = "K" * 200
    _put_store({name: RECORD, name[:196] + " (2)": RECORD})
    at = make_app().run()
    _name_box(at).set_value(name).run()
    _button(at, label="Save this chart").click().run()
    _button(at, label="Keep both").click().run()
    assert_no_exception(at, "keep both")
    kept = set(json.loads(_store_path().read_text(encoding="utf-8")))
    assert kept == {name, name[:196] + " (2)", name[:196] + " (3)"}, kept


@pytest.mark.parametrize("key, value, kept", [
    ("last_chart", "L" * 200, True), ("last_chart", "L" * 201, False),
    ("home_place", {"label": "H" * 1000, "lat": 43.7792, "lon": 11.2463}, True),
    ("home_place", {"label": "H" * 1001, "lat": 43.7792, "lon": 11.2463}, False),
])
def test_a_preference_text_past_its_bound_is_dropped_as_a_malformed_one_is(engine, key, value, kept):
    assert engine["preference_is_valid"](key, value) is kept
    assert (key in engine["_loadable_preferences"]({key: value})) is kept


def test_the_app_does_not_open_on_a_last_chart_past_the_bound(prefs_on):
    past = "L" * 201
    _put_store({past: RECORD})
    _put_prefs({"last_chart": past})
    at = _launch().run()
    assert_no_exception(at, "the launch")
    assert at.session_state["chart_picker"] == "-- New Chart --"
    assert not [w for w in _sidebar(at, "warning") if "could not be loaded" in w]


# --- 3. the atlas builder's place names ----------------------------------------

def _row(**cols):
    values = {"name": "Florence", "ascii_name": "Florence", "admin1": "16", **cols}
    fields = ["3176959", values["name"], values["ascii_name"], "", "43.77925", "11.24626", "P", "PPLA", "IT", "",
              values["admin1"], "FI", "048017", "", "367150", "", "50", "Europe/Rome", "2024-01-01"]
    return ("\t".join(fields) + "\n").encode("utf-8")


ZONES = frozenset({"Europe/Rome"})
REFUSED = {"Cc": "\x07", "Cf (RLO)": RLO, "Cf (ZWSP)": ZWSP, "Cf (BOM)": "\ufeff", "Zl": "\u2028",
           "Zp": "\u2029", "Cc (C1)": "\x85"}


@pytest.mark.parametrize("column", ["name", "ascii_name", "admin1"])
@pytest.mark.parametrize("kind", sorted(REFUSED))
def test_the_builder_refuses_a_control_or_format_character_in_a_place(column, kind):
    with pytest.raises(builder.AtlasBuildError, match=f"U\\+{ord(REFUSED[kind]):04X}"):
        builder.place_row(7, _row(**{column: "Flo" + REFUSED[kind] + "rence"}), ZONES)


def test_the_builder_refuses_a_lone_surrogate():
    with pytest.raises(builder.AtlasBuildError, match="U\\+D800"):
        builder._refuse_unprinted("Flo\ud800rence", "name", "a row")
    with pytest.raises(builder.AtlasBuildError, match="not UTF-8"):
        builder.place_row(7, _row().replace(b"Florence", b"Flo\xed\xa0\x80rence", 1), ZONES)


@pytest.mark.parametrize("name", ["L'Aquila", "Mbanza [Kongo]", "Trinidad & Tobago", "Ka`upulehu", 'Say "Hi"',
                                  "\u0627\u0644\u0642\u0627\u0647\u0631\u0629", "S\u00e3o Paulo", "Zuni Pueblo"])
def test_the_builder_keeps_the_marks_real_place_names_hold(name):
    row = builder.place_row(7, _row(name=name, ascii_name=name), ZONES)
    assert row[1] == name and row[2] == name


def test_every_place_of_the_shipped_atlas_passes_the_builders_check():
    atlas = EXECUTABLE_DIR / "atlas.db"
    with sqlite3.connect(f"{atlas.resolve().as_uri()}?mode=ro", uri=True) as conn:
        rows = conn.execute("SELECT id, name, ascii_name, admin1 FROM cities").fetchall()
    assert len(rows) > 200_000
    refused = []
    for gid, *texts in rows:
        for what, text in zip(("name", "ASCII name", "region code"), texts):
            try:
                builder._refuse_unprinted(text, what, f"geonameid {gid}")
            except builder.AtlasBuildError as error:
                refused.append(str(error))
    assert not refused, refused[:5]


# --- 4. two banners and one escape -------------------------------------------

FOLDER_NAMES = ("_code_span", "_code_spans", "_folder_text", "_BACKTICKS", "_store_blocked_sentence",
                "_prefs_blocked_sentence", "_data_folder_refusal")


@pytest.fixture(scope="module")
def banners():
    import engine
    return _lift(*FOLDER_NAMES, _isolated=engine._isolated, NEW_CHART_SENTINEL="-- New Chart --")


def _outside_code(markdown):
    """`markdown` with each code span taken out. CommonMark: a run of
    backticks opens a span that the next run of exactly its length closes;
    a run that no such run follows is a literal."""
    runs = list(re.finditer(r"`+", markdown))
    out, at, k = [], 0, 0
    while k < len(runs):
        opener = runs[k]
        close = next((j for j in range(k + 1, len(runs)) if len(runs[j].group()) == len(opener.group())), None)
        if close is None:
            k += 1
            continue
        out.append(markdown[at:opener.start()] + "\0")
        at = runs[close].end()
        k = close + 1
    return "".join(out) + markdown[at:]


@pytest.mark.parametrize("which", ["_store_blocked_sentence", "_prefs_blocked_sentence"])
def test_a_banner_prints_a_folder_holding_a_backtick_as_itself(banners, which):
    folder = "/tmp/we`ird [x](https://example.com) *folder*"
    sentence = banners[which](folder)
    assert re.search(re.escape("``/tmp/we`ird [x](https://example.com) *folder*``"), sentence), sentence
    assert "`" not in _outside_code(sentence) and not re.search(re.escape("example.com"), _outside_code(sentence)), sentence
    plain = banners[which]("/srv/data/Zij")
    assert "`/srv/data/Zij`" in plain
    # Spaces are the folder's own; line breaks are printed as the code
    # span's spaces, and two of them do not end the paragraph inside it.
    assert "`/srv/two  spaces/Zij`" in banners[which]("/srv/two  spaces/Zij")
    broken = banners[which]("/srv/a\n\nb/Zij")
    assert "`/srv/a  b/Zij`" in broken and "\n" not in broken


@pytest.mark.parametrize("state", [("made", "Permission denied"), ("opened", "Permission denied")])
def test_the_data_folders_own_refusal_prints_a_folder_holding_a_backtick_as_itself(banners, state):
    folder = "/tmp/we`ird"
    fake = SimpleNamespace(data_folder_state=lambda: state, DATA_DIR=Path(folder))
    namespace = dict(banners, engine=fake, st=SimpleNamespace(session_state={}))
    exec(compile(ast.Module([n for n in ast.parse(ui_source()).body if isinstance(n, ast.FunctionDef)
                             and n.name == "_data_folder_refusal"], []), str(APP_PATH), "exec"), namespace)
    sentence = namespace["_data_folder_refusal"]()
    assert "``/tmp/we`ird``" in sentence, sentence
    assert "`" not in _outside_code(sentence), sentence


@pytest.fixture(scope="module")
def markdown_as_typed():
    import engine
    return _lift("_PLAIN_TEXT", "_NOT_PLAIN", "_MARKDOWN_MARKS", "_markdown_as_typed",
                 _isolated=engine._isolated)["_markdown_as_typed"]


# GitHub's Markdown opens a "www." link at the start of a line, after a space,
# and after "*", "_", "~" or "(" (the specification's autolinks extension).
WWW_OPENERS = {"start": "www.example.com", "space": "Smith www.example.com", "star": "*www.example.com",
               "underscore": "_www.example.com", "tilde": "~www.example.com", "paren": "(www.example.com)",
               "inside": "Smith_www.example.com", "capitals": "_WWW.example.com"}


@pytest.mark.parametrize("opener", sorted(WWW_OPENERS))
def test_the_markdown_export_escapes_every_www(markdown_as_typed, opener):
    text = markdown_as_typed(WWW_OPENERS[opener])
    assert not re.search(r"(?i)www\.", text), text
    assert re.search(r"(?i)www\\\.", text), text


def test_the_markdown_export_of_a_name_after_an_underscore_holds_no_link(scratch):
    name = "Smith_www.example.com"
    _put_store({name: RECORD})
    at = _launch().run()
    _picker(at).select(name).run()
    assert_no_exception(at, "the load")
    lines = [line for line in at.session_state["_analysis_markdown"].splitlines() if re.search(re.escape("example.com"), line)]
    assert lines and all(re.search(re.escape("Smith\\_www\\.example.com"), line) for line in lines), lines
    assert not any(re.search(r"(?i)www\.", line) for line in lines), lines


# --- 5. what the version is written into ---------------------------------------

def test_the_version_is_in_the_saved_record_and_in_no_export(scratch, engine):
    at = make_app().run()
    _name_box(at).set_value("Versioned").run()
    _button(at, label="Save this chart").click().run()
    record = json.loads(_store_path().read_text(encoding="utf-8"))["Versioned"]
    version = engine["APP_VERSION"]
    assert record["saved_with"]["app"] == version
    exported = json.dumps(at.session_state["_analysis_export"], ensure_ascii=False)
    for text in (exported, at.session_state["_analysis_html"], at.session_state["_analysis_markdown"]):
        assert version not in text
    source = (EXECUTABLE_DIR / "engine.py").read_text(encoding="utf-8")
    comment = source[:source.index("APP_VERSION = ")].rsplit("\n\n", 1)[-1]
    assert "into every exported analysis" not in " ".join(comment.split()), comment
