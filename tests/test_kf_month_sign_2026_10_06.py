"""The month sign the Revolutions wheels outline, at the seam of 0 Aries.

page_timing takes the month's sign from monthly indicator #1's longitude
and hands it to the wheels as `outline_sign`. `(-1e-16 % 360.0) // 30` is
12 in floats, a sign index past Pisces: the wheel drew `data-sign="12"` and
its label placement took Aries for a sign other than itself. The point is
0 Aries, as at 0.0 and 360.0; a true 359.99999999999994 is still Pisces.

The expression is inline in page_timing, so it is read from app.py and
evaluated in the app's own namespace (the engine's names, as app.py's
`from engine import *` gives them).
"""
import ast

import pytest

from conftest import EXECUTABLE_DIR


def _month_sign_expression():
    tree = ast.parse((EXECUTABLE_DIR / "app.py").read_text(encoding="utf-8"))
    found = [node.value for node in ast.walk(tree)
             if isinstance(node, ast.Assign)
             and [getattr(t, "id", None) for t in node.targets] == ["month_sign"]
             and "_month_lon" in ast.unparse(node.value)]
    assert len(found) == 1, f"the premise: one month_sign assignment from _month_lon, found {len(found)}"
    return ast.unparse(found[0])


def test_kf_the_month_sign_at_the_seam_is_aries(engine):
    namespace = dict(engine)            # app.py's `from engine import *`: every engine name (lane TL, TL-11)
    expression = _month_sign_expression()
    got = {lon: eval(expression, namespace, {"_month_lon": lon})
           for lon in (-1e-16, 0.0, 360.0, 359.99999999999994)}
    assert got == {-1e-16: 0, 0.0: 0, 360.0: 0, 359.99999999999994: 11}, (expression, got)
