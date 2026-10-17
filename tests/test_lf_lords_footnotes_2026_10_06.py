"""Lane LF (the owner's ruling 79 of 2026-10-06, PW-32): six Masha'allah lords
cells carry their translator's footnote as a note, in ruling 45's house form
("Variant / Alternative translation / Referent — <locator> fn N: ...").

Each footnote was read on its page photograph (the lane's report, LF_BUILD,
quotes each one as printed):

- [1][10] On Nativities 10.2.4, 1, fn 160 (Sahl I p. 707): Or perhaps, "master".
- [1][7]  7.1, 205, fn 130 (Sahl I p. 605): This can also mean "victorious," ...
- [2][2]  2.14, 10, fn 197 (Sahl I p. 415): ... could be "self-employed."
- [9][7]  7.1, 213, fn 133 (Sahl I p. 605): I take this to be the native.
- [10][4] 4.11, 18, fns 165-166 (Sahl I p. 488): M's "the parents will be well
  known ..."; Or perhaps, he will be better at being a well-known acquaintance
  ... of the Sultan, as they are.
- [11][11] 11.1, 26, fn 19 (Sahl I p. 730): ... "traced to a good lineage."

Two layers: the notes word for word (no corpus needed), and, with the corpus
present, each quoted span found in its footnote, the footnote's cue standing in
the cell's cited sentence.
"""
from __future__ import annotations

import re

import pytest

from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import needs_corpus

_corpus = needs_corpus()

NOTES = {
    (1, 10): "Alternative translation — 10.2.4, 1 fn 160: 'master'.",
    (1, 7): "Alternative translation — 7.1, 205 fn 130: 'victorious'.",
    (2, 2): "Alternative translation — 2.14, 10 fn 197: 'self-employed'.",
    (9, 7): "Referent — 7.1, 213 fn 133: 'he' is taken to be the native.",
    (10, 4): ("Variant — 4.11, 18 fn 165. M: 'the parents will be well known in the house of the Sultan'. "
              "Alternative translation — fn 166: 'he will be better at being a well-known acquaintance ... "
              "of the Sultan, as they are'."),
    (11, 11): "Alternative translation — 11.1, 26 fn 19: 'traced to a good lineage'.",
}
KEYS = sorted(NOTES)
IDS = [f"lord-of-{r}-in-{p}" for p, r in KEYS]


@pytest.mark.parametrize("placed_in, ruled", KEYS, ids=IDS)
def test_lords_cell_carries_its_footnote_as_a_note(engine, placed_in, ruled):
    cell = engine["MASHAALLAH_LORDS"][placed_in][ruled]
    assert cell.get("note") == NOTES[(placed_in, ruled)]
    assert "detail" not in cell


def test_the_note_reaches_the_signification_column(engine):
    # Lord of the seventh in the first: Libra rising, Mars (Aries' lord) in Libra.
    planets = {p: {'longitude': lon} for p, lon in
               [('Saturn', 10.0), ('Jupiter', 40.0), ('Mars', 185.0), ('Sun', 100.0),
                ('Venus', 130.0), ('Mercury', 160.0), ('Moon', 220.0)]}
    rows = engine["evaluate_house_lords"](planets, 180.0)
    row = next(r for r in rows if r['Topical House'] == 7)
    assert row['Placed in (WS place)'] == 1 and row['Domicile Lord'] == 'Mars'
    assert row["Masha'allah Signification"] == ("Good from women, and he successful (7.1, 205) "
                                                + NOTES[(1, 7)])


# (cell) -> [(sentence number, footnote number, spans its note quotes from it)]
SOURCES = {
    (1, 10): ("10.2.4", [(1, 160, ["master"])]),
    (1, 7): ("7.1", [(205, 130, ["victorious"])]),
    (2, 2): ("2.14", [(10, 197, ["self-employed"])]),
    (9, 7): ("7.1", [(213, 133, ["to be the native"])]),
    (10, 4): ("4.11", [(18, 165, ["M", "the parents will be well known in the house of the Sultan"]),
                       (18, 166, ["he will be better at being a well-known acquaintance",
                                  "of the Sultan, as they are"])]),
    (11, 11): ("11.1", [(26, 19, ["traced to a good lineage"])]),
}
CHAPTER_HEADS = {
    "2.14": r"^### \[Chapter 2\.14:", "4.11": r"^### \[Chapter 4\.11:", "7.1": r"^### Chapter \[7\.\] 1:",
    "10.2.4": r"^### \[Chapter 10\.2\.4:", "11.1": r"^### \[Chapter 11\.1:",
}


def _footnote_after_sentence(lines, chapter, sentence, fn):
    start = next(i for i, line in enumerate(lines) if re.match(CHAPTER_HEADS[chapter], line))
    pattern = re.compile(rf"(^|[ .>]){sentence} (?=[A-Z\[])")
    at, hit = next((i, m) for i in range(start, len(lines))
                   if not lines[i].startswith("<sup>") and (m := pattern.search(lines[i])))
    tail = lines[at][hit.end():]
    nxt = re.search(rf" {sentence + 1} [A-Z\[]", tail)
    assert f"<sup>{fn}</sup>" in (tail[:nxt.start()] if nxt else tail), (chapter, sentence, fn)
    note = next(line for line in lines[at:] if line.startswith(f"<sup>{fn}</sup> "))
    return note.replace("**", "")


@_corpus
@pytest.mark.parametrize("placed_in, ruled", KEYS, ids=IDS)
def test_every_quoted_span_is_its_footnotes_own(placed_in, ruled):
    lines = corpus_file("on_nativities.md").read_text(encoding="utf-8").splitlines()
    chapter, sources = SOURCES[(placed_in, ruled)]
    note = NOTES[(placed_in, ruled)]
    assert len(sources) >= 1
    for sentence, fn, spans in sources:
        assert f"fn {fn}" in note
        footnote = _footnote_after_sentence(lines, chapter, sentence, fn)
        assert len(spans) >= 1
        for span in spans:
            assert span in footnote, (fn, span, footnote)
            assert span in note
