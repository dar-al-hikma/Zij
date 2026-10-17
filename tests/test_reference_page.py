"""The navigation in sections, the lesson gate retired, the Reference tables page
(2026-09-10, UI_REVIEW_2026-09-10.md §1 A and §3)."""
import re

import pytest

from conftest import assert_no_exception, make_app, ui_source


def test_the_lesson_gate_is_gone_and_nothing_is_hidden():
    src = ui_source()
    assert "Show material through" not in src and "lesson_gate" not in src
    assert 'st.navigation(pages, position="top")' in src
    for section in ('"**The Nativity**"', '"**Prediction**"', '"**Reference**"'):
        assert section in src
    at = make_app(page="chart").run()
    assert_no_exception(at, "chart")
    assert not [s for s in at.sidebar.selectbox if "material" in s.label.lower()]


def test_reference_page_prints_the_handy_tables_from_the_engines_data(engine):
    at = make_app(page="reference").run()
    assert_no_exception(at, "reference")
    heads = [h.value for h in at.main.subheader]
    assert heads == ["Dignities by sign", "Egyptian bounds", "Orders of the dignities, and the good places",
                     "Planetary years", "Degrees of nobility and rank", "The Ages of Man"]
    tables = {}
    for df in at.main.dataframe:
        tables.setdefault(tuple(df.value.columns), df.value)
    dign = next(v for k, v in tables.items() if "Domicile" in k)
    assert list(dign["Sign"]) == engine["SIGN_ORDER"]
    # Fig. 38's degrees are ordinals and print as the figure prints them.
    assert dign[dign["Sign"] == "Libra"].iloc[0]["Exaltation"] == "Saturn (21st degree of Libra)"
    assert dign[dign["Sign"] == "Aries"].iloc[0]["Exaltation"] == "Sun (19th degree of Aries)"
    assert dign[dign["Sign"] == "Taurus"].iloc[0]["Exaltation"] == "Moon (3rd degree of Taurus)"
    assert dign[dign["Sign"] == "Gemini"].iloc[0]["Exaltation"] == "-"
    assert dign[dign["Sign"] == "Aries"].iloc[0]["Faces (1st, 2nd, 3rd)"] == "Mars · Sun · Venus"
    bounds = next(v for k, v in tables.items() if "1st bound" in k)
    assert len(bounds) == 12 and bounds.iloc[0]["1st bound"] == "Jupiter 0°–5°59′"
    assert bounds[bounds["Sign"] == "Pisces"].iloc[0]["5th bound"] == "Saturn 28°–29°59′"
    years = next(v for k, v in tables.items() if "Mighty" in k)
    for _, r in years.iterrows():
        y = engine["PLANETARY_YEARS"][r["Planet"]]
        assert (r["Lesser"], r["Middle"], r["Greater"], r["Mighty"], r["Fardar (years)"]) == \
            (y["lesser"], y["middle"], y["greater"], y["mighty"], y["fardar"])
    # Sahl's Figure 57 as a twelve-row table, the empty signs a dash; under
    # Course text (the harness default) Abu Ma'shar's Figure 64 is not beside it.
    nob = next(v for k, v in tables.items() if "Sahl (On Nativities 1.38, 41)" in k)
    assert list(nob["Sign"]) == engine["SIGN_ORDER"] and len(nob.columns) == 2
    assert nob[nob["Sign"] == "Gemini"].iloc[0]["Sahl (On Nativities 1.38, 41)"] == "13th"
    assert nob[nob["Sign"] == "Libra"].iloc[0]["Sahl (On Nativities 1.38, 41)"] == "-"
    ages = next(v for k, v in tables.items() if "Period of life" in k)
    assert list(ages["Planet"]) == [p for p, _y, _d in engine["PN4_AGES_OF_MAN"]]
    assert list(ages["Period of life"]) == [d for _p, _y, d in engine["PN4_AGES_OF_MAN"]]


def test_the_static_tables_left_the_chart_page_for_the_reference_page():
    chart = make_app(page="chart").run()
    # (an expander with an icon is not typed as one by AppTest; read its caption)
    assert any("are on the Reference tables page" in c.value for c in chart.main.caption)
    assert "Sahl's sign categories for this chart's points" in ui_source()
    assert not [df for df in chart.main.dataframe if "Order, strongest first" in df.value.columns]
    ref = make_app(page="reference").run()
    assert [df for df in ref.main.dataframe if "Order, strongest first" in df.value.columns]
    assert [df for df in ref.main.dataframe if "Scheme" in df.value.columns]


# --- The Ages of Man (PN IV I.8, 9-26) -------------------------------------
# The Reference page's table said each age ran for its planet's lesser years
# "in the Chaldean order from the Moon", and closed Saturn's age at 98. I.8, 9
# orders the ages by sphere, lowest upward, and makes each span a planet's
# lesser years or a half or a tenth of its lesser or middle years (the Moon's
# 4 is a tenth of her middle years, I.8, 12; Mercury's 10 half his lesser
# years, I.8, 14); I.8, 25 runs the seventh age "until the end of his
# lifespan". The Fardar and ages page already printed it so.

def _ages_help(at):
    head = next(h for h in at.main.subheader if h.value == "The Ages of Man")
    return head.proto.help


def _ages_table(at):
    return next(df.value for df in at.main.dataframe
                if {"Planet", "Ruler"} & set(df.value.columns) and "Years" in df.value.columns)


def _spans(df):
    """[(planet, first year, the year after the last, or None if open-ended)],
    read from either shape the table has had: an 'Ages' string per row
    ("4-13", "68 onward") or 'From'/'To' columns."""
    out = []
    for _, r in df.iterrows():
        planet = r["Planet"] if "Planet" in df.columns else r["Ruler"]
        if "Ages" in df.columns:
            m = re.fullmatch(r"(\d+)(?:-(\d+)| onward)", str(r["Ages"]))
            assert m, f"unreadable age span {r['Ages']!r}"
            out.append((planet, int(m.group(1)), int(m.group(2)) + 1 if m.group(2) else None))
        else:
            out.append((planet, int(r["From"]), int(r["To"])))
    return out


def test_the_reference_ages_help_does_not_say_chaldean_or_lesser_years_for_all():
    text = _ages_help(make_app(page="reference").run())
    assert "Chaldean" not in text
    assert "for its lesser years" not in text
    # "lesser years" only as one of I.8, 9's kinds of span, never as the rule for all
    for m in re.finditer(r"lesser years", text):
        assert text[m.end():].startswith(", or a half or a tenth of its lesser or middle years"), text


def test_the_reference_ages_help_names_the_sphere_order_and_the_open_ended_last_age():
    text = _ages_help(make_app(page="reference").run())
    assert "ordered by sphere from the lowest upward" in text
    assert "a half or a tenth of its lesser or middle years (PN IV I.8, 9)" in text
    assert "the last age is open-ended (I.8, 25)" in text
    assert "The Fardar and ages page" in text


def test_the_reference_ages_last_row_is_open_ended(engine):
    at = make_app(page="reference").run()
    assert_no_exception(at, "reference")
    df = _ages_table(at)
    closed = sum(y for _p, y, _d in engine["PN4_AGES_OF_MAN"][:-1])
    assert _spans(df)[-1] == ("Saturn", closed, None), _spans(df)[-1]
    assert not df.isin([closed + 30, closed + 29]).any().any(), "Saturn's age is closed at 98"


def test_the_reference_and_fardar_pages_agree_on_every_age():
    ref = make_app(page="reference").run()
    far = make_app(page="fardar").run()
    assert_no_exception(ref, "reference")
    assert_no_exception(far, "fardar")
    ref_df, far_df = _ages_table(ref), _ages_table(far)
    assert _spans(ref_df) == _spans(far_df)
    for (_p, start, end), years in zip(_spans(ref_df), ref_df["Years"]):
        assert end is None or end - start == years


def test_the_reference_ages_caption_explains_saturns_30_beside_68_onward():
    """Saturn's row shows 30 years and "68 onward": the caption says why, as
    the Fardar and ages page's does -- PN IV Figure 53 tabulates 30, but the
    prose runs the seventh age "until the end of his lifespan" (I.8, 25)."""
    at = make_app(page="reference").run()
    assert_no_exception(at, "reference")
    captions = [c.value for c in at.main.caption]
    hit = [c for c in captions if "PN IV Figure 53 tabulates Saturn's 30" in c]
    assert len(hit) == 1, captions
    assert "Saturn's 30 (his lesser years, Gr. Intr. VII.8, Figure 146), but the prose governs" in hit[0]
    assert "the seventh age runs \"until the end of his lifespan\" (I.8, 25)" in hit[0]
    assert hit[0].startswith("The last age is open-ended")
