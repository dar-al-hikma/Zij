"""The stop check's launcher, as it is read before and after it runs its program.

On Linux a child the check has just started can be seen before it runs the
command it was given: its executable is still the check's own interpreter,
and its command line the check's own. The check looks again until the
command line read before a look is no longer its own, within the time it
already allows its launcher to appear, and only then gives up as before. And
every later look at the launch takes each process's latest entry of the
process table, the launcher's among them, so a name read early is corrected,
and a process that runs another program later is named by the one it runs now.

Each case but the last runs the check's own code against a stand-in process
table, the launcher's start a recorder: no process is started. The last
runs the check on the stand-in launcher whose server entry runs another
program once started.
"""
import os
import re
import subprocess
import sys
import threading
import types

import pytest

# _outside: the watch every test here runs under.
from test_stop_check_2026_10_13 import _PASSING, _fake, _module, _outside

CHILD, STAMP = 4242, 777
OWN_LINE = b"/usr/bin/python3\x00stop_check.py\x00--command\x00Zij\x00"
INTERPRETER = os.path.realpath(sys.executable)


class _Table:
    """A process table whose looks are set by the test: each look is a
    command line read for the child, then the table read, and gives the next of
    `looks` (the last again once they run out), each a pair (the child's
    command line, its executable). The check's own process is listed with
    its own command line and this interpreter; `lines=False` makes a table
    that reads no command line, as on Windows."""

    def __init__(self, module, looks=(), lines=True, own=OWN_LINE):
        self.proc, self.looks, self.own, self.taken = module.Proc, list(looks), own, 0
        self.closed = False
        if lines:
            self.command_line = self._command_line

    def _look(self):
        if self.closed:
            raise RuntimeError("looked at after the test's own time limit")
        return self.looks[min(self.taken, len(self.looks) - 1)]

    def _command_line(self, pid):
        return self.own if pid == os.getpid() else self._look()[0]

    def snapshot(self):
        line, exe = self._look()
        self.taken += 1
        return {os.getpid(): self.proc(os.getpid(), 1, INTERPRETER, 1),
                CHILD: self.proc(CHILD, os.getpid(), exe, STAMP)}

    def listening(self, pids):
        return {}

    def kill(self, proc):
        raise AssertionError("nothing is ended here")


class _Started:
    """What `subprocess.Popen` returns here: the child's id, still running."""

    pid, returncode = CHILD, None

    def poll(self):
        return None


def _check(module, tmp_path, monkeypatch, table, reach="5"):
    folder = tmp_path / "download"
    folder.mkdir()
    windows, work = tmp_path / "windows", tmp_path / "work"
    windows.mkdir()
    work.mkdir()
    check = module.Check(module.parse_args(["--work", str(work), "--reach-seconds", reach,
                                            "--stand-in-windows", str(windows), "--folder", str(folder),
                                            "--command", str(folder / "Zij")]))
    check.work, check.processes = str(work), table
    started = []

    def _popen(argv, **kwargs):
        started.append(list(argv))
        return _Started()

    monkeypatch.setattr(module, "subprocess", types.SimpleNamespace(Popen=_popen, DEVNULL=subprocess.DEVNULL))
    monkeypatch.setattr(module, "POLL_SECONDS", 0.01)
    return check, folder, started


@pytest.fixture
def module():
    return _module()


def test_a_launcher_first_seen_as_this_checks_interpreter_is_looked_at_again_and_named_by_its_program(
        module, tmp_path, monkeypatch, capsys):
    table = _Table(module)
    check, folder, started = _check(module, tmp_path, monkeypatch, table)
    zij = str(folder / "Zij")
    table.looks = [(OWN_LINE, INTERPRETER), (OWN_LINE, INTERPRETER), (b"Zij\x00", zij)]
    launch, _ = check.start(1)
    assert started == [[zij]]
    assert table.taken == 3
    assert launch.launcher.pid == CHILD and launch.launcher.exe == zij
    assert capsys.readouterr().out == (f"launch 1: started: the command run with a fresh home and data folder; "
                                       f"launcher Zij ({CHILD})\n")


def test_a_launcher_that_never_runs_its_program_is_given_up_as_one_that_never_appeared(
        module, tmp_path, monkeypatch, capsys):
    """Run under a time limit of the test's own, far past the check's: a
    look that never stops fails here rather than holding the run."""
    table = _Table(module, [(OWN_LINE, INTERPRETER)])
    check, _, _ = _check(module, tmp_path, monkeypatch, table, reach="0.2")
    ended = []

    def _start():
        try:
            check.start(1)
        except BaseException as error:
            ended.append(error)

    looking = threading.Thread(target=_start, daemon=True)
    looking.start()
    looking.join(10)
    still = looking.is_alive()
    table.closed = True                                    # its next look ends it
    looking.join(10)
    assert not still, "still looking 10 s after its start, though it allows 0.2 s"
    [failed] = ended
    assert isinstance(failed, module.CheckFailed), repr(failed)
    assert str(failed) == "launch 1: no launcher process appeared within 0.2 s"
    assert table.taken > 2, "it looked again within the time it allows"
    assert check.current.launcher is None
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("line, exe, lines", [
    (b"Zij\x00", "Zij", True),                                     # the download's program
    (b"/usr/bin/python3\x00desktop_launcher.py\x00", None, True),    # this interpreter, run on the launcher's source
    (b"", "Zij", True),                                            # the program before its arguments are laid out
    (None, "Zij", True),                                           # its command line unreadable
    (OWN_LINE, None, False),                                       # a table that reads no command line
], ids=["program", "same-interpreter", "no-arguments-yet", "unreadable", "no-command-lines"])
def test_a_launcher_whose_look_is_not_this_checks_own_is_taken_at_the_first_look(
        module, tmp_path, monkeypatch, capsys, line, exe, lines):
    table = _Table(module, lines=lines)
    check, folder, _ = _check(module, tmp_path, monkeypatch, table, reach="0.2")
    exe = str(folder / exe) if exe else INTERPRETER
    table.looks = [(line, exe)]
    launch, _ = check.start(1)
    assert table.taken == 1
    assert launch.launcher.exe == exe
    name = "Zij" if exe != INTERPRETER else os.path.basename(INTERPRETER)
    assert capsys.readouterr().out.endswith(f"; launcher {name} ({CHILD})\n")


def test_a_launcher_whose_own_command_line_cannot_be_read_is_taken_at_the_first_look(
        module, tmp_path, monkeypatch, capsys):
    table = _Table(module, own=None)
    check, _, _ = _check(module, tmp_path, monkeypatch, table, reach="0.2")
    table.looks = [(None, INTERPRETER)]
    launch, _ = check.start(1)
    assert table.taken == 1 and launch.launcher.exe == INTERPRETER


def test_each_look_at_the_launch_takes_the_latest_entry_and_names_the_launcher_by_it(module, tmp_path):
    folder = tmp_path / "download"
    folder.mkdir()
    zij = str(folder / "Zij")
    table = _Table(module, [(OWN_LINE, INTERPRETER)])
    launch = module.Launch(table, str(folder), 2)
    launch.popen = _Started()
    launch.adopt(table.snapshot()[CHILD])
    assert launch.name(launch.launcher) == f"{os.path.basename(INTERPRETER)} ({CHILD})"
    table.looks = [(b"Zij\x00", zij)]
    live = launch.live()
    assert set(live) == {CHILD} and live[CHILD].exe == zij
    assert launch.launcher.exe == zij and launch.name(launch.launcher) == f"Zij ({CHILD})"
    assert launch.history().startswith(f"Zij ({CHILD}) [the launcher; parent {os.getpid()}, outside this launch; "
                                       f"seen from "), launch.history()


def test_a_later_process_given_the_launchers_id_is_not_taken_for_it(module, tmp_path):
    folder = tmp_path / "download"
    folder.mkdir()
    table = _Table(module, [(OWN_LINE, INTERPRETER)])
    launch = module.Launch(table, str(folder), 2)
    launch.popen = _Started()
    first = module.Proc(CHILD, os.getpid(), INTERPRETER, STAMP - 1)
    launch.adopt(first)
    table.looks = [(b"Zij\x00", str(folder / "Zij"))]
    live = launch.live()
    assert launch.launcher is first
    assert live[CHILD].stamp == STAMP, "found by its executable inside the download, a process of its own"
    assert launch.sighting(first).ended is not None


def test_a_launcher_whose_executable_cannot_be_read_as_it_ends_keeps_the_name_it_was_read_by(module, tmp_path):
    """A process that is ending is still listed a moment after its memory,
    and so its executable, is gone: that look does not unname it."""
    folder = tmp_path / "download"
    folder.mkdir()
    zij = str(folder / "Zij")
    table = _Table(module, [(b"Zij\x00", zij)])
    launch = module.Launch(table, str(folder), 2)
    launch.popen = _Started()
    launch.adopt(table.snapshot()[CHILD])
    table.looks = [(None, None)]
    live = launch.live()
    assert set(live) == {CHILD} and live[CHILD].exe == zij
    assert launch.name(launch.launcher) == f"Zij ({CHILD})"
    assert launch.history().startswith(f"Zij ({CHILD}) [the launcher; "), launch.history()


def test_a_server_that_runs_another_program_once_started_is_named_by_the_one_it_runs_now(tmp_path):
    """The stand-in's third launch starts the download's program, which then
    runs the interpreter it is given (this one) in its own place: the lines
    that say the server was reached and that it stopped name it by that
    interpreter, by the id it was started with."""
    code, out = _fake(tmp_path, "obeys", bounds=_PASSING)
    assert code == 0, out
    third = [line for line in out.splitlines() if line.startswith("launch 3: ")]
    started = re.search(r"; server \S+ \((\d+)\)$", third[0])
    assert started, out
    now = f"{os.path.basename(os.path.realpath(sys.executable))} ({started.group(1)})"
    [reached] = [line for line in third if line.startswith("launch 3: reached after ")]
    assert re.search(rf"holds 127\.0\.0\.1:\d+ \({re.escape(now)}\) and answered$", reached), out
    [stopped] = [line for line in third if line.startswith("launch 3: stopped as the launcher stops it")]
    assert f"no process of this launch remains (1 seen: {now}) and port " in stopped, out
