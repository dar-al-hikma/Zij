"""The server child's watch on its launcher, on Windows.

The launcher holds the only writing end of its server child's input pipe and
never writes to it; the end of that pipe is the child's signal to stop. On
macOS and Linux a thread holds a read open on the pipe and sees the end when
the read returns. On Windows a read held open on the pipe stalls the app's
own run, so there the thread holds none: it asks the pipe how many bytes
wait, takes just those, and waits a named interval before asking again; a
broken pipe, the end of input, or anything else the pipe raises takes the
same stop path as the end of a held read.

The Windows path cannot run here. It is run with the platform said to be
Windows and stand-ins for msvcrt and _winapi, and with the stop path's calls
recorded rather than made. That the server on Linux still stops with its
launcher, live, is the stop window's own tests.
"""
import errno
import importlib.util
import signal
import subprocess
import sys
import time
import types

import pytest

from conftest import EXECUTABLE_DIR

LAUNCHER_PATH = EXECUTABLE_DIR / "desktop_launcher.py"
HANDLE = 4242
NOWHERE = 99


class _Exited(Exception):
    """os._exit as the stop path calls it, ending the run here instead."""


class _ScriptRanOut(BaseException):
    """The pipe was asked more often than the test's script allows: a watch
    that does not end where it should. Not an Exception, so that no handler
    in the watch can take it for the pipe's end."""


def _load_launcher(monkeypatch):
    """desktop_launcher.py as a module, a stand-in in pywebview's place."""
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    spec = importlib.util.spec_from_file_location("desktop_launcher_windows_pipe", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Pipe:
    """The child's end of the pipe as Windows shows it, and the process
    around it. `script` says what each ask finds: a count of bytes waiting,
    or an exception raised. Every call is recorded in `calls`, in order."""

    def __init__(self, script, *, given=None, handle_refused=None, reads=()):
        self.script = list(script)
        self.given = given
        self.handle_refused = handle_refused
        self.reads = list(reads)
        self.waiting = 0
        self.calls = []

    # msvcrt
    def get_osfhandle(self, fd):
        self.calls.append(("handle", fd))
        if self.handle_refused is not None:
            raise self.handle_refused
        return HANDLE

    # _winapi
    def PeekNamedPipe(self, handle, size=0):
        self.calls.append(("peek", handle, size))
        if not self.script:
            raise _ScriptRanOut("the pipe was asked again after its end")
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            self.waiting = 0
            raise step
        self.waiting = step
        return step, 0

    def ReadFile(self, handle, size, overlapped=False):
        self.calls.append(("ReadFile", handle, size, self.waiting))
        taken = self.given if self.given is not None else b"x" * min(size, self.waiting)
        self.waiting -= len(taken)
        return taken, 0

    # os, signal and time, as the watch and the stop path call them
    def read(self, fd, size):
        self.calls.append(("os.read", fd, size))
        if not self.reads:
            raise _ScriptRanOut("the input was read again after its end")
        step = self.reads.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    def open(self, path, flags):
        self.calls.append(("open", path, flags))
        return NOWHERE

    def dup2(self, fd, fd2):
        self.calls.append(("dup2", fd, fd2))

    def _exit(self, status):
        self.calls.append(("exit", status))
        raise _Exited(status)

    def raise_signal(self, number):
        self.calls.append(("raise_signal", number))

    def sleep(self, seconds):
        self.calls.append(("sleep", seconds))

    def watched(self):
        """The calls before the stop path's first."""
        names = [call[0] for call in self.calls]
        return self.calls[:names.index("open")] if "open" in names else list(self.calls)

    def stopped(self):
        """The calls from the stop path's first on."""
        return self.calls[len(self.watched()):]


def _watch(monkeypatch, platform, pipe, poll=None):
    """Run the watch on fd 0 with the platform said to be `platform`, its
    every outside call made on `pipe` (and its interval `poll`, if given);
    returned once the stop path has called os._exit."""
    launcher = _load_launcher(monkeypatch)
    if poll is not None:
        monkeypatch.setattr(launcher, "LAUNCHER_POLL_SECONDS", poll)
    monkeypatch.setattr(launcher, "sys", types.SimpleNamespace(platform=platform))
    monkeypatch.setattr(launcher, "os", types.SimpleNamespace(
        read=pipe.read, open=pipe.open, dup2=pipe.dup2, _exit=pipe._exit, devnull="nul", O_WRONLY=1))
    monkeypatch.setattr(launcher, "signal", types.SimpleNamespace(
        raise_signal=pipe.raise_signal, SIGTERM=signal.SIGTERM))
    monkeypatch.setattr(launcher, "time", types.SimpleNamespace(sleep=pipe.sleep))
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(get_osfhandle=pipe.get_osfhandle))
    monkeypatch.setitem(sys.modules, "_winapi", types.SimpleNamespace(
        PeekNamedPipe=pipe.PeekNamedPipe, ReadFile=pipe.ReadFile))
    with pytest.raises(_Exited):
        launcher._stop_when_the_launcher_goes(0)
    return launcher


def _assert_the_stop_path(launcher, pipe):
    """The stop path whole, as the end of a held read takes it: output sent
    nowhere, SIGTERM raised, and os._exit(1) after ORPHAN_WAIT_SECONDS."""
    assert pipe.stopped() == [
        ("open", "nul", 1), ("dup2", NOWHERE, 1), ("dup2", NOWHERE, 2),
        ("raise_signal", signal.SIGTERM), ("sleep", launcher.ORPHAN_WAIT_SECONDS), ("exit", 1),
    ], pipe.calls


def _assert_no_read_while_none_waits(pipe):
    """No read of the input but ReadFile, and each ReadFile asks for exactly
    the bytes its ask just found waiting, right after that ask."""
    watched = pipe.watched()
    assert not [call for call in watched if call[0] == "os.read"], watched
    for index, call in enumerate(watched):
        if call[0] == "ReadFile":
            _, handle, size, waiting = call
            assert handle == HANDLE and waiting > 0 and size == waiting, watched
            assert watched[index - 1] == ("peek", HANDLE, 0), watched


def test_on_windows_it_asks_the_pipe_and_reads_nothing_until_the_pipe_breaks(monkeypatch):
    pipe = _Pipe([0, 0, 0, BrokenPipeError(errno.EPIPE, "The pipe has been ended")])
    launcher = _watch(monkeypatch, "win32", pipe)
    poll = launcher.LAUNCHER_POLL_SECONDS
    assert pipe.watched() == [
        ("handle", 0),
        ("peek", HANDLE, 0), ("sleep", poll),
        ("peek", HANDLE, 0), ("sleep", poll),
        ("peek", HANDLE, 0), ("sleep", poll),
        ("peek", HANDLE, 0),
    ], pipe.calls
    _assert_no_read_while_none_waits(pipe)
    _assert_the_stop_path(launcher, pipe)


def test_on_windows_bytes_waiting_are_taken_exactly_and_the_watch_goes_on(monkeypatch):
    """A stray byte is not the end: the watch takes exactly the bytes the
    pipe says wait, by a read that cannot wait for more, and asks again."""
    pipe = _Pipe([0, 3, 0, 1, 4096, BrokenPipeError(errno.EPIPE, "The pipe has been ended")])
    launcher = _watch(monkeypatch, "win32", pipe)
    poll = launcher.LAUNCHER_POLL_SECONDS
    assert pipe.watched() == [
        ("handle", 0),
        ("peek", HANDLE, 0), ("sleep", poll),
        ("peek", HANDLE, 0), ("ReadFile", HANDLE, 3, 3), ("sleep", poll),
        ("peek", HANDLE, 0), ("sleep", poll),
        ("peek", HANDLE, 0), ("ReadFile", HANDLE, 1, 1), ("sleep", poll),
        ("peek", HANDLE, 0), ("ReadFile", HANDLE, 4096, 4096), ("sleep", poll),
        ("peek", HANDLE, 0),
    ], pipe.calls
    _assert_no_read_while_none_waits(pipe)
    _assert_the_stop_path(launcher, pipe)


@pytest.mark.parametrize("pipe", [
    pytest.param(lambda: _Pipe([0, OSError(errno.EINVAL, "The parameter is incorrect")]), id="another-OSError"),
    pytest.param(lambda: _Pipe([PermissionError(errno.EACCES, "Access is denied")]), id="refused"),
    pytest.param(lambda: _Pipe([0, 2], given=b""), id="end-of-input"),
    pytest.param(lambda: _Pipe([], handle_refused=OSError(errno.EBADF, "Bad file descriptor")), id="no-handle"),
    pytest.param(lambda: _Pipe([0, ValueError("not a pipe")]), id="not-an-OSError"),
])
def test_on_windows_every_other_end_takes_the_same_stop_path(monkeypatch, pipe):
    """Any other OSError, the end of input, a handle the descriptor does not
    give, and an ask that fails in a way no OSError says: each is the end,
    taken by the same stop path at once, and the pipe is not asked again (the
    stand-in raises a BaseException if it is)."""
    pipe = pipe()
    launcher = _watch(monkeypatch, "win32", pipe)
    _assert_no_read_while_none_waits(pipe)
    _assert_the_stop_path(launcher, pipe)
    assert not pipe.script, pipe.calls


def test_on_windows_it_waits_the_named_interval_between_asks(monkeypatch):
    """One wait of LAUNCHER_POLL_SECONDS after every ask that is not the
    end, and no ask without one before it but the first: no busy loop. The
    interval is the named one, about half a second."""
    launcher = _load_launcher(monkeypatch)
    assert 0.1 <= launcher.LAUNCHER_POLL_SECONDS <= 1.0
    pipe = _Pipe([0] * 20 + [7, 0, BrokenPipeError(errno.EPIPE, "The pipe has been ended")])
    launcher = _watch(monkeypatch, "win32", pipe)
    watched = pipe.watched()
    asks = [index for index, call in enumerate(watched) if call[0] == "peek"]
    sleeps = [call for call in watched if call[0] == "sleep"]
    assert len(asks) == 23 and len(sleeps) == 22, watched
    assert set(sleeps) == {("sleep", launcher.LAUNCHER_POLL_SECONDS)}, watched
    waited = [("sleep", launcher.LAUNCHER_POLL_SECONDS) in watched[before:after]
              for before, after in zip(asks, asks[1:])]
    assert waited == [True] * 22, watched


def test_on_windows_the_interval_used_is_the_named_one(monkeypatch):
    pipe = _Pipe([0, 0, BrokenPipeError(errno.EPIPE, "The pipe has been ended")])
    _watch(monkeypatch, "win32", pipe, poll=0.25)
    assert [call for call in pipe.watched() if call[0] == "sleep"] == [("sleep", 0.25)] * 2, pipe.calls


def test_on_windows_the_interval_as_windows_loads_it_is_a_polite_one(monkeypatch):
    """The file loaded as Windows loads it, `sys.platform` said to be
    win32 while it runs: the interval it names there is about half a second,
    and the watch it drives sleeps exactly that."""
    _load_launcher(monkeypatch)  # once as it is, so the standard library's own Windows-only imports are made
    real = sys.platform
    sys.platform = "win32"
    try:
        spec = importlib.util.spec_from_file_location("desktop_launcher_loaded_as_windows", LAUNCHER_PATH)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
    finally:
        sys.platform = real
    assert sys.platform != "win32"
    poll = launcher.LAUNCHER_POLL_SECONDS
    assert 0.1 <= poll <= 1.0
    pipe = _Pipe([0, BrokenPipeError(errno.EPIPE, "The pipe has been ended")])
    monkeypatch.setattr(launcher, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(launcher, "os", types.SimpleNamespace(
        read=pipe.read, open=pipe.open, dup2=pipe.dup2, _exit=pipe._exit, devnull="nul", O_WRONLY=1))
    monkeypatch.setattr(launcher, "signal", types.SimpleNamespace(
        raise_signal=pipe.raise_signal, SIGTERM=signal.SIGTERM))
    monkeypatch.setattr(launcher, "time", types.SimpleNamespace(sleep=pipe.sleep))
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(get_osfhandle=pipe.get_osfhandle))
    monkeypatch.setitem(sys.modules, "_winapi", types.SimpleNamespace(
        PeekNamedPipe=pipe.PeekNamedPipe, ReadFile=pipe.ReadFile))
    with pytest.raises(_Exited):
        launcher._stop_when_the_launcher_goes(0)
    assert [call for call in pipe.watched() if call[0] == "sleep"] == [("sleep", poll)], pipe.calls


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_on_macos_and_linux_the_watch_holds_a_read_open_as_before(monkeypatch, platform):
    """Nothing of Windows is asked: the watch reads 4096 bytes at a time
    until the end of input, a stray byte read and passed over."""
    pipe = _Pipe([], reads=[b"x", b""])
    launcher = _watch(monkeypatch, platform, pipe)
    assert pipe.watched() == [("os.read", 0, 4096), ("os.read", 0, 4096)], pipe.calls
    _assert_the_stop_path(launcher, pipe)


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_on_macos_and_linux_an_error_on_the_held_read_takes_the_stop_path(monkeypatch, platform):
    pipe = _Pipe([], reads=[OSError(errno.EIO, "Input/output error")])
    launcher = _watch(monkeypatch, platform, pipe)
    assert pipe.watched() == [("os.read", 0, 4096)], pipe.calls
    _assert_the_stop_path(launcher, pipe)


def test_the_docstring_says_why_windows_polls(monkeypatch):
    launcher = _load_launcher(monkeypatch)
    said = " ".join(launcher._end_with_the_launcher.__doc__.split())
    assert "On Windows a read held open on the pipe stalls the app's own run" in said
    assert "every LAUNCHER_POLL_SECONDS it asks the pipe how many bytes wait" in said


# --- The Windows path on a real pipe ----------------------------------------
#
# A child given a pipe as its input, as the launcher gives it, runs the
# Windows path with msvcrt and _winapi made of this system's own calls: the
# bytes waiting are the pipe's count (FIONREAD), and a pipe with nothing
# waiting whose every writing end has closed is broken, as Windows says it.
# Every take is recorded, with how many bytes waited when it was asked, and
# so is the SIGTERM the stop path raises (the child's output is sent nowhere
# by then).

WINDOWS_ON_A_REAL_PIPE = '''\
import fcntl, importlib.util, os, select, signal, struct, sys, termios, time, types
record = sys.argv[3]

def note(text):
    with open(record, "a") as f:
        f.write(f"{text} {time.monotonic()}\\n")

def peek(handle, size=0):
    waiting = struct.unpack("i", fcntl.ioctl(handle, termios.FIONREAD, bytes(4)))[0]
    if not waiting:
        asked = select.poll()
        asked.register(handle, select.POLLIN)
        if any(event & select.POLLHUP for _, event in asked.poll(0)):
            raise BrokenPipeError(32, "The pipe has been ended")
    return waiting, 0

def read_file(handle, size, overlapped=False):
    waiting = peek(handle)[0]
    taken = os.read(handle, size) if size <= waiting else b""
    note(f"took {len(taken)} of {size} asked with {waiting} waiting")
    return taken, 0

sys.modules["webview"] = types.ModuleType("webview")
spec = importlib.util.spec_from_file_location("desktop_launcher_real_pipe", sys.argv[1])
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
launcher.ORPHAN_WAIT_SECONDS = float(sys.argv[2])
launcher.sys = types.SimpleNamespace(platform="win32")
# Put in place once the launcher and what it imports are loaded: subprocess
# takes a module named msvcrt for Windows itself.
sys.modules["msvcrt"] = types.SimpleNamespace(get_osfhandle=lambda fd: fd)
sys.modules["_winapi"] = types.SimpleNamespace(PeekNamedPipe=peek, ReadFile=read_file)
signal.signal(signal.SIGTERM, lambda number, frame: note("SIGTERM"))
launcher._end_with_the_launcher()
print("up", flush=True)
while True:
    time.sleep(0.05)
'''


def _noted(record, what):
    if not record.exists():
        return []
    return [line.rsplit(" ", 1) for line in record.read_text().splitlines() if line.startswith(what)]


def _until(seconds, found):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if found():
            return True
        time.sleep(0.05)
    return bool(found())


@pytest.mark.parametrize("end", ["closed", "killed"])
def test_on_a_real_pipe_a_stray_byte_is_taken_and_the_launchers_end_seen_within_one_interval(tmp_path, monkeypatch,
                                                                                               end):
    """Bytes written by mistake are taken, exactly as many as wait, and the
    child goes on; the launcher's end, its pipe closed or the process that
    held it killed, is seen within one interval (and a second of the
    machine's own delays), SIGTERM raised, and the child ends by its own end
    ORPHAN_WAIT_SECONDS later."""
    launcher = _load_launcher(monkeypatch)
    poll, wait = launcher.LAUNCHER_POLL_SECONDS, 1.5
    record = tmp_path / "record"
    child = subprocess.Popen([sys.executable, "-c", WINDOWS_ON_A_REAL_PIPE, str(LAUNCHER_PATH), str(wait), str(record)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    holder = None
    try:
        assert child.stdout.readline().split() == [b"up"]
        if end == "killed":
            holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                      pass_fds=[child.stdin.fileno()])
        child.stdin.write(b"xyz")
        child.stdin.flush()
        assert _until(poll + 5, lambda: _noted(record, "took")), "the stray bytes were never taken"
        time.sleep(2 * poll)
        assert child.poll() is None, "a stray byte ended the watch"
        assert [what for what, _ in _noted(record, "took")] == ["took 3 of 3 asked with 3 waiting"]
        assert not _noted(record, "SIGTERM")
        child.stdin.close()
        # Killed: another process holds the pipe's writing end until it is
        # killed outright, and while it holds it the end is not seen.
        early = []
        if holder is not None:
            time.sleep(2 * poll)
            early = [child.poll(), _noted(record, "SIGTERM")]
            holder.kill()
            holder.wait()
        assert early in ([], [None, []]), f"the end seen while another end was open: {early}"
        ended = time.monotonic()
        assert _until(poll + 5, lambda: _noted(record, "SIGTERM")), "the launcher's end was never seen"
        seen = float(_noted(record, "SIGTERM")[0][1]) - ended
        assert seen <= poll + 1.0, f"the end seen {seen:.2f} s after it, more than one interval of {poll} s"
        assert child.wait(timeout=wait + 10) == 1
        assert time.monotonic() - ended >= wait
    finally:
        for proc in (child, holder):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait()
