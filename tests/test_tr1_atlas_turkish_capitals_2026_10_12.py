"""TR1 (follow-up to B-14): a city typed in Turkish capitals finds its city.

``casefold`` follows no locale, so the dotted capital İ (U+0130) folded to
"i" and U+0307 COMBINING DOT ABOVE, and "İZMİR", "İSTANBUL" and "ZİYARET"
found nothing on the folded look (the atlas holds "Izmir", "Istanbul").
Now İ is mapped to i before the casefold, and a dot above that directly
follows an i (a text already lower-cased to i and the mark) is dropped
after it. Dotless ı (U+0131) is mapped to i too, on both sides, so that the
capital I standing for it ("YUKARI BEĞDEŞ") finds its name.

The first look (as typed) is unchanged, so a text that finds anything as
typed keeps exactly the options it had; only the second, folded look sees
the change. The atlas is part of the repository, so nothing here skips.
"""
import random
import sqlite3

import pytest

from conftest import APP_PATH
from test_b14_atlas_search_fold_2026_10_11 import (
    LOOKUP, SEEDED, _as_before, _lifted, atlas_matches)  # noqa: F401  (fixture)

ATLAS = APP_PATH.parent / "atlas.db"
DOT = "\u0307"


def _old_fold(text):
    import unicodedata
    return unicodedata.normalize("NFC", text or "").casefold()


@pytest.fixture(scope="module")
def fold():
    return _lifted("_atlas_fold")["_atlas_fold"]


def _first_label(atlas_matches, text):
    options, why = atlas_matches(text)
    assert why is None, text
    return next(iter(options))


@pytest.mark.parametrize("typed, city", [
    ("İZMİR", "İzmir"), ("İSTANBUL", "Istanbul"), ("İstanbul", "Istanbul"),
    ("İZMİ", "İzmir"), ("ZİYARET", "Ziyaret"), ("izmir", "İzmir"), ("IZMIR", "İzmir"),
    ("i" + DOT + "zmi" + DOT + "r", "İzmir"),   # already lower-cased, mark and all
])
def test_turkish_capitals_reach_their_city(atlas_matches, typed, city):
    options, why = atlas_matches(typed)
    assert why is None, typed
    assert any(label.startswith(city) for label in options), (typed, list(options))


@pytest.mark.parametrize("typed, city", [
    # names holding İ and another non-ASCII letter: neither NOCASE nor the ASCII
    # name reaches them, so the name side of the fold is their only route
    ("İNANÖZ", "İnanöz"), ("inanöz", "İnanöz"), ("İŞGÖREN", "İşgören"), ("işgören", "İşgören"),
    ("İÇMELER", "İçmeler"), ("İNÖNÜ", "İnönü"), ("içören", "İçören"), ("İKİKÖPRÜ", "İkiköprü"),
    ("İNCEĞİZ", "İnceğiz"), ("İMAMOĞLU", "İmamoğlu"),
    # a Turkish capital I that stands for dotless ı, on both sides of the fold
    ("YUKARI BEĞDEŞ", "Yukarı Beğdeş"), ("şırnak", "Şırnak"), ("çınarcık", "Çınarcık"), ("ığdır", "Iğdır"), ("YOLBAŞI", "Yolbaşı"), ("YAYLADAĞI", "Yayladağı"),
    ("YEŞİLYAZI", "Yeşilyazı"), ("yukarı beğdeş", "Yukarı Beğdeş"),
])
def test_a_name_with_more_than_one_non_ascii_letter_is_reached_through_the_fold_of_names(atlas_matches, typed, city):
    options, why = atlas_matches(typed)
    assert why is None, typed
    assert any(label.startswith(city) for label in options), (typed, list(options))


def test_the_turkish_capitals_give_what_the_ascii_spelling_gives(atlas_matches):
    assert atlas_matches("İZMİR") == atlas_matches("IZMIR")
    assert atlas_matches("İstanbul") == atlas_matches("Istanbul")


def test_the_fold_maps_the_dotted_capital_the_dot_and_the_dotless_i_to_i(fold):
    assert fold("İ") == "i"
    assert fold("i" + DOT) == "i"
    assert fold("İZMİR") == "izmir"
    assert fold("ı") == "i" and fold("I") == "i"
    assert fold("YUKARI BEĞDEŞ") == fold("Yukarı Beğdeş") == "yukari beğdeş"
    assert fold("ı" + DOT) == "i"
    # a dot above after anything but an i is a mark like any other
    # (q has no precomposed form with it, so NFC leaves the mark apart)
    assert fold("q" + DOT) == "q" + DOT
    assert fold("Q" + DOT + "i") == "q" + DOT + "i"
    assert fold("e" + DOT) == _old_fold("e" + DOT)
    assert fold("Ünal İ") == "ünal i"


def _holds_dotted(text):
    """A text the fold moves: one holding İ, ı or i and a dot above."""
    return "\u0130" in text or "\u0131" in text or "i" + DOT in _old_fold(text)


def test_a_text_holding_neither_folds_as_it_did(fold):
    texts = [t for t in SEEDED if not _holds_dotted(t)]
    assert len(texts) > 150
    assert [t for t in texts if fold(t) != _old_fold(t)] == []
    with sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True) as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM cities")]
    moved = [n for n in names if fold(n) != _old_fold(n)]
    assert moved
    assert [n for n in moved if not _holds_dotted(n)] == []
    assert [n for n in names if _holds_dotted(n) is False and fold(n) != _old_fold(n)] == []


def test_a_text_holding_neither_gives_the_options_it_gave(atlas_matches):
    """Over the seeded texts of B-14 (several cases and scripts), a text
    with neither a dotted capital I nor i and a dot above gives what the
    old fold gives: the old fold stands in for the new one in the same
    lookup."""
    old = _lifted(*LOOKUP)
    old["_atlas_fold"] = _old_fold
    texts = [t for t in SEEDED if not _holds_dotted(t)]
    assert len(texts) > 150
    assert [t for t in texts if atlas_matches(t) != old["_atlas_matches"](t)] == []


def test_a_text_that_matches_as_typed_is_unmoved_by_the_fold(atlas_matches):
    for text in ("İzmir", "izmir", "Istanbul", "İ", "i"):
        before = _as_before(text)
        if before is not None:
            assert atlas_matches(text)[0] == before, text
    # a dotless ı typed as it is in the atlas matches as typed: its options
    # are the base's, not those of a text with the ı already folded to i
    before = _as_before("Çınar")
    assert before and len(before) > 1
    assert atlas_matches("Çınar")[0] == before
    # in lower case it misses as typed and is looked up folded: it offers
    # the Turkish Çınar places too, not the one place a ı-for-i text would
    options = atlas_matches("çınar")[0]
    assert options and [label for label in options if label.startswith("Çınar") and "(TR)" in label][1:]


def _turkish_capitals(name):
    """The name in Turkish capitals: i to İ, ı to I, then upper."""
    return name.replace("i", "İ").replace("ı", "I").upper()


def _reached(atlas_matches, text, place):
    options, _why = atlas_matches(text)
    return bool(options) and place in options.values()


def test_a_seeded_sample_of_turkish_names_in_turkish_capitals_reaches_wherever_the_ascii_spelling_does(atlas_matches):
    """Turkish capitals (i to İ, ı to I, then upper) against the atlas's own
    ASCII spelling in capitals (ascii_name, upper-cased), over 200 TR names
    drawn with a fixed seed: 70 with ı and another non-ASCII letter, 50 with
    an i and a non-ASCII letter (no ı), 40 with an i and nothing else non-ASCII,
    40 with no i or ı. Each reaches its own place wherever the ASCII
    spelling does (the full emulation over all 4,028 names is a script, not
    part of the suite)."""
    with sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True) as conn:
        rows = conn.execute("SELECT name, lat, lon, ascii_name FROM cities WHERE country = 'TR' ORDER BY id").fetchall()
    # 4,028 TR rows in the atlas of v1.0.0; 4,076 in the atlas rebuilt from
    # GeoNames' dump of 2026-10-14 (ATLAS1's rebuild, rulings 172 and 179
    # S-01): the dump's own growth. The seeded sample is drawn from these.
    assert len(rows) == 4076
    dotless = [r for r in rows if "ı" in r[0] and not r[0].isascii()]
    with_i = [r for r in rows if "i" in r[0] and "ı" not in r[0] and not r[0].isascii()]
    plain_i = [r for r in rows if "i" in r[0] and r[0].isascii()]
    neither = [r for r in rows if "i" not in r[0] and "ı" not in r[0]]
    rnd = random.Random(2611)
    sample = rnd.sample(dotless, 70) + rnd.sample(with_i, 50) + rnd.sample(plain_i, 40) + rnd.sample(neither, 40)
    ascii_reach = [_reached(atlas_matches, a.upper(), (la, lo)) for n, la, lo, a in sample]
    turkish_reach = [_reached(atlas_matches, _turkish_capitals(n), (la, lo)) for n, la, lo, a in sample]
    # a short common name ("Çalı") can be crowded out of the twenty in one
    # spelling and not the other, so the pin is: nothing the ASCII spelling
    # reaches is lost in Turkish capitals
    assert [n for (n, *_rest), a, t in zip(sample, ascii_reach, turkish_reach) if a and not t] == []
    assert sum(turkish_reach) >= 190
