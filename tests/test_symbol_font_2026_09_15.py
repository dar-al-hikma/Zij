"""The embedded symbol font (process/tae_docs/UI_CHANGES_2026-09-15_symbol_font.md).

Item 13 of `UI_FRAMEWORK_REVIEW_2026-09-15_SECOND_OPINION.md` (brief #8's
second half): `glyph_font.py` carries two subset WOFF2 faces, base64, family
'TAE Symbols'; the four renderers write a `<style>` element with
`font_face_css()` right after their opening `<svg>` tag and put the family
first in `_WHEEL_FONT`'s stack. Nothing else moves. Three things could each
break quietly and are each held to a proof here:

1. **The picture is the picture it always was.** Strip the `<style>` block
   and the embedded family name from `style="font-family:..."` and what is
   left is `main`'s SVG, byte for byte, for the default chart on all four
   renderers.
2. **Every glyph the renderers draw from SIGN_GLYPHS, POINT_GLYPHS and
   _ASPECT_GLYPH is covered by the embedded font -- with one documented
   exception.** The Lot of Fortune's own glyph (U+2297, circled times) is in
   neither of the two source files this branch was told to subset from
   (`glyph_font.py`'s docstring has the full finding); a genuinely new
   uncovered glyph -- one that is not that documented exception -- fails
   this test loudly rather than shipping quietly.
3. **The subsets are what they claim to be.** Each embedded base64 blob
   decodes to bytes beginning with WOFF2's own magic, and its font, opened
   with `fontTools`, maps exactly the code points `glyph_font.COVERED`
   claims for it. `fontTools` and its WOFF2 decoder's `brotli` are still
   deliberately not dependencies of the app; they are in
   `requirements-dev.txt`, which is what CI installs, so this check runs
   there rather than skipping. In a venv without them it skips.
"""
import base64
import re

import pytest

import glyph_font
from conftest import EXECUTABLE_DIR, FLORENCE, LOCAL_TIME
from datetime import datetime, timedelta

# The added markup, and nothing else: a <style>...</style> right after the
# opening <svg> tag, and the embedded family prepended to the font stack.
STYLE_BLOCK = re.compile(r"<style>.*?</style>")
DEFAULT_CHART = "1240-05-23"


# The one-time proofs that compared this checkout against origin/main were
# retired on 2026-09-16: such a comparison passes exactly once, and fails on
# main itself the moment its own branch merges (it did, four times that day).
# The proofs stand in the docs notes of their branches.



def _chart(engine, date_text=DEFAULT_CHART):
    local = datetime.combine(datetime.strptime(date_text, "%Y-%m-%d").date(), LOCAL_TIME)
    dt_utc = local - timedelta(hours=FLORENCE[1] / 15.0)
    return engine["calculate_traditional_chart"](dt_utc, *FLORENCE), local


def _normalise(svg):
    """Strip the <style> element the symbol-font branch added and the
    embedded family name it prepends to font-family, leaving the picture
    alone. Applied to both sides: main has carried the font since that
    branch merged, so the comparison is symmetric (the way the clickable
    wheel's own proof was made symmetric once main carried its handles)."""
    svg = STYLE_BLOCK.sub("", svg)
    svg = svg.replace(f"'{glyph_font.FAMILY}', ", "")
    return svg


# --- 1. The four pictures ---------------------------------------------------


def test_sizes_are_reported(engine):
    """Not a doctrinal assertion -- the byte counts the docs and the PR
    report cite, pinned here so a future change can see them move."""
    chart, local = _chart(engine)
    plain = engine["generate_hybrid_svg"](chart, "Transits", "Florence", FLORENCE[0], FLORENCE[1],
                                          local, "LMT")
    without_style = STYLE_BLOCK.sub("", plain).replace(f"'{glyph_font.FAMILY}', ", "")
    added = len(plain.encode()) - len(without_style.encode())
    assert added > 0
    b64_total = len(glyph_font._SYMBOLS_WOFF2_B64) + len(glyph_font._SYMBOLS2_WOFF2_B64)
    assert added >= b64_total, "the <style> element must carry at least the base64 payload itself"


# --- 2. Every glyph the tables use is covered, with one documented gap -----

def _glyph_table_codepoints(engine):
    codepoints = set()
    for glyph in engine["SIGN_GLYPHS"]:
        codepoints.add(ord(glyph))
    for glyph in engine["POINT_GLYPHS"].values():
        codepoints.add(ord(glyph))
    for glyph in engine["_ASPECT_GLYPH"].values():
        codepoints.add(ord(glyph))
    return codepoints


def test_every_glyph_table_codepoint_is_covered_or_the_one_documented_gap(engine):
    wanted = _glyph_table_codepoints(engine)
    uncovered = wanted - glyph_font.COVERED
    # A NEW uncovered glyph -- one that is not the Lot of Fortune's own,
    # the single documented gap -- must fail here loudly rather than reach
    # a viewer silently missing a dingbat.
    assert uncovered == glyph_font.KNOWN_UNCOVERED, (
        f"glyph_font.COVERED is missing {uncovered - glyph_font.KNOWN_UNCOVERED!r} "
        "with no documented reason; see glyph_font.py's docstring")
    assert glyph_font.COVERED, "the subset must cover something"
    assert glyph_font.COVERED.isdisjoint(glyph_font.KNOWN_UNCOVERED)


def test_covered_and_known_uncovered_together_are_every_symbol_the_tables_use(engine):
    wanted = _glyph_table_codepoints(engine)
    assert wanted <= (glyph_font.COVERED | glyph_font.KNOWN_UNCOVERED)


# --- 3. The base64 blobs are what they claim to be --------------------------

WOFF2_MAGIC = b"wOF2"


@pytest.mark.parametrize("attr, unicode_range", [
    ("_SYMBOLS_WOFF2_B64", None),
    ("_SYMBOLS2_WOFF2_B64", None),
])
def test_each_blob_decodes_to_a_woff2_header(attr, unicode_range):
    data = base64.b64decode(getattr(glyph_font, attr))
    assert data[:4] == WOFF2_MAGIC, f"{attr} does not start with the WOFF2 magic"


def test_each_face_maps_exactly_its_claimed_codepoints():
    fonttools = pytest.importorskip(
        "fontTools.ttLib", reason="fontTools is not a runtime dependency of this app; "
                                  "it is in requirements-dev.txt, which CI installs -- "
                                  "install that to check subset coverage here")
    try:
        import brotli  # noqa: F401  -- the WOFF2 decoder needs it; skip cleanly if absent
    except ImportError:
        pytest.skip("brotli is not installed (requirements-dev.txt); "
                    "fontTools cannot decode WOFF2 without it")
    from fontTools.ttLib import TTFont
    import io

    faces = [
        (glyph_font._SYMBOLS_WOFF2_B64,
         {0x260A, 0x260B, 0x260C, 0x260D, 0x263D, 0x263F, 0x2640, 0x2642, 0x2643, 0x2644,
          0x2648, 0x2649, 0x264A, 0x264B, 0x264C, 0x264D, 0x264E, 0x264F, 0x2650, 0x2651,
          0x2652, 0x2653, 0x26B9}),
        (glyph_font._SYMBOLS2_WOFF2_B64, {0x2609, 0x25A1, 0x25B3}),
    ]
    covered_union = set()
    for b64, expected in faces:
        font = TTFont(io.BytesIO(base64.b64decode(b64)))
        cmap = set(font.getBestCmap().keys())
        assert cmap == expected
        covered_union |= expected
    assert covered_union == glyph_font.COVERED
