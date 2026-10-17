"""
desktop_launcher.py
Packages app.py (Zīj) as a native desktop window
using pywebview, with Streamlit running as a local, headless subprocess.

DEV MODE (no packaging, just testing the desktop shell):
    pip install pywebview
    python desktop_launcher.py

PACKAGED MODE:
    Build with `pyinstaller build.spec`. Must be run separately ON Windows
    (produces a .exe) and ON macOS (produces a .app) -- PyInstaller does not
    cross-compile between platforms. See docs/BUILD_NOTES.md.

HOW THIS WORKS INSIDE A FROZEN (PyInstaller) BUILD:
A frozen build has no separate `python`/`streamlit` binary to shell out to --
the interpreter and this script are merged into one executable. So instead,
this same executable re-invokes ITSELF (via sys.executable, which points at
the frozen exe/app itself once packaged) with a hidden sentinel flag. That
child process detects the flag and runs Streamlit's CLI in-process instead
of opening a window. The parent process waits for that server to come up,
then opens a pywebview window pointed at it.
"""

import os
import sys
import secrets
import signal
import socket
import stat
import subprocess
import time
import threading
import atexit
import logging
import urllib.parse
import webbrowser
import zoneinfo

# Every zone comes from the pinned tzdata package, never the computer's own
# database (the owner's ruling 71): the directories zoneinfo would search
# before the package are dropped before anything in this process makes a
# zone -- the window's, and the Streamlit server's when this program is
# re-invoked as that server. time_zones.py (which the engine imports) and
# app.py do the same themselves.
zoneinfo.reset_tzpath(to=[])
zoneinfo.ZoneInfo.clear_cache()

import webview

# Sentinel argument that tells a re-invocation of this executable to act as
# the Streamlit server rather than opening the desktop window.
_SERVER_SENTINEL = "--run-streamlit-server"

APP_TITLE = "Zīj"

# The window's door (the owner's rulings 150 and 157). Each launch makes a
# secret of its own; the server child is given it in its ENVIRONMENT, never
# on its command line (another account can read a process's command line on
# Linux, but not its environment), and the window opens on a URL that
# carries it as this query parameter. app.py's first act is to stop any
# session that has not shown it. Both names are app.py's too.
LAUNCH_KEY_VARIABLE = "ZIJ_LAUNCH_KEY"
LAUNCH_KEY_PARAMETER = "launch"

# The server's stop (the owner's rulings 140 and 150). The launcher asks its
# server child to stop by closing the child's standard input; the child
# stops as Streamlit stops on SIGTERM. A child still running after
# STOP_WAIT_SECONDS is killed, and reaped within KILL_WAIT_SECONDS. A child
# whose launcher has gone without asking (killed, crashed) sees the same
# end of its input and stops itself, and if it has not ended
# ORPHAN_WAIT_SECONDS later it ends at once, by no signal (the orphan of the
# reproduction ignored SIGTERM).
STOP_WAIT_SECONDS = 10.0
KILL_WAIT_SECONDS = 5.0
ORPHAN_WAIT_SECONDS = 10.0
# On Windows the server child asks its input pipe this often how many bytes
# wait, rather than hold a read open on it (_end_with_the_launcher). It sees
# its launcher's end at most one interval later than a held read would: a
# stop the launcher asks for leaves the server STOP_WAIT_SECONDS less one
# interval to stop as Streamlit stops on SIGTERM, the launcher's own bound
# (STOP_WAIT_SECONDS, then the kill and KILL_WAIT_SECONDS) is unchanged, and
# an orphan ends at most ORPHAN_WAIT_SECONDS and one interval after its
# launcher.
LAUNCHER_POLL_SECONDS = 0.5
# After SIGTERM or SIGHUP the launcher closes its window and ends as a
# program ends, its exit hooks run; if it has not ended this long after, it
# ends at once.
END_WAIT_SECONDS = 10.0

# What the server child writes on its own output, with the port, once its
# server is bound and listening on that port (the owner's ruling 157,
# SA-05). The launcher reads it from the pipe it holds to that child alone,
# so no other process can say it.
SERVER_LISTENING_MARK = "zij-server-listening"

# The window's log, in the app's data folder (ruling 157, SA-12).
WINDOW_LOG_NAME = "webview_debug.log"
WINDOW_SIZE = (1400, 900)
WINDOW_MIN_SIZE = (900, 600)


def _resource_path(relative_path: str) -> str:
    """Resolve a bundled data file's path, both in dev and when frozen by
    PyInstaller (which unpacks --add-data files under sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


def _free_port() -> int:
    """Ask the OS for an unused local port rather than hardcoding one, so a
    port left busy by a leftover process (or a second instance) never
    causes a silent failure."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, proc, listening, timeout: float = 25.0) -> bool:
    """Whether the server at `url` is this launch's own child (the owner's
    ruling 157, SA-05 and D-07): the child `proc` is alive, has said on the
    pipe only it writes to that its server is bound and listening on this
    port (`listening`, set by the launcher's reader of that pipe), and the
    port answers Streamlit's health check. While the child listens there no
    other process can bind the same address and port, so what answers is
    the child. Any HTTP answer alone proves nothing: the port is chosen
    before the child binds it, and another process can bind it first, in
    which case the child exits."""
    import urllib.request
    import urllib.error

    # Straight to the loopback port, never through a proxy from the
    # environment.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if listening.is_set():
            try:
                with opener.open(f"{url}/_stcore/health", timeout=1) as answer:
                    if answer.status == 200 and answer.read(16) == b"ok":
                        return proc.poll() is None
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
        time.sleep(0.25)
    return False


def _server_options(port: str) -> list:
    """Every server option that bears on who can connect, what a client is
    told, or what the server reads or serves, pinned as a flag (the owner's
    ruling 157, SA-13). Streamlit ranks a flag above an environment variable
    and both above a config file, so neither a `.streamlit/config.toml` in
    the home folder or the folder the program is started from nor a
    STREAMLIT_* variable can loosen any of these; the launcher also starts
    its child with no STREAMLIT_* variable at all (_server_environment).

    A frozen build has no .streamlit/config.toml either: build.spec bundles
    app.py, atlas.db and app_icon.ico and nothing else, and Streamlit reads
    project config from the CWD anyway, which is wherever the user launched
    the binary from. So the options the checkout's own config sets for a
    source run (the toolbar, magic) are passed here too, for the packaged
    app's sake."""
    origin = f"http://127.0.0.1:{port}"
    return [
        # Who can connect. Loopback only, on this launch's port, under the
        # literal host the window uses: any other Host header is refused
        # (DNS rebinding, C-05). The origin check stays on, and its lists
        # name only the window's own origin, so neither a foreign page
        # (C-06) nor a configured address or origin list can be let in.
        "--server.address", "127.0.0.1",
        "--server.port", port,
        "--server.allowedHosts", "127.0.0.1",
        "--server.enableCORS", "true",
        "--server.corsAllowedOrigins", origin,
        "--browser.serverAddress", "127.0.0.1",
        "--server.enableXsrfProtection", "true",
        "--server.xsrfCookieSameSite", "lax",
        "--client.allowedOrigins", origin,
        # Plain http at the root, which is what the window opens: a
        # configured certificate or path prefix would only stop the window
        # from finding the app.
        "--server.sslCertFile", "",
        "--server.sslKeyFile", "",
        "--server.baseUrlPath", "",
        # Development and test modes let any origin in and let any client
        # shut the server down.
        "--global.developmentMode", "false",
        "--global.e2eTest", "false",
        # What a client is told. A session that has not shown the launch's
        # secret is stopped before any widget exists, so the full detail of
        # an error reaches only the window; the help links stay as they are.
        "--client.showErrorDetails", "full",
        "--client.showErrorLinks", "auto",
        # The Deploy button and the toolbar are not for a study companion.
        "--client.toolbarMode", "minimal",
        # What the server reads or serves. No source file to watch or
        # reload inside a frozen build, and the watcher can raise errors
        # there; no folder of the program's served as static files (the
        # house-style lane turns static serving on under its own ruling);
        # no route that runs the script outside a session; no usage
        # statistics sent anywhere; no prompt for an e-mail address.
        "--server.headless", "true",
        "--server.showEmailPrompt", "false",
        # A session whose connection is down is kept thirty days, not
        # Streamlit's two minutes: the window's session is let in once,
        # by the secret its first address carried, and the address no
        # longer carries it, so a window that comes back to a session
        # already dropped -- after the computer slept, say -- would be
        # told it is not the window. A session never let in holds one
        # sentence, so keeping it as long costs next to nothing.
        "--server.disconnectedSessionTTL", "2592000",
        "--server.fileWatcherType", "none",
        "--server.runOnSave", "false",
        "--server.allowRunOnSave", "false",
        "--server.enableStaticServing", "false",
        "--server.scriptHealthCheckEnabled", "false",
        "--browser.gatherUsageStats", "false",
        # The script's runner, as the checkout and the suite run it: the
        # app has no bare expression for magic to print.
        "--runner.magicEnabled", "false",
        "--runner.fastReruns", "true",
        "--runner.enforceSerializableSessionState", "false",
        "--runner.enumCoercion", "nameOnly",
    ]


def _server_environment(secret: str) -> dict:
    """The server child's environment: this process's own, less every
    STREAMLIT_* variable, plus this launch's secret."""
    environment = {name: value for name, value in os.environ.items()
                   if not name.upper().startswith("STREAMLIT_")}
    environment[LAUNCH_KEY_VARIABLE] = secret
    return environment


def _run_as_streamlit_server(port: str):
    """Entry point used when this executable is re-invoked with the
    sentinel flag: this process BECOMES the Streamlit server."""
    # The launcher starts this child with no STREAMLIT_* variable; one set
    # some other way is dropped here too, before Streamlit reads any.
    for name in [name for name in os.environ if name.upper().startswith("STREAMLIT_")]:
        del os.environ[name]

    try:
        from streamlit.web import cli as stcli
    except ImportError:
        # Fallback for older Streamlit versions.
        from streamlit import cli as stcli

    app_path = _resource_path("app.py")

    _say_when_listening()
    sys.argv = ["streamlit", "run", app_path, *_server_options(port)]
    sys.exit(stcli.main())


def _say_when_listening():
    """Write SERVER_LISTENING_MARK and the port on this server's output once
    Streamlit is listening on it and will stop on SIGTERM (ruling 157,
    SA-05; ruling 140). Streamlit's bootstrap calls _set_up_signal_handler,
    by its module name, only after its socket is bound and listening; a
    Streamlit that no longer has it stops the child here, and the window
    does not open."""
    from streamlit import config
    from streamlit.web import bootstrap

    set_up = bootstrap._set_up_signal_handler

    def _set_up_signal_handler(server):
        set_up(server)
        print(f"{SERVER_LISTENING_MARK} {config.get_option('server.port')}", flush=True)

    bootstrap._set_up_signal_handler = _set_up_signal_handler


def _end_with_the_launcher():
    """The server child ends with its launcher on every platform (the
    owner's ruling 150, C-11; ruling 140, LS-03). Called first in the child,
    before Streamlit is loaded.

    On Linux the kernel kills the child when the launcher's thread that
    started it ends (PR_SET_PDEATHSIG; the launcher starts it from its main
    thread). Everywhere, the launcher holds the only writing end of the
    child's standard input and never writes to it: when that end closes --
    the launcher asks for a stop, or has ended in any way -- the child stops
    as Streamlit stops on SIGTERM, with its output sent nowhere (a dead
    launcher's pipe can take no more), and if it has not ended
    ORPHAN_WAIT_SECONDS later it ends at once.

    On macOS and Linux a thread holds a read open on the pipe and sees the
    end when that read returns. On Windows a read held open on the pipe
    stalls the app's own run, since other calls on the same pipe wait for
    that read to finish; so there the thread holds none: every
    LAUNCHER_POLL_SECONDS it asks the pipe how many bytes wait, takes just
    those, and sees the end when the pipe says it is broken."""
    if sys.platform.startswith("linux"):
        try:
            import ctypes

            libc = ctypes.CDLL(None, use_errno=True)
            libc.prctl(1, int(signal.SIGKILL), 0, 0, 0)   # PR_SET_PDEATHSIG
        except (OSError, AttributeError):
            pass
    # The descriptor itself, not sys.stdin: a windowed build may give Python
    # no sys.stdin even where the launcher's pipe is there.
    try:
        if not stat.S_ISFIFO(os.fstat(0).st_mode):
            return
    except OSError:
        return
    threading.Thread(target=_stop_when_the_launcher_goes, args=(0,), daemon=True).start()


def _stop_when_the_launcher_goes(fd):
    if sys.platform == "win32":
        _watch_the_pipe_on_windows(fd)
    else:
        try:
            while os.read(fd, 4096):
                pass
        except OSError:
            pass
    try:
        nowhere = os.open(os.devnull, os.O_WRONLY)
        os.dup2(nowhere, 1)
        os.dup2(nowhere, 2)
    except OSError:
        pass
    try:
        signal.raise_signal(signal.SIGTERM)
    except (OSError, ValueError):
        pass
    time.sleep(ORPHAN_WAIT_SECONDS)
    os._exit(1)


def _watch_the_pipe_on_windows(fd):
    """Return once the launcher's end of the pipe on `fd` has closed,
    never leaving a read pending on it: ask how many bytes wait, take just
    those (the launcher writes none, and a stray byte is not the end), and
    wait LAUNCHER_POLL_SECONDS before asking again. A broken pipe, the end
    of input, or anything else the pipe raises is the end: a watch that can
    no longer see its launcher stops the server rather than outlive it."""
    import _winapi
    import msvcrt

    try:
        handle = msvcrt.get_osfhandle(fd)
        while True:
            waiting, _ = _winapi.PeekNamedPipe(handle, 0)
            if waiting:
                taken, _ = _winapi.ReadFile(handle, waiting)
                if not taken:
                    return
            time.sleep(LAUNCHER_POLL_SECONDS)
    except Exception:       # BrokenPipeError among them: the launcher's end closed
        return


def _self_invoke_command(port: str) -> list:
    """Build the command to re-invoke this program as the Streamlit server.

    In a FROZEN build, sys.executable IS this program -- [sys.executable,
    sentinel, port] is correct on its own.

    In DEV mode, sys.executable is just the raw Python interpreter, which
    doesn't know to run this script unless we explicitly pass its path as
    an argument -- omitting that (as an earlier version of this file did)
    causes Python to receive "--run-streamlit-server" as its own argument,
    exit immediately, and the server never starts (surfacing as the
    "did not start within the timeout" error with no visible cause,
    since stdout/stderr were suppressed)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, _SERVER_SENTINEL, port]
    return [sys.executable, os.path.abspath(__file__), _SERVER_SENTINEL, port]


def _start_server(port: str, secret: str) -> subprocess.Popen:
    """Start this launch's server child on `port`, holding `secret` in its
    environment and nowhere on its command line."""
    return subprocess.Popen(
        _self_invoke_command(port),
        env=_server_environment(secret),
        # The child's input is a pipe whose only writing end the launcher
        # holds and never writes to: its end is the child's signal to stop
        # (_end_with_the_launcher).
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


_STOP_LOCK = threading.Lock()


def _stop_server(proc):
    """Stop the server child `proc` and reap it, on every platform (ruling
    140, LS-01): ask by closing its input, wait up to STOP_WAIT_SECONDS for
    it to stop as Streamlit stops on SIGTERM, then kill it and wait up to
    KILL_WAIT_SECONDS for its end (subprocess.TimeoutExpired if even that
    does not end it). Windows has no SIGTERM to send another process --
    Popen.terminate() there ends the child at once, its own cleanup skipped
    -- so the request goes by the pipe on every platform alike. Safe to call
    more than once and from any thread; one stop runs at a time."""
    with _STOP_LOCK:
        if proc.poll() is None:
            _close_quietly(proc.stdin)
            try:
                proc.wait(STOP_WAIT_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(KILL_WAIT_SECONDS)
        _close_quietly(proc.stdin)


def _close_quietly(stream):
    try:
        stream.close()
    except (AttributeError, OSError, ValueError):
        pass


class _StopSignals:
    """SIGTERM and SIGHUP to the launcher become a stop that reaps the
    server child, and then the launcher's end with 128 plus the signal's
    number (the owner's ruling 150, C-11): its window is closed and the
    program ends as a program ends, its exit hooks run (the engine it loaded
    for the data folder removes its temporary folder); before a window
    exists, or END_WAIT_SECONDS after closing it, it ends at once. Python
    runs a signal's handler
    only on the main thread, between steps of Python code, and the window's
    event loop keeps the main thread in native code; so the handler is a
    formality and the signal's number, which Python writes at once to the
    wakeup socket, is read by a thread of its own. A GTK loop puts a wakeup
    socket of its own in place while it runs and wakes for each signal, so
    there the handler runs, and it stops the same way. Made on the main
    thread; `restore` gives back the handlers and the wakeup socket it
    found."""

    NAMES = ("SIGTERM", "SIGHUP")

    def __init__(self):
        self.signals = [getattr(signal, name) for name in self.NAMES if hasattr(signal, name)]
        self.ended = None
        self._ending = threading.Lock()
        self._stop = self._close = None
        self._previous = {}
        self._previous_wakeup = None
        self._reader = self._writer = None
        if threading.current_thread() is not threading.main_thread():
            return
        try:
            self._reader, self._writer = socket.socketpair()
            self._writer.setblocking(False)
            self._previous_wakeup = signal.set_wakeup_fd(self._writer.fileno(), warn_on_full_buffer=False)
            for number in self.signals:
                self._previous[number] = signal.signal(number, self._on_signal)
        except (OSError, ValueError):
            self.restore()

    def watch(self, stop):
        """From now on a stop signal calls `stop` and ends the launcher."""
        self._stop = stop
        if self._reader is not None:
            threading.Thread(target=self._read_wakeups, args=(self._reader,), daemon=True).start()

    def close_with(self, close):
        """From now on a stop signal ends the launcher by `close` (the
        window's), and the end of the window's loop."""
        self._close = close

    def _read_wakeups(self, reader):
        while True:
            try:
                numbers = reader.recv(64)
            except OSError:
                return
            if not numbers:
                return
            for number in numbers:
                if number in self.signals:
                    self._stop_and_end(number)

    def _on_signal(self, number, frame):
        threading.Thread(target=self._stop_and_end, args=(number,)).start()

    def _stop_and_end(self, number):
        with self._ending:
            if self.ended is not None:
                return
            self.ended = number
        close = None
        try:
            if self._stop is not None:
                self._stop()
        finally:
            close = self._close
            if close is not None:
                try:
                    close()
                except Exception:       # a window that cannot be closed: ended at once
                    close = None
            if close is None:
                os._exit(128 + number)
            timer = threading.Timer(END_WAIT_SECONDS, os._exit, args=(128 + number,))
            timer.daemon = True
            timer.start()

    def restore(self):
        for number, handler in self._previous.items():
            try:
                signal.signal(number, handler)
            except (OSError, ValueError, TypeError):
                pass
        self._previous = {}
        if self._writer is not None:
            try:
                # Ours is given back only if it is still the one in place.
                current = signal.set_wakeup_fd(-1)
                if current == self._writer.fileno():
                    current = self._previous_wakeup if self._previous_wakeup is not None else -1
                signal.set_wakeup_fd(current)
            except (OSError, ValueError):
                pass
        for end in (self._reader, self._writer):
            _close_quietly(end)
        self._reader = self._writer = None


class _SecretKeptOut(logging.Formatter):
    """A log line with this launch's secret written over: pywebview may log
    the URL it opens, and that URL carries the secret. `inner`, when given,
    is the handler's own formatter, whose line is the one written over."""

    def __init__(self, secret: str, *args, inner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._secret = secret
        self._inner = inner

    def format(self, record):
        text = self._inner.format(record) if self._inner is not None else super().format(record)
        return text.replace(self._secret, "(withheld)")


def _withhold_the_secret(secret: str):
    """Every handler that can write a log line -- the root logger's, the
    window's log among them, and pywebview's own console handler -- writes
    through a formatter that withholds the secret (SEC1's blind check)."""
    for logger in (logging.getLogger(), logging.getLogger("pywebview")):
        for handler in logger.handlers:
            if not isinstance(handler.formatter, _SecretKeptOut):
                handler.setFormatter(_SecretKeptOut(secret, inner=handler.formatter or logging.Formatter()))


def _window_log_folder():
    """The app's data folder, as the app itself finds and makes it
    (engine.py's own function), or None where it cannot be had: an engine
    that fails at its import with any error included, so that the launcher
    goes on to its window, where the server shows what failed, rather than
    ending before it with no word of its own."""
    folder = os.path.dirname(_resource_path("engine.py"))
    if folder not in sys.path:
        sys.path.append(folder)
    try:
        import engine

        return engine._user_data_dir()
    except Exception:
        return None


def _open_window_log(folder):
    """A handler writing pywebview's diagnostics to WINDOW_LOG_NAME in
    `folder` (ruling 157, SA-12), or None. The file was written beside the
    program, where anyone who could read that folder read it, a link planted
    there was followed, and in a checkout it was a file a commit could take.
    Now: never through a hard link, only as a regular file (on Linux and
    macOS one of this account's, made and kept owner-only), and at INFO --
    DEBUG only when pywebview's own PYWEBVIEW_LOG asks for it. A link at the
    name is refused: on Linux and macOS by the open itself, which does not
    follow one; on Windows only by a look before the open, so a link put at
    the name after that look is followed by the open."""
    if folder is None:
        return None
    path = os.path.join(os.fspath(folder), WINDOW_LOG_NAME)
    try:
        if os.path.islink(path):
            return None
        # O_NONBLOCK: a FIFO planted at the name is refused at once rather
        # than waited on; it changes nothing for a regular file.
        flags = (os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0))
        fd = os.open(path, flags, 0o600)
    except OSError:
        return None
    try:
        seen = os.fstat(fd)
        if (not stat.S_ISREG(seen.st_mode) or seen.st_nlink != 1
                or (hasattr(os, "getuid") and seen.st_uid != os.getuid())):
            os.close(fd)
            return None
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        stream = os.fdopen(fd, "a", encoding="utf-8")
    except OSError:
        os.close(fd)
        return None
    handler = logging.StreamHandler(stream)
    debug = os.environ.get("PYWEBVIEW_LOG", "").strip().lower() == "debug"
    handler.setLevel(logging.DEBUG if debug else logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))
    return handler


# --- The window's doors (the owner's ruling 157, SA-07) ----------------------

_GO, _REFUSE, _GIVE_THE_SECRET = "go", "refuse", "give the secret"


class _WindowRules:
    """Where the window may go. Its main frame stays on the server's origin;
    a frame inside the page may also hold about:, data: or blob: content. A
    new page in the main frame on the server's origin without the secret --
    which the app takes out of the address once the window's session is let
    in -- is given it again: a reload (which Qt reports as a redirect when
    the page's own script asks for it), a step back or forward, a link. The
    app would refuse each as a session that has not shown the secret, and
    the server is this launch's own."""

    def __init__(self, origin_url, secret):
        parts = urllib.parse.urlsplit(origin_url)
        self.origin = (parts.scheme, parts.netloc)
        self.secret = secret

    def verdict(self, url, main_frame):
        """_GO, _REFUSE or _GIVE_THE_SECRET for a navigation to `url`;
        `main_frame` True, False, or None where the backend does not say."""
        parts = urllib.parse.urlsplit(url or "")
        if (parts.scheme, parts.netloc) == self.origin:
            if main_frame is True and not self.carries_the_secret(url):
                return _GIVE_THE_SECRET
            return _GO
        if main_frame is not True and parts.scheme in ("about", "data", "blob"):
            return _GO
        return _REFUSE

    def carries_the_secret(self, url):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url or "").query)
        return self.secret in query.get(LAUNCH_KEY_PARAMETER, [])

    def with_the_secret(self, url):
        parts = urllib.parse.urlsplit(url)
        query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                 if k != LAUNCH_KEY_PARAMETER]
        query.append((LAUNCH_KEY_PARAMETER, self.secret))
        return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _no_bridge(window, func_name, param, value_id):
    """pywebview's bridge from the page to Python, closed: with no js_api it
    still called any callable reachable by attribute from None, and moved
    the window, for any script in the page. This app's pages call none."""
    return None


def _is_https_link(url):
    try:
        parts = urllib.parse.urlsplit(str(url))
    except ValueError:
        return False
    return parts.scheme.lower() == "https" and bool(parts.hostname)


class _OnlyHttpsLinks:
    """Put in pywebview's place of the webbrowser module: a link the page
    opens in a new window goes to the system's browser only when it is an
    https link. On Windows that browser is reached through os.startfile,
    which would otherwise be handed any scheme at all."""

    @staticmethod
    def open(url, new=0, autoraise=True):
        if not _is_https_link(url):
            return False
        return webbrowser.open(str(url), 2, autoraise)

    @staticmethod
    def open_new_tab(url):
        return _OnlyHttpsLinks.open(url, 2)


_FAKE_MEDIA_CONSENT = "--use-fake-ui-for-media-stream"


def _without_fake_media_consent(environ_append):
    """pywebview's Qt window adds a Chromium switch that says yes to every
    camera and microphone request without asking; it is left out."""
    def _append(key, *values, **kwargs):
        environ_append(key, *[v for v in values if v != _FAKE_MEDIA_CONSENT], **kwargs)
    return _append


def _hold_the_qt_window(lib, rules):
    """The Qt (QtWebEngine) window, which the Windows build uses: main-frame
    navigation held to the server's origin before any request leaves, a
    reload given the secret, every permission (camera and microphone among
    them) refused, and the history entry that carried the secret dropped
    once the address no longer does."""
    lib.environ_append = _without_fake_media_consent(lib.environ_append)
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS")
    if flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(f for f in flags.split() if f != _FAKE_MEDIA_CONSENT)
    # pywebview's page class is held in place, its methods given here: it
    # names itself in its own super() call, so a subclass in its place
    # would call its constructor twice. Given before the window makes its
    # page, they are the ones Qt calls.
    page = lib.BrowserView.WebPage
    denied = lib.QWebPage.PermissionPolicy.PermissionDeniedByUser
    QUrl, QTimer = lib.QtCore.QUrl, lib.QtCore.QTimer
    make = page.__init__

    def __init__(self, *args, **kwargs):
        make(self, *args, **kwargs)
        if hasattr(self, "permissionRequested"):
            self.permissionRequested.connect(_refuse_the_permission)
        self.urlChanged.connect(lambda url: _forget_the_secret(self, url))

    def acceptNavigationRequest(self, url, kind, is_main_frame):
        target = url.toString()
        verdict = rules.verdict(target, bool(is_main_frame))
        if verdict == _GO:
            return lib.QWebPage.acceptNavigationRequest(self, url, kind, is_main_frame)
        if verdict == _GIVE_THE_SECRET:
            again = rules.with_the_secret(target)
            QTimer.singleShot(0, lambda: self.setUrl(QUrl(again)))
        return False

    def onFeaturePermissionRequested(self, url, feature):
        self.setFeaturePermission(url, feature, denied)

    def _forget_the_secret(self, url):
        if rules.carries_the_secret(url.toString()):
            return
        history = self.history()
        if any(rules.carries_the_secret(item.url().toString()) for item in history.items()):
            history.clear()

    page.__init__ = __init__
    page.acceptNavigationRequest = acceptNavigationRequest
    page.onFeaturePermissionRequested = onFeaturePermissionRequested


def _refuse_the_permission(permission):
    permission.deny()


def _hold_the_gtk_window(lib, rules):
    """The GTK (WebKitGTK) window, which a source run on Linux uses:
    navigation held to the server's origin, a reload of the page given the
    secret, the camera and microphone switched off and every permission
    refused. WebKitGTK does not say which frame a navigation is for, so
    about:, data: and blob: pass in any frame, and a navigation is taken for
    the main frame's only when it is to the page the window shows."""
    view = lib.BrowserView
    navigate, make = view.on_navigation, view.__init__
    webkit = lib.webkit

    def _bare(url):
        return urllib.parse.urlsplit(url or "")._replace(query="", fragment="")

    def on_navigation(self, webkit_view, decision, decision_type):
        if decision_type == webkit.PolicyDecisionType.NAVIGATION_ACTION:
            target = decision.get_navigation_action().get_request().get_uri()
            this_page = _bare(target) == _bare(webkit_view.get_uri())
            verdict = rules.verdict(target, True if this_page else None)
            if verdict != _GO:
                decision.ignore()
                if verdict == _GIVE_THE_SECRET:
                    webkit_view.load_uri(rules.with_the_secret(target))
                return True
        return navigate(self, webkit_view, decision, decision_type)

    def __init__(self, window):
        make(self, window)
        self.webview.get_settings().props.enable_media_stream = False
        self.webview.connect("permission-request", lambda _view, request: request.deny() or True)

    view.on_navigation = on_navigation
    view.__init__ = __init__


def _hold_the_backend(lib, rules):
    """Close the doors of whichever pywebview backend has just been loaded:
    no bridge, new windows only for https links in the system's browser,
    and the backend's own navigation and permission rules where it has a
    place to hold them (Qt, GTK). A backend whose names have moved fails
    here, and the window does not open."""
    if hasattr(lib, "js_bridge_call"):
        lib.js_bridge_call = _no_bridge
    if hasattr(lib, "webbrowser"):
        lib.webbrowser = _OnlyHttpsLinks
    backend = getattr(lib, "__name__", "").rsplit(".", 1)[-1]
    if backend == "qt" and getattr(lib, "is_webengine", False):
        _hold_the_qt_window(lib, rules)
    elif backend == "gtk":
        _hold_the_gtk_window(lib, rules)


def _close_the_windows_doors(rules):
    """Before webview.start: its bridge closed in pywebview's own module,
    and each backend held as it is loaded (webview.start loads it through
    webview.initialize)."""
    util = getattr(webview, "util", None)
    if util is not None and hasattr(util, "js_bridge_call"):
        util.js_bridge_call = _no_bridge
    initialize = getattr(webview, "initialize", None)
    if initialize is None or getattr(initialize, "_zij_held", False):
        return

    def _initialize(*args, **kwargs):
        lib = initialize(*args, **kwargs)
        _hold_the_backend(lib, rules)
        return lib

    _initialize._zij_held = True
    webview.initialize = _initialize


def _keep_to_the_server(window, rules, home):
    """After each page load, on any backend: a main frame that has left the
    server's origin is sent back to it. The backends held above refuse such
    a load before it starts; this catches it on one that has no place to
    hold it (macOS's WebKit)."""
    def _loaded():
        try:
            url = window.get_current_url()
        except Exception:               # a window already closing
            return
        if url and rules.verdict(url, True) == _REFUSE:
            window.load_url(home)
    return _loaded


def _set_windows_dpi_awareness():
    """Tell Windows this process handles its own per-monitor DPI scaling.

    Without this, an unaware process gets DPI-virtualized by Windows: it
    thinks it's drawing at the requested size/position, but Windows silently
    bitmap-scales the actual window to compensate for display scaling. The
    visible symptom is a window that renders larger than the screen and
    offset away from where Qt's own centering logic (platforms/qt.py, which
    positions purely from QScreen geometry) placed it -- often far enough
    up and to the right that the title bar is unreachable. Must run before
    any window is created, so this is called first thing in
    _launch_desktop_window(), before pywebview/Qt touches anything."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # Vista+ fallback: system DPI only
        except (AttributeError, OSError):
            pass


def _fit_window_to_screen(window):
    """Re-size/re-center the window against the real detected screen,
    rather than trusting the hardcoded WINDOW_SIZE default and pywebview's
    own centering -- both of which assume the screen is at least as big as
    the requested window. That assumption breaks down at high DPI scale
    factors: window sizing/positioning all operates in DPI-independent
    ("logical") pixels, and logical screen resolution shrinks as the scale
    factor climbs -- e.g. a 3840x2400 panel at 300% scaling has only
    ~1280x800 logical pixels to lay out in, well under the 1400x900
    default. That alone explains an oversized window; on top of it, once
    the requested size exceeds the real screen, pywebview's own
    self.screen.center() - self.rect().center() centering math (in
    pywebview's platforms/qt.py) goes askew too, which is consistent with
    reports of the window landing in a corner instead of centered even at
    a scale factor where the size itself came out fine.

    Runs as webview.start()'s func= callback, which pywebview invokes on a
    background thread once the event loop -- and with it, the real Qt
    backend and its screen info -- is actually up. window.resize()/.move()
    are both decorated to block until the window's 'shown' event fires, so
    this only ever runs once there's a real window to measure against."""
    try:
        screen = webview.screens[0]
        margin = 0.9  # leave a little breathing room, not edge-to-edge
        width = max(WINDOW_MIN_SIZE[0], min(WINDOW_SIZE[0], int(screen.width * margin)))
        height = max(WINDOW_MIN_SIZE[1], min(WINDOW_SIZE[1], int(screen.height * margin)))
        x = screen.x + (screen.width - width) // 2
        y = screen.y + (screen.height - height) // 2
        window.resize(width, height)
        window.move(x, y)
    except Exception:
        logging.exception("Failed to fit window to detected screen size")


def _launch_desktop_window():
    """Normal entry point: spawn a private Streamlit server (by
    re-invoking this executable with the sentinel flag) and point a native
    pywebview window at it. The server is stopped and reaped however this
    ends: the window closed, macOS's Quit (which asks the window's closing
    event first), an error, SIGTERM or SIGHUP (_StopSignals), or this
    process's exit."""
    _set_windows_dpi_awareness()
    stop_signals = _StopSignals()
    try:
        _run_the_window(stop_signals)
    except Exception:
        if stop_signals.ended is None:
            raise
    finally:
        stop_signals.restore()
    if stop_signals.ended is not None:
        raise SystemExit(128 + stop_signals.ended)


def _run_the_window(stop_signals):
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    # This launch's secret (the owner's ruling 150): the window's URL
    # carries it, and the server child holds it in its environment.
    secret = secrets.token_urlsafe(32)
    window_url = f"{url}/?{LAUNCH_KEY_PARAMETER}={secret}"

    # Started from the main thread: on Linux the child's death signal is
    # tied to the thread that started it (_end_with_the_launcher).
    proc = _start_server(str(port), secret)
    stopping = threading.Event()

    def stop():
        stopping.set()
        _stop_server(proc)

    atexit.register(stop)
    stop_signals.watch(stop)
    try:
        # Read the child's output in the background instead of DEVNULL-ing
        # it, so a failure can be diagnosed immediately without editing this
        # file; the child's word that its server is listening comes this way.
        captured_lines = []
        listening = threading.Event()
        windows = []
        mark = f"{SERVER_LISTENING_MARK} {port}"

        def _drain_output():
            for line in proc.stdout:
                line = line.rstrip()
                if line == mark:
                    listening.set()
                captured_lines.append(line)
            # The server has gone without being asked: the window is closed
            # too, so that it does not reconnect to whatever takes the port.
            if not stopping.is_set():
                for window in windows:
                    window.destroy()

        reader_thread = threading.Thread(target=_drain_output, daemon=True)
        reader_thread.start()

        # pywebview's own diagnostics go to a log in the data folder (with
        # console=False, a windowed build, there is no stdout or stderr, so
        # without it pywebview's logger.exception(...) calls when a backend
        # fails to load would be silently discarded).
        handler = _open_window_log(_window_log_folder())
        if handler is not None:
            root = logging.getLogger()
            root.addHandler(handler)
            if root.level > handler.level or root.level == logging.NOTSET:
                root.setLevel(handler.level)
        # Whatever is logged, the secret is not written.
        _withhold_the_secret(secret)

        if not _wait_for_server(url, proc, listening):
            stop()
            reader_thread.join(timeout=2)
            server_output = "\n".join(captured_lines) or "(no output captured -- the process may have exited instantly)"
            raise RuntimeError(
                "The local Streamlit server did not start within the timeout, or what answered on its port "
                "was not this launch's own server.\n"
                "--- Captured server output ---\n"
                f"{server_output}\n"
                "-------------------------------"
            )

        rules = _WindowRules(url, secret)
        _close_the_windows_doors(rules)
        # No js_api and nothing exposed: the page has no way into Python.
        window = webview.create_window(
            APP_TITLE, window_url,
            width=WINDOW_SIZE[0], height=WINDOW_SIZE[1],
            min_size=WINDOW_MIN_SIZE,
        )
        windows.append(window)
        stop_signals.close_with(window.destroy)
        window.events.loaded += _keep_to_the_server(window, rules, window_url)
        # macOS's Quit asks each window's closing event before it ends the
        # program, which may then end without returning here: the server is
        # stopped first (ruling 140, LS-03).
        window.events.closing += stop

        icon_path = _resource_path("app_icon.ico")
        if not os.path.isfile(icon_path):
            icon_path = None

        if sys.platform == "win32":
            # pywebview's legacy WinForms + Internet Explorer/MSHTML renderer is
            # meant purely as a last-resort fallback -- but on any modern
            # Windows install with no IE registry traces left, it crashes with
            # an uncaught FileNotFoundError instead of failing gracefully.
            # pywebview's own changelog documents that forcing a specific gui
            # (Qt here) does NOT prevent this fallback if that backend fails to
            # load for any reason -- it still falls through to WinForms.
            # Disable that fallback candidate as a safety net so a genuine Qt
            # failure surfaces as a clean WebViewException instead of that
            # crash. This is defensive only, not load-bearing for the normal
            # case (Qt/PySide6 succeeds on the first try and never reaches this
            # code path at all) -- so if pywebview's internals aren't reachable
            # this way in a given frozen build, skip the patch rather than let
            # it crash the app over what was only ever meant to be a safety net.
            try:
                import webview.guilib as _guilib
                _guilib.import_winforms = lambda: False
            except (ImportError, AttributeError):
                pass

        # Force the Qt (PySide6/QtWebEngine) backend on Windows. Unlike the
        # WebView2/EdgeChromium backend this replaced, PySide6 bundles its own
        # complete Chromium build in the pip wheel itself -- no external
        # runtime to install, detect, or bundle separately.
        gui_backend = "qt" if sys.platform == "win32" else None
        webview.start(_fit_window_to_screen, window, gui=gui_backend, icon=icon_path)
    finally:
        # Window closed, or anything else -> stop and reap the server.
        stop()


if __name__ == "__main__":
    if _SERVER_SENTINEL in sys.argv:
        _end_with_the_launcher()
        _run_as_streamlit_server(sys.argv[sys.argv.index(_SERVER_SENTINEL) + 1])
    else:
        _launch_desktop_window()
