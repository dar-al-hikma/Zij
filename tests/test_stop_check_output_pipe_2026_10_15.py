"""The stop check's third launch reads its server's output as it comes.

The launcher gives its server child's output and errors a pipe and reads it
in a thread as it comes. The stop check's third launch does the same: the
server's output and errors a pipe, which a thread of the check copies into a
file as it comes, so the listening mark, the output's last lines and every
failure line read that file as before.

Pinned live: against a stand-in that writes well over what a pipe holds
before it becomes the real server entry run from source, the step passes,
the file holds every byte and the listening mark, and the reader has ended
with its pipe. And where a program outside the launch holds the pipe's
writing end, so that its reader can never reach the pipe's end, the reader
keeps the check from ending neither after a failure nor after a pass.
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time

from conftest import EXECUTABLE_DIR
# _outside: the watch every test here runs under.
from test_stop_check_2026_10_13 import NO_WAY_OUT, SCRIPT, STAND_IN_WEBVIEW, _module, _outside
from test_stop_check_atlas_2026_10_15 import _copy, _stand_in_server, _step

FIXTURES = EXECUTABLE_DIR / "tests" / "fixtures" / "stop_check"
KEY = "Key-Made-For-This-Test_0123456789abcdefABCDEF"


def _loud(tmp_path):
    """A copy of this checkout whose server entry first writes more than a
    pipe holds, then runs the launcher's own."""
    program = _copy(tmp_path)
    (program / "desktop_launcher.py").unlink()
    shutil.copyfile(FIXTURES / "loud_server.py", program / "desktop_launcher.py")
    (program / "server_entry.py").symlink_to(EXECUTABLE_DIR / "desktop_launcher.py")
    return program


def _loud_constants():
    namespace = {}
    exec(compile((FIXTURES / "loud_server.py").read_text(encoding="utf-8"), "loud_server.py", "exec"), namespace)
    return namespace["LOUD_BYTES"], namespace["DONE"]


def test_a_server_that_writes_more_than_a_pipe_holds_before_it_listens_passes(tmp_path, monkeypatch, capsys):
    module, check, short = _step(tmp_path, monkeypatch, _loud(tmp_path))
    monkeypatch.setattr(module, "secrets", type("Secrets", (), {"token_urlsafe": staticmethod(lambda n: KEY)}))
    check.args.reach_seconds = 60
    failure, drained, launch = None, None, None
    try:
        check.typed_place()
        launch = check.current
        [(_, path)] = launch.streams
        with open(path, "rb") as f:
            drained = f.read()
    except module.CheckFailed as error:
        failure = str(error)
        for line in check.explain(check.current):
            module.say(f"  {line}")
        check.current.end_everything()
    finally:
        shutil.rmtree(check.work, ignore_errors=True)
        shutil.rmtree(short, ignore_errors=True)
    out = capsys.readouterr().out
    assert failure is None, out
    third = [line for line in out.splitlines() if line.startswith("launch 3: ")]
    assert len(third) == 8, out
    assert ("with a key of this check's own, its input a pipe only this check holds and its output a pipe it reads "
            "as it comes, as the launcher gives them; server ") in third[0], out
    assert f"offered {module.PLACE_FOUND!r} among its 3 option(s)" in third[4], out
    assert third[7].startswith("launch 3: stopped as the launcher stops it, by the end of its input; "), out
    # Every byte the server wrote, in order, then its listening mark.
    loud, done = _loud_constants()
    port = third[0].split("on 127.0.0.1:", 1)[1].split(" ", 1)[0]
    lines = drained.splitlines()
    assert lines[0] == b"loud: input a pipe, output a pipe", "both streams as the launcher gives them"
    assert len(drained) > loud and lines.index(done) > 1, len(drained)
    assert [int(line.split(b" ", 1)[0]) for line in lines[1:lines.index(done)]] == list(range(lines.index(done) - 1))
    assert f"{module.LISTENING_MARK} {port}".encode("ascii") in lines[lines.index(done):], drained[-2000:]
    assert KEY.encode("ascii") not in drained and KEY not in out
    # The reader has ended with its pipe, and was never one to hold the
    # check open.
    assert launch.drain is not None and launch.drain.daemon and not launch.drain.is_alive()


# A program outside the launch holds the writing end of the server's output
# pipe (opened by its path under /proc), so the check's reader of that pipe
# can never reach its end. The check, in its own process, then ends as it
# would on the runner: after a failure, its explanation and every process
# of the launch ended; after a pass, the step's own end.
_DRIVER = textwrap.dedent('''
    import importlib.util, shutil, subprocess, sys, tempfile, time

    script, program, work, outcome = sys.argv[1:5]
    spec = importlib.util.spec_from_file_location("stop_check", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    check = module.Check(module.parse_args(["--work", work, "--stand-in-windows", work, "--reach-seconds",
                                            "3" if outcome == "fail" else "60", "--command", sys.executable,
                                            program + "/desktop_launcher.py"]))
    check.work, check.current = tempfile.mkdtemp(dir=work), None
    found = module.Check._find_launcher

    def find(self, launch):
        holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                  stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  stdout=open(f"/proc/{launch.popen.pid}/fd/1", "wb"))
        print(f"holder {holder.pid}", flush=True)
        return found(self, launch)

    module.Check._find_launcher = find
    began = time.monotonic()
    try:
        check.typed_place()
        print("passed", flush=True)
    except module.CheckFailed as error:
        print(f"FAILED {error}", flush=True)
        check.explain(check.current)
        check.current.end_everything()
    print(f"step ended after {time.monotonic() - began:.1f} s; reader running {check.current.drain.is_alive()}",
          flush=True)
    shutil.rmtree(check.work, ignore_errors=True)
''')


def _held(tmp_path, program, outcome):
    """The driver's output, and the seconds from its start to its end."""
    driver, work = tmp_path / "driver.py", tmp_path / "work"
    driver.write_text(_DRIVER, encoding="utf-8")
    work.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("STREAMLIT_")}
    env.pop("ZIJ_LAUNCH_KEY", None)
    short = tempfile.mkdtemp(dir="/tmp")
    env.update(NO_WAY_OUT, PYTHONPATH=str(STAND_IN_WEBVIEW), TMPDIR=short)
    began, out = time.monotonic(), ""
    try:
        done = subprocess.run([sys.executable, str(driver), str(SCRIPT), str(program), str(work), outcome],
                              capture_output=True, text=True, env=env, timeout=90)
        out = done.stdout
        assert done.returncode == 0 and done.stderr == "", (done.stdout, done.stderr)
        return out, time.monotonic() - began
    except subprocess.TimeoutExpired as expired:
        out = expired.stdout.decode() if isinstance(expired.stdout, bytes) else (expired.stdout or "")
        raise AssertionError(f"the check did not end with its reader still waiting:\n{out}") from None
    finally:
        for line in out.splitlines():
            if line.startswith("holder "):
                try:
                    os.kill(int(line.split()[1]), signal.SIGKILL)
                except OSError:
                    pass
        shutil.rmtree(short, ignore_errors=True)


def test_a_reader_that_cannot_reach_its_pipes_end_never_holds_the_check_open_after_a_failure(tmp_path, monkeypatch):
    program = _stand_in_server(tmp_path, "mute", monkeypatch)
    out, took = _held(tmp_path, program, "fail")
    assert "FAILED launch 3: the server was not reached on 127.0.0.1:" in out and \
        "within 3 s: it never said it was listening" in out, out
    assert "reader running True" in out, "the pipe was held: the reader was still waiting when the check ended"
    assert took < 60, took


def test_a_reader_that_cannot_reach_its_pipes_end_holds_a_passing_step_no_longer_than_its_bound(tmp_path):
    module = _module()
    out, took = _held(tmp_path, _copy(tmp_path), "pass")
    assert "passed" in out.splitlines(), out
    assert "reader running True" in out, "the pipe was held: the reader was still waiting when the step ended"
    assert took < 60, took
    assert module.DRAIN_SECONDS <= 5
