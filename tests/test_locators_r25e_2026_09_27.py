"""Locators that read alone (round 2026-09-25e's triage, notes C and F).

1. The lord-of-the-year scope comment names the volume on every locator:
   PN IV for II.1, II.23 and III.2, On Nativities for Sahl's 1.23, 33 and
   1.24, 2. Bare, the round resolved II.1, 6 and its neighbours in two works.
2. The testimony-84 label names On Nativities on each locator, and no number
   follows a semicolon (the round read "1.22, 1; 15 deg" as sentence 15).
3. Note C: "considered eastern" and "easternizes at" are the headings of
   Dykes's table, not Sahl's words. The label, the Governor caption and the
   Eastern qualification note quote 1.22, 1 ("considered to be eastern") and
   1.22, 6 ("the power of easternization") instead.
4. Note F: Dykes's fn 13 on PN IV III.1, 10 is cited as a Ptolemy witness
   beside fn 16 on III.1, 12.
"""
import ast
import re
from pathlib import Path

import pytest

from corpus_paths import corpus_file
from skip_guard import needs_corpus

ENGINE_DIR = Path(__file__).resolve().parent.parent
LOCATOR = re.compile(r"[IVX]{1,4}\.\d{1,2}, \d{1,3}|\d\.\d{1,2}, \d{1,3}")


def _strings(name):
    return [n.value for n in ast.walk(ast.parse((ENGINE_DIR / name).read_text(encoding="utf-8")))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _scope_comment():
    lines = (ENGINE_DIR / "engine.py").read_text(encoding="utf-8").split("\n")
    end = next(i for i, ln in enumerate(lines) if ln.startswith("PN4_YEAR_INDICATOR_SCOPE_NOTE = ("))
    start = end
    while lines[start - 1].startswith("#"):
        start -= 1
    return " ".join(ln.lstrip("# ") for ln in lines[start:end])


def test_the_scope_comment_names_the_volume_on_every_locator():
    text = _scope_comment()
    assert "ranks NINETEEN indicators" in text
    found = list(LOCATOR.finditer(text))
    assert len(found) >= 15
    bare = [m.group(0) for m in found
            if not re.search(r"(PN IV|On Nativities) $", text[max(0, m.start() - 16):m.start()])]
    assert not bare, bare
    for loc in ("PN IV II.1, 6)", "PN IV II.1, 7)", "PN IV II.1, 26 ", "PN IV II.1, 6-7, 25",
                "PN IV II.23, 1", "PN IV III.2, 2-3", "On Nativities 1.23, 33", "On Nativities 1.24, 2"):
        assert loc in text, loc


def _label_84(engine):
    p = {name: {'longitude': lon, 'latitude': 0.0, 'distance': 1.0, 'speed_in_lon': sp, 'speed_in_dist': -0.01}
         for name, lon, sp in (('Sun', 180.0, 1.0), ('Moon', 40.0, 13.0), ('Mercury', 200.0, 1.2),
                               ('Venus', 215.0, 1.1), ('Mars', 164.0, .5), ('Jupiter', 200.0, .08),
                               ('Saturn', 172.0, .03))}
    cusps = [(170.0 + 30.0 * n) % 360.0 for n in range(12)]
    essential = engine['evaluate_essential_dignities'](p, 'Diurnal')
    accidental = engine['evaluate_accidental_dignities'](p, cusps, 'Diurnal')
    rows = engine['evaluate_strength_of_planets'](p, essential, accidental, 170.0, 'Diurnal', cusps)
    return {row['Planet']: next(t['sentence'] for t in row['Testimonies'] if t['n'] == '84')
            for row in rows if row['Planet'] in ('Saturn', 'Mars')}


def test_the_testimony_84_label_reads_each_locator_alone(engine):
    for planet, label in _label_84(engine).items():
        assert "On Nativities 1.22, 1;" in label and "On Nativities 1.22, 3)" in label, label
        assert not re.search(r";\s*\d", label), label
        assert '"considered to be eastern"' in label and '"considered eastern"' not in label, label


def test_page_text_quotes_sahl_not_the_table_headings():
    strings = _strings("app.py")
    caption = [s for s in strings if s.startswith("Sahl, On Nativities 1.7, 3-7; the eastern preference")]
    note = [s for s in strings if s.startswith("This column applies an interpretation of Sahl's On Nativities 1.22 to 1.7")]
    assert len(caption) == 1 and len(note) == 1
    for s in caption + note:
        assert '"considered eastern"' not in s and '"easternizes at"' not in s, s
        assert "are \"considered to be eastern\" (1.22, 1)" in s, s
    assert "the figures for \"the power of easternization\" in 1.22, 6 (Saturn and Jupiter 15°, Mars 18°)" in note[0]


def test_fn_13_is_a_ptolemy_witness():
    assert any("Ptolemy's method as Dykes identifies it (PN IV III.1, 10 fn 13; PN IV III.1, 12 fn 16; "
               "PN IV VI.2, 21 fn 33)" in s for s in _strings("app.py"))


NAT = corpus_file("on_nativities.md")
PN4 = corpus_file("pn4/book_i_to_v/pn4_books_i_to_v.md")


@needs_corpus(NAT, PN4)
def test_the_quoted_words_and_the_witnesses_are_on_the_page():
    nat = NAT.read_text(encoding="utf-8")
    ch = nat[nat.index("### [Chapter 1.22]"):nat.index("## [Chapter 1.23]")]
    s1 = re.search(r"^1 And know that if there were 6° .*$", ch, re.M).group(0)
    assert "they are considered to be eastern" in s1
    s6 = re.search(r"6 And the power of easternization \[for\] Saturn and Jupiter is when 15° have passed them, "
                   r"and Mars 18°\.", ch)
    assert s6
    fn174 = re.search(r"^<sup>174</sup>.*$", ch, re.M).group(0)
    assert "considered eastern at 15°" in fn174
    pn4 = PN4.read_text(encoding="utf-8")
    ch = pn4[pn4.index("### Chapter III.1:"):pn4.index("### Chapter III.2:")]
    assert re.search(r"\*\*10\*\* And you work like that too .*?<sup>13</sup>", ch)
    fn13 = re.search(r"^<sup>13</sup>.*$", ch, re.M).group(0)
    assert "Ptolemy's astronomical method of proportional semi-arcs" in fn13
    start = pn4.index("### Chapter II.1:")
    ch = pn4[start:pn4.index("\n### ", start + 1)]
    assert "**6** The first is the sign of the terminal point, and its lord." in ch
    assert "**7** The second is the distribution and the distributor." in ch
    assert "**26** But in some places we have given priority to some of them over others" in ch
