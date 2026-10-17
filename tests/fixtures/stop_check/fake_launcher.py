"""A stand-in for the desktop launcher, for the stop check's own tests.

    fake_launcher.py MODE             the launcher
    fake_launcher.py --server MODE    its server child, started by the launcher
    fake_launcher.py --successor      what a launcher that hands off starts
    fake_launcher.py MODE --run-streamlit-server PORT
                                      the server entry, whatever MODE: the
                                      real launcher's own, from this checkout

The launcher makes its data folder under XDG_DATA_HOME and its window log
in it, as the real launcher does (one line in it), starts its server child
with the child's input a pipe only the launcher holds, shows a stand-in
window (`<pid>.open` in STAND_IN_WINDOWS) and waits for its close
(`<pid>.close` there). The server answers Streamlit's health check on a
loopback port of its own, and a WebSocket opening of the session's route as
the app's server does: opened (101) under the Host 127.0.0.1, with any port,
sent with no Origin or with the Origin of that Host, and refused (403) under
any other Host or from any other Origin. MODE says how the two behave:

  obeys      the server stops at the end of its input, FAKE_STOP_DELAY
             seconds later (default 0); on the window's close the launcher
             closes that input, waits for the server and exits 0.
  survives   the server never reads its input, and renames itself; on the
             window's close the launcher kills it and exits 0, but a
             launcher ended abruptly leaves it running.
  deaf       the server listens but never answers.
  leaves     the server never reads its input; on the window's close the
             launcher exits 0 and leaves it running.
  no-window  as obeys, but no window is ever shown.
  rebinds    as obeys, but the server opens a WebSocket under any Host.
  any-origin as obeys, but the server opens a WebSocket from any Origin.
  refused-window
             as obeys, but the server's metrics show no media file and no
             result of the engine's, as when its window is refused.

The server's metrics (/_stcore/metrics) show media files and one result of
the engine's, as the app's server's do once its window's session has run
the app, in every mode but refused-window, where they show only the state
of a refused session.
  shut       as obeys, but the server refuses a WebSocket under every Host,
             its window's own too.
  no-log     as obeys, but the launcher makes no window log, as when its
             engine could not be imported.
  log-link   as obeys, but a link to another file of the data folder stands
             at the window log's name.
  log-fifo   as obeys, but a FIFO no program writes to stands at the window
             log's name.
  log-link-to-fifo
             as obeys, but a link to such a FIFO stands there.
  log-folder as obeys, but a folder stands there.
  ends       the launcher writes sixty numbered lines on its standard error
             (its home folder, a launch key, a terminal colour code and an
             over-long line among them) and one on its standard output, and
             exits 3 at once, before it makes its data folder or starts a
             server.
  crashes    the launcher makes its data folder, starts a server that obeys
             (as in obeys), and a moment later exits 9 with no window: the
             server sees the end of its input and stops FAKE_STOP_DELAY
             seconds after.
  hands-off  the launcher starts a successor that shows no window and runs
             on, and exits 0 a moment later, its data folder made; the
             successor ends itself within FAKE_SUCCESSOR_SECONDS (default 30).

crashes and hands-off make an empty window log, as the real launcher does
before its window.

The server entry, which the check starts on its own to type a place in the
app's city search, is the real one: the launcher of this checkout run with
its sentinel and the port by the interpreter FAKE_SERVER_PYTHON names (this
one, a copy of an interpreter, has no Streamlit), with the stand-in
pywebview the launcher imports.
"""
import ctypes
import http.server
import os
import socket
import subprocess
import sys
import threading
import time


def server(mode):
    if mode in ("survives", "leaves"):
        try:
            ctypes.CDLL(None).prctl(15, b"renamed", 0, 0, 0)     # PR_SET_NAME
        except (OSError, AttributeError):
            pass
    if mode == "deaf":
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(16)
        while True:
            time.sleep(60)

    class Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/_stcore/stream" and self.headers.get("Upgrade", "").lower() == "websocket":
                host, origin = self.headers.get("Host", ""), self.headers.get("Origin")
                own_origin = mode == "any-origin" or origin is None or origin == f"http://{host}"
                opened = mode != "shut" and (mode == "rebinds" or host.rpartition(":")[0] == "127.0.0.1" and own_origin)
                self.send_response(101 if opened else 403)
                if opened:
                    self.send_header("Upgrade", "websocket")
                    self.send_header("Connection", "Upgrade")
                else:
                    self.send_header("Content-Length", "0")
                self.end_headers()
                self.close_connection = True
                return
            if self.path == "/_stcore/metrics":
                body = b"active_sessions 1\n" + (
                    b'cache_memory_bytes{cache_type="st_session_state",cache=""} 1\n' if mode == "refused-window" else
                    b'cache_memory_bytes{cache_type="st_cache_data",cache="engine.calculate_prenatal_syzygy"} 593\n'
                    b'cache_memory_bytes{cache_type="st_memory_media_file_storage",cache=""} 1314176\n'
                    b'cache_memory_bytes{cache_type="st_session_state",cache=""} 46\n')
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = b"ok" if self.path == "/_stcore/health" else b"no"
            self.send_response(200 if body == b"ok" else 404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Health)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if mode in ("obeys", "no-window", "rebinds", "shut", "any-origin", "refused-window"):
        while os.read(0, 4096):
            pass
        time.sleep(float(os.environ.get("FAKE_STOP_DELAY", "0")))
        os._exit(0)
    while True:
        time.sleep(60)


def ends():
    home = os.environ["HOME"]
    for n in range(60):
        print(f"line {n}: the home folder {home}", file=sys.stderr)
    print(f"\x1b[31mTraceback: the window at http://127.0.0.1:1/?launch=Fake-Launch-Key_0123456789 failed\x1b[0m",
          file=sys.stderr)
    print("x" * 1000, file=sys.stderr)
    print("the standard output's one line", flush=True)
    sys.stderr.flush()
    os._exit(3)


WINDOW_LOG_NAME = "webview_debug.log"


def data_folder(log=""):
    """The app's data folder, made, with its window log holding `log`
    (None: no window log)."""
    folder = os.path.join(os.environ["XDG_DATA_HOME"], "Zij")
    os.makedirs(folder, exist_ok=True)
    if log is not None:
        with open(os.path.join(folder, WINDOW_LOG_NAME), "a") as f:
            f.write(log)
    return folder


def hands_off():
    data_folder()
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--successor"], stdin=subprocess.DEVNULL)
    time.sleep(1.5)
    os._exit(0)


def successor():
    time.sleep(float(os.environ.get("FAKE_SUCCESSOR_SECONDS", "30")))
    os._exit(0)


def crashes():
    data_folder()
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--server", "obeys"], stdin=subprocess.PIPE)
    time.sleep(1.5)
    os._exit(9)


def launcher(mode):
    if mode == "ends":
        ends()
    if mode == "crashes":
        crashes()
    if mode == "hands-off":
        hands_off()
    log_modes = ("log-link", "log-fifo", "log-link-to-fifo", "log-folder")
    if mode == "log-link":
        folder = data_folder(None)
        with open(os.path.join(folder, "elsewhere.log"), "w") as f:
            f.write("a file the link names\n")
        os.symlink("elsewhere.log", os.path.join(folder, WINDOW_LOG_NAME))
    elif mode in ("log-fifo", "log-link-to-fifo"):
        folder = data_folder(None)
        fifo = os.path.join(folder, WINDOW_LOG_NAME if mode == "log-fifo" else "elsewhere.fifo")
        os.mkfifo(fifo)
        if mode == "log-link-to-fifo":
            os.symlink("elsewhere.fifo", os.path.join(folder, WINDOW_LOG_NAME))
    elif mode == "log-folder":
        os.mkdir(os.path.join(data_folder(None), WINDOW_LOG_NAME))
    else:
        data_folder(None if mode == "no-log" else "pywebview INFO: a line the fake launcher's window log holds\n")
    child = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--server",
                              "obeys" if mode in ("no-log",) + log_modes else mode],
                             stdin=subprocess.PIPE)
    folder, me = os.environ["STAND_IN_WINDOWS"], os.getpid()
    shown, close = os.path.join(folder, f"{me}.open"), os.path.join(folder, f"{me}.close")
    if mode != "no-window":
        open(shown, "w").close()
    while not os.path.exists(close):
        time.sleep(0.05)
    if mode == "survives":
        child.kill()
        child.wait()
    elif mode != "leaves":
        child.stdin.close()
        child.wait()
    if os.path.exists(shown):
        os.remove(shown)
    os._exit(0)


def the_apps_server(port):
    here = os.path.dirname(os.path.abspath(__file__))
    launcher = os.path.normpath(os.path.join(here, "..", "..", "..", "desktop_launcher.py"))
    python = os.environ["FAKE_SERVER_PYTHON"]
    os.execve(python, [python, launcher, "--run-streamlit-server", port],
              dict(os.environ, PYTHONPATH=os.path.join(here, "stand_in")))


if __name__ == "__main__":
    if "--run-streamlit-server" in sys.argv:
        the_apps_server(sys.argv[sys.argv.index("--run-streamlit-server") + 1])
    elif sys.argv[1] == "--server":
        server(sys.argv[2])
    elif sys.argv[1] == "--successor":
        successor()
    else:
        launcher(sys.argv[1])
