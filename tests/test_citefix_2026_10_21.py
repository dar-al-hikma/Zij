"""Two code comments in engine.py held to the page.

The comment over JN_YEARS_LADDER quotes 'Umar al-Tabari's reading of the
superiors (TBN I.4.3, Persian Nativities II p. 14): every quoted run, split at
an ellipsis, is printed on that page, and the note it points to is named as the
program's own. The comment at the station split in the forward simulation says
nothing about the texts ordering stations and sign changes: they do not, and
the split is ephemeris arithmetic.

The source is read as text; nothing imports the app.
"""
from __future__ import annotations

import re

from conftest import ENGINE_PATH
from corpus_paths import corpus_file, page_marker
from skip_guard import skip_without_corpus

PN2 = corpus_file("pn2/pn2_photographed.md")


def _lines():
    return ENGINE_PATH.read_text(encoding="utf-8").splitlines()


def _comment_block_above(anchor):
    """The run of comment lines directly above the one line that starts with
    `anchor` (indentation ignored), joined into one string."""
    lines = _lines()
    at = [i for i, line in enumerate(lines) if line.lstrip().startswith(anchor)]
    assert len(at) == 1, f"{anchor!r} found {len(at)} times in engine.py"
    block = []
    i = at[0] - 1
    while i >= 0 and lines[i].lstrip().startswith("#"):
        block.insert(0, lines[i].lstrip()[1:].strip())
        i -= 1
    assert block, f"no comment above {anchor!r}"
    return " ".join(block)


def _squeeze(text):
    return re.sub(r"\s+", " ", text).strip()


def _umar_quotation():
    block = _comment_block_above("JN_YEARS_LADDER = {")
    found = re.search(r"'Umar's reading of the superiors \(([^\"]*)\"([^\"]+)\"\)", block)
    assert found, "the comment over JN_YEARS_LADDER no longer quotes 'Umar's reading of the superiors"
    return block, found.group(1), found.group(2)


def _pn2_page_14():
    text = PN2.read_text(encoding="utf-8")
    lo = text.index(page_marker("PN II", 14))
    hi = text.index(page_marker("PN II", 15), lo)
    page = re.sub(r"<sup>\d+</sup>", "", text[lo:hi])
    return _squeeze(page)


def test_umar_quotation_names_the_work_and_the_programs_own_note():
    block, before, _ = _umar_quotation()
    assert "TBN I.4.3" in before and "PN II p. 14" in before, before
    assert "the program's own note printed under 1.20, 14-15" in block, block
    assert "14-15's note" not in block, "reads as Dykes's footnote; name the program's note"


def test_umar_quotation_is_verbatim_on_pn2_page_14():
    skip_without_corpus(PN2)
    _, _, quoted = _umar_quotation()
    page = _pn2_page_14()
    runs = [_squeeze(run) for run in re.split(r"\s*\.\.\.\s*", quoted)]
    assert runs and all(runs), quoted
    missing = [run for run in runs if run not in page]
    assert not missing, f"quoted runs not printed on PN II p. 14: {missing}"


def test_station_split_does_not_say_the_texts_order_stations_and_sign_changes():
    block = _squeeze(_comment_block_above("pieces = [(days[i], lons[i]), (days[i + 1], lons[i + 1])]"))
    assert "split at the station" in block, block
    assert not re.search(r"\border(s|ing)?\b[^.]*\bstations?\b", block), block
    for locator in ("Gr. Intr. VII.5, 117-119", "Aphorism 48, 99-102"):
        assert locator not in block, block
    # Nor in other words, as far as these lists reach: no sentence of the
    # comment that names a station or a sign change also says before, after,
    # precedes or follows, and the comment names none of the works, authors
    # or words for them listed below, the words in either case.
    ordered = [sentence for sentence in block.split(".")
               if re.search(r"\bstation\w*|\bsign changes?\b|\bchang\w* (?:of )?signs?\b", sentence, re.I)
               and re.search(r"\b(?:before|after|preced\w*|follow\w*)\b", sentence, re.I)]
    assert not ordered, (ordered, block)
    cited = re.findall(r"Gr\. Intr\.|Aphorism|\bSahl\b|\bPN [IV]+\b|Persian Nativities|\bCarmen\b|Introduction"
                       r"|(?i:\b(?:texts?|sources?|authors?|tradition|doctrine|taught|teach\w*)\b)"
                       r"|(?i:\b(?:books?|astrologers?|authorit\w*|ancients?|writers?)\b)"
                       r"|Ma.shar|Ptolemy|Dykes|Bonatti|Dorotheus|Masha", block)
    assert not cited, (cited, block)
