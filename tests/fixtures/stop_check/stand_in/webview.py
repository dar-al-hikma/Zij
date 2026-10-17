"""A stand-in for pywebview, for running the real desktop launcher from
source under the stop check: its window is `<pid>.open` in STAND_IN_WINDOWS,
closed when `<pid>.close` appears there, which fires the window's closing
event as a real window's close does, before `start` returns.

With STAND_IN_LOADS_THE_PAGE=1 the window also loads its page as a real
one does: a session opened as a browser opens one, under the window's own
address, its first run asked with the window's address's query (the key
and all), held open until the window closes. The session is the stop
check's own client, loaded from the script."""
import importlib.util
import os
import threading
import urllib.parse

_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", ".github", "scripts",
                       "stop_check.py")


def _load_the_page(window):
    spec = importlib.util.spec_from_file_location("stand_in_browser", _SCRIPT)
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    parts = urllib.parse.urlsplit(window.url)
    session = client.Session(parts.port)
    try:
        session.open()
        session.run(client.rerun_message(parts.query), 120)
        window.closed.wait()
    except Exception:
        pass
    finally:
        session.close()


class _Hooks(list):
    def __iadd__(self, hook):
        self.append(hook)
        return self


class _Screen:
    x = y = 0
    width, height = 1920, 1080


screens = [_Screen()]


class _Window:
    def __init__(self, url):
        self.url = url
        self.events = type("Events", (), {})()
        self.events.loaded, self.events.closing = _Hooks(), _Hooks()
        self.closed = threading.Event()

    def destroy(self):
        self.closed.set()

    def get_current_url(self):
        return self.url

    def load_url(self, url):
        self.url = url

    def resize(self, width, height):
        pass

    def move(self, x, y):
        pass


def create_window(title, url, **options):
    return _Window(url)


def start(func=None, window=None, **options):
    folder, me = os.environ["STAND_IN_WINDOWS"], os.getpid()
    shown, close = os.path.join(folder, f"{me}.open"), os.path.join(folder, f"{me}.close")
    if func is not None:
        threading.Thread(target=func, args=(window,), daemon=True).start()
    open(shown, "w").close()
    if os.environ.get("STAND_IN_LOADS_THE_PAGE") == "1":
        threading.Thread(target=_load_the_page, args=(window,), daemon=True).start()
    try:
        while not window.closed.is_set() and not os.path.exists(close):
            window.closed.wait(0.05)
        if not window.closed.is_set():
            for hook in list(window.events.closing):
                hook()
    finally:
        os.remove(shown)
