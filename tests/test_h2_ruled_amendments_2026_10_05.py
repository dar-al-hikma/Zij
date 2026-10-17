"""Lane H2 of the re-pass: the owner's rulings 2, 7 and 8 of 2026-10-05.

Rulings 2 (the besieging relief) and 8 (the unresolved domain's source under
Masha'allah's rule) have their pins in test_repass_l2/l3_2026_10_04.py. Ruling
7 (Q10) had none: the Configurations page's quotation of Sahl, The
Introduction Ch. 3, 57 is quoted whole, or its cut is marked, never words
dropped unmarked nor "[that]" standing for words the page prints.
"""
from __future__ import annotations

import re

import pytest

from conftest import ui_source
from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import needs_corpus

_corpus = needs_corpus()

# Sahl I p. 61, read off the page photograph: 57 whole (its note markers 76 and
# 77 omitted). The page's quotation opens at "if", as its quotation of 56 does.
SAHL_57 = ("if the Moon was empty in course, and then she passed over into the next sign and connected with "
           "the lord of her first sign (or its exaltation), it is just like reception; and if she connected "
           "with a planet other than the lord of her first sign or its exaltation, it undermines her.")


def _quoted_57():
    text = ui_source()
    start = text.index("'57, **after the sign change**:")
    match = re.search(r'> "(.+?)"\\n', text[start:start + 2000])
    assert match, text[start:start + 300]
    return match.group(1)


def test_q10_sahl_57_is_quoted_whole_as_sahl_i_p61_prints_it():
    quoted = _quoted_57()
    assert quoted.startswith("if the Moon was empty in course"), quoted       # premise: the 57 quotation
    assert "[that]" not in quoted, quoted
    assert quoted == SAHL_57, quoted


@_corpus
def test_q10_the_corpus_sentence_is_the_one_quoted():
    """The corpus transcription of 57 carries the same words as the photograph."""
    lines = corpus_file("sahl_introduction_ch3.md").read_text(encoding="utf-8").splitlines()
    sentence = next(line for line in lines if line.startswith("57 And if the Moon was empty in course"))
    plain = re.sub(r"<sup>\d+</sup>", "", sentence)
    assert plain == "57 And " + SAHL_57, plain
