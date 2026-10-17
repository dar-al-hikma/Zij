"""Lane P1 of the re-pass: what a reader opens carries no build process.

The owner's rulings 27-30 (2026-10-05, third word), with block F of the page
text read after Step 4:

27  the exports' provenance block (version, libraries, SHA) is dropped from
    what a reader opens -- the JSON, the Markdown and the HTML;
28  the JSON's ``store_key`` is dropped (the key is internal);
29  the two "TNAC Reference Guide" mentions are removed;
30  a refusal's appended reason names "the fixed-star file", not the file's
    name.

One test a ruling, over every export it applies to (28 is the JSON's alone;
29's mentions are on the Dignities page, which the exports are also read
for; 30's refusal is the Timing page's, which no export carries). Written
red against the tree before the lane and turned green by it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from conftest import assert_no_exception, make_app, sync_engine_to_environment

_RENDERS: dict = {}


def _render(page):
    """One render per page for the whole module."""
    if page not in _RENDERS:
        at = make_app(page=page).run(timeout=180)
        assert_no_exception(at, page)
        _RENDERS[page] = at
    return _RENDERS[page]


def _exports(page="chart"):
    at = _render(page)
    export = at.session_state["_analysis_export"]
    return export, at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]


def _texts(node, out=None):
    """Every string a reader can see under ``node``: bodies, values, labels,
    help strings and every dataframe cell."""
    out = [] if out is None else out
    for attr in ("value", "label", "help", "body", "caption", "placeholder"):
        try:
            v = getattr(node, attr)
        except Exception:
            continue
        if isinstance(v, str) and v:
            out.append(v)
    proto = getattr(node, "proto", None)
    if proto is not None:
        for attr in ("help", "body", "label"):
            v = getattr(proto, attr, None)
            if isinstance(v, str) and v:
                out.append(v)
    if type(node).__name__ == "Dataframe":
        df = node.value
        out.extend(str(c) for c in df.columns)
        for row in df.itertuples(index=False):
            out.extend(str(cell) for cell in row if cell is not None)
    for child in (getattr(node, "children", None) or {}).values():
        _texts(child, out)
    return out


# --- 27: the provenance block --------------------------------------------------

# The rows block F lists, by the words the reports label them with.
_PROVENANCE_ROWS = ("This app's version", "Streamlit", "Python", "pyswisseph",
                    "Checksum of the calculation code (SHA-256)")


def test_ruling_27_no_export_carries_the_version_the_libraries_or_the_checksum(engine):
    export, md, page_html = _exports()
    version = engine["APP_VERSION"]
    import engine as engine_module
    sha = hashlib.sha256(Path(engine_module.__file__).read_bytes()).hexdigest()
    # The JSON: the block keeps the ephemeris the positions are computed
    # from (the ruling names version, libraries and SHA; block F's second
    # option keeps "Ephemeris: Moshier (built in)") and nothing else.
    assert export["app"] == {"ephemeris": "Moshier (built in)"}, export["app"]
    assert sha not in json.dumps(export)
    # The Markdown and the HTML: no version in the header line, no library
    # row, no checksum; the ephemeris row stands.
    for text in (md, page_html):
        assert version not in text and sha not in text
    assert re.search(r"^Exported \S+ by this app\.$", md, flags=re.M), md[:300]
    assert re.search(r"<p class='sub'>Exported \S+ by this app\.</p>", page_html), page_html[:300]
    for label in _PROVENANCE_ROWS:
        assert f"| {label} |" not in md, label
        assert f"<td>{label}</td>" not in page_html, label
    assert "| Ephemeris | Moshier (built in) |" in md
    assert "<td>Ephemeris</td><td>Moshier (built in)</td>" in page_html


# --- 28: store_key ---------------------------------------------------------------

def test_ruling_28_the_json_readings_carry_no_store_key():
    export, md, page_html = _exports()
    readings = export["readings"]
    assert len(readings) == 9, "the nine readings in force are exported"
    for row in readings:
        assert set(row) == {"label", "value", "default", "set_on"}, row
    assert '"store_key"' not in json.dumps(export)
    assert "store_key" not in md and "store_key" not in page_html


# --- 29: the two Reference Guide mentions ------------------------------------------

def test_ruling_29_no_reference_guide_on_the_dignities_page_or_in_its_exports():
    at = _render("dignities")
    page = _texts(at.main)
    export, md, page_html = _exports("dignities")
    for where, texts in (("page", page), ("json", [json.dumps(export, ensure_ascii=False)]),
                         ("markdown", [md]), ("html", [page_html])):
        hits = [t for t in texts if "Reference Guide" in t or re.search(r"\bthe Guide\b", t)]
        assert not hits, (where, [h[:200] for h in hits])
    # The two notes the mentions stood in are still there.
    joined = "\n".join(page)
    assert "Which sources each column represents" in joined
    assert "The twelve passages, and the arrangement" in joined


# --- 30: the refusal's appended reason ---------------------------------------------

@pytest.fixture
def engine_in_step(engine):
    """The engine re-imported for this test's environment before the test
    swaps its star catalogue. make_app() reloads the engine whenever the
    environment has moved since the last reload (sync_engine_to_environment),
    and an earlier test in the same worker that pointed XDG_DATA_HOME at its
    own tmp_path and rendered a page leaves it moved. A reload in the middle
    of one of these tests, at its Timing page's render, put back the shipped
    catalogue's source and SHA-256 and a fresh _FIXED_STAR_STATE: the page
    read the shipped file and showed no warning (the CI flake of P1-7 and
    P1-8, the Timing page's warnings []). Reloaded here, before the swap,
    the render's own sync finds nothing to do. Under the tests only: a
    served app never reloads the engine."""
    sync_engine_to_environment()
    return engine


def _refusal_says_the_fixed_star_file(sentence):
    assert "sefstars" not in sentence, sentence
    assert "the fixed-star file" in sentence, sentence


@pytest.mark.usefixtures("engine_in_step")
def test_ruling_30_every_refusal_reason_names_the_fixed_star_file(engine, monkeypatch, tmp_path):
    import swisseph as swe
    import engine as engine_module
    state = engine["_FIXED_STAR_STATE"]
    bundled = str(Path(engine["__file__"]).parent / "ephe" / "sefstars.txt")
    real_isfile = os.path.isfile
    try:
        # 1. no catalogue anywhere: the Timing page's warning and the engine's sentence
        monkeypatch.setattr(os.path, "isfile", lambda p: False if str(p).endswith("sefstars.txt") else real_isfile(p))
        state.update(checked=False, ready=False, where=None, why=None)
        assert engine["_fixed_star_catalogue_ready"]() is False
        _refusal_says_the_fixed_star_file(engine["fixed_star_refusal"]())
        state.update(checked=False, ready=False, where=None, why=None)
        at = make_app(page="timing").run(timeout=180)
        assert_no_exception(at, "timing without a star catalogue")
        (warning,) = [w.value for w in at.main.warning if w.value.startswith("Not computed: no Swiss Ephemeris")]
        _refusal_says_the_fixed_star_file(warning)
        monkeypatch.undo()

        # 2. the bundled catalogue the only one visible, and unreadable
        def boom(*a, **k):
            raise OSError("SwissEph file 'sefstars.txt' not found (simulated)")
        monkeypatch.setattr(swe, "fixstar2_ut", boom)
        monkeypatch.setattr(os.path, "isfile",
                            lambda p: (str(p) == bundled) if str(p).endswith("sefstars.txt") else real_isfile(p))
        state.update(checked=False, ready=False, where=None, why=None)
        assert engine["_fixed_star_catalogue_ready"]() is False
        _refusal_says_the_fixed_star_file(engine["fixed_star_refusal"]())
        monkeypatch.undo()

        # 3. a catalogue found elsewhere that cannot be linked into the user data directory
        # A copy of its own in a folder of its own, offered through $SE_EPHE_PATH,
        # so the case does not rest on some installed package shipping one.
        (tmp_path / "sefstars.txt").write_bytes(Path(bundled).read_bytes())
        monkeypatch.setenv("SE_EPHE_PATH", str(tmp_path))
        monkeypatch.setattr(os.path, "isfile",
                            lambda p: (str(p) != bundled) if str(p).endswith("sefstars.txt") else real_isfile(p))

        def no_folder():
            raise PermissionError(13, "Permission denied (simulated)")
        monkeypatch.setattr(engine_module, "_user_data_dir", no_folder)
        state.update(checked=False, ready=False, where=None, why=None)
        assert engine["_fixed_star_catalogue_ready"]() is False
        sentence = engine["fixed_star_refusal"]()
        _refusal_says_the_fixed_star_file(sentence)
        # the reason the search records, off the page since ruling 58 (c), in the same words
        _refusal_says_the_fixed_star_file(state["why"])
    finally:
        monkeypatch.undo()
        state.update(checked=False, ready=False, where=None, why=None)
    assert engine["_fixed_star_catalogue_ready"]() is True


# --- ruling 58: what rulings 27-30 left at their edges ------------------------------

def test_ruling_58b_the_entered_block_has_no_app_version_and_reads_by_label(engine):
    export, _md, _html = _exports()
    entered = export["entered"]
    # the block stays: what was entered, with the record's schema
    assert entered["date_string"] == "1240-05-23" and entered["saved_with"]["schema"] == 2
    # without the app version (ruling 27)
    assert "app" not in entered["saved_with"], entered["saved_with"]
    assert engine["APP_VERSION"] not in json.dumps(export)
    # its readings keyed by the labels the pages show (ruling 28), the same
    # labels and values as the readings-in-force rows
    in_force = {row["label"]: row["value"] for row in export["readings"]}
    assert len(in_force) == 9
    assert entered["readings"] == in_force, (sorted(entered["readings"]), sorted(in_force))


_SEARCH_WORDS = ("$SE_EPHE_PATH", "site-packages", "user data directory", "bundled", "found ", "simulated",
                 "Error(", "Errno", "ephe")


@pytest.mark.usefixtures("engine_in_step")
def test_ruling_58c_a_fixed_star_refusal_says_only_that_the_file_could_not_be_read(engine, monkeypatch, tmp_path):
    import swisseph as swe
    import engine as engine_module
    state = engine["_FIXED_STAR_STATE"]
    bundled = str(Path(engine["__file__"]).parent / "ephe" / "sefstars.txt")
    real_isfile = os.path.isfile
    sentences = []

    def refusal():
        state.update(checked=False, ready=False, where=None, why=None)
        assert engine["_fixed_star_catalogue_ready"]() is False
        return engine["fixed_star_refusal"]()
    try:
        # 1. none found -- and the Timing page's warning
        monkeypatch.setattr(os.path, "isfile", lambda p: False if str(p).endswith("sefstars.txt") else real_isfile(p))
        sentences.append(refusal())
        state.update(checked=False, ready=False, where=None, why=None)
        at = make_app(page="timing").run(timeout=180)
        assert_no_exception(at, "timing without a star catalogue")
        (warning,) = [w.value for w in at.main.warning if w.value.startswith("Not computed: no Swiss Ephemeris")]
        sentences.append(warning.removeprefix("Not computed: ").removesuffix("."))
        monkeypatch.undo()
        # 2. the bundled file the only one visible, and unreadable
        monkeypatch.setattr(swe, "fixstar2_ut", lambda *a, **k: (_ for _ in ()).throw(OSError("unreadable (simulated)")))
        monkeypatch.setattr(os.path, "isfile",
                            lambda p: (str(p) == bundled) if str(p).endswith("sefstars.txt") else real_isfile(p))
        sentences.append(refusal())
        # the search still records what it tried, off the page: the Windows shape
        # (the bundled file the only one, unreadable) is not denied by the fall-through
        assert "could not read it from" in state["why"], state["why"]
        assert "is not in the bundled folder" not in state["why"], state["why"]
        monkeypatch.undo()
        # 3. found elsewhere and not linkable
        # A copy of its own in a folder of its own, offered through $SE_EPHE_PATH,
        # so the case does not rest on some installed package shipping one.
        (tmp_path / "sefstars.txt").write_bytes(Path(bundled).read_bytes())
        monkeypatch.setenv("SE_EPHE_PATH", str(tmp_path))
        monkeypatch.setattr(os.path, "isfile",
                            lambda p: (str(p) != bundled) if str(p).endswith("sefstars.txt") else real_isfile(p))

        def no_folder():
            raise PermissionError(13, "Permission denied (simulated)")
        monkeypatch.setattr(engine_module, "_user_data_dir", no_folder)
        sentences.append(refusal())
    finally:
        monkeypatch.undo()
        state.update(checked=False, ready=False, where=None, why=None)
    assert len(sentences) == 4
    for sentence in sentences:
        assert "the fixed-star file could not be read" in sentence, sentence
        assert "/" not in sentence and "\\" not in sentence, sentence
        leaks = [w for w in _SEARCH_WORDS if w in sentence]
        assert not leaks, (leaks, sentence)
    assert len(set(sentences)) == 1, sentences                  # one sentence, whatever failed
    assert engine["_fixed_star_catalogue_ready"]() is True


# --- after the blind check: a real catalogue that cannot be read (P1-7, P1-8) -----------

REFUSAL = "no Swiss Ephemeris star catalogue is attached; nothing is computed -- the fixed-star file could not be read"


def _forget_star_records(engine):
    """swe_close() where the catalogue is read: the library's star records and
    path are per thread, and every read runs on the engine's one reader
    thread (_on_fixed_star_reader; owner's ruling 62), so a close in the
    test's own thread would leave the reader's records in place."""
    import swisseph as swe
    engine["_on_fixed_star_reader"](swe.close)


def _with_catalogue(engine, monkeypatch, folder):
    """Offer `folder`'s catalogue in the shipped one's place, with its own
    SHA-256 recorded (ruling 103: no other catalogue is looked for, so the
    shipped file is the one place a catalogue comes from); the search
    starts afresh."""
    import engine as engine_module
    offered = Path(folder) / "sefstars.txt"
    try:
        digest = hashlib.sha256(offered.read_bytes()).hexdigest()
    except PermissionError:                         # unreadable: refused before its hash is asked
        digest = engine_module.FIXED_STAR_CATALOGUE_SHA256
    monkeypatch.setattr(engine_module, "_fixed_star_catalogue_source", lambda: offered)
    monkeypatch.setattr(engine_module, "FIXED_STAR_CATALOGUE_SHA256", digest)
    # Swiss Ephemeris keeps the star records it has read in memory until
    # swe_close(), whatever path is set after; a reader's own process starts
    # without them, so this one is made to as well.
    _forget_star_records(engine)
    engine["_FIXED_STAR_STATE"].update(checked=False, ready=False, where=None, why=None, missing={})


def _timing_star_text(engine):
    engine["_FIXED_STAR_STATE"].update(checked=False, ready=False, where=None, why=None, missing={})
    at = make_app(page="timing").run(timeout=180)
    assert_no_exception(at, "timing with the reader's catalogue")
    warnings = [w.value for w in at.main.warning]
    star_tables = [d for d in at.main.dataframe if "Star" in d.value.columns]
    return warnings, star_tables


def _restore(engine, monkeypatch):
    monkeypatch.undo()
    _forget_star_records(engine)      # forget the reader's catalogue; the bundled one is read afresh
    engine["_FIXED_STAR_STATE"].update(checked=False, ready=False, where=None, why=None, missing={})
    assert engine["_fixed_star_catalogue_ready"]() is True


def _refused_everywhere(engine):
    assert engine["_fixed_star_catalogue_ready"]() is False
    assert engine["fixed_star_refusal"]() == REFUSAL
    out = engine["pn4_fixed_stars_in_image"]({"planetary_data": {}, "ascendant": 0.0, "mc": 270.0}, 2451545.0)
    assert out["rows"] == [] and out["refused"] == REFUSAL, out
    warnings, star_tables = _timing_star_text(engine)
    assert f"Not computed: {REFUSAL}." in warnings, warnings
    assert not [w for w in warnings if w.startswith("Not in the catalogue attached")], warnings
    assert not star_tables


@pytest.mark.usefixtures("engine_in_step")
def test_p1_7_an_unreadable_catalogue_is_refused_with_the_one_sentence(engine, monkeypatch, tmp_path):
    locked = tmp_path / "sefstars.txt"
    locked.write_bytes((Path(engine["__file__"]).parent / "ephe" / "sefstars.txt").read_bytes())
    locked.chmod(0)
    try:
        with pytest.raises(PermissionError):           # the premise: this process cannot read it
            locked.read_bytes()
        assert engine["_fixed_star_catalogue_ready"]() is True
        _with_catalogue(engine, monkeypatch, tmp_path)
        _refused_everywhere(engine)
    finally:
        locked.chmod(0o600)
        _restore(engine, monkeypatch)


@pytest.mark.usefixtures("engine_in_step")
def test_p1_7_an_empty_catalogue_is_refused_with_the_one_sentence(engine, monkeypatch, tmp_path):
    (tmp_path / "sefstars.txt").write_bytes(b"")
    try:
        _with_catalogue(engine, monkeypatch, tmp_path)
        _refused_everywhere(engine)
    finally:
        _restore(engine, monkeypatch)


@pytest.mark.usefixtures("engine_in_step")
def test_p1_8_a_star_missing_from_the_catalogue_is_named_without_its_exception(engine, monkeypatch, tmp_path):
    lines = (Path(engine["__file__"]).parent / "ephe" / "sefstars.txt").read_text(encoding="latin-1").splitlines(True)
    kept = [line for line in lines if not re.match(r"Regulus\s*,", line)]
    assert len(lines) - len(kept) >= 1
    (tmp_path / "sefstars.txt").write_text("".join(kept), encoding="latin-1")
    note = "Not in the catalogue attached, so not placed: Regulus."
    try:
        _with_catalogue(engine, monkeypatch, tmp_path)
        assert engine["_fixed_star_catalogue_ready"]() is True
        stars = engine["fixed_star_longitudes"](2451545.0)
        assert "Regulus" not in stars and len(stars) == 27
        assert engine["fixed_star_missing_note"]() == note
        assert "Regulus" in engine["_FIXED_STAR_STATE"]["missing"]       # the exception, kept off the page
        warnings, star_tables = _timing_star_text(engine)
        assert note in warnings, warnings
        assert not [w for w in warnings if "swe" in w or "Error" in w], warnings
    finally:
        _restore(engine, monkeypatch)
