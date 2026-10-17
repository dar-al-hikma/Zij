"""The program's source modules are named once, in source_modules.txt.

Everything that reads the program's source as a whole -- the frozen build's data files,
the suite's source scans, the maintainer tools -- reads the modules the list names, so a
module split out of engine.py is bundled, scanned and checked without another edit. These
tests pin the list's rules, the list itself, the suite's helpers and the build: each runs
on the repository and on a constructed tree with a module split out, and each shows that a
reader written against the pair would miss the new module.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import conftest
from conftest import EXECUTABLE_DIR, engine_files, engine_source, function_source, source_files, source_list
# build.spec executed with PyInstaller stood in for, and the walk over the modules the listed
# ones import: shared with the scan of what the frozen app carries.
from shipped_modules import program_modules, spec_datas


# --- the list's rules ---------------------------------------------------------------------

def test_the_list_is_read_in_order_with_comments_and_blank_lines():
    text = "# the program\nengine.py   # the engine\n\nwheel.py\napp.py\n"
    assert source_list.parse(text) == ["engine.py", "wheel.py", "app.py"]


@pytest.mark.parametrize("text,message", [
    ("# nothing\n\n", "names no file"),
    ("engine.py\napp.py\nengine.py\n", "engine.py twice"),
    ("engine.py\nsub/wheel.py\napp.py\n", "is not a file name in the tree"),
    ("engine.py\n..\napp.py\n", "is not a file name in the tree"),
])
def test_a_bad_list_is_an_error(text, message):
    with pytest.raises(ValueError, match=message):
        source_list.parse(text)


def test_a_tree_with_no_list_is_the_pair(tmp_path):
    for name in ("engine.py", "app.py"):
        (tmp_path / name).write_text("x = 1\n")
    assert source_list.names(tmp_path) == ["engine.py", "app.py"]
    assert [p.name for p in source_list.files(tmp_path)] == ["engine.py", "app.py"]


def test_a_listed_file_that_is_not_there_is_an_error_not_a_skip(tmp_path):
    for name in ("engine.py", "app.py"):
        (tmp_path / name).write_text("x = 1\n")
    (tmp_path / source_list.LIST_NAME).write_text("engine.py\nwheel.py\napp.py\n")
    with pytest.raises(FileNotFoundError, match="wheel.py"):
        source_list.files(tmp_path)


def test_the_repositorys_list_names_every_module_once_and_app_py_last():
    names = source_list.names(EXECUTABLE_DIR)
    assert (EXECUTABLE_DIR / source_list.LIST_NAME).is_file(), "the list is committed, not implied"
    assert names[-1] == "app.py" and "engine.py" in names, names
    assert [n for n in names if not (EXECUTABLE_DIR / n).is_file()] == [], names
    assert [p.name for p in source_files()] == names


# --- a constructed tree: a module split out of engine.py ----------------------------------

ENGINE = '''"""A tiny engine."""
from glyph_font import font_face_css


def stays():
    return 1
'''
WHEEL = '''"""The wheel, split out of the engine."""


def draw_wheel():
    """Draws the wheel."""
    return "<svg/>"
'''
APP = '''"""A tiny app."""
from engine import *
# 4. STREAMLIT UI INTEGRATION
'''


def split_tree(root: Path, listed: str = "engine.py\nwheel.py\napp.py\n") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in (("engine.py", ENGINE), ("wheel.py", WHEEL), ("app.py", APP),
                       ("glyph_font.py", "def font_face_css():\n    return ''\n")):
        (root / name).write_text(text, encoding="utf-8")
    if listed is not None:
        (root / source_list.LIST_NAME).write_text(listed, encoding="utf-8")
    return root


def test_the_suites_helpers_read_every_listed_module(tmp_path, monkeypatch):
    """source_files(), engine_source() and function_source() follow the list: a scan of the
    pair would not read the wheel."""
    tree = split_tree(tmp_path / "tree")
    monkeypatch.setattr(conftest, "EXECUTABLE_DIR", tree)
    assert [p.name for p in source_files()] == ["engine.py", "wheel.py", "app.py"]
    assert [p.name for p in engine_files()] == ["engine.py", "wheel.py"]
    assert "def draw_wheel(" in engine_source() and "def stays(" in engine_source()
    assert "from engine import" not in engine_source()
    assert function_source("draw_wheel").startswith("def draw_wheel():")
    with pytest.raises(LookupError):
        function_source("not_anywhere")


def test_the_helpers_read_the_pair_when_the_tree_has_no_list(tmp_path, monkeypatch):
    tree = split_tree(tmp_path / "tree", listed=None)
    monkeypatch.setattr(conftest, "EXECUTABLE_DIR", tree)
    assert [p.name for p in source_files()] == ["engine.py", "app.py"]


# --- the frozen build -----------------------------------------------------------------------

def missing_from_datas(root: Path) -> list[str]:
    bundled = {src for src, dest, *_ in spec_datas(root) if dest == "."}
    return [name for name in program_modules(root) if name not in bundled]


def test_the_build_bundles_every_listed_module_and_what_they_import():
    assert program_modules(EXECUTABLE_DIR)[:2] == source_list.names(EXECUTABLE_DIR)[:2]
    assert "glyph_font.py" in program_modules(EXECUTABLE_DIR), "premise: the engine's own import is followed"
    assert missing_from_datas(EXECUTABLE_DIR) == []


# --- every module of the program is listed ------------------------------------------------

# The modules of the repository that the listed modules import (at any depth) and that are not
# program source: the list leaves them out, so the chain, the citation ratchet and the page-text
# guard never read them -- and each is held to carrying nothing those would find, by a private
# test beside the citation ratchet's.
NOT_PROGRAM_SOURCE = {
    "glyph_font.py": "the wheel's symbol font, embedded as data: no citation and no page text",
}


def unlisted_program_modules(root: Path) -> list[str]:
    """Every module of the repository the listed modules import, transitively, that is
    neither listed nor in NOT_PROGRAM_SOURCE."""
    listed = set(source_list.names(root))
    return [m for m in program_modules(root) if m not in listed and m not in NOT_PROGRAM_SOURCE]


def test_every_module_the_listed_modules_import_is_listed():
    """A module split out of engine.py and imported by it, but left out of source_modules.txt
    (and bundled by hand, as glyph_font.py is), would be read by no guard: the chain, the
    citation ratchet and the page-text guard read the list. Every module of the repository
    a listed module imports, however deep, is listed or named in NOT_PROGRAM_SOURCE."""
    assert unlisted_program_modules(EXECUTABLE_DIR) == [], (
        "a module of the program is imported but not in source_modules.txt: list it, so that "
        "every guard reads it (or, if it holds no program source, name it in NOT_PROGRAM_SOURCE "
        "with a reason)")


UNLISTED = '"""Moved out of the engine."""\nSPLIT_AT = "Gr. Intr. VII.4, 77"\n'


@pytest.mark.parametrize("engine_import", [
    "from ephemeris import *\n",                                           # the check's construction
    "\n\ndef later():\n    import ephemeris\n    return ephemeris\n",      # only inside a function
    "\n\ndef later():\n    return importlib.import_module('ephemeris')\n",
])
def test_an_imported_module_that_is_not_listed_is_caught(tmp_path, engine_import):
    """The check's construction: engine.py imports ephemeris.py, the build bundles it by hand,
    the list leaves it out. The build test passes (it is bundled); this one does not."""
    tree = built_tree(tmp_path)
    with open(tree / "engine.py", "a", encoding="utf-8") as f:
        f.write(engine_import)
    (tree / "ephemeris.py").write_text(UNLISTED, encoding="utf-8")
    spec = (tree / "build.spec").read_text(encoding="utf-8")
    by_hand = 'datas += [("glyph_font.py", "."),'
    assert spec.count(by_hand) == 1, "premise: glyph_font.py is bundled by hand"
    (tree / "build.spec").write_text(spec.replace(by_hand, 'datas += [("ephemeris.py", "."), ("glyph_font.py", "."),'),
                                     encoding="utf-8")
    assert missing_from_datas(tree) == [], "premise: bundled, so the build test passes"
    assert unlisted_program_modules(tree) == ["ephemeris.py"]
    (tree / source_list.LIST_NAME).write_text("engine.py\nwheel.py\nephemeris.py\napp.py\n", encoding="utf-8")
    assert unlisted_program_modules(tree) == []


def test_a_module_imported_only_by_an_unlisted_module_is_caught(tmp_path):
    """Transitively: glyph_font.py (not program source, not listed) importing a module of the
    program is no way round the list."""
    tree = split_tree(tmp_path / "tree")
    (tree / "glyph_font.py").write_text("from ephemeris import X\n\n\ndef font_face_css():\n    return ''\n",
                                        encoding="utf-8")
    (tree / "ephemeris.py").write_text(UNLISTED + "X = 1\n", encoding="utf-8")
    assert unlisted_program_modules(tree) == ["ephemeris.py"]


def test_a_module_imported_two_modules_deep_is_caught(tmp_path):
    tree = split_tree(tmp_path / "tree")
    with open(tree / "wheel.py", "a", encoding="utf-8") as f:
        f.write("from helpers import h\n")
    (tree / "helpers.py").write_text("import ephemeris\n\n\ndef h():\n    return ephemeris\n", encoding="utf-8")
    (tree / "ephemeris.py").write_text(UNLISTED, encoding="utf-8")
    assert unlisted_program_modules(tree) == ["helpers.py", "ephemeris.py"]


def test_the_standard_library_and_installed_packages_are_not_the_repositorys(tmp_path):
    """`import json`, `import swisseph` resolve outside the repository's folder; a module or a
    package folder the repository holds resolves inside it, even under a standard name."""
    tree = split_tree(tmp_path / "tree")
    with open(tree / "engine.py", "a", encoding="utf-8") as f:
        f.write("import json, swisseph\nimport secrets\nfrom pkg.part import main\n")
    assert unlisted_program_modules(tree) == []
    (tree / "secrets.py").write_text("X = 1\n", encoding="utf-8")
    (tree / "pkg").mkdir()
    (tree / "pkg" / "part.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    assert unlisted_program_modules(tree) == ["secrets.py", "pkg/"]


def built_tree(tmp_path: Path, spec_text: str | None = None) -> Path:
    tree = split_tree(tmp_path / "tree")
    (tree / "build.spec").write_text(spec_text or (EXECUTABLE_DIR / "build.spec").read_text(encoding="utf-8"),
                                     encoding="utf-8")
    return tree


def test_the_build_bundles_a_split_out_module_without_an_edit(tmp_path):
    tree = built_tree(tmp_path)
    assert {"engine.py", "wheel.py", "app.py", "glyph_font.py"} <= {src for src, *_ in spec_datas(tree)}
    assert missing_from_datas(tree) == []


def test_the_build_reads_the_list_by_the_suites_rules(tmp_path):
    """build.spec reads the list on its own (the build imports nothing from tests/): comments,
    blank lines and order as tests/source_list.py reads them; a bad list stops the build."""
    tree = built_tree(tmp_path)
    (tree / source_list.LIST_NAME).write_text("# the program\n\nwheel.py  # split out\nengine.py\napp.py\n")
    assert [src for src, dest, *_ in spec_datas(tree) if src.endswith(".py")][:3] == source_list.names(tree)
    (tree / source_list.LIST_NAME).unlink()
    assert [src for src, dest, *_ in spec_datas(tree) if src.endswith(".py")][:2] == list(source_list.PAIR)
    for bad in ("engine.py\napp.py\nengine.py\n", "# nothing\n", "engine.py\nsub/wheel.py\napp.py\n"):
        (tree / source_list.LIST_NAME).write_text(bad)
        with pytest.raises(SystemExit, match="source_modules.txt names"):
            spec_datas(tree)


def test_a_build_that_names_the_pair_misses_the_split_out_module(tmp_path):
    """The guard bites: the data files written by name, as they were, leave the wheel out of
    the frozen app, and the whole suite would have passed."""
    spec = (EXECUTABLE_DIR / "build.spec").read_text(encoding="utf-8")
    listed = 'datas += [(name, ".") for name in SOURCE_MODULES]\n'
    assert spec.count(listed) == 1, "premise: the spec takes the modules from the list"
    tree = built_tree(tmp_path, spec.replace(listed, 'datas += [("app.py", "."), ("engine.py", ".")]\n'))
    assert missing_from_datas(tree) == ["wheel.py"]


# --- the page-text guard reads a split-out module by itself --------------------------------

def _prose_counts_on(tree: Path, monkeypatch):
    """tests/test_prose_counts.py imported afresh with the suite's helpers reading `tree`, so
    its per-module parametrization is the tree's list."""
    import importlib.util
    monkeypatch.setattr(conftest, "EXECUTABLE_DIR", tree)
    spec = importlib.util.spec_from_file_location("prose_counts_on_a_split_tree",
                                                  EXECUTABLE_DIR / "tests" / "test_prose_counts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_build_process_string_in_a_split_out_module_fails_the_page_text_guard(tmp_path, monkeypatch):
    """The export may move out of engine.py; the guard over it must move with it. On a tree
    with wheel.py listed, the guard has a case for wheel.py, and a date written into a string
    there fails it -- a guard that still read engine.py alone would pass."""
    tree = split_tree(tmp_path / "tree")
    prose = _prose_counts_on(tree, monkeypatch)
    guard = prose.test_engine_strings_carry_no_build_process
    cases = [m.args[1] for m in getattr(guard, "pytestmark", []) if m.name == "parametrize"]
    assert cases == [["engine.py", "wheel.py"]], cases
    guard("wheel.py")                                                     # clean as written
    with open(tree / "wheel.py", "a", encoding="utf-8") as f:
        f.write('\nCAPTION = "Drawn as the owner ruled on 2026-10-13."\n')
    with pytest.raises(AssertionError):
        guard("wheel.py")
    with pytest.raises(AssertionError):
        prose.test_page_strings_carry_no_build_process()
