"""The frozen build leaves out the package parts the program never runs
(build.spec's UNUSED_MODULES): pandas' own test suite, Streamlit's demo pages,
timezonefinder's command line and the builder of its C extension, and Qt's
SQL module (tests/test_build_pins.py holds its drivers).

Read from build.spec's text, and its two filters run (they are plain
functions) over the installed packages' files laid out as collect_all hands
them to the build, (source, destination folder): exactly those parts go, and
streamlit.hello and its streamlit_app, which Streamlit's server imports at
every start, stay. Only a release build shows the bundle itself.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path

import pytest

from conftest import EXECUTABLE_DIR

SPEC = EXECUTABLE_DIR / "build.spec"
EXPECTED = ["pandas.tests", "streamlit.hello.hello", "streamlit.hello.animation_demo",
            "streamlit.hello.dataframe_demo", "streamlit.hello.mapping_demo", "streamlit.hello.plotting_demo",
            "streamlit.hello.utils", "timezonefinder.command_line", "timezonefinder.__main__",
            "timezonefinder.build", "PySide6.QtSql"]


@pytest.fixture(scope="module")
def spec():
    """build.spec's tree, and its UNUSED_MODULES, _unused and _module_of run
    in a namespace of their own."""
    source = SPEC.read_text(encoding="utf-8")
    tree = ast.parse(source)
    space = {"os": os}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and [ast.unparse(t) for t in node.targets] == ["UNUSED_MODULES"]) or (
                isinstance(node, ast.FunctionDef) and node.name in ("_unused", "_module_of")):
            exec(ast.get_source_segment(source, node), space)
    return tree, space


def test_the_parts_left_out_are_these(spec):
    _tree, space = spec
    assert space["UNUSED_MODULES"] == EXPECTED


def test_they_are_dropped_from_the_modules_the_files_and_analysis(spec):
    tree, _space = spec
    lines = [ast.unparse(n) for n in tree.body]
    assert "hiddenimports = [name for name in hiddenimports if not _unused(name)]" in lines
    assert "datas = [entry for entry in datas if not _unused(_module_of(entry))]" in lines
    collect = next(i for i, n in enumerate(tree.body) if isinstance(n, ast.For) and "collect_all" in ast.unparse(n))
    assert lines.index("datas = [entry for entry in datas if not _unused(_module_of(entry))]") > collect
    analysis = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == "Analysis")
    excludes = next(k.value for k in analysis.keywords if k.arg == "excludes")
    assert "*UNUSED_MODULES" in ast.unparse(excludes)


SPECS = {"pandas": importlib.util.find_spec("pandas"), "streamlit": importlib.util.find_spec("streamlit"),
         "timezonefinder": importlib.util.find_spec("timezonefinder")}


def _collected(package):
    """The package's files as collect_all lays them out: (source, destination folder)."""
    root = Path(SPECS[package].submodule_search_locations[0])
    out = []
    for folder, subs, names in os.walk(root):
        subs[:] = [s for s in subs if s != "__pycache__"]
        for name in names:
            out.append((os.path.join(folder, name), os.path.relpath(folder, root.parent)))
    return out


@pytest.mark.parametrize("package", ["pandas", "streamlit", "timezonefinder"])
def test_over_the_installed_files_exactly_those_parts_go(spec, package):
    _tree, space = spec
    files = _collected(package)
    gone = [entry for entry in files if space["_unused"](space["_module_of"](entry))]
    kept = [entry for entry in files if entry not in gone]
    names = {space["_module_of"](entry) for entry in gone}
    if package == "pandas":
        under_tests = lambda dest: (dest.replace(os.sep, "/") + "/").startswith("pandas/tests/")
        assert gone and all(under_tests(dest) for _src, dest in gone)
        assert not [src for src, dest in kept if under_tests(dest)]
    elif package == "streamlit":
        assert names == {f"streamlit.hello.{n}" for n in
                         ("hello", "animation_demo", "dataframe_demo", "mapping_demo", "plotting_demo", "utils")}
        assert {space["_module_of"](e) for e in kept} >= {"streamlit.hello.__init__", "streamlit.hello.streamlit_app"}
    else:
        assert names == {"timezonefinder.command_line", "timezonefinder.__main__", "timezonefinder.build"}
    for name in ("streamlit.hello", "streamlit.hello.streamlit_app", "streamlit", "pandas", "timezonefinder",
                 "timezonefinder.timezonefinder", "pandas.testing", "pandas.util._tester"):
        assert space["_unused"](name) is False, name


def test_the_program_imports_none_of_them():
    imported = set()
    for path in sorted(EXECUTABLE_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert not [m for m in imported if any(m == u or m.startswith(u + ".") for u in EXPECTED)]
