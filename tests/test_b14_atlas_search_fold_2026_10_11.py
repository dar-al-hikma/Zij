"""B-14 of the third outside pass (ruling 146): the city search folds case
and normalization for letters outside ASCII.

The offline atlas search matched ``name LIKE ? COLLATE NOCASE`` and the same
on ``ascii_name``. SQLite's NOCASE and LIKE fold ASCII letters only, so
"évora", "århus", "łódź" and "ZÜRICH" found nothing ("No matches found in
offline atlas.") while "Évora", "Århus", "Łódź" and "Zürich" found their
places, and an accent typed as a separate combining mark (NFD) found
nothing in any case.

Now a text that finds nothing as typed is looked up once more, with the text
and each name composed (NFC) and case-folded (``casefold``). A text that
finds anything as typed keeps exactly the options it had, in the same
order: a casefold of both sides would also have made "Groß" match
"Grosseto", "Grosse Pointe ..." and "Grossos", which it never did.

The pins: each miss now offers what its title-case spelling offers (on the
page); the title-case spellings offer what they did; a seeded set of texts
that match as typed give the options the lookup of before gives, in its
order; a text with no match still says "No matches" and casts nothing.
The atlas is part of the repository, so nothing here skips.
"""
import ast
import contextlib
import pathlib
import random
import sqlite3
import unicodedata

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, ui_source

ATLAS = APP_PATH.parent / "atlas.db"
TIME_ZONES_PATH = APP_PATH.parent / "time_zones.py"
PICKER = "Select specific location:"
NO_MATCH = "No matches found in offline atlas."

ZURICH = ["Zürich, ZH (CH)", "Zürich (Kreis 11), ZH (CH)", "Zürich (Kreis 3), ZH (CH)",
          "Zürich (Kreis 9), ZH (CH)", "Zürich (Kreis 10), ZH (CH)", "Zürich (Kreis 7), ZH (CH)",
          "Zürich (Kreis 6), ZH (CH)", "Zürich (Kreis 2), ZH (CH)", "Zürich (Kreis 9) / Altstetten, ZH (CH)",
          "Zürich (Kreis 12), ZH (CH)", "Zürich (Kreis 4) / Aussersihl, ZH (CH)",
          "Zürich (Kreis 3) / Sihlfeld, ZH (CH)", "Zürich (Kreis 6) / Unterstrass, ZH (CH)",
          "Zürich (Kreis 11) / Oerlikon, ZH (CH)", "Zürich (Kreis 11) / Seebach, ZH (CH)",
          "Zürich (Kreis 11) / Affoltern, ZH (CH)", "Zürich (Kreis 10) / Höngg, ZH (CH)",
          "Zürich (Kreis 9) / Albisrieden, ZH (CH)", "Zürich (Kreis 2) / Wollishofen, ZH (CH)",
          "Zürich (Kreis 10) / Wipkingen, ZH (CH)"]

# What each title-case spelling offers (as it did before the fix).
TITLE_CASE = {
    "Évora": ["Évora, 08 (PT)", "Évora, 13 (PT)", "Évora Monte, 08 (PT)"],
    "Århus": ["Århus, 18 (DK)"],
    "Łódź": ["Łódź, 74 (PL)"],
    "Zürich": ZURICH,
    "Großräschen": ["Großräschen, 11 (DE)"],
    # h with a line below: no capital is precomposed, so in capitals it is
    # H and a combining mark, and its casefold is h and that mark.
    "Petaẖ Tiqva": ["Petaẖ Tiqva, 02 (IL)"],
}

# Each miss of the reproduction, and the spelling whose options it must give.
MISSES = [
    pytest.param("évora", "Évora", id="evora-lower"),
    pytest.param(unicodedata.normalize("NFD", "Évora"), "Évora", id="evora-nfd"),   # the accent typed as a mark
    pytest.param(unicodedata.normalize("NFD", "évora"), "Évora", id="evora-lower-nfd"),
    pytest.param("århus", "Århus", id="arhus-lower"),
    pytest.param("łódź", "Łódź", id="lodz-lower"),
    pytest.param("ZÜRICH", "Zürich", id="zurich-capitals"),
    # casefold, not lower: ß folds to ss, and no ASCII spelling helps here
    # (the atlas's is "Grossraeschen", and "PETAH" is not "Peta\u1e96").
    pytest.param("GROSSRÄSCHEN", "Großräschen", id="grossraschen-capitals"),
    pytest.param("PETAH\u0331 TIQVA", "Peta\u1e96 Tiqva", id="petah-tiqva-capitals"),
    # surrounding spaces are not part of a name, on the folded look too
    pytest.param("  \u00e9vora  ", "\u00c9vora", id="evora-lower-padded"),
    pytest.param("\tZ\u00dcRICH ", "Z\u00fcrich", id="zurich-capitals-padded"),
]


# --- the lookup itself, lifted from app.py -----------------------------------

class _ReadOnlySqlite:
    """sqlite3 as the lookup uses it, except that connect opens the atlas
    read-only whatever it is handed: these tests never write to atlas.db.
    (The lookup itself opens it read-only since SC-07: a file: URI.)"""
    def __getattr__(self, name):
        return getattr(sqlite3, name)

    @staticmethod
    def connect(path, *args, uri=False, **kwargs):
        if uri:
            assert str(path).startswith("file:") and str(path).endswith("?mode=ro"), path
            return sqlite3.connect(path, uri=True)
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _degrees_text(value, places):
    return f"{value:.{places}f}"


def _lifted(*names):
    """Module-level definitions of app.py and of time_zones.py, by their
    source, in one namespace. The fold, the prefix and the query moved to
    time_zones.py (ruling 175 (7)); app.py keeps _atlas_matches, which makes
    the labels and the sentences, and the ATLAS_ sentences themselves."""
    namespace = {"Path": pathlib.Path, "sqlite3": _ReadOnlySqlite(), "unicodedata": unicodedata,
                 "contextlib": contextlib, "degrees_text": _degrees_text, "__file__": str(APP_PATH)}
    found = set()
    for source in (TIME_ZONES_PATH.read_text(encoding="utf-8"), ui_source()):
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and node.name in names:
                exec(ast.get_source_segment(source, node), namespace)
                found.add(node.name)
            elif isinstance(node, ast.Assign) and any(getattr(t, "id", "").startswith("ATLAS_") for t in node.targets):
                exec(ast.get_source_segment(source, node), namespace)
    assert found == set(names), (sorted(set(names) - found))
    return namespace


LOOKUP = ("_atlas_matches", "atlas_rows", "_atlas_fold", "_like_prefix")


@pytest.fixture(scope="module")
def atlas_matches():
    return _lifted(*LOOKUP)["_atlas_matches"]


def _as_before(text):
    """The lookup as it stood before the fix (main at c692300): the same
    query and the same labels, for the texts that matched then."""
    prefix = text.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    with sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True) as conn:
        rows = conn.execute("""
            SELECT name, admin1, country, lat, lon
            FROM cities
            WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE OR ascii_name LIKE ? ESCAPE '\\' COLLATE NOCASE
            ORDER BY population DESC
            LIMIT 20
        """, (prefix, prefix)).fetchall()
    if not rows:
        return None
    options = {}
    for m in rows:
        region = (m[1] or '').strip()
        label = f"{m[0]}, {region} ({m[2]})" if region else f"{m[0]} ({m[2]})"
        if label in options:
            label += f" [{_degrees_text(m[3], 4)}, {_degrees_text(m[4], 4)}]"
        options[label] = (m[3], m[4])
    return options


def _seeded_texts():
    """Texts a reader types, drawn from the atlas with a fixed seed: whole
    names, their first letters as written, in lower case and (for an ASCII
    name) in capitals; and a fixed set of the usual ones."""
    with sqlite3.connect(f"file:{ATLAS}?mode=ro", uri=True) as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM cities ORDER BY id")]
    rnd = random.Random(1414)
    texts = {"London", "Lon", "New York", "Petoskey", "São Paulo", "são paulo", "Évora", "Evora",
             "Zürich", "Zur", "Madrid", "Berlin", "x", "  London  ", "Groß", "groß", "GROSS",
             "Großräschen", "ÉVORA", "zürich", "Aş Ş", "Ōsaka", "Đồng", "İzmir", "izmir", "Москва", "東京", "Flor"}
    for name in rnd.sample(names, 60):
        texts |= {name, name[:4], name[:4].lower()}
        if name.isascii():
            texts.add(name.upper())
    return sorted(texts)


SEEDED = _seeded_texts()


# --- the page ------------------------------------------------------------------

def _picker_options(at):
    pickers = [s for s in at.sidebar.selectbox if s.label == PICKER]
    return pickers[0].options if pickers else []


def _messages(at):
    return [e.value for where in (at.sidebar, at.main) for kind in ("error", "warning")
            for e in getattr(where, kind)]


def _city_app(text):
    at = make_app(page="chart")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = text
    return at.run()


@pytest.mark.parametrize("typed, spelling", MISSES)
def test_a_miss_offers_what_its_title_case_spelling_offers(typed, spelling):
    at = _city_app(typed)
    assert_no_exception(at, repr(typed))
    assert NO_MATCH not in _messages(at)
    assert _picker_options(at) == TITLE_CASE[spelling]
    assert [s.value for s in at.sidebar.success][0].startswith(f"**{TITLE_CASE[spelling][0]}**")


def test_a_text_with_no_match_still_says_so_and_casts_nothing():
    for text in ("xqzw-no-such-city", "ŵxqz-no-such-city"):
        at = _city_app(text)
        assert_no_exception(at, text)
        assert NO_MATCH in [w.value for w in at.sidebar.warning]
        assert _picker_options(at) == []
        assert not at.sidebar.success and not at.sidebar.info


# --- the lookup ----------------------------------------------------------------

@pytest.mark.parametrize("spelling", list(TITLE_CASE))
def test_the_title_case_spelling_offers_what_it_did(atlas_matches, spelling):
    options, why = atlas_matches(spelling)
    assert why is None and list(options) == TITLE_CASE[spelling]
    assert options == _as_before(spelling)


@pytest.mark.parametrize("typed, spelling", MISSES)
def test_a_miss_resolves_as_its_spelling_does(atlas_matches, typed, spelling):
    assert atlas_matches(typed) == atlas_matches(spelling)


def test_a_text_that_matched_as_typed_keeps_its_options_and_their_order(atlas_matches):
    """Every seeded text that the lookup of before matched gives the same
    options, labels and places in the same order; one it missed gives
    nothing, or only names that begin with it once both are folded."""
    def fold(s):
        return unicodedata.normalize("NFC", s).casefold()
    assert len(SEEDED) > 150
    checked = 0
    for text in SEEDED:
        before = _as_before(text)
        options, why = atlas_matches(text)
        if before is not None:
            checked += 1
            assert why is None and list(options.items()) == list(before.items()), text
        elif options is not None:
            assert options
            assert all(fold(label).startswith(fold(text.strip())) for label in options), (text, list(options))
        else:
            assert why == NO_MATCH, text
    assert checked >= 150, checked


def test_groß_offers_no_name_spelled_with_ss(atlas_matches):
    """The reason the folded look is a second look: "Groß" folds to
    "gross", which begins Grosseto, Grosse Pointe ... and Grossos; a
    casefold of both sides would have added them to a text that matched."""
    assert unicodedata.normalize("NFC", "Groß").casefold() == "gross"
    for text in ("Groß", "groß"):
        options, _why = atlas_matches(text)
        assert options
        assert not any(label.startswith("Gross") for label in options), (text, list(options))
        assert list(options) == list(_as_before("Groß"))


@pytest.mark.parametrize("text", ["%", "Flor%", "_", "\\", "ÉVORA%", "évor_"])
def test_a_wildcard_is_still_text_when_the_text_is_folded(atlas_matches, text):
    """The second, folded look escapes the text as the first does."""
    options, why = atlas_matches(text)
    assert options is None and why == NO_MATCH, (text, options)
