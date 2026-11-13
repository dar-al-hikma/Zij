"""The comment over the quadrant genders, and the sets it describes.

The comment once said that Gr. Intr. IV.8, 16, which defines the quadrants,
lay outside the corpus. It is Gr. Intr. p. 251. The comment now cites IV.8, 16
and VI.26, 3-4 by volume, writes its table in the book's direction (Asc to MC
= 12, 11, 10), and quotes only what those two pages say. The sets themselves
do not change.
"""
from __future__ import annotations

import re

import pytest

import engine
from conftest import engine_source
from corpus_paths import corpus_file, page_marker
from skip_guard import needs_corpus

GR_INTR = corpus_file("gr_intr/abu_mashar_great_introduction.md")
ANCHOR = "MASCULINE_QUADRANT_HOUSES = {"


def comment_block(source: str | None = None) -> str:
    """The comment lines directly above MASCULINE_QUADRANT_HOUSES, '#' cut,
    joined by single spaces."""
    lines = (engine_source() if source is None else source).split("\n")
    at = next(i for i, ln in enumerate(lines) if ln.startswith(ANCHOR))
    block = []
    for ln in reversed(lines[:at]):
        if not ln.startswith("#"):
            break
        block.append(ln[1:].strip())
    assert block, "no comment above MASCULINE_QUADRANT_HOUSES"
    return re.sub(r"\s+", " ", " ".join(reversed(block))).strip()


ABSENCE = re.compile(r"outside (?:this|the) corpus|not in (?:this|the) corpus|unsourced|absent from the corpus",
                     re.I)


# Words a claim of absence reaches for and this block never needs; the block
# has no reason to name the corpus at all.
NEVER_NEEDED = re.compile(r"corpus|\b(?:outside|missing|absent|beyond|lack\w*|hold|holds|held)\b", re.I)


def test_the_block_claims_no_absence_and_carries_no_process_word():
    text = comment_block()
    assert not ABSENCE.search(text), text
    assert not NEVER_NEEDED.search(text), text
    assert "VERIFIED" not in text and "previously" not in text, text


def test_every_chapter_and_sentence_locator_in_the_block_names_its_volume():
    """A back-reference such as "(IV.8, 16)" names Gr. Intr. as well."""
    text = comment_block()
    found = list(re.finditer(r"(?<![\w.])[IVX]+\.\d+, \d+", text))
    assert len(found) >= 6, text
    for m in found:
        assert text[:m.start()].endswith("Gr. Intr. "), (m.group(), text)


@pytest.mark.parametrize("locator", ["Gr. Intr. IV.8, 16", "Gr. Intr. VI.26, 3-4", "Gr. Intr. VII.6, 28-29",
                                     "Gr. Intr. Fig. 34", "Gr. Intr. Fig. 90"])
def test_the_block_cites_by_volume(locator):
    assert locator in comment_block()


ROWS = [("Asc to MC", (12, 11, 10), "MALE"), ("MC to Desc", (9, 8, 7), "FEMININE"),
        ("Desc to IC", (6, 5, 4), "MALE"), ("IC to Asc", (3, 2, 1), "FEMININE")]


def test_the_table_runs_in_the_books_direction_and_matches_the_sets():
    text = comment_block()
    for ends, houses, gender in ROWS:
        row = re.search(re.escape(ends) + r" = " + r", ".join(str(h) for h in houses) + r" -> \w+, (\w+),", text)
        assert row and row.group(1) == gender, (ends, text)
        side = engine.MASCULINE_QUADRANT_HOUSES if gender == "MALE" else engine.FEMININE_QUADRANT_HOUSES
        assert set(houses) <= side
    for reversed_ends in ("MC to Asc", "Desc to MC", "Asc to IC", "IC to Desc"):
        assert reversed_ends not in text


def test_the_sets_are_unchanged_and_complementary():
    assert engine.MASCULINE_QUADRANT_HOUSES == {4, 5, 6, 10, 11, 12}
    assert engine.FEMININE_QUADRANT_HOUSES == {1, 2, 3, 7, 8, 9}
    assert engine.MASCULINE_QUADRANT_HOUSES | engine.FEMININE_QUADRANT_HOUSES == set(range(1, 13))
    assert not engine.MASCULINE_QUADRANT_HOUSES & engine.FEMININE_QUADRANT_HOUSES


def test_the_block_parser_finds_a_planted_claim():
    """The pin above can fail: the old sentence, planted back, is found."""
    src = engine_source().replace(
        "\n" + ANCHOR, "\n# them at IV.8, 16,\n# outside this corpus.\n" + ANCHOR, 1)
    assert ABSENCE.search(comment_block(src))


def page_text(page: int) -> str:
    """Gr. Intr. `page` in the corpus, from its marker to the next page's."""
    text = GR_INTR.read_text(encoding="utf-8")
    start = text.index(page_marker("Gr. Intr.", page))
    end = text.index(page_marker("Gr. Intr.", page + 1), start)
    return text[start:end]


def flat(text: str) -> str:
    """Words only: markup, footnote marks, line-break hyphens and spacing dropped."""
    text = re.sub(r"<sup>.*?</sup>|\*+", "", text).replace("-", "")
    return re.sub(r"\s+", " ", text).strip()


@needs_corpus(GR_INTR)
def test_iv_8_16_is_in_the_corpus_on_gr_intr_p_251():
    page = flat(page_text(251))
    assert "16 And [2] if the planets were from the Ascendant" in page
    assert "two eastern quadrants they indicate masculinization" in page
    assert "Masculine and feminine quadrants" in page


@needs_corpus(GR_INTR)
def test_every_quotation_in_the_block_is_on_its_page():
    p251, p386 = flat(page_text(251)), flat(page_text(386))
    quotes = re.findall(r'"([^"]+)"', comment_block())
    assert quotes
    for q in quotes:
        assert flat(q) in p251 or flat(q) in p386, q
    assert any(flat(q) in p251 for q in quotes), "nothing quoted from IV.8, 16"
    assert any(flat(q) in p386 for q in quotes), "nothing quoted from VI.26, 3"
