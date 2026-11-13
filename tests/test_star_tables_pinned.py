# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The star lists and the sky's source ids, each read once, checked against the SHA-256 its program
records, and parsed from the bytes checked. A changed table costs what a changed pin beside it costs:
the lists go with the catalogue, the ids with the sky's page, and never the app."""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from conftest import make_app, sync_engine_to_environment  # noqa: E402

import server_limits  # noqa: E402
import sky  # noqa: E402

LISTS = ROOT / "data" / "fixed_star_lists.tsv"
IDS = ROOT / "data" / "sky_source_ids.tsv"
JD = 2460002.25
DAMAGES = ("byte", "line", "gone")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _damaged(raw, damage):
    """The bytes of a table so damaged, or None for a table removed. Each still parses."""
    if damage == "gone":
        return None
    if damage == "line":
        return raw + b"invented\tline\n"
    changed = bytearray(raw)
    changed[-2] ^= 1
    return bytes(changed)


def _plant(path, raw, damage):
    data = _damaged(raw, damage)
    if data is not None:
        path.write_bytes(data)
    return path


class _ReadOnce:
    """A table that gives other bytes on any later read, and has no way to read but this one."""

    def __init__(self, name, first, later):
        self.name, self.reads, self._first, self._later = name, 0, first, later

    def read_bytes(self):
        self.reads += 1
        return self._first if self.reads == 1 else self._later


def _attach_afresh(engine):
    engine._FIXED_STAR_STATE["checked"] = False
    engine._fixed_star_places_at.cache_clear()
    engine._fixed_star_finder_read.cache_clear()
    engine._fixed_star_catalogue_read.cache_clear()
    engine.fixed_star_list_file.cache_clear()


@pytest.fixture
def engine():
    import engine as module
    sync_engine_to_environment()
    module = sys.modules["engine"]
    module.fixed_star_list_file.cache_clear()
    yield module
    module.fixed_star_list_file.cache_clear()


@pytest.fixture
def lists_refused(engine, tmp_path, monkeypatch):
    """The engine with a changed star list, attaching for the first time; put right after."""
    monkeypatch.setattr(engine, "FIXED_STAR_LISTS_FILE", _plant(tmp_path / "lists.tsv", LISTS.read_bytes(), "byte"))
    _attach_afresh(engine)
    yield engine
    monkeypatch.undo()
    _attach_afresh(engine)
    assert engine.fixed_star_places(JD)[0] is not None


# --- The star lists ------------------------------------------------------------------------------

@pytest.mark.parametrize("damage", DAMAGES)
def test_a_changed_star_list_is_refused_by_its_reader(engine, tmp_path, monkeypatch, damage):
    monkeypatch.setattr(engine, "FIXED_STAR_LISTS_FILE", _plant(tmp_path / "lists.tsv", LISTS.read_bytes(), damage))
    with pytest.raises(OSError if damage == "gone" else ValueError):
        engine.fixed_star_list_file()


def test_a_changed_recorded_hash_refuses_the_true_star_list(engine, monkeypatch):
    monkeypatch.setattr(engine, "FIXED_STAR_LISTS_SHA256", "0" * 64)
    with pytest.raises(ValueError):
        engine.fixed_star_list_file()


def test_the_star_list_is_read_once_and_parsed_from_what_was_checked(engine, monkeypatch):
    raw = LISTS.read_bytes()
    shipped = engine.fixed_star_list_file()
    engine.fixed_star_list_file.cache_clear()
    table = _ReadOnce(LISTS.name, raw, _damaged(raw, "byte"))
    monkeypatch.setattr(engine, "FIXED_STAR_LISTS_FILE", table)
    assert engine.fixed_star_list_file() == shipped and table.reads == 1


def test_a_changed_star_list_gets_the_catalogues_refusal(lists_refused):
    engine = lists_refused
    assert engine.fixed_star_places(JD) == (None, {})
    assert "star lists" in engine._FIXED_STAR_STATE["why"]
    assert engine.fixed_star_finder() is None
    eyesight = engine.evaluate_eyesight_stars(JD)
    assert eyesight["refused"] == engine.fixed_star_refusal() and eyesight["rows"]


@pytest.mark.parametrize("page", ["fixed-stars", "sky"])
def test_a_changed_star_list_costs_the_pages_and_not_the_app(lists_refused, page):
    at = make_app(page=page).run()
    assert not at.exception, at.exception
    assert "The star catalogue is unavailable; no entries could be placed." in [element.value for element in at.main.info]


# --- The sky's source ids ------------------------------------------------------------------------

@pytest.mark.parametrize("damage", DAMAGES)
def test_changed_source_ids_are_refused_by_their_reader(tmp_path, monkeypatch, damage):
    monkeypatch.setattr(sky, "SOURCE_IDS_FILE", _plant(tmp_path / IDS.name, IDS.read_bytes(), damage))
    with pytest.raises(OSError if damage == "gone" else ValueError):
        sky._load()


def test_a_changed_recorded_hash_refuses_the_true_source_ids(monkeypatch):
    assert sky._load()[4] == sky.SOURCE_IDS
    monkeypatch.setitem(sky.PINS, IDS.name, "0" * 64)
    with pytest.raises(ValueError):
        sky._load()


def test_the_source_ids_are_read_once_and_parsed_from_what_was_checked(monkeypatch):
    raw = IDS.read_bytes()
    table = _ReadOnce(IDS.name, raw, _damaged(raw, "byte"))
    monkeypatch.setattr(sky, "SOURCE_IDS_FILE", table)
    assert sky._load()[4] == sky.SOURCE_IDS and table.reads == 1


@pytest.mark.parametrize("damage", (None, *DAMAGES))
def test_changed_source_ids_cost_the_page_and_not_the_import(tmp_path, damage):
    """The module itself, from a copy of what it reads, with no name of it patched."""
    for name in ("sky.py", "sky_words.json", "sky_host.js", "sky_host.css"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    shutil.copytree(ROOT / "vendor", tmp_path / "vendor")
    (tmp_path / "data").mkdir()
    if damage is None:
        shutil.copyfile(IDS, tmp_path / "data" / IDS.name)
    else:
        _plant(tmp_path / "data" / IDS.name, IDS.read_bytes(), damage)
    spec = importlib.util.spec_from_file_location("sky_copy", tmp_path / "sky.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.AVAILABLE is (damage is None)
    assert module.SOURCE_IDS == (sky.SOURCE_IDS if damage is None else {})


# --- The checklist ---------------------------------------------------------------------------------

def test_the_release_checklist_says_so():
    text = " ".join((ROOT / "docs" / "RELEASING.md").read_text(encoding="utf-8").split())
    assert (f"The font route, `{server_limits.FONT_ROUTE.rstrip('/')}/`, stands ahead of the secret and behind the "
            "single-`Host` check, and answers only the shipped font files by name.") in text
    assert "the star catalogue and its added rows, the star lists, the sky's source ids," in text
