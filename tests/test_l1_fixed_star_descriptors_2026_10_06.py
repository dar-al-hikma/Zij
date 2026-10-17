"""The fixed-star catalogue's file descriptors (wave 3, lane L1).

Swiss Ephemeris keeps its open star catalogue in thread-local state, and the
engine attached the catalogue in every thread that asked for a star. A thread
that read a star and then ended left its descriptor on ``ephe/sefstars.txt``
open for the life of the process: one per Streamlit script run, so a served
app leaked one per session run, and the suite's workers held thousands. The
catalogue is now read in one thread per process, so however many threads ask
for stars, at most one descriptor on the file is ever open.

Every descriptor test asserts, on every platform, that the catalogue was read
in exactly one thread, and that something was read at all; where the platform
can name an open descriptor's file (``/proc/self/fd`` on Linux, ``/dev/fd``
with ``F_GETPATH`` on macOS) it also counts the descriptors. Nothing skips.

A process that forks after a star read hands its child the reader's executor
but not its thread; the child must still read its stars.
"""
from __future__ import annotations

import json
import os
import signal
import threading
import time

import pytest

try:
    import fcntl
except ImportError:                                    # Windows
    fcntl = None

_PROC_FD = "/proc/self/fd"
_DEV_FD = "/dev/fd"


def _star_descriptors():
    """Open descriptors on sefstars.txt, or None where this platform cannot
    name an open descriptor's file."""
    if os.path.isdir(_PROC_FD):
        base, name = _PROC_FD, lambda fd: os.readlink(f"{_PROC_FD}/{fd}")
    elif os.path.isdir(_DEV_FD) and fcntl is not None and hasattr(fcntl, "F_GETPATH"):
        base, name = _DEV_FD, lambda fd: fcntl.fcntl(int(fd), fcntl.F_GETPATH, bytes(1024)).split(b"\0")[0].decode(errors="replace")
    else:
        return None
    n = 0
    for fd in os.listdir(base):
        try:
            if name(fd).endswith("sefstars.txt"):
                n += 1
        except OSError:
            pass
    return n


@pytest.fixture
def star_readers(monkeypatch):
    """The threads in which the catalogue is read, from now on (the thread
    objects: an ident is reused once its thread ends)."""
    import swisseph as swe
    real, readers = swe.fixstar2_ut, set()

    def counted(*a, **k):
        readers.add(threading.current_thread())
        return real(*a, **k)

    monkeypatch.setattr(swe, "fixstar2_ut", counted)
    return readers


def _assert_one_handle(readers, what):
    assert readers, f"no star was read during {what}; the count proves nothing"
    assert len(readers) == 1, f"the catalogue was read in {len(readers)} threads during {what}"
    n = _star_descriptors()
    if n is not None:
        assert n <= 1, f"{n} descriptors open on sefstars.txt after {what}"


def _in_fresh_threads(fn, n, *args):
    out = []
    for _ in range(n):
        t = threading.Thread(target=lambda: out.append(fn(*args)))
        t.start()
        t.join(timeout=60)
        assert not t.is_alive()
    return out


def test_threads_that_read_stars_and_end_leave_at_most_one_descriptor(engine, star_readers):
    assert engine["fixed_star_longitudes"](2451545.0), "no catalogue attached; the count below proves nothing"
    results = _in_fresh_threads(engine["fixed_star_longitudes"], 20, 2451545.0)
    assert [len(r) for r in results] == [28] * 20
    _assert_one_handle(star_readers, "20 threads")


def test_a_reattach_and_a_refusal_open_no_second_descriptor(engine, star_readers):
    """Clearing the search's flag forces the attach again (the tests above in
    test_doctrine_fixtures.py do it); the refusal's sentence asks for the
    catalogue too. Neither, in fresh threads, leaves a descriptor behind."""
    state = engine["_FIXED_STAR_STATE"]
    for _ in range(5):
        state.update(checked=False, ready=False, where=None, why=None)
        assert _in_fresh_threads(engine["_fixed_star_catalogue_ready"], 1) == [True]
        assert _in_fresh_threads(engine["fixed_star_refusal"], 1)[0].startswith("no Swiss Ephemeris star catalogue")
    _assert_one_handle(star_readers, "5 re-attaches and 5 refusals")


def test_timing_page_renders_leave_at_most_one_descriptor(star_readers):
    """Each AppTest run is a script run in a thread of its own, as each
    Streamlit session run is. The renders must read a star (this chart's
    page carries star rows) for the count to mean anything."""
    from conftest import assert_no_exception, make_app
    for k in range(3):
        at = make_app(page="timing", timeout=180).run()
        assert_no_exception(at, f"timing render {k + 1}")
    _assert_one_handle(star_readers, "3 Timing renders")


def test_the_catalogue_is_opened_in_one_thread_however_many_ask(engine, monkeypatch):
    """Portable: every read of the catalogue happens in one thread, so only
    one thread's Swiss Ephemeris state ever holds the file."""
    import swisseph as swe
    real, readers = swe.fixstar2_ut, set()

    def counted(*a, **k):
        readers.add(threading.current_thread())   # the object: an ident is reused once its thread ends
        return real(*a, **k)

    monkeypatch.setattr(swe, "fixstar2_ut", counted)
    engine["fixed_star_longitudes"](2451545.0)
    _in_fresh_threads(engine["fixed_star_longitudes"], 5, 2451545.0)
    assert len(readers) == 1, f"the catalogue was read in {len(readers)} threads"


def test_every_thread_places_every_star_at_the_same_longitude(engine):
    """The values do not depend on the asking thread: equal, not close."""
    for jd in (2451545.0, 2176000.0, 2460000.5):
        here = engine["fixed_star_longitudes"](jd)
        assert len(here) == 28
        assert _in_fresh_threads(engine["fixed_star_longitudes"], 3, jd) == [here] * 3


def test_a_child_forked_after_a_star_read_reads_its_stars(engine):
    """The child inherits the reader's executor but not its thread; without a
    fork hook its first read queued work nothing would run and never
    returned. Bounded: the child is killed after 30 s and the test fails."""
    want = engine["fixed_star_longitudes"](2451545.0)
    assert len(want) == 28 and _in_fresh_threads(engine["fixed_star_longitudes"], 1, 2451545.0) == [want]
    if not hasattr(os, "fork"):                        # Windows: no child can inherit the reader
        return
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:                                       # the child: read, write, leave without pytest's teardown
        code = 1
        try:
            os.close(r)
            signal.alarm(40)
            os.write(w, json.dumps(engine["fixed_star_longitudes"](2451545.0)).encode())
            code = 0
        finally:
            os._exit(code)
    os.close(w)
    deadline = time.monotonic() + 30
    while True:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        if time.monotonic() > deadline:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            os.close(r)
            pytest.fail("the forked child's first star read did not return in 30 s")
        time.sleep(0.05)
    with os.fdopen(r, "rb") as pipe:
        got = pipe.read()
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0, status
    assert json.loads(got) == want


def test_a_star_read_after_shutdown_has_begun_is_still_computed():
    """A non-daemon thread still running when the main thread returns (a
    session mid-run as the server stops) asks for stars after the reader's
    executor has stopped taking work: the read is done in place."""
    import subprocess
    import sys
    from pathlib import Path
    code = ("import sys, threading, time, warnings\n"
            "warnings.simplefilter('ignore')\n"
            "import engine\n"
            "engine.fixed_star_longitudes(2451545.0)\n"
            "def late():\n"
            "    time.sleep(0.5)\n"
            "    print(len(engine.fixed_star_longitudes(2451545.0)), flush=True)\n"
            "threading.Thread(target=late).start()\n")
    root = Path(__file__).resolve().parent.parent
    p = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PYTHONPATH": str(root)})
    assert p.returncode == 0 and p.stdout.split() == ["28"], (p.stdout, p.stderr[-2000:])
