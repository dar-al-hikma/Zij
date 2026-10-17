"""The skip guard (tests/skip_guard.py): the run fails on a skip it cannot account for."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from skip_guard import problems

TESTS = Path(__file__).resolve().parent


def test_with_the_texts_present_nothing_may_skip():
    assert problems([("t::a", "corpus file not in hand")], present=True) == ["t::a: corpus file not in hand"]
    assert problems([], present=True) == []


def test_without_the_texts_only_a_skip_for_them_is_allowed():
    """Only the guard's own check of the texts excuses a skip (the third field):
    a reason that merely names them does not."""
    skipped = [("t::a", "the corpus is not on this machine (x.md)", True),
               ("t::b", "the photographed page is not on this machine", False),
               ("t::c", "brotli is not installed", False),
               ("t::d", "escaping check disabled until the corpus of names is re-cut")]
    assert problems(skipped, present=False) == [
        "t::b: the photographed page is not on this machine", "t::c: brotli is not installed",
        "t::d: escaping check disabled until the corpus of names is re-cut"]


HOOKS = ("from skip_guard import pytest_runtest_logreport, pytest_sessionfinish, pytest_collectreport, "
         "pytest_runtest_setup, pytest_runtest_makereport\n")


def run(tmp_path, reason, corpus_dir, workers=None):
    """A throwaway suite whose one test skips with `reason`, run as a real pytest session.
    `reason` None: the test skips through the guard's own check of the texts."""
    (tmp_path / "conftest.py").write_text(f"import sys\nsys.path.insert(0, {str(TESTS)!r})\n" + HOOKS)
    skip = "skip_without_corpus('a.md')" if reason is None else f"pytest.skip({reason!r})"
    (tmp_path / "test_one.py").write_text(
        "import pytest\nfrom skip_guard import skip_without_corpus\n\ndef test_ok():\n    pass\n\n"
        f"def test_skips():\n    {skip}\n")
    cmd = [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"]
    if workers:
        cmd += ["-n", str(workers)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=tmp_path,
                          env=dict(os.environ, CORPUS_DIR=str(corpus_dir)))


@pytest.mark.parametrize("workers", [None, 2])
def test_a_skip_with_the_texts_present_fails_the_run(tmp_path, workers):
    present = tmp_path / "corpus"
    present.mkdir()
    suite = tmp_path / "suite"
    suite.mkdir()
    r = run(suite, "corpus file not in hand", present, workers)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "SKIP GUARD" in r.stdout and "test_skips" in r.stdout


@pytest.mark.parametrize("workers", [None, 2])
def test_without_the_texts_a_corpus_skip_passes_and_another_fails(tmp_path, workers):
    absent = tmp_path / "no-corpus"
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ok = run(tmp_path / "a", None, absent, workers)
    assert ok.returncode == 0 and "1 skipped" in ok.stdout, ok.stdout + ok.stderr
    bad = run(tmp_path / "b", "no star catalogue in this interpreter", absent, workers)
    assert bad.returncode == 1 and "SKIP GUARD" in bad.stdout, bad.stdout + bad.stderr
    (tmp_path / "c").mkdir()
    worded = run(tmp_path / "c", "the corpus is not on this machine", absent, workers)
    assert worded.returncode == 1 and "SKIP GUARD" in worded.stdout, worded.stdout + worded.stderr


# ---------------------------------------------------------------- the hostile pass over P2 (batch D)

def run_module(tmp_path, body, corpus_dir, workers=None):
    """A throwaway suite with one module whose source is `body`."""
    (tmp_path / "conftest.py").write_text(f"import sys\nsys.path.insert(0, {str(TESTS)!r})\n" + HOOKS)
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    pass\n")
    (tmp_path / "test_mod.py").write_text(body)
    cmd = [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"]
    if workers:
        cmd += ["-n", str(workers)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=tmp_path,
                          env=dict(os.environ, CORPUS_DIR=str(corpus_dir)))


@pytest.mark.parametrize("workers", [None, 2])
@pytest.mark.parametrize("body", [
    "import pytest\npytest.skip('corpus file not in hand', allow_module_level=True)\ndef test_x():\n    pass\n",
    "import pytest\nnope = pytest.importorskip('a_module_that_is_not_there')\ndef test_x():\n    pass\n",
    "import unittest\nraise unittest.SkipTest('corpus file not in hand')\n",
    "import pytest\n@pytest.mark.xfail(reason='the corpus file moved')\ndef test_x():\n    assert False\n",
])
def test_collection_skips_and_corpus_xfails_fail_with_the_texts_present(tmp_path, body, workers):
    present = tmp_path / "corpus"
    present.mkdir()
    suite = tmp_path / "suite"
    suite.mkdir()
    r = run_module(suite, body, present, workers)
    assert r.returncode == 1 and "SKIP GUARD" in r.stdout, r.stdout + r.stderr


def test_a_strict_xfail_for_a_known_bug_is_not_a_skip(tmp_path):
    present = tmp_path / "corpus"
    present.mkdir()
    suite = tmp_path / "suite"
    suite.mkdir()
    body = ("import pytest\n@pytest.mark.xfail(strict=True, reason='F12: the label is wrong today')\n"
            "def test_x():\n    assert False\n")
    r = run_module(suite, body, present)
    assert r.returncode == 0, r.stdout + r.stderr


def scanned_files(tests=TESTS):
    """Every Python file under tests/ that pytest could collect or a test could
    import: nested folders and `*_test.py` names included; only the fixtures'
    data and the harness's scratch folder are left out."""
    return sorted(f for f in tests.rglob("*.py")
                  if not {"fixtures", ".xdg-scratch", "__pycache__"} & set(f.relative_to(tests).parts))


def nonstrict_xfails(tests=TESTS):
    """Non-strict, run=False and imperative xfails in scanned_files(tests)."""
    import ast
    bad = []
    for f in scanned_files(tests):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = ast.unparse(n.func)
            if name.endswith("pytest.xfail") or name == "xfail":
                bad.append(f"{f.relative_to(tests)}:{n.lineno} imperative xfail")
            elif name.endswith("mark.xfail"):
                kw = {k.arg: k.value for k in n.keywords}
                strict = isinstance(kw.get("strict"), ast.Constant) and kw["strict"].value is True
                runs = not (isinstance(kw.get("run"), ast.Constant) and kw["run"].value is False)
                if not (strict and runs):
                    bad.append(f"{f.relative_to(tests)}:{n.lineno} xfail not strict, or not run")
    return bad


def test_every_xfail_in_the_suite_is_strict_and_runs():
    """Non-strict, run=False and imperative xfails are skips by another name;
    the hostile-pass files' strict xfails ("un-xfail me") are the one allowed form."""
    assert not nonstrict_xfails(), nonstrict_xfails()
