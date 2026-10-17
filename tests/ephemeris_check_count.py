"""The folder's check, counted by its own calls, for the scripts the import-route
tests hand to a subprocess (test_fm2, test_ls and test_ad's reload and fresh
import routes).

A route that reloads or re-imports ephemeris.py, and the engine after it, is
the folder's module's own route only where ephemeris.py's module code runs
its check of the folder again: the engine's import makes a library call,
which reaches the handle's guard, and the guard does the same work. So each
route's count is taken between its `ephemeris` step and the engine's, and
counts the check's own calls: each start of _ephemeris_folder_is_safe and of
_ephemeris_folder_is_held in ephemeris.py (sys.monitoring's PY_START event;
every other code object is switched off at its first start, so the count
costs the rest of the process nothing). A route whose `ephemeris` step does
not happen, or happens and skips the check, counts none there.

CHECK_COUNT is Python, to be pasted into a script at module level or, indented,
into a function's body: it binds `checked`, {"safe": n, "held": n}, and
`counted()`, a copy of it. Standard library only.
"""
from __future__ import annotations

CHECK_COUNT = r"""
checked = {"safe": 0, "held": 0}
def _check_started(code, offset, _kinds={"_ephemeris_folder_is_safe": "safe", "_ephemeris_folder_is_held": "held"}):
    kind = _kinds.get(code.co_name)
    if kind is None or not code.co_filename.endswith("ephemeris.py"):
        return sys.monitoring.DISABLE
    checked[kind] += 1
def counted():
    return dict(checked)
sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "the folder's check")
sys.monitoring.register_callback(sys.monitoring.PROFILER_ID, sys.monitoring.events.PY_START, _check_started)
sys.monitoring.set_events(sys.monitoring.PROFILER_ID, sys.monitoring.events.PY_START)
"""


def indented(code, by="    "):
    """`code` as the body of a function, indented by `by`."""
    return "\n".join(by + ln if ln.strip() else ln for ln in code.strip("\n").splitlines()) + "\n"
