# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""What keeps a file the program pins, and the Windows and macOS builds, as they were read.

Every file whose SHA-256 stands in a program module is safe from a checkout's line-end
conversion, found by what the modules hold, not from a list of names. The build reads the
sky's scripts against their pins before anything is built, and the archive's listing for
the wheel module after. Qt's database drivers stay out of the Windows build. Only a build
shows that bundle itself; here the spec's own filters run over what the wheels hold."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "build.spec"
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
_DIGEST = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
_NO_REPO = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")


def _git(root, *args, stdin=None):
    env = {key: value for key, value in os.environ.items() if key not in _NO_REPO}
    return subprocess.run(["git", *args], cwd=root, env=env, input=stdin, capture_output=True, text=True,
                          check=True).stdout


def _tracked(root):
    return [name for name in _git(root, "ls-files", "-z").split("\0") if name]


def _digests(raw):
    """The file's digest as tracked, and as a converted checkout would have to fold it back."""
    return {hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}


def pins(root):
    """Each tracked file whose SHA-256 stands in a Python module at the tree's top, and those modules."""
    tracked = _tracked(root)
    held = {}
    for name in tracked:
        if "/" not in name and name.endswith(".py"):
            for digest in _DIGEST.findall((Path(root) / name).read_text(encoding="utf-8")):
                held.setdefault(digest.lower(), set()).add(name)
    found = {}
    for name in tracked:
        path = Path(root) / name
        if path.is_file() and not path.is_symlink():
            for digest in _digests(path.read_bytes()):
                if digest in held:
                    found.setdefault(name, set()).update(held[digest])
    return found


def convertible(root, names):
    """Those of `names` a converting checkout could still change: not `-text` in the attributes."""
    if not names:
        return []
    lines = _git(root, "check-attr", "text", "--stdin", stdin="\n".join(names) + "\n").splitlines()
    return sorted(line.rsplit(": text: ", 1)[0] for line in lines if not line.endswith(": text: unset"))


def test_every_file_a_program_module_pins_is_safe_from_line_end_conversion():
    found = pins(ROOT)
    assert not convertible(ROOT, sorted(found)), "give each its own line in .gitattributes, `-text`"


def test_the_search_finds_the_pins_each_module_holds():
    """A search gone blind passes the test above, so what it finds is held to the modules' own tables."""
    import sky
    found = pins(ROOT)
    holders = {module for modules in found.values() for module in modules}
    assert {"engine.py", "sky.py", "time_zones.py"} <= holders
    by_digest = {hashlib.sha256((ROOT / name).read_bytes()).hexdigest(): name for name in found}
    assert set(sky.PINS.values()) <= set(by_digest), "each of the sky's pins, found by its digest"


@pytest.fixture
def tree(tmp_path):
    """A repository of one module, which pins pinned.bin and pins nothing of other.bin."""
    _git(tmp_path, "init", "-q")
    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "pinned.bin").write_bytes(b"pinned\n")
    (tmp_path / "other.bin").write_bytes(b"other\n")
    digest = hashlib.sha256(b"pinned\n").hexdigest()
    (tmp_path / "program.py").write_text(f'PIN = "{digest}"\n', encoding="utf-8")
    return tmp_path


def _add(tree):
    _git(tree, "add", "-A")


def test_a_plant_pin_with_no_line_is_found(tree):
    _add(tree)
    assert set(pins(tree)) == {"folder/pinned.bin"}
    assert convertible(tree, sorted(pins(tree))) == ["folder/pinned.bin"]


def test_a_plant_pin_in_upper_case_is_found(tree):
    text = (tree / "program.py").read_text(encoding="utf-8")
    (tree / "program.py").write_text(text.upper(), encoding="utf-8")
    _add(tree)
    assert set(pins(tree)) == {"folder/pinned.bin"}


def test_a_plant_pin_in_a_converted_checkout_is_found(tree):
    (tree / "folder" / "pinned.bin").write_bytes(b"pinned\r\n")
    _add(tree)
    assert set(pins(tree)) == {"folder/pinned.bin"}


@pytest.mark.parametrize("line", ["folder/pinned.bin -text", "folder/*.bin -text"])
def test_a_plant_pin_with_its_line_passes(tree, line):
    (tree / ".gitattributes").write_text(line + "\n", encoding="utf-8")
    _add(tree)
    assert convertible(tree, sorted(pins(tree))) == []


@pytest.mark.parametrize("line", ["folder/pinned.bin text", "folder/pinned.bin text=auto", "other.bin -text"])
def test_a_plant_line_that_does_not_stop_conversion_fails(tree, line):
    (tree / ".gitattributes").write_text(line + "\n", encoding="utf-8")
    _add(tree)
    assert convertible(tree, sorted(pins(tree))) == ["folder/pinned.bin"]


def _steps():
    """build.yml's steps of the build job in order: each one's own lines, comments dropped."""
    build = WORKFLOW.read_text(encoding="utf-8").split("\n  release:\n", 1)[0]
    build = build.split("\n    steps:\n", 1)[1]
    kept = "\n".join(line for line in build.splitlines() if not line.lstrip().startswith("#"))
    return [part for part in re.split(r"(?m)^      - ", kept) if part.strip()]


def _step_index(words):
    held = [i for i, step in enumerate(_steps()) if words in step]
    assert len(held) == 1, words
    return held[0]


def test_the_sky_s_pins_are_read_on_each_leg_before_the_build():
    node = "tests/test_sky_page.py::test_each_vendored_file_is_the_pinned_one"
    at = _step_index(node)
    assert at < _step_index("run: pyinstaller build.spec")
    assert _step_index("uses: actions/checkout") < at
    step = _steps()[at]
    assert f"run: python -m pytest -q -p no:cacheprovider {node}" in step
    assert "if:" not in step and "continue-on-error" not in step
    source = (ROOT / "tests" / "test_sky_page.py").read_text(encoding="utf-8")
    assert "def test_each_vendored_file_is_the_pinned_one(" in source


def test_the_archive_s_listing_is_read_on_each_leg_after_the_build():
    at = _step_index("archive_check.py")
    assert _step_index("run: pyinstaller build.spec") < at
    assert at < _step_index("run: python .github/scripts/stop_check.py")
    step = _steps()[at]
    assert "if:" not in step and "continue-on-error" not in step
    assert "shell: bash" in step and "set -eu" in step
    for program in ("dist/Zij/Zij.exe", "dist/Zij.app/Contents/MacOS/Zij"):
        assert program in step
    assert 'pyi-archive_viewer --list --recursive "$program" > "$RUNNER_TEMP/archive-listing.txt"' in step
    assert 'python .github/scripts/archive_check.py "$RUNNER_TEMP/archive-listing.txt"' in step


@pytest.fixture(scope="module")
def check():
    spec = importlib.util.spec_from_file_location("archive_check", ROOT / ".github" / "scripts" / "archive_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _listing(*pyz, pkg=()):
    """A listing in the form of pyi-archive_viewer --list --recursive, invented."""
    head = ["Options in 'dist/Zij/Zij.exe' (PKG/CArchive):", " pyi-runtime-tmpdir", "",
            "Contents of 'dist/Zij/Zij.exe' (PKG/CArchive):",
            " position, length, uncompressed_length, is_compressed, typecode, name",
            " 0, 201, 289, 1, 'm', 'struct'", " 201, 900, 2100, 1, 's', 'pyi_rth_setuptools'"]
    head += [f" 1101, 10, 20, 1, 'x', {name!r}" for name in pkg]
    head += [" 1111, 99999, 99999, 0, 'z', 'PYZ.pyz'", "", "Contents of 'PYZ.pyz' (PYZ):",
             " typecode, position, length, name", " 0, 17, 2100, 'engine'", " 1, 2117, 800, 'setuptools'",
             " 0, 2917, 310, 'setuptools.wheel'"]
    return "\n".join(head + [f" {typecode}, 3227, 400, {name!r}" for name, typecode in pyz]) + "\n"


def test_a_listing_with_the_program_s_module_passes(check):
    assert check.faults(_listing(("wheel", 0))) == []


def test_a_listing_with_windows_line_ends_passes(check):
    assert check.faults(_listing(("wheel", 0)).replace("\n", "\r\n")) == []


@pytest.mark.parametrize("plant", [
    pytest.param([("wheel", 1)], id="wheel a package"),
    pytest.param([("wheel", 0), ("wheel.wheelfile", 0)], id="something inside wheel"),
    pytest.param([("wheel", 0), ("setuptools._vendor.wheel", 1)], id="the copy beside the module"),
    pytest.param([("wheel", 0), ("setuptools._vendor.wheel.cli", 0)], id="part of the copy"),
    pytest.param([("wheel", 1), ("setuptools._vendor.wheel", 1), ("wheel.bdist_wheel", 0)], id="the alias"),
    pytest.param([], id="no wheel at all"),
])
def test_a_listing_planted_with_the_wrong_wheel_fails(check, plant):
    assert check.faults(_listing(*plant))


def test_setuptools_copy_is_found_in_the_outer_section_too(check):
    assert check.faults(_listing(("wheel", 0), pkg=["setuptools._vendor.wheel"]))


def test_names_that_only_resemble_them_pass(check):
    near = [("wheel", 0), ("wheelhouse", 1), ("wheelhouse.part", 0), ("setuptools._vendor.wheelbarrow", 0)]
    assert check.faults(_listing(*near)) == []


@pytest.mark.parametrize("text", ["", "Contents of 'x' (PKG/CArchive):\n position, length\n 0, 1, 1, 0, 'z', 'PYZ.pyz'\n",
                                  "Contents of 'PYZ.pyz' (PYZ):\n typecode, position, length, name\n"])
def test_a_listing_that_lists_nothing_fails(check, text):
    assert check.faults(text)


def test_the_script_runs_by_hand_on_a_listing(check, tmp_path, capsys):
    path = tmp_path / "listing.txt"
    path.write_text(_listing(("wheel", 0)), encoding="utf-8")
    assert check.main(["archive_check.py", str(path)]) == 0
    assert "wheel is a module" in capsys.readouterr().out
    path.write_text(_listing(("wheel", 1)), encoding="utf-8")
    assert check.main(["archive_check.py", str(path)]) == 1
    assert "typecode 1" in capsys.readouterr().err


@pytest.fixture(scope="module")
def spec():
    """build.spec's tree, and its UNUSED_MODULES, _unused, _module_of, _PYSIDE_DROP and _keep in a namespace of their own."""
    source = SPEC.read_text(encoding="utf-8")
    tree = ast.parse(source)
    space = {"os": os}
    names = {"UNUSED_MODULES", "_PYSIDE_DROP"}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and {ast.unparse(t) for t in node.targets} & names) or (
                isinstance(node, ast.FunctionDef) and node.name in ("_unused", "_module_of", "_keep")):
            exec(ast.get_source_segment(source, node), space)
    return tree, space


# As collect_all hands them over: the wheels' own paths, (source, destination folder).
SITE = "C:/runner/site-packages/PySide6"
DRIVERS = ("qsqlibase", "qsqlite", "qsqlmimer", "qsqloci", "qsqlodbc", "qsqlpsql")
STAYS = ("plugins/tls/qopensslbackend.dll", "plugins/platforms/qwindows.dll", "Qt6Sql.dll", "Qt6Help.dll",
         "Qt6WebEngineCore.dll", "QtNetwork.pyd", "QtHelp.pyd", "QtWebEngineWidgets.pyd",
         "QtWebEngineProcess.exe")


def _entry(relative):
    return (f"{SITE}/{relative}", "/".join(("PySide6", *relative.split("/")[:-1])))


@pytest.mark.parametrize("driver", DRIVERS)
def test_each_of_qt_s_database_drivers_leaves_the_windows_build(spec, driver):
    _tree, space = spec
    assert not space["_keep"](_entry(f"plugins/sqldrivers/{driver}.dll"))


@pytest.mark.parametrize("name", ["QtSql.pyd", "QtSql.pyi"])
def test_qt_s_sql_module_leaves_the_windows_build(spec, name):
    _tree, space = spec
    assert not space["_keep"](_entry(name))


@pytest.mark.parametrize("relative", STAYS)
def test_what_the_window_needs_of_qt_stays(spec, relative):
    _tree, space = spec
    assert space["_keep"](_entry(relative))


def test_the_filter_runs_on_both_lists_on_windows(spec):
    tree, _space = spec
    gate = next(n for n in tree.body if isinstance(n, ast.If) and "_keep" in ast.unparse(n)
                and ast.unparse(n.test) == "sys.platform == 'win32'")
    lines = [ast.unparse(n) for n in gate.body]
    assert "datas = [e for e in datas if _keep(e)]" in lines
    assert "binaries = [e for e in binaries if _keep(e)]" in lines


def test_the_module_goes_too_or_its_hook_collects_the_drivers_again(spec):
    """PyInstaller's hook for PySide6.QtSql collects the sqldrivers plugins: the hidden import from
    collect_all, and Qt6Help.dll's link through its own hook, would each reach it. Analysis's
    excludes are what stops both, and they hold UNUSED_MODULES."""
    tree, space = spec
    assert "PySide6.QtSql" in space["UNUSED_MODULES"] and space["_unused"]("PySide6.QtSql")
    assert not space["_unused"]("PySide6.QtHelp") and not space["_unused"]("PySide6.QtNetwork")
    analysis = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == "Analysis")
    assert "*UNUSED_MODULES" in ast.unparse(next(k.value for k in analysis.keywords if k.arg == "excludes"))
