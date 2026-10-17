"""A check that skips is not a check: the suite fails on a skip it cannot account for.

A plugin, loaded by pytest.ini's `-p skip_guard` rather than by conftest.py, so
that `--noconftest` cannot switch it off (it refuses that option instead: the
conftest also holds the data-folder redirect). At the end of a run it looks at
every skipped test:

* With the texts present (CORPUS_DIR is a directory), nothing may skip. A
  corpus test that skips there has lost its file -- renamed, moved, a path
  typed wrong -- and would otherwise go quiet while the rest stay green. So
  would a test whose dependency is missing (brotli, fontTools: install
  requirements-dev.txt).
* Without them (CI, a stranger's checkout), a test may skip only because the
  texts are absent, and only through this guard's own check of them:
  `needs_corpus(path, ...)` as a mark, or `skip_without_corpus(path, ...)` in
  the test. A skip whose reason merely mentions the texts is not one of those,
  and fails the run like any other.

Beside the skips it counts what is a skip by another name: an xfail that never
runs (run=False), a pytest.xfail() call, an xfail for a missing text, and an
xfail that passed without failing the run (a non-strict marker; pytest.ini
makes every marker strict unless it says otherwise). A run ended early by
pytest.exit() with a passing status fails too: the tests after it never ran.

No count is kept anywhere: counts go stale, and the rule does not need one.
With the texts present the allowed number of skips is 0, and without them
every skip must be one of the guard's own.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import corpus_paths

CORPUS_REASON = re.compile(r"corpus|photograph", re.I)
CAUSE = "skip_guard"                 # the user property a skip of the guard's own carries
_skipped: list[tuple[str, str, bool]] = []
_ended_early: list[str] = []


class CorpusAbsent(pytest.skip.Exception):
    """The one skip the guard allows without the texts: raised only by its own
    check, for a path under the corpus root that is not there."""


def corpus_present() -> bool:
    return Path(corpus_paths.CORPUS_DIR).is_dir()


def _corpus_paths(paths) -> list[Path]:
    root = Path(os.path.normpath(corpus_paths.CORPUS_DIR))
    found = [Path(os.path.normpath(root / p)) for p in paths] or [root]     # an absolute p replaces root
    outside = [str(p) for p in found if not p.is_relative_to(root)]
    if outside:
        raise ValueError(f"not under the corpus root, so its absence is not the texts': {outside}")
    return found


def _check(paths, why=None, **kw) -> None:
    missing = [p for p in _corpus_paths(paths) if not p.exists()]
    if missing:
        raise CorpusAbsent(f"the corpus is not on this machine ({missing[0].name})"
                           + (f": {why}" if why else ""), **kw)


def skip_without_corpus(*paths, why: str | None = None) -> None:
    """Skip the calling test unless every path (the corpus root when none is
    given) exists. Each path is a corpus file, absolute or relative to the root;
    a path anywhere else is refused, so this cannot excuse an unrelated skip.
    `why` adds what still guards the subject while the texts are away."""
    _check(paths, why)


def needs_corpus(*paths, why: str | None = None):
    """The mark form of skip_without_corpus: @needs_corpus(path, ..., why=...)."""
    _corpus_paths(paths)                          # refuse a path outside the root where it is written
    return pytest.mark.needs_corpus(*paths, why=why)


def problems(skipped, present: bool) -> list[str]:
    """[(test id, reason, by the guard's own check), ...] -> the skips the rule
    does not allow. A pair (test id, reason) is a skip of no known cause."""
    rows = [(s[0], s[1], bool(s[2]) if len(s) > 2 else False) for s in skipped]
    if present:
        return [f"{nid}: {why}" for nid, why, _ in rows]
    return [f"{nid}: {why}" for nid, why, ours in rows if not ours]


def _reason(report) -> str:
    lr = report.longrepr
    if isinstance(lr, tuple) and len(lr) == 3:
        return str(lr[2]).removeprefix("Skipped: ")
    return str(lr)


def _imperative_xfail(report) -> bool:
    """True when the report's xfail was raised by a call to pytest.xfail() -- in the
    test, a helper or a fixture -- rather than earned by an xfail marker's test
    failing. The raised exception is pytest's XFailed, and the report's crash line
    names it, serial and under xdist alike (the controller gets the serialised
    longrepr, whose reprcrash survives). A marker xfail's crash line names the
    test's own exception (AssertionError, ValueError ...)."""
    crash = getattr(report.longrepr, "reprcrash", None)
    message = getattr(crash, "message", "") or ""
    return message.startswith(("_pytest.outcomes.XFailed:", "XFailed:"))


def _ours(report) -> bool:
    """The skip came from CorpusAbsent: tagged where it was raised (in the
    worker, under xdist), the tag travels to the controller with the report."""
    return any(len(p) == 2 and p[0] == CAUSE and p[1] == "corpus absent"
               for p in getattr(report, "user_properties", ()) or ())


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_corpus(*paths): skip unless these corpus files are here "
                                       "(the skip guard's own check)")
    if config.getoption("noconftest", False):
        raise pytest.UsageError("--noconftest drops the harness that keeps a run off the reader's own "
                                "data folder; the suite does not run without it")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    for mark in item.iter_markers("needs_corpus"):
        _check(mark.args, mark.kwargs.get("why"), _use_item_location=True)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    # The tag is the guard's alone: one a test wrote into its own properties is dropped.
    report.user_properties = [p for p in report.user_properties if not (len(p) == 2 and p[0] == CAUSE)]
    if call.excinfo is not None and isinstance(call.excinfo.value, CorpusAbsent):
        report.user_properties.append((CAUSE, "corpus absent"))
    return report


def pytest_runtest_logreport(report):
    # Under xdist the controller receives every worker's reports here.
    xfail = getattr(report, "wasxfail", None)
    if report.skipped and not xfail:
        _skipped.append((report.nodeid, _reason(report), _ours(report)))
    elif xfail is not None and report.passed:
        # a non-strict xfail whose test passed: green whether its check holds
        # or not (pytest.ini makes markers strict; this one said strict=False,
        # or the run overrode the default)
        _skipped.append((report.nodeid, f"xfail not strict, passed: {xfail}", False))
    elif xfail is not None and report.skipped and "[NOTRUN]" in str(report.longrepr):
        # xfail(run=False) is never executed: a check switched off for good
        # (hostile pass of 2026-10-03, L7-14); the report's longrepr says [NOTRUN]
        _skipped.append((report.nodeid, f"xfail(run=False), never run: {xfail}", False))
    elif xfail is not None and report.skipped and _imperative_xfail(report):
        # pytest.xfail() stops its test where it is called: the rest never runs,
        # whatever the engine does -- a skip by another name (re-pass of
        # 2026-10-04, L7-14 partly). A strict xfail marker's test still runs.
        _skipped.append((report.nodeid, f"pytest.xfail() called, the rest never run: {xfail}", False))
    elif xfail is not None and CORPUS_REASON.search(str(xfail)):
        # an xfail for a missing text is a skip by another name (hostile pass
        # of 2026-09-23, finding 9); a strict xfail for a known bug is not
        _skipped.append((report.nodeid, f"xfail: {xfail}", False))


def pytest_collectreport(report):
    """A module skipped at collection -- pytest.skip(allow_module_level=True), a
    module-level importorskip, unittest.SkipTest at import -- never reaches
    pytest_runtest_logreport; it arrives here. None is the guard's own."""
    if report.skipped:
        _skipped.append((report.nodeid or "(collection)", _reason(report), False))


def pytest_keyboard_interrupt(excinfo):
    """Called for Ctrl-C and for pytest.exit(); the second can set a passing status."""
    if isinstance(excinfo.value, pytest.exit.Exception):
        _ended_early.append(str(excinfo.value.msg))


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):      # an xdist worker: the controller decides
        return
    lines = []
    if _ended_early and session.exitstatus == 0:
        lines = [f"SKIP GUARD: the run was ended by pytest.exit() ({_ended_early[0]}); "
                 "the tests after it never ran"]
    present = corpus_present()
    bad = problems(_skipped, present)
    if bad:
        head = ("the texts are present, so nothing may skip -- a corpus test that skips here has "
                "lost its file, and a missing dependency means requirements-dev.txt is not installed"
                if present else
                "the texts are absent, so a test may skip only through the guard's own check for them "
                "(needs_corpus, skip_without_corpus)")
        lines += [f"SKIP GUARD: {len(bad)} skip(s) not allowed -- {head}:"] + [f"  {b}" for b in bad]
    if not lines:
        return
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    if tr is not None:
        tr.write_line("")
        for ln in lines:
            tr.write_line(ln, red=True)
    session.exitstatus = 1
