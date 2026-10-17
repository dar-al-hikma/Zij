"""Values printed in words, not as Python (lane G9 of the re-pass of 2026-10-04).

The re-pass's strict xfails for L7-05, L5R-04 and L7-06 read the pages of a
few charts. These read the two printers themselves: every reason that has
words of its own is a reason the engine still gives (so a reworded reason
cannot drop its words back to yes/no unnoticed), each prints its own pair,
and a table with one open row gives every row a Status.
"""
import ast

from conftest import APP_PATH, engine_source


def _display_helpers(engine):
    """_display_result and _display_rows exec'd alone over the engine's
    namespace, as the page and the exports call them, and the first's
    source tree."""
    tree = ast.parse(APP_PATH.read_text())
    selected = [n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name in ("_display_result", "_display_rows")]
    assert len(selected) == 2
    ns = dict(engine)
    exec(compile(ast.Module(body=selected, type_ignores=[]), "display helpers", "exec"), ns)
    return ns, next(n for n in selected if n.name == "_display_result")


def _words(function):
    tables = [node.value for node in ast.walk(function)
              if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
              and node.targets[0].id == "words"]
    assert len(tables) == 1, "premise: _display_result keeps one table of words by reason"
    return ast.literal_eval(tables[0])


def test_every_reason_with_words_of_its_own_is_one_the_engine_gives(engine):
    _ns, function = _display_helpers(engine)
    table = _words(function)
    assert len(table) >= 9, table
    source = engine_source()
    stale = [reason for reason in table if f"'{reason}" not in source and f'"{reason}' not in source]
    assert not stale, stale


def test_a_truth_valued_alternative_prints_its_own_words(engine):
    ns, function = _display_helpers(engine)
    table = _words(function)
    assert len(table) >= 9, table
    unresolved = engine["UnresolvedResult"]
    shown = {reason: ns["_display_result"](unresolved(reason, "a source", (("first", True), ("second", False))))
             for reason in table}
    assert shown == {reason: f"Unresolved — {reason} (first: {yes}; second: {no})"
                     for reason, (yes, no) in table.items()}
    assert ns["_display_result"](unresolved("any other reason", "a source", (("a", False),))) == (
        "Unresolved — any other reason (a: no)")
    assert ns["_display_result"]({"eastern": True, "flags": [False, "x"]}) == "eastern: yes; flags: no; x"


def test_a_table_with_one_open_row_gives_every_row_a_status(engine):
    ns, _function = _display_helpers(engine)
    moon, venus = {"Planet": "Moon", "With": "Saturn"}, {"Planet": "Venus", "With": "Jupiter"}
    rows = engine["_connection_merge"]([[moon, venus], [moon]])
    assert [("Status" in row) for row in rows] == [False, True], rows    # premise: the merge's own rows
    shown = ns["_display_rows"](rows)
    assert [row["Status"] for row in shown] == [
        "", "Unresolved — this finding depends on an unresolved connection "
            "(permitted outcome 1: holds; permitted outcome 2: does not hold)"]
    assert ns["_display_rows"]([moon]) == [moon]
