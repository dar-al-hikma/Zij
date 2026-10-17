"""The skip guard holds where it reported clean before.

* Without the texts, a skip is allowed only through the guard's own check of
  them (needs_corpus, skip_without_corpus), not for a reason that mentions them.
* An xfail marker is strict by pytest.ini's default, wherever its file lies
  (a subfolder, a `*_test.py` name), and the static scan reads those files too.
* The guard is a plugin pytest.ini names: `--noconftest` cannot drop it (the
  run is refused), and a run that blocks it is refused by the conftest.
* pytest.exit() with a passing status does not end a run green.
* On macOS, where the harness moves HOME, the corpus key is still read from
  the reader's own Git configuration, and every xdist worker reads the corpus
  the run resolved.

Each throwaway suite runs under a copy of the real pytest.ini, so it is wired
as the suite is.
"""
from __future__ import annotations

import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import skip_guard
from test_skip_guard_2026_09_23 import nonstrict_xfails

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent


def suite(tmp_path, files, corpus_dir, *args, env=None, workers=None):
    """Run a throwaway suite (`files`: relative path -> source) under a copy of
    the real pytest.ini, the guard imported from this folder as the suite
    imports it."""
    root = tmp_path / "suite"
    (root / "tests").mkdir(parents=True)
    shutil.copy(ROOT / "pytest.ini", root / "pytest.ini")
    for rel, source in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(source, encoding="utf-8")
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args]
    if workers:
        cmd += ["-n", str(workers)]
    run_env = dict(os.environ, CORPUS_DIR=str(corpus_dir), PYTHONPATH=str(TESTS))
    run_env.pop("PYTEST_ADDOPTS", None)
    run_env.update(env or {})
    return subprocess.run(cmd, capture_output=True, text=True, cwd=root, env=run_env, timeout=300)


def out(r):
    return r.stdout + r.stderr


# ---------------------------------------------------------------- without the texts: the cause, not the word

WORDED = [
    "pytest.skip('symlink check needs a photograph-free tmpfs; skipped')",
    "pytest.skip('escaping check disabled until the corpus of names is re-cut')",
    "pytest.skip('the corpus is not on this machine')",
]


@pytest.mark.parametrize("workers", [None, 2])
@pytest.mark.parametrize("skip", WORDED)
def test_without_the_texts_a_skip_that_only_names_them_fails_the_run(tmp_path, skip, workers):
    body = f"import pytest\n\ndef test_ok():\n    pass\n\ndef test_x():\n    {skip}\n"
    r = suite(tmp_path, {"tests/test_plant.py": body}, tmp_path / "no-corpus", workers=workers)
    assert r.returncode == 1 and "SKIP GUARD: 1 skip(s) not allowed" in r.stdout, out(r)


@pytest.mark.parametrize("workers", [None, 2])
def test_without_the_texts_a_skipif_that_only_names_them_fails_the_run(tmp_path, workers):
    body = ("import pytest\n\n@pytest.mark.skipif(True, reason='Corpus-style fixture not built on this OS')\n"
            "def test_x():\n    pass\n")
    r = suite(tmp_path, {"tests/test_plant.py": body}, tmp_path / "no-corpus", workers=workers)
    assert r.returncode == 1 and "SKIP GUARD" in r.stdout, out(r)


@pytest.mark.parametrize("workers", [None, 2])
def test_without_the_texts_the_guards_own_check_passes(tmp_path, workers):
    """The honest case: a corpus test skipping through the guard's check, as a mark
    and in the test, with and without the reason's addition."""
    body = ("from skip_guard import needs_corpus, skip_without_corpus\n\n"
            "@needs_corpus('a.md', why='the vendored list still guards it')\ndef test_mark():\n    pass\n\n"
            "@needs_corpus()\ndef test_root():\n    pass\n\n"
            "def test_call():\n    skip_without_corpus('b/c.md')\n")
    r = suite(tmp_path, {"tests/test_honest.py": body}, tmp_path / "no-corpus", "-rs", workers=workers)
    assert r.returncode == 0 and "3 skipped" in r.stdout, out(r)
    assert "the corpus is not on this machine (a.md): the vendored list still guards it" in r.stdout, out(r)


@pytest.mark.parametrize("workers", [None, 2])
def test_with_the_texts_the_guards_own_check_that_skips_fails_the_run(tmp_path, workers):
    """A corpus file the test needs is missing while the corpus is here: a lost file."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    body = "from skip_guard import skip_without_corpus\n\ndef test_call():\n    skip_without_corpus('moved.md')\n"
    r = suite(tmp_path, {"tests/test_lost.py": body}, corpus, workers=workers)
    assert r.returncode == 1 and "SKIP GUARD" in r.stdout and "moved.md" in r.stdout, out(r)


@pytest.mark.parametrize("workers", [None, 2])
def test_a_test_cannot_write_the_guards_tag_itself(tmp_path, workers):
    body = ("import pytest\n\ndef test_x(request, record_property):\n"
            "    record_property('skip_guard', 'corpus absent')\n"
            "    request.node.user_properties.append(('skip_guard', 'corpus absent'))\n"
            "    pytest.skip('the corpus is not on this machine')\n")
    r = suite(tmp_path, {"tests/test_plant.py": body}, tmp_path / "no-corpus", workers=workers)
    assert r.returncode == 1 and "SKIP GUARD" in r.stdout, out(r)


def test_no_test_raises_the_guards_own_skip_by_itself():
    """Only skip_guard.py names CorpusAbsent: a test that raised it by hand would
    pass any skip off as the texts' absence."""
    offenders = [f.name for f in sorted(TESTS.rglob("*.py"))
                 if f.name != "skip_guard.py" and f != Path(__file__) and "CorpusAbsent" in f.read_text(encoding="utf-8")]
    assert not offenders, offenders


def test_the_guards_check_refuses_a_path_outside_the_corpus():
    """It cannot be pointed at something else that is absent."""
    with pytest.raises(ValueError):
        skip_guard.skip_without_corpus(Path(os.devnull) / "no-such-tool")
    with pytest.raises(ValueError):
        skip_guard.needs_corpus("../outside.md")


def test_the_rule_reads_the_cause_not_the_reason():
    rows = [("t::a", "the corpus is not on this machine (x.md)", True),
            ("t::b", "the corpus is not on this machine (x.md)", False)]
    assert skip_guard.problems(rows, present=False) == ["t::b: the corpus is not on this machine (x.md)"]
    assert len(skip_guard.problems(rows, present=True)) == 2


def test_every_skip_in_the_suite_goes_through_the_guards_check():
    """No test file calls pytest.skip, skipif or importorskip for the texts by
    itself; the ones left are the dependency skips, which no rule allows."""
    import ast
    allowed = {"test_symbol_font_2026_09_15.py", "test_doctrine_fixtures.py", "test_revolution_wheels.py"}
    found = []
    for f in sorted(TESTS.glob("test_*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and ast.unparse(n.func) in ("pytest.skip", "pytest.mark.skipif",
                                                                    "pytest.importorskip", "skip", "skipif"):
                found.append(f.name)
    assert set(found) <= allowed, sorted(set(found) - allowed)


# ---------------------------------------------------------------- strict xfail, wherever the file lies

def test_pytest_ini_makes_every_xfail_strict():
    ini = configparser.ConfigParser()
    ini.read(ROOT / "pytest.ini", encoding="utf-8")
    assert ini["pytest"]["xfail_strict"].strip() == "true"


XFAILS = ("import pytest\n\n@pytest.mark.xfail(reason='known: the guard is wrong today')\n"
          "def test_passes():\n    assert True\n\n"
          "@pytest.mark.xfail(reason='known')\ndef test_fails():\n    assert False\n")


@pytest.mark.parametrize("workers", [None, 2])
@pytest.mark.parametrize("where", ["tests/sub/test_nested.py", "tests/plant_test.py", "tests/test_top.py"])
def test_an_unexpected_pass_under_an_xfail_fails_the_run_wherever_it_lies(tmp_path, where, workers):
    r = suite(tmp_path, {where: XFAILS}, tmp_path / "no-corpus", workers=workers)
    assert r.returncode == 1 and "1 failed" in r.stdout and "XPASS(strict)" in r.stdout, out(r)


@pytest.mark.parametrize("workers", [None, 2])
def test_an_xfail_that_says_strict_false_and_passes_fails_the_run(tmp_path, workers):
    body = ("import pytest\n\npytestmark = pytest.mark.xfail(strict=False, reason='lenient')\n\n"
            "def test_passes():\n    assert True\n")
    r = suite(tmp_path, {"tests/sub/test_lenient.py": body}, tmp_path / "corpus-absent", workers=workers)
    assert r.returncode == 1 and "xfail not strict, passed" in r.stdout, out(r)


@pytest.mark.parametrize("where", ["sub/test_nested.py", "plant_test.py", "deeper/still/helpers.py"])
def test_the_static_scan_reads_nested_files_and_star_test_names(tmp_path, where):
    tests = tmp_path / "tests"
    (tests / where).parent.mkdir(parents=True, exist_ok=True)
    (tests / where).write_text("import pytest\n\n@pytest.mark.xfail(strict=False)\ndef test_x():\n    pass\n",
                               encoding="utf-8")
    (tests / "fixtures").mkdir()
    (tests / "fixtures" / "data.py").write_text("import pytest\nX = pytest.mark.xfail(run=False)\n", encoding="utf-8")
    assert nonstrict_xfails(tests) == [f"{where}:3 xfail not strict, or not run"]


# ---------------------------------------------------------------- the guard's wiring

@pytest.mark.parametrize("how", ["option", "environment"])
def test_noconftest_is_refused_not_obeyed(tmp_path, how):
    """The plugin is loaded by pytest.ini, so --noconftest no longer drops it;
    it refuses the run, which would also drop the data-folder redirect."""
    body = "import pytest\n\ndef test_x():\n    pytest.skip('no reason at all')\n"
    args = ("--noconftest",) if how == "option" else ()
    env = {"PYTEST_ADDOPTS": "--noconftest"} if how == "environment" else None
    r = suite(tmp_path, {"tests/test_plant.py": body}, tmp_path / "no-corpus", *args, env=env)
    assert r.returncode == 4 and "--noconftest" in out(r), out(r)


def test_a_run_that_blocks_the_guard_is_refused():
    """The suite's own conftest refuses a run in which the plugin is not loaded."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:skip_guard",
                        str(TESTS / "test_corpus_key_2026_10_13.py"), "--collect-only"],
                       capture_output=True, text=True, cwd=ROOT, timeout=300,
                       env={k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"})
    assert r.returncode == 4 and "skip guard" in out(r), out(r)


def test_the_guard_is_loaded_in_this_run(pytestconfig):
    """A third anchor: a run with neither the plugin nor the conftest fails here."""
    assert pytestconfig.pluginmanager.has_plugin("skip_guard")


def test_pytest_exit_with_a_passing_status_fails_the_run(tmp_path):
    body = ("import pytest\n\ndef test_a():\n    pytest.exit('enough', returncode=0)\n\n"
            "def test_b():\n    assert False\n")
    r = suite(tmp_path, {"tests/test_plant.py": body}, tmp_path / "no-corpus")
    assert r.returncode == 1 and "ended by pytest.exit()" in r.stdout, out(r)


# ---------------------------------------------------------------- the corpus key with HOME moved (macOS)

DARWIN = """
import os, sys
sys.path.insert(0, {tests!r})
import streamlit.config                    # what conftest imports first, before the platform is faked
sys.platform = "darwin"                    # the harness then moves HOME, as it does on a Mac
import conftest
import corpus_paths
assert os.environ["HOME"] == str(conftest.HARNESS_DATA_HOME), os.environ["HOME"]
print(corpus_paths.CORPUS_DIR)
print(corpus_paths.CORPUS_SOURCE)
"""


def test_on_macos_the_global_corpus_key_is_read_before_home_moves(tmp_path):
    """A clone with only the global key (in a scratch home, never the reader's)
    and the harness's darwin branch: the key is still found. The harness and
    its helpers run from a copy in a scratch repository, so no repository's own
    key can stand in for the global one."""
    clone = tmp_path / "clone"
    (clone / "tests").mkdir(parents=True)
    for name in ("conftest.py", "corpus_paths.py", "skip_guard.py", "source_list.py"):
        shutil.copy(TESTS / name, clone / "tests" / name)
    home = tmp_path / "home"
    home.mkdir()
    corpus = tmp_path / "the corpus"
    corpus.mkdir()
    (home / ".gitconfig").write_text(f'[zij]\n\tcorpusDir = {corpus}\n', encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "CORPUS_DIR" and not k.startswith("GIT_")}
    env.update(HOME=str(home), XDG_DATA_HOME=str(tmp_path / "xdg"), GIT_CONFIG_NOSYSTEM="1",
               GIT_CEILING_DIRECTORIES=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / "xdg-config"))
    env.pop("PYTEST_CURRENT_TEST", None)
    subprocess.run(["git", "init", "-q", str(clone)], check=True, env=env)
    r = subprocess.run([sys.executable, "-c", DARWIN.format(tests=str(clone / "tests"))], capture_output=True,
                       text=True, cwd=clone / "tests", env=env, timeout=120)
    assert r.returncode == 0, out(r)
    assert r.stdout.splitlines()[-2:] == [str(corpus), "git config"], out(r)


DARWIN_PLUGIN = '''
import sys
import pytest
import urllib.request, streamlit, streamlit.config   # noqa: F401  (loaded on the real platform first)


@pytest.hookimpl(wrapper=True)
def pytest_load_initial_conftests(early_config, parser, args):
    real = sys.platform
    sys.platform = "darwin"          # only while the conftest loads: its darwin branch moves HOME
    try:
        return (yield)
    finally:
        sys.platform = real
'''

WHERE = '''
import os
import pytest
import corpus_paths
from skip_guard import skip_without_corpus


@pytest.mark.parametrize("n", range(8))
def test_where(n):
    seen = [os.environ.get("PYTEST_XDIST_WORKER", "main"), str(corpus_paths.CORPUS_DIR),
            corpus_paths.CORPUS_SOURCE, os.environ["HOME"]]
    with open(os.path.join({out!r}, f"{{n}}.tsv"), "w", encoding="utf-8") as f:
        f.write("\\t".join(seen))
    skip_without_corpus("a.md")
'''


@pytest.mark.parametrize("workers", [None, 2])
def test_on_macos_every_worker_reads_the_corpus_the_run_resolved(tmp_path, workers):
    """The harness's darwin branch, in a whole run: the key only in a scratch home's
    global configuration, HOME moved by the conftest in the run and in every xdist
    worker (which starts with it moved already). Every test, in every process, sees
    the corpus the key names, and none skips."""
    clone = tmp_path / "clone"
    (clone / "tests").mkdir(parents=True)
    (clone / "plug").mkdir()
    for name in ("conftest.py", "corpus_paths.py", "skip_guard.py", "source_list.py"):
        shutil.copy(TESTS / name, clone / "tests" / name)
    shutil.copy(ROOT / "pytest.ini", clone / "pytest.ini")
    (clone / "engine.py").write_text("class UnresolvedResult:\n    pass\n", encoding="utf-8")   # the autouse fixture's
    (clone / "plug" / "darwin_sim.py").write_text(DARWIN_PLUGIN, encoding="utf-8")
    seen_dir = tmp_path / "seen"
    seen_dir.mkdir()
    (clone / "tests" / "test_where.py").write_text(WHERE.format(out=str(seen_dir)), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    corpus = tmp_path / "the corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("text\n", encoding="utf-8")
    (home / ".gitconfig").write_text(f'[zij]\n\tcorpusDir = {corpus}\n', encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if k not in ("CORPUS_DIR", "PYTEST_ADDOPTS", "PYTEST_CURRENT_TEST")
           and not k.startswith(("GIT_", "PYTEST_XDIST_"))}   # the outer run's worker is not the child's
    env.update(HOME=str(home), XDG_DATA_HOME=str(tmp_path / "xdg"), GIT_CONFIG_NOSYSTEM="1",
               GIT_CEILING_DIRECTORIES=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / "xdg-config"),
               PYTHONPATH=str(clone / "plug"))
    subprocess.run(["git", "init", "-q", str(clone)], check=True, env=env)
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "darwin_sim", "-rs"]
    if workers:
        cmd += ["-n", str(workers)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=clone, env=env, timeout=300)
    seen = [f.read_text(encoding="utf-8").split("\t") for f in sorted(seen_dir.glob("*.tsv"))]
    assert r.returncode == 0 and "8 passed" in r.stdout and "skipped" not in r.stdout, (out(r), seen)
    assert len(seen) == 8, seen
    assert {s[3] for s in seen} == {str(clone / "tests" / ".xdg-scratch")}, seen      # HOME moved in each
    assert {(s[1], s[2]) for s in seen} == {(str(corpus), "git config")}, seen
    assert {s[0] for s in seen} == ({"gw0", "gw1"} if workers else {"main"}), seen
