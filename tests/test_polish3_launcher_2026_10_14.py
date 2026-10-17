"""The desktop launcher goes on to its window when the engine fails at its import.

The launcher imports the engine for one thing: the data folder its window log
is written in. An engine that fails at its import -- an attribute a platform
lacks, a value error, a file that does not parse -- leaves no window log, and
the launcher goes on to its window as it does when the folder cannot be had;
the server, which imports the engine for each page, shows there what failed.
Before, an error of any kind but three ended the launcher before its window,
with no word of its own. An interruption (BaseException) is not swallowed.

The engine here is a stand-in module first on the import path; pywebview is
a stand-in that records the window; the server child is a stand-in object, so
no process is started and none is ended.
"""
import importlib.util
import io
import logging
import sys
import types

import pytest

from conftest import EXECUTABLE_DIR

LAUNCHER_PATH = EXECUTABLE_DIR / "desktop_launcher.py"

BROKEN = {
    "AttributeError": "import errno\nerrno.NO_SUCH_NAME_HERE\n",
    "ValueError": "raise ValueError('a table that does not hold together')\n",
    "SyntaxError": "def broken(:\n",
}


@pytest.fixture(autouse=True)
def _log_formatters_kept(monkeypatch):
    """The launcher puts a formatter on every root and pywebview handler;
    those of the test run's own are given back after each test."""
    for name in (None, "pywebview"):
        for handler in logging.getLogger(name).handlers:
            monkeypatch.setattr(handler, "formatter", handler.formatter)


def _load_launcher(monkeypatch, webview_module=None):
    monkeypatch.setitem(sys.modules, "webview", webview_module or types.ModuleType("webview"))
    spec = importlib.util.spec_from_file_location("desktop_launcher_polish3", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _broken_engine(tmp_path, monkeypatch, source):
    """An `engine` module first on the import path whose import runs
    `source`; the real one, if loaded, is put back after the test."""
    folder = tmp_path / "broken-engine"
    folder.mkdir()
    (folder / "engine.py").write_text(source, encoding="utf-8")
    monkeypatch.delitem(sys.modules, "engine", raising=False)
    monkeypatch.syspath_prepend(str(folder))
    return folder


@pytest.mark.parametrize("error", sorted(BROKEN))
def test_an_engine_that_fails_at_its_import_leaves_no_window_log_and_says_nothing(tmp_path, monkeypatch, capsys,
                                                                                 caplog, error):
    launcher = _load_launcher(monkeypatch)
    folder = _broken_engine(tmp_path, monkeypatch, BROKEN[error])
    with pytest.raises(BaseException) as raised:
        import engine  # noqa: F401
    assert type(raised.value).__name__ == error, "premise: the stand-in fails as named"
    caplog.set_level(logging.DEBUG)
    assert launcher._window_log_folder() is None
    assert launcher._open_window_log(launcher._window_log_folder()) is None
    out, err = capsys.readouterr()
    assert out == "" and err == "", (out, err)
    said = " ".join(record.getMessage() for record in caplog.records)
    assert str(folder) not in said and error not in said, said


def test_an_interruption_at_the_engines_import_is_not_swallowed(tmp_path, monkeypatch):
    launcher = _load_launcher(monkeypatch)
    _broken_engine(tmp_path, monkeypatch, "raise KeyboardInterrupt\n")
    with pytest.raises(KeyboardInterrupt):
        launcher._window_log_folder()


class _Child:
    """The server child, stood in for: it says nothing on its output, stops
    when its input is closed, and is never killed."""

    pid = 0

    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = iter(())

    def poll(self):
        return 0 if self.stdin.closed else None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        raise AssertionError("the stand-in child was to be stopped by its input, not killed")


def _window_stand_in(seen):
    webview = types.ModuleType("webview")

    class _Hooks(list):
        def __iadd__(self, hook):
            self.append(hook)
            return self

    def create_window(title, url, **options):
        seen.append(("window", url))
        return types.SimpleNamespace(events=types.SimpleNamespace(loaded=_Hooks(), closing=_Hooks()),
                                     destroy=lambda: seen.append(("destroyed",)))

    def start(*args, **kwargs):
        seen.append(("started",))

    webview.create_window, webview.start = create_window, start
    return webview


@pytest.mark.parametrize("error", sorted(BROKEN))
def test_with_a_broken_engine_the_launcher_goes_on_to_its_window(tmp_path, monkeypatch, capsys, error):
    seen, folders, children = [], [], []
    launcher = _load_launcher(monkeypatch, _window_stand_in(seen))
    _broken_engine(tmp_path, monkeypatch, BROKEN[error])
    open_window_log = launcher._open_window_log

    def _open(folder):
        folders.append(folder)
        return open_window_log(folder)

    def _start(port, secret):
        children.append(_Child())
        return children[-1]

    monkeypatch.setattr(launcher, "_open_window_log", _open)
    monkeypatch.setattr(launcher, "_free_port", lambda: 8599)
    monkeypatch.setattr(launcher, "_start_server", _start)
    monkeypatch.setattr(launcher, "_wait_for_server", lambda url, proc, listening: True)
    monkeypatch.setattr(launcher.atexit, "register", lambda *args, **kwargs: None)
    launcher._launch_desktop_window()
    assert folders == [None], "no window log: the data folder could not be had"
    windows = [entry for entry in seen if entry[0] == "window"]
    assert len(windows) == 1 and windows[0][1].startswith("http://127.0.0.1:8599/?launch="), seen
    assert ("started",) in seen, "the window's loop ran"
    assert len(children) == 1 and children[0].stdin.closed, "the server was stopped by its input"
    out, err = capsys.readouterr()
    assert out == "" and err == "", (out, err)
