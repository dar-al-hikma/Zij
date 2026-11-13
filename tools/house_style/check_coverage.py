#!/usr/bin/env python3
# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""Fail when a character the app needs would reach the computer's own fonts.

Reads what the app actually emits, not a model of it: the stacks and faces in
.streamlit/config.toml, the rules and the embedded face in house_style.py, and
the character maps of the files in fonts/. Each character of the list is walked
through each role's stack, as a browser walks it, to the first bundled face
that holds it.

Place names in other scripts are not on the list: they are left to the
computer's own fonts (characters.json says how many), and so is anything a
reader types beyond the list. This checks which face holds a character, not how
a browser places or shapes it.
"""
from __future__ import annotations

import argparse
import ast
import base64
import io
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"}


def parse_stack(text: str) -> list[str]:
    return [part.strip().strip("\"'") for part in text.split(",")]


def _range_points(text):
    points = set()
    for part in text.split(","):
        first, _, last = part.strip()[2:].partition("-")
        points |= set(range(int(first, 16), int(last or first, 16) + 1))
    return points


def page_style(repo: Path) -> str:
    """The text of house_style.PAGE_STYLE, read without importing the module."""
    tree = ast.parse((repo / "house_style.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "PAGE_STYLE":
            return ast.literal_eval(node.value)
    raise SystemExit("house_style.py has no PAGE_STYLE")


def _cmap(data: bytes) -> set[int]:
    from fontTools.ttLib import TTFont
    return set(TTFont(io.BytesIO(data)).getBestCmap())


def emitted(repo: Path) -> dict:
    """What the app sends a page: its stacks by role, and its faces."""
    theme = tomllib.loads((repo / ".streamlit" / "config.toml").read_text(encoding="utf-8"))["theme"]
    css = page_style(repo)
    faces = []
    for face in theme["fontFaces"]:
        points = _cmap((repo / "fonts" / face["url"].rsplit("/", 1)[-1]).read_bytes())
        if face.get("unicodeRange"):
            points &= _range_points(face["unicodeRange"])
        faces.append({"family": face["family"].strip('"'), "weight": int(face["weight"]), "style": face["style"],
                      "name": face["url"].rsplit("/", 1)[-1], "points": points})
    for rule in re.findall(r"@font-face\{(.*?)\}", css):
        points = _cmap(base64.b64decode(re.search(r"base64,([A-Za-z0-9+/=]+)", rule).group(1)))
        points &= _range_points(re.search(r"unicode-range:([^;]+);", rule).group(1))
        faces.append({"family": re.search(r"font-family:'([^']+)'", rule).group(1),
                      "weight": int(re.search(r"font-weight:(\d+)", rule).group(1)),
                      "style": re.search(r"font-style:(\w+)", rule).group(1),
                      "name": "embedded in house_style.py", "points": points})
    reading = re.search(r'\[class\*="st-key-reading-"\] :is\(p,li,blockquote\)[^{,]*\{font-family:([^;]+);', css).group(1)
    caption = re.search(r'\[data-testid="stCaptionContainer"\] p,[^{]*\{font-family:([^;]+);', css).group(1)
    stacks = {"interface": parse_stack(theme["font"]), "heading": parse_stack(theme["headingFont"]),
              "code": parse_stack(theme["codeFont"]), "reading": parse_stack(reading), "caption": parse_stack(caption)}
    weights = theme["headingFontWeights"]
    roles = {"label": ("interface", 400, "normal"), "label, bold": ("interface", 600, "normal"),
             "table cell": ("interface", 400, "normal"), "table heading": ("interface", 600, "normal"),
             "caption": ("caption", 400, "normal"), "code": ("code", 400, "normal"),
             "heading": ("heading", weights[0], "normal"), "prose": ("reading", 400, "normal"),
             "prose, bold": ("reading", 600, "normal"), "prose, italic": ("reading", 400, "italic")}
    return {"stacks": stacks, "faces": faces, "roles": roles, "css": css, "theme": theme}


def _chosen(faces, family, weight, style):
    """The faces of `family` a browser takes for this weight and style."""
    own = [f for f in faces if f["family"] == family]
    if not own:
        return []
    styled = [f for f in own if f["style"] == style] or own
    weights = sorted({f["weight"] for f in styled})
    if weight <= 500:
        order = [w for w in weights if weight <= w <= 500] + [w for w in reversed(weights) if w < weight] + [w for w in weights if w > 500]
    else:
        order = [w for w in weights if w >= weight] + [w for w in reversed(weights) if w < weight]
    return [f for f in styled if f["weight"] == order[0]]


def resolve(state: dict, role: str, point: int) -> tuple[str, str]:
    """(family, file) of the face a role draws `point` in. The family is a
    generic's name, and the file empty, when the stack holds no bundled face
    with it: the computer's own fonts then draw it."""
    stack, weight, style = state["roles"][role]
    for family in state["stacks"][stack]:
        if family in GENERIC:
            return family, ""
        for face in _chosen(state["faces"], family, weight, style):
            if point in face["points"]:
                return family, face["name"]
    return "", ""


def failures(state: dict, points) -> list[tuple[str, int]]:
    return [(role, point) for role in state["roles"] for point in sorted(points) if not resolve(state, role, point)[1]]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args()
    characters = json.loads((ROOT / "characters.json").read_text(encoding="utf-8"))
    if not characters["required"]:
        print("REFUSED: the list of required characters is empty", file=sys.stderr)
        raise SystemExit(2)
    state = emitted(args.repo)
    missing = failures(state, characters["required"])
    for role, point in missing:
        print(f"FAIL: {role} U+{point:04X} {chr(point)} reaches the computer's own fonts")
    if missing:
        raise SystemExit(1)
    print(f"PASS: {len(state['roles'])} roles, {len(characters['required'])} characters, each in a bundled face")
    print(f"Left to the computer's own fonts: {json.dumps(characters['other_scripts'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
