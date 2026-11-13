"""The Releaser page's 1.23, 13-14 redirection: 14's direction is this app's reading in both branches.

Sahl, On Nativities 1.23, 14 is conditional: "Now if there was nothing of what
I have mentioned, then take from the degree of the Ascendant ...". The page
draws 14's direction beside 13's whether or not 13 finds anything, so both
branches of the redirection (the lord of the Ascendant the house-master, or
another planet) say in a caption that drawing 14 there is this app's reading,
and neither says the text directs 14 in every case. Both direction tables stay.

The source is read as text; nothing imports the app.
"""
from __future__ import annotations

import ast
import re

from conftest import APP_PATH
from corpus_paths import corpus_file
from skip_guard import skip_without_corpus

NAT = corpus_file("on_nativities.md")
CONDITION = "if there was nothing of what I have mentioned"


def _branches():
    """(house-master branch, other branch): the two arms of the one
    `if _rd['lord_is_house_master']:` in app.py."""
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    found = [node for node in ast.walk(tree)
             if isinstance(node, ast.If) and ast.unparse(node.test) == "_rd['lord_is_house_master']"]
    assert len(found) == 1, f"the redirection's branch found {len(found)} times in app.py"
    branch = found[0]
    assert branch.body and branch.orelse, "the redirection has lost a branch"
    return branch.body, branch.orelse


def _strings(node):
    """Every string an expression can print: constants, and an f-string's literal parts."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_strings(part) if isinstance(part, ast.Constant) else "{}" for part in node.values)
    return ""


def _calls(statements, name):
    """The first arguments' strings of every `st.<name>(...)` call among the statements."""
    out = []
    for statement in statements:
        for node in ast.walk(statement):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "st" and node.args):
                out.append(_strings(node.args[0]))
    return out


def _tables(statements):
    """{label: the expression it draws} from the branch's `_redirect_tables = (...)`."""
    assigned = [node for statement in statements for node in ast.walk(statement)
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_redirect_tables"
                                                        for t in node.targets)]
    assert len(assigned) == 1, f"_redirect_tables assigned {len(assigned)} times in the branch"
    pairs = assigned[0].value
    assert isinstance(pairs, ast.Tuple)
    out = {}
    for pair in pairs.elts:
        assert isinstance(pair, ast.Tuple) and len(pair.elts) == 2
        out[_strings(pair.elts[0])] = ast.unparse(pair.elts[1])
    return out


def _reading_captions(statements):
    return [c for c in _calls(statements, "caption") if "14" in c and "this app's reading" in c]


def test_the_house_master_branch_keeps_its_caption():
    house_master, _ = _branches()
    captions = _reading_captions(house_master)
    assert len(captions) == 1, _calls(house_master, "caption")
    assert "that 14 covers the case is this app's reading" in captions[0], captions[0]


def test_the_other_branch_names_14_beside_13_as_this_apps_reading():
    _, other = _branches()
    captions = _reading_captions(other)
    assert len(captions) == 1, _calls(other, "caption")
    caption = captions[0]
    assert caption.startswith("Read: "), caption
    assert f"\"{CONDITION}\"" in caption, "14's condition, quoted from the page"
    # "in every case" is said once, and of this app's reading, never of the text.
    assert caption.count("in every case") == 1, caption
    assert re.search(r"beside 13's in every case is this app's reading\.$", caption), caption
    assert not re.search(r"\b(text|Sahl|sentence|page)\b[^;]*\b(always|in every case)\b", caption), caption


def test_neither_caption_says_the_text_directs_14_always():
    house_master, other = _branches()
    captions = _calls(house_master, "caption") + _calls(other, "caption")
    assert len(captions) >= 2, captions
    for caption in captions:
        assert not re.search(r"\b(text|Sahl|sentence)s?\b[^;.]*\b(always|in every case|whether or not)\b",
                             caption), caption


def test_both_branches_still_draw_their_tables():
    house_master, other = _branches()
    assert _tables(house_master) == {"1.23, 14: the degree of the Ascendant": "_rd['ascendant_direction']"}
    assert _tables(other) == {
        "1.23, 13: the lord of the Ascendant, in the house-master's stead": "_rd['lord_direction']",
        "1.23, 14: the degree of the Ascendant": "_rd['ascendant_direction']",
    }


def test_the_condition_is_printed_as_14_on_the_page():
    skip_without_corpus(NAT)
    text = NAT.read_text(encoding="utf-8")
    assert f"**14** Now {CONDITION}, then take" in text
