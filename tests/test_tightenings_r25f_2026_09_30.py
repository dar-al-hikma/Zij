"""Round 2026-09-25f's optional tightenings, and PN IV locators that name their volume.

A. Each tightening makes the sentence say only what the cited page says.
   1. The lord-of-the-year ranking cites the list it ranks (PN IV II.1, 6-7)
      beside the rule (II.1, 25) and II.23, 1: the scope comment and the
      page's scope note.
   2. The "What Persian Nativities IV does not settle" row for directing
      anything off the axial degrees says PN IV defers the method to a book
      it does not reproduce, and that fn 16 is Dykes's identification of the
      method -- not "Source silence".
   3. The semi-arc direction's docstring credits proportional semi-arcs to
      Ptolemy as Dykes identifies it (fn 16 on PN IV III.1, 12).
   4. The Eastern qualification note names the planet each of 1.22, 6's
      figures belongs to: Saturn and Jupiter 15 degrees, Mars 18.
B. PN IV locators on the page name their volume: the true-Sun return's
   "I.4, 23-31", the Count-of-the-year Source column, the formula's
   "III.1, 13" (and its fn 16 witness), and the unsettled table's "IX.8, 123"
   and "III.1, 12".
"""
import ast
import re
from pathlib import Path

import pytest

from corpus_paths import corpus_file
from skip_guard import needs_corpus

ENGINE_DIR = Path(__file__).resolve().parent.parent


def _src(name):
    return (ENGINE_DIR / name).read_text(encoding="utf-8")


def _strings(name):
    return [n.value for n in ast.walk(ast.parse(_src(name)))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _joined(name):
    """Every string constant, and every comment block read as one line."""
    comments = re.sub(r"\n\s*# ?", " ", _src(name))
    return "\n".join(_strings(name)) + "\n" + comments


def _scope_note(engine_mod=None):
    tree = ast.parse(_src("engine.py"))
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", None) == "PN4_YEAR_INDICATOR_SCOPE_NOTE")
    return ast.literal_eval(node.value)


def _scope_comment_tail():
    lines = _src("engine.py").split("\n")
    end = next(i for i, ln in enumerate(lines) if ln.startswith("PN4_YEAR_INDICATOR_SCOPE_NOTE = ("))
    start = end
    while lines[start - 1].startswith("#"):
        start -= 1
    return lines[start:end]


def _one(strings, prefix):
    found = [s for s in strings if s.startswith(prefix)]
    assert len(found) == 1, (prefix, len(found))
    return found[0]


# ---------------------------------------------------------------- A1

def test_a1_the_scope_comment_cites_the_list_it_ranks():
    lines = _scope_comment_tail()
    text = " ".join(ln.lstrip("# ") for ln in lines)
    assert "PN IV II.1, 6-7, 25 with PN IV II.23, 1 governs here, not the Introduction's Sect. 3." in text
    assert "PN IV II.1, 25 with" not in text
    # the locator sits on one comment line, not split across two
    assert any("PN IV II.1, 6-7, 25 with PN IV II.23, 1 governs here" in ln for ln in lines)


def test_a1_the_scope_note_cites_the_list_and_names_the_volume():
    note = _scope_note()
    assert ("within the year the lord of the year is the stronger (PN IV II.1, 6-7, 25; PN IV II.23, 1), "
            "across several years the distribution (PN IV III.2, 2-3).") in note
    assert "(II.1, 25; II.23, 1)" not in note
    assert "(III.2, 2-3)" not in note


# ---------------------------------------------------------------- A2 and B (the unsettled table)

def _unsettled_table():
    return _one(_strings("app.py"), "| Topic | State |\n|---|---|\n| The releaser and the house-master")


def test_a2_the_directing_row_says_deferred_not_silent():
    table = _unsettled_table()
    row = next(ln for ln in table.split("\n") if ln.startswith("| Directing anything that is not"))
    assert row == ("| Directing anything that is not the Ascendant or the meridian | Deferred to a book PN IV does "
                   "not reproduce (PN IV III.1, 12); Dykes's identification of the method (PN IV III.1, 12 fn 16), "
                   "applied from the texts that state it |")
    assert "Source silence (III.1, 12)" not in table
    assert "the editor's identification (fn 16)" not in table


def test_a2_matches_the_formulas_own_wording():
    assert any("whose method PN IV defers to a book it does not reproduce" in s for s in _strings("app.py"))


def test_b_the_greater_years_row_names_the_volume():
    table = _unsettled_table()
    assert ("| Where the greater years are granted | Source silence (PN IV IX.8, 123); another source used: "
            "*On Nativities* 1.20 |") in table
    assert "Source silence (IX.8, 123)" not in table


# ---------------------------------------------------------------- A3

def _docstring(fn):
    tree = ast.parse(_src("engine.py"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn)
    return " ".join(ast.get_docstring(node).split())


def test_a3_semi_arcs_are_ptolemys_method_as_dykes_identifies_it():
    doc = _docstring("pn4_distribution_by_semi_arcs")
    assert ("by proportional semi-arcs (Ptolemy's method as Dykes identifies it, PN IV III.1, 12 fn 16)"
            in doc), doc
    assert doc.startswith("PN IV III.1, 12's third case:"), doc
    assert "one degree of the arc to a year (PN IV III.1, 13)" in doc, doc
    assert "(III.1, 13)" not in doc.replace("(PN IV III.1, 13)", "")


# ---------------------------------------------------------------- A4

def test_a4_the_eastern_note_names_each_planets_figure():
    note = _one(_strings("app.py"), "This column applies an interpretation of Sahl's On Nativities 1.22 to 1.7")
    assert ("the figures for \"the power of easternization\" in 1.22, 6 (Saturn and Jupiter 15°, Mars 18°)"
            in note)
    assert "(15°, 15°, 18°)" not in note


# ---------------------------------------------------------------- B

def test_b_the_true_sun_return_names_the_volume():
    s = _one(_strings("app.py"), "**A true-Sun return.**")
    assert "applies the Hipparchan tropical year (PN IV I.4, 23-31)" in s
    assert "year (I.4, 23-31)" not in s


def test_b_the_count_of_the_year_source_names_the_volume():
    src = _src("engine.py")
    assert "'Source': 'PN IV II.3, 1; PN IV I.2, 1-3; PN IV IV.1, 5-6 and 11; PN IV III.1, 13'}" in src
    assert "'Source': 'II.3, 1; I.2, 1-3; IV.1, 5-6 and 11; III.1, 13'" not in src


def test_b_the_formula_names_the_volume():
    s = _one(_strings("app.py"), "Every other planet is the third case")
    assert s.endswith("a degree of it a year (PN IV III.1, 13).\n\n`PromMD - (SigMD / SigSA) * PromSA`"), s
    assert ("Ptolemy's method as Dykes identifies it (PN IV III.1, 10 fn 13; PN IV III.1, 12 fn 16; "
            "PN IV VI.2, 21 fn 33)") in s
    assert "a year (III.1, 13)" not in s


def test_no_new_page_text_carries_build_language():
    for s in (_unsettled_table(), _scope_note(), _one(_strings("app.py"), "**A true-Sun return.**")):
        assert not re.search(r"20\d\d-\d\d|\bround\b|triage|r25|\.py\b|\.tsv|\bcourse\b", s), s


# ---------------------------------------------------------------- the pages say it

PN4 = corpus_file("pn4/book_i_to_v/pn4_books_i_to_v.md")
PN4B = corpus_file("pn4/book_vi_to_ix/pn4_books_vi_to_ix.md")
NAT = corpus_file("on_nativities.md")


def _chapter(text, head):
    start = text.index(head)
    return text[start:text.index("\n### ", start + 1)]


@needs_corpus(PN4, PN4B, NAT)
def test_the_cited_sentences_are_on_the_page():
    pn4 = PN4.read_text(encoding="utf-8")
    ch = _chapter(pn4, "### Chapter II.1:")
    assert "**6** The first is the sign of the terminal point, and its lord." in ch
    assert "**7** The second is the distribution and the distributor." in ch
    assert "each one in turn is stronger in indication than the one which is after it" in ch
    ch = _chapter(pn4, "### Chapter II.23:")
    assert ("**1** After the sign of the terminal point, the power of the indication belongs to the "
            "distributor.") in ch
    ch = _chapter(pn4, "### Chapter III.1:")
    assert "is directed according to what we stated in our book [on that topic]).<sup>16</sup>" in ch
    fn16 = re.search(r"^<sup>16</sup>.*$", ch, re.M).group(0)
    assert "I'm not sure which book this is." in fn16
    assert "Abū Ma'shar is following Ptolemy" in fn16 and "everything else by proportional semi-arcs" in fn16
    assert "**13** So you look at what comes out from the degrees of the direction in all of this, and you make " \
           "every degree a year" in ch
    ch = _chapter(pn4, "### Chapter I.4:")
    assert "using the mean Sun and his circuit" in ch
    ch = _chapter(pn4, "### Chapter II.3:")
    assert "for every year the native has completed, cast out one sign from it" in ch
    ch = _chapter(pn4, "### Chapter I.2:")
    assert "he will have traversed 360° in 365 days (and a fraction)" in ch
    ch = _chapter(PN4B.read_text(encoding="utf-8"), "### Chapter IX.8:")
    assert re.search(r"\*\*123\*\* And there is great difficulty .*? is found in the book which we worked on "
                     r"concerning nativities\.", ch)
    nat = NAT.read_text(encoding="utf-8")
    assert ("6 And the power of easternization [for] Saturn and Jupiter is when 15° have passed them, "
            "and Mars 18°.") in nat
