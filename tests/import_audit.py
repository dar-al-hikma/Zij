"""The import audit's driver: run in a fresh interpreter, it installs an
audit hook before the program's first import and starts the program as far
as a test can, then writes what it saw as JSON.

    python tests/import_audit.py ROOT OUT [PAGE ...]

ROOT is the tree whose program is started; OUT the JSON written. The start:
desktop_launcher.py imported (the frozen app's entry; a stand-in takes the
place of its window library, which the suite does not install, and nothing
of it is run), then app.py through Streamlit's AppTest once for each PAGE
(app.py's `from engine import *` loads the engine and the modules split out
of it, by the program's own route); with no PAGE, the engine is imported
in place of the pages. The caller gives HOME, XDG_DATA_HOME, APPDATA and
TMPDIR, each under a scratch folder of its own.

Recorded: every `import` event (a module loaded for the first time); every
file opened for code under ROOT (`open` events, which the loader's
io.open_code raises too); and every `exec` and `compile` event with the
frame that made the call -- the code that called exec(), eval() or
compile(), whose own file says whose call it is (the import machinery's,
Streamlit's script runner's, a library's, or a module of ROOT's). The
standard library only, beside what the program itself imports.
"""
import sys

_SEEN = {"imports": [], "opened": [], "runs": [], "before": None}
_INTERESTING = frozenset({"import", "open", "exec", "compile"})


def _hook(event, args):
    if event not in _INTERESTING:
        return
    if event == "import":
        _SEEN["imports"].append(args[0])
    elif event == "open":
        path = args[0]
        if isinstance(path, bytes):
            path = path.decode("utf-8", "surrogateescape")
        if isinstance(path, str) and path.endswith((".py", ".pyc")):
            _SEEN["opened"].append(path)
    else:
        frame = sys._getframe(1)
        code = args[0] if event == "exec" else None
        _SEEN["runs"].append({"event": event, "caller": frame.f_code.co_filename, "line": frame.f_lineno,
                              "code": getattr(code, "co_filename", None) if code is not None else
                              (args[1] if isinstance(args[1], str) else repr(args[1]))})


sys.addaudithook(_hook)
_SEEN["before"] = sorted(sys.modules)


def main(argv):
    import json
    import os
    import types
    from pathlib import Path

    root, out, pages = Path(argv[1]).resolve(), Path(argv[2]), argv[3:]
    sys.path[:] = [str(root)] + [p for p in sys.path if Path(p or ".").resolve() != Path(__file__).resolve().parent]
    os.chdir(root)
    stand_in = types.ModuleType("webview")      # the window library: the launcher only names it at import
    sys.modules["webview"] = stand_in
    outcome = {"launcher": None, "pages": {}}
    try:
        import desktop_launcher  # noqa: F401
        outcome["launcher"] = "imported"
    except BaseException as exc:                 # noqa: BLE001 -- reported, and the test fails on it
        outcome["launcher"] = repr(exc)
    if not pages:
        import engine  # noqa: F401
    else:
        from streamlit import config
        from streamlit.testing.v1 import AppTest
        from streamlit.util import calc_hash
        from datetime import time

        config.set_option("runner.magicEnabled", False)     # as the app's own .streamlit/config.toml
        for page in pages:
            at = AppTest.from_file(str(root / "app.py"), default_timeout=300)
            at.session_state["manual_coords_key"] = True
            at.session_state["manual_lat_key"] = 43.7792
            at.session_state["manual_lon_key"] = 11.2463
            at.session_state["date_input_key"] = "1240-05-23"
            at.session_state["time_input_key"] = time(14, 30)
            at._page_hash = calc_hash(page)
            at.run()
            outcome["pages"][page] = {"exceptions": [e.value for e in at.exception],
                                      "elements": sum(1 for node in at.main if node is not at.main)}
    modules = {}
    imported = set(_SEEN["imports"])
    for name, loaded in list(sys.modules.items()):
        where = getattr(loaded, "__file__", None)
        if name in imported and where:
            modules[name] = os.path.realpath(where)
    out.write_text(json.dumps({**_SEEN, "modules": modules, "outcome": outcome, "root": str(root)}),
                   encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
