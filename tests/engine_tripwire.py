"""The tripwire's judgement: what the run saw done to the engine's namespace,
judged by the rules the split guard applies to what it reads.

The tripwire itself is in tests/conftest.py: while the suite runs, every
change to the watched namespaces of the engine and of the modules split out
of it is seen as it is made, by any route, with the site that made it (a file
under tests/ and its line, or the running test's own function where no frame
of tests/ is on the stack: a decorator's patch); a change made from a program
file or the import machinery is the program's, and not judged, whatever code
it runs (code compiled under a program file's name, or a writer a test hands to
a program function). An engine imported afresh within a test is watched only
from the next test's start.
The process that started the
run hands everything its tests' reports carried to judge() here, once, at
the run's end.

The rules, as tests/test_split_astro_2026_10_14.py states them for the
census's sites:

* a replacement of engine.X, where X is a name a split-out module binds or
  reads (_affected), fails unless that module's ENGINE_OWN keeps it for the
  site's file; so does a clear of the engine's namespace, which takes every
  such name; and so does any write of a withheld name into the engine, the
  program's own included, and any read of one as an attribute of the engine
  (a read through its namespace's mapping, `vars(engine).get(name)`, is not
  seen, nor is any attribute read once the engine's `__class__` is replaced);
* a read of an attribute of the engine, in a test, of a name that test has
  replaced in a split-out module fails (with the same two exceptions);
* a replacement in markup.py of a name wheel.py or export_html.py holds by its
  import fails, unless the same test replaces it in one of those: it reaches
  neither of them.

Beside them, the census: every replacement of the engine seen must be a site
the static census (tests/split_census.py) finds, in that file. The site's
line is matched to a census row with the same name at that line; a site with
no line (a decorator's patch) to a row with that name inside the test's own
function, its decorators included. A "<dynamic>" row stands for exactly the
names the split guard's DYNAMIC lists for it, and no other, and for a clear
of the namespace made at its site (patch.dict's clear=True, which the census
marks so); a row of an unlisted "<dynamic>" site stands for no name, and a
"<dynamic module>" row for nothing. So
a spelling the census does not read shows itself here, named by its line (a
decorator's patch by its file alone), when a test that uses it runs, save on
an engine imported afresh within that test and in a change made from a frame
of a program file (code compiled under its name, or a writer a test hands to a
program function). What runs in a process a test starts is not seen; the
census alone answers for a script.
"""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

import split_census

HEAD = "ENGINE TRIPWIRE"


@lru_cache(maxsize=None)
def _tree(path: Path):
    return ast.parse(path.read_text(encoding="utf-8"))


def _test_function_span(path: Path, nodeid: str):
    """(first, last) line of the test's function, its decorators included,
    or None where the node id names none in the file."""
    parts = [p.split("[")[0] for p in nodeid.split("::")[1:]]
    if not parts or not path.is_file():
        return None
    scope = _tree(path).body
    for part in parts:
        node = next((n for n in scope if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name == part), None)
        if node is None:
            return None
        scope = node.body
    return min([node.lineno] + [d.lineno for d in node.decorator_list]), node.end_lineno


def _file_of(event, tests: Path):
    """The site's file, relative to tests/: the frame's, else the test's own."""
    if event.get("file"):
        return event["file"]
    path = event["nodeid"].split("::")[0]
    return path.split("tests/", 1)[1] if path.startswith("tests/") else path


def judge(events, tests: Path, reports: int):
    """(lines, summary) for every event the run carried: one line per
    problem, a site met by many tests named once, with the first and the count."""
    import test_split_astro_2026_10_14 as split

    affected = {m: split._affected(m) for m in split.NEW}
    writes = [e for e in events if e["kind"] in ("set", "delete", "clear")]
    files = sorted({_file_of(e, tests) for e in writes if e.get("by") == "test"})
    paths = [tests / f for f in files if (tests / f).is_file()]
    rows = {}
    for f, line, where, _form, name in split_census.census(paths)["sites"] if paths else []:
        if where == "code":
            rows.setdefault(f, []).append((line, name))

    def dynamic_names(f, line):
        key = split._dynamic_key(paths, f, line)
        listed = split.DYNAMIC.get(key)
        return set(listed[0]) if listed else set()

    def in_census(e):
        f = _file_of(e, tests)
        base = Path(f).name
        if e.get("line") is not None and e.get("file"):
            lines = {e["line"]}
        else:
            span = _test_function_span(tests / f, e["nodeid"])
            if span is None:
                return False
            lines = set(range(span[0], span[1] + 1))
        for line, name in rows.get(base, []):
            if line in lines and (name == e["name"] or name == "<dynamic>" and (
                    e["name"] == "*" or e["name"] in dynamic_names(base, line))):
                return True
        return False

    problems = {}

    def problem(e, why):
        f = _file_of(e, tests) if e.get("by") != "program" else "(the program)"
        where = f"{f}:{e['line']}" if e.get("line") else f
        key = (where, e["name"], why)
        first, n = problems.get(key, (e["nodeid"], 0))
        problems[key] = (first, n + 1)

    moved = {}
    for e in events:
        if e["kind"] == "set in a module":
            moved.setdefault(e["nodeid"], set()).add((e["module"], e["name"]))
    taken = split._taken_from_markup()
    for e in events:
        if e["kind"] == "set in a module" and e["module"] == "markup" and e["name"] in taken and not any(
                (holder[:-len(".py")], e["name"]) in moved[e["nodeid"]] for holder in taken[e["name"]]):
            problem(e, f"replaces markup.{e['name']}, which {' and '.join(taken[e['name']])} hold by import: the "
                       "replacement does not reach them (replace it there too)")

    seen_sites = set()
    for e in events:
        name, f = e["name"], (_file_of(e, tests) if e.get("by") == "test" else None)
        if e["kind"] in ("set", "delete"):
            if e.get("by") == "test":
                seen_sites.add((f, e.get("line"), name))
            if name in split_census.WITHHELD:
                problem(e, f"writes the withheld name engine.{name}, which the engine does not take")
            if e.get("by") != "test":
                continue
            for module in split.NEW:
                if name in affected[module] and (Path(f).name, name) not in split.ENGINE_OWN[module]:
                    problem(e, f"replaces engine.{name}, a name {module} binds or reads: the replacement does not "
                               f"reach it there (replace it in {module}, or keep it in its ENGINE_OWN with why)")
            if not in_census(e):
                problem(e, f"replaces engine.{name}, a site the static census does not find in that file")
        elif e["kind"] == "clear" and e.get("by") == "test":
            seen_sites.add((f, e.get("line"), name))
            problem(e, f"clears the engine's namespace ({e['count']} names): every name a split-out module binds or "
                       "reads goes with it, and the code that reads them is not reached")
            if not in_census(e):
                problem(e, "clears the engine's namespace, a site the static census does not find in that file")
        elif e["kind"] == "read missing" and name in split_census.WITHHELD:
            problem(e, f"reads the withheld name engine.{name}, which the engine does not take")
        elif e["kind"] == "read replaced" and e.get("by") == "test":
            problem(e, f"reads engine.{name} after replacing {name} in a split-out module: the engine's is "
                       "the value before the replacement")
    lines = []
    if problems:
        lines.append(f"{HEAD}: {len(problems)} problem(s):")
        for (where, _name, why), (first, n) in sorted(problems.items()):
            lines.append(f"  {where}: {why} ({first}" + (f", and {n - 1} more" if n > 1 else "") + ")")
    tests_seen = len({e["nodeid"] for e in writes if e.get("by") == "test"})
    summary = (f"{HEAD}: {sum(1 for e in writes if e.get('by') == 'test')} replacement(s) of the engine seen at "
               f"{len(seen_sites)} site(s) in {tests_seen} test(s) of {reports} test report(s); "
               f"{len(problems)} problem(s)")
    return lines, summary
