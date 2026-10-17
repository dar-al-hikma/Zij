"""The sidebar and the chart strip: lane G13 of the re-pass of 2026-10-04
(L1-N4, L1-N5, L6R-N8), beside the re-pass's own pins.

* A manual offset is named as it is cast -- to the second when it holds
  seconds -- in the box, on the strip and in the export, and an offset that
  rounds to nothing is signed + wherever it is printed (L1-N4, L1-N5).
* The strip's offset is the box's, under every time standard (L1-N5).
* A chart's name and a place label reach the strip and every sidebar
  sentence that names them as typed, on one line (L6R-N8): the Saved,
  already-saved, Replace and Delete sentences, the "saved under other
  readings" question, the sentences of a record the loader refused or
  flagged (H3, H5, L6R-N3, the time standard), the sentence of a record
  another window moved (L6R-N7), the resolved place and the home place. A
  plain name is printed as it is; any other is a Markdown code span, whose
  text Streamlit neither parses nor rewrites afterwards -- a backslash
  escape is resolved before its second pass turns "https://", "www.", mail
  addresses, ":streamlit:", ":material/...:", ":smile:" and " -- " into
  links, pictures and dashes (seen in Firefox with Streamlit's own frontend,
  the lane's check of 2026-10-04). AppTest holds the Markdown, not what is
  drawn, so these tests read the Markdown's inline code spans.
"""
import json
import os
import re
from datetime import time
from pathlib import Path

import pytest

from conftest import assert_no_exception, make_app

LMT, ZONE, MANUAL = "LMT (Local Mean Time)", "Standard time (named zone)", "Manual UTC offset"
FLORENCE = (43.7792, 11.2463)
FLORENCE_REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": LMT,
                "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
HOSTILE = "Smith *draft* $x$ :red[B] [w](https://example.org)"


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A disposable XDG directory; preferences stay off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def _store():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d / "saved_charts.json"


def _cast(standard, lat, lon, offset=None, date="1982-06-01", hhmm=(12, 0)):
    at = make_app(date=date, page="chart")
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hhmm)
    at.session_state["time_standard_key"] = standard
    if offset is not None:
        at.session_state["utc_offset_key"] = offset
    at.run()
    assert_no_exception(at, f"{standard} {offset} at {lat}, {lon}")
    return at


def _box(at):
    return "\n".join(n.value for n in at.sidebar.info)


def _strip(at):
    return next(c.value for c in at.main.caption if " · " in c.value)


def _entered(at):
    return _strip(at).split("  \n")[0]


def _sidebar_texts(at):
    out = []
    for kind in ("error", "warning", "info", "success", "caption", "markdown"):
        out += [e.value for e in getattr(at.sidebar, kind)]
    return out


def _picker(at):
    return at.sidebar.selectbox(key="chart_picker")


def _save_as(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    assert_no_exception(at, f"save as {name!r}")
    return at


def _export(at):
    exp = at.session_state["_analysis_export"]
    return exp if isinstance(exp, dict) else json.loads(exp)


# --- L1-N4: a manual offset is named as it is cast ---------------------------

@pytest.mark.parametrize("offset, label", [
    (5.125, "UTC+05:07:30"),          # the finding's own
    (13.999, "UTC+13:59:56"),         # 50396.4 s, rounded to the second as LMT's are
    (-3.2575, "UTC-03:15:27"),
    (5.75, "UTC+05:45"),              # a quarter-hour holds no seconds and prints none
    (-0.0001, "UTC+00:00"),           # rounds to nothing: no minus sign (L1-N5)
])
def test_a_manual_offset_is_named_as_cast_in_the_box_the_strip_and_the_export(offset, label):
    at = _cast(MANUAL, *FLORENCE, offset=offset)
    assert f"**Manual offset** {label}  \n" in _box(at), _box(at)
    assert f" · {label} · " in _entered(at), _entered(at)
    assert _export(at)["input"]["timezone"] == label, _export(at)["input"]
    assert _export(at)["input"]["utc_offset_hours"] == offset, "the offset cast is the offset typed"


def test_the_universal_time_the_box_prints_agrees_with_the_seconds_it_names():
    at = _cast(MANUAL, *FLORENCE, offset=5.125)
    assert "UTC+05:07:30  \nUT 1982-06-01 06:52:30" in _box(at), _box(at)


# --- L1-N5: the strip's offset is the box's ----------------------------------

def _box_offset(at):
    text = _box(at)
    m = (re.search(r"UTC offset ([+-]\d\d:\d\d(?::\d\d)?)", text)
         or re.search(r"\*\*Manual offset\*\* UTC([+-]\d\d:\d\d(?::\d\d)?)", text))
    assert m, text
    return m.group(1)


def _strip_offset(at):
    standard = _entered(at).split(" · ")[2]
    m = re.search(r"([+-]\d\d:\d\d(?::\d\d)?)$", standard)
    assert m, standard
    return m.group(1)


@pytest.mark.parametrize("standard, lat, lon, offset", [
    (LMT, 43.7792, 11.2463, None),        # east: +00:44:59
    (LMT, 0.0, -0.001, None),             # a thousandth of a degree west: rounds to nothing
    (LMT, 0.0, 0.001, None),
    (LMT, 45.37334, -84.95533, None),     # west
    (MANUAL, 43.7792, 11.2463, 5.125),
    (MANUAL, 43.7792, 11.2463, -0.0001),
    (MANUAL, 43.7792, 11.2463, -5.0),
    (ZONE, 43.7792, 11.2463, None),       # Europe/Rome, summer time
    (ZONE, 40.71427, -74.00597, None),    # America/New_York, summer time
])
def test_the_strip_prints_the_offset_the_box_prints(standard, lat, lon, offset):
    at = _cast(standard, lat, lon, offset=offset)
    assert _strip_offset(at) == _box_offset(at), (_entered(at), _box(at))
    assert not _strip_offset(at).startswith("-00:00:00") and _strip_offset(at) != "-00:00"


# --- L6R-N8: a name and a place label are printed as typed --------------------

def _segments(markdown):
    """The Markdown's inline code spans and the text between them, as
    CommonMark reads them: a run of n backticks opens a span closed by the
    next run of exactly n; one space is stripped from each side of a span
    that has one on both."""
    out, text, i = [], "", 0
    while i < len(markdown):
        if markdown[i] != "`":
            text += markdown[i]
            i += 1
            continue
        j = i
        while j < len(markdown) and markdown[j] == "`":
            j += 1
        close = re.compile(r"(?<!`)`{%d}(?!`)" % (j - i)).search(markdown, j)
        if close is None:
            text += markdown[i:j]
            i = j
            continue
        content = markdown[j:close.start()]
        if content.startswith(" ") and content.endswith(" ") and content.strip():
            content = content[1:-1]
        out += [("text", text), ("code", content)]
        text, i = "", close.end()
    return [seg for seg in out + [("text", text)] if seg != ("text", "")]


def _carried(markdown, before, after):
    """The name the Markdown carries between `before` and `after`, asserting
    it is carried in code spans only (with nothing between two spans but the
    slash of ":material/")."""
    segs = _segments(markdown)
    assert segs[0] == ("text", before) or (before == "" and segs[0][0] == "code"), segs
    assert segs[-1][0] == "text" and segs[-1][1].startswith(after), segs
    middle = segs[1:-1] if before else segs[:-1]
    assert middle and all(kind == "code" or text == "/" for kind, text in middle), segs
    return "".join(text for _, text in middle)


def test_a_typed_name_is_printed_as_typed_in_the_strip_and_every_save_sentence(scratch):
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, HOSTILE)
    saved = [v for v in _sidebar_texts(at) if v.startswith("Saved ")]
    assert saved == [f"Saved `{HOSTILE}`."], saved
    assert _carried(saved[0], "Saved ", ".") == HOSTILE
    assert _carried(_entered(at), "", " · 1240-05-23 14:30:00 · ") == HOSTILE, _entered(at)
    _save_as(at, HOSTILE)
    assert f"`{HOSTILE}` is already saved as it is." in _sidebar_texts(at), _sidebar_texts(at)
    at.session_state["time_input_key"] = time(9, 0)
    at.run()
    assert _entered(at).startswith(f"`{HOSTILE}` (modified) · "), _entered(at)
    _save_as(at, HOSTILE)
    assert f"`{HOSTILE}` exists. Replace it?" in _sidebar_texts(at), _sidebar_texts(at)
    [b for b in at.sidebar.button if b.label == "\U0001F5D1"][0].click().run()
    assert_no_exception(at, "delete asked")
    assert f"Delete `{HOSTILE}`?" in _sidebar_texts(at), _sidebar_texts(at)


@pytest.mark.parametrize("name, shown", [
    (HOSTILE, f"`{HOSTILE}`"),
    ("Plain Name (2)", "'Plain Name (2)'"),
])
def test_the_saved_under_other_readings_question_prints_the_name_as_typed(scratch, name, shown):
    at = make_app(date="1240-05-23", page="chart")
    at.session_state["_connection_rule"] = "Abu Ma'shar"
    at.run()
    _save_as(at, name)
    at.session_state["_connection_rule"] = "Sahl"
    at.run()
    _picker(at).select("-- New Chart --").run()
    _picker(at).select(name).run()
    assert_no_exception(at)
    said = [v for v in _sidebar_texts(at) if "was saved under other readings" in v]
    assert said == [f"{shown} was saved under other readings."], said


# What Streamlit does to parsed text after the escapes are resolved: a code
# span is the element it leaves alone. Each is carried in code spans only, on
# the strip and in the Saved sentence.
@pytest.mark.parametrize("name", [
    ":streamlit:",                          # the logo
    ":material/home: x",                    # an icon
    "a -- b -> c",                          # a dash and an arrow
    "a -- b",                               # a dash alone (no other character marks it)
    "www.example.com",                      # a link
    "someone@example.com",                  # a mail link
    "see https://example.org now",          # a link: an escaped colon did not stop it
    ":smile: :+1:",                         # emoji (on the strip, whose times load the plugin)
])
def test_what_streamlit_rewrites_after_parsing_is_printed_in_code_spans(scratch, name):
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, name)
    saved = [v for v in _sidebar_texts(at) if v.startswith("Saved ")]
    assert len(saved) == 1 and _carried(saved[0], "Saved ", ".") == name, saved
    assert _carried(_entered(at), "", " · 1240-05-23 14:30:00 · ") == name, _entered(at)
    # Streamlit turns ":material/" into ":material_" in the whole Markdown
    # before it parses it, code spans included.
    assert ":material/" not in saved[0] and ":material/" not in _entered(at), (saved, _entered(at))


# R4 of the lane's re-check: a name that can turn text right to left is set
# between FIRST STRONG ISOLATE (U+2068) and POP DIRECTIONAL ISOLATE (U+2069),
# so the app's own text after it reads in its own direction. Firefox drew the
# strip's date, time and coordinates backwards after "abc", U+202E, "def".
FSI, PDI = "\u2068", "\u2069"


@pytest.mark.parametrize("name, shown", [
    ("abc\u202edef", f"{FSI}abc\u202edef{PDI}"),                       # a right-to-left override
    ("\u0645\u062d\u0645\u062f", f"{FSI}\u0645\u062d\u0645\u062f{PDI}"),   # a name written right to left
    ("a\u200fb", f"{FSI}a\u200fb{PDI}"),                               # a right-to-left mark
    ("a\u2069\u202eb", f"{FSI}a\u202eb{PDI}"),                         # a closing isolate with none open: dropped
    ("a\u2067b", f"{FSI}a\u2067b{PDI}{PDI}"),                           # an isolate left open: closed first
])
def test_a_name_that_can_turn_text_right_to_left_is_isolated(scratch, name, shown):
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, name)
    assert f"Saved '{shown}'." in _sidebar_texts(at), [ascii(v) for v in _sidebar_texts(at)]
    assert _entered(at).startswith(f"{shown} · 1240-05-23 14:30:00 · "), ascii(_entered(at))


def test_an_isolated_name_in_a_code_span_and_the_readings_question(scratch):
    name, plain = "*x* \u202e y", "abc\u202edef"
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, name)
    assert f"Saved `{FSI}{name}{PDI}`." in _sidebar_texts(at), [ascii(v) for v in _sidebar_texts(at)]
    assert _entered(at).startswith(f"`{FSI}{name}{PDI}` · 1240-05-23 14:30:00 · "), ascii(_entered(at))
    at.session_state["_connection_rule"] = "Abu Ma'shar"
    at.run()
    _save_as(at, plain)
    at.session_state["_connection_rule"] = "Sahl"
    at.run()
    _picker(at).select("-- New Chart --").run()
    _picker(at).select(plain).run()
    said = [v for v in _sidebar_texts(at) if "was saved under other readings" in v]
    assert said == [f"'{FSI}{plain}{PDI}' was saved under other readings."], [ascii(v) for v in said]


def test_a_name_with_no_right_to_left_text_is_not_isolated(scratch):
    name = "Abū Ma'shar \u200e(2)"                                        # a left-to-right mark moves nothing
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, name)
    assert f"Saved '{name}'." in _sidebar_texts(at), [ascii(v) for v in _sidebar_texts(at)]
    assert FSI not in _entered(at) and PDI not in _entered(at), ascii(_entered(at))


@pytest.mark.parametrize("name, shown", [
    ("# Heading *x*", "`# Heading *x*`"),
    ("> quoted", "`> quoted`"),
    ("- listed", "`- listed`"),
    ("1. numbered", "`1. numbered`"),
    ("a_b ~~c~~ `d` <i>e</i> &amp; f\\g |h", "``a_b ~~c~~ `d` <i>e</i> &amp; f\\g |h``"),
    ("`d`", "`` `d` ``"),
])
def test_a_name_opening_a_block_or_holding_markup_opens_nothing_on_the_strip(scratch, name, shown):
    _store().write_text(json.dumps({name: FLORENCE_REC}))
    at = make_app(date="1240-05-23", page="chart").run()
    _picker(at).select(name).run()
    assert_no_exception(at, name)
    assert _entered(at).startswith(f"{shown} · 1983-11-19 10:30:00 · "), _entered(at)
    assert _carried(_entered(at), "", " · 1983-11-19") == name


def test_a_plain_name_is_printed_as_it_is_and_quoted_in_a_sentence(scratch):
    name = "Abū Ma'shar, Jean-Paul [draft] (2)"
    at = make_app(date="1240-05-23", page="chart").run()
    _save_as(at, name)
    assert f"Saved '{name}'." in _sidebar_texts(at), _sidebar_texts(at)
    assert _entered(at).startswith(f"{name} · 1240-05-23 14:30:00 · "), _entered(at)
    assert _segments(_entered(at))[0][0] == "text", _segments(_entered(at))


def test_a_hand_edited_name_and_place_label_stay_on_one_line(scratch):
    name = "N|a\nme <i>x</i>"
    record = {**FLORENCE_REC, "location_query": "Pe|tos<b>key</b>\n## injected"}
    _store().write_text(json.dumps({name: record}))
    at = make_app(date="1240-05-23", page="chart").run()
    _picker(at).select(name).run()
    assert_no_exception(at)
    strip = _strip(at)
    assert strip.count("\n") == 1, strip
    assert _entered(at) == ("`N|a me <i>x</i>` · 1983-11-19 10:30:00 · LMT +00:44:59 · "
                            "`Pe|tos<b>key</b> ## injected` 43.78, 11.25"), _entered(at)
    place = [s.value for s in at.sidebar.success if s.value.startswith("**")][0]
    assert place.startswith("**`Pe|tos<b>key</b> ## injected`**  \n"), place


def test_the_sentences_of_a_refused_or_flagged_record_print_its_name_as_typed(scratch):
    no_time = {k: v for k, v in FLORENCE_REC.items() if k != "time_string"}
    off_range = {**FLORENCE_REC, "time_standard": MANUAL, "utc_offset": 99}
    no_standard = {k: v for k, v in FLORENCE_REC.items() if k != "time_standard"}
    bad_time = {**FLORENCE_REC, "time_string": 1030}
    _store().write_text(json.dumps({"*a*": no_time, "_b_": off_range, "$c$": no_standard, "`d`": bad_time}))
    at = make_app(date="1240-05-23", page="chart").run()
    _picker(at).select("*a*").run()
    assert "`*a*` could not be loaded: it holds no time." in _sidebar_texts(at), _sidebar_texts(at)
    _picker(at).select("_b_").run()
    assert ("`_b_` was saved with a UTC offset of 99, outside ±14; check the time standard."
            in _sidebar_texts(at)), _sidebar_texts(at)
    _picker(at).select("$c$").run()
    assert any(v.startswith("`$c$` was saved before the time standard was stored")
               for v in _sidebar_texts(at)), _sidebar_texts(at)
    _picker(at).select("`d`").run()
    assert any(v.startswith("`` `d` `` could not be loaded: its time") for v in _sidebar_texts(at)), (
        _sidebar_texts(at))


def test_a_record_another_window_replaced_is_named_as_typed(scratch):
    _store().write_text(json.dumps({HOSTILE: FLORENCE_REC}))
    a = make_app(page="chart").run()
    _picker(a).select(HOSTILE).run()
    b = make_app(page="chart").run()
    _picker(b).select(HOSTILE).run()
    b.session_state["time_input_key"] = time(9, 0)
    b.run()
    _save_as(b, HOSTILE)
    b.sidebar.button(key="_replace_now").click().run()
    assert json.loads(_store().read_text())[HOSTILE]["time_string"] == "09:00:00", "the premise"
    _save_as(a, HOSTILE)                    # A's copy, unchanged, as L6R-N7's own pin
    said = [v for v in _sidebar_texts(a) if "by another window" in v]
    assert said and said[0].startswith(f"`{HOSTILE}` was replaced by another window"), said


def test_the_home_place_label_is_printed_as_typed(scratch):
    at = make_app(page="chart")
    at.session_state["home_place"] = {"label": "Pe*tos*key $x$", "lat": 45.3733, "lon": -84.9553}
    at.run()
    assert_no_exception(at)
    homes = [c.value for c in at.sidebar.caption if c.value.startswith("Home: ")]
    assert homes == ["Home: `Pe*tos*key $x$` · 45.3733, -84.9553"], homes
