# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The HTML report a reader opens: one file, nothing beside it, built from the
same rows and through the same cell printer as the Markdown report, which is
built in app.py with the JSON. The engine takes this module whole. It imports
the standard library, markup.py, and house_style.py and saved_faces.py for its
stylesheet and faces; what it reads of the engine's (a longitude's words, the
class of a longitude, the zone's note) it reaches through _the_engine when it
is called, never at import.
"""
import json

import house_style
import saved_faces
from markup import _esc_text, _isolated


def _the_engine():
    """The engine, reached when called and never at import (the engine
    imports this module): what this module reads of the engine's is looked up
    there at each call, so that the object the engine holds under the name
    then is the one used."""
    import engine
    return engine


def _export_cell(value):
    """One cell's text, shared by every export format so a reader of the
    Markdown, the HTML and the JSON is reading the same words (the format
    applies its own escaping on top). A report for a reader, not a Python
    dump: nothing prints as None, a
    flag prints as a word, a bare number to four places -- the JSON keeps
    the full value."""
    # PN4Together: two or more partners met together (PN IV III.1, 50).
    if (isinstance(value, dict)
            and value.get('result_type') in {'UnresolvedResult', 'YearsOutcome', 'PN4Together'}):
        return str(value['display'])
    if isinstance(value, (list, tuple)):
        return "; ".join(_export_cell(v) for v in value)
    if isinstance(value, dict) and {'n', 'facts'} <= value.keys() and ('sentence' in value or 'label' in value):
        # A testimony as the engine records it: {'n', 'sentence', 'facts'}
        # (and 'result' where the sentence's answer is typed).
        # Facts left open by an undecided connection follow the settled ones.
        # The sentence prints through this printer too: one left open by an
        # undecided connection arrives as the JSON's typed result and prints
        # by its display, as the result beside it does, not as a dict.
        parts = [_export_cell(value.get('sentence', value.get('label'))),
                 _export_cell(list(value['facts']) + list(value.get('Unresolved facts', ())))
                 if isinstance(value['facts'], (list, tuple)) else _export_cell(value['facts'])]
        if value.get('result') is not None:
            parts.append(_export_cell(value['result']))
        return ": ".join(part for part in parts if part)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, _the_engine().CircleLongitude) and value == value:
        return _the_engine().degrees_text(value, 4, zodiac=True).rstrip("0").rstrip(".")
    if isinstance(value, float):
        if value != value:
            return "nan"
        # A value that rounds to zero prints 0, not "-0": no
        # unrounded value stands beside a bare cell to give the sign a
        # meaning ("-0.00" is kept only where one does, in _fact).
        text = f"{value:.4f}"
        if float(text) == 0.0:
            text = "0"
        return text.rstrip("0").rstrip(".") if "." in text else text
    return str(value)


ANALYSIS_HTML_STYLE = house_style.EXPORT_STYLE


def _html_table(rows, typed=()):
    """A list of dicts as an HTML table, in the rows' own key order and with
    the cells the other formats print (_export_cell). A row whose first cell
    is one of `typed` (the header's "Place") holds a name as it was typed:
    its "Value" is isolated (_isolated), as the Markdown export's is."""
    if not rows:
        return "<p class='none'>No rows.</p>"
    columns = list(dict.fromkeys(k for row in rows for k in row))

    def cell(value, as_typed=False):
        text = _export_cell(value)
        return _esc_text(_isolated(text) if as_typed else text).replace("\n", "<br>")

    def as_typed(row):
        return bool(typed) and next(iter(row.values()), None) in typed
    head = "".join(f"<th>{cell(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{cell(row.get(c, ''), as_typed(row) and c == 'Value')}</td>"
                                    for c in columns) + "</tr>"
                   for row in rows)
    return f"<div class='wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


# The header blocks of the two reports a person reads, in words. The JSON
# keeps its keys -- they are the file's schema, what a program reads -- and
# the Markdown and the HTML label each row with the words the pages use for
# the same thing (not the JSON's keys). A key missing here prints as
# its own words, never as an identifier.
EXPORT_FIELD_WORDS = {
    "app": {
        "ephemeris": "Ephemeris",
    },
    "entered": {
        "date_string": "Date",
        "time_string": "Time",
        "time_standard": "Time standard",
        "utc_offset": "UTC offset (hours, east positive)",
        "location_query": "Place",
        "lat": "Latitude",
        "lon": "Longitude",
        "target_mode": "Target by",
        "target_date": "Target date",
        "target_age": "Target age (completed years)",
    },
    "input": {
        "date": "Date",
        "time": "Local time",
        "time_standard": "Time standard",
        "utc_offset_hours": "UTC offset (hours, east positive)",
        "timezone": "Time zone",
        "civil_clock": "Civil clock then",
        "place": "Place",
        "latitude": "Latitude",
        "longitude": "Longitude",
        "julian_day_ut": "Julian Day (UT)",
        "calendar": "Calendar of the date",
        "ut_calendar": "Calendar of the universal time",
    },
    "display": {
        "chart_bounds": "Bounds ring",
        "wheel_layout": "Wheel layout",
    },
    "target": {
        "mode": "Target by",
        "date": "Target date",
        "age": "Age (completed years)",
        "hour": "Hour the target day is read at",
    },
    "status": {
        "chart_ok": "Chart cast",
        "chart_error": "Why no chart was cast",
        "modified": "Modified since it was saved",
        "edited_since_saved": "Edited since it was saved",
        "saved_with_other_readings": "Saved with other readings",
        "equal_hour_approximation": "Equal hours stand in for the temporal hours",
        "day_lord": "Lord of the Day",
        "pole": "At the pole",
        "forward_search_days": "Forward search (days)",
        "stale": "Tables from the last valid chart (the date box does not parse)",
        "target_out_of_reach": "Target out of reach",
    },
}


# The label of the one row the reports' block of the moment and place
# carries beyond the JSON's (export_header_tables).
EXPORT_ZONE_CAUTION_LABEL = "Time zone note"


def _export_words(key):
    """A key nobody gave words to, as words: underscores to spaces, the
    first letter capitalised ("Counts on the Releaser page")."""
    text = str(key).replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def export_header_tables(analysis):
    """The tables both reports print above the results, as (title,
    rows), from one list so that the Markdown and the HTML cannot part:
    what computed this, what was entered, the moment and place the chart
    was cast at, the readings in force, the display preferences, the target
    and the status. Every row is labelled in words (EXPORT_FIELD_WORDS).
    The block of the moment and place carries one row the JSON does not,
    read from that block's own values: the sentence a Standard-time cast
    before 1970 carries where its zone's record is another place's
    (export_zone_caution), after the zone's row."""
    def fields(block, column, skip=()):
        words = EXPORT_FIELD_WORDS.get(block, {})
        return [{column: words.get(k) or _export_words(k), "Value": v}
                for k, v in analysis[block].items() if k not in skip]
    cast_at = fields("input", "Field")
    caution = _the_engine().export_zone_caution(analysis["input"])
    if caution:
        zone_row = next((i for i, row in enumerate(cast_at) if row["Field"] == EXPORT_FIELD_WORDS["input"]["timezone"]),
                        len(cast_at) - 1)
        cast_at.insert(zone_row + 1, {"Field": EXPORT_ZONE_CAUTION_LABEL, "Value": caution})
    # A block an export does not carry is not printed: the Fixed stars export
    # holds no readings, display preferences or target.
    tables = [
        ("What computed this", fields("app", "Item")),
        ("What was entered", fields("entered", "Field", skip=("readings", "saved_with"))),
        ("The moment and place the chart was cast at", cast_at),
        ("The readings in force",
         [{"Reading": r["label"], "In force": r["value"], "Default": r["default"], "Set on": r["set_on"]}
          for r in analysis["readings"]]),
        ("Display preferences", fields("display", "Preference")),
        ("The target", fields("target", "Field")),
        ("Status", fields("status", "Field")),
    ]
    return [(title, rows) for title, rows in tables if rows]


def analysis_html(analysis):
    """The same analysis as one file a reader can open.

    Windows and macOS associate .html with a browser and neither renders
    Markdown or JSON for someone who has not chosen a tool for them, so
    this is the format a reader is actually able to read: one file, no
    second file to keep beside it, nothing fetched, and a browser's Print
    to hand for a PDF. It carries exactly what the Markdown carries, from
    the same rows and through the same _export_cell, and nothing the JSON
    does not but the zone's row export_header_tables reads from the JSON's
    own block. There is no script in it: the content is tables.

    It takes the in-memory export analysis_export builds, not one decoded
    back from its JSON: the JSON writes the Positions longitudes as plain
    floats, and a plain float loses the sign-end boundary formatting.
    """
    esc = _esc_text       # & < > in text, as every picture wheel.py draws escapes
    # No version after "this app": the provenance block is dropped
    # (version, libraries, checksum) from what a reader opens.
    # The name isolated, as the page and the Markdown export set it:
    # a RIGHT-TO-LEFT OVERRIDE in it ends with the name.
    name = _isolated(str(analysis['chart']))
    out = [f"<h1>Analysis: {esc(name)}</h1>",
           f"<p class='sub'>Exported {esc(str(analysis['exported']))} by this app.</p>",
           f"<p class='scope'>{esc(analysis['scope'])}</p>"]
    for title, rows in export_header_tables(analysis):
        out.append(f"<h2>{esc(title)}</h2>")
        out.append(_html_table(rows, typed=("Place",)))
    out.append("<h2>Results</h2>")
    # One collapsed section a page, so the reader meets a contents list
    # rather than a hundred tables at once; print opens them all again.
    for page, headings in analysis["results"].items():
        count = sum(len(entries) for entries in headings.values())
        out.append(f"<details><summary>{esc(str(page))} "
                   f"&mdash; {count} table{'s' if count != 1 else ''}</summary>")
        for heading, entries in headings.items():
            out.append(f"<h3>{esc(str(heading))}</h3>")
            for entry in entries:
                # The line the page prints over this table (a tied planet's
                # name, the releaser's verdict), then what it cites.
                if entry.get("label") is not None:
                    out.append(f"<p class='label'>{esc(_export_cell(entry['label']))}</p>")
                if entry.get("citation"):
                    out.append(f"<p class='cite'>{esc(str(entry['citation']))}</p>")
                out.append(_html_table(entry["rows"]))
        out.append("</details>")
    out.append(f"<footer>{esc(analysis['precision'])}</footer>")
    return ("<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>Analysis: {esc(name)}</title>"
            f"<style>{_the_engine().font_face_css()}{saved_faces.font_face_css()}{ANALYSIS_HTML_STYLE}</style></head><body><main>"
            + "".join(out) + "</main></body></html>\n")


__all__ = ['house_style', 'saved_faces', 'json', '_esc_text', '_isolated', '_export_cell', 'ANALYSIS_HTML_STYLE', '_html_table',
           'EXPORT_FIELD_WORDS', 'EXPORT_ZONE_CAUTION_LABEL', '_export_words', 'export_header_tables',
           'analysis_html']
