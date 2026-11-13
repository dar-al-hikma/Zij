# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The page a reader sees while the program opens: in the launcher's window
from its first paint until its server answers, and in the app's own page from
its first paint until a session's first run ends. One look for both, so the
reader sees one page: the ground of the saved colours (Light when none is
saved), the opening icon slowly growing and shrinking like a breath, and still
when the reader has asked for less motion, and under it the program's name,
still, in an italic face, in the colour the page's own accent has in that
palette. The name is the only visible text; a screen reader hears "Opening".
No script moves it: the beat is a style.

The app's page carries it in its document: the server writes it into
Streamlit's index.html as it serves it (server_limits.py), so that it stands
from the first paint, before Streamlit's own skeleton and before the engine is
loaded. It lifts by style alone: when the page's run state reads stopped, and
from a session's first run's end on by one style the app writes at that end
and at the top of every later run.

Nothing here loads the engine or Streamlit at import: the launcher reads it
before its server answers. The icon and the face are read as bytes when the
page is made; no image or font is written into a source file.
"""
import base64
import html
import os
import re
import sys

# What a screen reader hears of the cover: one word. The name beneath the icon
# is only seen.
SPOKEN = "Opening"
# The program's name as the program writes it (desktop_launcher.APP_TITLE and
# app.py's page title), shown beneath the icon and hidden from a screen reader,
# which hears SPOKEN alone.
NAME = "Z\u012bj"
# The name's face: EB Garamond Italic, the file the app already ships, its swash
# forms on (the face has a swash Z); its size and the gap above it, in CSS px.
FACE_FILE = os.path.join("fonts", "eb-garamond-400-italic.ttf")
FACE = "EB Garamond"
# The face as the app's server answers it (server_limits.FONT_ROUTE).
FACE_URL = "/zij-font/eb-garamond-400-italic.ttf"
NAME_PIXELS = 30
NAME_GAP_PIXELS = 12
# The icon's beat: one breath takes this many seconds (half out, half back),
# and the icon grows to this many times its size at the breath's fullest.
BEAT_SECONDS = 2.5
BEAT_SCALE = 1.08
# app_icon_opening_source.png reduced by icon.py to this many pixels a side,
# shown at half that many CSS pixels.
ICON_NAME = "app_icon_opening.png"
ICON_SOURCE = "app_icon_opening_source.png"
ICON_PIXELS = 256
CONFIG_FILE = os.path.join(".streamlit", "config.toml")
# The preferences entry page_colours.py keeps the reader's choice under.
PREFERENCE = "_page_colours"
LIGHT, DARK = "Light", "Dark"
# Used only when the configuration cannot be read.
_PLAIN = {LIGHT: ("#FFFFFF", "#000000"), DARK: ("#000000", "#FFFFFF")}
# The session state's mark that this session's first run has begun.
SHOWN = "_zij_opening_shown"
CLASS = "zij-opening"
# The one style that holds the cover lifted once a session's first run ends.
LIFTED = f"<style>.{CLASS}{{display:none !important;}}</style>"


def _path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _bytes(name):
    try:
        with open(_path(name), "rb") as f:
            return f.read()
    except OSError:
        return None


def colours(choice):
    """(ground, text) of the palette `choice` names, Light for anything but
    Dark, as the configuration gives them."""
    choice = DARK if choice == DARK else LIGHT
    try:
        import tomllib

        theme = tomllib.loads(_bytes(CONFIG_FILE).decode("utf-8"))["theme"][choice.lower()]
        return theme["backgroundColor"], theme["textColor"]
    except Exception:
        return _PLAIN[choice]


def accent(choice):
    """The page's gold in the palette `choice` names (Light for anything but
    Dark), as the configuration gives it; the palette's text colour when the
    configuration cannot be read."""
    choice = DARK if choice == DARK else LIGHT
    try:
        import tomllib

        return tomllib.loads(_bytes(CONFIG_FILE).decode("utf-8"))["theme"][choice.lower()]["primaryColor"]
    except Exception:
        return _PLAIN[choice][1]


# The served cover lifts only by :has(); where the window's engine cannot read
# it, the cover never shows, and the page opens as it would without one.
SUPPORTS = "@supports selector(:has(*))"


def _css(ground, text, gold, face_url, guarded=False):
    half = ICON_PIXELS // 2
    face = (f"@font-face{{font-family:'{FACE} Opening';font-style:italic;"
            f"src:url({face_url}) format('truetype');}}" if face_url else "")
    family = f"'{FACE} Opening','{FACE}',Georgia,'Times New Roman',serif"
    shown = (f".{CLASS}{{position:fixed;inset:0;z-index:1000100;display:flex;flex-direction:column;"
             f"align-items:center;justify-content:center;background:{ground};color:{text};margin:0;}}")
    if guarded:
        shown = f".{CLASS}{{display:none;}}{SUPPORTS}{{{shown}}}"
    # The beat moves the icon by transform alone, which neither lays out nor
    # paints again, so the browser can keep it going while the page is busy.
    return (face + shown +
            f".{CLASS} img{{width:{half}px;height:{half}px;"
            f"animation:zij-opening-beat {BEAT_SECONDS / 2:g}s ease-in-out infinite alternate;}}"
            f"@keyframes zij-opening-beat{{from{{transform:scale(1);}}to{{transform:scale({BEAT_SCALE:g});}}}}"
            # The name stands still: it is not the icon, and nothing moves it.
            f".{CLASS} .zij-opening-name{{margin:{NAME_GAP_PIXELS}px 0 0;color:{gold};"
            f"font-family:{family};font-style:italic;font-weight:400;font-size:{NAME_PIXELS}px;"
            f'line-height:1.2;font-feature-settings:"swsh" 1;}}'
            f"@media (prefers-reduced-motion: reduce){{.{CLASS} img{{animation:none;}}}}"
            # A run that ends by any road, an exception's too, lifts the
            # cover in the app: the page's own state, not a script.
            f'body:has([data-testid="stApp"][data-test-script-state="notRunning"]) .{CLASS},'
            f'body:has([data-testid="stApp"][data-test-script-state^="compilation"]) .{CLASS}{{display:none;}}')


def _body():
    icon = _bytes(ICON_NAME)
    img = (f'<img alt="" src="data:image/png;base64,{base64.b64encode(icon).decode("ascii")}">'
           if icon else "")
    return (f'<div class="{CLASS}" role="status" aria-label="{SPOKEN}">{img}'
            f'<div class="zij-opening-name" aria-hidden="true">{html.escape(NAME)}</div></div>')


def page(choice):
    """The launcher's whole page, for the window before its server answers:
    the face read from its file and carried in the page itself."""
    ground, text = colours(choice)
    face = _bytes(FACE_FILE)
    face_url = f"data:font/ttf;base64,{base64.b64encode(face).decode('ascii')}" if face else None
    return ('<!doctype html><html><head><meta charset="utf-8"><title></title>'
            f'<style>html,body{{margin:0;background:{ground};}}{_css(ground, text, accent(choice), face_url)}</style>'
            f'</head><body>{_body()}</body></html>')


def served(document, choice):
    """Streamlit's index.html with the cover written into it: its style first
    in the head, the page's ground on the body from the first paint, and its
    markup first in the body, beside the element Streamlit draws into. No
    script is added. A document of another shape is returned as it came."""
    head = (re.search(r"<meta charset[^>]*>", document, re.I)
            or re.search(r"<head(?:\s[^>]*)?>", document, re.I))
    body = re.search(r"<body[^>]*>", document, re.I)
    if head is None or body is None or body.start() < head.end():
        return document
    ground, text = colours(choice)
    style = (f"<style>html,body{{margin:0;background:{ground};}}"
             f"{_css(ground, text, accent(choice), FACE_URL, guarded=True)}</style>")
    return (document[:head.end()] + style + document[head.end():body.end()] + _body()
            + document[body.end():])


def first_run(st):
    """At the top of every run: True at a session's first run. At every later
    run the style that holds the cover lifted is written first, so a later
    run's running state never brings it back."""
    if st.session_state.get(SHOWN):
        st.html(LIFTED)
        return False
    st.session_state[SHOWN] = True
    return True


def keep_lifted(st):
    """At a session's first run's end, by whatever road it ends."""
    st.html(LIFTED)


def first_whole_run():
    """Cached once a first run has stood whole: the server's own metrics then
    name it, which is how a timed start knows the page stands."""
    return True


def mark_the_whole_run():
    import streamlit

    streamlit.cache_data(show_spinner=False)(first_whole_run)()
