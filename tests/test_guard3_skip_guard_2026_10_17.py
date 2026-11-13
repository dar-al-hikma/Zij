"""The skip guard refuses a run in which the suite's conftest did not load.

The conftest holds the data-folder redirect, and the guard used to refuse only
`--noconftest` by name: a `--confcutdir` below tests/ dropped the conftest as
surely, and the run went on with the reader's own data folder. The guard now
asks the run's own plugin registry whether the conftest beside it is loaded,
not the environment (the conftest's harness mark is inherited by every process
a test starts), at the start of the session, in the run and in each worker.

Options that drop the guard and the conftest together leave nothing in the run
to refuse them, so every run the guard polices ends with one fixed line,
`SKIP GUARD: <n> skip(s) checked`, whatever its outcome and once under xdist;
the test workflow fails a run without it (its own test is private, beside the
workflow).

Each throwaway suite is a copy of the harness (the conftest, the guard and the
two helpers they import, pytest.ini) with a stand-in engine, so the run is
wired as the suite is.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import conftest
import skip_guard

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
HARNESS = ("conftest.py", "corpus_paths.py", "skip_guard.py", "source_list.py")
CHECKED = re.compile(r"^SKIP GUARD: \d+ skip\(s\) checked$", re.M)
REFUSAL = "conftest.py did not load in this run"
SKIP = "import pytest\n\ndef test_ok():\n    pass\n\ndef test_skip():\n    pytest.skip('planted: an unpoliced skip')\n"


def clone(tmp_path, files):
    """A copy of the harness under `tmp_path`, with `files` (path -> source) planted."""
    root = tmp_path / "clone"
    (root / "tests" / "fixtures" / "deeper").mkdir(parents=True)
    (root / "plug").mkdir()
    for name in HARNESS:
        shutil.copy(TESTS / name, root / "tests" / name)
    shutil.copy(ROOT / "pytest.ini", root / "pytest.ini")
    (root / "engine.py").write_text("class UnresolvedResult:\n    pass\n", encoding="utf-8")
    for rel, source in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(source, encoding="utf-8")
    return root


def _environment(tmp_path, child, extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTEST_ADDOPTS", "PYTHONPATH") and not k.startswith("PYTEST_XDIST_")}
    if not child:                                    # started by hand: no test runs, no harness mark
        env.pop("PYTEST_CURRENT_TEST", None)
        env.pop(conftest.HARNESS_MARK, None)
    env.update(CORPUS_DIR=str(tmp_path / "no-corpus"), XDG_DATA_HOME=str(tmp_path / "xdg"))
    env.update(extra or {})
    return env


def run(root, *args, child=False, env=None, cwd=None):
    """pytest over the clone `root`. `child`: started as a test starts one, its
    environment carrying the harness mark, set to the clone's own scratch, which
    is what the clone's conftest would set."""
    tmp_path = root.parent
    extra = dict(env or {})
    if child:
        assert os.environ.get("PYTEST_CURRENT_TEST"), "premise: this runs inside a test"
        extra[conftest.HARNESS_MARK] = str(root / "tests" / ".xdg-scratch")
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or root,
                          env=_environment(tmp_path, child, extra), timeout=300)


def out(r):
    return r.stdout + r.stderr


# ---------------------------------------------------------------- the conftest dropped: refused

DROPS = {
    "confcutdir fixtures": ("--confcutdir=tests/fixtures",),
    "confcutdir deeper": ("--confcutdir=tests/fixtures/deeper",),
    "noconftest": ("--noconftest",),
}


@pytest.mark.parametrize("child", [False, True], ids=["top level", "child of a test"])
@pytest.mark.parametrize("how", sorted(DROPS))
def test_a_run_that_drops_the_conftest_is_refused(tmp_path, how, child):
    root = clone(tmp_path, {"tests/test_plant.py": SKIP})
    r = run(root, *DROPS[how], child=child)
    assert r.returncode == 4 and REFUSAL in out(r) and "data folder" in out(r), out(r)
    assert "passed" not in r.stdout, out(r)


@pytest.mark.parametrize("child", [False, True], ids=["top level", "child of a test"])
def test_the_options_in_the_environment_are_refused_too(tmp_path, child):
    root = clone(tmp_path, {"tests/test_plant.py": SKIP})
    r = run(root, child=child, env={"PYTEST_ADDOPTS": "--confcutdir=tests/fixtures"})
    assert r.returncode == 4 and REFUSAL in out(r), out(r)


@pytest.mark.parametrize("child", [False, True], ids=["top level", "child of a test"])
def test_under_xdist_the_run_is_refused_before_a_worker_starts(tmp_path, child):
    root = clone(tmp_path, {"tests/test_plant.py": SKIP})
    r = run(root, "-n", "2", "--confcutdir=tests/fixtures", child=child)
    assert r.returncode == 4 and REFUSAL in out(r), out(r)
    assert "created:" not in out(r) and "[gw" not in out(r), out(r)


def test_a_test_file_outside_tests_run_under_the_suites_ini_is_refused(tmp_path):
    """Another route to the same hole: the guard loaded by the ini, the conftest
    never met, because the file collected lies outside tests/."""
    root = clone(tmp_path, {"elsewhere/test_plant.py": SKIP})
    r = run(root, "elsewhere/test_plant.py")
    assert r.returncode == 4 and REFUSAL in out(r), out(r)


def test_the_real_suite_with_its_conftest_cut_off_is_refused():
    """The repository's own tree: the refusal comes before any test is collected."""
    for cut in ("tests/fixtures", "tests/fixtures/stop_check"):
        env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--confcutdir={cut}",
                            str(TESTS / "test_corpus_key_2026_10_13.py")],
                           capture_output=True, text=True, cwd=ROOT, env=env, timeout=300)
        assert r.returncode == 4 and REFUSAL in out(r), (cut, out(r))


# ---------------------------------------------------------------- the conftest loaded: the honest runs

KEPT = {
    "plain": (),
    "confcutdir tests": ("--confcutdir=tests",),
    "confcutdir root": ("--confcutdir=.",),
    "confcutdir sibling": ("--confcutdir=plug",),
    "importlib mode": ("--import-mode=importlib",),
    "two workers": ("-n", "2"),
    "by file": ("-n", "2", "--dist", "loadfile"),
}


@pytest.mark.parametrize("how", sorted(KEPT))
def test_an_honest_run_passes_and_says_so_once(tmp_path, how):
    root = clone(tmp_path, {"tests/test_honest.py": "def test_a():\n    pass\n\ndef test_b():\n    pass\n"})
    r = run(root, *KEPT[how])
    assert r.returncode == 0 and "2 passed" in r.stdout, out(r)
    assert CHECKED.findall(r.stdout) == ["SKIP GUARD: 0 skip(s) checked"], out(r)


def test_an_honest_run_started_in_the_tests_folder_passes(tmp_path):
    root = clone(tmp_path, {"tests/test_honest.py": "def test_a():\n    pass\n"})
    r = run(root, cwd=root / "tests")
    assert r.returncode == 0 and len(CHECKED.findall(r.stdout)) == 1, out(r)


@pytest.mark.parametrize("workers", [None, 2])
@pytest.mark.parametrize("body, code, n", [
    (SKIP, 1, 1),                                                      # the guard fails the run
    ("def test_a():\n    assert False\n", 1, 0),                       # a test fails it
    ("import pytest\n\ndef test_a():\n    pytest.exit('enough', returncode=0)\n", None, 0),
    ("def test_a(:\n", None, 0),                                       # collection error
], ids=["planted skip", "failing test", "pytest.exit", "collection error"])
def test_every_run_ends_with_the_line_once_whatever_its_outcome(tmp_path, body, code, n, workers):
    """`code` None: any failing status (xdist reports pytest.exit and a module
    that does not parse by statuses of its own)."""
    root = clone(tmp_path, {"tests/test_one.py": body})
    r = run(root, *(("-n", str(workers)) if workers else ()))
    assert r.returncode == code if code is not None else r.returncode != 0, out(r)
    assert CHECKED.findall(r.stdout) == [f"SKIP GUARD: {n} skip(s) checked"], out(r)


def test_the_real_suite_run_by_one_file_says_so_once():
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", "2",
                        str(TESTS / "test_corpus_key_2026_10_13.py")],
                       capture_output=True, text=True, cwd=ROOT, env=env, timeout=300)
    assert r.returncode == 0 and len(CHECKED.findall(r.stdout)) == 1, out(r)


def test_this_run_loaded_the_conftest(pytestconfig):
    assert skip_guard.conftest_loaded(pytestconfig.pluginmanager)
    assert skip_guard.CONFTEST == Path(conftest.__file__).resolve()
