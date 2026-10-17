"""The atlas opened read-only and closed (SC-07), the missing-atlas sentence
(B-18, KNOWN 15; ruling 146 (7)), the place data's credits on the Sources
and readings page (PK-01, PK-02; rulings 98 and 172) and the repository's
attributes for the data files (PK-03). ATLAS1's rebuild.
"""
import ast
import contextlib
import re
import shutil
import sqlite3
from pathlib import Path

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, ui_source

ROOT = APP_PATH.parent
ATLAS = ROOT / "atlas.db"


@pytest.fixture(scope="module")
def tz():
    import time_zones
    return time_zones


# --- Read-only and closed --------------------------------------------------------

def test_a_write_through_the_lookup_s_connection_raises(tz, tmp_path, monkeypatch):
    """The connection the lookup opens cannot write: a copy of the atlas is
    searched and a write tried on the same connection; the copy is
    untouched."""
    copy = tmp_path / "atlas.db"
    shutil.copyfile(ATLAS, copy)
    before = ATLAS.read_bytes()
    real, tried = sqlite3.connect, []

    def connect(*args, **kwargs):
        conn = real(*args, **kwargs)
        try:
            conn.execute("CREATE TABLE planted (x)")
            conn.commit()
            tried.append("written")
        except sqlite3.OperationalError as error:
            tried.append(str(error))
        return conn
    monkeypatch.setattr(tz.sqlite3, "connect", connect)
    assert tz.atlas_rows(copy, "London")
    assert tried == ["attempt to write a readonly database"]
    assert copy.read_bytes() == before


def test_the_lookup_opens_a_file_uri_in_read_only_mode_with_trusted_schema_off(tz, tmp_path, monkeypatch):
    real, seen = sqlite3.connect, []

    def connect(*args, **kwargs):
        conn = real(*args, **kwargs)
        seen.append((args, kwargs, conn))
        return conn
    monkeypatch.setattr(tz.sqlite3, "connect", connect)
    assert tz.atlas_rows(ATLAS, "Florence")
    (args, kwargs, conn), = seen
    assert kwargs == {"uri": True} and args[0] == ATLAS.resolve().as_uri() + "?mode=ro"
    with pytest.raises(sqlite3.ProgrammingError):            # closed on the way out
        conn.execute("SELECT 1")


def test_trusted_schema_is_off_on_the_lookup_s_connection(tz, monkeypatch):
    real, states = sqlite3.connect, []

    class _Connection(sqlite3.Connection):
        def cursor(self, *args, **kwargs):
            states.append(self.execute("PRAGMA trusted_schema").fetchone()[0])
            return super().cursor(*args, **kwargs)

    monkeypatch.setattr(tz.sqlite3, "connect", lambda *a, **k: real(*a, factory=_Connection, **k))
    assert tz.atlas_rows(ATLAS, "Florence")
    assert states == [0]


def test_the_lookup_reads_an_atlas_in_a_folder_named_with_awkward_characters(tz, tmp_path):
    """A frozen app may sit in such a folder: a space, "#", "%", "?" and
    letters outside ASCII each survive the URI."""
    folder = tmp_path / "Zīj app #1 100% ready? Größe"
    folder.mkdir()
    shutil.copyfile(ATLAS, folder / "atlas.db")
    rows = tz.atlas_rows(folder / "atlas.db", "Hekou")
    assert (22.53851, 104.01109) in [(lat, lon) for _n, _a, _c, lat, lon in rows]
    # each character on its own too
    for mark in (" ", "#", "%", "?", "é"):
        one = tmp_path / f"a{mark}b"
        one.mkdir()
        shutil.copyfile(ATLAS, one / "atlas.db")
        assert tz.atlas_rows(one / "atlas.db", "Hekou"), mark


def test_the_atlas_is_not_opened_with_immutable(tz):
    """immutable=1 is not used: it is not shown safe on all three platforms
    (it tells SQLite the file can never change, so it takes no lock and
    trusts no change it sees)."""
    assert "immutable" not in (ROOT / "time_zones.py").read_text(encoding="utf-8")


# --- The missing-atlas sentence -------------------------------------------------

MISSING = ("The offline place atlas is missing, so no city can be looked up. "
           "Enter the place's latitude and longitude instead.")


def _sentence(name):
    tree = ast.parse(ui_source())
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == [name])
    return ast.literal_eval(node.value)


def test_the_missing_atlas_sentence_names_the_thing_not_its_file():
    text = _sentence("ATLAS_MISSING_MESSAGE")
    assert text == MISSING
    for word in ("atlas.db", ".db", "folder", "directory", "root", "Please", "`"):
        assert word not in text, word


def test_a_missing_atlas_says_so_and_the_coordinates_still_cast(tmp_path):
    """The app's own lookup beside no atlas (its source lifted, its file
    beside an empty folder) answers with the sentence."""
    import time_zones
    source = ui_source()
    space = {"Path": Path, "__file__": str(tmp_path / "app.py"), "atlas_rows": time_zones.atlas_rows,
             "degrees_text": lambda v, p: f"{v:.{p}f}"}
    for node in ast.parse(source).body:
        if (isinstance(node, ast.FunctionDef) and node.name == "_atlas_matches") or (
                isinstance(node, ast.Assign) and any(getattr(t, "id", "").startswith("ATLAS_") for t in node.targets)):
            exec(ast.get_source_segment(source, node), space)
    assert space["_atlas_matches"]("London") == (None, MISSING)


# --- The credits -------------------------------------------------------------------

# Ruling 201 (2): the credit names the place names too.
GEONAMES = ("Place names, coordinates, and country and region names: [GeoNames](https://www.geonames.org/), "
            "licensed under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). Zīj "
            "selects and reformats the data for its offline atlas. GeoNames provides the data as is, with no "
            "warranty of accuracy, timeliness or completeness.")
OPENSTREETMAP = ("The outlines of the areas whose historical clocks are read by a birthplace's coordinates: © "
                 "OpenStreetMap contributors ([copyright and attribution](https://www.openstreetmap.org/copyright)), "
                 "under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Zīj has "
                 "edited them; they are published whole, as a data file of their own with its licence notice, with "
                 "the app and its source.")


def test_the_sources_page_carries_both_credits():
    at = make_app(page="sources").run()
    assert_no_exception(at, "the Sources page")
    texts = [m.value for m in at.main.markdown]
    assert GEONAMES in texts and OPENSTREETMAP in texts
    assert "Place data" in [h.value for h in at.main.subheader]


def test_the_credits_carry_no_date_no_file_and_no_omission_clause():
    for text in (_sentence("GEONAMES_CREDIT"), _sentence("OPENSTREETMAP_CREDIT")):
        assert not re.search(r"[0-9]", text.replace("4.0", "").replace("1.0", "").replace("1-0", ""))
        for word in (".json", ".tsv", ".db", "data/", "unnamed regions", "omitted"):
            assert word not in text, word
    assert _sentence("GEONAMES_CREDIT") == GEONAMES and _sentence("OPENSTREETMAP_CREDIT") == OPENSTREETMAP


# --- The attributes ------------------------------------------------------------------

def test_the_data_files_attributes_keep_them_byte_for_byte():
    lines = [line.strip() for line in (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    assert lines == ["data/mean_time_outlines.json -text", "data/place_zones.tsv -text", "atlas.db binary",
                     "ephe/sefstars.txt -text"]
