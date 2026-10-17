"""Run the app from source, behind the desktop app's door.

    python run_source.py

starts the app's server on this computer only, on a free port, with a key
made for this run alone, and prints the one address that carries the key:
open it in a browser. A session that has not shown the key is told one
sentence and stopped before any saved chart or preference is read (app.py,
_admit_only_the_window), as the desktop app's window is kept. The key is
held in the server's environment, never on a command line, in a file or in
a log, and it is not opened in a browser for you: a browser started with
an address has it on its command line, where another account can read it.
Ctrl-C stops the run, and the server with it.

``streamlit run app.py`` stays a developer's command. It has no key, so
any program on this computer can open the app there.

Only the standard library is used here; the desktop launcher is not
imported (it needs pywebview), and the server options that bear on who can
connect are its own, repeated.
"""
import os
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
# app.py's names, and the desktop launcher's.
LAUNCH_KEY_VARIABLE = "ZIJ_LAUNCH_KEY"
LAUNCH_KEY_PARAMETER = "launch"
# The server child is this script, started again with this argument.
SERVE = "--serve"
# What the server child writes, with its port, once its server is bound
# and listening there: only after that is the address printed, so that it
# is never sent to another program that took the port first.
LISTENING_MARK = "run-source-listening"
STOP_WAIT_SECONDS = 10.0


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _server_options(port):
    """The desktop launcher's server options that bear on who can connect
    and what the printed address reaches, as flags, which no config file
    or STREAMLIT_* variable can override. The rest are read as Streamlit
    reads them, the checkout's .streamlit/config.toml among them (the
    server is started in the checkout)."""
    origin = f"http://127.0.0.1:{port}"
    return [
        "--server.address", "127.0.0.1",
        "--server.port", str(port),
        "--server.allowedHosts", "127.0.0.1",
        "--server.enableCORS", "true",
        "--server.corsAllowedOrigins", origin,
        "--browser.serverAddress", "127.0.0.1",
        "--server.enableXsrfProtection", "true",
        "--server.xsrfCookieSameSite", "lax",
        "--client.allowedOrigins", origin,
        "--server.sslCertFile", "",
        "--server.sslKeyFile", "",
        "--server.baseUrlPath", "",
        "--global.developmentMode", "false",
        "--global.e2eTest", "false",
        "--server.enableStaticServing", "false",
        "--server.scriptHealthCheckEnabled", "false",
        "--browser.gatherUsageStats", "false",
        # No browser opened, and no address printed, by Streamlit: neither
        # would carry the key.
        "--server.headless", "true",
        "--server.showEmailPrompt", "false",
        "--logger.hideWelcomeMessage", "true",
        # A session let in by the key keeps it while its connection is
        # down (the computer slept), as the desktop window's does.
        "--server.disconnectedSessionTTL", "2592000",
    ]


def _stop_with_the_runner():
    """In the server child, outside Windows: when this script's end of the
    child's input closes (the script stopped, or ended in any way), stop as
    Streamlit stops on SIGTERM, and end at once if that has not ended it.
    On Windows a read held open on the pipe would stall the app, so none is
    held there; the script stops the child itself."""
    def watch():
        try:
            while os.read(0, 4096):
                pass
        except OSError:
            pass
        nowhere = os.open(os.devnull, os.O_WRONLY)
        os.dup2(nowhere, 1)
        os.dup2(nowhere, 2)
        signal.raise_signal(signal.SIGTERM)
        time.sleep(STOP_WAIT_SECONDS)
        os._exit(1)

    threading.Thread(target=watch, daemon=True).start()


def _serve(port):
    """The server child: ``streamlit run app.py`` with the options above."""
    if sys.platform != "win32":
        _stop_with_the_runner()
    from streamlit.web import bootstrap, cli

    # Streamlit calls this once its socket is bound and listening.
    set_up = bootstrap._set_up_signal_handler

    def say_when_listening(server):
        set_up(server)
        print(f"{LISTENING_MARK} {port}", flush=True)

    bootstrap._set_up_signal_handler = say_when_listening
    sys.argv = ["streamlit", "run", os.path.join(HERE, "app.py"), *_server_options(port)]
    sys.exit(cli.main())


def _stop(proc):
    if proc.poll() is None:
        proc.stdin.close()
        if sys.platform == "win32":
            proc.terminate()
        try:
            proc.wait(STOP_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    proc.stdin.close()
    proc.stdout.close()


def _end(number, frame):
    raise SystemExit(128 + number)


def main():
    port = _free_port()
    key = secrets.token_urlsafe(32)
    environment = {name: value for name, value in os.environ.items()
                   if not name.upper().startswith("STREAMLIT_")}
    environment[LAUNCH_KEY_VARIABLE] = key
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _end)
    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), SERVE, str(port)], cwd=HERE, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1)
        address = None
        for line in proc.stdout:
            if address is None and line.rstrip("\r\n") == f"{LISTENING_MARK} {port}":
                query = urllib.parse.urlencode({LAUNCH_KEY_PARAMETER: key})
                address = f"http://127.0.0.1:{port}/?{query}"
                print(f"\n  Open the app at {address}\n  Ctrl-C stops it.\n", flush=True)
                continue
            sys.stdout.write(line)
            sys.stdout.flush()
        code = proc.wait()
        if address is None:
            print("The app's server stopped before it was ready.", file=sys.stderr)
        return code or (0 if address else 1)
    except KeyboardInterrupt:
        return 130
    finally:
        if proc is not None:
            _stop(proc)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == SERVE:
        _serve(sys.argv[2])
    elif len(sys.argv) > 1:
        sys.exit("run_source.py takes no arguments.")
    else:
        sys.exit(main())
