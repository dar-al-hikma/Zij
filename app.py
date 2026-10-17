"""The Streamlit pages: the sidebar, the navigation, and every page a reader
opens, each one a function closing over the engine's top-level names.

The engine itself is engine.py, beside this file, and arrives whole through
the star import below. Run this file, not that one: ``python run_source.py``
runs it behind the desktop window's door, and ``streamlit run app.py`` runs
it unchecked.
"""

import contextlib
import dataclasses
import functools
import hmac
import json
import math
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, time, timedelta, timezone
from math import isfinite
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path

import pandas as pd
import streamlit as st
from timezonefinder import TimezoneFinder

# The window's door (the owner's rulings 150 and 157). The desktop launcher
# starts this server with a secret made for that launch alone, held in the
# server's environment, and opens its window on a URL that carries it
# (desktop_launcher.py; the two names below are the launcher's too). A
# session is let in once it has shown the secret, at its first run, and is
# remembered for its life, so a rerun or a page change asks nothing again.
# Once it is let in, the secret is taken out of the window's address, which
# no longer shows it to a copy of the address, the page's history or a
# reader of the screen; the launcher gives it again to a reload of the
# window (desktop_launcher._WindowRules). Any other client -- another account on this
# computer, a page served from another local port, a frame -- is told one
# sentence and stopped here: before the engine is loaded, before the launch
# is counted, before any saved chart or preference is read, and before any
# widget exists. A source run through run_source.py is kept the same way: it
# makes a secret of its own and prints the URL that carries it. A run with
# no secret in its environment -- `streamlit run app.py`, the developer's
# command, and the suite -- is not checked.
_LAUNCH_KEY_VARIABLE = "ZIJ_LAUNCH_KEY"
_LAUNCH_KEY_PARAMETER = "launch"
_LAUNCH_KEY_REFUSAL = ("This app can be used only in the window it opens when it starts; "
                       "use that window, or start the app again.")


def _admit_only_the_window():
    expected = os.environ.get(_LAUNCH_KEY_VARIABLE)
    if not expected:
        return
    if st.session_state.get("_launch_key_shown") is not True:
        shown = st.query_params.get(_LAUNCH_KEY_PARAMETER) or ""
        # Compared in constant time, as bytes: a str holding anything but
        # ASCII cannot be compared that way at all.
        if not hmac.compare_digest(shown.encode("utf-8", "surrogatepass"),
                                   expected.encode("utf-8", "surrogatepass")):
            st.info(_LAUNCH_KEY_REFUSAL)
            st.stop()
        st.session_state["_launch_key_shown"] = True
    st.query_params.pop(_LAUNCH_KEY_PARAMETER, None)


_admit_only_the_window()

# Swiss Ephemeris is not imported here: `swe` comes with the star import
# below, the engine's handle on it, which points each thread at the
# engine's own ephemeris folder before the thread's first calculation. The
# engine's first import, ephemeris.py, sets $SE_EPHE_PATH to that folder
# before it loads the library, so nothing may load the library before the
# engine does.
#
# Where no private folder can be made for Swiss Ephemeris -- a temporary
# folder on a filesystem that keeps no modes, or none at all -- the
# engine's own import refuses (EphemerisFolderRefused, raised by
# ephemeris.py as the engine imports it; the owner's ruling 120). An import
# made again after the engine was dropped from sys.modules (Streamlit's
# watcher does that when a source file changes) runs in this run's own
# thread, which its first calculation points at the folder: where the
# folder holds a file the app did not put there, that import refuses too
# (EphemerisRefused). The engine never loaded, so the class is known here
# only by its name and its parent's, the subclass looked for first, and
# each sentence (EPHEMERIS_FOLDER_REFUSAL, EPHEMERIS_REFUSAL; rulings 120
# and 121) is held here too, in the same words; the run says the one for
# the refusal raised and stops. Anything else raised still shows as itself.
_EPHEMERIS_FOLDER_REFUSAL_AT_IMPORT = ("Nothing is calculated: this app could not make a private folder for its "
                                       "ephemeris in the computer's temporary folder.")
_EPHEMERIS_REFUSAL_AT_IMPORT = ("Nothing is calculated: Swiss Ephemeris found a file this app does not supply. "
                                "Close the app and open it again.")
try:
    import engine
except RuntimeError as _refused:
    _refused_as = [_kind.__name__ for _kind in type(_refused).__mro__]
    if "EphemerisFolderRefused" in _refused_as:
        st.error(_EPHEMERIS_FOLDER_REFUSAL_AT_IMPORT)
    elif "EphemerisRefused" in _refused_as:
        st.error(_EPHEMERIS_REFUSAL_AT_IMPORT)
    else:
        raise
    st.stop()
from engine import *

# ==========================================
# 4. STREAMLIT UI INTEGRATION
# ==========================================

# Every zone this app reads comes from the pinned tzdata package, never the
# computer's own database (the owner's ruling 71;
# _read_zones_from_the_pinned_package, in time_zones.py, which the engine
# takes whole, says how). Importing the engine did it once for the process; the script runs again on every rerun in a process
# that outlives that import, so each run does it again here, before the
# script makes any zone.
engine._read_zones_from_the_pinned_package()

_icon_path = Path(__file__).parent / "app_icon.ico"
st.set_page_config(
    page_title="Zīj",
    page_icon=str(_icon_path) if _icon_path.exists() else None,
    layout="wide",
)

# The engine refuses to compute in a thread whose Swiss Ephemeris has met a
# file the app does not supply, or where no private folder can be had for
# it (ephemeris.py, "SWISS EPHEMERIS'S FILES"). Each run is a thread of its
# own, so the run asks first, before anything is drawn; a refusal is said
# in its own plain sentence and the run stops, its detail kept off the page.
try:
    engine.ephemeris_thread_check()
except engine.EphemerisFolderRefused:
    st.error(engine.EPHEMERIS_FOLDER_REFUSAL)
    st.stop()
except engine.EphemerisRefused:
    st.error(engine.EPHEMERIS_REFUSAL)
    st.stop()

# --- Structure: the course's own order, in three sections -----------------
# Pages follow the syllabus and are grouped in the navigation as the course
# is: The Nativity, Prediction, and the reference pages.
# Nothing is hidden. The lesson gate that used to hide pages by lesson
# number went on 2026-09-10 (UI_REVIEW_2026-09-10.md §1): the course
# reviews later material early -- the Lesson 5 warm-ups are the planets
# and their places, the Dignities page -- so a filter by lesson number hid
# exactly what the lecture was using, and a page a student is not ready
# for is simply a page not opened. What restrains the pages now is the
# Sources shown reading on the Sources page, which folds the supplement.

# The viewer's theme, read once for the pictures. Streamlit 1.62 reports
# it as st.context.theme.type -- "dark", "light", or None when the browser
# has not said yet (and under AppTest, which has no browser at all). It is
# not by itself what a picture is drawn in: the owner's ruling is that the
# wheels keep their white ground in every theme unless the reader asks
# otherwise, so this is read here and consulted only when the Dark wheel
# preference is on (WHEEL_THEME, below with the other readings).
_context_theme = getattr(st.context, "theme", None)
VIEWER_THEME = getattr(_context_theme, "type", None) if _context_theme is not None else None

# --- The natal wheel, clickable -------------------------------------------
# The Chart page's wheel is mounted as an st.components.v2 component rather
# than shown with st.image, so that a click on a planet or a sign can reach
# Python. The component is registered ONCE, here at the module level: a
# registration wrapped up with its own mounting would re-register the name
# on every instance, which the API warns against. It is mounted inside the
# Chart page's fragment, so a click reruns that fragment and not the page.
#
# What the component is handed is the SVG the app's own renderer produced,
# with every value already escaped at the point it was written (_esc_attr,
# _esc_text). No string from the sidebar, from a saved chart's name or from
# a place label is ever put into the html, css or js below -- those are
# component code, which Streamlit does not sanitise, and they are constants
# written here. User strings reach the component only inside `data`, which
# is data.
#
# The CSS styles the wrapper, the expand control and the hover tooltip and
# NOTHING inside the picture: the wheel carries its own palette, light or
# dark, and a component that recoloured it would be overruling the reader's
# own Dark wheel preference. Styles are isolated in a shadow root
# (isolate_styles defaults to True), so none of this reaches the app.
NATAL_WHEEL_CSS = """
/* The component's own root spans the main area, and an inline-block inside
   it sat at the left edge -- st.image used to do the centring itself, which
   the mount does not inherit. A block with auto margins centres the 560 px
   wheel inside the host, and at Wide, where the width is 100%, the margins
   come to nothing and the picture runs the full width as before. The outer
   st.container(horizontal=True, horizontal_alignment="center") stays where
   it is. overflow is visible so the tooltip is not cut off at the edge. */
.nw-wrap {
    position: relative;
    display: block;
    margin: 0 auto;
    max-width: 100%;
    overflow: visible;
}
.nw-wrap.nw-full {
    position: fixed;
    inset: 0;
    z-index: 2147483000;
    width: 100% !important;
    height: 100%;
    padding: 0.5rem;
    background: var(--st-background-color, #ffffff);
    display: flex;
    align-items: center;
    justify-content: center;
}
.nw-svg { line-height: 0; }
.nw-full .nw-svg {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
}
.nw-full .nw-svg svg {
    width: auto !important;
    height: 100% !important;
    max-width: 100%;
}
.nw-svg [data-point], .nw-svg [data-sign] { cursor: pointer; }
.nw-expand {
    position: absolute;
    top: 0.35rem;
    right: 0.35rem;
    z-index: 1;
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    border-radius: 0.35rem;
    background: var(--st-secondary-background-color, rgba(240, 242, 246, 0.9));
    color: var(--st-text-color, inherit);
    font: inherit;
    font-size: 0.9rem;
    line-height: 1;
    padding: 0.25rem 0.4rem;
    cursor: pointer;
    opacity: 0.55;
}
.nw-expand:hover { opacity: 1; }
/* The tooltip is placed against the VIEWPORT, not against the wrapper: at
   the right-hand side of the wheel a tooltip bounded by the wrapper had
   nowhere to go and wrapped itself into a column one word wide. Fixed
   position, one fixed width so the text breaks in the same place wherever
   it is raised, and the frontend flips it to the left of the pointer, or
   above it, when it would otherwise run off the screen. */
.nw-tip {
    position: fixed;
    z-index: 2147483001;
    width: 22rem;
    max-width: calc(100vw - 2rem);
    white-space: pre-line;
    pointer-events: none;
    padding: 0.3rem 0.45rem;
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    border-radius: 0.35rem;
    background: var(--st-secondary-background-color, rgba(240, 242, 246, 0.97));
    color: var(--st-text-color, inherit);
    font: inherit;
    font-size: 0.78rem;
    line-height: 1.35;
}
"""

# The frontend: one child div under the component's own root (the API's own
# warning -- writing innerHTML on the root itself would overwrite the CSS
# and HTML the component was registered with), the SVG dropped into it, a
# click listener on every [data-point] and every [data-sign], a tooltip fed
# from the envelope's own text, and an expand control the Escape key also
# closes. The listener set is rebuilt from scratch on every rerun because
# the SVG is replaced whole; the keydown listener is not, so the cleanup
# function returned at the end takes it off again when Streamlit unmounts.
NATAL_WHEEL_JS = """
export default function (component) {
    const { data, parentElement, setTriggerValue } = component;
    let wrap = parentElement.querySelector(".nw-wrap");
    if (!wrap) {
        wrap = document.createElement("div");
        wrap.className = "nw-wrap";
        const holder = document.createElement("div");
        holder.className = "nw-svg";
        const tip = document.createElement("div");
        tip.className = "nw-tip";
        tip.hidden = true;
        const expand = document.createElement("button");
        expand.type = "button";
        expand.className = "nw-expand";
        expand.title = "Expand the wheel (Escape closes it)";
        expand.textContent = "\\u2921";
        expand.onclick = () => { wrap.classList.toggle("nw-full"); };
        wrap.appendChild(holder);
        wrap.appendChild(tip);
        wrap.appendChild(expand);
        parentElement.appendChild(wrap);
    }
    const holder = wrap.querySelector(".nw-svg");
    const tip = wrap.querySelector(".nw-tip");
    const signs = (data && data.signs) || [];
    holder.innerHTML = (data && data.svg) || "";
    const svg = holder.querySelector("svg");
    if (svg) {
        svg.removeAttribute("width");
        svg.removeAttribute("height");
        svg.style.height = "auto";
        if (data.width === "stretch") {
            svg.style.width = "100%";
            wrap.style.width = "100%";
        } else {
            svg.style.width = data.width + "px";
            wrap.style.width = data.width + "px";
            wrap.style.maxWidth = "100%";
        }
    }
    holder.querySelectorAll("[data-point]").forEach((element) => {
        element.addEventListener("click", () => {
            setTriggerValue("picked", "planet:" + element.getAttribute("data-point"));
        });
    });
    holder.querySelectorAll("[data-sign]").forEach((element) => {
        const index = element.getAttribute("data-sign");
        element.addEventListener("click", () => {
            setTriggerValue("picked", "sign:" + index);
        });
        element.addEventListener("pointermove", (event) => {
            const text = signs[Number(index)];
            if (!text) { return; }
            tip.textContent = text;
            tip.hidden = false;
            // Placed in viewport coordinates, and flipped to the other side
            // of the pointer when it would otherwise run off the screen --
            // which is what the right-hand signs did before.
            const gap = 14;
            const box = tip.getBoundingClientRect();
            let left = event.clientX + gap;
            let top = event.clientY + gap;
            if (left + box.width + gap > window.innerWidth) {
                left = Math.max(gap, event.clientX - gap - box.width);
            }
            if (top + box.height + gap > window.innerHeight) {
                top = Math.max(gap, event.clientY - gap - box.height);
            }
            tip.style.left = left + "px";
            tip.style.top = top + "px";
        });
        element.addEventListener("mouseleave", () => { tip.hidden = true; });
    });
    const onKey = (event) => {
        if (event.key === "Escape") { wrap.classList.remove("nw-full"); }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); };
}
"""

NATAL_WHEEL = st.components.v2.component("natal_wheel", css=NATAL_WHEEL_CSS, js=NATAL_WHEEL_JS)

# The sidebar's first row, above the Nativity header (the owner's ruling on
# the preview): the "Here & Now" button on the left and the home place's
# popover on the right, each drawn INTO its column further down the script
# -- the button once the preferences are read, the popover once the
# Birthplace block has resolved this run's place -- so that the row stands
# at the top of the sidebar while the controls in it are drawn from state
# that exists only lower down. The home's controls live in the popover, out
# of sight until wanted, so the nativity's own boxes are not crowded.
_here_now_slot, _home_slot = st.sidebar.columns([3, 2])

st.sidebar.header("Nativity")

def _read_store():
    """Read the saved charts into this session: at its first run, and again
    when the folder they are kept in comes back while it is open (K-08)."""
    # K-08 of the re-pass's follow-ups (2026-10-05): whether the folder
    # could be used when this read was made. The folder is tried again first
    # (data_folder_problem makes it as a launch does, moving the folder kept
    # under the former name across), so that what it holds is what is read.
    st.session_state["_store_read_without_folder"] = engine.data_folder_problem() is not None
    st.session_state["saved_charts"] = load_saved_charts()
    # K-03: the digest of the bytes this load parsed, not of a second read of
    # the file -- another window's write landing just after the load would
    # otherwise be taken as this window's own, and lost at its next save.
    st.session_state["_store_digest"] = engine.loaded_saved_charts_digest()
    # F04 of the review of 2026-09-16: a store that cannot be read is copied
    # beside itself by the loader before anything writes over it, and the
    # copy's name is left in engine.LAST_STORE_ERROR. Held here so the
    # sidebar can say so once, below, in the session that read it.
    # The copy told to the reader at this load, if any: a save that later
    # writes over these same bytes has nothing new to say about them.
    # S01 of lane SC2: what this window's own load found (store_notices),
    # not the module's names, which another window's load may have reset
    # or set in between.
    found = engine.store_notices()
    st.session_state["_store_named_copy"] = found["copy"]
    if found["copy"]:
        st.session_state["_store_error_notice"] = found["copy"]
    elif found["unreadable"]:
        # L6-09: nothing could be copied (a directory in the store's place).
        st.session_state["_store_error_notice"] = True
    # Ruling 100: a save cut short, found by this load and kept beside the
    # saved charts (ruling 91), is said once.
    if found["recovered"]:
        st.session_state["_store_recovered_notice"] = True
    # S02 of SC2's check (lane SC3): a store kept where this app used to keep
    # its charts, which this load could not move in for the store's lock,
    # is said once -- ruling 109's sentence where something stands under the
    # lock's name -- and this window's next save moves it in first. SC3's
    # check: only where a reload would list those charts -- an old store
    # that reads (the engine's 'unmoved'), and a folder it can be moved into.
    if found["unmoved"] and not st.session_state["_store_read_without_folder"]:
        st.session_state["_store_unmoved"] = True
        if found["unlocked"]:
            st.session_state["_store_unlocked_notice"] = True
        else:
            st.session_state["_store_unmoved_notice"] = found["blocked"] or True
    # SB-06 and SB-05 of the security sweep (ruling 157): the store kept
    # beside the program, brought in this once; and something that is no
    # file where an older version kept its store, not read. Each said once.
    if found["imported"]:
        st.session_state["_store_imported_notice"] = True
    if found["old_not_a_file"]:
        st.session_state["_store_old_not_a_file_notice"] = True

if "saved_charts" not in st.session_state:
    _read_store()
elif (st.session_state.get("_store_read_without_folder")
        and engine.data_folder_problem() is None):
    # K-08: the folder could not be used when this session read the store,
    # and now it can -- put right while the app was open, and the saved
    # charts kept under the former name moved into it just now. No write
    # could be made meanwhile (Save refuses while the folder cannot be used,
    # and nothing can be written where it cannot be), so this session holds
    # nothing the file lacks: the store is simply read again, and the picker
    # lists what arrived.
    _read_store()
elif engine.data_folder_state()[0] == 'found':
    # SC-10 of the notes lanes (2026-10-06): the folder has gone since this
    # session read the store (the sidebar says so below, and Save refuses
    # while it stands). When it comes back, whatever it then holds is read
    # again, as K-08 reads a folder put right; the picker used to keep the
    # records of the folder that went until the next write.
    st.session_state["_store_read_without_folder"] = True

def _note_unreadable_preferences():
    """L6R-N5: after a read of the preferences file, leave the sidebar its
    sentence if the file could not be read -- the copy's name, or True when
    no copy could be made and the file was therefore not written. Each
    such sentence is said once a session, not again at every write that
    meets the same file. K-2: what this window's own read found, not what
    the module's names hold after another window's."""
    found = engine.preferences_notices()
    if found["unreadable"]:
        notice = found["copy"] or True
        if st.session_state.get("_prefs_error_said") != notice:
            st.session_state["_prefs_error_said"] = notice
            st.session_state["_prefs_error_notice"] = notice

# Ruling 77: another window of the app, or another launch of it on the same
# folder, held the saved charts' or the preferences' lock past the engine's
# bounded wait (engine.LOCK_WAIT_SECONDS); nothing was written.
STORE_BUSY_SENTENCE = ("Another window of this app is holding the saved charts just now, "
                       "so nothing was written. Try again in a moment.")
PREFERENCES_BUSY_SENTENCE = ("Another window of this app is holding the preferences just now, "
                             "so this choice was not kept. Try again in a moment.")
# The saved charts' folder refuses the lock call itself (a network folder
# with no lock service): a save, a delete or the move of a store kept in an
# old place is refused, and nothing is written (engine.DataLockUnavailable).
# A preference write so refused is said as any write the file did not take.
STORE_UNLOCKED_SENTENCE = ("Charts cannot be saved or deleted, because their folder could not be locked "
                           "against two windows saving at once. Nothing was changed.")
# Ruling 109 (lane SC3): something stands under the name of the lock file
# the saved charts' or the preferences' write takes -- a directory, a link, a
# file this app cannot open -- in the folder named (the data folder, or the
# folder of the file a linked store names); the write is refused and nothing
# is written. Said in the run of the action, in the window that made it, as
# the busy sentence is; the folder named as the folder's own sentence names
# it (_data_folder_refusal). Ruling 112: the owner's words, naming no file.


def _store_blocked_sentence(folder):
    return (f"Charts cannot be saved or deleted: something in their folder, `{folder}`, is in the way of the "
            "file this app uses to keep two windows from writing at once. Nothing was written.")


def _prefs_blocked_sentence(folder):
    return (f"Preferences cannot be saved: something in their folder, `{folder}`, is in the way of the file "
            "this app uses to keep two windows from writing at once. This choice was not kept.")


# S02 of SC2's check (lane SC3): a load that could not move in the store
# kept by an older version of the app (beside app.py, or in the folder under
# its former name: engine._old_stores), another window holding the saved
# charts past the lock's bound (ruling 77), listed nothing and said nothing.
# Ruling 112: the owner's words.
STORE_UNMOVED_SENTENCE = ("Another window was using the saved charts when this one opened, so charts kept by an "
                          "older version of the app are not listed yet. Reload the page to list them.")
# Ruling 100: a save cut short (a write ended between its bytes and its
# replace) found at the load and kept beside the store under a recovery
# name (ruling 91). The page names no file.
STORE_RECOVERED_SENTENCE = ("A save that was cut short was found and kept beside the saved charts; "
                            "it is not in the list.")
# SB-06 of the security sweep (ruling 157): a store kept beside the program by
# an older version is brought in once, and said; it is not brought in again.
STORE_IMPORTED_SENTENCE = ("Charts kept beside the program by an older version of the app were brought into "
                           "the saved charts. That file is left as it is and is not read again.")
# SB-05 (ruling 157): a pipe, a device or a folder where an older version kept
# its store is not read, and said.
STORE_OLD_NOT_A_FILE_SENTENCE = ("Something that is not a file stands where an older version of the app kept "
                                 "saved charts, so it was not read.")
# SB-11 (ruling 157; the owner's sentence, ruling 160): preferences switched off
# for this launch (ALMUTEN_NO_PREFERENCES, the test harness's switch) are said
# on every run while they are off.
PREFERENCES_OFF_SENTENCE = "Preferences are off for this launch, so no choice made in it will be kept."
# SC-09 of the notes lanes (2026-10-06): a choice the preferences file did
# not take (a link into a folder this account cannot write in, a folder
# that cannot be written in or is gone, a file that can be neither read nor
# copied aside) said nothing, and the window went on showing it as made.
# Ruling 93: it is said, in the run of the choice (K-1), and nothing is
# tried again on a later run; the window keeps the reader's value, and the
# sentence says the file did not.
PREFERENCES_REFUSED_SENTENCE = ("The preferences file was not written, so this choice was not kept. "
                                "Try again once it can be written.")


def _note_busy_preferences():
    """Ruling 77: after a write of the preferences, leave the sidebar its
    sentence if the write gave up on the lock. K-2: this window's write.
    Ruling 109: or the folder in which something stands under the lock's
    name."""
    found = engine.preferences_notices()
    if found["busy"]:
        st.session_state["_prefs_busy_notice"] = True
    if found["blocked"]:
        st.session_state["_prefs_blocked_notice"] = found["blocked"]


def _note_refused_preferences(kept):
    """SC-09, ruling 93: after a write of the preferences the file did not
    take (`kept` False) for a cause other than the lock held or blocked,
    whose sentence is the busy one (or ruling 109's), leave the sidebar its
    sentence, said in that run (K-1); a folder that refuses the lock call
    itself is such a cause.
    Every such choice is told: the folder's standing sentence says why the
    preferences cannot be kept, this one that this choice was not."""
    found = engine.preferences_notices()
    if not kept and engine.preferences_enabled() and not found["busy"] and not found["blocked"]:
        st.session_state["_prefs_refused_notice"] = True


def _data_folder_refusal():
    """L6R-N4: the sentence for a folder the saved charts and the
    preferences cannot be kept in, or None when it can be used. Said in the
    sidebar while it stands, and by Save and "Set as home" when pressed.
    K-09 of the re-pass's follow-ups: a folder that is there but that this
    account cannot enter or write in is said too, each in its own words.

    One that cannot be entered also explains an empty picker -- but only
    when the picker is empty. The KB check found the clause false where this
    window read the saved charts before the folder was shut: the picker
    beside the sentence listed them and opened them. It says "any", since a
    folder that cannot be entered cannot say whether it holds a chart."""
    what, problem = engine.data_folder_state()
    if what is None:
        return None
    if what == 'opened':
        listed = any(k != NEW_CHART_SENTINEL for k in st.session_state.get("saved_charts", {}))
        clause = "" if listed else ", so any saved charts in it are not listed"
        return (f"Saved charts and preferences cannot be kept: their folder, `{engine.DATA_DIR}`, "
                f"cannot be opened ({problem}){clause}. "
                "Nothing can be saved and no home can be set until it can.")
    return (f"Saved charts and preferences cannot be kept: their folder, `{engine.DATA_DIR}`, "
            f"{'could not be made' if what == 'made' else 'cannot be ' + what} ({problem}). "
            "Nothing can be saved and no home can be set until it can.")

# Preferences: read once per session into the store keys that nothing has
# set yet (a test's seeded session_state wins), written back through
# _remember() whenever _persist() moves a reading, so the file is the
# stores' shadow and never a second source of truth.
if "_prefs" not in st.session_state:
    st.session_state["_prefs"] = load_preferences()
    _note_unreadable_preferences()
    for _key, _value in st.session_state["_prefs"].items():
        if _key in PREFERENCE_KEYS and _key not in st.session_state:
            st.session_state[_key] = _value

def _remember(key, value, chosen=False, quiet=False):
    """Keep `key` = `value` in the preferences file, if it is a preference
    and it changed; False when a write was needed and the file did not take
    it (or preferences are off), else True. What is written is that one
    key, into the file as it stands now (L6R-N6), so a home place or a last
    chart another window has set since this session read the file stays in
    it.

    "Changed" is judged two ways. A control's value is restated on every
    run (_persist), so for it a change is a move of this window's own
    control, judged against the session's own copy: a rerun of a window
    whose readings another window has since changed writes nothing over
    them. A choice the reader has just made (`chosen`: a chart opened or
    saved, a home set, a record's readings put in force) is judged against
    the file as it stands, by remember_preference (K-10 of the re-pass's
    follow-ups: a window opening again the chart it last opened, after
    another window had opened another, left the other's in the file, its
    own copy already saying this one).

    SC-09 and ruling 93: a choice the file did not take is said in its run
    (K-1), and is not tried again: the window's copy takes the value as it
    always did, so a control restating it is not a new choice. `quiet`: say
    nothing of a refusal -- the caller says it where it was pressed ("Set
    as home"), or there was no choice of the reader's to speak of (the
    launch's count)."""
    prefs = st.session_state["_prefs"]
    if not (key in PREFERENCE_KEYS or key == 'last_chart'):
        return False
    if not chosen and prefs.get(key) == value:
        return True
    prefs[key] = value
    kept = engine.remember_preference(key, value, fallback=prefs)
    _note_unreadable_preferences()
    if not quiet:
        _note_busy_preferences()
        _note_refused_preferences(kept)
    return kept

def _forget(key, only_if=None, quiet=False):
    """Remove `key` from the session's copy and from the file as it stands
    (L6R-N6), and nothing else from either. With `only_if`, only where the
    value is still that one: a last chart is forgotten because its record
    was deleted, and a last chart another window has opened since is not
    that record. True when the file no longer holds it (SC-12); `quiet` as
    in _remember ("Forget home" says its own refusal; the last chart
    forgotten after a delete is no choice of the reader's, whose delete
    was kept)."""
    prefs = st.session_state["_prefs"]
    if only_if is None:
        prefs.pop(key, None)
        forgotten = engine.forget_preference(key, fallback=prefs)
    else:
        if prefs.get(key) == only_if:
            del prefs[key]
        forgotten = engine.forget_preference(key, only_if=only_if, fallback=prefs)
    _note_unreadable_preferences()
    if not quiet:
        _note_busy_preferences()
        _note_refused_preferences(forgotten)
    return forgotten

# The example nativity this app opens on -- Florence, 1240-05-23, 14:30 LMT
# -- as the sidebar's own widgets default to it, in one place so that the
# boxes and the reset below cannot come to disagree.
EXAMPLE_CHART = {
    "date_input_key": "1240-05-23",
    "time_input_key": time(14, 30),
    "time_standard_key": TIME_STANDARD_OPTIONS[0],
    "utc_offset_key": 0.0,
    "manual_coords_key": False,
    "location_input_key": "Florence",
    "manual_lat_key": 43.7698,
    "manual_lon_key": 11.2556,
}

# --- The readings, named before the picker ------------------------------
# A reading is READ at the top level (further down, where the engine's
# per-run values are pinned) because the evaluators read these globals at
# call time. The registry and the reader itself stand HERE, above the
# saved-chart picker, because from 2026-09-16 a saved record carries the
# readings it was saved under (F03 of the review of that date) -- so the
# record cannot be built, compared or restored without them.
def _reading(widget_key, store_key, default):
    """This run's value for a reading. The widget key is preferred when
    present: on the rerun a change triggers, the widget already carries the
    new value while the store still holds the old one."""
    return st.session_state.get(widget_key, st.session_state.get(store_key, default))


# Every doctrinal reading, for the Sources page's table of what is in force
# and its reset, for the readings a record is saved with, and for the
# analysis export. (label, widget key, store key, default, page it is set on)
READINGS_REGISTRY = (
    ("Connection test used in the shared tables", "connection_rule", "_connection_rule", "Sahl", "Configurations"),
    ("Gr. Intr. VII.6, 27/45 eastern/western relative to the Sun", "eastern_rule", "_eastern_rule", EASTERN_RULE_OPTIONS[0], "Configurations"),
    ("Fitting infortune (Choices Ch. 1, 12)", "fitting_infortune", "_fitting_infortune", False, "Configurations"),
    ("Moon under the rays to 15 degrees", "moon_rays_15", "_moon_rays_15", False, "Chart"),
    ("Mars under the rays to 18 degrees west", "mars_west_18", "_mars_west_18", False, "Chart"),
    ("Domain (hayz)", "domain_rule", "_domain_rule", DOMAIN_RULE_OPTIONS[0], "Dignities and places"),
    ("House-based Lot construction", "lot_house_cusp", "_lot_house_cusp", LOT_HOUSE_CUSP_OPTIONS[0], "Lots"),
    ("Monthly profections turn", "pn4_monthly_turn", "_pn4_monthly_turn", PN4_MONTHLY_TURN_OPTIONS[0], "Days and months"),
    ("Sources shown", "reading_depth", "_reading_depth", READING_DEPTH_OPTIONS[0], "Sources and readings"),
)


def _current_readings():
    """The doctrinal readings in force, as a record writes them:
    {store key: value}, exactly what the top level reads a moment later."""
    return {store_key: _reading(widget_key, store_key, default)
            for _label, widget_key, store_key, default, _page in READINGS_REGISTRY}


def _readings_differ_from(saved):
    """The stored readings that are not the ones in force, as
    {store key: the value the record was saved under}. Only the keys the
    record carries are looked at, and only the ones this app knows."""
    return {sk: saved[sk]
            for _label, wk, sk, default, _page in READINGS_REGISTRY
            if sk in saved and saved[sk] != _reading(wk, sk, default)}


def _set_reading(widget_key, store_key, value):
    """Put one reading in force as though its own control had been moved:
    the store key the top level reads, the widget key the control will be
    drawn from, and the preferences file, which is what _persist() does
    when a reader moves the control themselves."""
    st.session_state[store_key] = value
    st.session_state[widget_key] = value
    _remember(store_key, value, chosen=True)


# The picker's first option, which is not a chart but the act of starting
# one. M3 of the hostile pass of 2026-09-16: a chart could be SAVED under
# this very string, after which the picker listed it twice and the record
# could be neither selected nor deleted -- the option that means "new
# chart" cannot also mean "that chart". Named here so that the save can
# refuse it.
NEW_CHART_SENTINEL = "-- New Chart --"


def _is_reserved_name(name):
    """Whether a chart name would collide with the picker's own first
    option. Case and spacing do not save it: '--new chart--' and
    '-- NEW CHART --' read as the same option in the list."""
    def _flat(text):
        return re.sub(r"\s+", "", str(text)).casefold()
    return _flat(name) == _flat(NEW_CHART_SENTINEL)


# L6R-N8 of the re-pass of 2026-10-04: a chart's name or a place label in
# the Markdown the strip and the sidebar's sentences are drawn from. Streamlit
# draws Markdown in two passes, and a backslash escape reaches only the
# first. It parses the text (emphasis, code, links, HTML, character
# references, math, its ":red[...]" directives), and then it rewrites the
# parsed TEXT -- where every escape has already been resolved -- turning
# "https://", "www." and mail addresses into links, ":streamlit:" into its
# logo, ":material/home:" into an icon, ":smile:" into an emoji and " -- ",
# " -> ", " <= " into dashes and arrows. Text inside a code span is not
# parsed, and the second pass does not look into it. So a name holding none
# of what either pass acts on is printed as it is, and any other is printed
# as a code span, character for character. "Manual [43.7792, 11.2463]", the
# app's own label for typed coordinates, holds none: a bracket makes a link
# only as "](" or under a reference defined with a colon.
_PLAIN_TEXT = re.compile(r"[^\\`*_{}<>#|$~:&@^]*")
_NOT_PLAIN = re.compile(r"\]\(|--|www\.|^[+\-](?:\s|$)|^\d+[.)](?:\s|$)", re.I)
_BACKTICKS = re.compile(r"`+")


# _isolated, which sets a name that could turn the text around it right to
# left between FIRST STRONG ISOLATE and POP DIRECTIONAL ISOLATE (R4), is
# engine.py's, since the HTML export and the wheel isolate a name as the
# pages do (SB-08).


def _code_span(text):
    """`text` as one Markdown code span: a fence longer than any run of
    backticks inside it, and a space inside each fence when the text begins
    or ends with a backtick or a space (Markdown strips one from each side)."""
    fence = "`" * (max((len(run) for run in _BACKTICKS.findall(text)), default=0) + 1)
    pad = " " if text[:1] in ("`", " ") or text[-1:] in ("`", " ") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _names_something(value):
    """Whether a label has a character a reader can see: a label of
    separators and format characters only (a zero-width space, U+200B,
    which is not whitespace to Python) names nothing, as a label of spaces
    names nothing (K-29), and the sidebar's box and the strip print the
    coordinates alone for it."""
    return any(not (unicodedata.category(ch).startswith("Z") or unicodedata.category(ch) == "Cf"
                    or ch.isspace()) for ch in str(value))


def _as_typed(value, quoted=False):
    """A chart's name or a place label, as it was typed, for the strip or a
    sidebar sentence (L6R-N8: "Smith *draft* $x$" was printed in italics and
    as math). One line, as the Markdown export's title is (L6-08), so a
    newline in a hand-edited record cannot open a heading of its own. A
    plain name is printed as it is -- in quotes with `quoted`, as the
    sentences name a chart -- and any other as a code span, whose box is its
    quotation marks. Streamlit rewrites ":material/" to ":material_" in the
    whole text before parsing it, code spans and all, so there the slash
    stands between two spans. A name that could turn the text around it
    right to left is isolated (_isolated)."""
    text = " ".join(str(value).split())
    if _PLAIN_TEXT.fullmatch(text) and not _NOT_PLAIN.search(text):
        return f"'{_isolated(text)}'" if quoted else _isolated(text)
    pieces = text.split(":material/")
    pieces = [piece + ":material" for piece in pieces[:-1]] + pieces[-1:]
    return "/".join(_code_span(_isolated(piece)) if piece else "" for piece in pieces)


def _offset_text(hours, seconds=False):
    """An offset from UTC as the sidebar's box and the chart strip print it,
    from one rounded total of seconds: signed, hours and minutes, and the
    seconds -- always with `seconds`, as LMT's are, and otherwise whenever
    the offset holds any, as a named zone's history does (L1-N4: 5.125 h is
    cast at +05:07:30, and was labelled +05:07). An offset that rounds to no
    seconds at all is signed +, wherever it is printed (L1-N5: the box said
    +00:00:00 and the strip -00:00:00 a thousandth of a degree west)."""
    total = int(round(abs(hours) * 3600))
    text = (f"{'-' if hours < 0 and total else '+'}"
            f"{total // 3600:02d}:{(total % 3600) // 60:02d}")
    if seconds or total % 60:
        text += f":{total % 60:02d}"
    return text


# The clocks of the areas where the sources leave the clock to the record
# (time_zones.PLACE_ZONE_AREAS; rulings 180 (2), 190), named as the outside
# research names them (process/outside_tasks_sol_2026-10-06/
# DISPUTED_CLOCKS_RAW.md, its neutral sentences): each is a clock and its
# zone, never a claim on the place.
AREA_CLOCK_NAMES = {
    'west_bank': {'Asia/Hebron': "Palestinian civil time", 'Asia/Jerusalem': "Israeli civil time"},
    'xinjiang': {'Asia/Shanghai': "Beijing time", 'Asia/Urumqi': "Xinjiang time"},
    'cyprus_boundary': {'Asia/Nicosia': "the southern clock", 'Asia/Famagusta': "the northern clock"},
    'saskatchewan': {'America/Regina': "the Central clock", 'America/Swift_Current': "the Mountain clock"},
    'sokhumi': {'Europe/Moscow': "Moscow time", 'Asia/Tbilisi': "Tbilisi time"},
}


def _local_reading_text(reading, day=None):
    """A local reading (year, month, day, hour, minute, second) as the
    sentences below print it: the date, and the time when it is not
    midnight; only the time when its date is `day`."""
    date = f"{reading[0]:04d}-{reading[1]:02d}-{reading[2]:02d}"
    clock = f"{reading[3]:02d}:{reading[4]:02d}" if reading[3:] != (0, 0, 0) else ""
    if day == date and clock:
        return clock
    return f"{date} {clock}".strip()


# The named-zone refusals name each option to choose by its own label, as the
# time-standard box shows it, as _clock_choice_sentence below does for its
# remedy, so a sentence cannot drift from the box.
_LMT_OR_MANUAL = f"{TIME_STANDARD_OPTIONS[0]} or {TIME_STANDARD_OPTIONS[2]}"
_CHOOSE_BY_LONGITUDE = (f"Choose {TIME_STANDARD_OPTIONS[0]}, which takes the birthplace's own longitude, "
                        f"or {TIME_STANDARD_OPTIONS[2]}.")


def _clock_choice_sentence(refusal, local_dt):
    """The sentence for a Standard-time cast refused where the sources leave
    the clock open (NamedZoneRefusal 'clock_choice' or 'unsettled'): both
    clocks, the offset each gives at this moment, and the manual offset as
    the way to cast with either."""
    names = AREA_CLOCK_NAMES.get(refusal.area or "", {})
    clocks = []
    for zone, offset in refusal.clocks or ():
        clock = f"{names[zone]} ({zone})" if zone in names else zone
        clocks.append(f"{clock} gives UTC{_offset_text(offset / 3600.0)}" if offset is not None
                      else f"{clock} cannot place it")
    pair = " and ".join(clocks)
    when = f"**{local_dt:%Y-%m-%d %H:%M}**"
    # Ruling 201 (2): the option by its own label, as the time-standard box shows it.
    remedy = f"Choose {TIME_STANDARD_OPTIONS[2]} and enter the offset of the clock the time was recorded in."
    if refusal.kind == 'unsettled':
        return (f"{when}: the sources this app holds do not settle which clock this place keeps: {pair} at "
                f"this moment. {remedy}")
    if refusal.interval:
        start, end = refusal.interval
        if tuple(start) == engine._BEFORE:
            span = f"before {_local_reading_text(end)}"
        else:
            first = _local_reading_text(start)
            span = f"between {first} and {_local_reading_text(end, first.split()[0])}"
        return (f"{when}: the sources do not settle which clock was kept at this place {span}: {pair} at this "
                f"moment. {remedy}")
    return (f"{when}: at this place the sources leave the clock to the record, and its two clocks differ at this "
            f"moment: {pair}. {remedy}")


# The keys a new chart drops rather than sets: the target of the Prediction
# pages (widget and store alike, so the year block seeds them afresh),
# the label a loaded chart put on its coordinates, the legacy-record flag,
# and the last date that parsed.
_NEW_CHART_DROPS = ("target_date", "_target_date", "target_age", "_target_age",
                    "_target_last_good", "loaded_location",
                    "_loaded_without_standard", "_loaded_unoffered_standard", "_date_last_good",
                    # what the last record loaded said about itself (H3, H5):
                    # a new chart is not that record
                    "_record_notice", "_record_refused", "_record_loaded",
                    # nor is it the record whose readings were put to the
                    # reader, or the old one that had none to put (F03)
                    "_readings_pending", "_readings_legacy")


def _new_chart_form():
    """Put the example nativity back in the sidebar's boxes. Selecting
    '-- New Chart --' is a NEW CHART, not a deselection: the review found it
    keeping the edited date and place of the record just left, so that the
    next save wrote one chart under another chart's name (F04).

    The form only. The preferences file is not touched and 'last_chart' is
    not forgotten, so the next launch still opens on the last chart saved or
    loaded -- the reading taken of a new chart being an unsaved draft, which
    has nothing to be opened on."""
    for key, value in EXAMPLE_CHART.items():
        st.session_state[key] = value
    # The store only; the widget key is dropped with the rest, for the
    # reason given in _restore_chart.
    st.session_state["_target_mode"] = TARGET_MODE_OPTIONS[0]
    st.session_state.pop("target_mode", None)
    for key in _NEW_CHART_DROPS:
        st.session_state.pop(key, None)


def _apply_selected_chart():
    """on_change callback: runs before the script reruns, so writing into
    these session_state keys here makes the widgets below pick up the
    loaded values on this same rerun. The chart loaded becomes the one the
    app opens on next time (preference 'last_chart', 2026-09-10)."""
    name = st.session_state.get("chart_picker")
    if name and name != NEW_CHART_SENTINEL:
        # A record the sidebar cannot load is not the chart the app opens
        # on next time either: the fields have not moved, and nothing has
        # been loaded to remember.
        if _restore_chart(name):
            _remember('last_chart', name, chosen=True)
    else:
        _new_chart_form()

def _restore_chart(name):
    """Write a saved chart's fields into the sidebar widgets' keys. True
    when the record was loaded, False when it was refused.

    H3 of the hostile pass of 2026-09-16: the fields were written into the
    widget keys unread, so a record whose fields are the wrong TYPE -- an
    int time_string, a str latitude, an "abc" target_age, from a hand-edit
    or an import -- raised where the value was consumed and took the whole
    script down: on the selection, and at launch when it was the last
    chart, which made the app dead-on-open. The record is read first
    (chart_record_fault, engine): a fault leaves every widget exactly as it
    was, leaves the record in the file untouched, and leaves one sentence
    in _record_notice for the sidebar to show beside the picker."""
    entry = st.session_state["saved_charts"].get(name, {})
    # K-14, K-15 of the re-pass's follow-ups (2026-10-05): what the boxes
    # were last asked to hold is remembered with the record as it was asked
    # of -- refused (_record_refused, with the sentence that said why) or
    # loaded (_record_loaded) -- so that the strip and the refusal speak of
    # the record as the store now holds it, not of a name another window has
    # since written a different record under.
    st.session_state.pop("_record_refused", None)
    st.session_state.pop("_record_loaded", None)
    fault = chart_record_fault(entry)
    if fault is not None:
        field, expected = fault
        _refuse_record(name, entry,
                       f"{_as_typed(name, quoted=True)} could not be loaded: its {field} is not a {expected}.")
        return False
    # L6R-N3: a record lacking its date, its time, or under the manual
    # standard its offset -- or, K-11, its place (neither coordinates nor a
    # place query) -- is refused the same way (chart_record_lack, engine):
    # the boxes keep what they hold, and no chart is cast under the record's
    # name with the previous chart's value for the missing field.
    # The refusal is remembered with the record refused, for the strip and
    # the "edited since it was saved" caption below: the picker still names
    # the record, and the boxes do not hold it.
    lack = chart_record_lack(entry)
    if lack is not None:
        _refuse_record(name, entry, f"{_as_typed(name, quoted=True)} could not be loaded: it holds no {lack}.")
        return False
    st.session_state.pop("_record_notice", None)
    if True:
        if "date_string" in entry:
            st.session_state["date_input_key"] = entry["date_string"]
        if "time_string" in entry:
            try:
                h, m, s = (int(x) for x in entry["time_string"].split(":"))
                st.session_state["time_input_key"] = time(h, m, s)
            except (ValueError, KeyError, AttributeError):
                pass
        # The time standard (2026-09-10). An entry saved before it was
        # stored is flagged rather than silently cast at LMT: the owner's
        # reference nativity, recorded EST, loaded forty minutes wrong.
        # SC-02 of the notes lanes (R2-07 of Sol's pass): an entry that
        # stores a standard this app does not offer ("Eastern War Time", a
        # hand edit's) was told it had been saved before the standard was
        # stored, which it was not, and the label it holds was named
        # nowhere. It has its own sentence, naming the label as it is
        # stored and the standard the chart is cast under -- the one the
        # box already holds, which the load leaves as it was.
        _stored_standard = entry.get("time_standard")
        _standard = time_standard_current(_stored_standard)
        st.session_state.pop("_loaded_unoffered_standard", None)
        if isinstance(_standard, str) and _standard in TIME_STANDARD_OPTIONS:
            st.session_state["time_standard_key"] = _standard
            st.session_state.pop("_loaded_without_standard", None)
        elif _stored_standard is None:
            st.session_state["_loaded_without_standard"] = name
        else:
            st.session_state.pop("_loaded_without_standard", None)
            st.session_state["_loaded_unoffered_standard"] = {"name": name, "label": _stored_standard}
        # H5: an offset outside +-14 is NOT written to the widget. Streamlit
        # pulls a seeded value out of a number_input's bounds to a bound --
        # and to the wrong one: a stored 99 came back as -14, and the chart
        # was cast at UTC-14:00 with nothing said, while a re-save wrote the
        # clamp into the record. The record keeps its 99, the box keeps the
        # offset a chart is cast at by default, the sidebar says what was
        # stored, and the strip reads (modified) because the two differ --
        # which is the truth of it.
        if entry.get("utc_offset") is not None:
            if utc_offset_in_range(entry["utc_offset"]):
                st.session_state["utc_offset_key"] = record_number(entry["utc_offset"])
            else:
                st.session_state["utc_offset_key"] = EXAMPLE_CHART["utc_offset_key"]
                st.session_state["_record_notice"] = (
                    f"{_as_typed(name, quoted=True)} was saved with a UTC offset of {entry['utc_offset']}, "
                    "outside ±14; check the time standard.")
        # The target of the Prediction pages: the store the engine reads
        # is written and the page widgets' keys are dropped, so the year
        # block seeds its widgets from the store on its next render
        # (_carry). Until 2026-09-17 the widget keys were written too, as
        # plain values, and a plain value written for a widget that is not
        # rendered on that run is never refreshed by Streamlit's state
        # compaction once the widget exists (SessionState._keys converts a
        # mapped key to its element id first): it stood in _old_state
        # under the bare key with the record's value, and came back as
        # the widget's value every time the widget went stale on a
        # Nativity page -- the age set on Timing reverted to the record's
        # after a visit to the Chart page. Read at the top level through
        # _reading, which prefers the widget key.
        if entry.get("target_mode") in TARGET_MODE_OPTIONS:
            st.session_state["_target_mode"] = entry["target_mode"]
            st.session_state.pop("target_mode", None)
            if entry.get("target_date"):
                st.session_state["_target_date"] = entry["target_date"]
                st.session_state.pop("target_date", None)
            if entry.get("target_age") is not None:
                st.session_state["_target_age"] = int(record_number(entry["target_age"]))
                st.session_state.pop("target_age", None)
        if entry.get("lat") is not None and entry.get("lon") is not None:
            # Restore via Manual Coordinate Entry, using the saved lat/lon
            # directly, rather than re-running a City Search text query --
            # which would receive the already-resolved display label (e.g.
            # "Petoskey, MI (US)") as its search term and reliably match
            # nothing, since city names in atlas.db don't include the
            # ", State (Country)" suffix. This also correctly restores
            # charts that were originally entered via Manual Coordinate
            # Entry in the first place, which a location_query of
            # "Manual [lat, lon]" could never do by re-searching either.
            # As NUMBERS: a record can hold a coordinate written as text
            # ('43.7792'), which the comparison already reads as that
            # coordinate, and a string in a number_input's key raised
            # where the widget compared it with its own bounds (H3).
            _lat, _lon = record_number(entry["lat"]), record_number(entry["lon"])
            st.session_state["manual_coords_key"] = True
            st.session_state["manual_lat_key"] = _lat
            st.session_state["manual_lon_key"] = _lon
            st.session_state["loaded_location"] = {
                "lat": _lat,
                "lon": _lon,
                "label": entry.get("location_query", ""),
            }
        elif "location_query" in entry:
            # Saved before lat/lon capture was added -- best effort only,
            # since atlas.db matching needs a raw city name, not the old
            # free-text/resolved-label value this field used to hold.
            st.session_state["manual_coords_key"] = False
            st.session_state["location_input_key"] = entry["location_query"]
            # Ruling 145 (B-02, the check's 3d): the pair kept for the text
            # the coordinate switch wrote is not this record's, though its
            # text may read the same; the record is cast from what it holds.
            st.session_state.pop("_coords_off_pair", None)
    # The readings the record was saved under (F03). NOTHING is set here:
    # the load restores a nativity, and which readings it is to be read
    # under is the reader's to say. What is left behind is the question --
    # or, for a record written before this app stored them, the one
    # sentence that says there is no question to ask.
    st.session_state.pop("_readings_pending", None)
    st.session_state.pop("_readings_legacy", None)
    saved_readings = chart_record_readings(entry)
    if not saved_readings:
        st.session_state["_readings_legacy"] = name
    elif _readings_differ_from(saved_readings):
        st.session_state["_readings_pending"] = name
    st.session_state["_record_loaded"] = {"name": name, "record": entry}
    return True


def _same_record(stored, remembered):
    """Whether the record the store holds under a name is still the record
    remembered under it (K-14, K-15): the same fields, each holding the same
    value, a number compared as the number it means to four places -- as
    _record_inputs_match compares one, since a record read back can hold a
    latitude as text or 11.0 as 11 and is the same record for it. The stamp
    is not compared (it never is: _RECORD_NOT_INPUT). A field gained or lost
    makes another record: one made to lack its time under an open window is
    not the record the boxes were loaded from. The stamp is a field of
    neither kind (SC-16 of the notes lanes: a record that had only gained
    or lost its stamp was taken for another, against the sentence above)."""
    if stored is remembered:
        return True
    if not (isinstance(stored, dict) and isinstance(remembered, dict)):
        return False
    if set(stored) - {"saved_with"} != set(remembered) - {"saved_with"}:
        return False
    for field, value in remembered.items():
        if field == "saved_with":
            continue
        other = stored[field]
        if other == value:
            continue
        a, b = record_number(value), record_number(other)
        if a is None or b is None or round(a, 4) != round(b, 4):
            return False
    return True


def _refuse_record(name, entry, sentence):
    """The loader's refusal of `entry` under `name`: the sentence beside the
    picker, and the refusal remembered with the record refused and the
    sentence said of it (K-15). The record is never altered: the mapping's
    records are replaced, never written into, so the record kept here is
    the record as it was refused."""
    st.session_state["_record_notice"] = sentence
    st.session_state["_record_refused"] = {"name": name, "record": entry, "sentence": sentence}

# L6-07: a record named exactly like the first option would be listed twice
# and could be neither selected nor deleted; it stays in the file, untouched,
# and is not offered.
chart_options = [NEW_CHART_SENTINEL] + sorted(k for k in st.session_state["saved_charts"].keys()
                                              if k != NEW_CHART_SENTINEL)
# The app opens on the chart it was last working on (owner's decision
# 2026-09-10), unless something has already seeded the sidebar -- the
# harness does, and a fresh session has not.
LAUNCH_COUNT = 0          # bound every run; the count is set just below, once per session
if "_autoload_done" not in st.session_state:
    st.session_state["_autoload_done"] = True
    # One launch, counted once: this block runs exactly once per session.
    # The count includes the launch in hand, and it is what decides whether
    # the Chart page's introduction stands open or folded -- three
    # paragraphs that are read once and then in the way. A count already in
    # the session that the file did not put there is a test's, and is left
    # as it stands, which is the same rule the preferences read above
    # follows: a seeded session_state wins.
    if '_launches' not in st.session_state or '_launches' in st.session_state["_prefs"]:
        st.session_state["_launches"] = int(st.session_state["_prefs"].get('_launches', 0) or 0) + 1
        _remember('_launches', st.session_state["_launches"], quiet=True)
    _last = st.session_state["_prefs"].get('last_chart')
    if (_last in st.session_state["saved_charts"] and _last != NEW_CHART_SENTINEL
            and "date_input_key" not in st.session_state):
        # H3: the launch survives a last chart it cannot load -- the app
        # opens on no chart at all, with the sentence beside the picker,
        # where it used to open on a traceback and nothing else. The picker
        # is only pointed at the record when the record was loaded, so that
        # it never names a chart the boxes do not hold.
        if _restore_chart(_last):
            st.session_state["chart_picker"] = _last
# Read at the top level on every run, as every other reading is, so that a
# fragment rerun and a page change see the same number the launch set.
LAUNCH_COUNT = int(st.session_state.get("_launches", 0) or 0)
# A selection the script makes rather than the reader -- the record just
# saved, the picker after a delete -- is left here by the run that makes it
# and applied by the next one, because a widget's key cannot be assigned
# once the widget has been drawn (F04, item 1: the picker's options were
# built before the Save button ran, so a save reported success while the
# picker and the strip still said the chart was unsaved). The picker's
# on_change does not fire for a selection made this way, which is right:
# the fields already hold the values that were just written.
_selection = st.session_state.pop("_select_after_rerun", None)
if _selection is not None:
    st.session_state["chart_picker"] = _selection
    # The record this window has just written under the name is the one its
    # boxes hold (K-14, K-15): whatever the loader refused or loaded under
    # that name before, the strip now names what was written.
    if _selection != NEW_CHART_SENTINEL and _selection in st.session_state["saved_charts"]:
        st.session_state.pop("_record_refused", None)
        st.session_state["_record_loaded"] = {"name": _selection,
                                              "record": st.session_state["saved_charts"][_selection]}


# --- Here & Now: a chart for the home place at this moment -----------------
# "Here" is a STORED home place (the owner's ruling): the reader sets it
# from the birthplace the sidebar has already resolved, with the button in
# the "Home" popover of the sidebar's first row, and it is kept in the
# preferences file as 'home_place' -- not browser geolocation, not a
# lookup; this app is desktop only and offline. "Now" is this computer's
# clock, read through engine.now_utc() so that a test can freeze it.
def _home_place():
    """The home place in force, or None: the session's copy of the
    preference (the launch copies the file's; "Set as home" writes both),
    read through the same validator the loader uses so that a seeded shape
    the file would have refused is refused here too."""
    home = st.session_state.get("home_place")
    return home if home_place_is_valid(home) else None


_NOT_IN_PREFS = object()


def _forget_home_place():
    """on_click of "Forget home": the session's copy and the file's.

    SC-12 of the notes lanes (2026-10-06): in a folder that could not be
    written in, the session forgot the home and the file kept it, with
    nothing said, so the next launch brought it back. "Forget home" now
    refuses as "Set as home" does: with the folder's sentence while the
    folder cannot be used, else with the lock's or the file's own when the
    file does not take it; and the session keeps the home the file keeps.
    With preferences off the session's home is the only one there is.

    S07 of lane SC2 (the outside audit of face757; SC_CHECK's note 16): a
    refused forget kept the session's home but had already taken it out of
    the window's copy of the file (_forget), which is what an unreadable file
    is rebuilt from: the next choice that rebuilt it wrote it without the
    home the window still used. The copy keeps the home the file keeps."""
    refusal = _data_folder_refusal()
    if refusal:
        st.session_state["_home_refused_notice"] = refusal
        return
    prefs = st.session_state["_prefs"]
    kept = prefs.get("home_place", _NOT_IN_PREFS)
    if _forget("home_place", quiet=True) or not engine.preferences_enabled():
        st.session_state.pop("home_place", None)
        return
    if kept is not _NOT_IN_PREFS:
        prefs["home_place"] = kept
    found = engine.preferences_notices()
    if found["blocked"]:
        st.session_state["_home_refused_notice"] = _prefs_blocked_sentence(found["blocked"])   # ruling 109
    elif found["busy"]:
        st.session_state["_home_refused_notice"] = PREFERENCES_BUSY_SENTENCE
    else:
        st.session_state["_home_refused_notice"] = ("This home could not be forgotten: the preferences file "
                                                    "could not be written.")


def _here_and_now():
    """on_click of "Here & Now": the sidebar's boxes are written with the
    home place and this moment, exactly as _restore_chart writes them for a
    saved record -- a callback runs BEFORE the widgets of the rerun it
    triggers, so the keys written here are what the widgets are drawn from.

    The instant is read ONCE, in UTC. When the home falls inside a named
    zone the instant is converted to that zone's clock and the standard is
    Standard time, so the sidebar's own zone branch resolves the same
    offset from the same name; when TimezoneFinder has no zone for the
    point the instant is converted to this computer's own clock and the
    standard is Manual with that clock's offset, so the instant is right
    either way (the timezonefinder this app ships answers an ocean zone,
    Etc/GMT+2 and the like, at sea, so the second path is a guard for a
    None the sidebar's own branch also provides for rather than a path a
    chart is expected to take). One more case falls to Manual: the
    repeated hour of a zone's fall-back, which the Standard branch refuses
    as ambiguous (it is), so the offset the instant actually has is
    written instead.

    The date box's calendar rule and the ephemeris span need no handling
    here: now is Gregorian and inside the span. The picker is left as it
    is -- a loaded record then reads (modified) in the strip, which is the
    truth -- and the Prediction target keys are not touched: a chart cast
    now is at age 0 on those pages, which is correct. Nothing is saved."""
    home = _home_place()
    if home is None:
        return
    lat, lon = home["lat"], home["lon"]
    instant = engine.now_utc()
    # The home's zone as the sidebar's own branch resolves it (place_zone,
    # given this callback's own finder): the zone boundaries' answer, or the
    # list's or an area's. A place whose clock the sources leave open is
    # refused there, and takes the computer's clock here, as a point at sea
    # does: the person's own clock is the one this computer keeps.
    finder = TimezoneFinder()
    try:
        zone_name = engine.place_zone(lat, lon, finder)
    except engine.NamedZoneRefusal:
        zone_name = None
    if zone_name:
        try:
            zone = ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            zone = None
    else:
        zone = None
    if zone is not None:
        local = instant.astimezone(zone)
        try:
            # The moment's own rule (an area's two clocks, a dated rule) can
            # name another zone: the instant is read in that one.
            moment_zone = engine.place_zone(lat, lon, finder, (local.year, local.month, local.day,
                                                               local.hour, local.minute, local.second))
            if moment_zone and moment_zone != zone_name:
                zone_name, local = moment_zone, instant.astimezone(ZoneInfo(moment_zone))
            engine.named_zone_state(zone_name, local.year, local.month, local.day,
                                    local.hour, local.minute, local.second)
        except engine.NamedZoneRefusal as refusal:
            # The repeated hour of a fall-back writes the offset the instant
            # actually has; a nautical zone (a point at sea) is the Standard
            # branch's own refusal, so it takes the computer's clock too, and
            # so does a place whose clock the sources leave to the person.
            if refusal.kind in ('sea', 'clock_choice', 'unsettled'):
                local = engine.local_clock(instant)
            standard = TIME_STANDARD_OPTIONS[2]
        else:
            standard = TIME_STANDARD_OPTIONS[1]
    else:
        local = engine.local_clock(instant)
        standard = TIME_STANDARD_OPTIONS[2]
    offset_hours = None
    if standard == TIME_STANDARD_OPTIONS[2]:
        offset_hours = local.utcoffset().total_seconds() / 3600.0
        # Never an offset outside the number_input's bounds (H5). A clock
        # cannot give one short of a broken TZ string, but when it does the
        # cast is REFUSED, before anything is written: a Manual standard
        # with the old offset left underneath would cast a wrong chart
        # with nothing said. The sentence stands in the notice slot beside
        # the picker until the next load, new chart or save clears it.
        if not utc_offset_in_range(offset_hours):
            st.session_state["_record_notice"] = (
                "This computer's clock has an offset outside ±14 hours, "
                "so Here & Now cast nothing.")
            return
    st.session_state["time_standard_key"] = standard
    if offset_hours is not None:
        st.session_state["utc_offset_key"] = float(offset_hours)     # quarter-hours stand
    st.session_state["date_input_key"] = f"{local.year:04d}-{local.month:02d}-{local.day:02d}"
    st.session_state["time_input_key"] = time(local.hour, local.minute, local.second)
    st.session_state["manual_coords_key"] = True
    st.session_state["manual_lat_key"] = float(lat)
    st.session_state["manual_lon_key"] = float(lon)
    # The coordinate fields show the home's name rather than a bare pair
    # (the loaded-label rule under the fields).
    st.session_state["loaded_location"] = {"label": home["label"], "lat": float(lat), "lon": float(lon)}
    # What the record loaded said about itself is popped where the cast
    # makes it false or answers it: the H3/H5 notice describes fields the
    # boxes no longer hold, and "saved before the time standard was stored
    # ... check it" is answered by the standard written above. The readings
    # question (_readings_pending, "'X' was saved under other readings")
    # is LEFT standing: it is neither -- X was saved under other readings
    # still, the picker still names X, and which readings the chart is
    # read under is the reader's to say, which the cast does not say. An
    # edit of the date keeps the question too. A standard this app does
    # not offer (SC-02) is answered by the cast's standard likewise.
    st.session_state.pop("_loaded_without_standard", None)
    st.session_state.pop("_loaded_unoffered_standard", None)
    st.session_state.pop("_record_notice", None)


_home_in_force = _home_place()
_here_now_slot.button(
    "\U0001F4CD Here & Now", key="_here_and_now", on_click=_here_and_now,
    disabled=_home_in_force is None, width="stretch",
    help=("Cast a chart for the home place at this moment, by this computer's clock."
          if _home_in_force else "Set a home place under Birthplace first."))

# Said once, in the session whose load found the store unreadable (F04,
# item 6). The bytes are beside the file under the name this names; the
# store this session writes is a fresh one.
_saved_flash = st.session_state.pop("_saved_flash", None)
if _saved_flash:
    st.sidebar.success(f"Saved {_as_typed(_saved_flash, quoted=True)}.")

# What a write found on disk, carried over the rerun it asked for: a record
# another window had moved, named (L6R-N7); a store that could not be read
# and was left as it is (L6R-N1); a store that could not be read and was
# written over once its bytes were kept beside it, the copy told, naming
# no file (L6R-N2; ruling 135);
# a store removed since this window read it, written again from this
# window's records (K-05).
_store_moved = st.session_state.pop("_store_moved_notice", None)
if _store_moved:
    st.sidebar.warning(f"{_store_moved} The saved charts have been reloaded and "
                       "nothing was written; look at the list and try again.")
_store_refused = st.session_state.pop("_store_refused_notice", None)
if _store_refused:
    st.sidebar.error(_store_refused)
_store_kept = st.session_state.pop("_store_kept_notice", None)
if _store_kept:
    st.sidebar.warning(_store_kept)

_store_error = st.session_state.pop("_store_error_notice", None)
if _store_error is True:
    st.sidebar.error("Saved charts could not be read, and no copy of the "
                     "file could be made.")
elif _store_error:
    st.sidebar.error("Saved charts could not be read. A copy of the file was "
                     "kept beside the saved charts.")
# Ruling 100: the owner's sentence, said once, naming no file.
if st.session_state.pop("_store_recovered_notice", None):
    st.sidebar.warning(STORE_RECOVERED_SENTENCE)
if st.session_state.pop("_store_imported_notice", None):
    st.sidebar.info(STORE_IMPORTED_SENTENCE)                            # SB-06
if st.session_state.pop("_store_old_not_a_file_notice", None):
    st.sidebar.warning(STORE_OLD_NOT_A_FILE_SENTENCE)                   # SB-05
# S02 of SC2's check: the old store this window's load could not move in.
if st.session_state.pop("_store_unlocked_notice", None):
    st.sidebar.error(STORE_UNLOCKED_SENTENCE)
_store_unmoved = st.session_state.pop("_store_unmoved_notice", None)
if isinstance(_store_unmoved, str):
    st.sidebar.error(_store_blocked_sentence(_store_unmoved))          # ruling 109
elif _store_unmoved:
    st.sidebar.warning(STORE_UNMOVED_SENTENCE)

# What a record said about itself when it was loaded, or refused to be: the
# fields the sidebar could not read (H3), or an offset outside the bounds a
# chart can be cast at (H5). It stands beside the picker for as long as
# that record is the one in hand -- until another is loaded, a new chart is
# begun, or one is saved -- because it describes the record, not the click.
# K-15 of the re-pass's follow-ups (2026-10-05): a refusal is said of the
# record refused. When the store, as this window has since read it, holds
# another record under that name (another window replaced it) or none (it
# was deleted), the sentence speaks of a record the list no longer holds,
# and goes. The refusal itself stands: the boxes were never loaded from the
# record now under the name, so the strip still does not name it.
_refusal_kept = st.session_state.get("_record_refused")
if (isinstance(_refusal_kept, dict)
        and not _same_record(st.session_state["saved_charts"].get(_refusal_kept.get("name")),
                             _refusal_kept.get("record"))
        and st.session_state.get("_record_notice") == _refusal_kept.get("sentence")):
    st.session_state.pop("_record_notice", None)
_record_notice = st.session_state.get("_record_notice")
if _record_notice:
    st.sidebar.warning(_record_notice)

# L6R-N4: a folder the saved charts and the preferences cannot be kept in
# is said on every run while it stands (Save and "Set as home" refuse with
# the same sentence). L6R-N5: a preferences file that could not be read is
# said once, in the session that found it, as the store's is above.
_data_folder_sentence = _data_folder_refusal()
if _data_folder_sentence:
    st.sidebar.warning(_data_folder_sentence)
if engine.preferences_notices()["off"]:
    st.sidebar.caption(PREFERENCES_OFF_SENTENCE)                       # SB-11
# K-1 of the KS re-check (2026-10-06): a choice refused by the lock (ruling
# 77) or by the disk (SC-09) is said in the run in which it was refused. A
# page's control is written after the sidebar has drawn its notices, so its
# sentence used to wait for the reader's next action, the box meanwhile
# shown as ticked. The notices have a box of their own here, filled again
# at the run's end (after the page) with any said since.
#
# S05 of lane SC2 (the outside audit of face757; SC_CHECK's note 24): the
# sentence for a preferences file that could not be read (L6R-N5) was drawn
# above the box, once, so a page's control that met such a file had its
# refusal said in that run and the reason -- that a copy was kept, or that
# none could be made -- only on the reader's next action. It is said in the box
# too, as an error, ahead of the box's warnings.
_prefs_notice_box = st.sidebar.empty()
_PREFS_NOTICES_THIS_RUN = []


def _prefs_error_sentence(notice):
    """L6R-N5's sentence for a preferences file that could not be read:
    `notice` is the copy's name, or True when no copy could be made; the
    sentence names no file (ruling 135)."""
    if notice is True:
        return ("Preferences could not be read, and no copy of the file could be "
                "made, so it is left as it is: readings, the home place and the last "
                "chart are not kept.")
    return "Preferences could not be read. A copy of the file was kept beside the saved charts."


def _say_preference_notices():
    _found = st.session_state.pop("_prefs_error_notice", None)
    _said = [("error", _prefs_error_sentence(_found))] if _found else []
    _blocked = st.session_state.pop("_prefs_blocked_notice", None)
    if _blocked:
        _said.append(("error", _prefs_blocked_sentence(_blocked)))          # ruling 109
    for _flag, _sentence in (("_prefs_busy_notice", PREFERENCES_BUSY_SENTENCE),
                             ("_prefs_refused_notice", PREFERENCES_REFUSED_SENTENCE)):
        if st.session_state.pop(_flag, None):
            _said.append(("warning", _sentence))
    for _notice in _said:
        if _notice not in _PREFS_NOTICES_THIS_RUN:
            _PREFS_NOTICES_THIS_RUN.append(_notice)
    if _PREFS_NOTICES_THIS_RUN:
        with _prefs_notice_box.container():
            for _kind in ("error", "warning"):
                for _which, _sentence in _PREFS_NOTICES_THIS_RUN:
                    if _which == _kind:
                        (st.error if _kind == "error" else st.warning)(_sentence)


_say_preference_notices()

load_col, del_col = st.sidebar.columns([3, 1])
load_col.selectbox("\U0001F4C2 Load saved chart", chart_options, key="chart_picker", on_change=_apply_selected_chart)
# Filled once the sidebar's validation has run, when the fields have moved
# away from the record the picker names.
picker_note = st.sidebar.empty()

# The readings a loaded record was saved under, put to the reader (F03 of
# the review of 2026-09-16: a chart saved under Abu Ma'shar's connection
# rule came back under Sahl, with nothing said). The load has changed
# nothing: this is where the app says which it is about to do, and neither
# branch is taken for the reader.
readings_box = st.sidebar.empty()
_readings_pending = st.session_state.get("_readings_pending")
if _readings_pending and _readings_pending not in st.session_state["saved_charts"]:
    st.session_state.pop("_readings_pending", None)
    _readings_pending = None
if _readings_pending:
    with readings_box.container():
        st.info(f"{_as_typed(_readings_pending, quoted=True)} was saved under other readings.")
        _open_col, _keep_col = st.columns(2)
        _open_readings = _open_col.button("Open saved readings", key="_readings_open")
        _keep_readings = _keep_col.button("Keep current readings", key="_readings_keep")
    if _keep_readings:
        # Nothing to write: the readings in force are already the ones in
        # force. The chart stays (modified) by its readings, which is the
        # truth of it, and the caption under the picker says so.
        st.session_state.pop("_readings_pending", None)
        readings_box.empty()
    elif _open_readings:
        # Recorded, not done: the writing and the rerun happen at the foot
        # of the sidebar, where every field has been drawn. A rerun from
        # this height abandons the run before the date, time and place
        # widgets are drawn and Streamlit discards their state -- the
        # lesson the delete confirmation learned in the browser.
        st.session_state["_readings_open_now"] = _readings_pending
        readings_box.empty()

# A record written before this app stored the readings with a chart. There
# is no question to ask of it -- it has nothing to restore -- so it gets one
# sentence, once, on the load that found it.
_readings_legacy = st.session_state.pop("_readings_legacy", None)
if _readings_legacy:
    st.sidebar.caption("Saved before readings were stored with a chart; "
                       "results use the current readings.")

if del_col.button("\U0001F5D1", help="Delete the selected saved chart"):
    picked = st.session_state.get("chart_picker")
    if picked and picked != "-- New Chart --" and picked in st.session_state["saved_charts"]:
        # The bin asks first (F04, item 5): it used to delete the record on
        # the press, with no confirmation and nothing to undo it with.
        st.session_state["_delete_pending"] = picked
        st.session_state.pop("_replace_pending", None)
        st.session_state.pop("_replace_pending_record", None)

# The question stands here, beside the bin that asked it, in a placeholder
# of its own so that answering it can clear it without a rerun. A rerun from
# this height of the sidebar is not available: it abandons the run before
# the date, time and place widgets are drawn, and Streamlit discards the
# state of a widget a run did not draw -- the boxes came back holding the
# example nativity (seen in the browser, 2026-09-16). So Keep clears the
# placeholder, and Delete leaves the writing to the foot of the sidebar,
# where every field has been drawn and a rerun costs nothing.
delete_box = st.sidebar.empty()
_delete_pending = st.session_state.get("_delete_pending")
if _delete_pending and _delete_pending not in st.session_state["saved_charts"]:
    st.session_state.pop("_delete_pending", None)
    _delete_pending = None
if _delete_pending:
    with delete_box.container():
        st.warning(f"Delete {_as_typed(_delete_pending, quoted=True)}?")
        _delete_col, _keep_col = st.columns(2)
        _delete_clicked = _delete_col.button("Delete", key="_delete_confirm")
        _keep_clicked = _keep_col.button("Keep", key="_delete_keep")
    if _keep_clicked:
        st.session_state.pop("_delete_pending", None)
        delete_box.empty()
    elif _delete_clicked:
        st.session_state["_delete_now"] = _delete_pending
        delete_box.empty()

# --- Configurable readings: read here, set on the pages ------------------
# The Connection rule and the five readings the sources leave open are set
# by controls on the page and table each one affects (Configurations, Chart,
# Dignities, Lots), and remembered across navigation in a store key that
# _persist() keeps up to date. They are READ here, at the top level, because
# the engine functions below run before any page function does and read
# these globals at call time. The widget key is preferred when present: on
# the rerun a change triggers, the widget already carries the new value
# while the store still holds the old one. The target of the Timing page
# (2026-09-10) is read the same way, further down. _reading() itself is
# defined above the picker, where a record's own readings are first needed.

# The date is typed, not picked (UI evaluation 2026-09-10, A.1): a calendar
# popup is the wrong control for 1240, and the harness sets this key as a
# string. A malformed date no longer stops the script -- which took the
# page list with it -- but keeps the last good date and says so.
# Seeded through session state rather than a default argument: a loaded
# chart writes these keys before the widgets run, and Streamlit warns when a
# widget has both a default and a seeded key (the konsole warning of
# 2026-09-15). The same for every key _restore_chart writes.
st.session_state.setdefault("date_input_key", EXAMPLE_CHART["date_input_key"])
date_string = st.sidebar.text_input(
    "Date (YYYY-MM-DD)", key="date_input_key",
    help="The civil date of birth. Before 1582-10-15 the digits are read as a Julian-calendar date, "
         "as Solar Fire and astro.com read them; from that day on, Gregorian; type Old Style dates "
         "(Britain to 1752, Russia to 1918) in Gregorian. Years before 1000 are typed with their "
         "leading zeros (0787-08-10).")
# date_string is the DRAFT -- the characters in the box. input_date is the
# COMMITTED date: the draft when it parses, the last one that did when it
# does not. F01 of the review of 2026-09-16: everything downstream reads the
# committed date and nothing reads the draft, so the strip, the chart and a
# saved record cannot describe three different nativities.
_parsed = parse_iso_date(date_string)
date_is_valid = _parsed is not None
if _parsed is None:
    input_date = st.session_state.get("_date_last_good", CivilDate(1240, 5, 23))
    st.sidebar.error(f"Date must be YYYY-MM-DD, e.g. 1240-05-23. Showing {input_date:%Y-%m-%d}.")
else:
    input_date = _parsed
    st.session_state["_date_last_good"] = input_date
_cal_note = ("Julian calendar (before the reform of 1582-10-15)"
             if (input_date.year, input_date.month, input_date.day) < (1582, 10, 15) else "Gregorian calendar")
# Every UT this app prints is written in the calendar of its own moment
# -- Julian before the reform's JD, Gregorian from it -- which is the
# policy the date box reads digits by and the Prediction pages already
# write by, so a UT typed back as a birth gives the same JD (the hostile
# pass of 2026-09-22, M4, and its verification: writing the UT in the
# birth date's calendar put a Gregorian birth's UT on a day that never
# was). The note BESIDE a UT names the UT's calendar, not the birth's;
# _cal_note above is the birth date's, under the date box.
def _ut_cal_note(jd):
    return ("Gregorian calendar" if jd >= PN4_GREGORIAN_REFORM_JD
            else "Julian calendar (before the reform of 1582-10-15)")

# --- What the ephemeris can reach ----------------------------------------
# H1/H2 of the hostile pass of 2026-09-16. The date box takes any year from
# 1 to 9999 and a chart was cast from it without asking whether the
# ephemeris shipped with this app has a position for it: outside its span
# swe.calc_ut RAISES, and the calculation runs at module level, above
# st.navigation(...).run(), so a reachable-looking date took the whole
# shell down -- no page, no recovery panel, an inert navigation bar.
#
# The span the built-in (Moshier) ephemeris answers to, measured rather
# than assumed: swe.calc_ut is answered from Julian Day 625000.5
# (swe.revjul: -3001 February, i.e. 3002 BC) up to but not including
# 2818000.5 (3003 April).
EPHEMERIS_JD_MIN = 625000.5
EPHEMERIS_JD_MAX = 2818000.5
# A chart is never one position: every date this app is given is SEARCHED
# forward from, and the search must land inside the ephemeris too. The
# conservative existing margin includes the natal gestation Moons, which reach
# about 380 days past the birth. Indicator 15 reads the revolution instant
# and no longer performs a forward sign-exit search. So a usable date is one with a search's room
# left above it, which is what a date inside the RAW span need not have: a
# birth in 3002 is answered by swe.calc_ut and then raises in the gestation
# search.
EPHEMERIS_SEARCH_DAYS = 950.0
# The app's own last moment: the end of 3000 AD, which is what the sidebar
# states, or the last moment with a search's room above it, whichever comes
# first. It is the second, by some four months -- the sentence names the
# round span, as a limit stated to a reader should be, and the refusal
# falls just inside it rather than just outside.
EPHEMERIS_JD_LAST = min(civil_to_jd(3001, 1, 1, 0.0),
                        EPHEMERIS_JD_MAX - EPHEMERIS_SEARCH_DAYS)
# The sentence names the last DAY the app casts, not the round year: the
# refusal fell some four months inside "3000 AD" (the hostile pass of
# 2026-09-22, L5), so the span is stated to the day.
EPHEMERIS_LAST_DATE = CivilDate.from_jd(EPHEMERIS_JD_LAST - 1.0)
EPHEMERIS_DATE_MESSAGE = (f"This app's ephemeris covers 3000 BC to {EPHEMERIS_LAST_DATE:%Y-%m-%d}; "
                          "the date is outside it.")
EPHEMERIS_LAST_YEAR = 3000


def jd_in_ephemeris(jd):
    """Whether a Julian Day is one this app can compute a chart for, with
    room left over for the searches that run forward from it."""
    try:
        jd = float(jd)
    except (TypeError, ValueError):
        return False
    return EPHEMERIS_JD_MIN <= jd < EPHEMERIS_JD_LAST


def date_in_ephemeris(date):
    """The same question of a civil DATE, asked at noon: the offset can move
    a moment by at most 14 hours and the limit is a whole year inside the
    ephemeris, so the hour cannot decide this."""
    return jd_in_ephemeris(civil_to_jd(date.year, date.month, date.day, 12.0))


def max_target_age(birth_date):
    """The greatest age whose birthday this app can still analyse -- the
    Age box's own upper bound, so that the limit cannot be crossed by
    counting years instead of typing a date. Counted down from the last
    year covered, because the limit falls inside that year and a birthday
    late in it is past the limit while an earlier one is not."""
    age = EPHEMERIS_LAST_YEAR - int(birth_date.year)
    while age > 0 and not date_in_ephemeris(pn4_birthday(birth_date, age)):
        age -= 1
    return max(0, age)

# L6-10: a widget key holding a type its widget never produces (a text time,
# a text offset, a latitude of None, a number where the place box wants text,
# an age that is not a finite number) took the script down with a raw
# traceback where it was consumed. Such a value is dropped here, before any
# widget reads it, and the key falls back to the default its setdefault gives.
def _drop_wrong_typed_keys():
    def _number(v):
        # A number of any value: an impossible latitude is the coordinate
        # check's to refuse, with its sentence, not this pass's to drop.
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    wanted = {"time_input_key": lambda v: isinstance(v, time),
              "utc_offset_key": _number, "manual_lat_key": _number, "manual_lon_key": _number,
              "location_input_key": lambda v: isinstance(v, str),
              # SC-18 of the notes lanes (2026-10-06): math.isfinite turns an
              # int into a float, and 10**400 raised OverflowError here, in
              # the pass meant to drop it, on every run. The engine's test
              # bounds an int before it converts one.
              "_target_age": engine._is_real_number}
    # L6-10, the re-pass of 2026-10-04: a reading's store key holding a value
    # outside its options (_connection_rule = 5) took the Chart and Timing
    # pages down with a KeyError inside the first evaluator that looked the
    # reading up. The preferences file and a saved record are validated on
    # the way in; the session is validated here, by the same rule
    # (preference_is_valid, engine), before the readings are read further
    # down. The widget key is held to it too, since _reading prefers it.
    for _label, _widget_key, _store_key, _default, _page in READINGS_REGISTRY:
        _valid = functools.partial(preference_is_valid, _store_key)
        wanted[_store_key] = _valid
        wanted[_widget_key] = _valid
    for _key, _ok in wanted.items():
        # A None in utc_offset_key is not a wrong type: it is the value the
        # blank box itself returns (value=None). Dropping it would re-seed
        # 0.0 and cast the chart at UTC+00:00 from a blank, so it is left for
        # the offset block below to refuse with its sentence.
        if _key == "utc_offset_key" and st.session_state.get(_key) is None:
            continue
        if _key in st.session_state and not _ok(st.session_state[_key]):
            del st.session_state[_key]
_drop_wrong_typed_keys()

# To the second: the engine reads seconds, and a rectified time has them.
st.session_state.setdefault("time_input_key", EXAMPLE_CHART["time_input_key"])
input_time = st.sidebar.time_input("Time", key="time_input_key", step=timedelta(seconds=1))

# The time standard gets a key, so it is saved with the chart (F1 of the
# 2026-09-10 evaluation: the saved reference nativity, recorded EST, was
# loading at LMT, forty minutes wrong). The resolved offset is shown in the
# box directly under it, before the chart is cast, not at the sidebar's foot.
# The tooltip names the three standards in a line; their full sentences
# stand in the sidebar under the resolved offset, in a notes expander.
# A session that still holds a renamed label (a test's seed, or any state
# carried from before the rename) takes the option it now is, before the
# box is drawn (S1-4).
_seeded_standard = st.session_state.get("time_standard_key")
if time_standard_current(_seeded_standard) != _seeded_standard:
    st.session_state["time_standard_key"] = time_standard_current(_seeded_standard)
time_standard = st.sidebar.selectbox(
    "Time standard", TIME_STANDARD_OPTIONS, key="time_standard_key",
    help=(f"{TIME_STANDARD_OPTIONS[0]} for charts before standard time was adopted (late 19th century); "
          f"{TIME_STANDARD_OPTIONS[1]}: the zone at the birthplace; {TIME_STANDARD_OPTIONS[2]}: type the "
          "offset the birth record states, east positive."))
utc_offset_manual = None
utc_offset_refusal = None
if time_standard == TIME_STANDARD_OPTIONS[2]:
    st.session_state.setdefault("utc_offset_key", EXAMPLE_CHART["utc_offset_key"])
    # A signed zero is UTC itself: -0.0 (typed, or in a hand-edited record)
    # is read as 0.0 before the box takes it, so the box does not format it
    # "-0.0000" and the record and the reports do not print "-0".
    if st.session_state["utc_offset_key"] == 0:
        st.session_state["utc_offset_key"] = 0.0
    # L1-09: the box clamps what it holds to its bounds, and a seed above
    # them is pulled to the WRONG bound (14.25 became -14:00) with nothing
    # said. The key is read here, before the widget sees it, and an offset
    # outside the range is refused as an impossible latitude is -- the
    # loader already does. The widget's own value is remembered, so the
    # refusal stands on the runs that follow until the offset is changed.
    _offset_seed = st.session_state["utc_offset_key"]
    if _offset_seed is None or not utc_offset_in_range(_offset_seed):
        utc_offset_refusal = (
            f"The UTC offset box is blank. Type an offset from -14 to +14 hours, or choose {TIME_STANDARD_OPTIONS[0]}."
            if _offset_seed is None else
            f"The UTC offset {_offset_seed!r} is outside the box's range of -14 to +14 hours. "
            f"Type an offset inside it, or choose {TIME_STANDARD_OPTIONS[0]}.")
    utc_offset_manual = st.sidebar.number_input(
        "UTC offset (hours, east positive)", value=None, min_value=-14.0, max_value=14.0, step=0.25,
        # Four places (K-30): an offset of whole minutes and seconds such as
        # 5.125 h (+05:07:30) shows as the number it is cast at; at two
        # places the box showed 5.12 (5.13 in the browser), which, retyped,
        # casts at another offset. A ten-thousandth of an hour is 0.36 s, so
        # what the box shows is never more than 0.18 s from what it holds.
        format="%.4f", key="utc_offset_key")
    if utc_offset_refusal:
        _refused_now = st.session_state.get("utc_offset_key")
        if _refused_now is not None:
            st.session_state["_utc_offset_refused"] = _refused_now
    elif st.session_state.get("_utc_offset_refused") is not None:
        if st.session_state["utc_offset_key"] == st.session_state["_utc_offset_refused"]:
            utc_offset_refusal = ("The UTC offset was outside the box's range of -14 to +14 hours and the box "
                                  "has moved it. Type the offset the record states.")
        else:
            st.session_state.pop("_utc_offset_refused")
time_standard_box = st.sidebar.empty()
time_standard_box.caption(_cal_note)
with st.sidebar.expander("The three time standards", icon=":material/menu_book:"):   # NOTES_ICON, defined below the sidebar
    st.markdown(f"- {TIME_STANDARD_OPTIONS[0]} for charts before standard time was adopted (late 19th century): "
                "the offset is the longitude at 4 minutes a degree.\n"
                f"- {TIME_STANDARD_OPTIONS[1]}: the zone at the "
                "birthplace, with daylight saving as the zone's own history records it.\n"
                f"- {TIME_STANDARD_OPTIONS[2]}: type the "
                "offset the birth record states, east positive (EST is -5, CDT is -5, IST is +5.5).")
if st.session_state.get("_loaded_without_standard"):
    st.sidebar.warning(f"{_as_typed(st.session_state['_loaded_without_standard'], quoted=True)} was saved before the time "
                       "standard was stored with a chart. Check it, then save the chart again.")
_unoffered_standard = st.session_state.get("_loaded_unoffered_standard")
if isinstance(_unoffered_standard, dict):
    # S06 of lane SC2 (the outside audit of face757; SC_CHECK's note 4): a
    # stored label that is empty, or only spaces, was named as a label,
    # "this app does not offer, ''", a pair of empty quotation marks. It is
    # said to be empty; the rest of the sentence is the same. S06 of SC2's
    # check (lane SC3): so is a label of characters that print nothing (a
    # zero-width space, a direction mark), which printed the same marks.
    _label = _unoffered_standard.get('label')
    if any(_c.isprintable() and not _c.isspace() for _c in str(_label)):
        _held = f"a time standard this app does not offer, {_as_typed(_label, quoted=True)}"
    else:
        _held = "its time standard empty"
    st.sidebar.warning(f"{_as_typed(_unoffered_standard.get('name'), quoted=True)} was saved with {_held}; it is "
                       f"cast under {time_standard}. Choose the standard, then save the chart again.")

st.sidebar.header("Birthplace")

COORDINATE_RANGE_MESSAGE = ("Latitude must be between -90 and 90 and longitude "
                            "between -180 and 180.")
# coordinates_in_range, the one rule for a pair, stands in engine.py since
# the home place preference is validated there against the same rule.

# One control in effect (evaluation A.3): the search box also accepts a
# typed "latitude, longitude" pair; the toggle exposes the coordinate
# fields themselves, which is also how a saved chart is restored (the
# loader writes these three keys, as the harness does).
# The thing named, not its file, and no instruction about folders (rulings
# 30, 135 and 146 (7), B-18).
ATLAS_MISSING_MESSAGE = ("The offline place atlas is missing, so no city can be looked up. "
                         "Enter the place's latitude and longitude instead.")
ATLAS_NO_MATCH_MESSAGE = "No matches found in offline atlas."
# An entry longer than any place (PLACE_TEXT_MAX_CHARS) is refused before
# either lookup, with this sentence (ruling 160).
PLACE_TEXT_TOO_LONG_MESSAGE = ("This entry is too long to be a city or a latitude, longitude pair, "
                               "so it was not looked up.")


def _atlas_matches(city_search):
    """The offline atlas's matches for a city text, as {label: (lat, lon)}
    in the atlas's own order, the most populous first -- the order the
    selectbox under the search box offers them in -- or None with the
    sentence that says why there are none. The one lookup, so that the
    search box and the coordinate fields' start (below) cannot resolve a
    text two ways."""
    db_path = Path(__file__).parent / "atlas.db"
    if not db_path.exists():
        return None, ATLAS_MISSING_MESSAGE
    matches = atlas_rows(db_path, city_search)
    if not matches:
        return None, ATLAS_NO_MATCH_MESSAGE
    options = {}
    for m in matches:
        # Format: City, State/Admin (Country Code). A place the atlas
        # gives no region (117 of them: Hong Kong, Singapore, ...) is
        # City (Country Code), not "City,  (HK)" (C-02 of the hostile pass
        # of 2026-10-03). A saved record keeps the label it was saved
        # with: it is restored by its coordinates, never by this text.
        region = (m[1] or '').strip()
        label = f"{m[0]}, {region} ({m[2]})" if region else f"{m[0]} ({m[2]})"
        # Deduplicate identical names in the same region
        if label in options:
            label += f" [{degrees_text(m[3], 4)}, {degrees_text(m[4], 4)}]"
        options[label] = (m[3], m[4])
    return options, None


def _place_the_box_holds(text):
    """The place a city-box text resolves to before any choice among its
    matches: a typed "latitude, longitude" pair, or the atlas's first
    match -- what the selectbox would offer first. (None, None) when the
    text resolves to nothing, as does a text too long to be a place."""
    if not text or len(text) > PLACE_TEXT_MAX_CHARS:
        return None, None
    typed = parse_lat_lon(text)
    if typed:
        return typed
    options, _why = _atlas_matches(text)
    if options:
        return next(iter(options.values()))
    return None, None


def _manual_coords_switched():
    """on_change: the toggle moved on this run. A callback runs BEFORE the
    widgets of the rerun it triggers and before the script has resolved
    anything, so all it can know is that the switch happened; the fields
    are started at the toggle's own site, below, from this run's values.
    (Until 2026-09-18 the callback itself wrote the fields from
    _resolved_lat/_resolved_lon, the PREVIOUS run's place: a city typed
    over the box and the toggle clicked without Enter -- the click's
    mouse-down commits the text, so the edit and the switch arrive in one
    run -- started the fields at the place the box no longer showed.)"""
    st.session_state["_coords_switched"] = True


def _box_value(value, low, high):
    """What a coordinate box shows for a refused value (L6-06): the value
    itself where the box can hold it, and otherwise the bound the box pulls
    an impossible value to on its own, its lower one -- a NaN, an infinity
    and a number past either bound alike."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return low
    return number if math.isfinite(number) and low <= number <= high else low


def _refused_coordinate(value):
    """A refused coordinate as the number the sidebar goes on to read and
    write out ("Manual [lat, lon]"). An int past a float's range (10**400 in
    a coordinate key, K-13) is the infinity of its sign: the range check
    refuses it with its sentence as it refuses an infinity, where writing
    the int out as a float raised OverflowError on every run."""
    try:
        return float(value)
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def _manual_place_label(lat, lon):
    """The name a place entered by its coordinates goes by: in the box under
    the fields, on a saved record, and in the comparison of a record whose
    own name for its place is empty (SC-01). A coordinate that rounds to
    zero prints 0.0000, not -0.0000 (N04, ruling 107): every coordinate the
    sidebar and the strip print goes through degrees_text, which drops the
    sign of a rounded zero. A saved record keeps the place name it was
    saved with (loaded_location), so only labels made from now on change."""
    return f"Manual [{degrees_text(lat, 4)}, {degrees_text(lon, 4)}]"


manual_coords = st.sidebar.toggle("Enter coordinates directly", key="manual_coords_key",
                                  on_change=_manual_coords_switched,
                                  help="Or type them into the search box as 'latitude, longitude'.")
_coords_switched = bool(st.session_state.pop("_coords_switched", None))

# The reason a place cannot be read, in the words the sidebar already used;
# it becomes chart_error below, which the recovery panel prints.
location_error = None
if manual_coords:
    # B-02: the pair kept for the box's text is the box's; with the fields
    # on it is spent (switching off again keeps the fields' pair anew).
    st.session_state.pop("_coords_off_pair", None)
    if _coords_switched:
        # F02 of the review of 2026-09-16: switching the fields ON is a
        # change of input method, not of place, so they start at the place
        # the city box holds -- as of THIS run. The box's committed text is
        # in its key on this run whether or not the box is drawn. Text that
        # has moved since it was last resolved is resolved here, as the box
        # would resolve it; text the last run resolved keeps that resolution
        # (its choice among the matches included), and so does text that
        # resolves to nothing, the last place that resolved being the one
        # the reader was working from. Nothing ever resolved: the constants.
        _text = st.session_state.get("location_input_key")
        _start_lat, _start_lon = None, None
        if _text is not None and _text != st.session_state.get("_resolved_text"):
            _start_lat, _start_lon = _place_the_box_holds(_text)
        if _start_lat is None or _start_lon is None:
            _start_lat = st.session_state.get("_resolved_lat")
            _start_lon = st.session_state.get("_resolved_lon")
        if _start_lat is not None and _start_lon is not None:
            st.session_state["manual_lat_key"] = float(_start_lat)
            st.session_state["manual_lon_key"] = float(_start_lon)
    st.session_state.setdefault("manual_lat_key", EXAMPLE_CHART["manual_lat_key"])
    st.session_state.setdefault("manual_lon_key", EXAMPLE_CHART["manual_lon_key"])
    # What the fields hold BEFORE the widgets clamp them to their own
    # min/max: an impossible latitude seeded into the key (the review's own
    # reproduction, E03) is refused below rather than silently pulled to
    # the pole.
    _draft_lat = st.session_state.get("manual_lat_key")
    _draft_lon = st.session_state.get("manual_lon_key")
    # L6-06: the widget pulls a refused pair to its bound, and that bound
    # would be cast on the next run. While the key still holds exactly what
    # the widget wrote for a refused pair, the pair stays the refused one.
    _refused_manual = st.session_state.get("_refused_manual")
    if _refused_manual is not None:
        if (_draft_lat, _draft_lon) == _refused_manual["shown"]:
            _draft_lat, _draft_lon = _refused_manual["draft"]
        else:
            st.session_state.pop("_refused_manual", None)
    # L6-06, the re-pass of 2026-10-04: the refused value was left in the key
    # for the widget to pull to its bound after this run, and the pair
    # remembered was what the widget returned on it -- for a NaN, the NaN
    # itself, which equals nothing, while the key came back holding -90 and
    # the next run cast the South Pole. The values the boxes show for a
    # refused pair are written into their keys here, before the widgets read
    # them, and remembered: the widgets hold them as they are, and the pair
    # stays refused on every run until a box is changed.
    if not coordinates_in_range(_draft_lat, _draft_lon):
        _shown = (_box_value(_draft_lat, -90.0, 90.0), _box_value(_draft_lon, -180.0, 180.0))
        st.session_state["manual_lat_key"], st.session_state["manual_lon_key"] = _shown
        st.session_state["_refused_manual"] = {"shown": _shown, "draft": (_draft_lat, _draft_lon)}
    lat = st.sidebar.number_input("Latitude", min_value=-90.0, max_value=90.0,
                                  format="%.4f", key="manual_lat_key")
    lon = st.sidebar.number_input("Longitude", min_value=-180.0, max_value=180.0,
                                  format="%.4f", key="manual_lon_key")
    if not coordinates_in_range(_draft_lat, _draft_lon):
        lat, lon = _refused_coordinate(_draft_lat), _refused_coordinate(_draft_lon)
    # If these coordinates came from loading a saved chart and haven't been
    # hand-edited since, show the friendly place name it was saved under
    # instead of a bare coordinate pair.
    loaded_location = st.session_state.get("loaded_location")
    if (
        loaded_location
        and loaded_location.get("label")
        and loaded_location["lat"] == lat
        and loaded_location["lon"] == lon
    ):
        location_query = loaded_location["label"]
    else:
        location_query = _manual_place_label(lat, lon)
    city_search = None
else:
    if _coords_switched:
        # The other direction of F02 (the hostile pass of 2026-09-22, M2):
        # switching the fields OFF is no more a change of place than
        # switching them on. The box starts at the pair the fields held on
        # this run, written as the pair the box itself accepts, so the
        # chart stays where it was -- never the example's city unasked.
        # Ruling 145 (B-02): the box's text holds the pair to four places,
        # and a pair a zone line runs between would be cast, and its zone
        # resolved, a place away. The fields' own pair is kept aside with the
        # text written, and is the place while the box holds that text.
        _off_lat = st.session_state.get("manual_lat_key")
        _off_lon = st.session_state.get("manual_lon_key")
        if coordinates_in_range(_off_lat, _off_lon):
            _off_text = f"{degrees_text(float(_off_lat), 4)}, {degrees_text(float(_off_lon), 4)}"
            st.session_state["location_input_key"] = _off_text
            st.session_state["_coords_off_pair"] = {"text": _off_text, "lat": float(_off_lat),
                                                    "lon": float(_off_lon)}
    st.session_state.setdefault('location_input_key', EXAMPLE_CHART['location_input_key'])
    city_search = st.sidebar.text_input("City, or latitude, longitude", key="location_input_key",
                                        placeholder="Florence  |  45.3733, -84.9553")
    # A text that is blank after trimming is an empty box (the verification
    # of 2026-09-22: a single space had become the bare pattern "%").
    if city_search is not None and not city_search.strip():
        city_search = ""
    _typed = parse_lat_lon(city_search) if city_search else None
    # B-02: the pair the fields held when they were switched off, while the
    # box still holds the text written for it; a box edited is a new place.
    _off_pair = st.session_state.get("_coords_off_pair")
    if _off_pair is not None and city_search != _off_pair["text"]:
        st.session_state.pop("_coords_off_pair", None)
        _off_pair = None
    if _typed and _off_pair is not None:
        _typed = (_off_pair["lat"], _off_pair["lon"])
    if _typed:
        lat, lon = _typed
        location_query = _manual_place_label(lat, lon)
    elif city_search and len(city_search) > PLACE_TEXT_MAX_CHARS:
        # Longer than any place: neither parsed nor looked up (D-01).
        location_error = PLACE_TEXT_TOO_LONG_MESSAGE
        st.sidebar.warning(location_error)
        lat, lon, location_query = None, None, None
    elif city_search:
        options, location_error = _atlas_matches(city_search)
        if options:
            selected_label = st.sidebar.selectbox("Select specific location:", list(options.keys()))
            lat, lon = options[selected_label]
            location_query = selected_label
        elif location_error == ATLAS_MISSING_MESSAGE:
            st.sidebar.error(location_error)
            lat, lon, location_query = None, None, None
        else:
            st.sidebar.warning(location_error)
            lat, lon, location_query = None, None, None
    else:
        location_error = "No place is resolved."
        lat, lon, location_query = None, None, None
location_box = st.sidebar.empty()

# --- One validation of the coordinates, before any time standard ----------
# F02: the named-zone branch used to be the only thing that refused an
# impossible latitude, so the same 91 gave tables under a manual offset and
# an uncaught exception under a named zone. The pair is checked once, here,
# for the fields and for a "latitude, longitude" typed into the search box
# alike; a valid polar latitude passes (the engine refuses for itself what
# it cannot compute there).
chart_ok = True
chart_error = None
if lat is None or lon is None or not location_query:
    chart_ok = False
    chart_error = location_error or "No place is resolved."
elif not coordinates_in_range(lat, lon):
    chart_ok = False
    chart_error = COORDINATE_RANGE_MESSAGE
    st.sidebar.error(COORDINATE_RANGE_MESSAGE)
else:
    # The place now resolved, with the city text it came from (None when
    # it came from the fields), for the coordinate fields to start from
    # when they are switched on while the box still holds that text (F02a).
    st.session_state["_resolved_lat"] = float(lat)
    st.session_state["_resolved_lon"] = float(lon)
    st.session_state["_resolved_text"] = city_search

# --- The home place's popover, in the sidebar's first row -----------------
# Drawn HERE, after the Birthplace block, into the slot reserved at the top
# of the sidebar: "Set as home" must write THIS run's lat, lon and
# location_query -- the place the resolved box shows -- and those exist only
# once the block above has run. The natural gesture, a city typed over and
# the button clicked without Enter, delivers the edit and the click in one
# run, and an on_click callback reading _resolved_* from the run before
# wrote the previous place (Madrid in the box, Berlin written; the
# adversarial pass) -- so the press is handled inline, from this run's
# values. The "Here & Now" button and this popover's label were drawn or
# chosen before the press was seen, so when the home changes the run is
# repeated from the sidebar's foot, where every field has been drawn, as
# the delete confirmation does. The button is enabled only while this run
# resolved a place in range, which is what chart_ok says at this height.
_home_now = _home_place()
with _home_slot.popover("Home" if _home_now else "Set home", width="stretch"):
    # SC-12: "Forget home" refused, said where it was pressed.
    _home_refused = st.session_state.pop("_home_refused_notice", None)
    if _home_refused:
        st.error(_home_refused)
    if _home_now:
        st.caption(f"Home: {_as_typed(_home_now['label'])} · "
                   f"{degrees_text(_home_now['lat'], 4)}, {degrees_text(_home_now['lon'], 4)}")
    else:
        st.caption("Resolve a place under Birthplace, then set it as home.")
    if st.button("Set as home", key="_set_home", disabled=not chart_ok, width="stretch",
                 help="Keep the place resolved under Birthplace as the home that Here & Now casts a chart for."):
        _home_set = {"label": str(location_query), "lat": float(lat), "lon": float(lon)}
        _home_refusal = _data_folder_refusal()
        if _home_refusal:
            # L6R-N4: a home that cannot be kept is not set.
            st.error(_home_refusal)
        elif home_place_is_valid(_home_set):
            # K-10 of the re-pass's follow-ups: written whenever the file as
            # it stands does not hold it, not only when this window's home
            # moves, so a home set here again after another window set
            # another is the one kept. K-09: a home the file did not take is
            # not shown as the home either (with preferences off the
            # session's home is the only one there is).
            _home_before = st.session_state["_prefs"].get("home_place")
            if (_remember("home_place", _home_set, chosen=True, quiet=True)
                    or not engine.preferences_enabled()):
                if _home_set != st.session_state.get("home_place"):
                    st.session_state["home_place"] = _home_set
                    st.session_state["_home_changed"] = True
            else:
                if _home_before is None:
                    st.session_state["_prefs"].pop("home_place", None)
                else:
                    st.session_state["_prefs"]["home_place"] = _home_before
                _home_found = engine.preferences_notices()
                if _home_found["blocked"]:
                    st.error(_prefs_blocked_sentence(_home_found["blocked"]))   # ruling 109, as ruling 77's
                elif _home_found["busy"]:
                    # Ruling 77: said here, where it was pressed, and not
                    # again in the sidebar (quiet); K-2: this window's.
                    st.error(PREFERENCES_BUSY_SENTENCE)
                else:
                    st.error("This place could not be kept as the home: the preferences file "
                             "could not be written.")
    if _home_now:
        st.button("Forget home", key="_forget_home", on_click=_forget_home_place, width="stretch",
                  help="Remove the home place; Here & Now is then disabled.")

# --- The target of the Timing page: an age or a date -----------------------
# Set on the Timing page, where it is used (the owner's instinct, 2026-09-10),
# and remembered in store keys like the readings; read here because the
# bundle below is computed before the page runs. "Age 42" is the 42nd
# birthday; a date shows its completed years beside it on the page. Saved
# with the chart.
_today = CivilDate.of(datetime.now().date())
target_mode = _reading("target_mode", "_target_mode", TARGET_MODE_OPTIONS[0])
# F17 of the review of 2026-09-16: an unparseable target used to fall to
# today, which silently analysed a different period from the one asked for.
# It keeps the last target that did parse instead -- the same rule the birth
# date follows -- and only a session that has never had one falls to today.
st.session_state.setdefault("_target_last_good", _today.isoformat())
# H2 of the hostile pass of 2026-09-16: a target the ephemeris cannot reach
# -- typed as a date, or counted as an age, the Age box having had no upper
# bound at all -- raised inside the timing bundle at module level and took
# the shell with it. A target out of reach is treated exactly as a target
# that will not parse (F17): the last valid one stands, and the Timing page
# says so in the target's own row. `target_range_note` is that sentence, or
# None; it is read by the page, which is where the target is set.
_target_parsed = parse_iso_date(_reading("target_date", "_target_date", _today.isoformat()))
# A target before the birth lies in no month of any year (the hostile pass
# of 2026-09-22, M3): it is refused as an out-of-reach target is, the last
# valid one kept -- and the kept one is never before the birth either (a
# birth after today made today the target unprompted), the birthday itself
# standing in when nothing later is valid.
_target_before_birth = _target_parsed is not None and _target_parsed < input_date
_target_reachable = _target_parsed is not None and date_in_ephemeris(_target_parsed) and not _target_before_birth
if _target_reachable:
    st.session_state["_target_last_good"] = _target_parsed.isoformat()
_target_kept = parse_iso_date(st.session_state["_target_last_good"]) or _today
if _target_kept < input_date:
    _target_kept = input_date
_date_target = _target_parsed if _target_reachable else _target_kept
target_out_of_reach = False
if target_mode == TARGET_MODE_OPTIONS[1]:
    _asked_age = max(0, int(_reading("target_age", "_target_age", pn4_completed_years(input_date, _date_target))))
    _asked_date = pn4_birthday(input_date, _asked_age)
    if date_in_ephemeris(_asked_date):
        target_age, target_date = _asked_age, _asked_date
        st.session_state["_target_last_good"] = target_date.isoformat()
    else:
        target_out_of_reach = True
        target_date = _target_kept
        target_age = pn4_completed_years(input_date, target_date)
        st.session_state["_target_age"] = target_age
    # The other reading follows, so switching the mode carries the target over.
    st.session_state["_target_date"] = target_date.isoformat()
else:
    target_out_of_reach = _target_parsed is not None and not _target_reachable
    target_date = _date_target
    target_age = pn4_completed_years(input_date, target_date)
    st.session_state["_target_age"] = target_age
target_range_note = (
    (f"The target {_target_parsed:%Y-%m-%d} is before the birth ({input_date:%Y-%m-%d}) and lies in no year of the "
     f"life; keeping {target_date:%Y-%m-%d}.")
    if target_out_of_reach and _target_before_birth and target_mode != TARGET_MODE_OPTIONS[1] else
    (f"The target is beyond this app's ephemeris ({EPHEMERIS_LAST_DATE:%Y-%m-%d}); "
     f"keeping {target_date:%Y-%m-%d}.") if target_out_of_reach else None)

def _chart_record():
    """The committed input as a record: the fields Save writes, and the
    fields a saved record is compared with to see whether the nativity in
    the sidebar is still the one that was saved.

    From 2026-09-16 (F03) the record also carries the doctrinal readings in
    force at the save, under "readings", and says which app wrote it and in
    which schema, under "saved_with". The readings are the record's HISTORY,
    not a second copy of the reader's preferences: nothing reads them until
    the record is loaded, and then only to offer them."""
    return {
        "date_string": input_date.isoformat(),
        "time_string": input_time.strftime("%H:%M:%S"),
        "time_standard": time_standard,
        "utc_offset": utc_offset_manual,
        "location_query": location_query,
        "lat": lat,
        "lon": lon,
        "target_mode": target_mode,
        "target_date": target_date.isoformat(),
        "target_age": target_age,
        "readings": _current_readings(),
        "saved_with": {"app": APP_VERSION, "schema": CHART_RECORD_SCHEMA},
    }


# The record's two keys that are not the nativity: the readings, compared
# on their own so that the sidebar can say WHICH side has moved, and the
# stamp, compared never -- a record saved by an earlier build of this app
# has not been "edited since it was saved" for having been saved by it.
_RECORD_NOT_INPUT = ("readings", "saved_with")


_RUN_ZONE_FINDER = []


def _zone_finder():
    """This run's one TimezoneFinder (building one takes a fifth of a
    second), made when a run first asks for it. Not shared between runs or
    sessions: the finder reads its data files by seeking, and Streamlit runs
    sessions in threads of one process."""
    if not _RUN_ZONE_FINDER:
        _RUN_ZONE_FINDER.append(TimezoneFinder())
    return _RUN_ZONE_FINDER[0]


def _cast_zone(record):
    """The zone and offset a record's chart is cast with (ruling 145, B-01):
    the standard, the zone's name where the standard is the named zone (as
    the sidebar resolves it, from the full-precision pair), and the offset
    from UT -- lon/15 hours for LMT, the typed hours for a manual offset,
    the zone's own seconds for its clock reading under a named zone, or the
    refusal's kind where the zone refuses the reading. What cannot be read
    stands as None: two records alike in it are alike."""
    standard = time_standard_current(record.get("time_standard"))
    lat, lon = record_number(record.get("lat")), record_number(record.get("lon"))
    if lat is None or lon is None:
        return (standard, None, None)
    if standard == TIME_STANDARD_OPTIONS[0]:
        return (standard, None, lon / 15.0)
    if standard == TIME_STANDARD_OPTIONS[2]:
        return (standard, None, record_number(record.get("utc_offset")))
    if standard != TIME_STANDARD_OPTIONS[1]:
        return (standard, None, None)
    day = parse_iso_date(record.get("date_string"))
    try:
        hour, minute, second = (int(part) for part in str(record.get("time_string")).split(":"))
    except ValueError:
        moment = None
    else:
        moment = (day.year, day.month, day.day, hour, minute, second) if day is not None else None
    # The zone as the sidebar resolves it (place_zone): the list's and the
    # areas' rules read the moment, and a refusal there is the record's cast.
    try:
        zone = engine.place_zone(lat, lon, _zone_finder(), moment)
    except engine.NamedZoneRefusal as refusal:
        return (standard, None, ("refused", refusal.kind))
    if not zone or moment is None:
        return (standard, zone, None)
    try:
        state = engine.named_zone_state(zone, *moment, latitude=lat, longitude=lon)
    except engine.NamedZoneRefusal as refusal:
        return (standard, zone, ("refused", refusal.kind))
    except (TypeError, ValueError, OverflowError):
        return (standard, zone, None)
    return (standard, zone, state["offset_seconds"])


def _record_inputs_match(stored, record):
    """Whether a stored record describes the nativity `record` describes.

    The stored record's OWN fields are what is compared: a field it does not
    carry cannot have been edited since it was saved, so a record written
    before the time standard or the target was stored with a chart is not
    called modified for lacking them. The coordinates are compared exactly as
    written (ruling 145, B-01): the record holds the pair the chart was cast
    from at full precision, and an edit below the fourth decimal that moves
    the zone line moves the chart. Other numbers are compared as floats to
    four decimals, JSON reading a whole number back as an int. Then the zone
    and offset each side is cast with are compared too (_cast_zone), so an
    edit that moves the chart is never called unchanged."""
    if not isinstance(stored, dict):
        return False
    for field, value in record.items():
        if field in _RECORD_NOT_INPUT or field not in stored:
            continue
        other = stored[field]
        if field == 'time_standard':
            # A record saved under a renamed label holds the same standard
            # (S1-4): compared as the option it is now.
            other = time_standard_current(other)
        if field == 'location_query' and not other:
            # SC-01 of the notes lanes (2026-10-06): a record whose name for
            # its place is empty is opened under its coordinates, and the
            # box names the place as coordinates name themselves; a record
            # opened untouched was called modified for the difference. Its
            # empty name is compared as the name the load gave it.
            _lat, _lon = record_number(stored.get("lat")), record_number(stored.get("lon"))
            if _lat is not None and _lon is not None:
                other = _manual_place_label(_lat, _lon)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # B-05 (ruling 146): the stored number is read as the loader
            # reads it, through record_number. float() raised OverflowError
            # on an int past the float range (a hand edit), and the Save
            # that compared it showed a traceback; a value that is no number
            # is a mismatch, never an exception.
            number = record_number(other)
            if number is None:
                return False
            if field in ('lat', 'lon'):
                if number != float(value):
                    return False
            elif round(number, 4) != round(float(value), 4):
                return False
        elif other != value:
            return False
    # The stored record as the chart a load of it casts: its own fields, and
    # the chart in hand's where it carries none (a field it lacks cannot
    # have been edited, and the load leaves that box as it was).
    loaded = dict(record)
    loaded.update({field: stored[field] for field in record
                   if field in stored and field not in _RECORD_NOT_INPUT})
    return _cast_zone(loaded) == _cast_zone(record)


def _record_readings_match(stored, record):
    """Whether the readings a record was saved under are the ones in force.

    Read on the same principle as every other field: only what the STORED
    record carries is compared. A schema-1 record carries no readings and so
    cannot disagree with any -- it was saved before this app kept them, and
    saying it was "saved with other readings" would be an accusation the
    file does not support."""
    saved = chart_record_readings(stored) if isinstance(stored, dict) else {}
    if not saved:
        return True
    current = record.get("readings") or {}
    return all(value == current.get(key) for key, value in saved.items())


def _records_match(stored, record):
    """Whether a stored record is the chart in hand, input and readings
    alike. The two halves are compared apart above, because the caption
    under the picker names the side that has moved."""
    return _record_inputs_match(stored, record) and _record_readings_match(stored, record)


def _store_as_it_stands(name):
    """L6-02: the mapping to write a change to `name` onto. Two sessions on
    one store (two tabs) each wrote their own stale mapping over the file, so
    the second save dropped the first tab's record and a save from a tab
    opened before a delete brought the deleted record back. So the file is
    read again, and the change is made to what is there, not to what this
    session last saw. If the file's record under `name` is not the one this
    session last saw (another window has written that very name), nothing is
    written: the session takes the file's mapping, says so, and asks for a
    rerun.

    G1: what is in the store's place is read once, and the write is shaped by
    it (engine.saved_charts_as_they_stand). The digest compared here used to
    be None both for a missing file and for one that could not be read, so a
    store announced unreadable was taken as unchanged and replaced, with every
    record in it (L6R-N1); and a store broken under an open session was
    copied aside and replaced by the new record alone under a bare "Saved"
    (L6R-N2). Now:

    - bytes that cannot be read, or a malformed file whose bytes cannot be
      copied aside, are never written over: nothing is written, and the
      sidebar says so;
    - a malformed file is copied aside first, and the write keeps this
      session's records (the file's own cannot be read); the sidebar names
      the copy unless the load already named that copy for these same bytes;
    - an absent or readable file is written as L6-02 has it -- except a file
      removed since this session read or wrote it (K-05 of the re-pass's
      follow-ups, 2026-10-05). An absent file used to be merged onto as an
      empty store: the save wrote its one record alone under a bare
      "Saved", the picker lost every other, and an unchanged re-save called
      its record "deleted by another window" though the whole file had
      gone. Now the write keeps this session's records, as a store broken
      under it is kept (L6R-N2), and the sidebar says the file was removed.

    Returns (mapping, copy, changed): the mapping to write onto, the name of
    a recovery copy the write must announce (or None), and whether the file
    had changed since this session read it -- True or False, or "removed"
    when the whole file has gone since. (None, None, None) after asking for
    a rerun, the notice already set."""
    seen = st.session_state["saved_charts"]
    stands = engine.saved_charts_as_they_stand(keep_aside=True)
    changed = stands.digest != st.session_state.get("_store_digest")
    if stands.state == "unreadable" or (stands.state == "malformed" and stands.copy is None):
        st.session_state["_store_refused_notice"] = (
            "Saved charts could not be read, and no copy of the file could be "
            "made, so nothing was written and the file was left as it is.")
        for _k in ("_replace_pending", "_replace_pending_record", "_delete_pending"):
            st.session_state.pop(_k, None)
        return None, None, None
    if stands.state == "malformed":
        named = not changed and stands.copy == st.session_state.get("_store_named_copy")
        return dict(seen), (None if named else stands.copy), changed
    if stands.state == "absent" and st.session_state.get("_store_digest") is not None:
        # K-05: this session read or wrote a file, and there is none now.
        return dict(seen), None, "removed"
    if "_store_digest" not in st.session_state or not changed:
        return dict(seen), None, False
    fresh = stands.charts
    if fresh.get(name) != seen.get(name):
        st.session_state["saved_charts"] = fresh
        st.session_state["_store_digest"] = stands.digest
        for _k in ("_replace_pending", "_replace_pending_record", "_delete_pending"):
            st.session_state.pop(_k, None)
        # L6R-N7: the record is named, and what was done to it.
        if seen and not set(seen) & set(fresh):
            # SC-07 of the notes lanes (2026-10-06): a file holding none of
            # the records this window read is another file, not this one
            # with a record deleted (removed, then made again by another
            # window's save); "deleted by another window" named one record
            # and passed over the rest.
            moved = ("The saved charts file has been replaced since this window read it, and holds none "
                     "of the charts this window listed.")
        elif name not in fresh:
            moved = f"{_as_typed(name, quoted=True)} was deleted by another window since this one read it."
        elif name in seen:
            moved = f"{_as_typed(name, quoted=True)} was replaced by another window since this one read it."
        else:
            moved = f"{_as_typed(name, quoted=True)} was saved by another window since this one read the list."
        st.session_state["_store_moved_notice"] = moved
        return None, None, None
    return dict(fresh), None, True


def _store_still_holds(name, record):
    """L6R-N7: whether the store as it stands on disk holds `record` under
    `name`. "Already saved as it is" was said against this session's own
    mapping, so a window holding a record another window had since replaced
    called its stale copy saved. Read only: nothing is copied or written. A
    session that never read the store (a mapping seeded by a test) is taken
    at its word, as _store_as_it_stands takes it."""
    if "_store_digest" not in st.session_state:
        return True
    stands = engine.saved_charts_as_they_stand()
    if stands.state != "readable":
        return False
    return (stands.digest == st.session_state["_store_digest"]
            or stands.charts.get(name) == record)


def _write_store(charts, copy, changed):
    """Write `charts` over the store, as _store_as_it_stands shaped it, and
    let the session's mapping and digest follow only if the disk took it.
    A recovery copy the write must announce is told either way, naming no
    file (ruling 135): beside the record written over it, or beside a file
    left as it was. True when it was written."""
    if not write_saved_charts(charts):
        sentence = "The saved charts file could not be written to disk."
        if copy:
            sentence += (" It could not be read either, and was left as it "
                         "is; a copy of it was kept beside the saved charts.")
        st.sidebar.error(sentence)
        return False
    st.session_state["saved_charts"] = charts
    # K-03 of the re-pass's follow-ups (2026-10-05): the digest of the bytes
    # this window has just written, not of a second read of the file, which
    # took another window's write landing in between as this window's own.
    st.session_state["_store_digest"] = engine.saved_charts_digest(charts)
    if copy:
        cause = (": the file had been changed since this window read it"
                 if changed else "")
        st.session_state["_store_kept_notice"] = (
            f"Saved charts could not be read{cause}. A copy of the file was "
            "kept beside the saved charts, and this window's saved charts were "
            "written in its place.")
    elif changed == "removed":
        # K-05: the whole file had gone, not one record.
        st.session_state["_store_kept_notice"] = (
            "The saved charts file had been removed since this window read it, "
            "so this window's saved charts were written to a new one.")
    return True


def _store_chart(name, record):
    """Write the record under `name` and, only if the disk took it, let the
    session's mapping, the preferences and the picker follow (F04, item 7:
    the mapping used to be mutated first, so a failed write left the session
    holding a record the file did not have). True when it was written.

    HP2-02 of the second hostile pass (ruling 63): the read, the change and
    the write are made under the store's lock. Another window's save landing
    between this window's read and its write was written over, and both
    windows said "Saved"; now it waits, and then reads what this one wrote.
    A rerun asked for inside lets the lock go on its way out.

    Ruling 77: the lock is waited on for a bounded time; past it nothing is
    written and the sidebar says another window is holding the saved
    charts. Ruling 109: something standing under the lock's name refuses
    the save, and the sidebar names the folder. A folder that refuses the
    lock call itself refuses the save too, and the sidebar says so."""
    try:
        with engine.saved_charts_lock():
            if st.session_state.get("_store_unmoved"):
                # S02 of SC2's check: this window's load could not move in
                # the store kept in an old place; it is moved in now, under
                # this save's lock, and the save is added to it (a store
                # written without it would have left it out for good).
                engine.bring_in_the_old_store()
            charts, copy, changed = _store_as_it_stands(name)
            if charts is None:
                st.rerun()
            charts[name] = record
            if not _write_store(charts, copy, changed):
                return False
    except engine.DataLockBlocked as blocked:
        st.sidebar.error(_store_blocked_sentence(blocked.folder))
        return False
    except engine.DataLockUnavailable:
        st.sidebar.error(STORE_UNLOCKED_SENTENCE)
        return False
    except engine.DataLockBusy:
        st.sidebar.error(STORE_BUSY_SENTENCE)
        return False
    st.session_state.pop("_store_unmoved", None)
    st.session_state.pop("_loaded_without_standard", None)
    st.session_state.pop("_loaded_unoffered_standard", None)
    # The record under this name is now the one the boxes hold, whatever it
    # was before: an offset outside the bounds (H5) has just been written
    # over with the one the box holds, so the sentence that reported it is
    # no longer true of the record.
    st.session_state.pop("_record_notice", None)
    # The record now holds the readings in force, so there is nothing to
    # ask about it and nothing about it to call old (F03).
    st.session_state.pop("_readings_pending", None)
    st.session_state.pop("_readings_legacy", None)
    # The chart saved is the one the app opens on next time (ruling 78),
    # remembered for the reader, who made no choice of it: a refusal of that
    # write is not said beside the Save that succeeded (SC3's check, as SC's
    # for the last chart forgotten after a delete).
    _remember('last_chart', name, chosen=True, quiet=True)
    st.session_state["_select_after_rerun"] = name
    # The success message is carried over the rerun the caller asks for,
    # so that the reader still sees it beside the picker that now names
    # the record.
    st.session_state["_saved_flash"] = name
    return True


def _free_name(name):
    """The first free '<name> (n)', counting from 2."""
    n = 2
    while f"{name} ({n})" in st.session_state["saved_charts"]:
        n += 1
    return f"{name} ({n})"


# The nativity as it stands, or None when there is nothing to save: the
# record Save writes, and the record the picker's own is compared with.
input_record = _chart_record() if (chart_ok and date_is_valid) else None

# The placeholder suggests what a reader names a nativity by, not a chart of
# this app's own (N-05: it read "e.g. Test Chart 1240").
new_chart_name = st.sidebar.text_input("Chart name (for saving)", value="", placeholder="e.g. the native's name")
# The Save button stands here; what it does is decided below, once every
# refusal of this run has had its say (L6-05).
_save_clicked = st.sidebar.button("\U0001F4BE Save this chart")
_save_slot = st.sidebar.container()
# What Save said on the run that asked for this one (SC-15, below).
_already_saved = st.session_state.pop("_already_saved_flash", None)
if _already_saved:
    _save_slot.info(f"{_as_typed(_already_saved, quoted=True)} is already saved as it is.")

# Where the Export analysis buttons stand: under Save, and filled far below,
# once the chart has been cast and the pages' own row lists can be asked for
# (F08). A container holds the PLACE while the script goes on -- the export
# cannot be built here, where nothing has been computed yet, and a button
# written later without one would land below everything else here.
export_box = st.sidebar.container()

# The readings the prompt asked about, put in force here rather than where
# they were asked about, for the same reason the delete is: every sidebar
# field has been drawn by now, so the rerun below keeps them. Each reading
# goes in by the path its own control uses -- store key, widget key and the
# preferences file -- so that the controls on the pages show it and the next
# session opens under it.
_readings_open_now = st.session_state.pop("_readings_open_now", None)
if _readings_open_now:
    _saved_readings = chart_record_readings(
        st.session_state["saved_charts"].get(_readings_open_now, {}))
    for _label, _wk, _sk, _default, _page in READINGS_REGISTRY:
        if _sk in _saved_readings:
            _set_reading(_wk, _sk, _saved_readings[_sk])
    st.session_state.pop("_readings_pending", None)
    st.rerun()

# A home set on this run: the "Here & Now" button at the top of the sidebar
# was drawn disabled, and the popover's label chosen, before the press was
# seen, so the run is repeated from here, where every field has been drawn
# and a rerun costs nothing. Once: the flag is popped.
if st.session_state.pop("_home_changed", None):
    st.rerun()

# The delete the confirmation asked for, done here rather than where it was
# asked: every sidebar field has been drawn by now, so the rerun below keeps
# them. The disk first, the session's mapping after (item 7).
_delete_now = st.session_state.pop("_delete_now", None)
if _delete_now and _delete_now in st.session_state["saved_charts"]:
    # HP2-02: the read, the change and the write under the store's lock, as
    # a save makes them (_store_chart).
    # Ruling 77: past the lock's bounded wait nothing is written, and the
    # sidebar says so.
    try:
        with engine.saved_charts_lock():
            _remaining, _copy, _changed = _store_as_it_stands(_delete_now)
            if _remaining is None:
                st.rerun()
            _remaining.pop(_delete_now, None)
            _deleted = _write_store(_remaining, _copy, _changed)
    except engine.DataLockBlocked as _blocked:
        st.sidebar.error(_store_blocked_sentence(_blocked.folder))       # ruling 109
        _deleted = False
    except engine.DataLockUnavailable:
        st.sidebar.error(STORE_UNLOCKED_SENTENCE)
        _deleted = False
    except engine.DataLockBusy:
        st.sidebar.error(STORE_BUSY_SENTENCE)
        _deleted = False
    if _deleted:
        # L6R-N6: whichever window made it the last chart, and only while
        # the file still names it.
        _forget('last_chart', only_if=_delete_now, quiet=True)
        st.session_state.pop("_delete_pending", None)
        st.session_state["_select_after_rerun"] = "-- New Chart --"
        st.rerun()
    else:
        st.session_state.pop("_delete_pending", None)

# Modified: the picker names a record and the fields have moved away from
# it (F04, item 2). The strip says so beside the name; the sidebar says so
# under the picker. A record the sidebar could not load is not compared at
# all (H3): the fields never held it, so they cannot have been edited away
# from it, and the sentence beside the picker already says why.
_picked_name = st.session_state.get("chart_picker")
_picked_record = (st.session_state["saved_charts"].get(_picked_name)
                  if _picked_name and _picked_name != NEW_CHART_SENTINEL else None)
# Whether the record the picker names is the one the boxes are holding. A
# record the loader refused for lacking a field the cast needs (L6R-N3) is
# not, while the picker names it, so the strip does not name it over boxes
# it never filled. Read from the loader's own refusal, not recomputed from
# the record: only a record the loader was asked for and refused is one.
#
# K-14, K-15 of the re-pass's follow-ups (2026-10-05): nor is a record
# another window (or a hand edit) has put under the name since this one
# read it. A refused record's name stays unnamed when the record under it
# is replaced: the boxes were never loaded from the new one either (until
# this window loads it, or saves its own under the name). A loaded record
# whose name now holds a different record -- one with no time, or another
# window's nativity -- is no longer what the boxes were loaded from, so the
# strip does not name it, "(modified)" or not. A record the picker names
# without the loader ever having been asked (a seeded session) is named as
# before.
_refused = st.session_state.get("_record_refused")
_loaded = st.session_state.get("_record_loaded")
_picked_loaded = (_picked_record is not None and chart_record_fault(_picked_record) is None
                  and not (isinstance(_refused, dict) and _refused.get("name") == _picked_name)
                  and not (isinstance(_loaded, dict) and _loaded.get("name") == _picked_name
                           and not _same_record(_picked_record, _loaded.get("record"))))
# Which side has moved. From 2026-09-16 a record carries its readings too
# (F03), so there are two ways for the chart in hand to have parted from
# the record the picker names -- the nativity edited, or the readings
# changed under it -- and the caption says which, both lines when both.
_inputs_edited = bool(
    input_record is not None
    and _picked_loaded
    and not _record_inputs_match(_picked_record, input_record))
_readings_changed = bool(
    input_record is not None
    and _picked_loaded
    and not _record_readings_match(_picked_record, input_record))
chart_modified = _inputs_edited or _readings_changed
if chart_modified:
    with picker_note.container():
        if _inputs_edited:
            st.caption("Edited since it was saved.")
        if _readings_changed:
            st.caption("Saved with other readings.")

CONNECTION_PROFILE = _reading("connection_rule", "_connection_rule", "Sahl")
EASTERN_RULE = _reading("eastern_rule", "_eastern_rule", EASTERN_RULE_OPTIONS[0])
MOON_RAYS_ORB = 15.0 if _reading("moon_rays_15", "_moon_rays_15", False) else 12.0
MARS_WEST_RAYS_18 = bool(_reading("mars_west_18", "_mars_west_18", False))
FITTING_INFORTUNE = bool(_reading("fitting_infortune", "_fitting_infortune", False))
DOMAIN_RULE = _reading("domain_rule", "_domain_rule", DOMAIN_RULE_OPTIONS[0])
LOT_HOUSE_CUSP = _reading("lot_house_cusp", "_lot_house_cusp", LOT_HOUSE_CUSP_OPTIONS[0])
# The names above are this run's, for the page's own use; the evaluators read
# them from the engine, which keeps them per thread because Streamlit runs
# every session's script in one of its own. Pinned here, at the top of the
# run, before any evaluator is called. FITTING_INFORTUNE is not among them:
# no evaluator reads it, the page reads it to compute SOFTENED_INFORTUNE,
# which is pinned where it is named (D-13, below).
#
# Every pin goes through _pin_readings, which keeps a record of what this run
# pinned, because a run has a second kind of thread. A click on a widget
# inside a @st.fragment reruns the fragment's body alone, and Streamlit runs
# that body in a fresh ScriptRunner thread whenever the previous run's runner
# has stopped -- the usual case, the reader clicking after the page has
# rendered. The top level does not execute on such a rerun, so nothing pins
# there, and an evaluator called from the body read the module defaults: the
# Timing wheel's house-based Lots stood at the whole-sign cusps under a
# 'quadrant cusp' run (G18 of the doctrine audit, 2026-09-18). Fragments are
# therefore declared with _pinned_fragment, below, which pins this record
# before the body runs, so the body's thread answers as the full run's did.
_RUN_READINGS = {}


def _pin_readings(**values):
    """Pin readings for this run, on the engine for this thread's evaluators
    and in _RUN_READINGS for the fragment reruns that follow it."""
    engine.set_readings(**values)
    _RUN_READINGS.update(values)


def _pinned_fragment(func):
    """st.fragment, with this run's readings pinned before the body runs.

    The body Streamlit stores for a fragment rerun is a closure over the
    full run that declared it, so _RUN_READINGS read here is that run's
    record -- the very values the run pinned at the top and under
    chart_ok -- and the readings a fragment rerun's thread evaluates under
    are the full run's. Nothing between the two runs can have changed
    them: every doctrinal reading's control stands outside the fragments,
    so moving one is a full run. During the full run itself the pin is the
    same values again, in the same thread. No fragment in this file may
    use st.fragment directly; tests/test_fragment_readings_2026_09_18.py
    walks the file for that."""
    @functools.wraps(func)
    def _pinned(*args, **kwargs):
        engine.set_readings(**_RUN_READINGS)
        return func(*args, **kwargs)
    return st.fragment(_pinned)


_pin_readings(CONNECTION_PROFILE=CONNECTION_PROFILE, EASTERN_RULE=EASTERN_RULE,
              MOON_RAYS_ORB=MOON_RAYS_ORB, MARS_WEST_RAYS_18=MARS_WEST_RAYS_18,
              DOMAIN_RULE=DOMAIN_RULE, LOT_HOUSE_CUSP=LOT_HOUSE_CUSP)
# Owner's decision 2026-09-10: ship Abu Ma'shar's quadruplicity turn (IX.1, 26-34)
# as a reading, defaulting to Dykes' plain forward count. Read only by the
# Timing page, so it is not in the Configurations cross-product.
PN4_MONTHLY_TURN = _reading("pn4_monthly_turn", "_pn4_monthly_turn", PN4_MONTHLY_TURN_OPTIONS[0])
# Owner's decision 2026-09-10: the natal wheel carries the Egyptian-bounds
# ring too, as every PN IV wheel does -- the course works the bounds by hand.
CHART_BOUNDS = bool(_reading("chart_bounds", "_chart_bounds", True))
# Owner's ruling 2026-09-15: the wheels and the strips are drawn on white in
# every theme, because that is what a chart on paper is, and the dark
# palette is offered rather than imposed. A display preference like the
# bounds ring and the wheel layout -- not a doctrinal reading, so not in
# READINGS_REGISTRY -- set on the Chart page and in the Timing page's
# Options, one setting for both wheels. Off, every picture is handed None
# and draws exactly as it always has; on, it is handed the viewer's own
# theme, which is the dark palette only when the viewer is in the dark
# theme.
WHEEL_DARK_HELP = ("The wheels and the strips are drawn on a white ground unless this is on, when they take "
                   "the dark palette in the dark theme; in the light theme it changes nothing.")
WHEEL_DARK = bool(_reading("wheel_dark", "_wheel_dark", False))
WHEEL_THEME = VIEWER_THEME if WHEEL_DARK else None
# Which sources are shown (UI_REVIEW_2026-09-10.md §1 B): the course text
# alone, or with Abu Ma'shar's supplement laid beside it. Set on the Sources
# page, where the radio is labelled Sources shown (F12 of the review of
# 2026-09-16: it selects sources, it does not deepen a reading). The stored
# VALUES are unchanged -- the radio prints them through a format_func.
READING_DEPTH = _reading("reading_depth", "_reading_depth", READING_DEPTH_OPTIONS[0])

# READINGS_REGISTRY and _reading() are defined at the head of the sidebar,
# above the saved-chart picker: a saved record carries the readings it was
# saved under (F03), so the registry has to exist before a record is built
# or compared.

def _reading_value_text(value, named=True):
    """A reading's value as the pages print it: a switch's on or off as yes
    or no, never Python's True or False (L7-05 of the hostile pass of
    2026-10-03); a value that is a locator with its work (the eastern
    reading's "VII.2 band" is Gr. Intr.'s, printed on the Sources page,
    which opens with no book), unless the line already names the work
    before it (`named=False`: the readings note's "label = value", whose
    label names Gr. Intr.; ruling 129); every other value as itself."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value == EASTERN_RULE_OPTIONS[1] and named:
        return f"Gr. Intr. {value}"
    return str(value)


def _readings_off_default():
    """The doctrinal readings not at their course default, as (label, value)."""
    out = []
    for label, widget_key, store_key, default, _page in READINGS_REGISTRY:
        value = _reading(widget_key, store_key, default)
        if value != default:
            out.append((label, value))
    return out

# An element that is sometimes there and sometimes not, drawn directly in
# the main block before a page's st.tabs, shifts the tabs' place in the
# element tree between runs; the frontend then takes them for a new tabs
# widget and opens the first tab, which is how a click on a control inside
# the Planetary Condition tab used to throw the reader back to Aspects.
# So every such element takes a fixed slot -- st.empty(), reserved on every
# run and filled only when there is something to say -- and the tabs keep
# their place whatever the readings are. (_stale_notice and the fitting-
# infortune line do the same; conditional elements inside st.columns or a
# container do not move the main block's indices.)
def _readings_note():
    """One line under a page header when a persisted reading is in force
    that a reader might not remember setting (UI_REVIEW §2's caution); with
    several in force, a count and a list of their names and values, still
    one element in the slot (a container holding two captions)."""
    slot = st.empty()
    off = [(l, v) for l, v in _readings_off_default() if l != "Sources shown"]
    if len(off) == 1:
        slot.caption("Readings in force that differ from the defaults: "
                     + "; ".join(f"{l} = {_reading_value_text(v, named=False)}" for l, v in off)
                     + ". They are remembered between runs; see Sources and readings to reset them.")
    elif off:
        with slot.container():
            st.caption(f"{len(off)} readings differ from defaults. "
                       "They are remembered between runs; see Sources and readings to reset them.")
            st.caption("\n".join(f"- {l} = {_reading_value_text(v, named=False)}" for l, v in off))


# One line under the header of every page whose CONTENT the Sources shown
# reading changes -- F12 of the review of 2026-09-16 found the setting
# remote from its effect: it is set on Sources, and the pages it adds
# tables to, moves tabs on and adds rows to said nothing about it. The two
# sentences are the same on every such page; nothing here is page-specific.
def _sources_scope_line():
    """The sources in force, said where their effect is read."""
    if READING_DEPTH == READING_DEPTH_OPTIONS[1]:
        st.caption("Sources shown: Sahl's course texts with Abu Ma'shar's supplement.")
    else:
        st.caption("Sources shown: Sahl's course texts. Abu Ma'shar's supplement is off; "
                   "switch it on under Sources and readings.")


# --- The committed nativity, or the reason there is none -----------------
# F05 of the review of 2026-09-16. The shell must not depend on the draft
# being valid, so the sidebar's validation ends in two names -- chart_ok,
# whether a chart can be cast at all, and chart_error, the one sentence
# that says why not -- and only the calculation is conditional. The page
# functions below are defined whatever the answer is: they are closures
# over these top-level names and resolve them when they are called, so a
# page that is never called never touches a name the invalid run left
# unbound, and each page that reads the chart opens with the recovery
# panel instead of its tables.
tz_name = None
# Ruling 35: where a named mean time is cast (the area's civil clock then),
# the sentence that says so, carried by the box, the Calculation table and
# the exports' input block; so is a pre-1970 window's whose start is this
# app's choice, which opens with its clock; None for every other cast.
# zone_abbreviation is the named mean time's abbreviation, which the strip
# carries (PW-33); a standard time's is not on the strip, as for any
# named-zone cast.
zone_label = None
zone_abbreviation = None
if chart_ok:
    # The local moment as digits in the policy's calendar (a CivilMoment,
    # not a datetime: 1300-02-29 is a date here). The UT moment is a Julian
    # Day, jd_ut, and the offset is subtracted on it -- see the calendar
    # note above calculate_traditional_chart (Astra F01).
    local_dt = CivilMoment(input_date.year, input_date.month, input_date.day,
                           input_time.hour, input_time.minute, input_time.second)
    tz_name = None
    zone_note = ""

    if time_standard == TIME_STANDARD_OPTIONS[0]:
        # 15 degrees of longitude = 1 hour of time. East is +, West is -.
        offset_hours = lon / 15.0
        jd_ut = civil_local_to_jd_ut(local_dt.year, local_dt.month, local_dt.day, local_dt.hour_decimal(), offset_hours)
        dt_utc = pn4_datetime_from_jd(jd_ut)
        tz_name = "LMT"
        # One rounded total of seconds, so the three fields cannot each lose
        # a second to truncation (_offset_text, which the strip reads too).
        offset_str = _offset_text(offset_hours, seconds=True)
        utc_offset_hours = offset_hours
        time_standard_box.info(f"**Exact LMT** · UTC offset {offset_str}  \n"
                               f"UT {dt_utc:%Y-%m-%d %H:%M:%S} · {_ut_cal_note(jd_ut)}")
    elif time_standard == TIME_STANDARD_OPTIONS[2]:
        utc_offset_hours = float(utc_offset_manual or 0.0)
        if utc_offset_refusal:
            chart_error = utc_offset_refusal
            time_standard_box.error(chart_error)
            chart_ok = False
        else:
            jd_ut = civil_local_to_jd_ut(local_dt.year, local_dt.month, local_dt.day, local_dt.hour_decimal(), utc_offset_hours)
            dt_utc = pn4_datetime_from_jd(jd_ut)
            # L1-N4: the offset is cast as typed, so it is named as typed, to
            # the second when it holds seconds (5.125 h is UTC+05:07:30), as
            # a named zone's offset is below. The box takes an offset off its
            # quarter-hour step, and so does a saved record, so it is named
            # rather than refused: the step is the arrows', and nothing else
            # in the sidebar refuses an offset inside the range.
            tz_name = f"UTC{_offset_text(utc_offset_hours)}"
            time_standard_box.info(f"**Manual offset** {tz_name}  \n"
                                   f"UT {dt_utc:%Y-%m-%d %H:%M:%S} · {_ut_cal_note(jd_ut)}")
    else:
        # The place's zone (place_zone): the zone boundaries' answer, or the
        # sourced list's or an area's for this moment (ATLAS1: GeoNames' zone
        # where the boundaries give a border place another country's;
        # refused where the sources leave the clock to the record).
        tz_name = None
        # A named zone needs a datetime, which is proleptic Gregorian: a
        # Julian-only day (1300-02-29) has no place in it, and no zone kept
        # standard time then anyway.
        # The refusals below used to end in st.stop(), which took the page
        # list with them (F05): each states the same sentence in the
        # sidebar's own box and hands it to chart_error, and the else-arm
        # carries what st.stop() used to skip.
        # A zone named Etc/GMT+N is a band of ocean, which timezonefinder
        # answers for every point at sea: it is not a place, and its sign is
        # the POSIX inverse of the offset it carries, so the point has no
        # zone (C-06). A name the time-zone database does not hold has none
        # either (C-07).
        try:
            tz_name = engine.place_zone(lat, lon, _zone_finder(), (local_dt.year, local_dt.month, local_dt.day,
                                                                   local_dt.hour, local_dt.minute, local_dt.second))
            if not tz_name:
                raise engine.NamedZoneRefusal('none')
            _state = engine.named_zone_state(tz_name, local_dt.year, local_dt.month, local_dt.day,
                                             local_dt.hour, local_dt.minute, local_dt.second,
                                             latitude=lat, longitude=lon)
        except engine.NamedZoneRefusal as _refusal:
            _no_zone = ("There is no standard-time zone at these coordinates; "
                        f"choose {_LMT_OR_MANUAL}.")
            if _refusal.kind in ('none', 'sea', 'unknown'):
                chart_error = _no_zone
            elif _refusal.kind in ('clock_choice', 'unsettled'):
                # Rulings 180 (2) and 190: where the sources leave the clock to
                # the record, the two clocks and their offsets are named and
                # the manual offset casts with either.
                chart_error = _clock_choice_sentence(_refusal, local_dt)
            elif _refusal.kind == 'julian':
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** is a Julian-calendar date that no standard-time zone can "
                    f"place. Choose {_LMT_OR_MANUAL}."
                )
            elif _refusal.kind == 'before_rules' and _refusal.abbreviation == '-00':
                # Ruling 61 (d): the record's first state is "-00", which the
                # database uses for a place while uninhabited -- at a record's
                # start (the Canadian Arctic, the Antarctic stations, Kanton)
                # or where Davis, Macquarie and Vostok return to it. It holds
                # no time, so D1's "before ... kept any standard time" and "its
                # reference city" are not said of it.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** falls where {tz_name}'s record holds no time: the time-zone "
                    "database marks the place uninhabited then, so there is no standard-time zone to cast it "
                    f"in. {_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'before_rules':
                # D1 of the owner. The zone's records begin with the local
                # mean time of the zone's reference city, which is not this
                # birthplace's meridian; the sentence is the same in the box,
                # the recovery panel of every page that reads the chart, and
                # nowhere is an offset cast.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** is before {tz_name} kept any standard time, so there is no "
                    "standard-time zone to cast it in: the zone's own record then holds only the local mean "
                    f"time of its reference city, which is not this birthplace's meridian. {_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'linked' and tz_name in engine.PRE1970_WINDOWS:
                # Rulings 82, 104-106, 169 and 171: this place's own clocks
                # are cast inside the windows taken from the sources
                # (engine.PRE1970_WINDOWS), and this moment is in none of
                # them -- before the first, between two, or after the last
                # and before the local 1970 (ruling 180 (1): Blanc-Sablon's
                # 1969-12-31 20:00-24:00). The time is printed: a window can
                # end inside a day. anniversary_moment's reason says the same.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d %H:%M}** is before 1970, and this app casts {tz_name} before 1970 only "
                    "inside the stretches it takes from the sources; this moment is outside them, so there is no "
                    f"standard-time zone to cast it in: the time-zone database holds {tz_name} only as a link to "
                    f"{engine.LINKED_ZONES[tz_name]}, another place's record. {_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'linked':
                # Ruling 1 of the owner on the re-pass (Q1, L1-N1). Before
                # 1970 the database keeps this zone only as a link to another
                # place's record (engine.LINKED_ZONES: Africa/Accra to
                # Africa/Abidjan), so the offset it would give is the other
                # place's, under this birthplace's name. Refused as D1
                # refuses, with the same reach: the box, the recovery panel,
                # and no offset cast, so no strip and no export either.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** is before 1970, so there is no standard-time zone to cast it in: "
                    f"the time-zone database holds {tz_name} only as a link to {engine.LINKED_ZONES[tz_name]}, "
                    "another place's record, which it says agrees with this birthplace's clocks only from 1970. "
                    f"{_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'disputed':
                # Ruling 82: the hour the sources disagree on (Stockholm's
                # 1916-09-30 22:00-23:00 UT, engine.PRE1970_DISPUTED), read
                # at either offset its readings give.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d %H:%M}** falls where the sources disagree on when {tz_name}'s clocks "
                    f"were turned back, so there is no standard-time zone to cast it in. {_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'later_lmt':
                # Ruling 35: a later line of local mean time (the record goes
                # back to LMT after keeping another time, or takes another
                # place's under the name LMT: Lagos 1908-14, Sao Tome, Alaska
                # and the Pacific across the date line). D1's sentence would
                # say "before ... kept any standard time" and "its reference
                # city", which is not true of every one of them.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** falls where {tz_name}'s record holds local mean time (LMT), a time "
                    "taken from one place's meridian and not a standard time, so there is no standard-time zone to "
                    f"cast it in. {_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'mean_time':
                # Ruling 35 of the owner (D1's reach). The zone's record holds
                # a named mean time here, one city's meridian, which the
                # database's notes do not show to have been the area's clock
                # (engine.CIVIL_MEAN_TIMES lists where they do): refused as D1
                # refuses, with the same reach.
                # A summer form names the mean time it was kept on (Riga's LST
                # on RMT, St John's NDT on NST): it is not itself a mean time.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** falls where {tz_name}'s record holds "
                    f"{engine.mean_time_held(_refusal.abbreviation, _refusal.kept_on)}, a mean "
                    "time taken from one place's meridian"
                    f"{engine.mean_time_whose(_refusal.abbreviation, _refusal.kept_on)}, and the time-zone "
                    "database's notes do not show it to "
                    "have been this birthplace's clock then, so there is no standard-time zone to cast it in. "
                    f"{_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'mean_time_exception':
                # Ruling 35: inside the zone whose named mean time was the
                # area's clock, a part that kept its own (Sicily and Sardinia
                # under Rome's, the canton of Geneva under Bern's), found by
                # the coordinates.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** falls where {tz_name}'s record holds "
                    f"{engine.mean_time_held(_refusal.abbreviation, _refusal.kept_on)}, a mean "
                    f"time taken from one place's meridian, but {_refusal.area} kept its own time until "
                    f"{_refusal.until}, so there is no standard-time zone to cast it in. {_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'mean_time_city':
                # Rulings 61 (a) and 66: Rome's time reached the public clocks
                # city by city, and the notes date some cities later (Turin
                # and Bologna 1867-01-01, Venice 1880-05-01); found by the
                # coordinates. What the city kept before is not said.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** falls where {tz_name}'s record holds "
                    f"{engine.mean_time_held(_refusal.abbreviation, _refusal.kept_on)}, a mean "
                    f"time taken from one place's meridian, but {_refusal.area} set its public clocks to it only "
                    f"on {'%04d-%02d-%02d' % _refusal.since}, so there is no standard-time zone to cast it in. "
                    f"{_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'outside_clock':
                # Rulings 97 and 102: after the mean time, the record casts
                # the country's clock on a part whose clock the sources do
                # not establish (Alsace-Moselle from 1911, Trentino, South
                # Tyrol, Trieste and Gorizia from 1893, each to 1921).
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** falls where {tz_name}'s record holds {_refusal.abbreviation}, but "
                    f"the time-zone database's notes speak of {_refusal.country}'s clocks and say nothing of what "
                    f"{_refusal.area} kept then, so there is no standard-time zone to cast it in. {_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'mean_time_outside':
                # Ruling 81 (e): a part of the zone the notes on its country
                # never speak of (Alsace-Moselle under Paris's mean time;
                # Trentino, South Tyrol, Trieste and Gorizia under Rome's),
                # found by the coordinates inside today's borders.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d}** falls where {tz_name}'s record holds "
                    f"{engine.mean_time_held(_refusal.abbreviation, _refusal.kept_on)}, a mean "
                    f"time taken from one place's meridian, but the time-zone database's notes speak of "
                    f"{_refusal.country}'s clocks and say nothing of {_refusal.area}, so there is no "
                    f"standard-time zone to cast it in. {_CHOOSE_BY_LONGITUDE}"
                )
            elif _refusal.kind == 'ambiguous':
                # The clocks are set back for more than daylight saving: New
                # York's 1883 and Tokyo's 1888 adoptions of standard time
                # repeat a stretch too (S1-3, lane F1's check note 3), so the
                # sentence says what happened, not why.
                chart_error = (
                    f"**{local_dt:%Y-%m-%d %H:%M}** happens twice in {tz_name}: its clocks were set back "
                    f"over it. Choose {_LMT_OR_MANUAL}, or enter a time the clocks showed once."
                )
            else:
                chart_error = (
                    f"**{local_dt:%Y-%m-%d %H:%M}** does not exist in {tz_name}: its clocks jumped over it. "
                    "Check the recorded time."
                )
            time_standard_box.error(chart_error)
            chart_ok = False
        else:
            # This is the OFFSET, not the UTC clock time -- an earlier
            # version printed dt_utc's own time under the label "UTC offset".
            _tot = _state['offset_seconds']
            utc_offset_hours = _tot / 3600.0
            jd_ut = civil_local_to_jd_ut(local_dt.year, local_dt.month, local_dt.day, local_dt.hour_decimal(), utc_offset_hours)
            dt_utc = pn4_datetime_from_jd(jd_ut)
            _sign = '+' if _tot >= 0 else '-'
            _tot = abs(_tot)
            # The zone's own history holds offsets with seconds (Monrovia
            # Mean Time, -00:44:30, in 1971); the box says them when there are
            # any. (So do the pre-1970 windows: Amsterdam's AMT, +00:19:32, in
            # 1909-1916; Stockholm's Swedish time, +01:00:14, in 1879-1899.)
            _secs = f":{_tot % 60:02d}" if _tot % 60 else ""
            # Ruling 35: a named mean time is cast only where it was the
            # area's civil clock, and then the box says so.
            zone_label = _state.get('label')
            zone_abbreviation = _state['abbreviation'] if _state.get('civil_mean_time') else None
            _civil = f"{zone_label}.  \n" if zone_label else ""
            time_standard_box.info(
                f"**{tz_name}** · UTC offset {_sign}{_tot // 3600:02d}:{(_tot % 3600) // 60:02d}{_secs}"
                f" ({_state['abbreviation']})  \n{_civil}UT {dt_utc:%Y-%m-%d %H:%M:%S} · {_ut_cal_note(jd_ut)}"
            )
            zone_note = f" · {tz_name}"
    if chart_ok:
        # A label of nothing but spaces (a hand-edited record) prints as
        # nothing, and "****" on a line of its own is a horizontal rule, not
        # an empty bold label (K-29): the box then names the coordinates only.
        # So does a label of nothing visible ("**\u200b**" drew an
        # invisible bold line).
        _place_label = _as_typed(location_query) if _names_something(location_query) else ""
        location_box.success((f"**{_place_label}**  \n" if _place_label else "")
                             + f"{degrees_text(lat, 4)}, {degrees_text(lon, 4)}{zone_note}")

# H1: the moment is in UT by now, offset and all, so this is where to ask
# whether the ephemeris has anything to say about it -- and it is asked
# BEFORE the calculation, and answered like any other invalid input: one
# sentence in the sidebar and chart_ok False. The shell, the top
# navigation, Reference and Sources all stay, and every page that reads the
# chart opens with the recovery panel. The box the branch above filled is
# overwritten rather than left announcing the UT of a chart that is not
# going to be cast.
if chart_ok and not jd_in_ephemeris(jd_ut):
    chart_error = EPHEMERIS_DATE_MESSAGE
    time_standard_box.error(chart_error)
    chart_ok = False

# L6-05: Save and the replace question are answered here, after the named-zone
# and ephemeris refusals above have set chart_ok, so that a chart this run
# refuses to cast is not written as a record and announced "Saved". The record
# is decided again now that chart_ok is final.
input_record = _chart_record() if (chart_ok and date_is_valid) else None

if _save_clicked:
    trimmed_name = new_chart_name.strip()
    # A record is made of committed values or it is not made at all (F01):
    # an invalid draft used to be written out verbatim and to reload, in a
    # session with no last good date behind it, as the 1240 default.
    _save_refusal = _data_folder_refusal()
    if _save_refusal:
        # L6R-N4: nothing can be written where the store cannot be kept.
        _save_slot.error(_save_refusal)
    elif not trimmed_name:
        _save_slot.warning("Enter a name before saving.")
    elif _is_reserved_name(trimmed_name):
        # M3: the picker's first option is not a chart. A record saved under
        # that name was listed twice and could then be neither selected nor
        # deleted, since picking it is picking "new chart".
        _save_slot.error("That name is reserved; choose another.")
    elif not date_is_valid:
        _save_slot.error("The date is not valid; nothing was saved.")
    elif not (lat is not None and lon is not None and location_query
              and coordinates_in_range(lat, lon)):
        _save_slot.error("No place is resolved; nothing was saved.")
    elif input_record is None:
        # L6-05: the run has refused to cast this chart (a date past the
        # ephemeris, a moment the zone skips, a date the zone never kept).
        _save_slot.error("This chart cannot be cast as entered; nothing was saved.")
    else:
        _existing = st.session_state["saved_charts"].get(trimmed_name)
        if _existing is None:
            if _store_chart(trimmed_name, input_record):
                # The picker lists and selects it, and the strip names it,
                # on the rerun this asks for (item 1).
                st.rerun()
        elif (chart_record_fault(_existing) is None and chart_record_lack(_existing) is None
              # SC-17 of the notes lanes (2026-10-06): the match reads only
              # the fields a stored record carries, so a record the loader
              # refuses for lacking its time (or another field a chart is
              # cast with) matched the chart in hand and was never written
              # again. Such a record is not "already saved as it is": the
              # reader is asked whether to replace it, as for any other.
              # B-05 (ruling 146): and it is asked first, so that no such
              # record is ever compared, as the picker's caption never
              # compares one.
              and _records_match(_existing, input_record)):
            if _store_still_holds(trimmed_name, _existing):
                # Nothing to write, and nothing to ask about.
                # Ruling 78 (SC-14): a Save on an unchanged chart is a choice
                # of it, and the app opens on it next time, as on a chart
                # saved or opened. Remembered for the reader, a refusal of
                # that write is not said (SC3's check, as in _store_chart).
                _remember('last_chart', trimmed_name, chosen=True, quiet=True)
                # SC-15: the record the store holds under the name is the
                # one the boxes hold, whatever this window last loaded or
                # refused under it (another window may have replaced it
                # since): the strip names it. The strip is drawn from the
                # state this run has already read, so a change of it is
                # carried over a rerun, the sentence with it.
                _now_loaded = {"name": trimmed_name, "record": _existing}
                _refused_here = st.session_state.get("_record_refused")
                if (st.session_state.get("_record_loaded") != _now_loaded
                        or (isinstance(_refused_here, dict) and _refused_here.get("name") == trimmed_name)):
                    st.session_state.pop("_record_refused", None)
                    st.session_state["_record_loaded"] = _now_loaded
                    st.session_state["_already_saved_flash"] = trimmed_name
                    st.rerun()
                _save_slot.info(f"{_as_typed(trimmed_name, quoted=True)} is already saved as it is.")
            elif _store_chart(trimmed_name, input_record):
                # L6R-N7: this session's copy is the chart in hand, the
                # store's is not (another window replaced or deleted it, or
                # the file cannot be read), so the write decides, and says
                # which: a moved record is named and nothing is written.
                st.rerun()
        else:
            # A name in use and a different nativity: the collision is put
            # to the reader and NOTHING is written on this press (item 4).
            st.session_state["_replace_pending"] = trimmed_name
            st.session_state["_replace_pending_record"] = input_record

# The question stands only while the name and the nativity it was asked
# about stand: any other change in the sidebar rewrites one or the other
# and takes the question with it.
_replace_pending = st.session_state.get("_replace_pending")
if _replace_pending is not None and (
        _replace_pending != new_chart_name.strip()
        or _replace_pending not in st.session_state["saved_charts"]
        or input_record != st.session_state.get("_replace_pending_record")):
    st.session_state.pop("_replace_pending", None)
    st.session_state.pop("_replace_pending_record", None)
    _replace_pending = None
if _replace_pending:
    _save_slot.warning(f"{_as_typed(_replace_pending, quoted=True)} exists. Replace it?")
    _replace_col, _both_col = _save_slot.columns(2)
    if _replace_col.button("Replace", key="_replace_now"):
        if _store_chart(_replace_pending, input_record):
            st.session_state.pop("_replace_pending", None)
            st.session_state.pop("_replace_pending_record", None)
            st.rerun()
    if _both_col.button("Keep both", key="_keep_both"):
        if _store_chart(_free_name(_replace_pending), input_record):
            st.session_state.pop("_replace_pending", None)
            st.session_state.pop("_replace_pending_record", None)
            st.rerun()


if chart_ok:
    chart_data = calculate_traditional_chart_jd(jd_ut, lat, lon)
    p_data = chart_data['planetary_data']
    sect = chart_data['sect']
    # D-13: named here, before any evaluator runs, since they read it.
    SOFTENED_INFORTUNE = fitting_infortune(chart_data['ascendant']) if FITTING_INFORTUNE else None
    _pin_readings(SOFTENED_INFORTUNE=SOFTENED_INFORTUNE)

    essential = evaluate_essential_dignities(p_data, sect)
    accidental = evaluate_accidental_dignities(p_data, chart_data['houses'], sect, chart_data['julian_day'],
                                               armc=chart_data['armc'], obliquity=chart_data['obliquity'], geo_lat=lat)
    aspects = evaluate_ptolemaic_aspects(p_data)
    transfers = evaluate_transfers_of_light(p_data)
    collections = evaluate_collections_of_light(p_data)
    sim = _simulate_forward(p_data, chart_data['julian_day'])
    abu_mashar_condition = evaluate_abu_mashar_condition(
        p_data, chart_data['houses'], sect, essential, accidental, chart_data['julian_day'], chart_data['ascendant'], sim
    )
    banishment_data = evaluate_sahl_banishment(p_data)
    natural_connections = evaluate_abu_natural_connections(p_data)
    wildness_data = evaluate_abu_wildness(p_data)
    reflections = evaluate_reflections_of_light(p_data, chart_data['ascendant'])
    blocking_data = evaluate_blocking(p_data)
    enclosure_data = evaluate_enclosure(p_data)
    handing_over_data = evaluate_handing_over(p_data, sect)
    reception_data = evaluate_reception(p_data, sect, sim)
    non_reception_data = evaluate_non_reception(p_data, sect)
    strength_data = evaluate_strength_of_planets(p_data, essential, accidental, chart_data['ascendant'], sect, chart_data['houses'])
    weakness_data = evaluate_weakness_of_planets(p_data, essential, accidental, chart_data['ascendant'], sect)
    ascensional_bands = evaluate_ascensional_bands(p_data, chart_data['ascendant'], chart_data['mc'], chart_data['obliquity'], lat, sect)
    right_sidedness = evaluate_right_sidedness(p_data, sect)
    honor_guard = evaluate_honor_guard(p_data, chart_data['ascendant'])
    _moon = evaluate_corruption_of_the_moon(p_data, chart_data['houses'], sect)
    returning_data = evaluate_returning(p_data, accidental, chart_data['ascendant'])
    revoking_data = evaluate_revoking(p_data, sim)
    resistance_data = evaluate_resistance(p_data, sim)
    escape_data = evaluate_escape(p_data, sim)
    cutting_data = evaluate_cutting_the_light(p_data, sim)
    favor_recompense_data = evaluate_favor_and_recompense(p_data, essential, sect, sim)
    forward_looking_data = (
        [{'Condition': 'Revoking', **row} for row in revoking_data]
        + [{'Condition': 'Resistance', **row} for row in resistance_data]
        + [{'Condition': 'Escape', **row} for row in escape_data]
    )
    syzygy = calculate_prenatal_syzygy(chart_data['julian_day'], lat, lon, chart_data['houses'])
    syzygy_governor = sahl_syzygy_governor(syzygy, p_data, chart_data['houses'], sect)
    # The cached function takes the local HOUR (an int Streamlit can
    # hash), not the CivilMoment; it reads nothing else of it.
    chronocrats = calculate_chronocrats(chart_data['julian_day'], lat, lon, local_dt.hour, utc_offset_hours)
    classical_lots = calculate_classical_lots(chart_data['ascendant'], p_data['Sun']['longitude'], p_data['Moon']['longitude'], sect)
    topical_lots = calculate_topical_lots(p_data, chart_data['ascendant'], chart_data['houses'], sect)
    special_degrees = evaluate_special_degrees(p_data)
    book_v_degrees_data = evaluate_book_v_degrees(p_data, chart_data['ascendant'], chart_data['lot_of_fortune'], sect)
    nobility_degrees_data = evaluate_nobility_degrees(p_data, chart_data['ascendant'], sect)
    moon_third_day_data = evaluate_moon_third_day(chart_data)
    gestation_data = evaluate_gestation(
        chart_data, lat, lon,
        birth_context={'local_moment': local_dt, 'time_standard': time_standard,
                       'timezone': tz_name, 'utc_offset_hours': utc_offset_hours,
                       'birth_calendar': civil_calendar(local_dt.year, local_dt.month, local_dt.day)})
    mercury_phase_sect_data = evaluate_mercury_phase_sect(p_data, sect)
    mercury_company_data = evaluate_mercury_company(p_data)
    moon_phase_valens_data = evaluate_moon_phase_valens(p_data)
    morin_aspects_data = evaluate_morin_aspects(p_data, chart_data['houses'], chart_data['ascendant'])
    eyesight_places_data = evaluate_eyesight_places(p_data, chart_data['ascendant'])
    rhetorius_affliction_data = evaluate_rhetorius_affliction(p_data, chart_data['ascendant'], sect)
    mars_abu_bakr_data = evaluate_mars_abu_bakr(p_data, sect, chart_data['ascendant'])
    prosperity_data = evaluate_prosperity(chart_data)
    rays_by_ascension_data = evaluate_rays_by_ascension(p_data, chart_data['armc'], chart_data['obliquity'], lat)
    house_lords_data = evaluate_house_lords(p_data, chart_data['ascendant'])
    victors_data = evaluate_victors(p_data, chart_data['ascendant'], chart_data['lot_of_fortune'],
                                     syzygy['syzygy_longitude'], sect, chronocrats)
    planets_in_houses_data = evaluate_planets_in_houses(p_data, abu_mashar_condition, chart_data['ascendant'])
    moon_in_houses_data = evaluate_moon_in_houses(p_data, chart_data['ascendant'])
    time_lords_data = calculate_time_lords(chart_data['ascendant'], input_date, target_date)
    planetary_years_data = evaluate_planetary_years_display(p_data, chart_data['houses'], chart_data['ascendant'], sect, essential,
                                                            supplement=READING_DEPTH == READING_DEPTH_OPTIONS[1])
    pn4 = pn4_timing_bundle(chart_data, lat, lon, input_date, target_date, PN4_MONTHLY_TURN, chronocrats, supplement=READING_DEPTH == READING_DEPTH_OPTIONS[1])
    # Indicator 15's Connected is a plain bool per row inside the engine, but
    # a row whose connection is left to one of the permitted completions of
    # an unresolved connection (evaluate_with_connection_uncertainty raising
    # _ConnectionChoice in _connection_decision, tried both ways and merged)
    # comes back an UnresolvedResult where the two tried completions
    # disagree -- a column pyarrow cannot type with the rest still bool.
    # Only the bool rows are turned to text, here, before either the page
    # (which reads this list) or the export (which reads the same list,
    # unrenamed) can see the mix; the UnresolvedResult itself is left alone,
    # so its reason, source and alternatives still reach the export, and
    # _display_rows still turns it to the page's own words at render time --
    # the mixed-type Count column fix, extended to this table.
    # Nothing else is changed here: the export carries this list, so its
    # Distance stays the engine's float and an empty cell stays None (null
    # in the JSON). The page prints the Distance to hundredths and a dash
    # for an empty cell through _indicator_relationship_rows(), as the
    # Planetary Positions' Absolute is printed on its page and carried as
    # the float (L5-04 and L7-06 of the hostile pass of 2026-10-03).
    if pn4.get('indicator_relationships'):
        pn4['indicator_relationships'] = [
            {**row, 'Connected': (row['Connected'] if is_unresolved(row['Connected'])
                                  else ('Yes' if row['Connected'] else 'No'))}
            for row in pn4['indicator_relationships']]

    # The hub names the chart: the saved chart picked in the sidebar, else
    # "Unsaved chart" -- the strip's own word since the readability round,
    # and one name for one chart on the strip, the hub, the wheel and the
    # export (the hostile pass of 2026-09-22, L4, and its verification: a
    # name typed for saving is a form value until it is saved, and naming
    # the chart by it gave a deleted or never-saved record's name to the
    # chart; the owner's D5 of 2026-09-07 had named an unnamed chart
    # "Transits"). The typed name still names the DOWNLOADED files.
    # Loading a saved chart and then editing its date keeps the saved
    # name on the hub and the wheel; accepted. The strip and the export add
    # "(modified)" to it (F04, item 2; the hostile pass of 2026-10-03, L5-03).
    #
    # The two natal wheels used to be built here, at the top level, from
    # CHART_BOUNDS and WHEEL_THEME. They are built inside the Chart
    # page's _wheel_block() fragment now (item 9, 2026-09-15), from the
    # bounds and dark-wheel values its own widgets hold: a fragment rerun
    # does not re-run this line, so a wheel built here would be the
    # previous full run's wheel. Nothing else on this page or any other
    # read svg_code or svg_wide -- the Chart page's picture and its
    # download button were the only two consumers -- so the top-level
    # build is gone rather than kept beside the fragment's, and the eight
    # pages that never draw a natal wheel no longer generate two of them.
    # A record the sidebar could not load does not name the chart either
    # (H3): the boxes hold what they held before it was picked, so titling
    # the strip with it would name a nativity that is not on the screen.
    # The picker still shows the name the reader clicked, and the sentence
    # beside it says why nothing was loaded.
    chart_name = _picked_name if _picked_loaded else "Unsaved chart"
    _download_stem = re.sub(r'[^A-Za-z0-9]+', '_', _picked_name if _picked_loaded else new_chart_name.strip() or chart_name).strip('_') or 'chart'
    # K-31: cut at 200 characters (ASCII here, so 200 bytes), as the
    # exports' names are, so no wheel's file name passes 255 bytes.
    _download_stem = _download_stem[:200].strip('_') or 'chart'

# The app's name is the browser title (st.set_page_config) and the
# header bar's own; it used to be repeated as an st.title above every
# page's st.header, which cost a heading's height on every page and
# told the reader nothing the window did not already say.

# --- one finding, at three depths ---------------------------------
# Provenance used to live in help= because that was the nearest
# container, and 31 tooltips grew to 22,771 characters of citations,
# quotations, measured frequencies and superseded readings -- served
# as hover text, which cannot be scrolled, selected or searched.
#
# Three depths, and the layers each is served in. GLANCE: what this
# is, in the tooltip -- one sentence, about 200 characters the aim;
# the guard test (tests/test_text_lengths_2026_09_17.py) holds help=
# and glance= to a ceiling of 300 and a caption to 400. CHECK: the
# citation, as a visible caption under the heading (standing · source),
# plus the row's own Source and Standing columns where the table
# carries them; then, visible above the table and at reading width,
# the SUMMARY (one or two sentences: what the reader is looking at)
# and the QUALIFICATIONS (short bold-led statements the result cannot
# be read without -- "This app's synthesis.", "Display only." --
# supplied by the call, never inferred from the rows). AUDIT: the
# quotations, the alternatives and the measurements, in the notes
# expander under the table, as headed sections (note_sections) at
# reading width, or as one Markdown string (notes=) where a block has
# not been divided yet; and, for a row too long for its cell, a
# selectbox under the table that prints one row's fields whole
# (detail= and detail_key=). The largest dossiers place further
# expanders after the finding themselves (_notes_expander), never
# nested. Nothing in these layers reads the chart: every status and
# value comes from the engine's rows.
#
# column_config, name-based: the DataFrame's own values never change
# on this branch (the doctrine fixtures compare them), only how a
# column is displayed. Value/Text/Reading/Source/Note/Notes/
# Quotation/Sentence/Standing are this app's citation- and
# prose-heavy columns, cut off at the default width.
_WIDE_TEXT_COLUMNS = {'Value', 'Text', 'Reading', 'Source', 'Note', 'Notes',
                       'Quotation', 'Sentence', 'Standing', 'Witnesses'}

def _wide_text_columns(df):
    """column_config for a table's own text-heavy columns, by name."""
    return {col: st.column_config.TextColumn(width="large")
            for col in df.columns if col in _WIDE_TEXT_COLUMNS}

# The Date column of the Prediction pages' distributions and directions is
# written in the calendar of its own day, as every UT there is
# (pn4_datetime_from_jd: Julian before the reform's JD, Gregorian from it),
# so a table that runs across the reform changes calendar between two rows.
# The column's help names the calendar; the cells stay as the export
# carries them (the re-pass of 2026-10-04, L5-08). A column wholly on one
# side of the reform names that side's calendar alone: a table of 1990 is
# not told about a Julian calendar none of its cells is in (K-19).
_DATE_COLUMN_HELP = "Each date is in the calendar of its epoch: Julian before the Gregorian reform, Gregorian from it."
_DATE_COLUMN_HELP_GREGORIAN = "Each date is in the Gregorian calendar."
_DATE_COLUMN_HELP_JULIAN = "Each date is in the Julian calendar, before the Gregorian reform."
_REFORM_DAY = (1582, 10, 15)          # the first Gregorian day, as PN4_GREGORIAN_REFORM_JD


def _date_column_help(values):
    """The calendar a Date column's cells are in: one calendar where every
    readable date lies on one side of the reform, both where they straddle
    it or none can be read."""
    days = []
    for value in values:
        m = re.match(r"\s*(-?\d+)-(\d{2})-(\d{2})", str(value))
        if m:
            days.append(tuple(int(g) for g in m.groups()))
    if days and all(d >= _REFORM_DAY for d in days):
        return _DATE_COLUMN_HELP_GREGORIAN
    if days and all(d < _REFORM_DAY for d in days):
        return _DATE_COLUMN_HELP_JULIAN
    return _DATE_COLUMN_HELP


def _date_columns(df):
    """column_config naming the calendar of a table's Date column, if it has one."""
    return {col: st.column_config.TextColumn(help=_date_column_help(df[col].tolist()))
            for col in df.columns if col == 'Date'}

# The columns this app actually prints as "Yes" / "No" / "" -- found
# by checking each candidate's real values (2026-09-15): "Received"
# holds a planet's name and "Active" holds "yes" (lowercase) or a
# full sentence, so neither is here despite the family resemblance.
# Width alone; no CheckboxColumn and no boolean conversion.
_YES_NO_COLUMNS = {'Match', 'Sees ASC', 'Above horizon',
                    "Domain (hayz)", "Of the chart's sect", 'Averse to its place',
                    'Rules differ'}

def _yes_no_columns(df):
    """column_config for a table's own Yes/No/"" columns, by name."""
    return {col: st.column_config.TextColumn(width="small")
            for col in df.columns if col in _YES_NO_COLUMNS}

# Columns whose values are a short PHRASE rather than a word, a name or a
# number: wider than the default, narrower than a prose column. Connection
# holds "Under a single blanket" (Sahl, The Introduction Ch. 3, 7), which
# the default width cuts off mid-word -- and the width of a state's name is
# not a reason to shorten the name the text gives it.
_MEDIUM_TEXT_COLUMNS = {'Connection'}


def _medium_text_columns(df):
    """column_config for a table's own short-phrase columns, by name."""
    return {col: st.column_config.TextColumn(width="medium")
            for col in df.columns if col in _MEDIUM_TEXT_COLUMNS}

# Reading width. Body text at PROSE_WIDTH pixels: a container that
# the page's own width constrains, so prose narrows on a phone and
# stops growing on a wide desktop instead of running the window's
# width. Native and nothing else: no CSS, no st.html, no keyed
# container. The number is settled by measurement in the preview
# (a rendered paragraph's width against the app's own font) so that
# a line holds about 65-75 characters, the reading-width target.
PROSE_WIDTH = 680

def _prose():
    """A container at reading width for body text, notes and detail."""
    return st.container(width=PROSE_WIDTH)

# One notes disclosure, the same everywhere: the book icon (which is
# what the table walker in tests/conftest.py skips an expander by),
# and inside it, at reading width, headed sections -- each heading a
# bold line of its own, each body one Markdown string that may hold
# a comparison table or a "> " quotation, and never an st.dataframe,
# which would enter the table fixture under the expander's label.
NOTES_ICON = ":material/menu_book:"
NOTES_TITLE = "Sources and editorial notes"

# The Sect table's caption, ONE string for the Dignities page and the export
# alike, so that a reader of either sees why a Diurnal chart's Sun can read
# "Above horizon: No" in the minutes his disk shows while his centre is
# still below the true horizon (hostile pass 2026-10-03, F5 check 4). The
# Sun's domain reads that division, not his centre, at his rising and his
# setting alike (the owner's rulings 61 (c) and 88 of 2026-10-06;
# evaluate_accidental_dignities quotes the sentences), so his row can read
# "Above horizon: No" and "Domain (hayz): Yes" together, and the last
# sentence says why.
SECT_CAPTION = ("Sect: Sahl, The Introduction Ch. 3, 85. Domain: Gr. Intr. VII.1, 37 and VII.6, 13 "
                "(or Masha'allah, On Nativities 1.23, 17, per the reading in force). Above horizon: the body's "
                "centre against the true horizon by its own altitude; day and night themselves are divided at "
                "the Sun's visible rising and setting, as the Chart page states. The Sun's own domain reads him "
                "by that division.")

# Topical Planets in Houses' qualification, ONE string for the Dignities
# page, which prints it over the table, and the export, which carries it
# with the table (ruling 146, B-08).
NATAL_ADAPTATION = ("**Natal adaptation.** The Book II entries adapt PN IV's annual rules for planets serving as lord "
                    "of the year to natal house positions. The source evaluates the root and revolution together; the "
                    "natal lookup does not establish those annual prerequisites. The columns summarize suitable and "
                    "adverse conditions, with the qualifications shown in each entry.")

def _note_sections(sections):
    with _prose():
        for heading, body in sections:
            st.markdown(f"**{heading}**")
            st.markdown(body)

def _notes_expander(title, sections):
    """A sibling topic expander a page places after a finding, for a
    dossier too large for one expander; never nested in another."""
    with st.expander(title, icon=NOTES_ICON):
        _note_sections(sections)

def _paragraphs(text, *leads):
    """A display representation of an engine note: the text cut into
    paragraphs before each lead phrase, in order, the engine's own string
    untouched -- joined back with one space, the pieces are the constant
    (tests/test_readability_c_2026_09_17.py holds each site to that).
    The notes are runs of adjacent literals in engine.py, where a blank
    source line puts no break into the value, so the paragraph breaks
    are made here, at named sentence boundaries, and the same string
    still feeds the export and every evaluator unchanged."""
    parts, rest = [], text
    for lead in leads:
        head, sep, tail = rest.partition(lead)
        parts.append(head)
        rest = sep + tail
    parts.append(rest)
    return [p.strip() for p in parts if p.strip()]

def _slug(title):
    return re.sub(r'\W+', '_', title.lower()).strip('_')

# "Read details for": a selectbox listing one field of every row, in
# the table's order, unselected until the reader picks -- the keyboard
# path to a row whose cells are too long to be read in the table --
# and the row's fields printed whole under it by the caller's own
# renderer. Widget key `<slug>_detail`, the slug derived from the
# finding's title as _tick_grid derives its grid key.
def _display_result(value):
    """Turn engine result objects into scalar page text at the UI boundary."""
    if isinstance(value, YearsOutcome):
        return value.text
    # Two or more partners met together (PN IV III.1, 50): "Mars and Venus".
    # Known by its marker, so this boundary names no engine class.
    if getattr(value, 'pn4_together', False):
        return str(value)
    # A truth value inside a list or a mapping prints as the reports print a
    # bare flag (yes/no), never as Python's True/False.
    if isinstance(value, (list, tuple)):
        return '; '.join(('yes' if v else 'no') if isinstance(v, bool) else str(_display_result(v))
                         for v in value)
    if isinstance(value, dict):
        return '; '.join(f"{k}: {('yes' if v else 'no') if isinstance(v, bool) else _display_result(v)}"
                         for k, v in value.items())
    if not isinstance(value, UnresolvedResult):
        return value
    heading = value.display_label or {
        'unresolved': 'Unresolved',
        'unavailable': 'Unavailable',
        'unassigned': 'Unassigned',
        'not decided': 'Not decided',
    }[value.status]
    # An alternative whose value is a truth value prints in the words its
    # evaluator, or the column the result stands in, already gives those two
    # values when they are settled -- not as Python's True/False, which
    # reached the pages and all three exports (the re-pass of 2026-10-04,
    # L7-05 and L5R-04). By the result's reason (a prefix where the reason
    # goes on to name its case); the engine's values stay typed in the JSON.
    # Any other truth value prints yes/no, the words the reports and the
    # Yes/No columns give a bare flag (Indicator 15's Connected, for one).
    # Mercury's two domain flags are yes/no, as the Sect table's Domain
    # (hayz) column prints the first: "in its domain" and "contrary to its
    # domain" are not the two values of either flag, since a planet may be
    # neither (domain_description's third wording).
    words = {
        # _connection_merge's Status of a row present under some permitted
        # completions only: _split_labels's names for the same two values.
        'this finding depends on an unresolved connection': ('holds', 'does not hold'),
        # ProsperityAssessment.result: its evidence's words, and the
        # lifetime row's "Lifelong happiness: met / not met".
        'whose easternness is required remains open': ('met', 'not met'),
        'satisfied under the declared checks; remaining defects not fully assessed': ('met', 'not met'),
        'partial / not fully assessed: ': ('met', 'not met'),
        # Dykes's fn 28 gate on Mercury (Abu 'Ali, JN Ch. 4): whether a
        # benefic companion's own Ch. 4 row adds, in that column's words.
        'Mercury lacks the required sextile or trine to the house-master': (
            'adds its lesser years', 'adds or subtracts nothing'),
        'no benefic companion actually adds under JN Ch. 4': ('adds its lesser years', 'adds or subtracts nothing'),
        'the only qualifying benefic companion has an unresolved Ch. 4 contribution': (
            'adds its lesser years', 'adds or subtracts nothing'),
        # Mercury's domain flags at an unassigned phase sect.
        "Mercury's domain depends on its unassigned phase sect": ('yes', 'no'),
        "Mercury's contrary-domain state depends on its unassigned phase sect": ('yes', 'no'),
    }
    yes, no = next((pair for reason, pair in words.items() if value.reason.startswith(reason)), ('yes', 'no'))
    # An alternative whose value is empty prints nothing: "if Moon eastern
    # preference met: " is a conditional with no consequence, and it reached
    # the page, the export and the Markdown from a governor route on which
    # the candidate held no model points (L5-11, the hostile pass of
    # 2026-10-03). The empty alternative stays on the object for the JSON.
    shown = [(name, (yes if result else no) if isinstance(result, bool) else _display_result(result))
             for name, result in value.alternatives]
    alternatives = ('; '.join(f"{name}: {text}" for name, text in shown if str(text) != '')
                    if value.display_alternatives else '')
    return f"{heading} — {value.reason}" + (f" ({alternatives})" if alternatives else '')


def _point_name(point):
    """A point as a sentence names it: a planet's name bare ("Saturn"); the
    luminaries, and a point that takes the article, with it ("the Sun", "the
    Ascendant")."""
    return point if point in ('Saturn', 'Jupiter', 'Mars', 'Venus', 'Mercury') else f"the {point}"


def _named_empty_arms(value, words):
    """An arm of an unresolved result whose value is None (an arm with no
    releaser or no house-master) carries the engine's words for it, not a
    printed "None"; the object itself, and the JSON's null, are untouched."""
    if not isinstance(value, UnresolvedResult):
        return value
    return dataclasses.replace(value, alternatives=tuple((name, words if result is None else result)
                                                         for name, result in value.alternatives))


def _short_life_headline(short_life):
    """The short-life headline (Sahl, On Nativities 1.18), built once for the
    Releaser page and for the line the reports print over the short-life
    table, so the two cannot drift. Returns (the bold head, the separator,
    the rest, the reports' label). Where testimony 4 is open the count is a
    range, its two totals, and the sentence is given at each end, or once
    where both ends give the same (the owner's ruling 145); the label is
    then an UnresolvedResult carrying the two totals typed, whose display
    is the head, the separator and the rest. Where nothing is open the label
    is the same words as a string."""
    count, sentence = short_life['count'], short_life['sentence']
    tail = ("Shown beside the releaser; they do not disqualify it here. "
            "5-7 are \"equivalent\" and not counted (fn 126, 129).")
    head = "The short-life testimonies (1.18, 1-10, Masha'allah, fn 125): "
    if not isinstance(count, UnresolvedResult):
        head += f"{count} of the four counted"
        rest = f"{sentence}. {tail}"
        return head, ' -- ', rest, f"{head} -- {rest}"
    ends = [n for _name, n in count.alternatives]
    head += (' or '.join(str(n) for n in ends) if all(isinstance(n, int) for n in ends)
             else str(_display_result(count))) + " of the four counted (4 is open)"
    if isinstance(sentence, UnresolvedResult):
        sentence = '; '.join(f"{name}, {_display_result(s)}" for name, s in sentence.alternatives)
    rest = f"{sentence}. {tail}"
    label = UnresolvedResult(rest, count.source, alternatives=count.alternatives,
                             display_label=head, display_alternatives=False)
    # _display_result prints it "head — rest"; the page prints the same.
    return head, ' — ', rest, label


def _display_rows(rows):
    shown = [{key: _display_result(value) for key, value in row.items()} for row in rows]
    # A row left open by an undecided connection carries a Status the
    # settled rows beside it lack (_connection_merge gives it only to the
    # open row), and a table drew every other row's Status as NaN (the
    # re-pass of 2026-10-04, L7-06). Each such row gets an empty Status,
    # as the Markdown and HTML reports already print it: nothing is open
    # there, as the Planetary Condition's Unresolved column is blank where
    # nothing is open.
    if any('Status' in row for row in shown):
        shown = [row if 'Status' in row else {**row, 'Status': ''} for row in shown]
    return shown


def _source_text(value):
    """Source supplies such as <not> must survive Markdown/HTML rendering."""
    return str(_display_result(value)).replace('<', '&lt;').replace('>', '&gt;')


def _detail_selector(title, data, detail_key, detail, placeholder):
    options = [str(_display_result(row[detail_key])) for row in data]
    if len(set(options)) != len(options):
        options = [f"{n}. {option}" for n, option in enumerate(options, 1)]
    picked = st.selectbox("Read details for", options, index=None, key=f"{_slug(title)}_detail",
                          placeholder=placeholder)
    if picked is not None and picked in options:
        with _prose():
            detail(data[options.index(picked)])

# A finding with nothing to report is not given a heading at all --
# it is collected and named in one line at the foot of its group,
# which is what turns seventeen "No X found" headings into four.
# standing= is the finding's own footing -- "Supplement", "display
# only" -- which used to be a parenthesis inside the h3 itself. The
# heading is the finding's NAME; the footing and the citation are one
# caption under it, separated by a middle dot.
def _finding(bucket, title, citation, data, glance=None, notes=None, columns=None, height=None,
             standing=None, absent=None, column_help=None, caption=None,
             summary=None, qualifications=None, detail=None, detail_key=None, under_table=None,
             detail_placeholder="Select a row to read its grounds and source passages",
             notes_title=NOTES_TITLE, note_sections=None):
    if not data:
        # absent= is for a finding whose emptiness is the END OF A SEARCH,
        # not an absence: the search ran, it was bounded, and what it
        # covered has to be said where the zero rows are (F07). Such a
        # finding keeps its own heading and says what was looked at,
        # instead of joining the "Not present in this chart" line, which
        # claims more than a bounded search can establish.
        if absent:
            st.subheader(title, help=glance)
            st.caption(absent)
            return
        bucket.append(title)
        return
    st.subheader(title, help=glance)
    if standing or citation:
        st.caption(" · ".join(part for part in (standing, citation) if part))
    # summary= and qualifications= are body text at reading width above
    # the table: what the rows are, then the statements the rows cannot
    # be read without, each its own bold-led paragraph.
    if summary or qualifications:
        with _prose():
            if summary:
                st.markdown(summary)
            for _statement in (qualifications or ()):
                st.markdown(_statement)
    # columns= pins the order (pandas otherwise takes the first
    # row's); height= shows every row of a table meant to be read
    # whole, instead of st.dataframe's ten-row inner scroll.
    if columns is not None and any('Status' in row for row in data) and 'Status' not in columns:
        columns = list(columns) + ['Status']
    _df = pd.DataFrame(_display_rows(data), columns=columns)
    # column_help= is the one-line definition of a column whose HEADING is
    # a term of art, carried on the heading itself rather than in the notes
    # expander, so the word is defined where it is read (F10).
    _help = {col: st.column_config.TextColumn(
                 help=text, **({'width': 'medium'} if col in _MEDIUM_TEXT_COLUMNS else {}))
             for col, text in (column_help or {}).items() if col in _df.columns}
    # placeholder="": a missing value is drawn empty, as the grids draw it
    # and the exports print it; without a placeholder Streamlit draws the
    # word "None" in the cell (a Revoking row's empty Escape cells, a
    # merged Moon outcome's empty Unresolved).
    st.dataframe(_df, hide_index=True, width='stretch', placeholder="",
                 column_config={**_wide_text_columns(_df), **_yes_no_columns(_df),
                                **_medium_text_columns(_df), **_help},
                 **({'height': height} if height is not None else {}))
    # caption= sits UNDER the table, for the sentence that explains the
    # rows themselves rather than the finding's source.
    if caption:
        st.caption(caption)
    # under_table= is body text at reading width under the table: a
    # statement that qualifies particular rows, read beside them.
    if under_table:
        with _prose():
            for _statement in under_table:
                st.markdown(_statement)
    # detail= prints one chosen row whole, under the table, from the
    # same rows the table was built from.
    if detail is not None and detail_key:
        _detail_selector(title, data, detail_key, detail, detail_placeholder)
    # The notes: headed sections at reading width (note_sections=),
    # one Markdown string as before (notes=), or both, notes first.
    if notes or note_sections:
        with st.expander(notes_title, icon=NOTES_ICON):
            if notes:
                st.markdown(notes)
            if note_sections:
                _note_sections(note_sections)

def _absent(bucket):
    if bucket:
        st.caption("Not present in this chart: " + ", ".join(bucket) + ".")
        del bucket[:]

# The strip under every page header: which chart the page is reading.
# The app opens on the last chart used, and nothing above the fold
# named it except the sidebar's picker and the wheel's hub -- and the
# wheel is on one page of nine. One caption, the parts separated by a
# middle dot, each formatted as the sidebar's own boxes format it, so
# the strip and the sidebar cannot come to disagree.
def _chart_strip(counts_from_the_ascendant=False):
    # No chart, no strip: a recovery page has nothing to name (F05).
    if not chart_ok:
        return
    # A record the sidebar could not load does not name the chart either
    # (H3): the boxes hold what they held before it was picked, so naming
    # the strip after it would name a nativity that is not on the screen.
    # The picker still shows the name the reader clicked, and the sentence
    # beside it says why nothing was loaded.
    # One name on the strip, the hub and the export: the picked record's,
    # else the name typed for saving, else "Unsaved chart" (L4 of the
    # hostile pass of 2026-09-22 and its verification's typed-draft case).
    # The name is printed as it was typed, not read as Markdown (L6R-N8):
    # the strip is a caption, and a caption renders markdown.
    name = _as_typed(_picked_name) if _picked_loaded else "Unsaved chart"
    # A record whose fields have been edited since it was saved is named as
    # what it is (F04, item 2): the review found an edited record still
    # carrying its saved name with nothing to say the two had parted.
    if chart_modified:
        name = f"{name} (modified)"
    # The offset as the sidebar's box prints it, sign and all (L1-N5): LMT
    # resolves to the second; a named zone gives the seconds its own history
    # holds, when it holds any; a manual offset is its own name, to the
    # second when it holds seconds (L1-N4).
    _offset = _offset_text(utc_offset_hours, seconds=time_standard == TIME_STANDARD_OPTIONS[0])
    # A manual offset's name IS its offset ("UTC+05:00"), so it is not
    # printed twice.
    standard = tz_name if tz_name.startswith("UTC") else f"{tz_name} {_offset}"
    # A named mean time cast as the area's clock is named on the strip by its
    # abbreviation, as the box names it (PW-33: Lyon 1900, "Europe/Paris
    # +00:09:21" with no PMT where the box says PMT was the civil clock).
    if zone_label and zone_abbreviation:
        standard += f" ({zone_abbreviation})"
    # Coordinates entered directly name themselves -- the place IS
    # "Manual [43.7792, 11.2463]" -- so the strip prints them once. A
    # place's label is printed as it was typed or saved (L6R-N8).
    # A label of nothing but spaces names nothing, so the strip prints the
    # coordinates alone there too (K-29), and so does a label of nothing a
    # reader can see (a zero-width space).
    # A coordinate that rounds to zero prints 0.00, not -0.00 (N04, ruling 107: the
    # atlas's Beniarbeig, 0.0021 W, printed "38.82, -0.00").
    _coords = f"{degrees_text(lat, 2)}, {degrees_text(lon, 2)}"
    place = (_coords if location_query.startswith("Manual [") or not _names_something(location_query)
             else f"{_as_typed(location_query)} {_coords}")
    # The prenatal lunation is one of the first questions asked of a
    # nativity, and the strip is on every page, so it rides here as
    # one word: the label is "Conjunctional (New Moon)" and its first
    # word is the answer. The degree and the house it falls in stay
    # on the lunation and victors page, whose syzygy table carries
    # them in full.
    lunation = syzygy['event_label'].partition(' ')[0]
    # Two lines, not one: the first is the nativity as it was entered
    # -- the name, the moment, the standard it is counted in, the
    # place -- and the second is what the app makes of it. Eight parts
    # on one line ran past the window and wrapped where the width
    # happened to fall, which put the break in a different place on
    # every page. The hard break is two spaces and a newline, which is
    # how the sidebar's own boxes break a caption.
    # The COMMITTED date, never the draft in the box: the strip names the
    # chart the page is showing, and "not-a-date 14:30" named a chart that
    # was never cast (F01a).
    entered = " · ".join((
        str(name),
        f"{input_date:%Y-%m-%d} {input_time:%H:%M:%S}",
        standard,
        place,
    ))
    # The qualification travels with the value (F09). Where there is no
    # sunrise or sunset the hour is not a temporal hour at all, and the
    # strip is on every page while the Chart page's fuller warning is on
    # one: an unqualified hour lord elsewhere is the same value said
    # without the thing that makes it approximate.
    hour_lord = f"Hour lord {chronocrats['Hour Lord']}"
    if chronocrats.get('Approximate'):
        hour_lord += " (equal-hour approximation)"
    read = " · ".join((
        sect,
        f"{lunation} lunation",
        # The day lord likewise says where he is the civil weekday's, no
        # sunrise lying within a day behind the moment (the owner's ruling
        # of 2026-10-05, Q7), and where his weekday repeats, two sunrises
        # having fallen on one civil date (ruling 25, FQ-6).
        f"Day lord {day_lord_qualified(chronocrats)}",
        hour_lord,
    ))
    # The second line in bold: the first line is the nativity as the
    # reader typed it and they know it already, while these four are
    # measurements the app made, and nothing else above the fold
    # states them. The markers wrap the joined line once, not each
    # part -- a caption renders markdown, as the sidebar's own boxes
    # do.
    # One element whatever the draft date says: the strip caption alone, or
    # a container holding the caption and the stale-date warning, in one
    # st.empty() slot -- so the elements after it, a page's st.tabs among
    # them, keep their place in the element tree (see _readings_note).
    # At the pole the strip of every page built on the Ascendant carries the
    # pole's qualification in the same slot, as it carries the equal-hour
    # approximation: the Chart page's sentence stood on that page alone
    # while the places, Lots and lords counted from that Ascendant were
    # printed elsewhere with no word of it (the re-pass of 2026-10-04,
    # L1-07). The Chart page says it beside its cusps; the reference
    # tables and the sources read no chart.
    pole = counts_from_the_ascendant and AT_POLE
    strip = "  \n".join((entered, f"**{read}**"))
    slot = st.empty()
    if (chart_ok and not date_is_valid) or pole:
        with slot.container():
            st.caption(strip)
            _stale_notice()
            if pole:
                st.warning(POLE_ASCENDANT_SENTENCE)
    else:
        slot.caption(strip)


def _stale_notice():
    """One line under the strip while the draft date does not parse: the
    tables below it are the last valid chart's and have not moved (F01d).
    The sidebar says the same of the date field; this says it where the
    results are, on every page."""
    if chart_ok and not date_is_valid:
        st.warning(f"Results have not updated. Showing the last valid chart: "
                   f"{input_date:%Y-%m-%d} {input_time:%H:%M:%S}.")


def _recovery_panel(title):
    """What a page that reads the chart shows when there is no chart: its
    own header, the one sentence that says why, and where to fix it. The
    reference tables and the sources do not call it -- they read the
    engine's tables, not the chart, and render in full (F05)."""
    st.header(title)
    st.error(chart_error)
    st.caption("Correct the nativity in the sidebar; the reference tables and the sources "
               "stay available.")

# Streamlit drops a widget's state when the widget is not rendered
# on a run, which is why a page-level control resets after
# navigating away even with a key. _persist() copies the widget's
# value into a store key that survives navigation; the widget takes
# st.session_state.get(store_key, default) as its default, so the
# page and the engine (which read the same store at the top level)
# agree on the first render.
def _persist(widget_key, store_key, default):
    """Render-independent memory for a page widget. Call AFTER the widget.
    A store that is a preference is also written to disk (2026-09-10)."""
    if widget_key in st.session_state:
        st.session_state[store_key] = st.session_state[widget_key]
        _remember(store_key, st.session_state[store_key])
    return st.session_state.get(store_key, default)

def _reading_checkbox(label, widget_key, store_key, help=None):
    st.checkbox(label, value=st.session_state.get(store_key, False), key=widget_key, help=help)
    return _persist(widget_key, store_key, False)

def _reading_select(label, options, widget_key, store_key, help=None):
    options = list(options)
    stored = st.session_state.get(store_key, options[0])
    st.selectbox(label, options, index=options.index(stored) if stored in options else 0,
                 key=widget_key, help=help)
    return _persist(widget_key, store_key, options[0])

def _reading_radio(label, options, widget_key, store_key, help=None,
                   label_visibility="visible", format_func=None, default=None):
    # label_visibility is passed through for the one control that
    # stands in a row of checkboxes, where a label above the options
    # puts the radio on a tier of its own. The label string is still
    # given -- Streamlit requires a non-empty one, and it stays the
    # widget's accessible name and the name a test looks it up by.
    options = list(options)
    default = options[0] if default is None else default
    stored = st.session_state.get(store_key, default)
    # Seeded, not defaulted by index: the target keys are also written
    # by _restore_chart, and a default beside a seeded key warns.
    st.session_state.setdefault(widget_key, stored if stored in options else default)
    # format_func changes only what the reader sees: the option VALUES are
    # what is stored, compared and printed in the readings table.
    st.radio(label, options, key=widget_key, horizontal=True, help=help,
             label_visibility=label_visibility, format_func=format_func or str)
    return _persist(widget_key, store_key, default)

# Strength and Weakness as tick grids: one row per planet, one column
# per numbered testimony, ticked where the planet's Labels cite that
# paragraph. The labels end in "(78)" ... "(100)", or "(84; ...)",
# "(95, ...)" where a citation follows; the first such number is the
# paragraph. The sentence form stays under the grid as the answer key.
STRENGTH_COLUMNS = [('78', '78 excellent place'), ('79', '79 own dignity'), ('80', '80 direct'),
                    ('81', '81 not in infortune stakes'), ('82', '82 not with fallen'),
                    ('83', '83 advancing'), ('84', '84 eastern, masculine'), ('85', '85 of sect'),
                    ('86', '86 fixed sign'), ('87', '87 heart of Sun'), ('88', '88 gender match')]
WEAKNESS_COLUMNS = [('91', '91 falling, averse ASC'), ('92', '92 retrograde'), ('93', '93 under rays'),
                    ('94', '94 connects infortune'), ('95', '95 enclosed'), ('96', '96 own fall'),
                    ('97', '97 averse / lost receiver'), ('98', '98 alien'), ('99', '99 with nodes'),
                    ('100', '100 inverted')]
_PARAGRAPH = re.compile(r'\((\d{2,3})(?=[;,)])')
# citation reads "Sahl, The Introduction Ch. 3, 78-88": everything
# before the trailing run of sentence numbers is the chapter locator.
_CITATION_LOCATOR = re.compile(r'^(.*), [\d\s,-]+$')

def _tick_grid(bucket, title, citation, data, text_key, columns, glance=None, notes=None,
               key=None, note_sections=None):
    if not data:
        bucket.append(title)
        return
    st.subheader(title, help=glance)
    if citation:
        st.caption(citation)
    grid = []
    for row in data:
        cited = {m.group(1) for m in map(_PARAGRAPH.search, row['Labels']) if m}
        unresolved = {t['n'] for t in row.get('Testimonies', [])
                      if isinstance(t.get('result'), UnresolvedResult)}
        cells = {'Planet': row['Planet']}
        for num, header in columns:
            cells[header] = '?' if num in unresolved else ('\u2713' if num in cited else '')
        # Count stays an int in every row; a planet's unresolved testimonies
        # go in their own column instead of turning Count into a string on
        # some rows and a number on others -- a column pyarrow cannot type
        # and Streamlit silently papers over with a legacy table. Unresolved
        # is None rather than 0 where there is none: when at least one row
        # in the grid has something unresolved, pandas upcasts the whole
        # column to float64 (NaN, not 0) for it, a NumberColumn beside
        # Count rather than the blank TextColumn a plain int-or-'' would
        # need (Moon Defects' "str, not int-or-''" fix works a cell at a
        # time; a whole numeric column reads better here). Not a pandas
        # nullable Int64: that keeps the blank as pd.NA, which prints as
        # the leaking "<NA>" (test_rendered_capitals_2026_09_21's guard
        # catches it) rather than NaN's lower-case "nan". On a grid with
        # nothing unresolved at all the column is every value None, which
        # pandas types object rather than float64; Arrow nulls it out either
        # way. A null cell is not drawn blank by itself: Streamlit draws a
        # missing value as the word "None" unless the dataframe names a
        # placeholder, so every grid here passes placeholder="" and a cell
        # with nothing open is drawn empty (the exports print it empty too).
        cells['Count'] = row['Count']
        cells['Unresolved'] = len(unresolved) if unresolved else None
        grid.append(cells)
    # Each testimony column's header becomes the words alone -- "78
    # excellent place" reads "excellent place" -- with the sentence
    # number moved into the header's tooltip: the chapter locator
    # read off `citation` itself (not invented) plus the number, or
    # "sentence 78" alone where the citation does not name a chapter.
    _locator_match = _CITATION_LOCATOR.match(citation) if citation else None
    _locator = _locator_match.group(1) if _locator_match else None
    _grid_columns = {'Planet': st.column_config.TextColumn(width="small"),
                      'Count': st.column_config.NumberColumn(width="small"),
                      'Unresolved': st.column_config.NumberColumn(width="small", format="%d")}
    for num, header in columns:
        _grid_columns[header] = st.column_config.TextColumn(
            label=header[len(num) + 1:],
            help=f"{_locator}, {num}" if _locator else f"sentence {num}",
            width="small")
    # A row can be selected (single-row, rerun): the grid's key is
    # its title, lower-cased and underscored, unless key= names it
    # (so a title can change without the key). The selection reruns
    # the fragment this grid stands in and nothing else on the page.
    _grid_key = key or _slug(title) + '_grid'
    _event = st.dataframe(pd.DataFrame(grid), hide_index=True, width='stretch', height=_rows_height(len(grid)),
                          column_config=_grid_columns, on_select="rerun", selection_mode="single-row",
                          key=_grid_key, placeholder="")
    _picked = list(_event.selection.rows)
    if _picked and 0 <= _picked[0] < len(data):
        _row_detail(data[_picked[0]], len(columns), _locator)
    with st.expander("Answer key: testimonies in words"):
        answer_rows = [{
            'Planet': row['Planet'],
            # The resolved words and the unresolved ones joined only where
            # both exist (the hostile pass of 2026-09-22, L1: a dangling "; ").
            text_key: '; '.join(part for part in (
                row[text_key],
                '; '.join(_display_result(t['result']) for t in row.get('Testimonies', [])
                          if isinstance(t.get('result'), UnresolvedResult))) if part),
            'Count': row['Count'],
            'Unresolved': row['Unresolved Count'] if row.get('Unresolved Count') else None,
        } for row in data]
        st.dataframe(pd.DataFrame(answer_rows, columns=['Planet', text_key, 'Count', 'Unresolved']),
                     hide_index=True, width='stretch', height=_rows_height(len(data)), placeholder="",
                     column_config={'Count': st.column_config.NumberColumn(width="small"),
                                    'Unresolved': st.column_config.NumberColumn(width="small", format="%d")})
    if notes or note_sections:
        with st.expander(NOTES_TITLE, icon=NOTES_ICON):
            if notes:
                st.markdown(notes)
            if note_sections:
                _note_sections(note_sections)

# Why a tick fired: the selected planet's row, one block per ticked
# testimony in numerical order -- the sentence's locator as the
# column tooltips give it, the sentence as the answer key words it,
# then the chart values the evaluator tested, which it reports as
# "Fact: Value" strings alongside each label (its Testimonies key).
# Nothing here is computed on the page; the panel restates the
# evaluator's own reasoning and adds no test of its own.
def _row_detail(row, total, locator):
    unresolved_count = row.get('Unresolved Count', 0)
    count_text = (f"{row['Count']} resolved of {total}; {unresolved_count} unresolved"
                  if unresolved_count else f"{row['Count']} of {total}")
    st.subheader(f"{row['Planet']}: {count_text} testimonies")
    for testimony in sorted(row.get('Testimonies', []), key=lambda t: int(t['n'])):
        st.caption(f"{locator}, {testimony['n']}" if locator else f"sentence {testimony['n']}")
        st.markdown(_display_result(testimony['sentence']))
        if isinstance(testimony['facts'], UnresolvedResult):
            st.caption(_display_result(testimony['facts']))
            continue
        facts = [fact.partition(': ') for fact in testimony['facts']]
        if len(facts) == 1:
            st.caption(testimony['facts'][0])
        elif facts:
            st.dataframe(pd.DataFrame([{'Fact': name, 'Value': value} for name, _, value in facts]),
                         hide_index=True, width='stretch', height=_rows_height(len(facts)))
        # A fact that holds under only some permitted readings of an
        # undecided connection, with the reason it is open.
        for fact in testimony.get('Unresolved facts', ()):
            st.caption(_display_result(fact))

# Table heights: st.dataframe shows about ten rows and then scrolls
# inside itself. A table meant to be read whole gets its own height:
# 35 px per row and header, 3 px of border, and 12 px for the
# horizontal scrollbar a wide table (the aspects grid, the tick
# grids) draws -- measured at 1280 px, where without it those
# tables were 9 px short and still scrolled.
def _rows_height(n):
    return 35 * (n + 1) + 15

# The sidereal clocks and the RAMC are read on their circles, [0, 24) hours
# and [0, 360) degrees, and printed to the second: a value within half a
# second of the circle's end rounded up to "24h 00m 00s" and "360° 00' 00"",
# outside the circle (the outside inventory of 2026-10-06, N02). The rounded
# total stops at the last second below the end, as degrees_text stops a
# longitude at 359.9999 (the owner's ruling Q6: the carry stops at the
# boundary).
def _hms(hours):
    total = min(int(round((hours % 24.0) * 3600)), 24 * 3600 - 1)
    return f"{total // 3600:02d}h {(total % 3600) // 60:02d}m {total % 60:02d}s"

def _dms(degrees):
    total = min(int(round((degrees % 360.0) * 3600)), 360 * 3600 - 1)
    return f"{total // 3600}° {(total % 3600) // 60:02d}' {total % 60:02d}\""


# --- The rows a page draws, and the export writes down --------------------
# F08 of the review of 2026-09-16 asks that an exported analysis carry the
# results the pages show -- the SAME results, not a second computation of
# them. Most of them already stand at the top level, where every evaluator
# runs once a run (aspects, receptions, strength, weakness, the victors,
# the whole timing bundle). These nine were built inside a page function,
# so they are built here instead and the page calls them: one list, drawn
# by the page and written down by the export, which cannot drift from what
# the reader saw because it IS what the reader saw.
#
# Each reads the top-level names the page read (chart_data, p_data,
# essential, accidental, ...), so each is called only when chart_ok.

def _positions_rows():
    """Planetary Positions (Chart page)."""
    rows = []
    for p, d in p_data.items():
        if p == 'North Node':
            continue
        lon_p = d['longitude']
        q = get_effective_house(lon_p, chart_data['houses'])
        phase, side, elong = solar_phase(p, lon_p, p_data['Sun']['longitude'], p_data[p].get('speed_in_lon'),
                                         latitude=p_data[p].get('latitude'))
        acc_p = accidental[p]
        ws_place = get_wsh_house(lon_p, chart_data['ascendant'])
        rows.append({
            "Planet": p,
            "Position": get_degree_string(lon_p),
            # On the circle: -1e-16 prints 0.0000°, not a signed zero (K-16),
            # and a value a hair under 0 Aries 359.9999°, not 360.0000°,
            # beside its Position's 29° Pis 59' (degrees_text); and a hair
            # under any sign's end the last value below it, 239.9999° beside
            # 29° Sco 59', not the next sign's 240.0000° (N01).
            "Absolute": f"{degrees_text(lon_p, 4, zodiac=True)}°",
            "WS place": ws_place,
            "Sees ASC": "No (averse)" if ws_place in (2, 6, 8, 12) else "Yes",
            # Sahl's sense (Ch.3, 4-5: stake or succedent vs. falling), not
            # Abu Ma'shar's quadrant term of VI.26, 3. Cited in the caption.
            "Quadrant": ("undefined at this latitude" if AT_POLE
                         else f"{q}, {'advancing' if q in ANGLE_HOUSES | SUCCEDENT_HOUSES else 'retreating'}"),
            "Motion": ('Retrograde' if acc_p['Retrograde']
                       else 'Stationary' if acc_p['Stationary'] else 'Direct'),
            "Solar phase": (f"{phase}, {side}" if phase and side else (phase or '–')),
        })
    return rows


def _positions_export_rows():
    """Planetary Positions as the export carries it: Absolute is the
    longitude the calculation holds, the float, where the page prints it to
    four places with a degree sign (the hostile pass of 2026-10-03, L5-04;
    the export's precision paragraph names the column, ruling 11).
    The Markdown and the HTML print it to four places as the page does,
    through degrees_text on the circle: the float is carried as a
    CircleLongitude, which the JSON writes as the float it is."""
    return [{**row, "Absolute": CircleLongitude(p_data[row["Planet"]]['longitude'])} for row in _positions_rows()]


def _indicator_relationship_rows():
    """Indicator 15's relationship details as the Revolutions page prints
    them (the hostile pass of 2026-10-03, L7-06): the Distance to hundredths
    of a degree, as text (the Description beside it states it to the
    tenth), and a pair in aversion, which has no motion, applicant or
    receiver, given the dash its State column already prints for it rather
    than an empty cell the page would draw as NaN. The export carries
    pn4['indicator_relationships'] itself -- the engine's float, and None --
    as it carries the Positions' Absolute (L5-04)."""
    return [{**row,
             **{key: '–' for key in ('Motion', 'Applicant', 'Receiver') if row[key] is None},
             # Printed on its own side of every bound the connection is read
             # against, as the Description beside it is (N08: 12.0001 printed
             # "12.00" beside a row outside the window).
             'Distance': (verdict_text(row['Distance'], 2, bound_sides(CONNECTION_BOUNDS))
                          if isinstance(row['Distance'], float) else row['Distance'])}
            for row in pn4['indicator_relationships']]


def _calculated_point_rows():
    """Calculated Points (Chart page): the four angles, the Nodes, Fortune."""
    north_node_lon = p_data['North Node']['longitude']
    points = {
        'Ascendant': chart_data['ascendant'],
        'Midheaven': chart_data['mc'],
        'Descendant': chart_data['descendant'],
        'Imum Coeli': chart_data['ic'],
        'North Node': north_node_lon,
        'South Node': (north_node_lon + 180.0) % 360.0,
        'Lot of Fortune': chart_data['lot_of_fortune'],
    }
    return [{"Point": name, "Position": get_degree_string(lon_val)} for name, lon_val in points.items()]


# At the pole no ecliptic degree rises or sets: the diurnal motion runs
# parallel to the horizon, the Ascendant has no semi-arc to trisect, and
# the quadrant divisions are undefined. The Chart page says so and
# withholds the cusps (hostile pass 2026-10-03, L1-07), as the distributions
# already refuse above the polar circle. |lat| within a millionth of a
# degree of 90 counts as the pole.
AT_POLE = lat is not None and abs(lat) >= 90.0 - 1e-6
POLE_HOUSES_SENTENCE = ("At the pole no ecliptic degree rises or sets, so the Ascendant has no semi-arc "
                        "and the quadrant divisions are undefined at this latitude. The Ascendant and "
                        "Midheaven shown are where the ecliptic meets the horizon and the meridian, not a "
                        "rising degree.")
# Which degree that is (the re-pass of 2026-10-04, L1-07): at the pole the
# horizon is the celestial equator, so the ecliptic meets it only at the
# equinoctial points, 0 Aries and 0 Libra, each on a sign boundary, and the
# eastern one is chosen by the RAMC -- by the moment and by the longitude
# typed, which at the pole is all that fixes the meridian. Measured with
# swe.houses at 90N and 90S, 2000-12-21, every hour and every 15 degrees
# of longitude: the Ascendant is 0, 180 or a hair under 360 or 180, so
# its sign is Aries, Libra, Pisces or Virgo by the last digit.
POLE_CROSSING_SENTENCE = ("There the horizon is the equator, which the ecliptic crosses at only two points, each "
                          "on the boundary between two signs: the Ascendant is one of them, and which one turns "
                          "on the moment and the longitude entered.")
# The pages built on the Ascendant carry the qualification on their strip,
# and the exports carry it in their status, of the tables they hold.
POLE_ASCENDANT_SENTENCE = ("At the pole no ecliptic degree rises or sets, so an Ascendant cast there is where the "
                           "ecliptic meets the horizon, not a rising degree. " + POLE_CROSSING_SENTENCE
                           + " Every place, Lot and lord this page counts from the Ascendant rests on that point.")
POLE_ASCENDANT_EXPORT_SENTENCE = POLE_ASCENDANT_SENTENCE.replace("this page counts", "these tables count")


def _house_cusp_rows():
    """Quadrant divisions (Alchabitius) (Chart page); one row saying why
    not at the pole."""
    if AT_POLE:
        return [{"House": "1-12", "Cusp": "undefined at this latitude: no ecliptic degree rises at the pole"}]
    return [{"House": i + 1, "Cusp": get_degree_string(chart_data['houses'][i])} for i in range(12)]


def _lordship_rows():
    """Lordship Mapping (Dignities page)."""
    triplicity_key = 'triplicity_day' if sect == 'Diurnal' else 'triplicity_night'
    rows = []
    for p, data in p_data.items():
        if p == 'North Node':
            continue
        rulers = get_essential_rulers(data['longitude'])
        # The planet's own claim at its position, from the labels the
        # dignity evaluation already computed, without the app's
        # point weights ("Domicile (+5)" -> "Domicile").
        own = [re.sub(r'\s*\([+-]\d+\)', '', lbl) for lbl in essential[p]['Essential Labels']]
        rows.append({
            "Planet": p,
            "Position": get_degree_string(data['longitude']),
            "Sign Dispositor": rulers['domicile'],
            "Exaltation Lord": rulers['exaltation'],
            "Triplicity lord": rulers[triplicity_key],
            "Bound lord": rulers['term'],
            "Face lord": rulers['face'],
            "Own dignity here": ", ".join(own) if own else ("Peregrine" if essential[p]['Peregrine'] else "-"),
        })
    return rows


def _sect_table_rows():
    """Sect (Dignities page), under the Domain rule in force."""
    rows = []
    for p, data in p_data.items():
        if p == 'North Node':
            continue
        # The engine's row carries the planet's sect; the fallback is computed
        # only when a row lacks it (a default argument would run it every time).
        own_diurnal = accidental[p].get('PlanetSect')
        if own_diurnal is None:
            own_diurnal = planet_sect_is_diurnal(p, data['longitude'], p_data['Sun']['longitude'])
        # Above the horizon by the body's own ALTITUDE (_sin_altitude, from
        # its ecliptic longitude, latitude and distance against the chart's
        # RAMC and latitude), the horizon the same row's hayz is read
        # against -- not the ecliptic proxy (lon - Ascendant) % 360 > 180,
        # which inverts near the poles and on the horizon (hostile pass
        # 2026-10-03, L1-02).
        above = _sin_altitude(data['longitude'], data.get('latitude', 0.0), data.get('distance', 1.0),
                              chart_data['obliquity'], chart_data['armc'], chart_data['geo_lat']) > 0.0
        rows.append({
            "Planet": p,
            "Planet's sect": (own_diurnal if isinstance(own_diurnal, UnresolvedResult)
                               else ('Diurnal' if own_diurnal else 'Nocturnal')),
            "Above horizon": 'Yes' if above else 'No',
            "Of the chart's sect": (own_diurnal if isinstance(own_diurnal, UnresolvedResult)
                                     else ('Yes' if own_diurnal == (sect == 'Diurnal') else 'No')),
            "Domain (hayz)": (accidental[p]['Hayz'] if isinstance(accidental[p]['Hayz'], UnresolvedResult)
                              else ('Yes' if accidental[p]['Hayz'] is True else 'No')),
        })
    return rows


def _house_lord_rows():
    """Topical House Lords (Dignities page). Averse: the lord sits in the
    2nd, 6th, 8th or 12th sign from the house it rules, so it does not see
    its own place."""
    return [{**{k: v for k, v in r.items() if k != "Masha'allah Signification"},
             'Averse to its place': 'Yes' if (r['Placed in (WS place)'] - r['Topical House']) % 12 in (1, 5, 7, 11) else 'No'}
            for r in house_lords_data]


# The four Lots that have their own table at the top of the Lots page, and
# so are kept out of the topical table below it.
CLASSICAL_LOT_NAMES = ('Lot of Fortune', 'Lot of Spirit', 'Lot of Exaltation', 'Lot of Basis')


def _classical_lot_rows():
    """Classical Lots (Lots page). The Formula comes from the same
    LOT_DEFINITIONS text the Topical Lots table carries (through
    calculate_topical_lots), so the two cannot differ."""
    formula_by_lot = {r['Lot']: r['Formula'] for r in topical_lots}
    rows = []
    for r in classical_lots:
        row = {k: v for k, v in r.items() if k != 'Standing'}
        row['Formula'] = formula_by_lot[r['Lot Name']]
        row['Standing'] = r['Standing']
        rows.append(row)
    return rows


# The Topical Lots table's heading on the Lots page and in the export, one
# string for both at every depth (the re-pass of 2026-10-04, L5-10).
TOPICAL_LOTS_HEADING = "Topical Lots (Sahl, On Nativities)"


def _topical_lot_rows():
    """Topical Lots (Lots page). A row flagged Supplement -- Abu Ma'shar's
    form of a Lot Sahl also gives, or a Lot of his Sahl has not -- is shown
    only under Course text and supplement, so the Sources shown reading
    decides the length of this list."""
    supplement = READING_DEPTH == READING_DEPTH_OPTIONS[1]
    return [{k: v for k, v in r.items() if k not in ('Id', 'Longitude', 'Operative')} for r in topical_lots
            if r['Lot'] not in CLASSICAL_LOT_NAMES and lot_visible(r, supplement)]


# The columns the Lots page draws for its two tables of Lots: the topical
# worksheet, and the comparison table of each Lot's provenance under its
# expander. Each export carries these columns and no others, in the page's
# order, as the Topical Planets in Houses export does
# (TOPICAL_EXPORT_COLUMNS): copied whole, the rows had reached the reports
# with the Supplement flag, the provenance columns under the worksheet's
# heading, and under the provenance heading the positions, the operative
# flag and an internal Id (the re-pass's follow-ups of 2026-10-05, K-27).
LOT_WORKSHEET_COLUMNS = ('Topic', 'Lot', 'Position', 'WS place', 'Lord', 'Formula', 'Status')
LOT_PROVENANCE_COLUMNS = ('Topic', 'Lot', 'Status', 'Standing', 'Source', 'Editor’s note')


def _page_columns(rows, columns):
    """Rows cut to the columns a page draws, in the page's order; a field a
    row does not carry stays absent, as the export always had it."""
    return [{key: row[key] for key in columns if key in row} for row in rows]


def _lot_provenance_rows():
    """Provenance and standing per Lot (Lots page): the four classical Lots'
    provenance, then the topical Lots' -- the rows the page's selector and
    its comparison table read."""
    return [r for r in topical_lots if r['Lot'] in CLASSICAL_LOT_NAMES] + _topical_lot_rows()


def _syzygy_rows():
    """Prenatal Lunation (Syzygy) (Lunation and victors page)."""
    r = syzygy['rulers']
    # The triplicity table named and printed is the one Sources shown
    # shows: Sahl's under Course text, the Great Introduction's (Mercury,
    # not Mars, partnering in Virgo) only with Abu Ma'shar's supplement
    # (L5-05 of the hostile pass of 2026-10-03). The governor and the
    # almuten read the sect's lord alone, which the two tables share, so
    # nothing computed here moves with the depth.
    _table = 'Great Introduction' if READING_DEPTH == READING_DEPTH_OPTIONS[1] else 'Sahl'
    _trip = triplicity_rulers(r['sign'], table=_table)
    triplicity_str = (
        f"{syzygy_governor['triplicity_lord']}★ (Natal sect: {syzygy_governor['triplicity_sect']}) · "
        f"Day: {_trip['Day']} · Night: {_trip['Night']} · Partner: {_trip['Participating']}"
    )
    return [
        {"Metric": "Event Type", "Value": syzygy['event_label']},
        {"Metric": "Position", "Value": get_degree_string(syzygy['syzygy_longitude'])},
        {"Metric": "Natal House", "Value": f"House {syzygy['natal_house']}"},
        {"Metric": "Domicile Lord", "Value": r['domicile']},
        {"Metric": "Exaltation Lord", "Value": r['exaltation']},
        {"Metric": "Triplicity Lords", "Value": triplicity_str},
        {"Metric": "Triplicity table", "Value": TRIPLICITY_TABLE_SOURCES[_table]},
        *([{"Metric": "Virgo source note", "Value": VIRGO_PARTNER_NOTE}] if r['sign'] == 'Virgo' else []),
        {"Metric": "Term Lord", "Value": r['term']},
        {"Metric": "Face Lord", "Value": r['face']},
        {"Metric": "Governor of the syzygy degree (Sahl, On Nativities 1.7, 3-7)",
         "Value": syzygy_governor['summary']},
        {"Metric": "This app's approximation of 1.7 (one point a listed condition)",
         "Value": syzygy_governor['model_how']},
        {"Metric": "Almuten by 5/4/3/2/1 points (al-Qabisi's weights, ITA I.18; a technique not in Sahl; the lunation's sect, this app's convention for the degree's almuten)",
         # A tie at the top stays typed: the page shows it as "Unresolved"
         # with the tied lords and their points, and the export carries
         # the object, as the governor row two above does for its own tie.
         "Value": (syzygy['almuten'] if is_unresolved(syzygy['almuten'])
                   else f"{syzygy['almuten']} (Score: {syzygy['almuten_score']})")},
    ]


# ==========================================
# THE ANALYSIS EXPORT
# ==========================================
# F08 of the review of 2026-09-16: "There is no portable, versioned research
# record". The app could download a wheel and save a nativity; nothing bound
# what was entered to what was in force, what was computed and what computed
# it, so a result on a screen could not be reproduced by another machine or
# compared with the same chart cast a month later.
#
# Two files, one content: a JSON record for a machine and a Markdown report
# for a reader. Both carry the same header -- the app's identity, the
# committed input, the readings in force, the target -- and both are built
# from the row lists the pages themselves draw, never from a second
# calculation. No source text beyond the citations and notes the pages
# already print: the translations are copyrighted and stay out of it.

ANALYSIS_SCHEMA = 1

# The forward-looking conditions (revoking, resistance, escape, cutting) are
# searched this many days past the chart. Read from the engine's own default
# rather than written down again, so the export cannot quote a horizon the
# search does not use.
FORWARD_SEARCH_DAYS = _simulate_forward.__defaults__[0]

def app_identity():
    """What computed this, as the exports carry it: the ephemeris the
    positions are read from. The owner's ruling 27 (2026-10-05, block F of
    the page-text read after Step 4) drops the provenance block -- the app's
    version, the libraries under it and the checksum of the calculation
    code -- from what a reader opens; the ruling names those three, and the
    ephemeris, which says what the positions are computed from, stays."""
    return {
        "ephemeris": "Moshier (built in)",
    }


# --- What the export writes down -----------------------------------------
# (page, heading, citation the page prints for it, rows). The heading is the
# subheader or expander label the reader sees, so that a row in the file can
# be found on the screen; table_inventory() in the harness reads the same
# strings off a rendered page, which is how the two are held together.
#
# The rows are the page's OWN lists: the nine factored above, and the
# evaluator results that already stand at the top level. Nothing here calls
# an evaluator.

def _condition_tables(condition, primary=None):
    """IX.9, 11-13 as (label, rows) pairs, one table each, never asking the
    typed result for a truth value. One primary: one unlabelled table. A
    tied primary (IX.9, 10 names one planet "more primary than the others"
    and the text does not break a tie): one table per tied planet, labelled
    with its name and the tie. A tied opening partner on top of that wraps
    the result once more, route by route, and the labels are joined; a
    route whose own primary is a single planet is wrapped the same way, so
    its label takes that planet's name from `primary` (the governor's,
    wrapped route by route like the condition) -- every table names the
    planet it is built for."""
    if is_unresolved(condition):
        routes = dict(primary.alternatives) if is_unresolved(primary) else {}
        out = []
        for name, value in condition.alternatives:
            route_primary = routes.get(name, primary)
            for inner, rows in _condition_tables(value, route_primary):
                label = f"{name} ({condition.reason})"
                if inner:
                    label += f"; {inner}"
                elif name in routes and isinstance(route_primary, list) and len(route_primary) == 1:
                    label += f"; {route_primary[0]}"
                out.append((label, rows))
        return out
    return [(None, condition)] if condition else []


# The revolution's convention, as the Revolutions page states it over the
# table: the export carries it beside the table (HP-16).
REVOLUTION_TRUE_SUN_CITATION = (
    "A true-Sun return: the revolution is cast for the moment the true Sun comes back to his position at the "
    "root, the return PN IV I.2, 1 defines. Abu Ma'shar computes a mean Sun and then applies the Hipparchan "
    "tropical year (PN IV I.4, 23-31), which is not reproduced here.")

# The fixed stars' reading, ONE string for the Revolutions page, which prints
# it over the two star tables, and the export, which carries it with each of
# them (ruling 146, B-09).
FIXED_STARS_READING = (
    "**The fixed stars (I.6, 7 in the root; III.8, 9 in the revolution)** -- Sahl's list, *On Nativities* "
    "2.2, in Dykes's identifications (the table at that chapter's end, with Rhetorius Ch. 58's natures); "
    "PN IV names no stars of its own. \"The very degree\" and \"with\" are read as within one degree "
    "of longitude; the planets \"in the stakes\" by whole-sign place; latitude ignored. Positions from "
    "the Swiss Ephemeris star catalogue this app ships.")


def _page_line_text(markdown):
    """A line the page prints in Markdown, as the export carries it: the
    same words, without the emphasis marks the page renders as bold or
    italic, so that the JSON, the Markdown and the HTML read one text."""
    return re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", markdown)


def _releaser_arm_directions():
    """Each arm of an election open on the Moon's easternness, as (label,
    direction, reading at the revolution's moment): the arm's releaser
    directed by PN IV III.1, 12, which the governor reads for #3 on that arm.
    Empty on a settled election. One source for the Releaser page and the
    export, so the label the page prints is the label the export carries."""
    return [(f"PN IV testimony #3, {arm}", direction, at_revolution)
            for arm, direction, at_revolution in (pn4['releaser_arms'] or ())]


def _timing_bundle_tables():
    """The timing bundle's tables, under the Prediction pages' own subheaders
    (the export's section label is "Prediction": the bundle spans the four
    pages Revolutions, The releaser, Days and months and Fardar and ages).
    Several headings carry more than one table, which is why a heading maps
    to a LIST of tables throughout the export. Each is (heading, citation,
    rows[, label]); the label is the line the page prints over the table."""
    ii3, gov_rows = pn4['ii3'], pn4['governor'][0]
    rel, father = pn4['releaser'], pn4['father_lot']
    day_rows, day_month, day_ninth = pn4['day_methods']
    image_rows = pn4['image'][0]
    out = [
        # The page qualifies the return in a sentence over this table; the
        # export carries the qualification with it (the hostile pass of
        # 2026-10-03, HP-16).
        ("The revolution of the year", REVOLUTION_TRUE_SUN_CITATION, pn4['revolution_rows']),
        ("The image of the revolution of the year: its points (PN IV I.6, 3-8)", None, image_rows),
        # The page reads the fixed stars in a sentence over both tables; the
        # export carries it with each (ruling 146, B-09).
        ("The image of the revolution of the year: its points (PN IV I.6, 3-8)",
         _page_line_text(FIXED_STARS_READING), pn4['fixed_stars']['rows']),
        ("The image of the revolution of the year: its points (PN IV I.6, 3-8)",
         _page_line_text(FIXED_STARS_READING), pn4['fixed_stars_revolution']['rows']),
        ("The reading checklist (PN IV I.7, 1-26)", None, pn4['i7_ascendant']),
        ("The reading checklist (PN IV I.7, 1-26)",
         f"Motion (7): a planet within {STATION_SPEED_TOLERANCE} degrees a day of rest is stationary, neither direct "
         "nor retrograde (this app's own figure; I.7, 7 names direct and retrograde only); Sahl's strength testimony 80 "
         "on the Configurations page reads the same three states.",
         pn4['i7_planets']),
        ("Indicators of the year, in Abu Ma'shar's order (PN IV II.1, 5-24)", None, pn4['year_rows']),
        ("The sign of the terminal point and its lord, examined (PN IV II.3, 2-19)", None, ii3['root_rows']),
        ("The sign of the terminal point and its lord, examined (PN IV II.3, 2-19)", None, ii3['revolution_rows']),
        ("The sign of the terminal point and its lord, examined (PN IV II.3, 2-19)", None, ii3['lord_rows']),
        ("The sign of the terminal point and its lord, examined (PN IV II.3, 2-19)", None, ii3['refinement_rows']),
        ("The sign of the terminal point and its lord, examined (PN IV II.3, 2-19)", None, ii3['figure_55']),
        ("Indicators 6-19: the fact each one reads (PN IV II.1, 11-24)", None, pn4['further_rows']),
        ("Indicator 15: relationship details", None, pn4['indicator_relationships']),
        ("The lord of the orb (PN IV VI.1)", None, pn4['orb_rows']),
        ("The governor (PN IV IX.9, 1-10; IX.2, 4-7)", None, gov_rows),
        # A tied primary's tables, each with the line the page prints over
        # it, in the entry's label and not in its citation (F3 check 18).
        *[("The governor (PN IV IX.9, 1-10; IX.2, 4-7)", None, rows, label)
          for label, rows in _condition_tables(pn4['governor_condition'], pn4['governor'][1]['primary'])],
        ("The governor (PN IV IX.9, 1-10; IX.2, 4-7)", None, pn4['first_month_governor'][0]),
        ("The Moon's connections in her sign, and the portions of the year (PN IV II.22)", None, pn4['moon_rows']),
        ("The Moon's connections in her sign, and the portions of the year (PN IV II.22)", None, pn4['portion_rows']),
        ("Proxies and the host of the lord of the year (PN IV II.13, 1; II.14, 1; II.22, 1-5, 23-25)", None, pn4['proxies']),
        ("The turning of the houses of the root (PN IV VI.2)", None, pn4['turning_rows']),
        ("The turning of the houses of the root (PN IV VI.2)", None, pn4['turning_triplicity_rows']),
        ("The distribution from the Ascendant (the *jar bakhtar*)", None, pn4['distribution_rows']),
    ]
    if pn4['iii2_type'] is not None:
        # The page draws the III.2 checklist only when there IS a current
        # distribution to analyse; where there is none it says so in a
        # sentence and draws nothing, and the export follows it.
        out += [("The distribution analysed (PN IV III.2)", None, pn4['iii2_checklist']),
                ("The distribution analysed (PN IV III.2)", None, pn4['iii2_transitions'])]
    out.append(("The distribution analysed (PN IV III.2)", None, pn4['bound_transits']))
    for _point, _rows in pn4['meridian_rows'].items():
        out.append(("The distribution from the Midheaven and the fourth", _point, _rows))
    for _ap in pn4['angle_planets']:
        out.append(("The planets, each with its measure under PN IV III.1, 12", _ap.get('planet'), _ap['rows']))
        out.append(("The planets, each with its measure under PN IV III.1, 12", _ap.get('planet'), _ap['terms']))
    _releaser = "The releaser and the house-master (Sahl, *On Nativities* 1.15-1.16, 1.20)"
    out += [
        # The verdict the page prints over the candidates (F6 check 24).
        (_releaser, None, rel['candidates'], rel['verdict']),
        (_releaser, None, rel['ranking']),
        # The headline the page prints over the short-life table (ruling
        # 145: the count, a range where testimony 4 is open, on the reports).
        (_releaser, None, pn4['short_life']['rows'], _short_life_headline(pn4['short_life'])[3]),
        # The stand-in on the arm of an open election that has no releaser
        # carries that arm's label, as the page prints it over the table.
        (_releaser, None, pn4['standin_moon'],
         *((f"The stand-in, {pn4['standin_arm']} (Sahl, On Nativities 1.32, 11-14)",) if pn4['standin_arm'] else ())),
        (_releaser, None, pn4['releaser_rows']),
        # PN IV's releaser table, where the page draws it: while the governor
        # counts testimony #3 and the direction is inside the table. Past
        # the table the page prints a sentence in its place, and so the
        # export carries none (the re-pass of 2026-10-04, L5-10).
        (_releaser, 'PN IV III.1, 12; IX.9, 4-5',
         pn4['pn4_releaser']['rows']
         if pn4['releaser_sr'] is not None and pn4['pn4_releaser']['status'] == 'available' else []),
        # On an election open on the Moon's easternness, each arm's table
        # where the page draws it, with the label the page prints over it
        # (K-28).
        *[(_releaser, 'PN IV III.1, 12; IX.9, 4-5',
           direction['rows'] if at_revolution is not None and direction['status'] == 'available' else [], label)
          for label, direction, at_revolution in _releaser_arm_directions()],
        # Supplement depth only, exactly as the Releaser page draws it: after
        # the releaser's section, under its own heading (L5R-02).
        ("Additions and subtractions to the house-master's years (Abu 'Ali)",
         JN_CH4_ADDITIONS_CITATION,
         pn4['hm_years_additions'] if pn4['hm_years'] and READING_DEPTH == READING_DEPTH_OPTIONS[1] else []),
        ("The house-master directed (Sahl, *On Nativities* 1.23, 1-11)", None, pn4['hm_direction']),
        ("The house-master directed (Sahl, *On Nativities* 1.23, 1-11)", None, pn4['hm_revolution']),
        ("The house-master directed (Sahl, *On Nativities* 1.23, 1-11)", None, pn4['hm_turning']),
        ("The father's Lot: its harmers and their direction (Sahl, *On Nativities* 4.20, 31-36)", None, father['harmers']),
        # The two directed tables the page prints under the same heading:
        # from the Lot's own degree, and from the second point (32).
        ("The father's Lot: its harmers and their direction (Sahl, *On Nativities* 4.20, 31-36)",
         "From the degree of the Lot of the father (32), to the harmers' bodies, squares and oppositions",
         father['from_lot'] or []),
        ("The father's Lot: its harmers and their direction (Sahl, *On Nativities* 4.20, 31-36)",
         f"From {_point_name(father['second'])} (32), to the same", father['from_second'] or []),
        ("The small days: the revolution's Ascendant distributed round the year", None, pn4['small_days_rows']),
        ("The mighty days: the terminal degree of the year directed through the revolution", None, pn4['mighty_days_rows']),
        ("The nine methods for the days and hours (PN IV IX.7, 1-72)", None, day_rows),
        ("The nine methods for the days and hours (PN IV IX.7, 1-72)", None, day_month),
        ("The nine methods for the days and hours (PN IV IX.7, 1-72)", None, day_ninth),
        ("The seven indicators of the month", None, pn4['monthly_rows']),
        ("The lords of the triplicity of the sect light, over the life", None, pn4['life_lords_rows']),
        (LIFE_LORDS_ASCENDANT_HEADING, None, pn4['life_lords_ascendant_rows']),
        ("The *fardar* (PN IV IV.1)", None, pn4['fardar_rows']),
        ("When a natal indication comes out (PN IV III.7, 32-42)", None, pn4['activation_rows']),
        ("The Ages of Man", None, pn4['age_rows']),
    ]
    return out


EXPORT_SCOPE_NOTE = (
    "The export carries this chart's readings: the tables the pages from Chart to Fardar and ages draw, "
    "with their cells as the pages print them. It leaves these on their pages, wherever this chart "
    "draws them. "
    "From the Findings page, every table: The fetus's stay (Sahl); The Moon on the third day (Sahl); "
    "Sahl: indications of fortune and livelihood; Places harming the eyesight; Mars in his own domicile, "
    "by sect (Abu Bakr); The Moon's phase, Valens's eleven; Mercury's phase against the sect; Mercury's "
    "company and sect; Affliction and fortification after Rhetorius; and Morin's rules for aspects into "
    "good and bad houses. "
    "From the Chart page: Special Degrees & Conditions, and Degrees of nobility and rank. "
    "Of the Chart page's Calculation table, the universal time, the two sidereal times, the RAMC and the "
    "obliquity are not carried; its local time, time standard and Julian day are carried with the moment "
    "and place the chart was cast at, and its MC and Ascendant in the Calculated Points table. "
    "From the Configurations page: Enclosure, Returning, Wildness, Favor & Recompense, and Book V degrees. "
    "From The releaser page, under The house-master directed: the redirection, which directs the lord of "
    "the Ascendant in the house-master's stead when that lord is another planet, and then the degree of the "
    "Ascendant. "
    "From the Days and months page: the two tables for a further point chosen there, its small days from "
    "the revolution and its mighty days from the natal point profected; the small days from the "
    "revolution's Ascendant and the mighty days from the terminal point of the year are carried. "
    "It also leaves two lookups keyed to this chart: Sahl's sign categories for this chart's points, on the "
    "Chart page, and al-Andarzaghar's triplicity lords of the twelve houses, on the Fardar and ages page. "
    "Nor does it carry the three 'Directing: which ascensions' tables on the Fardar and ages page, which "
    "read the same for every chart. "
    "What opens only on a click -- a point picked on the wheel, the whole of one selected row -- restates "
    "tables already on the pages and is not carried separately. The Reference tables page reads the same for every chart "
    "and is not carried; of the Sources and readings page, the readings in force are.")


def _dignity_rows():
    """The Planetary Dignity Evaluation grid as the Dignities page orders
    it: the resolved ranking first, the unresolved after it and unranked.
    Built here so the export carries the rows the page draws (M6). The
    column is "Ranking score", not "Net" -- one word must not head two
    different numbers for one planet (the hostile pass, L7).

    Ranking score and Acc hold the known subtotal in every row, one type
    per column on the page and in the export; where Mercury's sect leaves
    the +3 domain contribution unassigned, Unresolved counts it (the
    column is drawn only when a row has one), the row's Accidental
    Conditions name it, and the row is unranked on the engine's own
    score."""
    dignity_list, engine_scores = [], {}
    for p in essential.keys():
        ess = essential[p]
        acc = accidental[p]
        acc_score = acc['Accidental Score']
        if isinstance(acc_score, UnresolvedResult):
            net_score = UnresolvedResult(
                reason=(f"known subtotal {ess['Essential Score'] + acc['Known Accidental Score']}; "
                        'the +3 domain contribution is unassigned'),
                source=acc_score.source,
                alternatives=tuple((name, ess['Essential Score'] + value)
                                   for name, value in acc_score.alternatives),
                status=acc_score.status,
            )
        else:
            net_score = ess['Essential Score'] + acc_score
        # "Ranking score", not "Net": the Configurations page's Planetary
        # Condition has a Net that is Abu Ma'shar's own count (VII.6), and
        # one word must not head two different numbers for one planet
        # (the hostile pass of 2026-09-22, L7). This one is the app's
        # ranking convenience, as the paragraph above says.
        engine_scores[p] = {'Ranking score': net_score}
        dignity_list.append({
            "Planet": p,
            "Ranking score": ess['Essential Score'] + acc['Known Accidental Score'],
            "Ess": ess['Essential Score'],
            "Acc": acc['Known Accidental Score'],
            "Essential Dignities": ", ".join(ess['Essential Labels']) if ess['Essential Labels'] else "-",
            "Accidental Conditions": ", ".join(acc['Accidental Labels']) if acc['Accidental Labels'] else "-",
        })
    if any(isinstance(engine_scores[row['Planet']]['Ranking score'], UnresolvedResult) for row in dignity_list):
        for row in dignity_list:
            row['Unresolved'] = (1 if isinstance(engine_scores[row['Planet']]['Ranking score'], UnresolvedResult)
                                 else None)

    resolved_dignity = sorted(
        (row for row in dignity_list if not isinstance(engine_scores[row['Planet']]['Ranking score'], UnresolvedResult)),
        key=lambda row: row['Ranking score'], reverse=True)
    unresolved_dignity = [row for row in dignity_list
                          if isinstance(engine_scores[row['Planet']]['Ranking score'], UnresolvedResult)]
    return resolved_dignity + unresolved_dignity


def _topical_rows():
    """Topical Planets in Houses as the Dignities page's readings table and
    the export show it. Net is the Planetary Condition's known subtotal in
    every row and Lean is text, one type per column; where a row's
    condition has testimonies left open, Unresolved counts them (the column
    is drawn only when a row has one) and the row's details print the
    engine's own Net, possible totals and all."""
    open_rows = any(abu_mashar_condition[row['Planet']]['Unresolved Count'] for row in planets_in_houses_data)
    rows = []
    for row in planets_in_houses_data:
        cond = abu_mashar_condition[row['Planet']]
        shown = {**row, 'Net': cond['Known Net'], 'Lean': _display_result(row['Lean'])}
        if open_rows:
            shown['Unresolved'] = cond['Unresolved Count'] or None
        rows.append(shown)
    return rows


# The Topical Planets in Houses columns the Dignities page draws -- its grid
# and its readings table -- and Entries, the row's list printed whole, which
# the row's detail prints. Nothing else of the evaluator's row reaches the
# export: it also carries the joint passages' identifiers, by which the page
# counts a joint passage once and which it never prints (the hostile pass of
# 2026-10-03, HP-27).
TOPICAL_EXPORT_COLUMNS = ('Planet', 'Placed in (WS place)', 'Lean', 'Net', 'Unresolved', 'Standing',
                          'If in a suitable condition', 'If in a bad condition',
                          'Rhetorius and Firmicus, as the texts state it', 'Shared PN IV passages', 'Entries')


def _topical_export_rows():
    """Topical Planets in Houses as the export carries it: the page's
    columns, in the rows' own order."""
    return [{key: value for key, value in row.items() if key in TOPICAL_EXPORT_COLUMNS}
            for row in _topical_rows()]


# The Collection of Light columns the Configurations page draws: the
# collector and the pair it collects, and the Status a row left open by an
# undecided connection carries. The evaluator's other fields -- the profile,
# the tests it ran, the (applicant, collector) pairs -- are what the row's
# detail prints on a click, which the export does not carry separately
# (EXPORT_SCOPE_NOTE); copied whole, they reached the reports as nine
# columns no page draws, the pairs flattened to a list of names (the
# re-pass of 2026-10-04, HP-27).
COLLECTION_EXPORT_COLUMNS = ('Collector', 'Collects', 'Status')


def _collection_export_rows():
    """Collection of Light as the export carries it: the page's columns,
    in the rows' own order."""
    return [{key: value for key, value in row.items() if key in COLLECTION_EXPORT_COLUMNS}
            for row in collections]


def _moon_corruption_rows():
    """Sahl's Corruption of the Moon as the Configurations page and the
    export show it: one row, or none when no defect holds.

    Count is "how many of Sahl's ten testimonies", never the number of
    clauses that matched: 104 and 109 can each be met by several planets,
    and a list of ten must not add up to twelve. An undecided connection
    splits the list: the defects that hold under every permitted reading
    are the labels, and Count counts their testimonies; a defect that holds
    under only some is listed after them with its reason, and Unresolved
    counts the testimonies left open."""
    opened = list(_moon.get('Unresolved labels', ()))
    if opened:
        known = sum(t['matched'] is True for t in _moon['testimonies'].values())
        unresolved = sum(is_unresolved(t['matched']) for t in _moon['testimonies'].values())
        return [{'Planet': 'Moon',
                 'Defects': ', '.join(list(_moon['labels']) + [_display_result(v) for v in opened])
                 + (f" [{len(_moon['labels'])} settled clauses across "
                    f"{known} of the ten testimonies]"
                    if len(_moon['labels']) > known else ''),
                 'Count': known,
                 'Unresolved': unresolved or None}]
    return ([{'Planet': 'Moon',
              'Defects': ', '.join(_moon['labels'])
              + (f" [{_moon['matching_instances']} clauses across "
                 f"{_moon['unique_testimony_count']} of the ten testimonies]"
                 if _moon['matching_instances'] > _moon['unique_testimony_count'] else ''),
              'Count': _moon['unique_testimony_count']}]
            if _moon['labels'] else [])


def _condition_rows():
    """Abu Ma'shar's planetary conditions as the Configurations page
    orders them: the resolved heuristic ranking first, the unresolved
    after it and unranked. Built here so the export carries the rows the
    page draws, cell for cell (M6)."""
    condition_list = []
    for p, cond in abu_mashar_condition.items():
        # Then the conditions no text lets the app compute for this planet
        # (23, and 9's increase in light), each with its reason: shown here,
        # counted in none of the columns beside them.
        positive_labels = list(cond['Positive Labels']) + [
            _display_result(value) for value in cond.get('Unresolved Positive Labels', ())] + [
            _display_result(value) for value in cond.get('Not Computed Labels', ())]
        negative_labels = list(cond['Negative Labels']) + [
            _display_result(value) for value in cond.get('Unresolved Negative Labels', ())]
        condition_list.append({
            "Planet": p,
            # VII.6's own four sections, kept apart: the chapter
            # enumerates these separately and never totals them.
            # Every count holds the testimonies that are settled -- true
            # under every permitted reading -- and Unresolved says how many
            # are left open, as the Sahl grids' Count does: when Mercury's
            # sect is unassigned, or an undecided connection leaves a label
            # in some outcomes and not others, the engine's own counts are
            # UnresolvedResults, and a column mixing them with numbers is
            # one Arrow cannot type. The possible totals are in the row's
            # details, from the engine's own values.
            "Good Fortune": cond['Known Good Fortune'],
            "Strength": cond['Known Strength'],
            "Weakness": cond['Known Weakness'],
            "Misfortune": cond['Known Misfortune'],
            # str, not int-or-'': a column mixing the two is an
            # object column that Arrow rejects.
            "Moon Defects": str(cond['Known Moon Defects']) if cond['Known Moon Defects'] else '',
            # None, not 0, where nothing is open: blank on the page and in
            # the export.
            "Unresolved": cond['Unresolved Count'] or None,
            "Good Fortune / Strength": ", ".join(positive_labels) if positive_labels else "-",
            "Weakness / Misfortune": ", ".join(negative_labels) if negative_labels else "-",
            # Last, and labelled app arithmetic in the qualification
            # above: VII.6 never totals its conditions.
            "Net": cond['Known Net'],
            # Text in every row, the export included: an unresolved verdict
            # is its display sentence here, as the page has always shown it.
            "Verdict": _display_result(cond['Condition']),
        })
    # Ranked on the engine's own Net: a row whose Net is unresolved stays out
    # of the ranking although its cell shows the resolved subtotal.
    resolved_condition = sorted(
        (row for row in condition_list if not isinstance(abu_mashar_condition[row['Planet']]['Net'], UnresolvedResult)),
        key=lambda row: row['Net'], reverse=True)
    unresolved_condition = [row for row in condition_list
                            if isinstance(abu_mashar_condition[row['Planet']]['Net'], UnresolvedResult)]
    return resolved_condition + unresolved_condition


def _prevented_rows():
    """Sahl's intervention, nullification and cutting in the one table the
    Handy Tables' Lesson 17 gives them, with Abu Ma'shar's two further
    cuttings. Built here rather than in the page so the export carries the
    rows the page draws, cell for cell (M6)."""
    rows = []
    for r in blocking_data:
        # Sahl Ch.3, 35-48; VII.5, 90-94 -- cited in the caption.
        rows.append({'Kind': r['Type'], 'Planet': r['Blocked'],
                     'Prevented From': r['From Reaching'],
                     'By': r['Blocked By'], 'Because': r.get('Standing', '')})
    for r in cutting_data:
        rows.append({'Kind': 'Cutting ' + r['Type'], 'Planet': r['Planet'],
                     'Prevented From': r.get('Other Contact', ''),
                     'By': r.get('Yields To', ''),
                     # Types I and II are Abu Ma'shar's own (VII.5, 121-124);
                     # only Type III and the nullification are in Sahl
                     # (Ch.3, 31-34 and 44-48; VII.5, 120, 125). Both are
                     # cited in the table's caption.
                     'Because': r.get('Because', '')})
    return rows


def analysis_tables():
    """Every result table the export carries, as
    (page, heading, citation or None, rows[, label]), in the pages' own
    order, each under the heading the page draws it under (the hostile pass
    of 2026-10-03, L5-10). The list is fixed and named as such
    (EXPORT_SCOPE_NOTE, in the envelope, the Markdown header and on the
    Sources page): the hostile pass of 2026-09-22, M6."""
    tables = [
        ("Chart", "Planetary Positions",
         "Quadrant column: Alchabitius house, advancing or retreating in Sahl's sense "
         "(The Introduction Ch. 3, 4-5). Sees ASC: whole-sign aversion to the first place.",
         _positions_export_rows()),
        ("Chart", "Calculated Points", None, _calculated_point_rows()),
        ("Chart", "Quadrant divisions (Alchabitius)", None, _house_cusp_rows()),
        ("Dignities and places", "Lordship Mapping", None, _lordship_rows()),
        ("Dignities and places", "Sect", SECT_CAPTION, _sect_table_rows()),
        ("Dignities and places", "Topical Planets in Houses",
         "Rhetorius Ch. 57 and Firmicus, Mathesis III, as the texts state it, under each author's own division; PN IV Book II paraphrased in the two condition columns and shared passages; the Moon from VII.8 by her transit in her own table; every entry with its locator. "
         # The page's qualification over the table travels with it (ruling 146, B-08).
         + _page_line_text(NATAL_ADAPTATION),
         _topical_export_rows()),
        ("Dignities and places", "The Moon in the houses \u2014 PN IV VII.8, by her transit",
         "PN IV VII.8, 1-12 paraphrased, a natal analogy: one unsplit reading per house, the natal Moon's own house marked.",
         moon_in_houses_data),
        ("Dignities and places", "Planetary Dignity Evaluation (Hellenistic/Rhetorius reconstruction)",
         "The point weights are this app's own ranking convenience; no source totals these "
         "conditions. The geometry each test uses is sourced.", _dignity_rows()),
        ("Dignities and places", "Topical House Lords (Masha'allah)",
         "Sahl, On Nativities, the twelve lords-of-places passages, paraphrased; each cell carries its locator.",
         [{**raw, **shown} for raw, shown in zip(house_lords_data, _house_lord_rows())]),
        # The page's caption, which names the work its cells' short "Sahl N"
        # (The Introduction Ch. 3, sentence N) stand under (ruling 86).
        ("Configurations", "Aspects, aversions and connections",
         f"Sahl, The Introduction Ch. 2, 50-60 and Ch. 3, 6-21 — {CONNECTION_PROFILE} rule in force", aspects),
        ("Configurations", f"Reception \u2014 {CONNECTION_PROFILE} rule", None, reception_data),
        ("Configurations", "Strength of the Planets",
         "Sahl, The Introduction Ch. 3, 78-88. Testimony 80, direct in course, is withheld from a planet at its "
         f"station (a speed within {STATION_SPEED_TOLERANCE} degrees a day, this app's own figure: Sahl names none), "
         "which is neither direct nor retrograde; the Motion column of the Revolutions page reads the same three states.",
         strength_data),
        ("Configurations", "Weakness of the Planets",
         "Sahl, The Introduction Ch. 3, 91-100.", weakness_data),
        ("Lots", "Classical Lots", None, _classical_lot_rows()),
        ("Lots", TOPICAL_LOTS_HEADING, None, _page_columns(_topical_lot_rows(), LOT_WORKSHEET_COLUMNS)),
        ("Lots", "Provenance and standing per Lot",
         "Each Lot's status, standing, source and editor's note, as the Lots page reads them.",
         _page_columns(_lot_provenance_rows(), LOT_PROVENANCE_COLUMNS)),
        ("Lunation and victors", "Prenatal Lunation (Syzygy)",
         "Sahl, On Nativities 1.7, 3-7.", _syzygy_rows()),
        ("Lunation and victors", "Governor of the syzygy degree: the five lords under On Nativities 1.7, 3-7",
         "Sahl, On Nativities 1.7, 3-7; the eastern preference reads the allowance by which Sahl's Saturn and Jupiter are \"considered to be eastern\" (1.22, 1), Dykes's 15° for Mars (fn 174 on 1.22, 3), and 1.22, 7 for Venus and Mercury.", syzygy_governor['rows']),
    ]
    # The readings the pages draw that the fixed list above had left on
    # their pages (the hostile pass's M6, deferred past the first release
    # and taken here): each is this chart's own result, not a reference
    # lookup, and the export carries the rows its page draws.
    tables.extend([
        ("Configurations", "Transfer of Light",
         "Sahl, The Introduction Ch. 3, 24-27; Type II is Gr. Intr. VII.5, 84-85", transfers),
        ("Configurations", "Collection of Light",
         "Sahl, The Introduction Ch. 3, 28-30", _collection_export_rows()),
        ("Configurations", "Reflection of Light", "Gr. Intr. VII.5, 87-89", reflections),
        ("Configurations", "Natural connections", "Gr. Intr. VII.5, 53-77", natural_connections),
        ("Configurations", "Handing Over",
         "Sahl, The Introduction Ch. 3, 70-76", handing_over_data),
        ("Configurations", "Non-reception",
         "Sahl, The Introduction Ch. 3, 58-62", non_reception_data),
        ("Configurations", "Prevented connections",
         "Sahl, The Introduction Ch. 3, 31-48; Gr. Intr. VII.5, 90-94 and 120-125", _prevented_rows()),
        ("Configurations", "Banished", "Sahl, The Introduction Ch. 3, 64", banishment_data),
        ("Configurations", "Forward-Looking Conditions",
         f"Revoking, Resistance, Escape \u2014 next {FORWARD_SEARCH_DAYS} days", forward_looking_data),
        ("Configurations", "Corruption of the Moon",
         "Sahl, The Introduction Ch. 3, 103-112", _moon_corruption_rows()),
        ("Configurations", 'Right-sidedness, "the spear-bearing of the planets"',
         "Sahl, On Nativities 2.5, 1-3: a finding table, no score", right_sidedness),
        ("Configurations", 'The honor-guard, "and it is spear-bearing"',
         "Ptolemy in Sahl, On Nativities 10.2.1, 10-15: a finding table, no score", honor_guard),
        ("Configurations", "Planetary Condition",
         "Gr. Intr. VII.6: the four sections kept apart; Net and Verdict are this app's convenience, "
         "not Abu Ma'shar's, as the page says. " + VII6_46_INTERPRETATION_READER, _condition_rows()),
        ("Configurations", "Rays cast by ascensions (Ptolemy's method as reported by Abu Ma'shar, Gr. Intr. VII.7)",
         "Gr. Intr. VII.7, 1-22", rays_by_ascension_data),
        ("Configurations", "The sect light's first triplicity lord by ascensional band -- and the app's generalisation",
         "Sahl, On Nativities 2.13, 48-51 (fn 189: Carmen I.28, 1-6); Fifty Aphorisms #45, 90-92 with fn 57",
         ascensional_bands['rows'] or [{'Refused': ascensional_bands['refused']}]),
        ("Prediction", "Planetary years", None, planetary_years_data),
        ("Prediction", "Chronocrator Matrix",
         "The lord of the year by annual profection.", time_lords_data),
    ])
    # The two matched-preset grids stand under Victor of the Chart on the
    # page and the two unmatched pairings in its cross-check expander, and
    # the export files them the same way (L5-10).
    for _matched in (True, False):
        for _scheme, _res in victors_data.items():
            if ('matched preset' in _scheme) is _matched:
                tables.append(("Lunation and victors",
                               "Victor of the Chart" if _matched
                               else "Cross-check: the two unmatched weight/place pairings",
                               _scheme, _res['grid']))
    for heading, citation, rows, *label in _timing_bundle_tables():
        tables.append(("Prediction", heading, citation, rows, *label))
    # A table with no rows is a table the pages do not draw: _finding()
    # prints its "nothing found" sentence instead of a grid, and the timing
    # page skips a bundle entry that came back None or empty. The export
    # carries what the reader saw, so an empty one is not written down --
    # it would claim a grid stood where a sentence did.
    return [entry for entry in tables if entry[3]]


def _jsonable(value):
    """A value as JSON holds it, with conditional results kept explicit."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else str(value)
    if isinstance(value, UnresolvedResult):
        return {
            'result_type': 'UnresolvedResult',
            'status': value.status,
            'reason': value.reason,
            'source': value.source,
            'alternatives': [
                {'name': name, 'value': _jsonable(result)}
                for name, result in value.alternatives
            ],
            'display_label': value.display_label,
            'display_alternatives': value.display_alternatives,
            'display': _display_result(value),
        }
    if isinstance(value, PN4Together):
        # Two or more partners met together (PN IV III.1, 50), one value
        # each, all in force at once -- not alternatives.
        return {'result_type': 'PN4Together', 'values': [_jsonable(v) for v in value],
                'display': _display_result(value)}
    if isinstance(value, YearsOutcome):
        return {
            'result_type': 'YearsOutcome',
            'sentence': value.sentence,
            'grade': value.grade,
            'number': _jsonable(value.number),
            'unit': value.unit,
            'text': value.text,
            'display': _display_result(value),
        }
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, set):
        return sorted(str(v) for v in value)
    return str(value)


def analysis_export(*, name, entered, committed, readings, display, target,
                    tables, status, app, exported):
    """The analysis as one mapping, ready for json.dumps.

    Pure: every value it writes is passed in. `entered` is the record
    _chart_record() builds (what was entered), `committed` the resolved
    moment and place the chart was actually cast at, `readings` the
    doctrinal readings in force with their defaults, `display` the
    preferences that change what is DRAWN and not what is computed,
    `tables` the (page, heading, citation, rows[, label]) list above, and
    `status` what the app knows about its own answer. A table's cells are
    the values its page prints: where the page prints a number as text,
    rounded or truncated, the JSON carries that text; a cell that is a bare
    number is the number the calculation holds, and the precision paragraph
    names the columns where that runs past four places (the re-pass's
    ruling 11, L5-04, block B1 of the page-text read).

    An entry's `citation` is what the page cites for its table; its `label`,
    where there is one, is the line the page prints over that table -- the
    planet a tied primary's condition table is built for, the releaser's
    verdict -- kept in a field of its own rather than in the citation (the
    hostile pass of 2026-10-03, F3 check 18; F6 check 24), and typed where
    the page's line is an unresolved result."""
    results = {}
    for page, heading, citation, rows, *label in tables:
        entry = {"rows": _jsonable(list(rows))}
        entry["columns"] = sorted({str(k) for row in rows for k in row}) if rows else []
        if citation:
            entry["citation"] = citation
        if label and label[0] is not None:
            entry["label"] = _jsonable(label[0])
        results.setdefault(page, {}).setdefault(heading, []).append(entry)
    return {
        "schema": ANALYSIS_SCHEMA,
        "exported": exported,
        "app": dict(app),
        "chart": name,
        "input": _jsonable(committed),
        "entered": _jsonable(entered),
        "readings": _jsonable(readings),
        "display": _jsonable(display),
        "target": _jsonable(target),
        "results": results,
        "status": _jsonable(status),
        "scope": EXPORT_SCOPE_NOTE,
        "precision": _precision_paragraph(results),
    }


def _entered_for_export(record):
    """The record a save would write, as the export carries it (the owner's
    ruling 58 (b)): the block stays, without the app version under
    "saved_with" (ruling 27) and with its readings keyed by the labels the
    pages show rather than the session keys they are stored under (ruling
    28). The record itself, which Save writes and a load reads back, keeps
    both; only the export's copy changes."""
    out = dict(record)
    if isinstance(out.get("saved_with"), dict):
        out["saved_with"] = {k: v for k, v in out["saved_with"].items() if k != "app"}
    if isinstance(out.get("readings"), dict):
        label_of = {store_key: label for label, _wk, store_key, _d, _p in READINGS_REGISTRY}
        out["readings"] = {label_of.get(k, _export_words(k)): v for k, v in out["readings"].items()}
    return out


def _precision_paragraph(results):
    """What the export says of its own numbers, true of the tables it
    carries (the re-pass's ruling 11: the JSON keeps the page's printed
    values and says so; where a column carries the calculation's number,
    the paragraph says that). A column is named when one of its cells is a
    bare number with more than four decimal places -- the places a report
    prints -- as Planetary Positions' Absolute is (the hostile pass of
    2026-10-03, L5-04)."""
    full = []
    for headings in results.values():
        for heading, entries in headings.items():
            for entry in entries:
                for row in entry["rows"]:
                    if not isinstance(row, dict):
                        continue
                    for column, value in row.items():
                        if isinstance(value, float) and round(value, 4) != value:
                            name = f"{column} ({heading})"
                            if name not in full:
                                full.append(name)
    # Its exceptions said where they stand (H6's check, notes 4-5): the
    # columns named below, where a page prints the number as text and the
    # JSON carries it whole; a list, an empty cell and an unresolved answer,
    # which keep their JSON type; and the numbers inside a page's text
    # ("unrounded: 0.9553844877934661"), which are text, not bare numbers.
    out = ("The JSON's tables carry the values the pages print, as they print them: a number a page "
           "shows as text, rounded or truncated, is that same text here, at the page's places"
           + (", except in the columns named below" if full else "")
           + "; a list, an empty cell or an unresolved answer keeps its JSON type. A cell that is "
           "a bare number rather than text is the number as this app holds it")
    if full:
        out += ("; these columns carry it past four decimal places, unrounded: " + "; ".join(full))
    return out + (". The HTML and Markdown reports print the same cells, a bare number (not a number inside "
                  "a page's text) to at most four decimal places; where a report rounds such a number, the "
                  "JSON does not.")


# What a Markdown reader takes as a mark in running text: emphasis, code,
# links, headings, table cells, math, strikethrough, emoji names (":sun:")
# and the colon of a web address ("https:", which GitHub's Markdown links
# unescaped). The marks _as_typed sends to a code span on the pages, with
# the link's brackets. "@" is escaped with them, but that stops nothing:
# GitHub's Markdown makes an e-mail address a link escaped or not (only a
# code span would stop it), so a name holding one is printed as typed and
# may be drawn as a link.
_MARKDOWN_MARKS = re.compile(r"([\\`*_{}\[\]#|$~:@^])")


def _markdown_as_typed(value):
    """A chart's name or a place label as it was typed, for the Markdown
    export (K-31), by _as_typed's rule (G13): one line, as the title is
    (L6-08); a plain name as it is; any other with each mark escaped by a
    backslash, which any Markdown reader prints as the mark itself
    ("Smith $x$ :sun:" was set as math and an emoji), and & < > as
    entities, so no tag or entity is read either. Escaped rather than set
    as a code span: a heading and a table cell print it as plain words."""
    text = " ".join(str(value).split())
    # A name that could turn the text around it right to left is isolated
    # last, as the pages isolate it (_isolated): "abc", RIGHT-TO-LEFT
    # OVERRIDE, "def" was written raw into the title and the Place row. The
    # isolates are no Markdown mark and no entity.
    if _PLAIN_TEXT.fullmatch(text) and not _NOT_PLAIN.search(text):
        return _isolated(text)
    text = _MARKDOWN_MARKS.sub(r"\\\1", text)
    # "www." opens a link in GitHub's Markdown without any mark at all.
    text = re.sub(r"(?i)\b(www)\.", r"\1\\.", text)
    return _isolated(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _markdown_table(rows, typed=()):
    """A list of dicts as a Markdown table, in the rows' own key order. A
    row whose first cell is one of `typed` (the header's "Place") holds a
    name as it was typed: its "Value" prints through _markdown_as_typed."""
    if not rows:
        return "_No rows._\n"
    columns = list(dict.fromkeys(k for row in rows for k in row))

    def cell(value, as_typed=False):
        if as_typed:
            return _markdown_as_typed(_export_cell(value))
        return _export_cell(value).replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(cell(c) for c in columns) + " |",
           "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        as_typed = bool(typed) and next(iter(row.values()), None) in typed
        out.append("| " + " | ".join(cell(row.get(c, ""), as_typed and c == "Value") for c in columns) + " |")
    return "\n".join(out) + "\n"


def analysis_markdown(analysis):
    """The same analysis as a report a reader can read: the same header
    block, the same sections and the same tables. Nothing is added that the
    JSON does not carry, and no source text beyond the citations the pages
    already print. It takes the in-memory export analysis_export builds,
    not one decoded back from its JSON, whose plain floats lose the
    sign-end boundary formatting of the Positions longitudes."""
    # L6-08: the name is one line of text, not markup -- a newline would end
    # the heading and its markup would be written verbatim. K-31: every
    # mark, "$" and ":" too, and the Place rows below the same way.
    out = [f"# Analysis: {_markdown_as_typed(analysis['chart'])}", ""]
    # No version after "this app": ruling 27 (the provenance block dropped).
    out.append(f"Exported {analysis['exported']} by this app.")
    out.append("")
    out.append(analysis.get("scope", EXPORT_SCOPE_NOTE))
    out.append("")
    # The header tables, their rows labelled in words, from the one list the
    # HTML prints too (export_header_tables).
    for title, rows in export_header_tables(analysis):
        out.append(f"## {title}")
        out.append("")
        out.append(_markdown_table(rows, typed=("Place",)))
    out.append("## Results")
    out.append("")
    for page, headings in analysis["results"].items():
        out.append(f"### {page}")
        out.append("")
        for heading, entries in headings.items():
            out.append(f"#### {heading}")
            out.append("")
            for entry in entries:
                # The line the page prints over this table, bold as the page
                # prints it (a tied planet's name, the releaser's verdict),
                # then what it cites.
                if entry.get("label") is not None:
                    out.append(f"**{_export_cell(entry['label'])}**")
                    out.append("")
                if entry.get("citation"):
                    out.append(f"*{entry['citation']}*")
                    out.append("")
                out.append(_markdown_table(entry["rows"]))
    out.append("## Precision")
    out.append("")
    out.append(analysis["precision"])
    out.append("")
    return "\n".join(out)


# --- The two buttons, in the place reserved under Save -------------------
# Built HERE, at the foot of the script, because the export is made of the
# pages' own row lists and those need the chart. st.download_button must
# hold the bytes at render time, so there is no deferring the build behind
# the click itself; what the cost is, and why it is paid on every rerun, is
# in process/tae_docs/SAVED_READINGS_EXPORT_2026-09-16.md.
with export_box:
    if not chart_ok:
        # Disabled rather than absent: the action exists, and the reason it
        # cannot run is the same one the box above already gives.
        st.download_button("Export analysis (HTML)", data=b"", file_name="analysis.html",
                           mime="text/html", disabled=True, key="_export_html")
        st.download_button("Export analysis (JSON)", data=b"", file_name="analysis.json",
                           mime="application/json", disabled=True, key="_export_json")
        st.download_button("Export analysis (Markdown)", data=b"", file_name="analysis.md",
                           mime="text/markdown", disabled=True, key="_export_md")
        st.caption("There is no chart to export; the input above says why.")
        # A refused run has no chart, so it has no export either: the
        # previous chart's must not stay in the session as if it were this
        # one's (F1 check; F4b re-check).
        for _key in ("_analysis_export", "_analysis_markdown", "_analysis_html"):
            st.session_state.pop(_key, None)
    else:
        # The strip's name: a record edited since it was saved, or opened
        # under other readings, is "(modified)" here as there, and the
        # status says which (the hostile pass of 2026-10-03, L5-03).
        _export_name = f"{chart_name} (modified)" if chart_modified else chart_name
        _analysis = analysis_export(
            name=_export_name,
            entered=_entered_for_export(_chart_record() if input_record is None else input_record),
            committed={
                "date": input_date.isoformat(),
                "time": input_time.strftime("%H:%M:%S"),
                "time_standard": time_standard,
                "utc_offset_hours": utc_offset_hours,
                "timezone": tz_name,
                # Ruling 35's label, where a named mean time was cast (or a
                # pre-1970 window's whose start is this app's choice).
                **({"civil_clock": zone_label} if zone_label else {}),
                "place": location_query,
                "latitude": lat,
                "longitude": lon,
                "julian_day_ut": jd_ut,
                "calendar": _cal_note,
                "ut_calendar": _ut_cal_note(jd_ut),
            },
            # Each reading by the label its page shows; the session key it is
            # stored under is internal and stays out (ruling 28).
            readings=[{"label": _label,
                       "value": _reading(_wk, _sk, _default), "default": _default,
                       "set_on": _page}
                      for _label, _wk, _sk, _default, _page in READINGS_REGISTRY],
            display={
                # What is DRAWN, not what is computed: the bounds ring, the
                # dark wheels, the wheel's shape. Kept apart from the
                # readings above for exactly that reason.
                "chart_bounds": CHART_BOUNDS,
                "wheel_dark": WHEEL_DARK,
                "wheel_layout": _reading("wheel_layout", "_wheel_layout", WHEEL_LAYOUT_OPTIONS[0]),
            },
            # The hour the target day is read at, and the one line each
            # Prediction page carries saying which count of the year its
            # tables key on: the export of a page carries the page's line.
            # On a target date whose noon UT falls before the birth both say
            # the birth's own moment, as the pages' header does.
            target={"mode": target_mode, "date": target_date.isoformat(), "age": target_age,
                    "hour": pn4_target_read_at(pn4['target_at_birth'], export=True),
                    **{f"counts on the {page} page": pn4_count_line(page, pn4['target_at_birth'])
                       for page in PN4_PAGE_COUNTS}},
            tables=analysis_tables(),
            status={
                "chart_ok": chart_ok,
                "chart_error": chart_error,
                # The record the picker names and the chart in hand: parted
                # (the strip's "(modified)"), and on which side, as the two
                # captions under the picker say.
                "modified": chart_modified,
                "edited_since_saved": _inputs_edited,
                "saved_with_other_readings": _readings_changed,
                # The planetary hour where the Sun neither rises nor sets:
                # an equal hour stands in for a temporal one, and the strip
                # says so beside the hour lord.
                "equal_hour_approximation": bool(chronocrats.get('Approximate')),
                # The Lord of the Day as the strip names him, with his
                # qualification where he is the civil weekday's (no sunrise
                # within a day behind, ruling Q7), his weekday repeats or
                # the civil date's weekday is passed over.
                "day_lord": day_lord_qualified(chronocrats),
                # At the pole the Ascendant is not a rising degree, and every
                # place, Lot and lord counted from it rests on that point:
                # the pages built on it say so on their strip, and so does
                # each report of them.
                **({"pole": POLE_ASCENDANT_EXPORT_SENTENCE} if AT_POLE else {}),
                "forward_search_days": FORWARD_SEARCH_DAYS,
                # The draft date does not parse: the tables are the last
                # valid chart's and have not moved (F01d).
                "stale": not date_is_valid,
                "target_out_of_reach": bool(target_out_of_reach),
            },
            app=app_identity(),
            exported=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        _stem = re.sub(r"[^\w.-]+", "-", _export_name).strip("-") or "unsaved"
        # K-31: a file name of more than 255 bytes is refused by the usual
        # file systems, so the name's part is cut at 200 bytes, on a whole
        # character (the rest of the file name is 25 bytes).
        _stem = _stem.encode("utf-8")[:200].decode("utf-8", "ignore").strip("-") or "unsaved"
        _stamp = f"analysis_{_stem}_{input_date:%Y-%m-%d}"
        # The harness cannot read a download button's bytes, so the object
        # the two buttons carry is left here to be asserted on directly.
        _report = analysis_markdown(_analysis)
        _page = analysis_html(_analysis)
        st.session_state["_analysis_export"] = _analysis
        st.session_state["_analysis_markdown"] = _report
        st.session_state["_analysis_html"] = _page
        # HTML first: it is the one format a reader can open by double-clicking
        # on either platform, and the only one that needs no second file.
        st.download_button("Export analysis (HTML)", data=_page.encode("utf-8"),
                           file_name=f"{_stamp}.html", mime="text/html", key="_export_html",
                           help="One file: opens in your browser, prints to PDF, keeps nothing beside it.")
        st.download_button("Export analysis (JSON)",
                           data=json.dumps(_analysis, indent=1, ensure_ascii=False).encode("utf-8"),
                           file_name=f"{_stamp}.json", mime="application/json", key="_export_json")
        st.download_button("Export analysis (Markdown)", data=_report.encode("utf-8"),
                           file_name=f"{_stamp}.md", mime="text/markdown", key="_export_md")


def page_chart():
    if not chart_ok:
        _recovery_panel("Chart")
        return
    st.header("Chart")
    _chart_strip()
    _readings_note()
    _gap = []
    # The twelve signs' hover text, and the panel a click opens. Both
    # are display only: every row either restates a position the page
    # already prints or is lifted whole out of a table another page
    # draws, and each table's caption says which page that is. The
    # hover text is worked out once per run, in Python, and handed to
    # the component inside its envelope, so that moving the pointer
    # across the zodiac asks the server nothing.
    def _sign_hover(index):
        summary = sign_summary(index, sect)
        bounds = ", ".join(f"{row['Lord']} to {row['Bound'].split('-')[1]}" for row in summary['bounds'])
        return (f"{summary['sign']} · {summary['element']}\n"
                f"Bounds: {bounds}\n"
                f"Triplicity ({sect}): {summary['lords'][2]['Lord']}, "
                f"with {summary['lords'][3]['Lord']} partnering. {summary['Triplicity table']}"
                + ("\n" + summary['Virgo source note'] if summary['Virgo source note'] else ""))

    # Two across rather than one down: a caption and a small table
    # stacked six deep ran the panel far past the wheel. Each section
    # is its caption and then its table, so the pair reads as a
    # labelled block, and the sections fill left, right, left, right
    # in their own order. A section with no rows draws nothing and
    # takes no slot, so the two columns stay level.
    def _panel_columns(sections):
        filled = [(caption, rows) for caption, rows in sections if rows]
        if not filled:
            return
        columns = st.columns(2)
        for index, (caption, rows) in enumerate(filled):
            with columns[index % 2]:
                st.caption(caption)
                st.dataframe(pd.DataFrame(rows), hide_index=True, width='content')

    def _pick_panel(picked):
        """The panel under the controls row: nothing until a planet,
        an angle or a sign is clicked in the wheel."""
        kind, _sep, value = str(picked or "").partition(":")
        if kind == "sign" and value.isdigit():
            summary = sign_summary(int(value), sect)
            st.subheader(summary['sign'])
            _panel_columns([
                ("The lords of the sign. The Reference tables page carries every sign. " + summary['Triplicity table'] + ". " + summary['Virgo source note'], summary['lords']),
                ("The Egyptian bounds, which the Reference tables page carries in full.", summary['bounds']),
                ("The three faces, which the Reference tables page carries beside the other dignities.", summary['faces']),
            ])
        elif kind == "planet":
            summary = point_summary(value, chart_data, essential, accidental, aspects,
                                    reception_data, classical_lots, topical_lots)
            if summary is None:
                return
            st.subheader(summary['point'])
            _panel_columns([
                ("Where it stands. The Calculated Points and Quadrant divisions tables below carry every point.",
                 summary['position']),
                ("Its dignity at its own degree. The Dignities and places page carries the full lordship table.",
                 summary['essential']),
                ("Its accidental conditions. The Dignities and places page carries them for every planet."
                 + (" " + summary['accidental_note'] if summary['accidental_note'] else ""),
                 summary['accidental']),
                ("The connections it stands in. The Configurations page carries the whole aspects table.",
                 summary['connections']),
                (f"Reception under the {CONNECTION_PROFILE} rule. The Configurations page carries the full table.",
                 summary['receptions']),
                ("The Lots it is lord of. The Lots page carries the classical and the topical Lots in full.",
                 summary['lots']),
            ])

    # Looking at the chart is the primary act, so the wheel takes the
    # centre of the page: the square wheel centred at 560 px, its
    # controls in one row beneath it, the introduction beneath those.
    # The picture is a component (item 11) rather than an st.image,
    # which cost it Streamlit's own fullscreen wrapper -- the expand
    # arrows the tables carry -- so the component carries an expand
    # control of its own instead. The wide variant runs the full page width and scrolls,
    # with its positions panel drawn into the picture, and is there for
    # the full-window view, which a square can only fill to the
    # window's height. Both layouts then read alike: the same controls
    # row, the same three sentences.
    #
    # The layout is still read from the control's state BEFORE the
    # control is drawn, because the control now sits under the wheel
    # and the wheel must know which of the two to draw. The widget key
    # holds the new value from the start of the rerun that a click
    # causes; the store key keeps it across pages.
    #
    # The wheel and its four controls are one @st.fragment (item 9,
    # 2026-09-15). A click on the radio, either checkbox or the
    # download button used to rerun the whole script and redraw every
    # table on the page; a fragment reruns only its own body on its
    # own widgets' changes. The engine is cheap -- the whole run is
    # about a fifth of a second -- so this is about the redraw and
    # the flicker, not the compute. Two consequences the code has to
    # honour: the SVG is generated INSIDE the fragment, from the
    # bounds and dark-wheel values the fragment's own widgets hold
    # (the top-level CHART_BOUNDS and WHEEL_THEME are a full run's
    # values and do not move on a fragment rerun), and a fragment may
    # not write to a container outside itself, so everything it draws
    # -- picture and controls row -- is inside its body and nothing
    # else is. The three captions, the circumpolar warning and the
    # rest of the page stay outside, where they are not redrawn.
    @_pinned_fragment
    def _wheel_block():
        st.session_state.setdefault("_chart_bounds", True)
        # The four controls in one row across the page, aligned on
        # their feet so the radio's row of options, the two checkboxes
        # and the button sit on one line rather than at three heights.
        #
        # A flex row, not st.columns: Streamlit stacks columns
        # vertically below about 640 px of page width, and a reader
        # zoomed in or in a narrow window is below it, so the four
        # controls ran down the left-hand edge in a column. A
        # horizontal container keeps them in a row at any width and
        # wraps (wrap defaults to True) only when they genuinely
        # cannot fit. Left-aligned and the page's full width, as the
        # row of controls was asked for.
        def _layout_control():
            with st.container(horizontal=True, vertical_alignment="bottom", gap="medium"):
                # The label is collapsed and the tooltip dropped here, and
                # here only: a radio carries its label above its options
                # and a checkbox carries its beside the box, so labelled
                # this radio stood a tier above the three controls next to
                # it and the row read as two. The two words "Square" and
                # "Wide" beneath a wheel say what the control does. The
                # label string stays as the widget's accessible name.
                layout = _reading_radio(
                    "Wheel layout", WHEEL_LAYOUT_OPTIONS, "wheel_layout", "_wheel_layout",
                    label_visibility="collapsed")
                # The two checkboxes still write their store keys and the
                # preferences file through _persist, which works inside a
                # fragment exactly as it does at the top level; that is
                # what lets the next full run read CHART_BOUNDS and
                # WHEEL_DARK and find what the fragment left.
                _reading_checkbox("Bounds ring", "chart_bounds", "_chart_bounds",
                                  help="The Egyptian bounds, with their lords, as a ring inside the degree scale -- "
                                       "as every natal wheel in Persian Nativities IV carries them (Figures 1, 22, "
                                       "25, 26).")
                _reading_checkbox("Dark wheel", "wheel_dark", "_wheel_dark", help=WHEEL_DARK_HELP)
                st.download_button("Download the wheel (SVG)", svg_wide if layout == WHEEL_LAYOUT_OPTIONS[1] else svg_code,
                                   key="dl_chart_wheel", mime="image/svg+xml",
                                   file_name=f"{_download_stem}_natal.svg")
            return layout
        wheel_layout = st.session_state.get(
            "wheel_layout", st.session_state.get("_wheel_layout", WHEEL_LAYOUT_OPTIONS[0]))
        # Read before draw, for the same reason the layout is: the two
        # checkboxes sit UNDER the picture, and the picture has to be
        # generated before them. A widget key holds the new value from
        # the start of the rerun a click causes, so the wheel the click
        # asks for is the wheel drawn on that same (fragment) rerun.
        # The fallback is this run's top-level reading -- CHART_BOUNDS
        # and WHEEL_DARK are _reading(widget key, store key, default)
        # and are what every other reader of these two preferences
        # sees -- which is what the first render of the page uses,
        # before the checkbox has a key, and after navigating back to
        # the page, where Streamlit has dropped the widget's state.
        # On a fragment rerun they are the last full run's values, so
        # the widget key in front of them is what moves.
        _bounds = bool(st.session_state.get("chart_bounds", CHART_BOUNDS))
        _dark = bool(st.session_state.get("wheel_dark", WHEEL_DARK))
        # The same rule the top level uses for WHEEL_THEME: the
        # viewer's own theme when the preference is on, None when it
        # is off, so off the picture is drawn exactly as it always was.
        _theme = VIEWER_THEME if _dark else None
        svg_code = generate_hybrid_svg(chart_data, chart_name, location_query, lat, lon, local_dt, tz_name,
                                       chronocrats=chronocrats, bounds=_bounds, theme=_theme)
        svg_wide = generate_hybrid_svg(chart_data, chart_name, location_query, lat, lon, local_dt, tz_name,
                                       wide=True, chronocrats=chronocrats, bounds=_bounds, theme=_theme)
        # The picture is mounted as the natal_wheel component rather
        # than shown with st.image, so that a click on a planet, an
        # angle or a sign can reach Python (item 11, 2026-09-15).
        # The mount stands INSIDE this fragment, so the rerun a
        # click causes is a fragment rerun: the tables on the rest
        # of the page are not redrawn to show a panel under a wheel.
        #
        # The envelope carries three things and no more: the SVG the
        # renderer just produced, the width this layout asks for,
        # and the twelve signs' hover text, worked out here from the
        # engine's own tables so that a hover is answered in the
        # browser and never round-trips to Python.
        _picked_wide = wheel_layout == WHEEL_LAYOUT_OPTIONS[1]
        _envelope = {
            "svg": svg_wide if _picked_wide else svg_code,
            "width": "stretch" if _picked_wide else 560,
            "signs": [_sign_hover(i) for i in range(12)],
        }
        if _picked_wide:
            picked = NATAL_WHEEL(data=_envelope, key="natal_wheel",
                                 on_picked_change=lambda: None).picked
        else:
            # st.image draws at the left edge of whatever holds it, so the
            # wheel needs a container that centres its contents. A three
            # column split does NOT do it: a column is a fraction of the
            # page, and the middle of [1, 2, 1] is 454 px at 1400 and
            # 394 px at 1280 -- narrower than the 400 px this replaced,
            # because st.image shrinks a picture to the width it is given.
            # A horizontal container is a flex row instead: its children
            # keep their own width and the row centres them, so the wheel
            # is 560 px at every window width.
            with st.container(horizontal=True, horizontal_alignment="center"):
                picked = NATAL_WHEEL(data=_envelope, key="natal_wheel",
                                     on_picked_change=lambda: None).picked
        _layout_control()
        # Nothing at all until something is clicked, which is why the
        # page's inventory of tables is what it always was.
        _pick_panel(picked)
    _wheel_block()
    # The notice says what is shown and what is not affected; the reason --
    # which bounding sunrise or sunset is missing -- is the engine's own
    # sentence, in notes. On the first night after a polar day the night's
    # own sunset and sunrise both exist ('Hour Bracketed') and only the
    # sunrise that opened its day is out of reach, so the note says the
    # night has hours whose lords cannot be counted, not that it has no
    # hours (re-pass of 2026-10-04, L1-05); Gr. Intr. VI.33, 6, "until the
    # lords of the twenty-four hours completed the amount of a single day
    # and a single night", and 17, the hours of the day begin "from the
    # inception of the Sun's rising".
    # The notice's last sentence says whose the day lord is, true on both
    # sides of the one day the engine searches back for a sunrise: exact
    # where a sunrise lies within a day behind the moment (its weekday's
    # lord), the civil weekday's where none does -- the owner's ruling of
    # 2026-10-05 (Q7), with Gr. Intr. VI.33, 4, "the Sun is the planet by
    # whose rising the day comes to be".
    # Where the sunrise that opened the day is the second on its civil date,
    # the day keeps that sunrise's weekday and his lord rules twice running
    # (the owner's ruling 25 of 2026-10-05, FQ-6), and the page says so
    # here: in the notice's last sentence where the hour is approximate --
    # whose day then ends a day after its sunrise, no sunrise following
    # within it (ruling 5) -- and in a caption of its own where the hours
    # are temporal. The notice names the rule this app's reading there, as
    # the caption and the notes do (ruling 25: "the page says so there").
    # Where the hours are temporal the repeated day's first hour is his
    # again: Gr. Intr. VI.33, 7, "Then they looked at the planet which the
    # counting had reached at the twenty-fifth count, and made it be the
    # lord of the day which followed, and made it be the lord of the first
    # hour of that day, as well" -- so the count of Gr. Intr. VI.33, 6 does
    # not run on into the second day (40N 0E at UTC-7, 2000-02-09: Saturn's
    # last night hour, then Mercury's first hour again). Where the hour is the
    # equal-hour approximation the hours run on unbroken from civil
    # midnight, so the notes there say nothing of it.
    # The mirror case: a civil date on which no sunrise falls, so no
    # planetary day is its weekday's and that weekday's lord is passed over
    # (calculate_chronocrats' 'Day Lord Skipped'); said in a caption of its
    # own, as the repeated day is.
    _repeat_reason = (
        "Two sunrises fell on one civil date, and each planetary day keeps the civil weekday of the sunrise "
        "that opened it, since \"the Sun is the planet by whose rising the day comes to be\" (Gr. Intr. VI.33, 4), "
        "so the day the second opened has the lord the day before had. The texts do not contemplate two "
        "sunrises on one date: this is this app's reading.")
    if chronocrats.get('Approximate'):
        _day_lord_sentence = (
            "The Lord of the Day is the civil weekday's lord, this app's stand-in, since no sunrise lies within a "
            "day behind this moment, and \"the Sun is the planet by whose rising the day comes to be\" "
            "(Gr. Intr. VI.33, 4)."
            if chronocrats.get('Day Lord Civil') else
            "The Lord of the Day is exact and repeats: two sunrises fell on one civil date, and each planetary day "
            "keeps the weekday of the sunrise that opened it (this app's reading); it ends a day after its sunrise."
            if chronocrats.get('Day Lord Repeated') else "The Lord of the Day is still exact.")
        # Ruling 87 (PW-18): the civil weekday's lord is called this app's
        # stand-in, and the notice is cut to stay under 400 characters
        # ("the same Chaldean cycle" to "the Chaldean cycle").
        st.caption(
            "⚠️ **The Lord of the Hour here is not a temporal hour.** What is shown is an "
            "explicitly modern approximation: the civil day divided into 24 equal hours, "
            "continuing the Chaldean cycle. " + _day_lord_sentence
        )
        _reason = chronocrats['Hour Reason'][:1].upper() + chronocrats['Hour Reason'][1:] + "."
        if chronocrats.get('Hour Bracketed'):
            _why_note = (
                "This night has hours, but their lords cannot be counted.",
                _reason + " Gr. Intr. VI.33, 4-6 and 17: the lords of the hours are counted on from the first "
                "hour of the day, \"until the lords of the twenty-four hours completed the amount of a single day "
                "and a single night\", and the hours of the day begin \"from the inception of the Sun's rising\". "
                "The night's sunset and sunrise give its hours a length, but with no sunrise behind them their "
                "lords have nothing to be counted from, and no source in hand contemplates the case.")
        else:
            _why_note = (
                "No temporal hour exists at this moment at this location.",
                _reason + " The temporal hour "
                "is *defined* by the interval from a sunrise to the sunset that follows it, or from a sunset "
                "to the sunrise that follows -- so it has no value at all, and no source in hand contemplates "
                "the case.")
        _notes_expander("Why the hour lord is approximate here",
                        [_why_note] + ([("Why the day lord's weekday repeats.", _repeat_reason + " No sunrise "
                                         "follows within a day of the one that opened this day, so it ends a day "
                                         "after that sunrise, and the civil weekday's lord follows.")]
                                       if chronocrats.get('Day Lord Repeated') else []))
    elif chronocrats.get('Day Lord Repeated'):
        st.caption("**The Lord of the Day's weekday repeats here:** two sunrises fell on one civil date, and each "
                   "planetary day keeps the civil weekday of the sunrise that opened it, since \"the Sun is the "
                   "planet by whose rising the day comes to be\" (Gr. Intr. VI.33, 4), and its first hour is his "
                   "again, not the twenty-fifth count's (Gr. Intr. VI.33, 7): this app's reading of a case the "
                   "texts do not contemplate.")
    elif chronocrats.get('Day Lord Skipped'):
        _skipped = chronocrats['Day Lord Skipped']
        st.caption(f"**No planetary day is {_skipped}'s here:** no sunrise fell on this civil date, and each "
                   "planetary day keeps the civil weekday of the sunrise that opened it, since \"the Sun is the "
                   "planet by whose rising the day comes to be\" (Gr. Intr. VI.33, 4), so the day the last sunrise "
                   f"opened runs on to the next one and {DAY_LORD_BY_WEEKDAY[WEEKDAY_NAMES.index(_skipped)]}'s day "
                   "is passed over: this app's reading of a case the texts do not contemplate.")
    # Four paragraphs at reading width, each its own markdown. Both layouts
    # print the same four, so the page reads alike whichever wheel is drawn.
    # The opening is the README's own, word for word: one description of
    # what this is, wherever a reader meets it.
    _intro = ("A *z\u012bj* is a set of astronomical tables with the rules for using them. This one is a "
              "study companion for traditional natal astrology: cast a chart, then check, table by "
              "table, what the texts say about it.",
              "The texts are *The Astrology of Sahl b. Bishr*, vol. I, and Abu Ma'shar's *On the "
              "Revolutions of the Years of Nativities* (*Persian Nativities* IV), in Benjamin Dykes's "
              "translations, with his *Great Introduction* as the supplement. Every rule applied on "
              "a page names its sentence.",
              "Enter or load a nativity in the sidebar. The Nativity sets out what the chart contains, "
              "Prediction what the year holds; the reference tables and the sources close the page "
              "list. The judgment is the astrologer's.",
              "Click a planet or a sign on the wheel for what the tables say of it; hover a sign for its bounds and triplicity lords.")
    # They are read once and then in the way, so they stand open for
    # the first two launches and fold themselves after that, one
    # click from the reader either way. The count is the launches
    # including this one; under the harness, where preferences are
    # neither read nor written, it stays 0 and the three stand open.
    if LAUNCH_COUNT <= 2:
        with _prose():
            for _sentence in _intro:
                st.markdown(_sentence)
    else:
        with st.expander("About this app", expanded=False):
            with _prose():
                for _sentence in _intro:
                    st.markdown(_sentence)
    # The Lesson 5 worksheet's intermediate lines, so a hand
    # calculation can be checked line by line rather than only at
    # the Ascendant. GST is the Greenwich sidereal time at the UT of
    # birth; LST adds the longitude in hours; RAMC is the right
    # ascension of the meridian from the same swe.houses call that
    # produced the cusps.
    st.subheader('Calculation', help="The intermediate quantities of the chart calculation -- universal time, the Julian day, sidereal time, the RAMC, the obliquity -- so a hand calculation can be checked against this app line by line.")
    gst_hours = swe.sidtime(chart_data['julian_day'])
    lst_hours = (gst_hours + lon / 15.0) % 24.0
    calc_rows = [
        {"Quantity": "Local time", "Value": f"{local_dt:%Y-%m-%d %H:%M:%S}"},
        {"Quantity": "Time standard", "Value": tz_name},
        # Ruling 35: a named mean time cast as the area's clock says so here
        # too, as the sidebar's box does (and so does a pre-1970 window
        # whose start is this app's choice, naming its clock).
        *([{"Quantity": "Civil clock then", "Value": zone_label}] if zone_label else []),
        # The calendar named where the UT's differs from the birth date's
        # (a moment either side of the reform's JD), so the digits are
        # never read in the wrong calendar.
        {"Quantity": "Universal time", "Value": f"{dt_utc:%Y-%m-%d %H:%M:%S} UT"
         + (f" ({_ut_cal_note(jd_ut).split(' (')[0]}; the birth date is {_cal_note.split(' (')[0]})"
            if _ut_cal_note(jd_ut)[:4] != _cal_note[:4] else "")},
        {"Quantity": "Julian Day", "Value": f"{chart_data['julian_day']:.4f}"},
        {"Quantity": "Greenwich sidereal time at birth", "Value": _hms(gst_hours)},
        {"Quantity": "Local sidereal time", "Value": _hms(lst_hours)},
        {"Quantity": "RAMC", "Value": _dms(chart_data['armc'])},
        {"Quantity": "Obliquity of the ecliptic", "Value": _dms(chart_data['obliquity'])},
        {"Quantity": "MC", "Value": get_degree_string(chart_data['mc'])},
        {"Quantity": "Ascendant", "Value": get_degree_string(chart_data['ascendant'])},
    ]
    st.dataframe(pd.DataFrame(calc_rows), hide_index=True, width='content',
                 column_config=_wide_text_columns(pd.DataFrame(calc_rows)))
    # Day and night are divided ONCE, here, for the chart's sect and the
    # planetary hours alike (hostile pass 2026-10-03, L1-04); the sentences
    # are Gr. Intr. VI.33, 4 and 17, quoted in the notes.
    st.caption("Day and night -- the chart's sect and the planetary hours alike -- are divided at the Sun's "
               "visible rising and setting, refraction included (Gr. Intr. VI.33, 4 and 17). Where he neither "
               "rises nor sets within a day, whether any of his disk is above that same horizon decides. A body's "
               "\"above the horizon\" in the tables is its own centre against the true horizon.")
    _notes_expander("How day and night are divided", [
        ("The Sun's rising makes the day.",
         "Gr. Intr. VI.33, 4: \"the Sun is the planet by whose rising the day comes to be, and by his "
         "setting the night comes to be\"."),
        ("The hours begin at his first appearance.",
         "Gr. Intr. VI.33, 17: \"the beginning of the hours of the day are from the inception of the Sun's "
         "rising from the eastern horizon, while the beginning of the hours of the night are from the "
         "disappearance of the Sun's body from the horizon of the west\" -- so long as any part of the disk "
         "shows, it is day, as Dykes's note there reads it. The chart's sect and the planetary hours turn "
         "at the same instant, the apparent rising and setting of the upper limb."),
        # The rule in force since the one horizon's second and third builds:
        # the disk, not the centre against the true horizon (re-pass of
        # 2026-10-04, L1-N3), as the caption above already says.
        ("Where the Sun is circumpolar.",
         "With no rising or setting within a day, the sect follows whether any of the Sun's disk is above the "
         "horizon his visible rising and setting are reckoned on -- his centre above the altitude at which his "
         "upper limb would stand on it, refraction included -- and the planetary hours fall to the flagged "
         "equal-hour approximation."),
    ])
    pos_col, moon_col = st.columns([2, 1], vertical_alignment="center")
    pos_col.subheader('Planetary Positions', help="The seven classical planets' ecliptic (tropical) longitude at the moment of birth, in sign and degree.")
    with moon_col:
        _reading_checkbox("Moon under the rays to 15°", "moon_rays_15", "_moon_rays_15",
                          help="Sahl, On Nativities 1.19, 6: 15°; Gr. Intr. VII.2, 61 and 72-73: 12°. Affects solar phase, "
                               "ray-dependent configurations and prosperity's triplicity lords (On Nativities 2.11, 5). "
                               "The separate burning rule (103) stays within 12°. Full text in the notes below.")
        _reading_checkbox("Mars under the rays to 18° west", "mars_west_18", "_mars_west_18",
                          help="Dykes's table has Mars under the rays at 18° west; Gr. Intr. VII.2, 31 gives 15°. "
                               "With this reading on, the table's 22° figure closes his setting band. Both give 18° "
                               "east. Full text is on Sources and in this table's notes.")
    # True planets only — angles, nodes, and Lot of Fortune
    # now live in the "Calculated Points" table alongside it.
    # The Lesson 3 homework asks for sign/degree/minute AND absolute
    # longitude, whole-sign place, quadrant division, and whether the
    # planet is direct or retrograde -- all of which this app already
    # computes and none of which it showed on the table a student
    # reaches for first. Lesson 16's solar phase is here for the same
    # reason, and Lesson 15's standing instruction -- does the planet
    # see the Ascendant, i.e. is it out of the 2nd, 6th, 8th and 12th
    # -- is the "Sees ASC" column.
    pos_list = _positions_rows()
    st.dataframe(pd.DataFrame(pos_list), hide_index=True, width='stretch',
                 column_config=_yes_no_columns(pd.DataFrame(pos_list)))
    st.caption("Quadrant column: Alchabitius house, advancing or retreating in Sahl's sense "
               "(The Introduction Ch. 3, 4-5): stake or succedent versus falling. "
               "Sees ASC: whole-sign aversion to the first place (the 2nd, 6th, 8th and 12th do not see it).")
    # What the table's two least obvious states rest on, said beside the
    # table that prints them (the re-pass of 2026-10-04, L2R-07): the
    # station is this app's one tolerance (motion_state; the texts speak of
    # a planet's station, Gr. Intr. VII.2, 41-42, and name no speed for
    # it), and Appearing is Abu Ma'shar's own exception for Venus,
    # Gr. Intr. VII.2, 39 with 38 (Gr. Intr. p. 418): 38, "sometimes she will be
    # seen in the east or west while she is [still] with the Sun in 1', and
    # indeed it is like that when she is at the utmost of her latitude" --
    # the heart, by longitude (Dykes's fn 40) -- and 39, "So when Venus is
    # in this condition of great latitude and visibility, she is not called
    # 'burned,' but rather she is called 'appearing' until her latitude is
    # below 7° and she nears the Sun a little bit by latitude: then perhaps
    # she will not be seen, and is called 'burned' at that time." The
    # caption's "in the heart or burned" rests on both, so it cites both,
    # in the form the Dignities page's note uses for the same pair.
    st.caption(f"Motion: a planet within {STATION_SPEED_TOLERANCE} degrees a day of rest is Stationary, neither "
               "direct nor retrograde (this app's own figure; the texts name none). Solar phase: Venus is "
               f"Appearing where her latitude is {VENUS_APPEARING_LATITUDE:.0f}° or more and her longitude alone "
               "would put her in the heart or burned: \"she is not called 'burned,' but rather she is called "
               "'appearing' until her latitude is below 7°\" (Gr. Intr. VII.2, 39, with 38).")
    # The two under-the-rays readings' full texts, the Mars tooltip's
    # sentences whole beside the Moon's, where the checkboxes stand.
    _notes_expander(NOTES_TITLE, [
        ("The Moon under the rays to 15°.",
         "Sahl, On Nativities 1.19, 6 gives 15 degrees for the Moon; Gr. Intr. VII.2, 61 and 72-73 "
         "give 12. Affects: the Solar phase column here, and on the Configurations "
         "page Weakness (93), Planetary Condition and the ray-dependent Moon conditions; also the prosperity triplicity lords (Sahl, On Nativities 2.11, 5). The separate Moon burning rule (103) remains within 12°. "),
        ("Mars under the rays to 18° west.",
         "Dykes's table for Sahl (the chapter head of On Nativities 1.22, with fn 175, which "
         "works the 18 out from the 22 degrees of 1.22, 2 and Mars's daily motion) has Mars under the rays "
         "at 18 west; Sahl's own sentences are silent on Mars west. The same 18 is Gr. Intr. VII.2, 30's "
         "westernizing boundary for Mars, an agreement this app notes; fn 175 does not cite it. Gr. Intr. VII.2, 31 puts "
         "him under the rays at 15 on the western side. With the reading on, Dykes's paired "
         "22-degree figure keeps the setting band from above 18 through 22. Both "
         "give 18 east. Affects: the Solar phase column here and every test that reads it "
         "(Weakness 93, Planetary Condition 27/34/45)."),
    ])
    points_col, cusps_col = st.columns(2)
    with points_col:
        st.subheader('Calculated Points', help="Non-planetary chart points: the four angles (Ascendant, Midheaven, Descendant, Imum Coeli), the Moon's Nodes, and the Lot of Fortune (a sect-dependent formula combining the Sun, Moon, and Ascendant).")
        calc_list = _calculated_point_rows()
        st.dataframe(pd.DataFrame(calc_list), hide_index=True, width='content')
    with cusps_col:
        st.subheader('Quadrant divisions (Alchabitius)', help='The twelve quadrant house cusps computed by the Alchabitius (semi-arc) system -- this app\'s other unit beside the whole-sign places: whole signs where the texts speak of a topic, these divisions where they speak of a planet\'s strength (the five-degree allowance at the four axial degrees).')
        if AT_POLE:
            st.warning(POLE_HOUSES_SENTENCE + " " + POLE_CROSSING_SENTENCE)
        else:
            house_list = _house_cusp_rows()
            st.dataframe(pd.DataFrame(house_list), hide_index=True, width='content', height=_rows_height(12))
    _finding(_gap, 'Special Degrees & Conditions', None, special_degrees,
              glance='Flags planets in Sahl\'s dark signs (Libra, Capricorn), in the two signs of his burned place, in a welled degree of their sign, or in one of Sahl\'s two sign-boundary conditions.',
              summary='Flags planets in Sahl\'s dark signs (Libra, Capricorn), in the two signs of his burned place ("the end of Libra and the beginning of Scorpio" -- he gives no degrees; Abu Ma\'shar\'s band from the 19th degree of Libra to the 3rd degree of Scorpio is applied in his own Planetary Condition table and, borrowed and labelled, in Sahl\'s condition 110), in a welled degree of their sign (Abu Ma\'shar, Gr. Intr. V.21, Fig. 62), or in one of Sahl\'s two sign-boundary conditions.',
              note_sections=[
                  ("Entering a sign.",
                   '**Entering**:\n\n> "every planet which is at the beginning of a sign is weak until it is firmly established in it and comes to be 5 degrees within it"\n\n(Fifty Aphorisms #44, 87), repeated in On Nativities Ch. 1.22, 9. This is the other half of the five-degree rule that also governs advancement.'),
                  ("Leaving a sign.",
                   '**Leaving**:\n\n> "if a planet came to be in the last degree of the sign, then its strength has already gone away from that sign, and its strength is in the next sign ... like a man putting his foot on the threshold of his door. And if a planet was in the twenty-ninth degree, then indeed the strength of the planet is in that sign"\n\n(Fifty Aphorisms #15, 31-33) -- so the 29th degree still counts and only the 30th has left.'),
              ])
    _finding(_gap, 'Degrees of nobility and rank', 'Sahl, On Nativities 1.38, 39-41 (Figure 57)', nobility_degrees_data,
              glance='Sahl\'s own table of the degrees in which "the native will reach nobility and rank": a row when the Ascendant, the Sun or the Moon stands in one. Display only; nothing scores it.',
              notes='On Nativities 1.38, 40-41: "If it happened that a native was born and his Ascendant was one of these degrees, or the Moon and Sun were in the equivalent of these degrees (and that is superior if it was the Sun by day and by night the Moon), then he will reach exaltation and power, or he will rule many lands, by the permission of God." Figure 57 of his volume prints the degrees: Aries 19; Taurus 3; Gemini 13; Cancer 1, 13, 14, 15; Leo 5, 7; Virgo 2, 13, 20; Capricorn 12, 13, 20; Aquarius 12, 20 -- none in Libra, Scorpio, Sagittarius or Pisces. The figure prints bare degrees; this app reads them as ordinals, as Figure 64 prints the same rule\'s degrees -- Dykes\'s own resolution of the tables\' cardinal-or-ordinal inconsistency is the end of the numbered degree, 19 for "the nineteenth" (ITA I.3 fn 23), the endpoint, not a warrant for the ordinal interval. This app tests the nineteenth degree as [18°, 19°), excluding the point 19°. The whole table is on the Reference tables page, with al-Qabisi\'s third table of the rule named (ITA VII.9, Figure 118). Abu Ma\'shar states the same rule with a table of his own (Gr. Intr. V.22, 4, Figure 64), twelve signs to its eight, six of those eight disagreeing; it is shown under Course text and supplement, on the Configurations page beside Strength and weakness and on the Reference tables page beside this table.')
    _absent(_gap)
    # The orders of the dignities and the good places -- static tables --
    # moved to the Reference tables page on 2026-09-10; what stays is
    # the one table that reads this chart.
    with st.expander("Sahl's sign categories for this chart's points", icon=":material/menu_book:"):
        st.caption("Where The Introduction and On Nativities disagree, both readings are shown and neither is merged. "
                   "Sources: " + "; ".join(f"{k}: {a} / {b}" for k, (a, b) in SIGN_CATEGORY_SOURCES.items())
                   + ". The orders of the dignities and the good places are on the Reference tables page.")
        cat_rows = []
        for p, d in list(p_data.items()) + [('Ascendant', {'longitude': chart_data['ascendant']})]:
            if p == 'North Node':
                continue
            sign_p = get_zodiac_sign(d['longitude'])
            cat_rows.append({'Point': p, 'Sign': sign_p, **sign_categories(sign_p)})
        st.dataframe(pd.DataFrame(cat_rows), hide_index=True, width='stretch', height=_rows_height(len(cat_rows)))

# The delineation findings, off the Chart page (which is the cast) and,
# for Mars by sect, off the Dignities page. Ordered by the source rather
# than by the order they were appended: the course text's findings in the
# order of the Sahl chapter each cites, then the supplement's, grouped by
# author in the order the Sources page names the texts, and the texts it
# does not name after those, the oldest first.
def page_findings():
    if not chart_ok:
        _recovery_panel("Findings")
        return
    st.header("Findings")
    _chart_strip(counts_from_the_ascendant=True)
    st.caption("The delineations the texts read off the chart already cast -- "
               "Sahl's own findings first, then the supplement's -- each under the sentence it applies. "
               "Nothing here is scored; the judgment is the astrologer's.")
    _sources_scope_line()
    _readings_note()
    with st.expander("The prenatal degree's governor (Sahl, On Nativities 1.7)"):
        st.markdown(_display_result(syzygy_governor['summary']))
        st.caption("The candidate conditions and any alternatives are shown on Lunation and victors; this note reads the same judgment.")
    _gap = []
    _finding(_gap, "The fetus's stay (Sahl)", "Sahl, On Nativities 1.8-1.9", gestation_data,
              columns=GESTATION_COLUMNS, height=_rows_height(len(gestation_data)),
              glance="What On Nativities 1.8 and 1.9 let this app state of the fetus's stay in the belly. Display only; nothing scores it.",
              summary="What On Nativities 1.8 and 1.9 let this app state of the fetus's stay in the belly: the meeting before the birth and its Ascendant (1.8, 5-6), the three Moons of 1.9, 1 and the sentence of 1.9, 2-10 that names their aspects.",
              qualifications=["**Not computed.** On Nativities 1.8's three divisions are framed from a chart the text does not name and are not computed; the rows say what is not.",
                              "**This app's reading of the year.** The anniversary repeats the local birth month, day and clock time in the birth calendar, then converts that selected moment to UT. A named zone uses its rule on the target date; LMT and manual offsets stay fixed. A date or local clock time that does not exist, or is ambiguous, or that falls in a period the birth would be refused in, is unavailable without a fallback, and the cell says why. The aspects are whole-sign; a sentence of 2-10 whose condition holds is a row, and where none holds the row says so."],
              note_sections=[
                  ("The meeting before the birth and its Ascendant (On Nativities 1.8, 5-6).",
                   'On Nativities 1.8, 5-6:\n\n> "' + SAHL_1_8_5 + ' ' + SAHL_1_8_6 + '"\n\n-- the meeting is the last New Moon before the birth; Dykes\'s fn 40 ("' + SAHL_1_8_FN40 + '") allows the lunation generally, so the opposition is shown beside it when that was the lunation nearer the birth. The Ascendant is erected for the hour of the meeting at the birthplace.'),
                  ("The three divisions of On Nativities 1.8, not computed.",
                   'On Nativities 1.8, 3-4:\n\n> "' + SAHL_1_8_3 + ' ' + SAHL_1_8_4 + '"\n\nFn 38 on "the degree of the Ascendant":\n\n> "' + SAHL_1_8_FN38 + '"\n\nDykes\'s comment:\n\n> "' + SAHL_1_8_COMMENT + '".\n\nThe sentence does not name the chart whose Ascendant frames the divisions; the pre-conception lunation is not found by any sentence of On Nativities 1.8 (the conception is the matter of 1.10); so this app lays out no divisions and does not read 7-13. Dykes also notes that 7-9 disagree with Hephaistion (fnn 41-42) and that 10-13 give three of the six permutations.'),
                  ("The seven-month native and the four-footed nativities (On Nativities 1.8, 1).",
                   'On Nativities 1.8, 1:\n\n> "' + SAHL_1_8_1 + '"'),
                  ("The three Moons of On Nativities 1.9, 1, and the year.",
                   'On Nativities 1.9, 1:\n\n> "' + SAHL_1_9_1 + '"\n\nFn 45:\n\n> "' + SAHL_1_9_FN45 + '"\n\nThe numerical convention repeats the local birth month, day and clock time in the birth calendar and only then converts to UT. Named zones use the target date\'s rule; LMT and manual offsets remain fixed. Invalid, ambiguous, or nonexistent target moments, and those in a period the birth would be refused in, are unavailable without substituting an elapsed-year duration; the cell says why. The aspects of the past and renewed Moons to the natal Moon are whole-sign; a sentence of 2-10 whose condition holds is a row, and where none holds the row says so.'),
                  ("The aspects of On Nativities 1.9, 2-10.",
                   'On Nativities 1.9, 2-10:\n\n> "' + ' '.join(t for _, t in SAHL_1_9_RULES) + '"\n\n(fn 47: "' + SAHL_1_9_FN47 + '"; fn 49: "' + SAHL_1_9_FN49 + '"; fn 51: "' + SAHL_1_9_FN51 + '")'),
                  ("The conception and the stay by the day and hour, not computed (On Nativities 1.9, 11-14).",
                   'On Nativities 1.9, 11:\n\n> "' + SAHL_1_9_11 + '"\n\n(fn 53: "' + SAHL_1_9_FN53 + '") -- not computed: the meeting of the conception is not in hand.\n\nOn Nativities 1.9, 12-14:\n\n> "' + SAHL_1_9_12 + ' ' + SAHL_1_9_13 + ' ' + SAHL_1_9_14 + '"\n\n(fn 54: "' + SAHL_1_9_FN54 + '"; fn 55: "' + SAHL_1_9_FN55 + '") -- the stay by the day and hour is On Nativities 1.10\'s matter and is not computed here.'),
              ])
    _finding(_gap, "The Moon on the third day (Sahl)", "Sahl, On Nativities 1.29, 11-12; 1.26, 7", moon_third_day_data,
              columns=MOON_THIRD_DAY_COLUMNS, height=_rows_height(len(moon_third_day_data)),
              glance="The Moon on the third day -- two days after the birth, the birth day counted as the first. Display only; nothing scores it.",
              summary="The Moon on the third day -- two days after the birth, the birth day counted as the first: her sign and place, On Nativities 1.26, 7's intersign looks; the corruption profile this app reads from 1.29, 3 (co-presence, enclosure, burning, falling); and the limited third-day component of 1.29, 11-12.",
              qualifications=["**The third day, this app's reading of Firmicus.** This app takes it two days after the birth, the birth day counted as the first (Firmicus, Mathesis II.29, 34, in the nativity of Albinus; III.14, 17-19), the birth hour kept, and computes all seven planets with motion there.",
                              THIRD_DAY_CORRUPTION_READER],
              note_sections=[
                  ("The sentences: On Nativities 1.29, 11-13 and 1.26, 7.",
                   'On Nativities 1.29, 11:\n\n> "' + SAHL_1_29_11 + '"\n\nOn Nativities 1.29, 12:\n\n> "' + SAHL_1_29_12 + '"\n\nOn Nativities 1.29, 13:\n\n> "' + SAHL_1_29_13 + '"\n\n(fn 304: "' + SAHL_1_29_FN304 + '")\n\nDykes\'s fn 303 on 11:\n\n> "' + SAHL_1_29_FN303 + '"\n\nOn Nativities 1.26, 7:\n\n> "' + SAHL_1_26_7 + '"'),
                  ("The day count.",
                   'No sentence of On Nativities 1.29 or 1.26 says when "the third day of the Moon" is taken; Sahl\'s words elsewhere are "the position of the Moon, where she is on the third day from the nativity" (Ch. 9, 3) and "the position of the Moon on the third day, the seventh, and the fortieth day" (1.30, 22). This app takes it two days after the birth, the birth day counted as the first (Firmicus, Mathesis II.29, 34, in the nativity of Albinus; III.14, 17-19), the birth hour kept, and computes all seven planets with motion there. Sahl\'s fn 95 and Holden\'s fn 2 on Rhetorius independently witness this inclusive count. Firmicus gives the worked chart\'s places by sign (II.29, 22), and says "on the third day the Moon, being established in Leo, full of light, flung herself into the rays of Mars" (II.29, 34). At the corrected Figure 34 instant, the Moon remains in Cancer one day after the birth, reaches Leo on Mars\'s opposition ray two days after, and is past that ray three days after. Of the third day he says, "and this day, that is the third, operates in a very powerful way in nativities" (Mathesis II.29, 34), and at III.14, 17-19 that on it "she decrees all things in a similar way" to the first. The retained birth hour is this app\'s numerical convention.'),
                  ("The corruption tests.",
                   'On Nativities 1.29, 3 names the corruptions the chapter has in view:\n\n> "' + SAHL_1_29_3 + '"\n\nSo the third-day Moon is read as corrupted under this limited profile by co-presence, square or opposition with an infortune, enclosure, burning or falling. This remains separate from On Nativities 1.26, 7\'s broader looking predicate; enclosure uses Sahl\'s separation, application and intervening-ray evaluation. Burning is within twelve degrees (The Introduction Ch. 3, 103). Falling is counted from the Ascendant of the nativity, which On Nativities 1.30, 33 takes her position relative to, and by the Alchabitius divisions of the nativity, as the Planetary Condition and Strength of the Planets tables count the stakes. On Nativities 1.22, 9 gives the allowance, "the planets will not fall from the stakes except after 5°". So the third-day Moon falls only in the 12th, 3rd, 6th or 9th division, and only when she is more than five degrees before the degree of the stake that division ends at: the Ascendant, the stake of the earth, the seventh or the Midheaven. Within those five degrees she is still in the stake. The divisions, the five degrees counted in longitude, and exactly five degrees counted as within are this app\'s reading. The first row gives her whole-sign place from the Ascendant of the nativity; the Falling row counts by the divisions with the five degrees, so their numbers can differ. The square/opposition aggravation is On Nativities 1.29, 31. Other lunar defects are outside this row.'),
                  ("The four-footed signs.",
                   'On Nativities 1.26, 7\'s sign is taken from 1.38, 1:\n\n> "' + SAHL_1_38_1 + '"\n\n-- Aries, Taurus, Leo and the second half of Sagittarius. On Nativities 1.26, 7 is one indicator among the chapter\'s; the row says met or not met and no more.'),
                  ("Clauses not evaluated: On Nativities 1.29, 11 and 12.",
                   'The row for 11 reports only its last clause, the third day not corrupted; the lords of the triplicity and the fortune in a stake are not tested in this table. The row for 12 reads "the two infortunes were in the Ascendant or seventh" as both natal infortunes in the whole-sign first or seventh place, this app\'s reading, and reports its first clause; the second clause (the lords of the triplicities withdrawing from the stakes) is not tested here.'),
              ])
    # The first row is this app's synthesis, said so: the two lords of the
    # sect light's triplicity by whole-sign place give the pattern
    # (On Nativities 2.11, 1-3), the partnering lord (2.11, 4) and the Lot
    # step (2.3, 6) modify it. Rows a text other than Sahl states (2.16, 6,
    # bracketed from BA) show under Course text and supplement only.
    # One row of the finding printed whole: its cells as labelled
    # paragraphs, the words the table holds and nothing else.
    def _prosperity_row(row):
        for _field in ('Class', 'Ground', 'Sahl', 'Also', 'Triplicity table', 'Virgo source note'):
            _value = row.get(_field)
            if _value is not None and _value != '':
                st.markdown(f"**{_field}.** {_display_result(_value)}")
    _finding(_gap, "Sahl: indications of fortune and livelihood", "Sahl, On Nativities 2.1-2.21",
              [r for r in prosperity_data if READING_DEPTH == READING_DEPTH_OPTIONS[1] or not r['Supplement']],
              columns=['Class', 'Ground', 'Sahl', 'Also', 'Triplicity table', 'Virgo source note'],
              column_help={'Class': "The first two triplicity lords describe the pattern across their periods; the partnering lord, the Lot of Fortune, and other conditions modify the reading. A single seven-class outcome is not specified for every combination in Sahl's chapter."},
              glance="Sahl's indications of fortune and livelihood. Display only; nothing scores it.",
              summary="The first row is this app's synthesis: the class it reads from the first and second lords of the sect light's triplicity by whole-sign place, said so, with the partnering lord's modification (On Nativities 2.11, 4) and, when the Lot of Fortune is worked (2.3, 6), the Lot's judgment beside the lords' -- mixed or unresolved where Sahl gives no precedence; under it the lords, the partnering lord, and every further rule of the chapter that the chart meets, each with Sahl's sentence and the parallel in the Book of Aristotle or Abu 'Ali.",
              qualifications=["**This app's synthesis.** A single seven-class outcome is not specified for every combination in Sahl's chapter, so the first row is this app's synthesis and says \"read by this app as class N\" with its grounds."],
              detail=_prosperity_row, detail_key='Class')
    st.caption("For the triplicity lords, On Nativities 2.11, 5 gives a lord under the rays no strength; the "
               "heart through 1° (The Introduction Ch. 3, 87) is exempt, this app's reading. "
               "Falling or a separate infortune still applies; the Moon's outer ray limit follows the 12°/15° reading.")
    st.caption("This class summarizes the two lords' place-and-rays strength (On Nativities 2.11, 1, 5); the lifelong-happiness "
               "promise additionally requires both to be angular and free of infortune affliction and defects (2.3, 2), "
               "and the qualifications shown here modify the overall reading.")
    st.caption("Looking is measured by whole sign: On Nativities 2.3, 7 follows Dykes's proposed 'and' and Sahl's phase criteria, "
               "with otherwise qualifying results marked partial when either strength condition is untested; "
               "2.3, 9 includes its better looking case; and 2.16, 2 uses the six excellent places, "
               "with both readings of whose easternness is required shown separately.")
    _notes_expander("How the prosperity reading is assembled", [
        ("Cleanliness, strength and excellent places.",
         "For On Nativities 2.3, 2 this app checks each lord's angularity by whole sign, retrogradation (1.22, 10), Sahl's rays "
         "(2.11, 5) and fall (Introduction 3, 82); the remaining defects are not fully assessed, so the promise reads 'satisfied under the "
         "declared checks' at best, never verified. Introduction 3, 81's three configurations are read as the infortune "
         "with the lord in one sign (fn 93: assembling), connecting with it under Sahl's connection test, or looking at it "
         "from a square or opposition by whole sign, and the row names the configuration met; fnn 93–94 do not authorize "
         "a new conjunction orb. "
         "This does not replace the separate declared affliction measure of the Lot's rows. "
         "Excellent places are the six 1, 4, 5, 7, 10, 11 (Introduction 3, 78; fn 92), used in On Nativities 2.17, 2–3; "
         "2.19, 6; 2.16, 2; and 2.21, 1. Introduction 2, 37–44 praises seven, adding the ninth: a differing "
         "classification, retained here as a witness. Excellent, strong and powerful are not interchangeable. "
         "In On Nativities 2.17, 2 this app applies the plural to either primary lord; rays do not exempt an afflicted lord "
         "in an excellent place. In On Nativities 2.17, 3 the placement and affliction must belong to the same subject, "
         "the Lot or its lord; both branches are evidence for one sentence."),
        ("The Lot's two strength clauses.",
         "On Nativities 2.3, 7 requires the lord to look from a strong position and an external benefic to witness both Lot "
         "and lord from a powerful position. Neither phrase has a uniquely supplied test; both remain untested "
         "on charts, so an otherwise qualifying row is partial. A failed mandatory clause makes the rule not met. "
         "One external witness can serve both benefic clauses; the lord cannot witness itself. The especially "
         "clause (fn 88) remains an unresolved enhancement. Easternness uses On Nativities 1.22's easternizes-at level: "
         "Saturn/Jupiter 15°, Mars 18°, Venus/Mercury 12° and direct; the Moon's criterion remains unresolved. "
         "On Nativities 2.16, 2's \"and it is eastern\" can be read of the fortune or of the lord of the Lot; the sentence "
         "does not say which, so this app reads it both ways and shows each, with the one outcome, \"in the middle\"."),
        ("Two degree assessments.",
         "The five-degree allowance adjusts strength at the four stakes only, leaving whole-sign place and raw "
         "quadrant house visible. Aphorism 45's fifteen degrees after a stake is a separate power testimony, "
         "not a reassignment of either house measure. Ascensional grades start at the actual axis; their OA/OD/RA "
         "coordinate recipe is this app's convention, and the five-degree allowance never shifts that origin."),
        ("The two triplicity lords.",
         "The first two triplicity lords describe the pattern across their periods; the partnering lord, the Lot of Fortune, and other conditions modify the reading. The pattern is Theophilus's, On Nativities 2.11, 1-3 --\n\n> \"" + PROSPERITY_SAHL['2.11, 1'] + " " + PROSPERITY_SAHL['2.11, 2'] + " " + PROSPERITY_SAHL['2.11, 3'] + "\"\n\n-- with On Nativities 2.11, 5,\n\n> \"" + PROSPERITY_SAHL['2.11, 5'] + "\",\n\nand On Nativities 2.13, 40,\n\n> \"" + PROSPERITY_SAHL['2.13, 40'] + "\"\n\nStrong is a stake or what follows one, falling the third, sixth, ninth and twelfth (fn 149 on \"strong\"), by whole sign. Both strong is read as class 1; On Nativities 2.3, 2 additionally requires both angular and cleansed of infortunes and defects, which is assessed separately; both weak as class 6, the ground naming each lord's weakness -- falling (2.11, 3) or under the rays (2.11, 5) -- since 2.11, 3's word is falling and 2.11, 5 says only that a lord under the rays has no strength; the mixed pair is a timing pattern, \"his benefit will be in the time of the strong one\" (2.11, 2), read by this app as class 2 when the first lord is the strong one and class 5 when the second is, the first lord's time being the beginning of life. That rests on On Nativities 2.13, 39, which says it of the parents' lords (\"the first lord of the triplicity indicates the end of the father's life, and the beginning of the native's life\"); Dykes calls the sentence \"rather unclear\" and thinks the second lord should indicate the beginning (fn 181), and applying the parents' lords to the native's own is this app's step. The infortunes with a lord or in its square or opposition are listed: On Nativities 2.11, 4 makes their aspect an increase or a subtraction, not a class step, and Abu 'Ali's charts read the lords' places."),
        ("The partnering lord.",
         "On Nativities 2.11, 4:\n\n> \"" + PROSPERITY_SAHL['2.11, 4'] + "\"\n\n-- the third lord of the sect light's triplicity is a stated modifier, ranked third by On Nativities 2.3, 22 (\"" + PROSPERITY_SAHL['2.3, 22'] + "\"): its row gives its whole-sign place and its effect in Sahl's words, and the synthesis appends the modification -- \"Modified by the partnering lord (2.11, 4)\", its place, its effect, \"no class step\" -- Sahl giving no class step for it. A lord under the rays in a stake or what follows one is neither: On Nativities 2.11, 4's support wants strength and its bringing down a falling place. Abu 'Ali's own phrase for the Lot at Figure 20, \"of the nature of Venus\", is not a rule Sahl states and is not read."),
        ("Three measures, kept apart.",
         "| Measure | Its part in the reading |\n"
         "|---|---|\n"
         "| The whole-sign place from the Ascendant | Read by the synthesis: strong is a stake or what follows one, falling the third, sixth, ninth and twelfth |\n"
         "| The sign against the degree (On Nativities 2.3, 17-18) | A second measure, read from the raw quadrant cusps and a separate strength house with the inclusive 5° allowance before the four stakes when the chart carries them and shown as their own rows (\"By sign and by degree\"); they move nothing |\n"
         "| The fifteen degrees from the axial degree by ascensions (On Nativities 2.13, 48-51) | A third measure, shown as the grade row when the chart carries its meridian and latitude, and never folded into strong or weak |\n\n"
         "The synthesis reads the whole-sign place from the Ascendant. On Nativities 2.3, 17-18 --\n\n> \"" + PROSPERITY_SAHL['2.3, 17'] + " " + PROSPERITY_SAHL['2.3, 18'] + "\"\n\n-- are a second measure, the sign against the degree, read from the raw quadrant cusps and a separate strength house with the inclusive 5° allowance before the four stakes when the chart carries them and shown as their own rows (\"By sign and by degree\"); they move nothing. The fifteen degrees --\n\n> \"" + PROSPERITY_SAHL['2.13, 48'] + " " + PROSPERITY_SAHL['2.13, 49'] + " " + PROSPERITY_SAHL['2.13, 50'] + " " + PROSPERITY_SAHL['2.13, 51'] + "\"\n\n-- are a third, measured from the axial degree by ascensions (fnn 82-83, 222): oblique ascension from the Ascendant, oblique descension from the seventh, right ascension from the Midheaven and the fourth, the preceding stake selected first in zodiacal order, then measured in its own coordinate; the first lord only, with no whole-sign exclusion; the earlier interval includes exactly 15°, 30° and 45°, and the next axis restarts at zero; shown as the grade row when the chart carries its meridian and latitude, and never folded into strong or weak. No house system is changed by any of the three."),
        ("When the Lot is considered.",
         "On Nativities 2.3, 6:\n\n> \"" + PROSPERITY_SAHL['2.3, 6'] + "\"\n\nThe sentence's \"the lord of the triplicity\" is singular and states no quantifier -- not the first lord only, not both together; this app enters the Lot step when either lord is made unfortunate, its own reading of that singular, not the sentence's word. \"Made unfortunate\" is read by this app as a lord weak (falling, or under the rays) or with an infortune with it or in its square or opposition (On Nativities 2.20, 1's gloss, applied here as it is to the Lot, its lord and the lords of places). Sahl's own \"made unfortunate\" is affliction by the infortunes (On Nativities 2.17, 2, \"the infortunes made them unfortunate\"; 2.20, 1's gloss; and 2.11, 14 keeps \"falling\" and \"made unfortunate\" apart); the wider gate rests on 2.3, 2's \"cleansed of the infortunes and of defects\" and is this app's."),
    ])
    _notes_expander("How the Lot and the triplicity lords are combined", [
        ("What each source judges, and that Sahl gives no precedence.",
         "At the Lot, Sahl's sentences are judgments of the native, not evidence to collect: On Nativities 2.3, 7 \"the native will be a king, or prominent\", 2.3, 9 \"he will be happy\", 2.16, 2 and 4 \"in the middle\", 2.20, 1 \"will not cease to be miserable from the day he is born up to the day he dies\". No sentence of On Nativities says how they combine with Theophilus's judgment from the two lords (2.11, 1-3): none says the Lot's sentence replaces it, none says the two lords' reading stands regardless, none makes the number of weak lords a threshold, and 2.11, 4's \"increases in that and subtracts from that\" is about the aspects of the fortunes and infortunes, not the Lot's verdict; Sahl gives an order of investigation (2.3, 6, then 2.3, 10, \"" + PROSPERITY_SAHL['2.3, 10'] + "\"), not a precedence among verdicts, and Theophilus (2.11) and al-Andarzaghar (2.16, 2.20) are never reconciled into one rule. So when a sentence of the Lot's is met the synthesis carries two attributed clauses, the Lot's judgment with its sentence and the two lords' with theirs, and says the combination is this app's."),
        ("Mixed: one lord strong, the other made unfortunate.",
         "With one lord strong and the other made unfortunate, the two lords give a timing pattern (On Nativities 2.11, 2), not a level, and the Lot's level stands beside it, mixed by design and no single class -- \"the Lot indicates middling livelihood (2.16, 4); the two triplicity lords indicate hardship in the first lord's time and benefit in the second's (2.11, 2)\" -- with 2.11, 2 shown beside it:\n\n> \"" + PROSPERITY_SAHL['2.11, 2'] + "\"\n\nThat mixed reading rests on On Nativities 2.16, 5, which couples a middling condition with variation (\"sometimes with good, and sometimes with hardship\"), and holds for the Lot's middling and high levels; 2.20's misery \"from the day he is born up to the day he dies\" admits no time of benefit, so beside the mixed pair it is a conflict, not a mixture."),
        ("Agreement, and conflict left unresolved.",
         "When the two lords give a level (On Nativities 2.11, 1 high rank throughout, 2.11, 3 baseness throughout) and the Lot the same level, the two are concordant and the class is read; when the judgments are opposed -- both lords falling and the Lot promising very high rank (2.3, 7), both strong and the Lot 2.20's misery, or one strong and the Lot 2.20's misery -- the synthesis says \"conflicting status indications\", names both with their sentences, and reads unresolved: this app installs no priority."),
        ("The Lot's own sentences met at two levels.",
         "On Nativities 2.16, 2 and 4 need no order between them, both supporting the one middling statement; 2.3, 7 cannot hold with 2.16, 4 (the infortunes not looking at the Lot against all looking), with 2.16, 2 (the lord cleansed against made unfortunate) or with 2.20, 1 (the Lot in a stake or what follows against the sixth or twelfth) under the one measure of looking; 2.3, 9 can hold beside 2.16 or 2.20, and where the Lot's own sentences are met at two levels the synthesis says so and is unresolved, no order installed. On Nativities 2.3, 7's \"eastern or cleansed\" is read as \"and\" (fn 87), and its two strength positions are not uniquely defined by the supplied passages: otherwise qualifying results remain partial. On Nativities 2.3, 9's \"it occurred in the fifth or eleventh from the Ascendant\" is the Lot's lord, the sentence's subject, and the place tested is the lord's. On Nativities 2.3, 10-11's further step, the lords of the Ascendant, the Midheaven and the house of hope, is not computed here except as 2.16, 5's motley mixture."),
    ])
    _notes_expander("Source passages, alternatives and coverage", [
        ("The seven approaches.",
         "Sahl, On Nativities 2.1, 2-9:\n\n> \"And good fortune is based on seven approaches: The first of them, on good fortune and how much that good fortune will come to. Second, <on one who> falls from that good fortune. Third, those whose livelihood is middling. Fourth, the rabble [and] those who come down from an ascent to a downfall. Fifth, those who rise up after wretchedness. Sixth, the wretched who do not cease to be in wretchedness. Seventh, those whose profit comes from their own hands.\"\n\nDykes's comment at the head of the chapter: the fourth repeats the second, and the seventh joins profit from one's own hands with violence and injustice (fn 1; On Nativities 2.21, 3); his table sets them against the Book of Aristotle's III.2.1-III.2.6."),
        ("On Nativities 2.20, 1-2, as this app reads the chain.",
         "On Nativities 2.20, 1, as this app reads its chain:\n\n> \"" + PROSPERITY_SAHL['2.20, 1'] + "\"\n\nThe first clause is two alternatives, the lord made unfortunate or the Lot unfortunate; \"it\" in \"the sixth and twelfth\" is the Lot, which is in one of the two places, not both -- the nearest antecedent in the fuller text, though there is another reading: fn 255 says one manuscript omits the phrase about the Lot, so there \"it\" is the lord, and the Book of Aristotle (III.2.5 [5.1], the row's parallel) has the lords of the triplicity or of the Lot themselves in the sixth or twelfth; this app reads the Lot; \"the infortunes were with it or they looked at it from a square or opposition\" says what unfortunate means and is applied to the Lot; \"the lord of the Lot in the house of its fall, or made unfortunate\" is two alternatives, and its \"powerful in misfortune\" is not tested; the parenthesis is the sect light; and the Mars clause is for a day birth only -- with the Lot, or opposing or in square to it -- so by night it is not required (fn 256: one manuscript adds \"or with the Sun\"; Carmen has the lord of the Lot). The Lot in the sixth or twelfth with an infortune on it, its lord in its fall or made unfortunate, and Mars on the Lot by day, all together, are what the row tests. On Nativities 2.20, 2 is read whole, its continuation over the page included:\n\n> \"" + PROSPERITY_SAHL['2.20, 2'] + "\"\n\n-- the lord of the Lot in the sixth or twelfth, Jupiter and Venus both made unfortunate in the sixth or twelfth, both not looking at the Moon; the bracketed \"worse is if\" clause is an aggravation, not a condition, and is not tested (fn 258: added with the sense of Carmen)."),
        ("Routes to middling livelihood.",
         "The middle has several routes in On Nativities' chapter, each its own row: the third fifteen degrees by ascensions (2.13, 50; 2.16, 3, whose wording Dykes calls unclear, fn 222); the Lot's 2.16, 2 and 4; 2.16, 5's motley mixture of the lords of the Ascendant, the Midheaven and the house of hope (listed; its third place disputed, fnn 225-226: the second house); 2.16, 6, bracketed in Sahl from BA III.2.3, 6, shown under Course text and supplement only; On Nativities 2.11, 14, \"" + PROSPERITY_SAHL['2.11, 14'] + "\" -- the lord of the house of assets falling but not made unfortunate, falling read as the place (fn 154 on 2.11, 13 asks whether its fall is meant); and 2.3, 19, \"" + PROSPERITY_SAHL['2.3, 19'] + "\", a lord of the triplicity in the second or eighth, listed as a decline (2.3, 20: set aright if a fortune; 2.3, 21: Jupiter there, not the governor). Abu 'Ali's own rule, the lords in the succedents middling, is quoted beside the rows and not applied: his second example, both lords in succedents, he calls prosperity and riches."),
        ("Further indications, listed under the synthesis.",
         "Sahl's further indications in On Nativities -- the eleventh from the Ascendant (2.3, 12), the falling of 2.17 (2, 3, 4, 5, 7, 8, 10, 11), the rising of 2.19 (1, 2, 5, 6), the earnings of 2.21 (1-4) -- are listed under the synthesis with their sentences and do not move it: the chapter gives no order for combining them and the twelve charts apply none. On Nativities 2.17, 8 states its own precedence (\"even if he was a king\") and is listed, not applied to the class; 2.19, 6 is listed on 2.17, 7's footing (BA III.2.4 [4.5] has the stars \"from the east toward the Midheaven\" where Sahl has the bad places). On Nativities 2.17, 7's and 2.21, 3's eleventh from the Lot of Fortune is Sahl's own; the Book of Aristotle (III.2.1 [1.7]) has it as strong as the eleventh from the Ascendant. The Moon's separation and connection (On Nativities 2.17, 10; 2.19, 2) are read by degree within her orb when the chart carries motions."),
        ("The other fortune and differing witnesses.",
         "For On Nativities 2.21, 2 this app retains no fortune looking as BA's reading (fn 268), whose outcome is dependence "
         "on others. Carmen instead has both fortunes looking (fn 267), with good livelihood among strangers. "
         "The referent of Sahl's other fortune remains open; no identity is supplied by this app. "
         "The two witnesses and their different outcomes are preserved beside Sahl's sentence. "
         "Fn 234 to On Nativities 2.17, 7, whole: \"Cf. *Carmen* I.28, 32 (which mentions only the eleventh from the Ascendant) "
         "and *Anth.* II.12 and Rhetorius Ch. 54 (p. 36), which discuss the infortunes (and other planets) in the "
         "eleventh from the Lot. However, *BA* adds that they are contrary to the sect (which makes more sense).\" "
         "The two On Nativities 2.17, 7 rows list Mars or Saturn there whatever the sect, as Sahl's sentence has it."),
        ("Passages not evaluated.",
         "| Passage of On Nativities | Extent not evaluated |\n"
         "|---|---|\n"
         "| 2.3, 3, 4-5 | Not read, except as the grade's footing (fnn 82-83) |\n"
         "| 2.3, 8 | Not read |\n"
         "| 2.3, 10-11 | Not read, except as On Nativities 2.16, 5's motley mixture |\n"
         "| 2.3, 13-16, 23-24, 25–56 | Not read |\n"
         "| 2.11, 6-13 and 15-19 | Not read |\n"
         "| 2.13 apart from 39-40 and 48-51 | Not read |\n"
         "| 2.16, 3 | Not read, except as the grade |\n"
         "| 2.17, 6, 9, 12-14 and 2.18 | Not read |\n"
         "| 2.19, 3-4 and 7-9 | Not read |\n"
         "| 2.20, 3-6 | Not read |\n"
         "| 2.2's fixed stars | Not read |\n"
         "| 2.4-2.10 and 2.12-2.15 | The chapter's other topics, not read |"),
        ("The worked-chart checks.",
         "The charts checked are Abu 'Ali's twelve worked charts (PN I, JN Ch. 7, Figures 10-21), read by whole sign from the signs he prints; the degrees he does not print are left unknown, and the six charts that his notes or Dykes's read otherwise than the printed signs allow are kept as textual observations, not as verdicts this app must reproduce."),
    ])
    if READING_DEPTH == READING_DEPTH_OPTIONS[1]:
        _finding(_gap, 'Places harming the eyesight', 'Sahl, On Nativities 6.2, 48-75; Gr. Intr. VI.20; Abu Bakr, On Nativities II.7.3',
                eyesight_places_data,
                columns=['Point', 'Position', 'Place', 'Source', 'Text'],
                standing="Display only",
                glance='The "degrees of chronic illness in the signs". Display only; nothing scores it; shown under Course text and supplement.',
                summary='The "degrees of chronic illness in the signs" -- the nebulous places named for the Pleiades, the cloud of Cancer, the forehead and sting of the Scorpion, the arrow, the spines and the rope: a row when the Moon, the lord of the Ascendant, the Sun or the Ascendant degree stands in one, each text\'s span under its own source (Sahl\'s four lists, Abu Ma\'shar\'s measured places, Abu Bakr\'s list), none reconciled.',
                qualifications=['**This app\'s addition, and what is not tested.** Sahl\'s rule names the Moon and the lord of the Ascendant (48), the Moon by night and the Sun by day (69); the Ascendant degree itself is shown beside them as this app\'s addition, and the further conditions each rule attaches -- the infortunes looking, the Moon\'s light, made unfortunate -- are printed in the Text column and are not tested.',
                                '**Method.** Neither table is precessed here: each is applied as printed. Readings, this app\'s: a degree named as an ordinal or printed bare ("the ninth degree", "from 6° to 9°") is the ordinal degree, as Sahl I Figure 57 is read, so "the ninth to the fifteenth" is 8°00\'-15°00\'; a longitude measured in minutes is taken as printed, a single one as the whole degree it falls in, and Abu Ma\'shar\'s bare "20°" and "22°" (Gr. Intr. VI.20, 6 and 8) as measured whole degrees, 20°00\'-21°00\' and 22°00\'-23°00\'.'],
                note_sections=[
                    ("Sahl, On Nativities 6.2, 48-75: four lists.",
                     'Sahl, On Nativities 6.2, 48:\n\n> "And if you found the Moon in the degrees of chronic illness in the signs, and the infortunes looked at her and their bound, <it indicates> a defect of the eyesight generally, or in the rest of the body: because in the signs are positions which if the Moon is made unfortunate in them, or the lord of the Ascendant, it indicates the corruption of the eye; and that is:"\n\n-- then 49-55, the places. 56-57:\n\n> "If you found the Moon in something of these signs, decreasing in glow, made unfortunate from hostility, then the eyesight will be chronically afflicted. And if she was increasing in glow, full, there will be water in his eyesight, and [uncertain] and [what] resembles that like [uncertain], and his eyesight will not be obscured."\n\nRhetorius\'s list follows (60: "The [degrees] indicative of chronic illness are:", 61-68), which Dykes says "overlap with, but are not identical to, the degrees harming the eyes"; then the Bizidaj (69: "Now as for the degrees which indicate the corruption of vision especially, if the Moon was with them by night and the Sun by day, made unfortunate, that is in the conjunction of:", 70-72); then Nawbakht (74: "And likewise if the Moon was in the middle of Taurus, or in the ninth degree of Cancer, or in the first degree of Sagittarius, for the native will have darkness in his eyes."). Nawbakht\'s 73 (the first degrees of Aries, the last of Capricorn) says the child will be sickly, not that the eyes are harmed, and is not a row.'),
                    ("Abu Ma'shar, Gr. Intr. VI.20: the measured places.",
                     'Abu Ma\'shar, Gr. Intr. VI.20, 1-3:\n\n> "The positions in the signs which indicate an ailment of the eyes, are [1] the position of the Pleiades in Taurus, [2] the position of the nebula in Cancer, Scorpio (the position of [3] its leg and the position of [4] its stinger), Sagittarius (the position of [5] the arrows), and Capricorn (the position of [6] the spines). And the position of [7] the pour of water from Aquarius also indicates an eruption in the eyes. But as for Libra and Leo, they both sometimes corrupt the vision as well."\n\nHis longitudes (4-9) differ from Sahl\'s by a few degrees to fourteen, not in one direction (his spines of Capricorn stand before Sahl\'s, the rest after), and 10:\n\n> "these positions which we have stated are their degrees in longitude and latitude in our time period; but their positions must be searched out and measured for every time period, because they move and withdraw from these degrees which we have stated."\n\nNeither table is precessed here: each is applied as printed. Dykes notes (fn 278) that Abu Ma\'shar names the leg where the sting is customary. Libra and Leo (3) carry no degrees and are not rows.'),
                    ("Two spans read from a phrase, and one bare number.",
                     'Each list is read for every point; the point each rule names (the Sun by day, the Moon by night, the Ascendant\'s lord) is shown in the list\'s own sentence and not enforced. In 71, <of Scorpio> is Dykes\'s supplement, used here as the sign. In 72, 15° to 19° is read ordinally as [14°, 19°). Two spans are this app\'s reading of a phrase: 49\'s "having already passed half [of it] until she completes 18°" as 15°00\'-18°00\', and Nawbakht\'s "the middle of Taurus" as the 15th and 16th degrees. 50\'s bare "(and in 23)" is read as the 23rd degree, the sting (fn 75).'),
                    ("Abu Bakr, On Nativities II.7.3: his list, beside the others.",
                     'Abu Bakr, On Nativities II.7.3 (p. 238):\n\n> "And it must be known that in some signs are some degrees which destroy vision: in Taurus, the place of Thurayyā, the sixth, ninth, and tenth degrees. In Cancer, from the ninth degree up to the fifteenth. In Leo, the place of Dafira, the eighteenth degree, the twenty-seventh, and twenty-eighth. In Scorpio, the nineteenth and twenty-eighth. And according to Dorotheus, in Scorpio the eighth degree, the ninth, tenth, and twenty-second. In Sagittarius, the first, seventh, eighth, and ninth degree. In Capricorn, from the twenty-sixth up to the twenty-ninth. In Aquarius, the sixth degree, tenth, and nineteenth."\n\nDykes: "This is the same list as Mash\'allah\'s" (fn 1024, the Book of Aristotle III.6.2), and Dykes, in his Introduction\'s paragraph on the fixed stars, calls the accounts of Dorotheus and Sahl somewhat different from it; this app carries the three lists side by side, each under its own source, and does not reconcile them. Abu Bakr\'s ordinals are read as Sahl\'s are, neighbouring degrees as one span ("the ninth, tenth" of Taurus is 8°00\'-10°00\', "the twenty-seventh, and twenty-eighth" of Leo 26°00\'-28°00\'), and Dorotheus\'s Scorpio degrees, which he gives as a second opinion, are their own rows and say so. The points tested stay the same four -- the Moon, the Sun, the lord of the Ascendant and the Ascendant degree; Abu Bakr\'s own rule sentences in the chapter (the Sun and Moon besieged by the infortunes, the Moon decreased in light in the sixth, the Tail in the degree of the Ascendant, and the rest) are not computed.'),
                ])
        # Abu Bakr's one paragraph on Mars by sect (II.1.0), whose condition
        # is his own domicile -- the sect of the chart decides which of two
        # sentences reaches him. Supplement only, display only; the other
        # planets have no such witness here and are not built.
        st.subheader("Mars in his own domicile, by sect (Abu Bakr)",
                     help="Abu Bakr, On Nativities II.1.0: Mars in his own domicile (Aries, Scorpio) by night, or by day. Display only; nothing scores it.")
        with _prose():
            st.markdown("Abu Bakr, On Nativities II.1.0: Mars in his own domicile (Aries, Scorpio) by night, or by day; Mars in a domicile of Saturn (Capricorn, Aquarius); and, as a second row, Mars in the Midheaven, read as the whole-sign tenth. The sentence for the case is quoted whole; where none reaches him the row says so.")
        st.dataframe(pd.DataFrame(mars_abu_bakr_data), hide_index=True, width='stretch',
                     height=_rows_height(len(mars_abu_bakr_data)),
                     column_config=_wide_text_columns(pd.DataFrame(mars_abu_bakr_data)))
        st.caption("Supplement · display only · Abu Bakr, On Nativities II.1.0. The condition is his own domicile by the sect of the chart, "
                   "not his being of or contrary to the sect at large; the fortune's aspect and \"he would rejoice in his own place\" are not tested.")
        _notes_expander(NOTES_TITLE, [
            ("The paragraph whole.",
             "Abu Bakr, On Nativities II.1.0, the paragraph whole:\n\n> \"" + ABU_BAKR_MARS_II_1_0['Nocturnal'][1] + " "
             + ABU_BAKR_MARS_II_1_0['Diurnal'][1] + " " + ABU_BAKR_MARS_II_1_0['Saturn'][1] + " "
             + ABU_BAKR_MARS_II_1_0['Midheaven'][1] + " " + ABU_BAKR_MARS_II_1_0['Fortune'] + "\""),
            ("Dykes's note on \"unsound\".",
             "Dykes's fn 652, on \"unsound\":\n\n> \"" + ABU_BAKR_MARS_II_1_0['fn652'] + "\""),
            ("This app's reading.",
             "How this app reads it: his own domicile is Aries or Scorpio, a domicile of Saturn Capricorn or Aquarius, by sign; "
             "the nativity's being nocturnal or diurnal is the chart's sect as the Chart page states it. The Midheaven is the "
             "whole-sign tenth, and \"he would rejoice in his own place\" is quoted, not tested -- the text does not say which "
             "place is meant. \"It was already stated\" points back to an earlier passage of the book, not quoted here. The fortune's "
             "aspect on \"a Mars so disposed\" is quoted above and not tested. The paragraph is about Mars alone; no other planet "
             "is read here."),
        ])
        _finding(_gap, "The Moon's phase, Valens's eleven", 'Valens, Anthologies II.36 (Riley)', moon_phase_valens_data,
                  standing="Supplement · display only",
                  glance="Valens's eleven phases of the Moon, the chart's Moon placed in one by its angle ahead of the Sun. Display only; nothing scores it.",
                  summary="Valens's eleven phases of the Moon, the chart's Moon placed in one by its angle ahead of the Sun, with what he says the phase indicates and the planet that adds its influence to the day he names.",
                  qualifications=["The phase is decided on the unrounded angle; the displayed angle is rounded to two decimals.", "**Two independent measures.** The 12° bounds not given by Valens are Abu Ma'shar's phase markers (ITA II.10.5) applied to Valens's phases; the Solar phase row follows the selected Moon-rays reading -- Sahl's 15° or Abu Ma'shar's 12° -- so at 13° the Moon can be both under the rays and in first visibility, each under its own author."],
                  note_sections=[
                      ("Phase boundaries used by this app.",
                       'His degrees are moments; this app reads each phase as running from its own degree to the next one\'s, so the crescent is 45-90, the quarter 90-135, the gibbous 135-180, the second gibbous 225-270, the second quarter 270-315 -- his degrees at both ends. The boundaries he does not give are Abu Ma\'shar\'s markers of the Moon\'s phases (Abbr. II.27-31, in ITA II.10.5), where she changes her property at 12° from the conjunction and from the opposition, applied here to Valens\'s phases: the new moon to 12° after the conjunction and the final visibility from 12° before it, the first visibility from 12° to his 45°, the full moon to 12° after the opposition, and the phase "when it first begins to wane" from there to his second gibbous at 225°, where his "What Each Phase Indicates" puts it, between the full moon and the second gibbous. Abu Ma\'shar\'s fourth marker, 12° before the opposition, is not used: Valens\'s gibbous runs to his 180°. The angle is the Moon\'s longitude less the Sun\'s, counted forward.'),
                      ("Source phase list.",
                       'Valens lists the phases so:\n\n> "1. New moon; 2. First visibility; 3. Next the crescent moon, 45° from the sun; 4. Next the quarter moon at 90°; 5. Next the gibbous moon at 135°; 6. Next the full moon at 180°; 7. Next the second gibbous phase when it is 45° from full, i.e. 225° <from the sun>; 8. Next the second quarter at 270°; 9. Next the second crescent at 315°; 10. Final visibility at 360°; 11. There is another phase as well, when it first begins to wane."'),
                      ("Phase indications.",
                       'What Each Phase Indicates and What Effects It Has, as Riley has it:\n\n> "We will append how the preceding phases are to be taken in casting horoscopes and to which god they belong. '
                       'The new moon is indicative of rank and power, of kingly and despotic dispositions, of all public business concerning cities, of parents, marriages, religion, and of all universal, cosmic matters. The rulers of the new moon, of the latitude, and of the motion are indicative of the same things.\n>\n> '
                       'The first visibility of the moon (which is also called its “light”) and its ruler are indicative of life, occupation, and future wealth; in addition, it strengthens the matters influences by the now moon. The ruler of the “light” indicates the overall influences in the same way that the monthly cycles and the universal cycles are observed by means of the first visibility. Mercury adds its influence until day 4 of the moon’s motion.\n>\n> '
                       'The crescent formation is indicative of nurture and expectations in life, of wives and mothers. Mercury adds its influence until day 8.\n>\n> '
                       'The quarter formation is indicative of injuries, diseases, and violent accidents; also of children, status, and good things to come. Venus is configured with the moon until day 12.\n>\n> '
                       'The gibbous phase is indicative of prosperity, future success, travel, and the affinity of relatives. The sun works with the moon until day 14.\n>\n> '
                       'The full moon is indicative of fame and infamy, of travel and violent events, of those who fall from pre-eminence as well as those who rise from a humble state, of affinities, passions, political opposition, and the affinity of parents. This phase has the color of the sign in the Descendant.\n>\n> '
                       'The first ruler of the waning of the light is indicative of the diminishing of resources, of the chilling of occupations, of those who grow humble and lowly, and of sudden falls. This phase has the same influence as the sign which just follows the Descendant. Mars is its ruler until day 21.\n>\n> '
                       'The second gibbous phase is indicative of travel abroad, of great activities, and of prosperity. It has the same influence as <the IX Place of> the God. Jupiter is its ruler to day 25 of the moon.\n>\n> '
                       'The second quarter phase is indicative of old affairs, of chronic diseases, and of children. It has the same influence as… Saturn is its ruler to day 30.\n>\n> '
                       'The ruler of the last crescent is indicative of a wife’s death, of unemployment or robbery.\n>\n> '
                       'Finally, the last visibility is indicative of chains, imprisonment, secrets, condemnation, and infamy.\n>\n> '
                       'The preceding was the arrangement of the moon’s phases, their relationships with the five gods and the sun in the … angles."'),
                      ("Rulers actually named.",
                       'The Ruler column carries the planet and day only where the sentence names one; the new moon, the full moon, the last crescent and the last visibility have none. "The rulers of the new moon, of the latitude, and of the motion" are not computed.'),
                  ])
        _finding(_gap, "Mercury's phase against the sect",
                  "Firmicus, Mathesis III.7, 7-9 and 26-30 (Dykes's fnn 186, 194)", mercury_phase_sect_data,
                  standing="Supplement · display only",
                  glance="Whether Mercury's phase matches the sect of the chart: a morning star in a diurnal nativity or an evening star in a nocturnal one matches; the other two pairings do not. One row for every chart, in Dykes's words for each case. Display only; nothing scores it.",
                  summary="Mercury's displayed sect follows solar phase, with exact conjunction unassigned; Abū Maʿshar also gives a company rule, shown separately because the text states no precedence.",
                  notes="Firmicus, Mathesis III.7 (Dykes), fn 194, on the figures for the sixth place (26-29): \"In the Figures here I have put the scenarios slightly out of order. In the top row we see the success that comes from Mercury's phase matching that of the chart (morning star-diurnal, evening star-nocturnal). In the second row, mismatches between the phase and sect produce less respected and independent uses of the intellect and skill.\" Fn 186, on the morning star in the second place (7): \"In this case he would be a morning star in a nocturnal chart, so there would be a mismatch between his phase and the sect of the chart.\" The examples: 7-9 for the second place (obscure men; lenders and business men; philologists), 26-30 for the sixth (the greatest fortune from speech, advocacy or business; interpreters, fishermen, sculptors; malign people; those in charge of accounts, banking, granaries, medicines, legal instruments; the scribes of judges). This app reads \"morning star\" as Mercury eastern of the Sun, rising before him, and \"evening star\" as western, the same reading its Solar phase column uses; the sect each phase gives him is Abu Ma'shar's rule, rising before the Sun diurnal and setting after him nocturnal (Gr. Intr. IV.9, in ITA V.11), the rule the Sect table applies. The Reading column gives fn 194's phrase for the matching and the mismatching case. Exact normalized conjunction satisfies neither directional clause in Abu Maʿshar, Gr. Intr. IV.9, 8, so the phase result is unassigned there; Mercury's native diurnal indication remains explanatory evidence. Gr. Intr. IV.9, 10 supplies the separate company indication below, and the text states no precedence between the two rules.")
        _finding(_gap, "Mercury's company and sect",
                  "Abū Maʿshar, Great Introduction IV.9, 10; ITA fn 171", mercury_company_data,
                  standing="Display only; no override",
                  columns=['Companion', 'Relationship', 'Companion sect', 'Company indication', 'Precedence'],
                  glance="Mercury's qualifying planetary company and each companion's sect, displayed separately from the adopted phase result.",
                  summary="Company means same-sign assembly or a connection under the selected relation rule. The Sun is excluded. Every qualifying companion is shown; conflicting indications are retained without a vote or tie-break.")
        def _rhetorius_row(row):
            for _field in ('Planet', 'Condition', 'Status', 'By', 'Chapter', 'Text', 'Exact contact', 'Effectiveness',
                           'Structure intact', 'Friendly-ray relief', 'Dykes interval break'):
                _value = row.get(_field)
                if _value is not None and _value != '' and not (isinstance(_value, float) and _value != _value):
                    st.markdown(f"**{_field}.** {_display_result(_value)}")
            # A siege's ray or body is printed on its own side of the 7 its
            # relief and its siege are read against ("less than 7", Q2): a
            # Venus sextile 6.99999 off printed "Distance: 7.00°" beside her
            # relief (N10, PW's check note 17).
            def _evidence(_field, _k, _v):
                if not isinstance(_v, float):
                    return f"{_k}: {_display_result(_v)}"
                if _k == 'Distance' and _field != 'Contact evidence':
                    return f"{_k}: {verdict_text(_v, 2, bound_sides((RHETORIUS_BESIEGING_DEGREES,)))}°"
                return f"{_k}: {_v:.2f}°"
            for _field in ('Contact evidence', 'Ray evidence', 'Bodily intervention'):
                _items = row.get(_field) or ()
                if _items:
                    st.markdown(f"**{_field}.**\n" + "\n".join(
                        "- " + "; ".join(_evidence(_field, _k, _v) for _k, _v in _item.items())
                        for _item in _items))
        _finding(_gap, "Affliction and fortification after Rhetorius",
                  "Rhetorius Chs. 26-28, 41-42 (Holden)", rhetorius_affliction_data,
                  columns=['Planet', 'Condition', 'By', 'Chapter', 'Text'],
                  detail=_rhetorius_row, detail_key='Condition',
                  standing="Supplement · display only",
                  glance="Rhetorius's definitions of a planet's being harmed (Ch. 27's list, with Ch. 41's besieging) or fortified (Ch. 42's list). Display only; nothing scores it.",
                  summary="Rhetorius's definitions of a planet's being harmed (Ch. 27's list, with Ch. 41's besieging) or fortified (Ch. 42's list), the tested conditions with unresolved results explicitly marked, and Ch. 26's dominance on its own since that chapter ties it to no harm. Each condition is quoted in the text's words and read as the notes say.",
                  qualifications=["The Moon must approach a malefic's body or aspect degree within her day's motion; other approaching planets are confirmed here only within 3° as kollêsis, with their wider limit unspecified and no added sign-boundary exclusion.", 'Relief follows the Latin Great Introduction and al-Qabīsī: a Sun, Jupiter, or Venus sextile or trine ray less than 7° from this planet, without an added between-the-flanks condition; bodily intervention is assessed separately.'],
                  note_sections=[
                      ("Enclosure, intervention and relief.",
                       "Rhetorius Ch. 41's third-ray interruption and Dykes's interval-breaking alternative are separate results. Including a body in the intervening geometry is an app expansion of the ray clause. The Abbreviation's seventh-degree bodily clause supplies no general body-within-seven rule. Figures 101–102 print 23°, although the stated seven-degree flank from 15° would be 22°; the discrepancy is retained."),
                      ("The conditions tested, each with its reading.",
                       "\n".join(f"- **{c['key']}** ({c['chapter']}), \"{c['text']}\": {c.get('reading') or c['untested']}"
                                 for c in RHETORIUS_AFFLICTION_CONDITIONS)),
                      ("Rhetorius's chapters, as Holden has them.",
                       '**Rhetorius Ch. 27 (Holden):**\n\n> "' + RHETORIUS_CH27 + '"\n\n**Rhetorius Ch. 41 (Holden):**\n\n> "' + RHETORIUS_CH41 + '"\n\n'
                       '**Rhetorius Ch. 42 (Holden):**\n\n> "' + RHETORIUS_CH42 + '"\n\n**Rhetorius Ch. 28 (Holden):**\n\n> "' + RHETORIUS_CH28 + '"\n\n'
                       'Holden\'s notes name them: the fifth house and the ninth; the eleventh house.\n\n**Rhetorius Ch. 26 (Holden):**\n\n> "' + RHETORIUS_CH26 + '"\n\n'
                       '**Rhetorius Ch. 34 (Holden), where Ch. 27\'s note sends the word:**\n\n> "' + RHETORIUS_CH34 + '"'),
                      ("The besiegers of an afflicted planet.",
                       "The besiegers of an afflicted planet are the malefics, as the definitions gathered in ITA IV.4.2 have it -- Abbr. IV.21-25: \"And there is another kind of misfortune which is called \u201cenclosure.\u201d But this is twofold. First, with some star between two malevolents or between two rays of malevolents, or if it heads from a malevolent to a malevolent. And likewise concerning the rays.\"; al-Qabisi III.28b (ITA IV.4.2): \"This is if a planet is in some sign, and in addition a bad one or its rays is in front of it, and a bad one or its rays after it.\" Enclosure by the fortunes is its own row: \"And if a planet or sign were besieged by the fortunes, this will be of the more worthy fortunes\" (Gr. Intr. VII.6, in ITA IV.4.2); BW VIII.76: \"[But if a significator is] from the class of being-in-the-middle [between infortunes], it denotes [prison and torture; if between fortunes], a good condition is going to come.\". What loosens a malefic besieging is the Sun or a fortune aspecting the besieged planet by a friendly aspect with fewer than seven degrees between it and the ray (Gr. Intr. VII.6; al-Qabisi III.28b, both in ITA IV.4.2); what breaks an enclosure by the fortunes is a malefic body or ray in the region (Dykes's comment there). Either is said on the row; a besieging is not silently dropped for a third body of another kind."),
                  ])
        _finding(_gap, "Morin's rules for aspects into good and bad houses",
                  'Morin, Astrologia Gallica 21.II.X (Holden, pp. 105-106)', morin_aspects_data,
                  standing="Supplement · display only",
                  glance='Each trine, sextile, square or opposition that a Fortune (Jupiter, Venus) or an Infortune (Saturn, Mars) casts to another planet. Display only; nothing scores it.',
                  summary='Each trine, sextile, square or opposition that a Fortune (Jupiter, Venus) or an Infortune (Saturn, Mars) casts to another planet, read by the kind of ray and the kind of house it falls into -- the whole-sign house of the aspected planet -- with Morin\'s sentence for that case.',
                  qualifications=["This app reads Morin's rays as whole-sign configurations with no orb and uses the aspected planet's whole-sign house; Morin's houses are quadrant divisions.", '**The unfortunate houses, this app\'s reading.** Morin says "the unfortunate houses" without listing them; this app takes the 6th, 8th and 12th as the unfortunate ones and the other nine as fortunate.'],
                  note_sections=[
                      ("The four governing sentences, whole.",
                       'Morin, Astrologia Gallica 21.II.X (Holden, pp. 105-106). The chapter\'s opening names the trine, sextile and semi-sextile as the rays "by nature benefic" and the opposition, square and quincunx as those "by nature malefic"; this app\'s aspect table has the four the ancients used (p. 110), so the two weak rays are not read. The four governing sentences, whole:\n\n> "The distinction should be observed, however, that the favorable rays of benefic planets are more prone to good, and the unfavorable rays are less prone to evil, than is true for the malefic planets."\n\n> "Moreover, a benefic planet\'s favorable rays produce good with ease and in abundance, and cause good in the fortunate houses as well as prevent or mitigate evil in the unfortunate ones, but its unfavorable rays bring difficulties, hindrances, or misfortunes to be surmounted."\n\n> "On the other hand, a malefic planet\'s malefic rays are extremely harmful, causing evil in the unfortunate houses and preventing or spoiling the good in the fortunate ones, unless it rules over the location where the adverse aspect falls, for in that case the aspect produces good in fortunate houses, but this good will be accompanied by violence, evil, or misfortune."\n\n> "And again, the favorable rays indicate something good gained by difficult means; for example, in the horoscope of the king of Sweden, Saturn ruled the second, and its trine to the Sun in the first house indicated great wealth, which he would acquire through war because Mercury, ruler of the seventh, is placed in the second; and in obtaining these things he had good fortune since Jupiter, Mercury, Venus, and the part of fortune were in the second house—and all ruled in turn by Saturn."'),
                      ("The unfortunate houses, this app's reading.",
                       'Morin says "the unfortunate houses" without listing them; this app takes the 6th, 8th and 12th as the unfortunate ones and the other nine as fortunate. The equation with Morin\'s phrase is this app\'s; the three are the tradition\'s difficult averse places, as Dykes\'s note on al-Qabisi III.28\'s "cadent from the Ascendant" has it (ITA IV.4.1 fn 43):\n\n> "That is, being in aversion to it; in a sign which does not aspect the rising sign, particularly the twelfth, eighth, and sixth; the second sign is also cadent from the Ascendant but is not considered as difficult."\n\nWhere one clause covers both kinds of house (a Fortune\'s adverse rays, an Infortune\'s favorable rays) the Rule column repeats the clause and says so.'),
                      ("Quoted but not tested, and what is not read.",
                       'The "unless it rules over the location" exception is quoted, not tested: the table does not look up the ruler of the house. The chapter goes on to make the aspecting planet\'s own house, its celestial state and its rulership part of the judgment; none of that is read here.'),
                  ])
    _absent(_gap)

def page_dignities():
    if not chart_ok:
        _recovery_panel("Dignities and places")
        return
    st.header("Dignities and places")
    _chart_strip(counts_from_the_ascendant=True)
    _sources_scope_line()
    _readings_note()
    st.subheader('Lordship Mapping', help="The domicile, exaltation, triplicity, term (bound), and face ruler of each planet's own degree -- the five essential dignities, read at the planet's own position rather than another point.")
    lordship_list = _lordship_rows()
    st.dataframe(pd.DataFrame(lordship_list), hide_index=True, width='stretch')
    # ---- Sect (Lesson 10) ----------------------------------------
    # The planet's own sect (85's test), its hemisphere, whether it is
    # of the chart's sect, and domain (hayz) under the rule chosen
    # beside the table. The chart's sect itself is the Chart page's
    # header metric.
    st.subheader('Sect', help="Each planet's own sect, whether it stands above the horizon, whether it agrees with the chart's sect (Sahl's testimony 85), and whether it is in its domain (hayz) under the Domain rule chosen beside the table.")
    sect_col, domain_col = st.columns([3, 1])
    with domain_col:
        _reading_radio("Domain (hayz)", DOMAIN_RULE_OPTIONS, "domain_rule", "_domain_rule",
                       help="Gr. Intr. VII.1, 37 / VII.6, 13: sign by gender, hemisphere by sect (Mars: male, "
                            "nocturnal); "
                            "Masha'allah, On Nativities 1.23, 17: gender follows the hemisphere. "
                            "Affects: this table, Dignity Evaluation, Planetary Condition (13, 36); not the "
                            "Revolutions page's PN IV rows. More on the Sources page.")
    with sect_col:
        sect_rows = _sect_table_rows()
        sect_df = pd.DataFrame(_display_rows(sect_rows))
        st.dataframe(sect_df, hide_index=True, width='stretch', height=_rows_height(len(sect_rows)),
                     column_config=_yes_no_columns(sect_df))
    st.markdown("Mercury's displayed sect follows solar phase, with exact conjunction unassigned; Abū Maʿshar also gives a company rule, shown separately because the text states no precedence.")
    st.caption(SECT_CAPTION)
    # One planet's row printed whole: its placement with the Lean and the
    # row's own standing, both PN IV halves, and every entry of its list.
    def _planet_in_house_detail(row):
        _n = len(row['Entries'])
        st.markdown(f"**{row['Planet']} in the {HOUSE_ORDINAL[row['Placed in (WS place)']]} place.** "
                    f"Lean: {_display_result(row['Lean'])} (Net {_display_result(row['Net'])}; {row['Standing']}).")
        st.markdown(f"**If in a suitable condition (PN IV).** {row['If in a suitable condition']}")
        st.markdown(f"**If in a bad condition (PN IV).** {row['If in a bad condition']}")
        st.markdown(f"**Shared PN IV passages.** {_source_text(row['Shared PN IV passages'])}")
        st.markdown(f"**Rhetorius and Firmicus, as the texts state it: {_n} {'entry' if _n == 1 else 'entries'}.**")
        for _entry in row['Entries']:
            st.markdown(_entry)
    st.subheader('Topical Planets in Houses', help="Each planet's whole-sign house placement with the readings for that pairing from two traditions, with both condition halves and shared passages, every entry with its locator.")
    st.caption("The third column is Rhetorius Ch. 57 and Firmicus, Mathesis III, as the texts state it, under each author's own division; the Moon's PN IV reading is VII.8, by her transit, in her own table below; every entry carries its locator.")
    with _prose():
        st.markdown(NATAL_ADAPTATION)
    st.caption(f"{topical_testimony_count(chart_data['planetary_data'], chart_data['ascendant'])} distinct indexed source passages; joint passages count once, not as satisfied predictions.")
    # The readings wrap in st.table; the structural columns stay above.
    # The structural table is selectable (single row, rerun) and stands
    # with the readings and the row's detail in one @st.fragment, the way
    # the tick grids do: a selection reruns this block alone. The
    # selectbox under the table is the state of the detail panel; a row
    # click writes the same key (a new grid selection, seen before the
    # selectbox is drawn, becomes its value), so the pointer and the
    # keyboard reach one panel, which prints the planet's placement with
    # its Lean, both PN IV halves whole, and every entry of its
    # Rhetorius/Firmicus list in full, the entries a long cell left to the
    # detail included.
    @_pinned_fragment
    def _planets_in_houses_block():
        _topical = _topical_rows()
        _event = st.dataframe(pd.DataFrame(_display_rows(_topical), columns=['Planet', 'Placed in (WS place)', 'Lean']),
                              hide_index=True, width='content', height=_rows_height(len(planets_in_houses_data)),
                              on_select="rerun", selection_mode="single-row", key="topical_planets_in_houses_grid")
        _picked = list(_event.selection.rows)
        if _picked != st.session_state.get("_topical_planets_in_houses_last_row"):
            st.session_state["_topical_planets_in_houses_last_row"] = _picked
            if _picked and 0 <= _picked[0] < len(planets_in_houses_data):
                st.session_state["topical_planets_in_houses_detail"] = planets_in_houses_data[_picked[0]]['Planet']
        _detail_selector('Topical Planets in Houses', planets_in_houses_data, 'Planet', _planet_in_house_detail,
                         "Select a planet to read its complete entries and sources")
        with st.expander("Rhetorius / PN IV readings for these placements", expanded=READING_DEPTH == READING_DEPTH_OPTIONS[1]):
            _open = any('Unresolved' in r for r in _topical)
            if _open:
                st.caption("Net here is the Planetary Condition's known subtotal, counting only the testimonies that "
                           "hold under every permitted reading; Unresolved gives how many are left open, because "
                           "Mercury's sect is unassigned or a connection is undecided, and a planet's details give "
                           "its possible totals.")
            # A static table prints a missing number as "nan": Unresolved is
            # text here, blank where nothing is open.
            st.table(pd.DataFrame([{**r, 'Shared PN IV passages': _source_text(r['Shared PN IV passages']),
                                    **({'Unresolved': str(r['Unresolved']) if r['Unresolved'] else ''} if _open else {})}
                                   for r in _display_rows(_topical)],
                                  columns=['Planet', 'Net'] + (['Unresolved'] if _open else [])
                                  + ['Standing', 'If in a suitable condition', 'If in a bad condition',
                                     'Rhetorius and Firmicus, as the texts state it', 'Shared PN IV passages']),
                     hide_index=True)
    _planets_in_houses_block()
    _notes_expander(NOTES_TITLE, [
        ("Which sources each column represents.",
         "The third column, Rhetorius and Firmicus, as the texts state it, is this app's paraphrases of Rhetorius, Astrological Compendium Ch. 57, the significations of the twelve houses, cited by chapter, house and page -- one page, or the pages a reading runs over or folds in (Ch. 57, the sixth, p. 76; the second, pp. 57-61) -- and of Firmicus, Mathesis III.2-III.7 and III.13, the planets in the twelve places, cited by chapter and sentence (III.2, 8): one tradition, but two witnesses, kept apart. The two condition columns, If in a suitable condition and If in a bad condition, are this app's paraphrases of Abu Ma'shar's PN IV Book II chapters on the lord of the year in the houses of the circle (Saturn II.6, Jupiter II.9, Mars II.12, the Sun II.15, Venus II.18, Mercury II.21), applied to natal planets -- that application is this app's reading, not the text's. Every PN IV half has text; the Moon has no Book II houses chapter (II.22, 13 says to judge her in the manner of the rest of the planets, and the translator's note there points to VII.8, her transit through the twelve houses), and her two halves point to her own table below, since VII.8 supplies no condition split. The arrangement is seven planets in twelve places."),
        ("How conditional entries are included.",
         "Neither text divides a planet's reading into well and badly placed; they divide by sect and by conditions, so the column is a list of entries, each under its own author and under the author's own division as he states it -- by day or by night, in sect or out of sect, or unsplit where the sentence makes no such division -- and each keeping every condition its sentence states; an entry whose whole reading rests on a stated configuration is kept whole or left out whole, never trimmed of its conditions. Rhetorius Ch. 57's sentences on the malefics or the benefics in a house are entered for Saturn and Mars, or for Jupiter and Venus, labelled general malefic or general benefic testimony for the class sentences; the four named pairs are joint configurations, indexed under both members as one testimony. Firmicus's portionally is printed after the entry, and is carried from the place's opening sentence where the cited run refers back to it (so put, in this place, in that place); a restated pivot or such a back-reference inherits, while 'in this sign' and 'generally' do not. A planet's own dignity or sign is a placement, not a configuration. Where the two authors disagree, both entries stand. A cell whose entries run past about sixty words prints only the entries that do not rest on a configuration and says how many it left to the row's detail: select a planet's row in the table above the readings and every entry of its list is printed in full beneath it. Named pairs require both planets and their stated configuration; the eighth-house Jupiter–Venus sentence has uncertain Node scope, Jupiter (PN IV II.9, 15) uses a translator-supplied 'not' with a possible 'even if received' reading, and entries stating no reception or affliction condition are identified as such rather than silently assigned one."),
        ("Misplaced, missing and supplemented passages.",
         "Where the translators mark a paragraph as printed under the wrong house -- Rhetorius's second set of third-house paragraphs is the ninth's, and his second set for Saturn, Jupiter, Mars and Mercury in the eleventh is the fifth's -- it serves the house it belongs to and is cited under it; the Sun and Venus paragraphs printed under the third serve the third as well, as the translator's note there says. Dykes's notes to Mathesis III.13 supply Rhetorius's Moon in the fifth and seventh where Firmicus's own sentences are lost, entered as Rhetorius, as summarized by Dykes; Rhetorius's Moon in the sixth, eighth and twelfth is lost in the manuscripts, and his sixth-house transfer of the Sun's sentence to the mother stands for her there. The list holds 355 indexed entries (351 distinct source passages, since the four joint passages are indexed twice): 198 by Rhetorius, 153 by Firmicus and 4 by Dykes's summary; no cell is without one -- a dash, where a cell had none, would be the absence of testimony, not a neutral reading."),
        ("How PN IV is adapted to natal placements.",
         "PN IV Book II's division is the planet's condition -- suitable, received, in his own house, against alien, not received, made unfortunate or retrograde -- with the house among its factors, so the columns are an index to the sentences, not a rule of location: the qualifications stated in each entry control, and where a suitable reading's sentence states no condition (Mercury in the ninth or third, II.21, 8) the entry says so -- condition not explicitly stated -- its condition being inferred from its adverse pair. A paired house cites the pair's sentence and names the sharing; in PN IV, Saturn's four falling places (II.6, 22-24), Jupiter's four places not looking at the Ascendant (II.9, 15-16) and Venus falling from the stakes (II.18, 18) are carried whole beside each house's own sentence, with their premise in the revolution. PN IV's Jupiter II.9, 15 and Venus II.18, 18 appear in Shared PN IV passages; II.9, 16 remains a separate made-unfortunate addition."),
        ("Why both condition readings remain visible.",
         "Neither is chosen for you. The only thing available to choose with is the Net from the Planetary Condition table, and that number is this app's own arithmetic -- Abu Ma'shar enumerates the Gr. Intr. VII.6 conditions, never totals them, gives no weighting and no tie rule. An invented score silently picking one of two classical delineations turns a convenience into a verdict.\n\nThe Net is shown as a **lean** instead, and reads Indeterminate within a margin of one, which is the width of a single testimony: those charts sit one label away from the opposite reading, and should be judged on the condition counts and the labels rather than on the number."),
    ])
    st.subheader("The Moon in the houses — PN IV VII.8, by her transit", help="A natal analogy: VII.8 reads the Moon's transit through the houses, and the natal Moon's own whole-sign house is marked.")
    with _prose():
        st.markdown("A natal analogy: PN IV VII.8 reads the Moon's transit through the houses from the three positions (the Ascendant of the root, the Ascendant of the revolution and the sign of the terminal point), so long as she is in each; it supplies no condition split, so each house has one reading, mixed where the sentence is mixed, and the natal Moon's own whole-sign house is marked.")
        st.markdown("**The text's own reservation.** (From this indication) is the text's own reservation: the Moon's indication alone shows this, and another indication could show otherwise.")
        st.markdown("**The translator's readings.** Where the translator reads \"conflicting\" dreams or simply \"different\", both are given; his reading of \"takes away the same\" in the tenth is marked as his guess; the third's \"some of him and his parents\" is as printed.")
    st.dataframe(pd.DataFrame(moon_in_houses_data), hide_index=True, width='stretch', height=_rows_height(len(moon_in_houses_data)),
                 column_config={'House': st.column_config.TextColumn(width="small"),
                                'Reading': st.column_config.TextColumn(width="large"),
                                'Locator': st.column_config.TextColumn(width="small"),
                                'Natal Moon here': st.column_config.TextColumn(width="small")})
    # One house's row printed whole under the table, in the table's order:
    # the reading, its locator, and the natal marker as the column has it.
    _moon_rows = [{**r, 'House label': f"{HOUSE_ORDINAL[r['House']]} house"
                   + (" (the natal Moon's)" if r['Natal Moon here'] == 'Yes' else "")} for r in moon_in_houses_data]
    def _moon_in_house_detail(row):
        st.markdown(f"**The Moon in the {HOUSE_ORDINAL[row['House']]} house.** {row['Reading']}")
        st.markdown(f"{row['Locator']}. Natal Moon here: {row['Natal Moon here'] or 'No'}.")
    _detail_selector("The Moon in the houses — PN IV VII.8, by her transit", _moon_rows, 'House label', _moon_in_house_detail,
                     "Select a house to read the Moon's transit through it in full")
    st.subheader("Topical House Lords (Masha'allah)", help='For each of the twelve topical houses, its domicile lord\'s own whole-sign placement, and Masha\'allah\'s delineation for that [placed-in, rules] pairing -- the classical way of reading what a house\'s ruler is "doing" elsewhere in the chart.')
    with _prose():
        st.markdown("This grid paraphrases Dykes's printed translation of Sahl's Māshā'allāh passages, marks material variants, doubts and conjectural reconstruction, and assesses the eight explicit topic conditions using the app's stated aspect convention (lord only for the seventh), with separate notes for the other four rows.")
        st.markdown("**This app's implementation.** Whole-sign: an infortune with, square or opposite the house or its lord; a fortune in any aspect or assembly. "
                    "The seventh tests its lord alone; the lord is not counted against itself. The eleventh's 'free of the infortunes and fortunes' "
                    "(On Nativities 11.1, 28) is interpreted by this same convention. The readings remain visible regardless of the assessment; "
                    "the four 'not stated' notes concern the source, not missing chart data.")
    # Averse: the lord sits in the 2nd, 6th, 8th or 12th sign from the
    # house it rules, so it does not see its own place.
    lords_rows = _house_lord_rows()
    _lords_display = pd.DataFrame(_display_rows(lords_rows))
    st.dataframe(_lords_display, hide_index=True, width='content', height=_rows_height(len(lords_rows)),
                 column_config=_yes_no_columns(_lords_display))
    # One lord's row printed whole, in the table's order: the placement,
    # the condition's result and the aversion beside the reading itself.
    _lord_rows = [{**r, **shown, 'Lord': f"Lord of the {HOUSE_ORDINAL[r['Topical House']]}: {r['Domicile Lord']}, "
                                         f"in the {HOUSE_ORDINAL[r['Placed in (WS place)']]} place"}
                  for r, shown in zip(house_lords_data, lords_rows)]
    def _house_lord_detail(row):
        _condition, _text = row[MASHAALLAH_ASSESSMENT_COLUMN], row["Masha'allah Signification"]
        st.markdown(f"**{row['Lord']}.** Stated topic condition — app assessment: {_display_result(_condition)}. Averse to its place: {row['Averse to its place']}.")
        st.markdown(f"**Condition source.** {_display_result(row['Condition source'])}")
        st.markdown(f"**Masha'allah's signification.** {_source_text(_text)}")
        if row['Source detail']:
            st.markdown(_source_text(row['Source detail']))
    _detail_selector("Topical House Lords (Masha'allah)", _lord_rows, 'Lord', _house_lord_detail,
                     "Select a topical house to read its lord's placement and Masha'allah's sentence")
    with st.expander("Masha'allah readings for lord placements", expanded=READING_DEPTH == READING_DEPTH_OPTIONS[1]):
        st.table(pd.DataFrame([{**r, "Masha'allah Signification": _source_text(r["Masha'allah Signification"])} for r in _display_rows(house_lords_data)],
                              columns=['Topical House', 'Domicile Lord', 'Placed in (WS place)', MASHAALLAH_ASSESSMENT_COLUMN, 'Condition source', "Masha'allah Signification", 'Source detail']),
                 hide_index=True)
    _notes_expander(NOTES_TITLE, [
        ("The twelve passages, and the arrangement.",
         'Every cell\'s wording is this app\'s paraphrase of Sahl\'s own sentence for that pairing, from his twelve lords-of-places passages in On Nativities (the lord of the first 1.36, 79-97; the second 2.14, 9-28; the third 3.10, 1-13; the fourth 4.11, 2-23; the fifth 5.1, 78-90; the sixth 6.3.4, 12-23; the seventh 7.1, 205-216; the eighth 8.5, 2-13; the ninth 9.4, 23-34; the tenth 10.2.4, 1-12; the eleventh 11.1, 16-27; the twelfth 12.1, 35-46), with Sahl\'s own conditions kept (if received, if a fortune or an infortune looked at it) and his locator in parentheses after the text. Sahl has a sentence for every one of the 144 pairings, so no cell is empty; the one his translator brackets as illegible (the lord of the fifth in the eighth, On Nativities 5.1, 85) says so and carries the sense of his footnote. The arrangement lays those twelve chapters out as a grid of the lord of each place in each place.'),
        ("Masha'allah's condition, where he states it.",
         'Masha\'allah\'s condition is his own, stated at the end of seven of the twelve lord-of-the-Nth sections:\n\n> "Work in this chapter if the lord of the third and the third [itself] were free of the infortunes, and the fortunes do not witness"\n\n(On Nativities 3.10, 14; likewise 4.11, 24; 6.3.4, 24; 7.1, 217; 9.4, 35; 10.2.4, 13; 12.1, 47). On Nativities 11.1, 28 instead says free of the infortunes and fortunes; it is not the same condition. On Nativities 5.1, 91 has nearly the same words after the fifth\'s list, "if the lord of the fifth and the fifth are both free of the infortunes, and the fortunes do not witness the Lot of children in the houses of the circle, then look at the Lot of children", but there they lead to the Lot of children, not to the list; Dykes is not sure whether the sentence is Masha\'allah\'s or Sahl\'s (fn 49) and reads its "witness" tentatively (fn 50). It is not counted here.'),
    ])
    with st.expander("Planetary Dignity Evaluation (Hellenistic/Rhetorius reconstruction)", expanded=READING_DEPTH == READING_DEPTH_OPTIONS[1]):
        # The statement the score table cannot be read without, before it.
        with _prose():
            st.markdown("**This app's ranking convenience.** The point weights are this app's own ranking convenience -- no source in hand "
                        "totals these conditions. The geometry each test uses is sourced.")
        resolved_dignity = _dignity_rows()
        if any(row.get('Unresolved') for row in resolved_dignity):
            st.caption("Ranking score and Acc hold the known subtotal: a contribution that is left open, because "
                       "Mercury's sect is unassigned, is counted under Unresolved and named in Accidental Conditions. "
                       "Rows with an open contribution are shown after the resolved ranking and are unranked.")
        df_dignity = pd.DataFrame(_display_rows(resolved_dignity))
        # Unresolved is null where nothing is open: drawn empty, not "None".
        st.dataframe(df_dignity, hide_index=True, width='stretch', placeholder="",
                     column_config={'Unresolved': st.column_config.NumberColumn(width="small", format="%d")})
        # The solar-phase thresholds as a method table, built from the
        # constants the evaluators read -- SOLAR_BURNED_ORB, solar_rays_orb()
        # (which applies the Moon's and Mars's readings) and CAZIMI_ORB -- so
        # the page carries no second set of numbers to drift from them.
        def _span(east, west):
            return f"{east:.0f}°" if east == west else f"{east:.0f}° east / {west:.0f}° west"
        _phase_rows = "\n".join(f"| {_planet} | {_span(*_burn)} | {_span(*solar_rays_orb(_planet))} |"
                                for _planet, _burn in SOLAR_BURNED_ORB.items())
        with _prose():
            st.markdown("**Solar phase** follows Abu Ma'shar's walk through the synodic cycle (Gr. Intr. VII.2); Sahl's *On Nativities* "
                        "1.22 and al-Biruni give the under-the-rays figures independently (Sahl states no burn "
                        "boundary; Dykes's table for Sahl has Mars westernizing at 18°, while Sahl's own sentences "
                        "are silent on Mars west):")
        st.markdown("| Planet | Burned within | Under the rays within |\n|---|---|---|\n" + _phase_rows)
        st.caption("The figures shown are those in force under the current readings.")
        with _prose():
            st.markdown(f"In the heart: within {round(CAZIMI_ORB * 60)}' (Gr. Intr. VII.2, 7-9, from the Sun's own apparent diameter). "
                        "Sahl elsewhere says one whole "
                        "degree for the heart, and that reading is used where his own testimonies are "
                        "scored.")
            st.markdown(f"Venus at great latitude is the chapter's own exception: \"when Venus is in this condition of "
                        "great latitude and visibility, she is not called 'burned,' but rather she is called "
                        f"'appearing' until her latitude is below {VENUS_APPEARING_LATITUDE:.0f}°\" (Gr. Intr. VII.2, 39, "
                        "with 38). Under Abu Ma'shar's phases a Venus whose latitude is that or more, where the "
                        "longitude alone would put her in the heart or burned, is shown as Appearing; Sahl's "
                        "chapter states no such exception and his testimonies do not read it.")
            st.markdown(
                f"**Domain/hayz** follows the Domain switch beside the Sect table above, currently {DOMAIN_RULE}: "
                + ("Gr. Intr. VII.1, 37-39 and VII.6, 13 -- the planet's own sect need not match the chart's; "
                   "the hemisphere requirement is what flips with it."
                   if DOMAIN_RULE == DOMAIN_RULE_OPTIONS[0] else
                   "On Nativities 1.23, 17 -- a male planet by day above the earth in a male sign, by "
                   "night under the earth in a female sign; the feminine planets by hemisphere only "
                   "(\"and if it was feminine, by night it is above the earth and by day under the earth\"), "
                   "so a feminine planet in the other hemisphere is contrary to its domain on that one condition. "
                   "Mercury, whom the sentence does not name, is read by his sect by phase (Gr. Intr. IV.9, 8): "
                   "easternizing with the male planets, westernizing with the feminine, so a westernizing Mercury "
                   "in the other hemisphere is contrary on that one condition too -- this app's reading.")
            )

def page_configurations():
    if not chart_ok:
        _recovery_panel("Configurations")
        return
    st.header("Configurations")
    _chart_strip(counts_from_the_ascendant=True)
    _sources_scope_line()
    _readings_note()
    _gap = []
    # The connection rule and the fitting infortune govern tables on every
    # tab, so they stay above the tabs. The three-way view control went on
    # 2026-09-10: the Sources shown reading (Sources page) decides where Abu
    # Ma'shar's tables sit -- a tab of their own under Course text, or
    # beside Sahl's on the same topic under Course text and supplement.
    rule_col, fit_col = st.columns([1.1, 1.9], vertical_alignment="bottom")
    with rule_col:
        # Governs only the dual-author tables; each author's own
        # tables pin their own rule (see doctrine()). The essay
        # comparing the two rules is on the Sources page.
        _reading_radio("Connection test used in the shared tables", CONNECTION_PROFILES.keys(),
                       "connection_rule", "_connection_rule",
                       help="Which author's test decides Connected in the aspects, reception and "
                            "prevented-connections tables. Sahl: the applying planet's own light. "
                            "Abu Ma'shar: 15° in one sign, 12° for aspects. Full comparison on the Sources page.")
    with fit_col:
        _reading_checkbox("Fitting infortune: the malefic that rules the Ascendant is not counted as an infortune (Choices Ch. 1, 12)",
                          "fitting_infortune", "_fitting_infortune",
                          help='Sahl, Choices Ch. 1, 12: "' + FITTING_INFORTUNE_QUOTE + '" '
                               + FITTING_INFORTUNE_STANDING + ' Off by default; full text on the Sources page.')
    st.caption(FITTING_INFORTUNE_STANDING)
    _fitting_slot = st.empty()  # a fixed slot before the tabs (see _readings_note)
    # The sentence that says which tests the reading changes stands where the
    # reading shows, on the in-force line, rather than in the tooltip.
    if FITTING_INFORTUNE:
        _fitting_slot.caption(f"Fitting infortune in force: {SOFTENED_INFORTUNE} rules the Ascendant and is not counted as an infortune. "
                              "When on, that malefic drops out of every 'afflicted by an infortune' test in these tables (Sahl's enclosure, "
                              "strength and weakness 94-95; Abu Ma'shar's 3, 47-50 and enclosure; the Moon's 67-68 and 106)."
                              if SOFTENED_INFORTUNE else "Fitting infortune switched on, but no malefic rules this Ascendant -- nothing changes.")
    supplement = READING_DEPTH == READING_DEPTH_OPTIONS[1]

    def sahl_aspects():
        _finding(_gap, "Aspects, aversions and connections",
                 f"Sahl, The Introduction Ch. 2, 50-60 and Ch. 3, 6-21 — {CONNECTION_PROFILE} rule in force", aspects,
                  columns=['Light Planet', 'Aspect', 'Heavy Planet', 'Connecting planet', 'Motion', 'Orientation', 'Exact Orb Dist', 'Bodies', 'Strength', 'Connection', 'Rules differ'], height=_rows_height(len(aspects)),
                  column_help={
                      'Connecting planet': "Which planet's own motion is closing the aspect, and the one it closes with: "
                                           "the light planet \"connects with\" the slower one (Sahl, The Introduction Ch. 3, 6; "
                                           "Gr. Intr. VII.5, 9). Retrogradation reverses it, and the cause is named in the cell.",
                      'Motion': 'Applying: going straightaway to the connection (Sahl, The Introduction Ch. 3, 6). Recession in Sahl 22 names the light planet in more degrees. Exact and No relative motion are distinct; motion alone does not prove completion.',
                      'Connection': 'Exact — connection completed at contact (Sahl 7; Gr. Intr. VII.5, 9-11). Under a single blanket after established completion: less than half of its body in one sign (Sahl 10), or a full degree across signs (Sahl 9). Separated at either limit. Not yet: configured and approaching outside the entry limit. Ordinary direct separation past the contact establishes completion (Sahl 22). Exceptional motion without encounter evidence is unresolved; a widening gap alone does not suffice.',
                      'Orientation': "Dexter, Dykes's right: the ray cast to earlier degrees of the zodiac; sinister, his "
                                     "left: to later ones (Sahl glossary, Right/left).",
                      'Strength': "A source-backed grade for an assembly from the two bodies and a shared bound (Gr. Intr. VII.4, 5-8). Aspect rows use a dash; their exact angular distance is shown separately.",
                  },
                  caption="Under this app's reading of Sahl, the Sun's 15° counts for same-sign application, and the blanket begins at exactness, ending at the departing light planet's limit or at 1° across signs.",
                  glance='Four separate facts about each pair, kept apart rather than collapsed into one verdict.',
                  summary='**Looking** is the whole-sign configuration (Union/Sextile/Square/Trine/Opposition, or Aversion if none applies) -- sign to sign.',
                  note_sections=[
                      ("The columns, and what each one measures.",
                       "| Column | Meaning |\n"
                       "|---|---|\n"
                       "| Motion, Exact Orb Dist | The degree-to-degree approach |\n"
                       "| Bodies | Whether each planet falls inside the other's sphere of power, which is asymmetric because the spheres differ in size |\n"
                       "| Connection | The active author's verdict, named as his own text names the state |\n"
                       "| Rules differ | The pairs where the two tests disagree |\n"
                       "| Strength | For an assembly only: the source's own grade from whose body reaches whose (Gr. Intr. VII.4, 5-8) and whether they share a bound; aspect rows carry no invented grade |\n"
                       "| Light, Heavy | The standing classes both authors name as nouns (Saturn heaviest through the Moon lightest), not a reading of momentary speed |\n"
                       "| Connecting planet | The separate, directed fact: which one is actually closing the aspect |"),
                      ("Motion, orb and bodies.",
                       "**Motion** and **Exact Orb Dist** are the degree-to-degree approach. **Bodies** is whether each planet falls inside the other's sphere of power, which is asymmetric because the spheres differ in size: Abu Ma'shar, Gr. Intr. VII.4, 7 notes that Saturn sits inside the Moon's body from 12 degrees while she only enters his at a little under 9."),
                      ("Connection, and where the rules differ.",
                       "**Connection** is the active author's verdict, named as his own text names the state -- switch the Connection rule at the top of this page to see where they disagree; **Rules differ** marks the pairs where the two tests disagree."),
                      ("Strength for assemblies; distance for aspects.",
                       "**Strength** is graded only for an assembly, from whose body reaches whose (Gr. Intr. VII.4, 5-8) and whether the planets share a bound. Gr. Intr. VII.5, 4 describes an aspect as progressively weaker farther from its exact degree but supplies no cutoffs; aspect rows therefore show no grade, and **Exact Orb Dist** carries the stated measurement."),
                      ("Light and heavy: the standing classes.",
                       "**Light** and **heavy** are the standing classes both authors name as nouns (Saturn heaviest through the Moon lightest), not a reading of momentary speed: they are fixed, and a planet slowing toward its station does not thereby become heavy."),
                      ("The connecting planet, and retrogradation.",
                       "**Connecting planet** is the separate, directed fact: which one is actually closing the aspect. Normally it is the lighter, and The Introduction Ch. 3, 6 assumes as much (\"a light, quick star is going straightaway to a heavy star ... fewer in degrees than the heavy one\"). The retrograde extension in the Sahl column is attributed to Abu Ma'shar, Gr. Intr. VII.5, 24 (\"the connection of one of them with the other ... will be by retrogradation\"), VII.5, 118 (\"the light one in more degrees goes retrograde and connects with the heavy one\"), and the note on VII.5, 130 (Saturn \"could never be received because he is too slow to connect with anyone, unless by retrogradation\"). The cause is named in this column whenever the heavier planet is the one applying, which happens for about 4% of configured pairs. An aversion row across a sign boundary that names a connecting planet (a body connection, Sahl, The Introduction Ch. 3, 20-21, or what is left of one, 9-10) is marked the same way, so a heavier planet departing over the cusp reads \"(its own motion)\" as it would in one sign. Across the boundary Sahl's 20 is read by his own usage, connecting being the lighter planet's act (The Introduction Ch. 3, 6): where a heavier planet retrogrades away while the lighter one moves on, the lighter one is named, and where the lighter planet retrogrades back onto a heavier one, both close and the lighter one is named, as in one sign. The Motion cell carries no retrogradation there: Abu Ma'shar counts retrogradation \"at the assembly\" (Gr. Intr. VII.5, 24), which this app flags on every configured row, never on an aversion; his planet that retrogrades over a boundary \"enters its sign, and conjoins with it\" (Gr. Intr. VII.5, 121). Out of sign the pair is in aversion, and its Connection is \"–\" unless Sahl's 20 admits their contact by body or what is left of it; where 20 refuses what is left of it, the Strength cell says which of its two conditions does. Reception, transfer, collection, returning, revoking, emptiness of course and enclosure all read this column, not the light/heavy one, though a Type II transfer also needs each leg to run from the lighter planet to the heavier."),
                  ])

    def sahl_connection_group():
        with st.container(border=True):
            st.markdown("**Connection group** — The Introduction Ch. 3, 24-30 and 119-123")
            _finding(_gap, 'Transfer of Light', "Sahl, The Introduction Ch. 3, 24-27; Type II is Gr. Intr. VII.5, 84-85", transfers,
                      glance='A faster "carrier" planet separates from one planet and connects with another, carrying the first planet\'s nature to the second -- Type I is a direct hand-off, Type II is via an intermediate planet already connecting onward.',
                      qualifications=["**One figure, two tables.** A Type II transfer -- \"a light planet connects with a planet slower than itself, and that slow one connects with [yet] another planet\" (Gr. Intr. VII.5, 85) -- is the same three bodies as Sahl's intervention (The Introduction Ch. 3, 35-37, his Fig. 13: the Moon, Mars and Saturn in Gemini), so one figure can stand here as a transfer and under Prevented connections as a blocking. Both are reported. Dykes's note on Gr. Intr. VII.5, 92 draws the line: \"the difference lies in what we want the planets to do\" -- the middle planet carries the matter on to the third, or stands in the way of it, by the question asked."])
            _finding(_gap, 'Collection of Light', 'Sahl, The Introduction Ch. 3, 28-30', collections,
                      glance=COLLECTION_POLICY, columns=['Collector', 'Collects'],
                      detail=lambda r: st.write(_display_rows([r])[0]), detail_key='Collects')
            _finding(_gap, 'Enclosure', 'Sahl, The Introduction Ch. 3, 119-123', enclosure_data,
                      glance='A planet separating from one of the two infortunes (or, per Abu Ma\'shar\'s extension, fortunes) and connecting with the other, with neither leg intercepted by a third planet\'s rays.',
                      summary='A planet separating from one of the two infortunes (or, per Abu Ma\'shar\'s extension, fortunes) and connecting with the other, "without another planet casting its rays between the two" (121): neither leg already blocked, and no third planet\'s sextile, square, trine or opposition ray cast between the two enclosing rays -- graded "more powerful/unfortunate" when both legs are within 7 degrees of exact.')
            _absent(_gap)

    def sahl_handing_over():
        with st.container(border=True):
            st.markdown("**Handing-over group** — The Introduction Ch. 3, 49-76")
            _finding(_gap, 'Handing Over', 'Sahl, The Introduction Ch. 3, 70-76', handing_over_data,
                      glance='Three grades of one phenomenon, per connected pair: Management is the baseline (any connection at all); Power is added when the giving planet is itself in its own house, exaltation, or triplicity; Nature is added when the planet it connects with is the ruler')
            _finding(_gap, f"Reception — {CONNECTION_PROFILE} rule", None, reception_data,
                      glance='Who receives whom, on what dignity, which way round, and how strongly.',
                      summary='Who receives whom, on what dignity, which way round, and how strongly. The two authors differ on every one of those, so the Connection rule at the top of this page governs here too.',
                      qualifications=['**Under Sahl\'s rule.** A pair refused by non-reception Kind II or Kind III is not also listed as received -- refusal wins. On Questions Ch. 1, 63 with 40-41 supplies the worked refusal context. Kind IV and Kind V keep the reception row but mark it brought down, naming whether the receiver is in its own fall or in the applicant\'s fall (62).',
                                      '**An empty table.** An empty table is **not** non-reception -- that is a separate set of hostile configurations, in the table below.'])
            # The notes as a sibling disclosure, so that the source comparison
            # can stand at the page's width (three columns) before the
            # sections at reading width; nothing when the finding is absent.
            if reception_data:
                with st.expander("Sahl and Abu Ma'shar on reception", icon=NOTES_ICON):
                    st.markdown(
                        "| Question | Sahl (The Introduction Ch. 3, 49-55) | Abu Ma'shar (Gr. Intr. VII.5, 129-133) |\n"
                        "|---|---|---|\n"
                        "| Direction | One way only: the connecting planet stands in a dignity of the planet it connects with, and so is received by it | Also in reverse, where the accepting planet sits in the connector's dignity (130) |\n"
                        "| Dignities that count | House or exaltation is perfect reception; triplicity alone ranked below it (50); bound only paired with triplicity (54-55); face never appears | All five dignities count (129); house/exaltation strongest (131); a lone minor dignity weak unless two of bound/triplicity/face combine (132) |\n"
                        "| Connection required | Always | Reception can hold by looking with no connection at all (133) |")
                    _note_sections([
                        ("Sahl's reception (The Introduction Ch. 3, 49-55).",
                         '**Sahl** (The Introduction Ch. 3, 49-55) runs one way only -- the connecting planet stands in a dignity of the planet it connects with, and so is received by it (52: the Moon in Aries connecting with Mars, "he receives her because Aries is his house"). House or exaltation is perfect reception; triplicity alone is expressly ranked below it (50); bound counts only paired with triplicity, which Sahl credits to Masha\'allah (54-55). Face never appears, and a connection is always required.'),
                        ("Abu Ma'shar's reception (Gr. Intr. VII.5, 129-133).",
                         '**Abu Ma\'shar** (Gr. Intr. VII.5, 129-133) is wider on every axis: all five dignities count (129), reception also runs in **reverse** where the accepting planet sits in the connector\'s dignity (130, which exists because Saturn is otherwise too slow to ever be received), house/exaltation is strongest (131), a lone minor dignity is weak unless two of bound/triplicity/face combine into a complete reception (132), and reception can hold by looking with no connection at all (133).'),
                        ("Dignity quality: the local basis.",
                         'He then classes reception a **second** way, and under his rule the table shows both. **Dignity quality** is 129-133, the local basis.'),
                        ("Overall class: 136-142.",
                         '**Triplicity claimant, this app\'s reading:** the first lord of the sect claims; Gr. Intr. V.14, 6\'s second lord is not counted.\n\n**Overall class** is 136-142: "a [2] middling reception is the planets\' reception of each other from the house, exaltation, bound, triplicity, or face" (140) -- house and exaltation included -- while "if two met [together] from this, or each one of them received its associate, it is a strong reception" (141); the natural acceptances of 134-135 are "[3] below that" (142); the Moon received by the Sun (137) and a planet received by Mercury from Virgo (139) are his named strong forms, and the Sun receiving the Moon from the opposition keeps his own word, "detestable" (137). A lone domicile reception is therefore the strongest basis **and** globally middling: both are true, and they are different questions.'),
                        ("Sahl's reception at one remove (56).",
                         'Sahl has two further forms, both under his profile only. 56, **reception at one remove**:\n\n> "if the Moon was connecting with a planet and that planet was connecting with the lord of the house of the Moon or its exaltation, then the Moon is received"\n\n-- the note there calls it "like a transfer of light which indirectly allows for reception." Both legs are read in Sahl\'s directed sense of connecting (6: "going straightaway to ... going towards"), since separating is his separate term at 22.'),
                        ("Sahl's reception after the sign change (57).",
                         '57, **after the sign change**:\n\n> "if the Moon was empty in course, and then she passed over into the next sign and connected with the lord of her first sign (or its exaltation), it is just like reception; and if she connected with a planet other than the lord of her first sign or its exaltation, it undermines her."\n\nBoth halves appear -- the undermining is a finding, not a blank.\n\n"Empty in course" is Sahl\'s own emptiness: Dykes\'s fn 76 on 57 reads "See also 63 below", and 63 says "that is when the Moon is not connecting with any of the planets, and not uniting with one". A Moon still connected is not empty and has no row here -- connected until she is a full degree past a planet (9), or in one sign until half her body past it (10), the same connected set that Wild (111) and Banished (64) read. The "and then" is read as her emptiness lasting until she passes over, so a connection she completes before leaving her sign ends it first: a reading of this app. Abu Ma\'shar\'s later sharpening, that she completes no connection while in her sign (Dykes\'s fn 85 on 63), is his.'),
                    ])
            _finding(_gap, 'Non-reception', 'Sahl, The Introduction Ch. 3, 58-62', non_reception_data,
                      glance="Five named ways a connection is refused rather than received (Sahl, The Introduction Ch. 3, 58-62), a distinct finding from simply lacking reception.",
                      summary="Five named ways a connection is refused rather than received (Sahl, The Introduction Ch. 3, 58-62), a distinct finding from simply lacking reception; the Kind column numbers them and the notes spell each one out.",
                      qualifications=["**Under Sahl's rule.** Kind II and Kind III override any reception for the same pair; On Questions Ch. 1, 63 with 40-41 supplies the worked refusal context. Kind IV and Kind V mark the pair's reception brought down without removing it, with their distinct reasons (62). This app reads Kinds I–III for every connecting pair; the text states them of the Moon or the lord of the Ascendant.",
                                      TRIPLICITY_TESTIMONY_READER],
                      note_sections=[
                          ("Sahl's A -> B model.", "Sahl's A -> B model: A is the connecting (applying) planet, B the planet it connects with."),
                          ("The five kinds.",
                           "- **Kind I (58):** B holds no essential dignity at all at A's position -- B is alien in A's sign, so A is not recognised.\n"
                           "- **Kind II (59-60):** A stands in B's own sign of fall, \"like one who comes to it from the house of its enemies.\"\n"
                           "- **Kind III (61):** A is in its **own** fall and B has no house or exaltation there to rescue it -- \"as though the one asking is offering defeat.\"\n"
                           "- **Kind IV (62):** B is in its own fall, which brings the connection down whatever A's condition.\n"
                           "- **Kind V (62):** B sits in A's own sign of fall; any surviving reception is marked brought down because the receiver stands in the applicant's fall."),
                      ])
            _finding(_gap, 'Returning', 'Sahl, The Introduction Ch. 3, 65-69', returning_data,
                      glance='Manner I: a planet connects with a retrograde planet or one under the rays -- it "returns to it what it accepted," corrupting the question.',
                      notes='Manner II: an angular (faster) planet hands over to a cadent (slower) one -- the matter has a beginning but no end.')
            _absent(_gap)

    def sahl_prevented():
        # The Handy Tables give Lesson 17 ONE table here, headed
        # "Prevented connections" and listing blocking, resistance,
        # cutting #1, escape, revoking and cutting #2 together. This
        # showed them as separate tables, so a student could not lay
        # the app beside the course's own page. Merged on the shape
        # they share -- who is prevented, from what, by whom -- with
        # the source kept per row.
        prevented = _prevented_rows()
        # The Handy Tables' own "Prevented connections" also lists
        # revoking, resistance and escape -- but those are Abu
        # Ma'shar's (VII.5, 117-119), and pulling them in here would
        # put his material inside a Sahl group and undo the author
        # separation. They stay on his side, under Forward-looking
        # conditions. This is a deliberate divergence from the
        # course's single table, and the only one in this grouping.
        with st.container(border=True):
            st.markdown("**Prevented connections** — The Introduction Ch. 3, 31-48, with Abu Ma'shar's two further cuttings")
            # Abu Ma'shar's two further cuttings are a forward search, so an
            # empty table is the end of a bounded search, said with its
            # horizon, and does not join "Not present in this chart" (L5-07
            # of the hostile pass of 2026-10-03; F07's absent= rule).
            _horizon = int(sim['horizon_days'])
            _finding(_gap, 'Prevented connections', "Sahl, The Introduction Ch. 3, 31-48; Gr. Intr. VII.5, 90-94 and 120-125", prevented,
                     absent=(f"Prevented connections: none at the chart, and none of Abu Ma'shar's two further "
                             f"cuttings within {_horizon} days of it; later events were not evaluated."),
                     glance="Ways of stopping a connection before it completes, in one table: Sahl's intervention, nullification and cutting, plus Abu Ma'shar's two further cuttings (Gr. Intr. VII.5, 121-124), which Sahl does not have. His revoking, resistance and escape are in his own section.")
            _finding(_gap, 'Banished', 'Sahl, The Introduction Ch. 3, 64', banishment_data,
                      glance='"The banished planet is the planet which none of the planets connects to" (64) -- a planet outside every live connection, whatever the signs are doing. Each row shows the nearest configured planet and why that is not a connection.',
                      notes='Sahl\'s definition is about **connections** (6-21), not signs: a planet can be in trine by sign with everyone and still be banished if no planet is inside a live connection with it, and it can hold an out-of-sign body connection (20-21) and not be banished at all. Abu Ma\'shar\'s later "wildness" (Gr. Intr. VII.5, 79-82) is a different, whole-sign test -- aversion to every planet -- and has its own table in his view. Dykes\' note on 64 calls Sahl\'s the earlier, less precise form; the two are kept apart rather than one served under both names.')
            _absent(_gap)

    def sahl_strength():
        with st.container(border=True):
            st.markdown("**Strength and weakness** — The Introduction Ch. 3, 77-112")
            st.caption("Sahl's heart of the Sun includes 1° on either side: 87 applies there and 93 does not. "
                       "Abu Ma'shar's solar judgments retain their own heart through 16′.")

            # Each tick grid, with its answer key, its notes and the
            # row detail a selection opens, is one @st.fragment:
            # selecting a row reruns that grid's block alone, the way
            # a wheel control reruns _wheel_block(). Everything the
            # fragment draws is drawn inside _tick_grid, inside its body.
            @_pinned_fragment
            def _strength_grid_block():
                _tick_grid(_gap, 'Strength of the Planets', 'Sahl, The Introduction Ch. 3, 78-88', strength_data,
                           'Strength Testimonies', STRENGTH_COLUMNS,
                           glance="The eleven testimonies of a planet's strength at the time of judgment (Sahl, The Introduction Ch. 3, 78-88), one column per testimony; the answer key under the grid spells each one out in words.",
                           note_sections=[
                               ("Testimonies 78 and 83: two measurements.",
                                'Testimonies 78 and 83 look similar but are different measurements. 78 is whole-sign, narrowed to the six places that **look** at the Ascendant. 83, advancing, is **dynamic** -- read against the Alchabitius quadrant cusps, since the note on 83 says the word means "dynamically angular or succeedent, i.e. by primary motion with respect to the angular axes, and not by whole sign." A planet leaving an angle is withdrawing even while its whole sign is still angular, so the two disagree for about a third of placements.'),
                               ("Sahl's five-degree rule.",
                                '83 also carries Sahl\'s **five-degree rule**:\n\n> "the planet will not be falling from the stake unless it was 5 degrees distant from its rear -- I mean, if the stake was 10 degrees of Aries, then every planet which has less than 5 degrees between it and the stake is truly counted as being in the stake"\n\n(Fifty Aphorisms #44, 88), which he states again in On Nativities Ch. 1.22, 9. This app includes the boundary at exactly five degrees. A planet in that band before one of the four angular degrees is therefore angular, not cadent; the row says so when that is why it qualifies. Sahl states the rule twice for the stakes and once for every house (On Nativities 1.18, 19: "and likewise in all of the houses"); this app reads that as the four stakes only, the course\'s reading, Lesson 3 §4-5, adopted here.'),
                               ("Testimony 88: quarter and sign.",
                                QUADRANT_GENDER_READER + " Testimony 88 requires both the planet's matching-gender quarter and its matching-gender sign; one without the other does not earn the testimony."),
                               ("Testimony 79, and whose triplicity counts.", TRIPLICITY_TESTIMONY_READER),
                               ("Testimony 80 and a station.",
                                'Testimony 80, "direct in course", is withheld from a planet at its station (a speed within '
                                f'{STATION_SPEED_TOLERANCE} degrees a day, this app\'s own figure: Sahl names none), which is '
                                'neither direct nor retrograde; the Motion column of the Revolutions page reads the same '
                                'three states, so one chart cannot be direct here and retrograde there.'),
                               ("Distinct from Planetary Condition.",
                                'Distinct from the Abu Ma\'shar-based Planetary Condition table, which scores a broader, later scheme.'),
                           ])

            @_pinned_fragment
            def _weakness_grid_block():
                _tick_grid(_gap, 'Weakness of the Planets', 'Sahl, The Introduction Ch. 3, 91-100', weakness_data,
                           'Weakness Testimonies', WEAKNESS_COLUMNS,
                           glance="The ten testimonies of a planet's weakness at the time of judgment (Sahl, The Introduction Ch. 3, 91-100), one column per testimony; the answer key under the grid spells each one out in words.",
                           note_sections=[
                               ("The ten, in words.",
                                "The ten (91-100): falling and averse to the Ascendant (the 6th or 12th), retrograde, under the rays, connecting with an infortune by assembly, square or opposition, enclosed between both infortunes, in its own fall, connecting with a falling planet or separating from a would-be receiver, alien (no house, exaltation or triplicity where it sits), with the Node and no latitude, or inverted (in detriment). Distinct from the Abu Ma'shar-based Planetary Condition table in his view, which scores a broader, later scheme."),
                               ("Alien (98), and whose triplicity counts.", TRIPLICITY_TESTIMONY_READER),
                           ])

            _strength_grid_block()
            _weakness_grid_block()
            _ab = ascensional_bands
            _finding(_gap, "The sect light's first triplicity lord by ascensional band -- and the app's generalisation",
                     "Sahl, On Nativities 2.13, 48-51 (fn 189: Carmen I.28, 1-6); Fifty Aphorisms #45, 90-92 with fn 57, as printed and not applied",
                     _ab['rows'] or [{'Refused': _ab['refused']}],
                     glance="Stated for **one** planet, the sect light's first triplicity lord (fn 190), and applied to it in the last column.",
                     summary=("On Nativities 2.13, 48: \"if the first lord of the triplicity of the glowing one is in a stake or what follows it, "
                              "and that is the 15 degrees which follows it, by degrees of ascensions ... it indicates praise and good "
                              "fortune (and what is less [than that] in degrees is preferable)\"; 49 the second 15, \"below the "
                              "first\"; 50 the third, \"the middle of assets\"; 51 \"what is after that in degrees, up to the next "
                              "stake, is of the nativities of the poor\". Stated for **one** planet, the sect light's first triplicity "
                              "lord (fn 190), and applied to it in the last column"
                              + (f" -- here {_ab['first_lord']}: {_ab['judged']['judgment']}" if _ab['judged'] else '') + "."),
                     note_sections=[
                         ("This app's generalisation, an ordinal preference and no score.",
                          "**This app's angular-proximity grade, generalised from Sahl, On Nativities 2.13, 48-51:** the per-planet column "
                          "applies 2.13's distances to every planet, which no text does -- an ordinal preference, no score; "
                          "Aphorism #45 with fn 57 is credited for the universal-band analogy and Carmen I.28 for \"the more that it "
                          "is closer to the degree of the stake, the more elevated\"."),
                         ("Aphorism 45 as printed, and the editor's correction.",
                          "**Aphorism 45 as printed:**\n\n> \"every planet which "
                          "is [distant] from the stake in what follows it, by 15 degrees, is in the situation of one who is in the "
                          "stake; and if it increases [beyond that], then it does not have strength\"\n\n(90-92; the example 10 to 25 "
                          "Aries). Dykes, fn 57: \"misstated here\" -- the source (Carmen I.28, 1-7; On Nativities 2.13, 48-51 \"repeated "
                          "correctly\") measures ascensions. Shown as printed in its own column, not applied; a different rule from "
                          "On Nativities 2.13 (every planet, angular strength, one band) and not harmonised with it; the editor's ascensional "
                          "correction of the aphorism is not applied."),
                         ("Conventions, this app's.",
                          "**Conventions, this app's:** the stake a planet **follows** (zodiacally behind it: On Nativities 2.13 \"what follows it\", Introduction "
                          "2, 33 \"rising up to them\"); oblique ascension at the horizon (the setting degree by the oblique "
                          "descension) and right ascension at the meridian, a split Carmen's single rising instruction does not "
                          "state; the ecliptic degree, latitude ignored; bands end-inclusive at 15, 30 and 45, truncated by the "
                          "next actual stake; the five-degree allowance (Aphorism #44) lies on the other side of the stake and is "
                          "not inherited. Refused where the ascension has no inverse (above the polar circle). The printed Carmen I.28, 3-6 "
                          "(p. 108) has the same four parts band for band; Sahl says \"the first lord\", Carmen \"the lord\"."),
                     ])
            _finding(_gap, 'Right-sidedness, "the spear-bearing of the planets"',
                     'Sahl, On Nativities 2.5, 1-3: a finding table, no score', right_sidedness,
                     standing="Display only",
                     glance=("On Nativities 2.5, 2: a pair in square or sextile, both in their exaltations or houses (or one in each, or one of "
                             "them in one of its shares), each casting rays upon the other -- \"a strong right-sidedness\"."),
                     summary=("On Nativities 2.5, 2: a pair in square or sextile, both in their exaltations or houses (or one in each, or one of "
                              "them in one of its shares), each casting rays upon the other -- \"a strong right-sidedness\"; 3: "
                              "if \"they were not in their houses nor exaltations, but they were both of the sect of the day or the "
                              "sect of the night\", the pair still in square or sextile and each casting rays upon the other -- "
                              "\"also called right-sidedness (though it is below [the first version])\"; 1: especially the diurnal "
                              "planets by day and the nocturnal by night."),
                     note_sections=[
                         ("Readings, this app's.",
                          "Readings, this app's: On Nativities 2.5, 3 states only what replaces 2's dignity clause; its \"they\" are 2's "
                          "two planets, and the rest of 2 -- the square or sextile, and each casting rays upon its "
                          "companion -- is carried into it, so a pair of one sect that does not cast rays is not graded; "
                          "\"casting rays upon its companion\" = the pair is Connected under the Configurations page's "
                          "connection rule, for 2.5, 2 and 2.5, 3 alike; \"one of its shares\" = a triplicity, bound or face held by "
                          "the partner of a planet in its house or exaltation; \"of the sect of the day or ... night\" = both "
                          "planets of one sect, each planet's own sect as the Sect table prints it: Mercury by his phase "
                          "(2.5, 3, \"they were both of the sect of the day or the sect of the night\", excepts no planet, "
                          "and 2.5, 6 names him a right-sider), with the exact conjunction unassigned and the pair's sect "
                          "columns then left open."),
                         ("A second definition, and the witnesses.",
                          "A second stated definition, the honor-guard of "
                          "On Nativities 10.2.1, 10-15, is the next table; no text in hand arbitrates between the two definitions, so both are "
                          "shown and neither enters a score. Rhetorius Chs. 23-25 (the doryphory in three kinds: an "
                          "angular planet in its house or exaltation looked at by another in its own; a planet of the "
                          "sect in another's house looking at an angular luminary, before the Sun and after the Moon; "
                          "the out-of-sect kind; the trine and square stronger than the sextile) and Ch. 53 (what each "
                          "planet's doryphory of the Sun gives) are witnesses to the doctrine and arbitrate neither."),
                     ])
            _finding(_gap, 'The honor-guard, "and it is spear-bearing"',
                     'Ptolemy in Sahl, On Nativities 10.2.1, 10-15: a finding table, no score', honor_guard,
                     standing="Display only",
                     glance=("10: the planets \"formed an honor-guard for [the luminaries] (and that is if the planets were eastern "
                             "from the Sun and western from the Moon)\"."),
                     summary=("10: the planets \"formed an honor-guard for [the luminaries] (and that is if the planets were eastern "
                              "from the Sun and western from the Moon)\"; 10-15 read the luminaries' signs (male or female), their "
                              "stakes, the guards' stakes and whether they look at the luminaries, into ranks from \"an elevated "
                              "king\" to \"weak with toil\" -- the delineation is not pronounced here, the facts are shown."),
                     note_sections=[
                         ("Readings, this app's.",
                          "Readings, this app's: \"eastern from the Sun\" = rising before him (the solar phase's side); "
                          "\"western from the Moon\" = rising after her, by the shorter arc; \"in the stakes\" = the whole-sign "
                          "places 1, 4, 7, 10 (rank is a topic, so the sign-places); \"look at\" = the whole-sign aspect. "
                          "Examples in On Nativities 10.2.7 are not reproduced."),
                     ])
            _finding(_gap, 'Corruption of the Moon', 'Sahl, The Introduction Ch. 3, 103-112', _moon_corruption_rows(),
                      glance="Sahl's own ten defects of the Moon, item [16] of his sixteen -- a different list from Abu Ma'shar's eleven corruptions in the Planetary Condition table.",
                      notes="Sahl's ten (103-112): burned within 12 degrees of the Sun; in her own fall or connecting with a planet in its own fall; approaching the Sun's opposition within 12 degrees; assembled with, square or opposed by an infortune, or enclosed between the two; with the Head or Tail in one sign under 12 degrees; in Gemini or in the sign's last bound; falling from the stakes or connecting with a planet that is, counted by the divisions with the five degrees; in the burned path, the end of Libra and beginning of Scorpio; wild, empty of course; slow, or waning in light.\n\n**Falling (109).** \"The seventh is if she was falling from the stakes or connecting with a planet falling from the stakes\" (109). The text does not say how falling is counted here: in The Introduction Ch. 2, 35 Sahl names the falling places by sign and defines retreat by the same phrase (Ch. 3, 5), which Dykes's Figure 9 in Sahl I draws \"understood dynamically\". This app's reading counts it by the Alchabitius divisions of the nativity with the five degrees, as the Strength of the Planets and Planetary Condition tables count the stakes: \"the planets will not fall from the stakes except after 5°\" (On Nativities 1.22, 9). So the Moon, or a planet she connects with, falls only in the 12th, 3rd, 6th or 9th division, and only when it is more than five degrees before the degree of the stake that division ends at: the Ascendant, the stake of the earth, the seventh or the Midheaven. Within those five degrees it is still in the stake. The divisions, the five degrees counted in longitude, and exactly five degrees counted as within are this app's reading.\n\n**Wild (111).** \"The ninth is if she was wild: and that is empty of course, not connecting with any of the planets\" -- 63's emptiness, \"when the Moon is not connecting with any of the planets, and not uniting with one\". The connected set is Sahl's (9-10), the one Banished (64) reads, and it is the aspects table's only while the Connection rule at the top of this page is Sahl's: a Moon separating from a planet is still connected until she is a full degree past it (9), or in one sign until half her body past it (10), and in one sign she is uniting with it until then; such a Moon is not wild here. Sahl bounds the union by her light, with \"the heavy one in front of the light one, and between the two of them in terms of degrees are 12° and what is less than that: for that is the limit of the assembly\" (Sahl, The Introduction Ch. 2, 51), which is the approach. Past the planet, at exactly 12° she has departed \"by one-half of its body\" and \"is sundered from it\" (10-11), so she is not uniting with it there. Abu Ma'shar's later sharpening, that she completes no connection while in her sign (Dykes's note on 63), is his and is read under his own name in the Planetary Condition table.\n\nAbu Ma'shar's eleven (Gr. Intr. VII.6, 63-74) are not a variant of this list. He has eclipse, the twelfth-part of Saturn or Mars, southern latitude and the ninth house, none of which Sahl lists; Sahl has her own fall, connection with a fallen planet, and wildness, none of which appear there. His list is scored in the Planetary Condition table, this one is not scored anywhere.")
            _absent(_gap)

    def abu_condition():
        with _prose():
            st.markdown("Here the stakes are the Alchabitius divisions with this app's five-degree allowance at the four stakes only, not whole-sign places.")
        st.subheader('Planetary Condition', help="Each planet checked against Abu Ma'shar's conditions in Gr. Intr. VII.6, kept in his own four groups: good fortune (1-20), strength (21-29), weakness (30-46), misfortune (47-62), plus, for the Moon only, his own eleven corruptions (63-74).")
        st.caption("Gr. Intr. VII.6")
        _reading_radio("Gr. Intr. VII.6, 27/45 'eastern/western relative to the Sun'", EASTERN_RULE_OPTIONS,
                       "eastern_rule", "_eastern_rule",
                       help="'hemisphere': the whole half, excluding the rays (VII.2, 2; VII.6, 34). "
                            "'VII.2 band': only the easternizing and westernizing bands (VII.2, 14-31). "
                            "Affects: Planetary Condition (27, 45). Full text on the Sources page.")
        # The qualification the table cannot be read without, above it.
        # Net's Indeterminate band is the engine's abs(net) <= 1, the same
        # margin the Dignities page's Lean reads (copy correction 9a).
        with _prose():
            st.markdown(
                ":orange[**Net and Verdict are this app's heuristic, not Abu Ma'shar's.**] He enumerates these "
                "conditions; he nowhere adds them up, and Gr. Intr. VII.6 gives no weighting and no tie rule. They are kept "
                "beside the Dignities and places page, which prints both the good and the bad Rhetorius/PN IV reading for each "
                "placement and chooses neither, showing this Net as a lean; a Net of −1, 0 or +1 is Indeterminate on both "
                "pages. Read the four counts and the labels themselves in preference to the single number."
            )
            st.markdown(
                f"**Divided-house strength and quarter gender.** {QUADRANT_GENDER_READER} "
                f"{SUN_NINTH_EXCEPTION_READER}"
            )
        condition_ordered = _condition_rows()
        if any(row['Unresolved'] for row in condition_ordered):
            st.caption(CONDITION_UNRESOLVED_READER)
        if any(isinstance(abu_mashar_condition[row['Planet']]['Net'], UnresolvedResult) for row in condition_ordered):
            st.caption("Rows with an unresolved Net are shown after the resolved heuristic ranking and are unranked; "
                       "the row's details give the possible totals and verdicts.")
        df_condition = pd.DataFrame(_display_rows(condition_ordered))
        # Unresolved is null where nothing is open: drawn empty, not "None".
        st.dataframe(df_condition, hide_index=True, width='stretch', height=_rows_height(len(df_condition)),
                     placeholder="",
                     column_config={'Unresolved': st.column_config.NumberColumn(width="small", format="%d")})
        # 46's easternization clause, beside the table that shows it: an
        # interpretation for Venus and Mercury, unresolved for the Moon.
        st.caption(VII6_46_INTERPRETATION_READER)
        # The rows in the order the table displays them (its index after the
        # sort is the row list's positions), so the selectbox lists the
        # planets as the table does.
        condition_shown = condition_ordered
        # One planet's row in words: the four counts (and the Moon's own),
        # Net and Verdict on one line, then the evaluator's own label lists
        # as bullets under the table's two label headings -- the arrays as
        # the engine holds them, never the joined cell split on its commas.
        def _condition_detail(row):
            cond = abu_mashar_condition[row['Planet']]
            # The engine's own counts, not the table's resolved subtotals, so
            # an open count prints its possible totals here.
            counts = (f"Good Fortune {_display_result(cond['Good Fortune'])} · Strength {_display_result(cond['Strength'])} · "
                      f"Weakness {_display_result(cond['Weakness'])} · Misfortune {_display_result(cond['Misfortune'])}"
                      + (f" · Moon Defects {_display_result(cond['Moon Defects'])}"
                         if is_unresolved(cond['Moon Defects']) or cond['Moon Defects'] else "")
                      + f" · Net {_display_result(cond['Net'])} · Verdict {_display_result(cond['Condition'])}")
            st.markdown(f"**{row['Planet']}.** {counts}")
            for heading, labels in (("Good Fortune / Strength", list(cond['Positive Labels']) +
                                     [_display_result(value) for value in cond.get('Unresolved Positive Labels', ())] +
                                     [_display_result(value) for value in cond.get('Not Computed Labels', ())]),
                                    ("Weakness / Misfortune", list(cond['Negative Labels']) +
                                     [_display_result(value) for value in cond.get('Unresolved Negative Labels', ())])):
                st.markdown(f"**{heading}**\n\n" + ("\n".join(f"- {label}" for label in labels) if labels else "-"))
            if row['Planet'] in ('Venus', 'Mercury', 'Moon'):
                st.caption(VII6_46_INTERPRETATION_READER)
        _detail_selector('Planetary Condition', condition_shown, 'Planet', _condition_detail,
                         "Select a planet to read its conditions in words")
        _notes_expander(NOTES_TITLE, [
            ("The two Moon checklists.",
             "The Moon's eleven corruptions (63-74) are shown as their own count rather than folded in with the rest. Sahl's ten (The Introduction Ch. 3, 103-112) are a different list, not a variant reading of this one, and have their own table, Corruption of the Moon, in the Sahl view: Abu Ma'shar has eclipse, the twelfth-part of Saturn or Mars, southern latitude and the ninth house, none of which Sahl lists; Sahl has her own fall, connection with a fallen planet, and wildness, none of which appear here."),
            ("How this app's count is formed.",
             "The four counts and the labels are the report. **Net** and **Verdict** are a convenience of this app and **not** Abu Ma'shar's: he enumerates the conditions but never totals them, and the chapter supplies no weighting and no rule for ties. They are kept because Topical Planets in Houses on the Dignities and places page prints both the good and the bad reading for every placement and chooses neither: this Net is shown there as a lean, and a Net of −1, 0 or +1 is Indeterminate in both places.\n\nTwo distortions in the raw count are corrected so that one fact cannot vote repeatedly: the Moon's eleven corruptions contribute a single entry (as their own checklist they had been dragging her to a Bad verdict about three times as often as any other planet), and multiple reception rows for one planet likewise count once; the Sun's reception of the Moon from the opposition, which Abu Ma'shar calls detestable, counts once against each of them, under Weakness."),
            ("Slow in course (31) and the stations.",
             f"31's \"slow in course\" is read of a direct planet only, one travelling less than its mean motion "
             f"(for Venus and Mercury the Sun's that day, Gr. Intr. VII.1, 29-31): a planet within {STATION_SPEED_TOLERANCE} "
             "degrees a day of rest is at a station and counts at 24 or 32, not at 31, and a retrograde one at 33. "
             "Gr. Intr. VII.6 lists the three apart and does not say whether they overlap; keeping them apart is this app's reading."),
            ("Rising in the circle of the apogee (23).",
             "23: \"Or they are rising up in the circle of their apogee.\" Gr. Intr. VII.1, 10 has a planet rising there when it is "
             "at the top of its apogee or less than 90 degrees from it on either side. This app does not compute the "
             "circle of the apogee: it reads 23 for the Sun alone, by distance from the earth, counting him when he "
             "stands farther from the earth than the middle of his range. That distance is a modern stand-in for "
             "the circle of the apogee, and the condition's label says it is approximated."),
            # Gr. Intr. VII.1, 17, 19 and 22 (Gr. Intr. p. 409), read on the
            # photograph; the Sun alone by distance, the six others not computed.
            ("23, and 9's increase in light by distance: the Sun only.",
             "The distance reading above is used for the Sun alone: his model has no epicycle, so his distance from "
             "the earth follows his place in the circle of his apogee. It gives his increase in light in 9 as well, "
             "which Gr. Intr. VII.1, 19 sets in the same circle: \"if it was falling down from the middle zone of the "
             "circle of the apogee, it is increasing in light and size\" (17: rising from it, \"it is decreasing in "
             "light\"). So the Sun, when swift, counts at 9 by standing nearer the earth than the middle of his range, "
             "and never together with 23. For the five planets and the Moon no source text gives where their apogees "
             "lie, and the translator's own apogee tables are not used here, so 23 is shown for them as not computed; "
             "for the five, Gr. Intr. VII.1, 16, 18 and 21 also make the distance the epicycle's work, so it cannot "
             "stand in. The five's increase in light rests on the same circle, so for a swift planet of the five 9 is "
             "shown as not computed too; the Moon's increase in light is her glow. What is not computed counts in "
             "none of the four counts, Net or the Verdict. Gr. Intr. VII.1, 22 also has the three superiors "
             "increasing in light from their meeting with the Sun until they oppose him, \"except that the first "
             "[way] which we stated previously is the one agreed upon [by all]\"; this app keeps the agreed way."),
            ("The divided-house classification in 26 and 39.",
             "Gr. Intr. VII.6, 26 and 39 are the positive and negative sides of one divided-house classification. Both use the Alchabitius division after the five-degree allowance at the four stakes; the boundary is included. " + QUADRANT_GENDER_READER + " Dykes's fn 231 also leaves a whole-sign reading of 39 open; that editorial alternative is preserved here as a note rather than mixed into this evaluator. " + SUN_NINTH_EXCEPTION_READER),
            ("Enclosure under this source.",
             "Enclosure here is Abu Ma'shar's own (56-62) -- by degree within 7 degrees either side counting rays as well as bodies, by sign in the 2nd and 12th, or separating from one encloser and connecting with the other -- and it can be **dissolved**: the degree type when the Sun or a fortune casts a ray within 7 degrees of the enclosed planet (60), the sign type by any look from them (61). The standalone Enclosure table in the Connection group of the Sahl view is Sahl's separate version.\n\nThe by-sign type counts an encloser's **rays** as well as its body, which is what 58 says twice. Be aware that this makes it common: it fires on roughly 43% of placements, because a planet's rays reach eight of the twelve signs. Counting bodies only would make it rare (about 2% of placements), but that is not what 58 says, and this app does not offer it."),
        ])

    def abu_natural():
        _finding(_gap, 'Natural connections', "Gr. Intr. VII.5, 53-77", natural_connections,
                  columns=['Pair', 'Family', 'Degrees', 'From exact', 'Motion', 'Affinity (76-77)', 'Ordinary aspect', 'Standing'],
                  glance='A relation of its own, not an aspect and not a dignity: the Ordinary aspect column keeps saying Aversion where that is what the signs are.',
                  summary='"Another type of connection and separation [even] without the planets\' looking at each other" (53): pairs standing in signs of equal ascensions (56) or of equal daylight (67-75), whose degrees correspond as complements within the sign -- 12 Gemini to 18 Capricorn (62). A relation of its own, not an aspect and not a dignity: the Ordinary aspect column keeps saying Aversion where that is what the signs are.',
                  note_sections=[
                      ("Equal ascensions (56), and equal daylight (67-75).",
                       '**Equal ascensions** (56): "Aries and Pisces, Taurus and Aquarius, Gemini and Capricorn, Cancer and Sagittarius, Leo and Scorpio, and Virgo and Libra." **Equal daylight** (67-75), the antiscia: Gemini-Cancer, Taurus-Leo, Aries-Virgo, Libra-Pisces, Sagittarius-Capricorn, exactly as he lists them -- Aquarius-Scorpio completes the standard scheme but is not enumerated here and is not added (see the coverage note on the Sources page).'),
                      ("Degrees, and the motion read from both speeds.",
                       '**Degrees**: "when a planet is in the first degree of Aries, then it is in the nature of a planet which is at the last degree of Pisces" (57); "the planet which is in 12° of Gemini is in the nature of the degree of the planet which is in 18° of Capricorn: so when it passes beyond 12° of Gemini, then it has separated from it" (62). So the counterpart degree runs backwards as the planet runs forwards, and **motion** is read from both speeds together. He gives no orb: every planet in Aries is in the nature of some degree of Pisces, so every pair in a listed sign pair is shown with its distance from exact.'),
                      ("Affinity (76-77).",
                       '**Affinity**: 76-77 single out four pairs of each family as bridging an ordinary aversion -- Gemini-Capricorn, Sagittarius-Cancer, Aries-Virgo, Libra-Pisces "is called a natural connection by opposition" (76); Gemini-Cancer, Virgo-Libra, Sagittarius-Capricorn, Pisces-Aries "the natural connection by sextile" (77). The notes there record that he omits Aries-Scorpio, Taurus-Libra and Aquarius-Capricorn; they are not added.'),
                      ("The same pairs in the Reception table.",
                       'The same sign pairs are one of 134\'s four bases of acceptance, in the Reception table under his rule.'),
                  ])

    def abu_wildness():
        _finding(_gap, 'Wildness', "Gr. Intr. VII.5, 79-82", wildness_data,
                  glance='A planet in whole-sign Aversion to all six other classical planets -- "in a sign such that absolutely no planet looks at it" (79) -- though it may still be "reached" via the lord of whatever bound it occupies (80-81).',
                  notes='Whole-sign and independent of degree. Sahl\'s "banished" (The Introduction Ch. 3, 64) is a different test, about live connections rather than signs, and has its own table in his view.')

    def abu_reflection():
        _finding(_gap, 'Reflection of Light', "Gr. Intr. VII.5, 87-89", reflections,
                  glance="Type I: an averse collection pair with the collector looking onward. Type II: transfer between planets not looking at each other, or both separating (Gr. Intr. VII.5, 89).",
                  notes="Sentence 88 is itself the aversion case (note 170); note 171 narrows 89 to planets in aversion, where the sentence also admits two that are both separating, as Type II here does. Type I here tests detected collections and the collector's ray destinations; looking-only arrangements outside collection are not tested.")

    def abu_favor():
        _finding(_gap, 'Favor & Recompense', "Gr. Intr. VII.5, 126-128", favor_recompense_data,
                  glance=f'A planet in its own Fall or a welled/pitted degree, pulled out of that weak condition by a connecting dispositor (Favor). Recompense is the same planet later returning the favor, searched for {FAVOR_SEARCH_DAYS} days ahead; none found by then is none within that horizon, not an absence.')

    def abu_rays():
        _finding(_gap, "Rays cast by ascensions (Ptolemy's method as reported by Abu Ma'shar, Gr. Intr. VII.7)",
                  "Gr. Intr. VII.7, 1-22", rays_by_ascension_data,
                  glance="Where each planet's sextile, square and trine rays fall once the ascensions of this latitude are taken into account, beside the zodiacal aspect the rest of these tables use. A static quantity of the chart, not a direction; VII.7, 1-2 attributes the method to Ptolemy. Nothing else reads it yet.",
                  notes="Gr. Intr. VII.7, 3-13: the planet's distance from the nearest stake in seasonal hours, from the right ascensions and the hourly times of its degree (or of the opposite degree on the nocturnal side). 14-15: two candidate ray positions, one from the right ascensions, one from the ascensions of the city (fn 252: the oblique ascensions). 16-19: when they differ, a sixth of the excess for every hour of distance is added to the candidate **nearest** the planet (left rays); 20-21: for right rays the same, to the more **distant** candidate. The nearest/distant flip is in the text and unexplained; this app takes it as written. 22: \"as for the opposition, [a planet] casts its ray into the opposition of its sign, in the same degree and minute.\" The tables the chapter presupposes (fn 250-251) are computed from the obliquity and the latitude.",
                  height=_rows_height(len(rays_by_ascension_data)))

    def abu_book_v():
        _finding(_gap, 'Book V degrees', "Gr. Intr. V.22, Figs. 63-64", book_v_degrees_data,
                  standing="Supplement · display only",
                  glance='Two degree tables from Gr. Intr. Book V that no condition in VII.6 reads. Shown when a named point falls in one; never scored.',
                  summary='Two degree tables from Gr. Intr. Book V that no condition in VII.6 reads: the seven "degrees increasing in good fortune" (for the Moon, the Lot of Fortune and the Ascendant) and the thirty-one "degrees of elevation and power" (for the Ascendant and the luminary of the sect). Shown when a named point falls in one; never scored.',
                  qualifications=['**Sahl\'s own table of the second rule.** Sahl states the second rule with a table of his own (On Nativities 1.38, 39-41, Figure 57), eight signs to Figure 64\'s twelve, six of the eight disagreeing; his is on the Chart page, and both are on the Reference tables page.'],
                  note_sections=[
                      ("Gr. Intr. V.22, 1-2 and 4, the sentences.",
                       'Gr. Intr. V.22, 1-2:\n\n> "when planets indicate the native\'s good fortune by means of their positions, and the Moon or the Lot of Fortune is in these degrees, or [these degrees] are exactly on the Ascendant, then they will increase in the native\'s good fortune. And if they indicate downfall, then these will instigate some motion towards high rank and power."\n\nGr. Intr. V.22, 4:\n\n> "if the Ascendant was one of these degrees ... or the Sun by day or the Moon by night was in one of them, and they were in an excellent position of the circle, and the planets of the root of the nativity indicated good fortune, then they will make him attain nobility and the houses of kings."'),
                      ("Ordinal degrees, and the degrees in both tables.",
                       'Ordinal degrees, as in the wells. The 5th degree of Leo and the 20th of Aquarius are in both tables; the 17th of Aquarius is a degree of elevation and a well.'),
                  ])

    def abu_forward():
        # The horizon is the simulation's own, not a number retyped here:
        # every sentence on this finding -- including the one printed when
        # it has no rows at all (F07) -- says the same number the search
        # actually ran to.
        _horizon = int(sim['horizon_days'])
        _finding(_gap, 'Forward-Looking Conditions', f'Revoking, Resistance, Escape — next {_horizon} days', forward_looking_data,
                  absent=f"No qualifying event found within {_horizon} days of the chart; later events were not evaluated.",
                  glance=f'Conditions describing what happens as the chart moves forward in time (up to ~{_horizon} days), not the birth moment alone.',
                  note_sections=[
                      ("An ordered sequence, against the ephemeris.",
                       f'Each chapter prescribes an **ordered sequence** of events, and a row appears only when every step in that sequence actually occurs against the ephemeris -- the day columns show when. A condition not found inside {_horizon} days is reported as not found, never as a negative finding.'),
                      ("Revoking (117).",
                       '**Revoking** (117): "a planet is connecting with a planet, but before it reaches it, it retrogrades away from it." The window is now birth to the applicant\'s first station: perfection inside it means nothing was revoked.'),
                      ("Resistance (118).",
                       '**Resistance** (118): a light planet ahead of a heavier one by degree stations retrograde, reaches that heavier one **by retrogradation**, goes past it, and a third planet lighter still -- one that wanted the heavy planet -- meets the retrograde one instead. All five steps are required and timed.'),
                      ("Escape (119).",
                       '**Escape** (119): the planet being applied to leaves its sign first; the applicant then follows across the **same** boundary on its own next crossing, and is captured by a body it meets in the new sign. Dykes\' note on Fig. 139 is the picture: Mercury slips from Virgo into Libra, Venus follows, and Saturn\'s body catches her there.'),
                  ])

    def abu_block(parts):
        with st.container(border=True):
            st.markdown("**Gr. Intr. VII.5-6** (supplement)")
            for part in parts:
                part()
            _absent(_gap)

    # --- Five chapters, or four with the supplement laid beside the text ---
    # In the page's own order: the aspects and the connection group;
    # handing over and reception; the prevented connections; strength
    # and weakness. Abu Ma'shar's tables join the topic they belong to
    # when the depth says so -- his natural connections, wildness,
    # reflection and rays with the aspects; favor and recompense with
    # reception; revoking, resistance and escape with the prevented
    # connections (the Handy Tables' own grouping for Lesson 17, kept
    # in his own bordered block so the author separation stands); his
    # planetary condition and Book V degrees with strength and weakness.
    _labels = ["Aspects & Connections", "Handing Over & Reception", "Prevented Connections",
               "Strength & Weakness"] + ([] if supplement else ["Abu Ma'shar (Supplement)"])
    # Client-side tabs (owner, 2026-09-10, third pass): no key, no
    # rerun. A click switches instantly, and the frontend keeps the
    # chapter across reruns caused by other controls on the page;
    # leaving the page and coming back opens the first chapter. The
    # earlier version remembered the chapter across pages by rerunning
    # the whole script on every click, which the owner saw as a
    # flicker. To have the memory back at the price of the rerun:
    # key=, on_change set to rerun, default=_reading(...) and _persist().
    _tabs = st.tabs(_labels)
    with _tabs[0]:
        sahl_aspects()
        sahl_connection_group()
        if supplement:
            abu_block([abu_natural, abu_wildness, abu_reflection, abu_rays])
    with _tabs[1]:
        sahl_handing_over()
        if supplement:
            abu_block([abu_favor])
    with _tabs[2]:
        sahl_prevented()
        if supplement:
            abu_block([abu_forward])
    with _tabs[3]:
        sahl_strength()
        if supplement:
            abu_block([abu_condition, abu_book_v])
    if not supplement:
        # The Book V degrees stay behind the supplement (owner,
        # 2026-09-13): Sahl's own table of the second rule is on the
        # Chart page, and the tab here is the course text's.
        with _tabs[4]:
            abu_block([abu_condition, abu_natural, abu_wildness, abu_reflection, abu_favor, abu_rays,
                       abu_forward])
    _absent(_gap)

def page_lots():
    if not chart_ok:
        _recovery_panel("Lots")
        return
    st.header("Lots")
    _chart_strip(counts_from_the_ascendant=True)
    _sources_scope_line()
    _readings_note()
    st.subheader('Classical Lots', help='Lots: sect-dependent formulas combining two planets or points with the Ascendant to derive a new sensitive degree tied to a specific topic (e.g. Fortune = body/livelihood, Spirit = mind/action).')
    # Formula from the same LOT_DEFINITIONS text the Topical Lots
    # table carries (via calculate_topical_lots), so the two cannot
    # differ; Basis has no definition row and says so.
    classical_rows = _classical_lot_rows()
    st.dataframe(pd.DataFrame(classical_rows), hide_index=True, width='stretch', height=_rows_height(len(classical_rows)),
                 column_config=_wide_text_columns(pd.DataFrame(classical_rows)))
    # The key: each classical Lot's formula (the table's own cell) against
    # where the sources state it, then the paragraph the key was built from.
    _stated_where = {
        'Lot of Fortune': "Stated in Sahl",
        'Lot of Exaltation': "Stated in Sahl",
        'Lot of Spirit': "Gr. Intr. VIII.3, 28-29 -- the Lot of the Invisible, which Sahl names",
        'Lot of Basis': "Gr. Intr. VIII.4, 22-24, the Lot of firmness and survival, the Lot of the Ascendant's support (fn 67: the Greek Basis)",
    }
    _classical_key = "| Lot | Formula | Stated where |\n|---|---|---|\n" + "\n".join(
        f"| {r['Lot Name']} | {r['Formula']} | {_stated_where[r['Lot Name']]} |" for r in classical_rows)
    with st.expander("Where the four classical Lots are stated", icon=NOTES_ICON):
        st.markdown(_classical_key)
        _note_sections([
            ("The four, in the sources' words.",
             'Fortune and Exaltation are stated in Sahl. Spirit -- the Lot of the Invisible, which Sahl names -- is stated at Gr. Intr. VIII.3, 28-29: by day from the Moon to the Sun, by night the reverse, from the Ascendant. Basis is stated at Gr. Intr. VIII.4, 22-24 as the Lot of firmness and survival, the Lot of the Ascendant\'s support (fn 67: the Greek Basis): by day from Fortune to the Invisible, by night the contrary, from the Ascendant -- the same construction as Sahl\'s Lot of passion (On Nativities 7.1, 141) and Abu Ma\'shar\'s Lot of Venus, with which VIII.4, 24 says it coincides. All four carry their provenance under Provenance and standing per Lot, below the Topical Lots table.'),
        ])
    # One heading at both depths, the one the export files the table under;
    # what the supplement adds is said in the caption over the table (the
    # re-pass of 2026-10-04, L5-10: the heading had carried it, and the
    # export a heading no page showed).
    st.subheader(TOPICAL_LOTS_HEADING, help="Sahl's topical Lots, each with its own provenance. He gives several of them **more than once**, with formulas that genuinely conflict, and Dykes's apparatus does not silently reconcile them -- so neither does this table.")
    _reading_radio("House-based Lot construction", LOT_HOUSE_CUSP_OPTIONS, "lot_house_cusp", "_lot_house_cusp",
                   default=LOT_HOUSE_CUSP_OPTIONS[0],
                   format_func=lambda value: ("Calculated cusp — Abū Maʿshar's construction" if value == LOT_HOUSE_CUSP_OPTIONS[1]
                                              else "Whole-sign places — 0° convention (default)"),
                   help=LOT_CONSTRUCTION_STANDING + " " + LOT_WHOLE_SIGN_HELP + " " + LOT_CUSP_HELP +
                        " Alchabitius is this app's cusp calculation. Affects the house-based Lots whose source is silent, on every page, wheel and export.")
    st.caption(("Three rows are Abu Ma'shar's. " if READING_DEPTH == READING_DEPTH_OPTIONS[1] else "")
               + "House/place passages: Sahl, On Nativities 2.15, 1; 8.6, 1; Ch. 9, 9.")
    # Fortune, Spirit and Exaltation are in the Classical Lots table
    # above, with the same Formula; the provenance columns are in the
    # expander so the table itself is the worksheet.
    # A row flagged Supplement (Abu Ma'shar's: a form of a Lot Sahl also
    # gives, or a Lot of his Sahl has not) is shown only under Course text and supplement.
    topical_rows = _topical_lot_rows()
    st.dataframe(pd.DataFrame(_display_rows(topical_rows), columns=list(LOT_WORKSHEET_COLUMNS)),
                 hide_index=True, width='stretch', height=_rows_height(len(topical_rows)))
    st.markdown(f'> “{FATHER_SUBSTITUTION_TEXT}” — Sahl, On Nativities 4.14, 2.')
    st.caption(FATHER_CONDITION_READING + '. ' + FATHER_NIGHT_POLICY + '.')
    # The four classical Lots keep their POSITIONS out of the table above --
    # they have their own table at the top of this page -- but their
    # provenance belongs here, which is where the classical note sends the
    # reader (F11), and their definitions carry the same three fields every
    # other Lot's does. Nothing new is written for them.
    provenance_rows = _lot_provenance_rows()
    # One Lot's provenance read whole -- its standing, source and editor's
    # note -- from the same rows the comparison table prints, which stays
    # in its expander as the secondary view.
    def _lot_provenance_detail(row):
        st.markdown(f"**{row['Topic']}: {row['Lot']}.**")
        for _field in ('Status', 'Standing', 'Source', 'Editor’s note'):
            if row.get(_field) is not None:
                st.markdown(f"**{_field}.** {_display_result(row[_field])}")
    _detail_selector("Provenance and standing per Lot", provenance_rows, 'Lot', _lot_provenance_detail,
                     "Select a Lot to read its standing, source and editor's note")
    with st.expander("Provenance and standing per Lot"):
        st.table(pd.DataFrame(_display_rows(provenance_rows), columns=list(LOT_PROVENANCE_COLUMNS)),
                 hide_index=True)

    _notes_expander("How the standings are recorded", [
        ("The Standing column.",
         'The **Standing** column records his editorial position in his own words where he states one. Every formula is taken from the running prose or a footnote, never from one of the summary tables.'),
        ("Four kinds of case.",
         '- **Sahl himself rules:** of the two sibling Lots, "both of the Lots are correct, so work with them both together" (On Nativities 3.11, 4) -- neither is subordinate.\n'
         '- **Dykes names his choice:** of the three witnesses to the Lot of enemies, "I have used M here"; on the night reversal of the Saturn-Moon work Lot, "Paul instructs us to reverse it by night, but Abu Ma\'shar says not to. We should follow Paul."\n'
         '- **Dykes marks one standard:** on children, "the usual calculation ... is that of Hermes."\n'
         '- **Dykes only tabulates:** three Lots for work, after noting that "Sahl quietly switches to Masha\'allah\'s treatise on Lots ... without telling us that the formula is different."'),
        ("The Lot of death: a stated rule with a manuscript variant.",
         'The Lot of death is projected from Saturn: **stated** by Abu Ma\'shar (Gr. Intr. VIII.4, 226; VIII.6, 69), and Sahl, On Nativities 8.6, 1 as printed agrees, his manuscripts reading the Ascendant (fn 89, with Masha\'allah\'s manuscripts and Dorotheus for Saturn). A stated rule with a manuscript variant: the rule is not an emendation, but Sahl\'s printed sentence is one, Dykes reading Saturn with Masha\'allah\'s manuscripts for the "Ascendant" of Sahl\'s (fn 89).'),
    ])
def page_victors():
    if not chart_ok:
        _recovery_panel("Lunation and victors")
        return
    st.header("Lunation and victors")
    _chart_strip(counts_from_the_ascendant=True)
    st.subheader('Prenatal Lunation (Syzygy)', help='The New or Full Moon before birth: its degree, its natal place, the five lords of the degree and the governor among them (Sahl, On Nativities 1.7, 3-7), with this app\'s approximation and the almuten beside it.')
    syzygy_rows = _display_rows(_syzygy_rows())
    st.dataframe(pd.DataFrame(syzygy_rows), hide_index=True, width='stretch',
                 column_config=_wide_text_columns(pd.DataFrame(syzygy_rows)))
    with _prose():
        st.markdown("**The verdict** names a planet only where the text's clear subcases decide, and otherwise says "
                    "\"unresolved\" with each candidate's profile.")
    # The governor's own table stands in this expander, which is its
    # heading for the table walker (no book icon here, so the table keeps
    # its key); the notes follow the table inside it as headed sections.
    with st.expander("Governor of the syzygy degree: the five lords under On Nativities 1.7, 3-7"):
        st.dataframe(pd.DataFrame(_display_rows(syzygy_governor['rows'])), hide_index=True, width='stretch',
                     height=_rows_height(len(syzygy_governor['rows'])))
        _note_sections([
            ("The selected triplicity lord.", "The star marks the triplicity lord selected by the nativity's sect, following Dykes's commentary on Sahl, On Nativities 1.7; Sahl's sentence 3 does not expressly identify the reference sect. The target degree comes from the prenatal lunation. Under Dykes's reading, planetary candidate conditions are evaluated in the assumed natal chart. After an opposition, the target degree is that of the luminary above the horizon at the lunation."),
            ("Eastern qualification.", f"This column applies an interpretation of Sahl's On Nativities 1.22 to 1.7: on the morning side, Saturn and Jupiter count from 6°, Mars from 15° following Dykes, and direct Venus and Mercury from 12°; the Moon's criterion is not established by the supplied passages. This column's measure is the allowance by which Sahl's Saturn and Jupiter in On Nativities are \"considered to be eastern\" (1.22, 1), Dykes's 15° for Mars (fn 174 on 1.22, 3), and 1.22, 7 for Venus and Mercury, not the figures for \"the power of easternization\" in 1.22, 6 (Saturn and Jupiter 15°, Mars 18°), which another rule may use. The morning interval includes exactly 180°, following an al-Qabīsī-informed convention (ITA II.10, al-Qabisi III.8a-9); any unrounded value beyond it is outside. Below the adopted threshold does not mean western. The heart is assessed separately. The Direct column reads the one station rule every motion reading in this app follows: a planet within {STATION_SPEED_TOLERANCE} degrees a day of rest is stationary, neither direct nor retrograde, so it is not direct here (the figure is this app's own; the texts name none)."),
            ("How the governor is decided.",
             "**The verdict** names a planet only where the text's clear subcases decide, and otherwise says "
             "\"unresolved\" with each candidate's profile: the five lords of the degree (the nativity's sect-selected triplicity lord) "
             "are the candidates; a retrograde one, or one not looking at the syzygy's sign (the same sign or a "
             "whole-sign aspect), is not eligible (4, read as eligibility); 3's \"the eastern one\" is a preference "
             "among the claim-holders, not a veto -- a candidate not qualifying as eastern is set aside only by a qualifying eastern one with at "
             "least as many claims on the degree; the **Sun** is a claim-holder whose side relative to himself is not "
             "applicable, so 3 neither prefers nor sets him aside, and a contest that only easternness would decide "
             "against him is left unresolved; 7 is kept as a profile, not a score -- a candidate with a listed "
             "advantage (a stake; own house, exaltation, triplicity or bound; the image is not in 7's list) beats one "
             "with none, and two that each hold one are left unresolved, the text stating no ranking among them and "
             "On Nativities 1.20, 2-4's ranking of the lords being stated for the house-master, not borrowed here."),
            ("Interpretive choices.",
             "| Choice | Reading made here |\n"
             "|---|---|\n"
             "| \"In a stake\" | Read by the division (Alchabitius, the five degrees at the four axial degrees), the convention Dykes proposes for strength language; the text's own word for the stakes is the counted sign |\n"
             "| The Moon's eastern preference | Unresolved: the supplied passages do not define her criterion; it affects the governor only where it can change the judgment |\n"
             "| The Sun's side | A claim-holder whose side relative to himself is not applicable, so 3 neither prefers nor sets him aside |\n"
             "| The chart the conditions are read in | The natal chart, the target degree being the lunation's; the natal context of Dykes's comment extended to 3-7, whose moment the text does not state |\n\n"
             "\"in a stake\" is read by the **division** (Alchabitius, the five "
             "degrees at the four axial degrees), the convention Dykes proposes for strength language (ITA "
             "Introduction §6, quadrant divisions for power; Alchabitius this app's choice among them) -- the text's own word "
             "for the stakes is the counted sign, \"the sign of the Ascendant, the fourth, the seventh, and the "
             "tenth\" (The Introduction Ch. 2, 31); Gr. Intr. VII.2, 4 names her right and left, not the lunar "
             "eastern criterion. Al-Qabisi's bridge (ITA II.10.1, al-Qabisi III.8) concerns the superiors. "
             "The target degree is the lunation's and every condition is read in the **natal** chart, "
             "following Dykes's commentary; the lunar preference remains unresolved where it could decide the outcome."),
            ("The three results compared.",
             "The **approximation** row is " + SAHL_1_7_MODEL_DISCLOSURE + "; the almuten row is the 5/4/3/2/1 "
             "weighting al-Qabisi states (ITA I.18: the lord of the domicile five strengths, of the exaltation "
             "four, of the triplicity three, of the bound two, of the face one; Dykes's fn 210 there, only the "
             "primary triplicity lord scoring), a technique not in Sahl, using the lunation's sect as this app's convention for the degree's almuten. The approximation uses the governor's natal-sect claimant and the same conditional facts. Where the three differ, the difference "
             "is the finding."),
            ("Source passages, and what is not modelled.",
             "Sahl, On Nativities 1.7, 3:\n\n> \"you will know the one in charge of that portion from five things: the "
             "lord of the house, triplicity, exaltation, bound, and image, and the eastern one of them -- if [one] had "
             "superior claims over the rest of them\";\n\n4:\n\n> \"Then see which of them is stronger in its [own] place, and "
             "is direct in course, looking at the sign of the meeting or opposition\";\n\n7:\n\n> \"if they were both in power "
             "equally, [then] whichever of them was in a stake or in its own house, triplicity, bound, or exaltation, "
             "and had superiority over its associate in this respect, that is the governor.\"\n\n[Sahl I p. 265]. "
             "Not modelled: " + SAHL_1_7_UNMODELLED + "."),
        ])
    st.subheader('Victor of the Chart', help="Ibn Ezra's victor table (his book is not among this app's sources), laid out cell for cell so it can be checked against one filled in by hand.")
    st.caption("ibn Ezra's victor #1 -- 1485/1537")
    with _prose():
        st.markdown("1. The first five rows score each planet's essential-dignity claim **at that point's** degree -- Sun, Moon, Ascendant, Lot of Fortune, and the prenatal New/Full Moon.\n"
                    "2. Then Lord of the Day (+7), Lord of the Hour (+6) and Places are added **once** each, not per point; Places is keyed the other way round, by the candidate planet's own whole-sign house.\n"
                    "3. Every column is summed into Totals, and the single highest total is the chart's victor.")
        # The four computed combinations, read off the results: the two
        # weightings against the two Places wheels, each cell the scheme's
        # own victor, total and preset status.
        def _victor_cell(weights, places):
            res = victors_data[f"{weights} weights + {places} places" + (" (matched preset)" if weights == places else "")]
            return (f"**{res['victor']}** ({res['total']})" + (", tied at the top" if res['tied'] else "")
                    + (", matched preset" if weights == places else ""))
        st.markdown("| Dignity weights | Older places | Newer places |\n|---|---|---|\n"
                    + "\n".join(f"| {w} | {_victor_cell(w, 'Older')} | {_victor_cell(w, 'Newer')} |" for w in ("Older", "Newer")))
    # The two same-tradition pairings are the grids a student fills
    # in; the two off-diagonal pairings are the cross-check.
    def _victor_grid(scheme_name, res):
        st.markdown(f"**{scheme_name}** — victor: **{res['victor']}** ({res['total']}), runner-up {res['runner_up']}"
                    + ("  \n:orange[Tied at the top — the sheet does not break ties.]" if res['tied'] else ""))
        st.dataframe(pd.DataFrame(res['grid']), hide_index=True, width='stretch', height=_rows_height(len(res['grid'])))
    for scheme_name, res in victors_data.items():
        if 'matched preset' in scheme_name:
            _victor_grid(scheme_name, res)
    with st.expander("Cross-check: the two unmatched weight/place pairings"):
        for scheme_name, res in victors_data.items():
            if 'matched preset' not in scheme_name:
                _victor_grid(scheme_name, res)

    _notes_expander(NOTES_TITLE, [
        ("The weights and the places.",
         "The weights and the five places are al-Qabisi's -- ITA I.18, the five dignities' points, and VIII.1.4 (al-Qabisi IV.7), the victor over the native from the Ascendant, the two luminaries, the Lot of Fortune and the prenatal syzygy; the table's Day, Hour and Places rows are ibn Ezra's. The seven planets are the columns."),
        ("Two independent axes.",
         "**Two independent axes**, and all four combinations are shown. The dignity weights are Older (al-Tabari/Masha'allah, Bound 3 > Triplicity 2) or Newer (al-Qabisi/Abu Ma'shar, Triplicity 3 > Bound 2); the Places wheel is ibn Ezra's own or Masha'allah's. Nothing in the source says which wheel goes with which weighting, so pairing each with the wheel of its own named tradition is a reading, not a fact -- those two are labelled \"matched preset\" and the two off-diagonal combinations, previously not computed at all, are shown beside them. Where all four agree the victor is robust; where they part, the disagreement is the finding."),
        ("The \"Older\" attribution.",
         "The \"Older\" attribution is kept as its source prints it; the one passage in these texts that gives 'Umar's weights -- Abu Bakr, On Nativities II.5.14, through al-'Anbas -- has triplicity 3 and bound 2, the \"Newer\" order; al-Qabisi knows the other order without naming its authors (\"certain people put the bound before the triplicity\", al-Qabisi I.22, in ITA I.18), so the attribution is unwitnessed here. Dykes's introduction to Abu Bakr (PN II) further says the weighted victor is not found in Sahl or Masha'allah."),
        ("Dykes's critique of the weighting.",
         "Dykes's standing critique of the weighting (ITA I.18 fn 211): with the Dorothean triplicities and the Egyptian bounds, and only the primary triplicity lord scoring, the victor is always the domicile or the exaltation lord but for a few degrees of Pisces (Mars) and of Cancer (Venus)."),
        ("Ibn Ezra's later victor, not implemented.",
         "Ibn Ezra's later victor #2 (1507) replaces the two chronocrator rows with a Superiors row scored only for Saturn, Jupiter and Mars; its weight is stated in no text in hand, so it is not implemented rather than guessed."),
    ])
# --- The year under examination (2026-09-10; a block of its own
# 2026-09-17) ----------------------------------------------------
# The target lives on the Prediction pages, where it is used, not in
# the sidebar with the nativity. Its store keys are read at the top
# level (the bundle is computed before any page runs); the widgets
# here write them through _persist, as the readings do. The block
# renders at the head of all four Prediction pages with the same
# widget keys, which is safe because one page runs per rerun; the
# store keys are what carry the target across the Nativity pages,
# since Streamlit drops the state of a widget not rendered on a run.
def _carry(widget_key, seed):
    """Seed one of the year block's widgets from its own current value, or
    from `seed` when it has none -- written every run, not setdefault. The
    block renders on four pages, and Streamlit gives a keyed widget a new
    element id on each page (the id carries the page's hash), so a value
    left by another page's widget is found under the user key only and
    would not reach the new widget: it would take its default, and
    _persist would carry the default into the store. A value written
    through st.session_state before the widget is created reaches it on
    any page; on a rerun the same page's widget triggers, the key already
    holds the new value and is written back to itself."""
    st.session_state[widget_key] = st.session_state.get(widget_key, seed)


# Abu 'Ali's ladder note (JN_YEARS_NOTE), the engine's sentences under
# headings this page places: the same sections on The releaser page,
# under the ladder, and on Fardar and ages, under the Planetary years
# table. Cut at the note's own lead phrases; the angle brackets escaped
# for Markdown as the caption escaped them; each impediment's definition
# a line of its own. The note is written as The releaser prints it, its
# On Nativities locators bare under that page's caption (ruling 117); on
# Fardar and ages, under PN IV's caption, `named` gives each sentence's
# first one its book (ruling 129).
_JN_NOTE_NAMED = ("no sentence of On Nativities 1.20, 10-34", "as On Nativities 1.20 is placed")


def _jn_years_note_sections(named=False):
    p = [s.replace('<', chr(92) + '<') for s in
         _paragraphs(JN_YEARS_NOTE, "Read: the place by the division", "\"peregrine\" is a planet",
                     "\"burned up\" is this app's", "the Sun takes no step", "\"free from the bad ones\" is not tested",
                     "Where JN Ch. 4's count differs", "On the additions Abu 'Ali and Sahl disagree")]
    for with_book in (_JN_NOTE_NAMED if named else ()):
        bare = with_book.replace("On Nativities ", "")
        assert sum(s.count(bare) for s in p) == 1, bare
        p = [s.replace(bare, with_book) for s in p]
    return [("When this ladder is shown.", p[0]),
            ("Steps and impediments.", p[1]),
            ("This app's definitions and exceptions.", "\n".join(f"- {s}" for s in p[2:6]) + "\n\n" + p[6]),
            ("Source disagreement.", p[7])]

# Abu 'Ali's additions note (JN_CH4_ADDITIONS_NOTE), the same way, for
# the additions finding's notes on The releaser page.
def _jn_ch4_note_sections():
    p = _paragraphs(JN_CH4_ADDITIONS_NOTE, "The principal rows state", "Abu Bakr and 'Umar are separate",
                    "Fortune strength grades", "Mercury results derived", "A solar modifier",
                    "Whole-sign aspects and any", "The fortunes are Jupiter")
    return [("What the rows state.", p[0] + "\n\n" + p[1]),
            ("Abu Bakr and 'Umar, separate witnesses.", p[2]),
            ("Grades left unchosen, and Mercury's conjecture.", p[3] + "\n\n" + p[4]),
            ("The luminaries.", p[5]),
            ("Conventions of this display.", p[6] + "\n\n" + p[7])]

# Sahl 1.20's readings (SAHL_1_20_READINGS, reaching the page through
# the hm_years dict's 'readings'), the engine's one long sentence under
# headings this page places: the placement, the vocabulary as a list, the
# sentence readings as a list, then On Times and 1.23.
# Editorial emphasis is sentence case; source quotations retain their printed case.
# This renderer only splits the constant into sections; it does not rewrite it.
def _sahl_1_20_readings_sections(text):
    p = _paragraphs(text, "\"enhanced\" (7-9) =", "\"a share\" =", "for the five planets", "\"under the rays\" =",
                    "\"alien\" =", "10 and 20 as fn 158", "\"under the earth\" (11)", "12 is subsumed by 10",
                    "13 is illegible", "14-15 are printed", "19 and 22 (alien", "where a sentence names months",
                    "Placements no sentence reaches", "On Times 4, 7 is a rule", "1.23, 53 and 61:")
    return [("The placement: the division, and a power judgment.", p[0]),
            ("The vocabulary.", "\n".join(f"- {s}" for s in p[1:6])),
            ("The sentences, as read.", "\n".join(f"- {s}" for s in p[6:14])),
            ("On Times 4, 7, and On Nativities 1.23, 53 and 61.", p[14] + "\n\n" + p[15])]

def _additions_detail(row):
    """One planet of the additions table, its cells whole under the
    column headings the table carries."""
    shown = {key: _display_result(value) for key, value in row.items()}
    st.markdown(f"**{shown['Planet']}**, {shown['Looks at the house-master']}.")
    st.markdown(f"**Effect (Ch. 4).** {shown['Ch. 4']}.")
    st.markdown(f"**Conditional grades.** Its own lesser years: {shown['Its own lesser years']}; if middling in "
                f"strength: {shown['If middling in strength']}; if more unsound: {shown['If more unsound']}. "
                f"Grade: {shown['Grade']}.")
    st.markdown(f"**This app's reading.** {shown['Reading']}.")
    st.markdown(f"**Other witnesses.** {shown['Witnesses']}")


def _year_under_examination(page):
    st.subheader("The year under examination",
                 help="Three counts of the year run here -- the revolution's cycle, the civil age, the years "
                      "elapsed from the birth hour -- and the line beside the date says which tables key on "
                      "which. Set the year as an age or as a date; the other is read back beside it. "
                      "Remembered across pages and saved with the chart.")
    t_mode, t_value, t_read = st.columns([1, 1.4, 2.6])
    with t_mode:
        _carry("target_mode", target_mode)
        _reading_radio("Target by", TARGET_MODE_OPTIONS, "target_mode", "_target_mode",
                       help="Age: the completed civil years; the target is that birthday's date, which can fall "
                            "before the Sun's return opens the revolution. Date: any civil date, its counts of the "
                            "year shown beside it. Either is read at noon UT, or at the birth's own moment where "
                            "that noon falls before the birth.")
    with t_value:
        if target_mode == TARGET_MODE_OPTIONS[1]:
            # "Past the table" is a state the page reports, not an error, so
            # the ages run as far as the ephemeris does -- and no further
            # (H2): the box had no upper bound at all, and an age that
            # carried the birthday past the ephemeris raised before any page
            # was drawn. The bound is this chart's own, counted from its
            # birth year.
            _age_bound = max_target_age(input_date)
            _carry("target_age", int(target_age))
            # B-03 (ruling 145): an age above this chart's bound -- left in
            # the box by a birth-date edit that lowered it -- would come back
            # as 0 and be persisted as the target. The box is seeded with the
            # kept age instead, the age the read-back and the export use.
            # Here only, where the box is drawn: a write into its key at the
            # top level reaches runs where the box is not drawn, and brings
            # a stale age back after a Nativity page (the record load's
            # comment above, 2026-09-17).
            if engine._is_real_number(st.session_state["target_age"]) and st.session_state["target_age"] > _age_bound:
                st.session_state["target_age"] = int(target_age)
            st.number_input("Age (completed years)", min_value=0, max_value=_age_bound,
                            step=1, key="target_age")
            _persist("target_age", "_target_age", target_age)
        else:
            _carry("target_date", target_date.isoformat())
            st.text_input("Target date (YYYY-MM-DD)", key="target_date")
            _persist("target_date", "_target_date", target_date.isoformat())
            if parse_iso_date(st.session_state.get("target_date", target_date.isoformat())) is None:
                st.error(f"Not a YYYY-MM-DD date; keeping {target_date:%Y-%m-%d}.")
        # A target the ephemeris cannot reach, from either box: the last
        # valid one stands and this says so, where the target is set.
        if target_range_note:
            st.error(target_range_note)
    with t_read:
        # The civil age and the revolution's cycle are two counts and are
        # said as two: between a birthday and its return they differ by
        # one, and a header that put "the Nth birthday opens this year"
        # and "the revolution fell on" the (N-1)th return in one sentence
        # asserted one year of two. Where the target is read is the
        # bundle's: noon UT, or the birth's own moment on a target date whose
        # noon UT falls before the birth (pn4_target_read_at).
        st.markdown(
            f"**{target_date:%Y-%m-%d}** -- age **{target_age}** completed "
            f"(born {input_date:%Y-%m-%d}); read at {pn4_target_read_at(pn4['target_at_birth'])}, "
            f"**{pn4_elapsed_text(pn4['elapsed_years'])}** years elapsed from the birth hour.  \n"
            f"The revolution of the year fell on **{pn4_datetime_from_jd(pn4['jd_sr']):%Y-%m-%d}** "
            f"{pn4_datetime_from_jd(pn4['jd_sr']):%H:%M} UT ({pn4_ut_calendar_note(pn4['jd_sr']).split(' (')[0]}), "
            + (f"the **{pn4_ordinal(pn4['cycle'])}** return" if pn4['cycle'] else
               # Before the first return the revolution is the root itself,
               # the Sun "in his position in which he was at the root" (the
               # subheader's quotation), not a "0th return" (K-22).
               "the root itself, before the **1st** return")
            + f"; the target is in its month **{pn4['month']}** of 12"
            + (" -- the civil birthday and the Sun's return fall either side of the target"
               if pn4['cycle'] != target_age else "") + ".")
        st.caption(pn4_count_line(page, pn4['target_at_birth']))


def page_timing():
    if not chart_ok:
        _recovery_panel("Revolutions")
        return
    st.header("Revolutions")
    _chart_strip(counts_from_the_ascendant=True)
    # B-11: PN IV is the page's frame and its bare Book.chapter locators are
    # PN IV's (ruling 117); a second caption, after the scope line (only the
    # opening sentence may stand between the strip and it), names the other
    # sources the page applies: one caption would pass the 400-character ceiling.
    st.caption("The frame of this page is Abu Ma'shar, "
               "*On the Revolutions of the Years of Nativities* (*Persian Nativities* IV), "
               "cited as Book.chapter, sentence.")
    _sources_scope_line()
    st.caption("This page also applies Sahl's fixed stars (with Rhetorius's natures), his releaser and his "
               "year of the turning; the Configurations page's connection rule and reception; the Lots of "
               "the Lots page; al-Qabisi's proportional semi-arcs; and the *Great Introduction*'s "
               "twelfth-parts, triplicity lords, classes of signs and degrees, Mercury's phase, and the "
               "Moon's connections within her sign.")
    _year_under_examination('Revolutions')

    # --- Three chapters, as tabs (2026-09-10, second pass; three of
    # the six became pages of their own on 2026-09-17: The releaser,
    # Days and months, Fardar and ages). The revolution read as one
    # thing, in the page's own order. Client-side tabs, as on
    # Configurations: a click switches instantly and reruns nothing;
    # the chapter is kept across reruns from the page's own controls,
    # and the page opens on the first chapter when returned to (owner,
    # third pass: the rerun that remembered the chapter across pages
    # flickered).
    _tab_labels = ("The Revolution", "Indicators of the Year", "Distributions")
    tab_rev, tab_ind, tab_dist = st.tabs(list(_tab_labels))
    with tab_rev:
        st.subheader("The revolution of the year",
                     help="I.2, 1: a revolution is the moment the Sun comes back to \"his position in which he was "
                          "at the root\". I.2, 4: derive its Ascendant and the twelve houses.")
        with _prose():
            st.markdown("**A true-Sun return.** This app uses a **true**-Sun return; Abu Ma'shar computes a mean "
                        "Sun and then applies the Hipparchan tropical year (PN IV I.4, 23-31), which Dykes says plainly "
                        "does not make sense (Intro Sect. 1).")
        st.dataframe(pd.DataFrame(pn4['revolution_rows']), hide_index=True, width='stretch',
                     height=_rows_height(len(pn4['revolution_rows'])),
                     column_config=_wide_text_columns(pd.DataFrame(pn4['revolution_rows'])))

        # --- The charts, drawn (2026-09-10) ---------------------------------
        # I.6, 1-6 and IX.3, 4-8 describe images holding the root, the
        # revolution of the year and the revolution of the month on one
        # zodiac. Drawn as PN IV's editor draws them: the outer charts in
        # whole signs, the sign of the year shaded, the profection a
        # dashed arc, an Egyptian-bounds ring, the default points of p. 12.
        # The controls are readings of the page, kept across navigation.
        # One @st.fragment for the whole of this subheader's block
        # (item 9, 2026-09-15). Every one of its eight controls -- the
        # View selectbox, the Wheel layout radio and the five in the
        # Options popover -- used to rerun the whole script, which
        # redraws the 67 tables this page carries; a fragment reruns
        # only its own body on its own widgets' changes. The picture is
        # what the controls are for, so the picture, its download and
        # the caption that explains its conventions are inside it and
        # the direction strips and every table are outside.
        #
        # The revolution data is the top level's: pn4 and the charts it
        # carries are computed once per run, before this page's tabs,
        # and the fragment reads them from the enclosing scope. What
        # the fragment regenerates on its own rerun is the SVG, from
        # the values its own widgets hold -- including the theme, which
        # is taken from this block's own Dark wheel checkbox rather
        # than from the top level's WHEEL_THEME, that being a full
        # run's value and not one a fragment rerun moves. The Lots
        # ring is the one thing any fragment computes through an
        # evaluator that reads a reading (lot_by_id, LOT_HOUSE_CUSP),
        # and the reason every fragment is declared with
        # _pinned_fragment: the rerun's thread is pinned to this run's
        # readings before the body runs, so the ring carries the Lots
        # the Lots page's table carries.
        @_pinned_fragment
        def _timing_wheel_block():
            st.subheader("The charts, drawn",
                         help="The Wide layout adds a positions column per chart; hover the picture for the expand arrows.")
            st.session_state.setdefault("_timing_bounds", True)
            v_view, v_layout, v_opts = st.columns([2.2, 1.4, 0.9], vertical_alignment="bottom")
            with v_view:
                wheel_view = _reading_select("View", WHEEL_VIEW_OPTIONS, "timing_wheel_view", "_timing_wheel_view")
            with v_layout:
                _timing_layout = _reading_radio("Wheel layout", WHEEL_LAYOUT_OPTIONS, "wheel_layout", "_wheel_layout")
            with v_opts:
                with st.popover("Options", icon=":material/tune:", width="stretch"):
                    wheel_order = _reading_radio("Inner wheel", WHEEL_ORDER_OPTIONS, "wheel_order", "_wheel_order",
                                                 help="PN IV Figure 51 follows Abu Ma'shar; every other figure in "
                                                      "the book puts the nativity in the centre. IX.3, 4-6 writes the "
                                                      "month first, then the year, then the root.")
                    wheel_bounds = _reading_checkbox("Bounds ring", "timing_bounds", "_timing_bounds",
                                                     help="The Egyptian bounds as a ring, as every PN IV wheel carries them.")
                    # Every control in this popover stands before the
                    # picture, so each one's own return is this
                    # fragment rerun's value -- no read-before-draw is
                    # needed here, as it is on the Chart page where the
                    # controls sit under the wheel. _persist still
                    # writes the store keys and the preferences file
                    # from inside the fragment, so the next full run's
                    # WHEEL_DARK and the rest read what was left here.
                    _timing_dark = _reading_checkbox("Dark wheel", "wheel_dark", "_wheel_dark", help=WHEEL_DARK_HELP)
                    want_lots = _reading_checkbox("Lots", "timing_lots", "_timing_lots",
                                                  help="I.6, 3-4 and 8: the Lots \"according to how you do it\" -- this app's, "
                                                       "beyond Fortune, as short ticks with their names.")
                    want_rays = _reading_checkbox("Rays", "timing_rays", "_timing_rays",
                                                  help="I.6, 3-4 and 8: the 98 rays, as ticks -- too many to letter; the "
                                                       "inventory table below lists each one.")
                    want_twelfths = _reading_checkbox("Twelfth-parts", "timing_twelfths", "_timing_twelfths",
                                                      help="I.6, 3-4 and 8: the 38 twelfth-parts of the planets and of the "
                                                           "house degrees, as ticks.")

            def _ring_extras(chart):
                out = []
                if want_lots:
                    for lot in operative_lot_rows(chart['planetary_data'], chart['ascendant'], chart['houses'],
                                                  chart['sect'], READING_DEPTH == READING_DEPTH_OPTIONS[1]):
                        if lot['Id'] != 'fortune':
                            out.append((lot['Lot'], lot['Longitude'], lot['Lot'].replace('Lot of ', '').replace('the ', '')[:9]))
                if want_rays:
                    for ray_lon, kind, who, aspect in pn4_bodies_and_rays(chart['planetary_data']):
                        if kind != 'body':
                            out.append((f"{who} by {aspect}", ray_lon, POINT_GLYPHS[who] + _ASPECT_GLYPH.get(aspect, '')))
                if want_twelfths:
                    for who, row in chart['planetary_data'].items():
                        if who in PLANET_SWE_IDS:
                            out.append((f"twelfth-part of {who}", pn4_twelfth_part(row['longitude']), '¹²' + POINT_GLYPHS[who]))
                    for i, cusp in enumerate(list(chart['houses'])[:12]):
                        out.append((f"twelfth-part of the degree of house {i + 1} ({get_degree_string(cusp)})",
                                    pn4_twelfth_part(cusp), f'¹²h{i + 1}'))
                return out

            _natal_when = f"{local_dt.day} {local_dt:%b} {local_dt.year} {local_dt:%H:%M} {tz_name}"
            natal_ring = {'label': 'Nativity', 'chart': chart_data, 'when': _natal_when}
            # The ring is the revolution's chart, so it is named by the
            # revolution's count, as the header names it: between a birthday
            # and its return "age 10" stood beside the 9th return's chart
            # (F2-wheel, lane F2's check 18).
            # Before the first return the ring is the root itself, as the
            # header says, not a "0th return" (K-22).
            year_ring = {'label': (f"Year, {pn4_ordinal(pn4['cycle'])} return" if pn4['cycle']
                                   else "Year, the root itself"), 'chart': pn4['sr'],
                         'when': f"{pn4_datetime_from_jd(pn4['jd_sr']):%d %b %Y %H:%M} UT, {pn4_ut_calendar_note(pn4['jd_sr']).split(' (')[0]}"}
            month_ring = {'label': f"Month {pn4['month']} of 12", 'chart': pn4['mr'],
                          'when': f"{pn4_datetime_from_jd(pn4['jd_mr']):%d %b %Y %H:%M} UT, {pn4_ut_calendar_note(pn4['jd_mr']).split(' (')[0]}"}
            year_sign = SIGN_ORDER.index(pn4['year']['sign'])
            _month_lon = next((r['longitude'] for r in pn4['monthly_indicators'] if r['number'] == 1), None)
            # On the circle first: -1e-16 % 360.0 is 360.0 in floats, sign
            # index 12, where the point is 0 Aries (_on_circle, as KD's sites).
            month_sign = None if _month_lon is None else int(_on_circle(_month_lon) // 30)
            # The Year over root view is the image of the revolution of the
            # year, so its letters and its solid arc are the image table's
            # (the owner's ruling 6, on D2): PN IV I.6, 6's time lords and
            # endpoint at the revolution's moment -- PN IV I.6, 3: "so that
            # all of them are in the signs in which they are at the
            # revolution of the year"; PN IV I.6, 6 fn 34: "the very degree
            # which the distribution had reached" -- the bundle's
            # `current_sr`, `fardar_sr` and the revolution's elapsed years,
            # which `pn4_revolution_image` is handed. The Month over year
            # and root view is the image of the revolution of the month, and
            # reads them at the month's revolution (the owner's ruling 34):
            # PN IV IX.3, 4 writes the month's planets "at the time of the
            # revolution of the month", and PN IV IX.3, 8 names the terminal
            # point of the distribution and the same time lords with no
            # moment of their own -- the bundle's `current_mr`, `fardar_mr`
            # and `month_from`.
            def _time_lord_letters(cur, fardar):
                letters = {}
                for _planet, _letter in (((cur or {}).get('distributor'), 'D'), ((cur or {}).get('partner'), 'P'),
                                         ((fardar or {}).get('lord'), 'F'), ((fardar or {}).get('sub_lord'), 'f'),
                                         (pn4['orb'], 'O')):
                    # A tied opening partner is an UnresolvedResult, which has no
                    # truth value and no single planet to badge: the wheel marks
                    # nothing for it (the row and the strip say the tie). Two or
                    # more partners met together (PN IV III.1, 50) are each badged.
                    for _one in (pn4_partner_planets(_planet) if isinstance(_planet, PN4Together) else (_planet,)):
                        if not is_unresolved(_one) and _one:
                            # A node holding the fardar (PN IV IV.7, 24) is
                            # named Head or Tail by the fardar table and
                            # drawn as the North or South Node by the wheel,
                            # so its F is put on the point the wheel draws.
                            _one = {'Head': 'North Node', 'Tail': 'South Node'}.get(_one, _one)
                            letters[_one] = (letters.get(_one, '') + '·' + _letter).strip('·')
                return letters

            def _distribution_to(cur, elapsed):
                if not (cur and pn4['segments']):
                    return None
                return {'start': chart_data['ascendant'],
                        'end': _pn4_seg_degree({'from': elapsed}, chart_data['ascendant'], chart_data, lat)}

            _distribution_at_revolution = _distribution_to(pn4['current_sr'], pn4['revolution_window'][0])
            _distribution_at_month = _distribution_to(pn4['current_mr'], pn4['month_from'])
            _badges_at_revolution = _time_lord_letters(pn4['current_sr'], pn4['fardar_sr'])
            _badges_at_month = _time_lord_letters(pn4['current_mr'], pn4['fardar_mr'])
            _dykes = wheel_order == WHEEL_ORDER_OPTIONS[0]
            _wide_t = _timing_layout == WHEEL_LAYOUT_OPTIONS[1]
            if wheel_view == WHEEL_VIEW_OPTIONS[0]:
                _rings, _kw = [year_ring], {}
            elif wheel_view == WHEEL_VIEW_OPTIONS[1]:
                _rings = [natal_ring, year_ring] if _dykes else [year_ring, natal_ring]
                _n = _rings.index(natal_ring)
                _kw = dict(shade_sign=year_sign, profection_from=chart_data['ascendant'],
                           distribution=_distribution_at_revolution,
                           marks=[('TP', pn4['year']['longitude'], _n)], badges={_n: _badges_at_revolution})
            elif wheel_view == WHEEL_VIEW_OPTIONS[2]:
                _rings = [natal_ring, year_ring, month_ring] if _dykes else [month_ring, year_ring, natal_ring]
                _n = _rings.index(natal_ring)
                _kw = dict(shade_sign=year_sign, outline_sign=month_sign, profection_from=chart_data['ascendant'],
                           distribution=_distribution_at_month,
                           marks=[('TP', pn4['year']['longitude'], _n)], badges={_n: _badges_at_month})
            elif wheel_view == WHEEL_VIEW_OPTIONS[3]:
                _rings, _kw = [month_ring], {}
            else:
                _rings = [natal_ring]
                _kw = dict(shade_sign=year_sign, outline_sign=month_sign, profection_from=chart_data['ascendant'],
                           marks=[('TP', pn4['year']['longitude'], 0)])
            _extras = {i: _ring_extras(r['chart']) for i, r in enumerate(_rings)} if (want_lots or want_rays or want_twelfths) else None
            # The same rule the top level's WHEEL_THEME follows, read
            # from this fragment's own checkbox: the viewer's theme
            # when the preference is on, None when it is off. No
            # picture is handed the viewer's theme unfiltered.
            _timing_theme = VIEWER_THEME if _timing_dark else None
            svg_timing = generate_multiwheel_svg(_rings, chart_name, wide=_wide_t, bounds=wheel_bounds, extras=_extras,
                                                 theme=_timing_theme, **_kw)
            st.image(svg_timing, width='stretch' if _wide_t else 560)
            st.download_button("Download this wheel (SVG)", svg_timing, key="dl_timing_wheel",
                               file_name=f"{_download_stem}_"
                                         f"{re.sub(r'[^A-Za-z0-9]+', '_', wheel_view).strip('_').lower()}_age{pn4['age']}.svg",
                               mime="image/svg+xml")
            st.caption("Default points are Dykes's (p. 12): the seven planets, the nodes, Fortune, the angles; "
                       "I.6, 3-4's Lots, rays and twelfth-parts are the toggles, and the inventory table below is "
                       "the authority the picture is held to.")
            # The wheel's conventions, read from PN IV's figures: the five
            # views, the layers, a Mark / Meaning key for the letters and
            # the arcs (the letters expanded only as the sentence beneath
            # the key defines them, F the lord of the fardar and f its
            # divider), and what the picture keeps as Dykes drew it.
            _notes_expander("How the wheel is drawn", [
                ("The five views.",
                 "- Year: the revolution alone (PN IV Figures 4, 26).\n"
                 "- Year over root: the image of the revolution of the year, I.6, 3-6 (PN IV Figure 51 and fn 33; "
                 "PN IV Figures 5 and 27 in Dykes's order).\n"
                 "- Month over year and root: the image of the revolution of the month, IX.3, 4-8 (PN IV Figures 39 "
                 "and 109, fn 58).\n"
                 "- Month: the month's revolution alone.\n"
                 "- Profection: the natal wheel with the sign of the year and the sign of the month (PN IV Figures 3, 15, 33)."),
                ("Chart layers.",
                 "PN IV's own conventions, read from its figures: the nativity in the centre and the "
                 "revolution outside in every bi-wheel but PN IV Figure 51, where Dykes follows Abu Ma'shar's order of I.6 "
                 "and says so (p. 12); the outer charts in whole signs; \"the profected natal Ascendant "
                 "... which I have shaded in grey\" (fn 33) -- the sign of the terminal point of the year -- "
                 "with the profection drawn as a dashed arc from the natal Ascendant (PN IV Figures 3, 33); the month "
                 "as a tri-wheel, root, year, month (fn 58); a ring of the Egyptian bounds on its wheels "
                 "(PN IV Figures 1, 22, 25, 26; not the simplified PN IV Figure 51). The inner wheel: Dykes: \"Abu Ma'shar "
                 "seems to prefer that the SR be the inner wheel, but to me this seem unnatural and I only do it to "
                 "illustrate his instructions in Ch. I.6\" (p. 12)."),
                ("Points shown.",
                 "| Mark | Meaning |\n"
                 "|---|---|\n"
                 "| TP | the terminal point of the year (I.6, 5) |\n"
                 "| D | distributor (PN IV I.6, 6's time lords, lettered under a natal planet) |\n"
                 "| P | partner |\n"
                 "| F | lord of the fardar |\n"
                 "| f | its divider |\n"
                 "| O | lord of the orb |\n"
                 "| dashed arc | the profection, from the natal Ascendant (PN IV Figures 3, 33) |\n"
                 "| solid arc | the distribution, from the natal Ascendant, ending on the degree it had reached at the revolution's moment, the year's or the month's, with its bound tinted (PN IV Figures 2, 65) |\n"
                 "| shaded sign | the sign of the terminal point of the year (fn 33) |\n"
                 "| ring | the Egyptian bounds (PN IV Figures 1, 22, 25, 26) |\n\n"
                 "On the Year over root view the time lords of PN IV I.6, 6 and the solid arc are read at the "
                 "revolution's moment, as the image table below takes them: PN IV I.6, 3 writes the image's points "
                 "\"so that all of them are in the signs in which they are at the revolution of the year\", and "
                 "carrying that moment to PN IV I.6, 6's time lords is this app's reading (the endpoint is \"the very "
                 "degree which the distribution had reached\", PN IV I.6, 6 fn 34). On the Month over year and "
                 "root view they are read at the month's revolution, the same reading: PN IV IX.3, 4 writes the "
                 "month's planets \"at the time of the revolution of the month\", and PN IV IX.3, 8 names the month "
                 "image's time lords with no moment for them. TP marks the terminal point of the year (I.6, 5); the "
                 "letters under a natal planet mark PN IV I.6, 6's time lords -- D distributor, P partner, F lord of "
                 "the fardar, f its divider, O lord of the orb; the solid arc from the natal Ascendant is the "
                 "distribution, ending on the degree it had reached at that revolution's moment, the year's or "
                 "the month's, with its bound tinted (PN IV Figures 2, 65)."),
                ("Display conventions: whole signs drawn, cusps computed.",
                 "Two "
                 "things the text asks for that the picture keeps as Dykes drew it: I.6, 2 has the houses "
                 "\"by their degrees and minutes ... the portions of hours and the ascensions of the right "
                 "circle\" -- the Alchabitius cusps this app computes -- and the wheel keeps whole signs, as "
                 "fn 33 says PN IV Figure 51 does \"to make the image easier to understand\"; and I.6, 5 profects the "
                 "terminal point \"from the Lot of Fortune of the root, and from the rest of the indicators\" "
                 "as well as from the Ascendant, where only the Ascendant's arc is drawn (the Lot of Fortune's "
                 "profection is in the month's indicators on the Days and months page)."),
            ])
        _timing_wheel_block()


        st.subheader("The image of the revolution of the year: its points (PN IV I.6, 3-8)",
                     help="I.6, 8 and Figure 52: 14 planets, 98 rays, the Head and Tail twice each, 38 "
                          "twelfth-parts -- 154 -- \"and the Lots according to how you do it\"; I.6, 9-10: within a "
                          "house, by degree.")
        image_rows, image_counts = pn4['image']
        st.markdown("The count: " + ", ".join(f"{k} {v}" for k, v in image_counts.items())
                    + f" -- I.6, 8 counts 154 without the Lots{' and the count agrees' if image_counts['total of I.6, 8'] == 154 else ', and this chart differs'}.")
        _shown_1 = pd.DataFrame(_display_rows(image_rows))
        st.dataframe(_shown_1, hide_index=True, width='stretch', height=_rows_height(16),
                     column_config=_wide_text_columns(_shown_1))
        st.caption("The fixed stars of I.6, 7 are the table below. The Lots are the ones this app "
                   "computes, \"many or few\"; the count line excludes them as I.6, 8 does.")
        _notes_expander("How the image table is built", [
            ("What I.6, 3-8 asks for.",
             "I.6, 3: the revolution's planets with their conditions, \"their rays and twelfth-parts, "
             "and the twelfth-parts of the degrees of the houses\", and its Lots and Head and Tail; "
             "I.6, 4: the root's planets likewise, "
             "\"and the Lots and Head and Tail\"; I.6, 5: the natal Ascendant and the terminal point; "
             "I.6, 6: the endpoint of the distribution, the distributor and partner, the fardar lord "
             "and its divider, and the lord of the orb, \"each of them in their signs and bounds\" -- "
             "taken at the revolution's moment, as the indicators of the year #2-#4 and the governor are, "
             "since PN IV I.6, 3 writes the image \"so that all of them are in the signs in which they are at the "
             "revolution of the year\" (the endpoint is \"the very degree which the distribution had "
             "reached\", PN IV I.6, 6 fn 34, at that moment; PN IV III.8, 9's \"degree of the distribution\" in the fixed "
             "stars' table below is the same degree); "
             "I.6, 8 and Figure 52: 14 planets, 98 rays, the Head and Tail twice each, 38 "
             "twelfth-parts -- 154 -- \"and the Lots according to how you do it\"; I.6, 9-10: within a "
             "house, by degree."),
            ("A table, by the revolution's cusps.",
             "A table, not the wheel of I.6, 1: every point by the revolution's house cusps -- I.6, 2: "
             "\"calculating the houses by their degrees and minutes, in the way that you calculate the houses by "
             "the portions of hours and the ascensions of the right circle\" (the Alchabitius cusps this app "
             "computes; Dykes drew Figure 51 by whole signs \"to make the image easier to understand\", fn 33; Figure 52 is the count table), "
             "ordered by degree within the house, with each "
             "point's bound."),
            ("The twelfth-parts.",
             "The twelfth-part construction -- 2.5 degrees to a sign, beginning with the sign "
             "itself -- is stated at Gr. Intr. V.18, 1-3 (Figure 57)."),
        ])
        _fs, _fsr = pn4['fixed_stars'], pn4['fixed_stars_revolution']
        st.markdown(FIXED_STARS_READING)
        if _fs['refused']:
            st.warning(f"Not computed: {_fs['refused']}.")
        else:
            if _fs.get('missing'):
                st.warning(_fs['missing'])
            st.markdown("*In the root (I.6, 7):*")
            if _fs['rows']:
                st.dataframe(pd.DataFrame(_fs['rows']), hide_index=True, width='stretch', height=_rows_height(min(len(_fs['rows']), 8)))
            else:
                st.markdown("None of Sahl's stars stands within a degree of the Ascendant, the Midheaven, a luminary or an angular planet.")
            # N04 of SC2's check (lane SC3): the revolution's table names the
            # stars its own read could not place, as the root's does.
            if _fsr.get('missing'):
                st.warning(_fsr['missing'])
            st.markdown("*In the revolution (III.8, 9):*")
            if _fsr['rows']:
                st.dataframe(pd.DataFrame(_fsr['rows']), hide_index=True, width='stretch', height=_rows_height(min(len(_fsr['rows']), 8)))
            else:
                st.markdown("None within a degree of the year's Ascendant, its tenth, the terminal point, the distribution's degree, their lords or the luminaries.")

        st.subheader("The reading checklist (PN IV I.7, 1-26)",
                     help="\"If you made the image of the revolution of the year, then understand:\" (I.7, 1) -- "
                          "twenty-six things.")
        with _prose():
            st.markdown("**Facts from this app's own evaluators**, run on the revolution's data as on the root's: the "
                        "pairwise configurations and the connection rule of the Configurations page, reception under "
                        "its rule, domain as plain sect, the solar phase, the twelfth-part (a "
                        "convention, as the image's notes say), and V.1, 2-3's grades for a return.")
        st.markdown("**I.7, 2-6 -- the revolution's Ascendant:**")
        st.dataframe(pd.DataFrame(pn4['i7_ascendant']), hide_index=True, width='stretch', height=_rows_height(5),
                     column_config=_wide_text_columns(pd.DataFrame(pn4['i7_ascendant'])))
        st.markdown("**I.7, 7-24 -- the planets, in both times** (the numbers are I.7's sentences):")
        st.caption("The stakes (23) use each chart's own cusps (I.6, 2), with the inclusive five-degree "
                   "allowance before the four stakes only: this app's strength reading; I.7, 23 names no unit "
                   "or allowance. The image retains raw quadrant houses and topical places remain whole sign.")
        st.caption(f"Motion (7): a planet within {STATION_SPEED_TOLERANCE} degrees a day of rest is stationary, neither "
                   "direct nor retrograde (this app's own figure; I.7, 7 names direct and retrograde only); Sahl's "
                   "strength testimony 80 on the Configurations page reads the same three states.")
        st.caption("Domain (17): \"those of them in their own domain or not in their domain (of the diurnal "
                   "[planets] and the nocturnal ones)\" (PN IV I.7, 17), read as plain sect, each chart by its "
                   "own: a planet of its sect is in its own domain, one of the other in the contrary "
                   "(PN IV II.3, 5, fn 46: \"simply of the sect of the chart\"); Mercury by his phase "
                   "(Gr. Intr. IV.9, 8). The Domain switch does not reach it.")
        _i7_planet_rows = _display_rows(pn4['i7_planets'])
        st.dataframe(pd.DataFrame(_i7_planet_rows), hide_index=True, width='stretch', height=_rows_height(14))
        _notes_expander("The twenty-six things, and what is not read", [
            ("The checklist, I.7, 2-26.",
             "- 2-6: the revolution's Ascendant -- its house in the root, who is in it "
             "and looks at it in both times, who has a claim on it and where they stand, whether its "
             "lord has one house or two and looks at them.\n"
             "- 7-24: every planet -- motion, strength, "
             "aversion and aspect, rays, connection, reception, support, friendship, domain, "
             "twelfth-parts, returns, course, transits, the Lots, the stakes, the Sun.\n"
             "- 25-26: \"its "
             "indication will be according to its place and condition in the two times together.\""),
            ("Not read, and said so.",
             "\n".join(f"- {n} \"{t}\" -- {why}" for n, t, why in PN4_I7_NOT_READ)),
            ("The Lots, the principle, and the worked example.",
             "I.7, 22, the Lots of the year, are in the image above. I.7, 25-26 is the principle the "
             "II.3 section applies. No worked example exists; I.7 is a list."),
        ])

    with tab_ind:
        st.subheader("Indicators of the year, in Abu Ma'shar's order (PN IV II.1, 5-24)",
                     help="II.1, 5-24 ranks nineteen indicators of the year and II.1, 25 says \"each one in turn "
                          "is stronger in indication than the one which is after it\".")
        with _prose():
            st.markdown("The first five are computed here; the rest are delineation material.")
            st.markdown("**Note the order: within a year** the lord of the "
                        "year outranks the distributor (II.1, 25; II.23, 1). Across several years the "
                        "distribution is the stronger (III.2, 2-3) -- PN IV ranks them by scope; Sahl's On Nativities 1.23, 33 "
                        "and 1.24, 2 contradict each other as printed (the notes under the table).")
        # Row 3's Active point is the distribution's partner_from, which a
        # tied opening makes an UnresolvedResult: the page boundary's words.
        df_year_rows = pd.DataFrame(_display_rows(pn4['year_rows']))
        st.dataframe(df_year_rows, hide_index=True, width='stretch',
                     column_config=_wide_text_columns(df_year_rows))
        # PN4_YEAR_INDICATOR_SCOPE_NOTE, the engine's sentences under
        # headings this page places: the scope comparison first, built
        # from its first and last sentences, which stand whole beneath.
        _scope = _paragraphs(PN4_YEAR_INDICATOR_SCOPE_NOTE, "Sahl's two consecutive chapters",
                             "Dykes fn 245 emends", "PN IV's within-the-year ranking")
        _notes_expander("The lord of the year and the distributor, ranked by scope", [
            ("Within one year, and across several.",
             "| Scope | The stronger indicator, and where it is stated |\n"
             "|---|---|\n"
             "| Within one year | the lord of the year (II.1, 25; II.23, 1); Sahl's On Nativities 1.24, 2 agrees |\n"
             "| Across several years | the distribution (III.2, 2-3); Sahl's On Nativities 1.23, 33 agrees |\n\n"
             + _scope[0]),
            ("Sahl's two sentences, as printed.", _scope[1]),
            ("The editor's emendation, not adopted.", _scope[2]),
            ("The disagreement, recorded and not resolved.", _scope[3]),
        ])

        st.subheader("The sign of the terminal point and its lord, examined (PN IV II.3, 2-19)",
                     help="II.3, 2: examine the sign of the terminal point in the root -- which house of the circle, "
                          "whose house, exaltation and triplicity, which planets, Lots and twelfth-parts are in it, "
                          "who looks at it or casts rays at it and from where, and whether it is devoid of them.")
        with _prose():
            st.markdown("**Facts, not a verdict.** II.3, 5-6 name the factors of a suitable and a contrary condition and "
                        "give no rule for weighing them, so each factor is shown for each chart from this app's own "
                        "evaluators (essential and accidental dignity, solar phase, reception under the Configurations "
                        "page's rule), and Figure 55's cell is not chosen.")
        ii3 = pn4['ii3']
        st.markdown(f"**The sign of the terminal point, {pn4['year']['sign']}, in the root (II.3, 2):**")
        st.dataframe(pd.DataFrame(ii3['root_rows']), hide_index=True, width='stretch', height=_rows_height(5),
                     column_config=_wide_text_columns(pd.DataFrame(ii3['root_rows'])))
        st.markdown("**In the revolution (II.3, 3):**")
        st.dataframe(pd.DataFrame(ii3['revolution_rows']), hide_index=True, width='stretch', height=_rows_height(5),
                     column_config=_wide_text_columns(pd.DataFrame(ii3['revolution_rows'])))
        st.markdown(f"**The lord of the year, {pn4['year']['lord']}: the factors of II.3, 5-6, per chart:**")
        _ii3_lord_rows = _display_rows(ii3['lord_rows'])
        _ii3_lord_df = pd.DataFrame(_ii3_lord_rows)
        st.dataframe(_ii3_lord_df, hide_index=True, width='stretch', height=_rows_height(6),
                     column_config=_wide_text_columns(_ii3_lord_df))
        # Through the display boundary like the rows above: a refinement read
        # from both completions of an undecided connection is an
        # UnresolvedResult, which a raw frame printed as its repr.
        _ii3_refinement_df = pd.DataFrame(_display_rows(ii3['refinement_rows']))
        st.dataframe(_ii3_refinement_df, hide_index=True, width='stretch',
                     height=_rows_height(len(ii3['refinement_rows'])),
                     column_config=_wide_text_columns(_ii3_refinement_df))
        st.markdown("**Figure 55 -- the four cases, in the book's words; which one holds is left to the reader:**")
        st.dataframe(pd.DataFrame(ii3['figure_55']), hide_index=True, width='stretch', height=_rows_height(4))
        _notes_expander("How the factors are read", [
            ("What PN IV II.3, 3-18 asks.",
             "PN IV II.3, 3: the same in the revolution, with where those planets were and are, and their "
             "condition in each. PN IV II.3, 5-8: the lord of the year's condition in root and revolution "
             "compared four ways (Figure 55); II.3, 9-18: reception, a stake of the revolution's "
             "Ascendant under an infortune, aversion to the Ascendant."),
            ("Row conventions.",
             "- Domain is read as plain sect: a lord of the chart's sect is in its own domain, one of the other "
             "sect in the contrary (PN IV II.3, 5 with fn 46, and PN IV II.3, 6 with fn 48); "
             "the Domain switch on the Dignities page does not reach it. "
             "The Sect table's domain is the fuller condition that switch chooses; Dykes notes that the word "
             "\"is often used to mean simply 'sect'\" (Gr. Intr. VII.1, 37, fn 23). "
             "\"westernization from the Sun\" is shown as the solar side (fn 47).\n"
             "- Aspects to the sign and to the lord are by whole sign.\n"
             "- Also read: the twelfth-parts (Gr. Intr. V.18, 3) and fn 37-41's "
             "classes of sign (Gr. Intr. VI.4, 4-6: loving, hating, hostile by aspect; PN IV IX.2, 33: matching in ascensions, in "
             "daylight, or one belt) and of degree (Gr. Intr. V.20's bright, dusky, empty and dark degrees, the editor's "
             "\"probably\"), as facts on rows [3] and [4-7]."),
            ("Not built.",
             "The delineations of II.4-II.21 are not built. No worked example exists; Figure 55 is Dykes's "
             "table."),
        ])

        st.subheader("Indicators 6-19: the fact each one reads (PN IV II.1, 11-24)",
                     help="II.1, 11-24 list the remaining fourteen indicators, in II.1, 25's order of strength.")
        with _prose():
            st.markdown("Each reads a fact from the root and the revolution and judges it in a chapter of its "
                        "own; the facts are computed here, the judgments are not.")
            st.markdown("**Facts, not judgments:** the delineation chapters behind these rows (II.6-21, V.1-8, VI.3-6, "
                        "VII.9, VIII.1-15) are not built as revolution readings; VI.3, the revolution's planets in the natal places, belongs "
                        "here with them, not in the natal Topical Planets in Houses table, whose PN IV halves paraphrase Book II's sentences as natal readings.")
        _shown_5 = pd.DataFrame(_display_rows(pn4['further_rows']))
        st.dataframe(_shown_5, hide_index=True, width='stretch',
                     height=_rows_height(14),
                     column_config=_wide_text_columns(_shown_5))
        st.caption('This row reads relationships at the revolution, names the applying planet, and distinguishes separation from aversion, counting houses from the natal Ascendant, terminal sign or revolution Ascendant for the corresponding indicator.')
        with st.expander("Indicator 15: relationship details"):
            st.dataframe(pd.DataFrame(_display_rows(_indicator_relationship_rows())), hide_index=True, width="stretch")
        _notes_expander("Row conventions of the fourteen indicators", [
            ("What each row reads.",
             "- Nine are lookups on the two charts.\n"
             "- #7 is read from the Moon's connections in her sign (II.22, below).\n"
             "- #15 reads relationships at the revolution instant, with whole-sign visibility and the "
             "Configurations page's selected connection rule and light as its limit; outside that light a "
             "phase remains descriptive, not aversion. Houses are counted from each indicator's own place "
             "(fn 129). VI.6, 38-40 orders their strength: root, terminal sign, revolution; no weighting is "
             "computed. VI.6, 45's secondary cross-scheme pairs are not read. #16 and #17 are not tracked.\n"
             "- #8 grades a transit as V.1, 2-3 does -- the degree, the "
             "bound, or only the sign.\n"
             "- #10 counts each lord from its own Ascendant (fn 128).\n"
             "- #14 and #19 "
             "count from the three places VI.5, 1 names.\n"
             "- #12 and #13 read both the terminal sign and the "
             "revolution's Ascendant, as VI.3-4 do."),
        ])

        st.subheader("The lord of the orb (PN IV VI.1)",
                     help="VI.1, 4: \"the lord of the hour in which the native was born\" is assigned to the "
                          "Ascendant and the first year; VI.1, 5-8: the next hour lord down the spheres to the "
                          "next house and the next year, and on past twelve.")
        # The planetary hours the cycle starts from are the Chart page's;
        # where that page flags its hour lord as an equal-hour
        # approximation (the Sun circumpolar), the sentence that says so
        # stands here too, beside the table.
        _hours_sentence = ("Their sequence from "
                           "the day lord at sunrise is Dykes's Figure 45 (Intro Sect. 13), which the Chart page's hour "
                           "lord follows with real sunrise and sunset, and with a flagged equal-hour approximation where "
                           "the Sun is circumpolar; Dykes notes that not everyone agrees on when the day begins.")
        with _prose():
            st.markdown("Row 5 above is this year's. The table here is VI.1, 18-19: six positions whose hour "
                        "lords are named by VI.1, 10 -- \"the lord of the hour of the house of assets\" is the "
                        "second hour lord from the natal one -- read as hour k for house k.")
            if pn4['hour_approximate']:
                st.markdown("**The natal hour lord is approximate here.** " + _hours_sentence)
        st.dataframe(pd.DataFrame(pn4['orb_rows']), hide_index=True, width='stretch',
                     height=_rows_height(len(pn4['orb_rows'])),
                     column_config=_wide_text_columns(pd.DataFrame(pn4['orb_rows'])))
        _notes_expander("The cycle of the hour lords, and the three answers to their names", [
            ("The continuing cycle.",
             "VI.1, 4: \"the lord of the hour in which the native was born\" is assigned to the "
             "Ascendant and the first year; VI.1, 5-8: the next hour lord down the spheres to the "
             "next house and the next year, and on past twelve -- \"the lord of the thirteenth hour "
             "from it belongs to the Ascendant of the root and the thirteenth year\" -- so the loop "
             "of seven runs on against the cycle of twelve and the pairing changes every twelve "
             "years. Judged \"just as you judge by means of the lord of the year\" (VI.1, 12)."),
            ("The names of the lords: three answers, and what is built.",
             "| Reading | Here |\n"
             "|---|---|\n"
             "| The continuing cycle (VI.1, 5-8): the loop of seven runs on against the cycle of twelve | Built |\n"
             "| The names fixed to the first cycle (VI.1, 10) | Shown beside the loop's planet for the same name; neither is stated for 18-19 |\n"
             "| A single-cycle version, each house keeping its first hour lord for life (Intro Figure 48, Dykes's thought) | Not built; VI.1, 8 states the loop and the loop is built |\n"
             "| The twelve-year reset of the named lords (Intro Sect. 13, \"my idea\") | Not built |\n\n"
             "VI.1, 10 fixes the "
             "name to the first cycle; VI.1, 8's assignment (\"the lord of the thirteenth hour from it "
             "belongs to the Ascendant of the root and the thirteenth year\") gives a different planet for "
             "the same name from age 12 on; both are shown, neither is stated for 18-19, and the reset "
             "Dykes proposes (Intro Sect. 13, \"my idea\") is a third answer, his own. Dykes "
             "also floats a single-cycle version in which each house keeps its first hour lord for life "
             "(Intro Figure 48), on the thought that the loop is Abu Ma'shar's own error; VI.1, 8 states "
             "the loop and the loop is built. His twelve-year \"reset\" of the named lords is, in his "
             "words, his idea, and is not built."),
            ("What PN IV presupposes: the planetary hours.",
             "What PN IV presupposes here rather than states: the planetary hours. " + _hours_sentence),
            ("Not built, and built elsewhere.",
             "The delineations of VI.1, 12-17 are not built; the seven days the "
             "lord of the orb grants (IX.7, 7-9) are method 2 on the Days and months page (This week / Today / This hour)."),
        ])

        st.subheader("The governor (PN IV IX.9, 1-10; IX.2, 4-7)",
                     help="IX.9, 1-9 name eight testimonies and IX.9, 10 the rule; IX.2, 4 gives a second, "
                          "sign-level governor for the first month.")
        with _prose():
            st.markdown(PN4_RELEASER_EXPLANATION)
            st.markdown("When both distributions are available, #4 is counted only for their shared partner -- "
                        "for each of them where two or more were met together (PN IV III.1, 50), each credited, "
                        "this app's reading; when no qualifying releaser exists, the Ascendant's share remains. "
                        "#7 is read from the Moon's connections in her sign (II.22, below).")
            st.markdown("These are \"eight special indicators to look at in the revolution of the years of "
                        "nativities\" (IX.9, 1), combining in one \"governor of the indication for the condition of "
                        "the year\" (IX.9, 10): so #2-#5 -- the two distributors, their partners and the fardar lord "
                        "-- are taken as they stand at the moment of this revolution, not at the target date, and one "
                        "revolution has one governor. The fardar lord is the one governing the revolution's year: a "
                        "return can fall minutes before the year mark the fardar's periods are counted on. The year's "
                        "indicators #2, #3 and #4 above are read the same way; the distributions' own Now and the "
                        "fardar table run on the years elapsed to the target.")
            if pn4['pn4_releaser']['note']:
                st.markdown(pn4['pn4_releaser']['note'])
        gov_rows, gov = pn4['governor']
        st.markdown(f"**IX.9:** {_display_result(gov['text'])}")
        _shown_2 = pd.DataFrame(_display_rows(gov_rows))
        st.dataframe(_shown_2, hide_index=True, width='stretch', height=_rows_height(8),
                     column_config=_wide_text_columns(_shown_2))
        _condition = pn4['governor_condition']
        _condition_how = ("the conclusions quoted, not pronounced; 13's place half (\"in a stake or in what follows a stake\") is "
                          "judged by the Alchabitius **division** in the revolution, the five degrees at the four axial degrees -- "
                          "the unit is **this app's convention** (an adopted dynamic-fitness reading), not the text's; "
                          "the row states the three parts and the qualified confidence (IX.5, 4 fn 106).")
        if is_unresolved(_condition):
            # A tied primary: IX.9, 10 names one planet "more primary than
            # the others" and the text does not break a tie, so the table
            # is drawn for each tied planet under its own name, not for the
            # alphabetically first one as the primary's (a tied opening
            # partner wraps the result once more; _condition_tables
            # unfolds both).
            # Where the tie on top is the opening partner's, the primary is
            # tied only on the routes where it is; the heading says so and
            # every table still names its planet.
            _tied = (("the primary, or the opening partner it depends on, is tied",
                      "route by route, for each planet under its own name")
                     if _condition.source == PN4_OPENING_SOURCE else
                     ("the primary, or the partner it depends on, is tied",
                      "route by route, for each planet under its own name")
                     if _condition.source == PN4_CONTACT_TIE_SOURCE else
                     ("the primary is tied", "for each of the tied planets under its own name"))
            if _condition.source == PN4_GOVERNOR_ARMS_SOURCE:
                # The arms of the open releaser name different primaries:
                # each arm's table is drawn under that arm's label, a tie
                # within an arm under each tied planet's name.
                st.markdown("**PN IV IX.9, 11-13, the condition of the primary planet, as facts** -- the primary differs "
                            "between the arms of the releaser's election, which is open on the Moon's easternness, so "
                            "the table is given arm by arm, for each planet under its own name; " + _condition_how)
            else:
                st.markdown(f"**IX.9, 11-13, the condition of the primary planet, as facts** -- {_tied[0]} "
                            "(IX.9, 10: one planet \"will be more primary than the others\", and the text does not "
                            f"break a tie), so the table is given {_tied[1]}; "
                            + _condition_how)
            for _label, _planet_rows in _condition_tables(_condition, gov['primary']):
                st.markdown(f"**{_label}**")
                _shown_3 = pd.DataFrame(_display_rows(_planet_rows))
                st.dataframe(_shown_3, hide_index=True, width='stretch', height=_rows_height(3),
                             column_config=_wide_text_columns(_shown_3))
        elif _condition:
            st.markdown(f"**IX.9, 11-13, the condition of the primary planet ({_display_result(gov['primary'][0]) if isinstance(gov['primary'], list) else _display_result(gov['primary'])}), as facts** -- "
                        + _condition_how)
            _shown_3 = pd.DataFrame(_display_rows(_condition))
            st.dataframe(_shown_3, hide_index=True, width='stretch', height=_rows_height(3),
                         column_config=_wide_text_columns(_shown_3))
        fm_rows, fm_verdict = pn4['first_month_governor']
        st.markdown(f"**IX.2, 4:** {fm_verdict}")
        st.dataframe(pd.DataFrame(fm_rows), hide_index=True, width='stretch', height=_rows_height(5),
                     column_config=_wide_text_columns(pd.DataFrame(fm_rows)))
        _notes_expander("How the governor is tallied", [
            ("The eight testimonies, and the rule.",
             "IX.9, 1-9 name eight testimonies and IX.9, 10 the rule: \"if these eight indicators "
             "would combine together in a single planet, then it alone would be the governor ... and "
             "if one of them had [only] some of the testimonies, it will be more primary than the "
             "others, and the rest of them will have a partnership with it.\""),
            ("The meaning of \"alone\".",
             "The tally runs over what is "
             "available and names a governor **alone** only when all eight are counted and combine in one "
             "planet, which is what IX.9, 10 reserves the word for. In the 71st to the 75th years of each fardar "
             "cycle (from age 70 until 75 is completed) the lord of "
             "the fardar is a node (PN IV IV.7, 24: \"the Head and Tail distribute ... when the native enters year "
             "71\"); PN IV IX.9, 10 combines the testimonies \"in a single planet\", read here as one of the seven planets, "
             "so the node is named in the fifth row and not tallied -- a reading -- and is not counted among the "
             "unavailable. Where the releaser's election is open on the Moon's easternness, testimony #3, \"the "
             "distributor from the [longevity] releaser\" (PN IV IX.9, 4), is read on each arm, and the tally with it: "
             "what the arms give alike is shown as one, what they give differently open with both."),
            ("A reading of \"the first lord\".",
             "\"The first lord\" of the revolution's Ascendant is read as its domicile lord (fn 324)."),
            ("The first month's governor (IX.2, 4).",
             "IX.2, 4 gives a second, "
             "sign-level governor for the first month: five conditions on the natal Lot, the terminal "
             "point, the revolution's Ascendant and Lot, and the sign's quadruplicity; fn 37: such a "
             "sign governs the year too. The "
             "IX.2 test is strict and most years fail it, so its five conditions are shown one by one; "
             "Dykes's fn 39 (age 39, everything in Cancer, the Moon) is the case it is checked against."),
            ("The condition of the primary planet, and what is not built.",
             "IX.9, 11-13 are shown as facts above (12 allows either arm, \"if the sign harmonized with it by nature, "
             "or it had testimony in it\": the nature arm is not read, so 12, and 13's sign half, are met on the "
             "testimony and not judged without it, never 'no'; PN IV IX.9, 12's testimony is read as a dignity of the planet's own at its "
             "degree, the triplicity by each chart's own sect, the root's by the nativity's and the revolution's by "
             "the revolution's, as the II.3 rows above read them -- PN IV reads a revolution by its own sect, \"if "
             "... the revolution was by day ... if the revolution was nocturnal\" (PN IV VIII.1, 1-2); 13's place half by the "
             "division, the convention Dykes proposes for strength language, ITA Introduction §6); IX.2, 8-11, "
             "the delineations, are not built."),
        ])

        st.subheader("The Moon's connections in her sign, and the portions of the year (PN IV II.22)",
                     help="The revolution's Moon is followed by the ephemeris "
                          "until she leaves her sign, and every perfection of body or Ptolemaic ray before that is "
                          "a connection.")
        mn = pn4['moon']
        if mn['void']:
            st.markdown(f"The revolution's Moon at {get_degree_string(mn['moon_lon'])} leaves {mn['sign']} on day "
                        f"{mn['exit_day']:.2f} **without perfecting a connection**: empty in course, so the lord of "
                        f"her house, **{mn['house_lord']}**, stands in (II.22, 4).")
        else:
            st.markdown(f"The revolution's Moon at {get_degree_string(mn['moon_lon'])} leaves {mn['sign']} on day "
                        f"{mn['exit_day']:.2f}; before that she connects with **{len(mn['connections'])}** "
                        f"planet{'s' if len(mn['connections']) != 1 else ''}, so the year "
                        f"({pn4['year_days']:.2f} days to the next revolution) is divided into "
                        f"**{len(mn['connections'])}** portion{'s' if len(mn['connections']) != 1 else ''} "
                        f"(II.22, 2). This year's lord is **{pn4['year']['lord']}**; II.22 states the division "
                        f"for a year whose lord is the Moon, and it is computed here in every year.")
            st.dataframe(pd.DataFrame(pn4['moon_rows']), hide_index=True, width='stretch',
                         height=_rows_height(len(pn4['moon_rows'])))
            st.dataframe(pd.DataFrame(pn4['portion_rows']), hide_index=True, width='stretch',
                         height=_rows_height(len(pn4['portion_rows'])))
        _notes_expander("How the Moon's connections are read", [
            ("The sentences of II.22.",
             "II.22, 1: \"the planet which the Moon connects with, so long as she is in her [current] "
             "sign\"; II.22, 2: \"if it was two planets, the year is divided into two halves; and if "
             "her connection in that sign of hers was with three planets, then that year is divided "
             "into equal thirds; and if it increased beyond that, then the year is divided according "
             "to their number\"; II.22, 3: each portion judged by \"the planet which owns the "
             "portion\"; II.22, 4: \"if the Moon was empty in course ... the lord of her house, "
             "whether it looked at her or not\"."),
            ("Read into the sentences.",
             "- a connection is a perfection by degree, of the body or a Ptolemaic "
             "ray, before she leaves the sign, with the whole-sign configuration re-checked at the moment of "
             "perfection (Gr. Intr. VII.5, 14: no out-of-sign connection);\n"
             "- the portions go to the planets in the order "
             "she connects, which II.22 does not state;\n"
             "- the division is stated for the Moon's year and is "
             "shown every year with this year's lord named;\n"
             "- \"empty in course\" is no such perfection "
             "before she leaves the sign."),
            ("Not counted, and not built.",
             "II.22, 11's rays, Lots and twelfth-parts are not counted. The judgments of "
             "II.22, 5-24 are not built. No worked example exists in PN IV."),
            ("Where else this computation is used.",
             "The "
             "same computation fills indicator #7 above and testimony #7 of the governor."),
        ])

        st.subheader("Proxies and the host of the lord of the year (PN IV II.13, 1; II.14, 1; II.22, 1-5, 23-25)",
                     help="II.14, 1 adds the distributor; "
                          "II.22, 1-5 give the Moon's list. Dykes's fn 237 reads these as proxies standing in for the "
                          "luminary.")
        with _prose():
            st.markdown("**The first proxy needs the releaser.** The first proxy in every version is the sign the "
                        "longevity releaser's distribution stands "
                        "in; this app retains Sahl's distribution for this separate proxy (IX.8, 123 defers the years). It is filled "
                        "from the releaser's distribution "
                        "(Sahl, On Nativities 1.15, on The releaser page) when that finds one, and reads "
                        "unavailable otherwise.")
        if pn4['proxies'] is None:
            st.markdown(f"This year's lord is **{pn4['year']['lord']}**, absent from the revolution.")
        else:
            st.markdown(f"This year's lord is **{pn4['year']['lord']}**.")
            st.dataframe(pd.DataFrame(pn4['proxies']), hide_index=True, width='stretch',
                         height=_rows_height(len(pn4['proxies'])),
                         column_config=_wide_text_columns(pd.DataFrame(pn4['proxies'])))
        _notes_expander("The proxies, and what each depends on", [
            ("II.13, 1, whole.",
             "II.13, 1:\n\n> \"If the Sun was the lord of the year, then the majority of that judgment in "
             "that year should be in accordance with the condition of [1] the lord of the sign in "
             "which the distribution of the lifespan from the [longevity] releaser was ..., and "
             "partnering with it in the indication is [2] the planet which is in Leo in the root of "
             "the nativity or in the revolution, and [3] the planet to which the Sun hands over the "
             "management (so long as it is in its sign), and then along with that you see [4] where "
             "the Sun is, calling upon [that] as a witness.\""),
            ("The Sun's proxies, as read.",
             "- The Sun's hand-over is read per fn 239 as the Sun's own "
             "connections before he leaves his sign, in the revolution (fn 239 notes the book does not say "
             "root or revolution), and \"hands over\" as the Sun applying to a heavier planet (Mars, Jupiter, Saturn); "
             "\"where the Sun is\" is his sign and its lord per fn 241."),
            ("The Moon's rows.",
             "- The Moon's rows are the II.22 "
             "computation above; her conditions are shown as facts and II.22, 6-10's judgment of them is "
             "not built, nor are II.13, 2 - II.21.\n"
             "- No worked example exists; fn 238 illustrates the missing "
             "part."),
        ])

        st.subheader("The turning of the houses of the root (PN IV VI.2)",
                     help="Whole-sign turning and proportional semi-arc direction are both built from each point's own natal position (PN IV VI.2, 1, 21).")
        with _prose():
            st.markdown("**Two rows for a cusp in another sign.** PN IV VI.2, 21-24: a quadrant cusp that falls in another "
                        "sign is turned both "
                        "from its house by counting and from the sign its degree falls in, and such houses get "
                        "two rows.")
        st.markdown(f"Turned by **{pn4['cycle']}** solar returns completed, a sign for each -- \"turned at the "
                    f"revolutions of years from its own position (a year for every sign)\" (PN IV VI.2, 1).")
        _shown_6 = pd.DataFrame(_display_rows(pn4['turning_rows']))
        st.dataframe(_shown_6, hide_index=True, width='stretch',
                     height=_rows_height(min(len(pn4['turning_rows']), 16)),
                     column_config=_wide_text_columns(_shown_6))
        st.markdown("**The triplicity lords examined beside the turning (PN IV VI.2, 4-5)** -- the sect light's for assets "
                    "(4; fn 13), the lords of Mars's natal sign for siblings (5: the first the older, the second the "
                    "middle, the third the younger); each lord's condition in the root and in the revolution, as the "
                    "II.3 examination prints it. fn 14's age mapping is the editor's and is not applied.")
        _shown_7 = pd.DataFrame(_display_rows(pn4['turning_triplicity_rows']))
        st.dataframe(_shown_7, hide_index=True, width='stretch',
                     height=_rows_height(len(pn4['turning_triplicity_rows'])),
                     column_config=_wide_text_columns(_shown_7))
        _notes_expander("The turning, the direction, and the twelve Lots", [
            ("PN IV VI.2, 1, whole.",
             "PN IV VI.2, 1:\n\n> \"every one of the seven planets, the twelve houses, and the twelve Lots, is "
             "turned at the revolutions of years from its own position (a year for every sign), and "
             "is directed from its degree (a year for every degree); and when any of them, by turning "
             "or by direction, reaches a sign or planetary fortune or infortune, it produces the "
             "indication of that sign or planet.\"\n\nPN IV VI.2, 2-17 say what each is turned for."),
            ("The direction \"a year for every degree\".",
             "The direction \"a year for every degree\" is proportional semi-arcs, each row saying where it "
             "stands at this age: for planets and Lots it is III.1, 12's third case (fn 16), for the cusps "
             "PN IV VI.2, 21's \"portions of the hours and the right circle\" (fn 33) -- the point's degree "
             "directed as the planets are in the Distributions tab (" + PN4_SEMIARCS_SOURCES + "). "
             "The Ascendant's and the meridian's directions are the distributions above."),
            ("Which twelve Lots: not stated.",
             "Which \"twelve "
             "Lots\" PN IV VI.2, 1 means is not stated; the formulas in fn 12-31 are Dykes's identifications from "
             "Sahl and the Great Introduction, and this app's Lots are paired to them here, with the three "
             "places they differ on the night reversal named in the row."),
            ("A substitution read from the editor.",
             "\"whichever of them had the shift in the "
             "root\" for the parents (PN IV VI.2, 8; compare 6) is read as the sect planet, per fn 16 and 19."),
            ("The triplicity lords, and what is not built.",
             "The "
             "triplicity lords of PN IV VI.2, 4-5 are the table above; the delineations are not built. No worked example exists; "
             "Figures 90-91 are Dykes's diagrams."),
        ])

    with tab_dist:
        st.subheader("The distribution from the Ascendant (the *jar bakhtar*)",
                     help="III.1, 12: the Ascendant is directed by the ascensions \"of the country in which the "
                          "native was born\" -- oblique ascensions of the birth latitude, one degree of ascension "
                          "to a year (III.1, 13). III.1, 14: the Persians gave this "
                          "particular distribution, and no other, the name *jar bakhtar*.")
        with _prose():
            st.markdown("III.1, 11: the lord of the bound reached is the distributor, "
                        "\"whether it looked at [the bound] or not\". III.1, 15-16: the most recent body or ray "
                        "met is the partner, and it holds until another body or ray is met; a ray is a point with "
                        "no orb. The text hands the management on one contact at a time (\"from the body or rays "
                        "of the first planet, to the body or rays of the other planet\", PN IV III.1, 16). Where "
                        "the direction reaches two bodies or rays at one position, at birth or later, both are "
                        "partners, read together: \"if one of them was in the management of two planets or more, "
                        "then the work in it is in accordance with their natures\" (PN IV III.1, 50). Where the "
                        "text speaks of one partner -- the seven types, the twenty-four shifts, the governor's "
                        "fourth testimony -- each is read by its own nature, and a pair of one nature gives one "
                        "type and one shift: this app's reading of III.1, 50.")
        if pn4['segments'] is None:
            st.warning("Refused at this latitude. Above the polar circle some degrees never rise, the oblique "
                       "ascension has no unique inverse, and an arc of direction from the Ascendant is not "
                       "defined.")
        else:
            _strip = generate_distribution_strip_svg(pn4['segments'], pn4['elapsed_years'], 'years',
                                                     PN4_DISTRIBUTION_SPAN_YEARS, 'The distribution from the Ascendant',
                                                     theme=WHEEL_THEME)
            st.image(_strip, width='stretch')
            st.download_button("Download this strip (SVG)", _strip, key="dl_strip_asc", mime="image/svg+xml",
                               file_name="distribution_ascendant.svg")
            cur = pn4['current']
            if cur:
                st.markdown(
                    f"**Now** (age {pn4['age']}): distributor **{cur['distributor']}**, partner "
                    f"**{pn4_result_text(cur['partner'], 'none -- the distributor acts alone')}**"
                    f" &nbsp;|&nbsp; this period runs from age {' to '.join(pn4_span_text(cur, 'years'))}"
                    f" &nbsp;|&nbsp; partner met: {_display_result(cur['partner_from'])}")
            st.dataframe(pd.DataFrame(_display_rows(pn4['distribution_rows'])), hide_index=True, width='stretch',
                         height=_rows_height(min(len(pn4['distribution_rows']), 16)),
                         column_config=_date_columns(pd.DataFrame(pn4['distribution_rows'])))
            if pn4['turning_partner']:
                st.markdown(f"**Sahl, the year of the turning and the partner:** {_display_result(pn4['turning_partner']['text'])}")
            st.caption("III.1, 23-25: at birth the partner is whatever body or ray lies between the beginning of "
                       "the Ascendant's sign and its degree; if there is none, \"the distributor without a planet "
                       "partnering with her\". III.2, 103-104 ranks partners body > opposition > square > trine > "
                       "sextile -- hard aspects above soft ones, which is the reverse of the usual intuition.")

        st.caption("Opening partners use III.1, 23–25 by analogy: the nearest preceding or coincident eligible body or ray within the sign (two or more equally near are partners together, PN IV III.1, 50), otherwise the bound lord alone, with a planet's own body and rays excluded by app convention and planets on a directed axis included.")

        st.subheader("The distribution analysed (PN IV III.2)",
                     help="III.2, 4-9: a checklist of questions about the bound the distribution stands in, answered "
                          "here as facts.")
        with _prose():
            st.markdown("**Facts and classification, not judgment:** the conditions III.2's delineation turns on -- in a "
                        "suitable condition in the root and in the revolution (III.2, 18) -- are not judged, and the prose of "
                        "III.2, 18-54 is not built.")
        if pn4['iii2_type'] is None:
            st.markdown("No current distribution to analyse (refused at this latitude, or the age is past the table).")
        else:
            t_num, t_label, t_cite = pn4['iii2_type']
            cur = pn4['current']
            # Partners met together whose natures give different types
            # carry each type in the label, partner by partner.
            _type_head = '' if t_num is None or isinstance(t_num, PN4Together) else 'type ' + pn4_result_text(t_num) + ', '
            st.markdown(f"**Static type:** {_type_head}{_display_result(t_label)} -- "
                        f"{cur['distributor']} distributing"
                        f"{', ' + pn4_result_text(cur['partner']) + ' partnering by ' + pn4_result_text(cur['partner_aspect']) if cur['partner'] is not None else ', alone'} "
                        f"({_display_result(t_cite)}).")
            st.dataframe(pd.DataFrame(pn4['iii2_checklist']), hide_index=True, width='stretch', height=_rows_height(7))
            # The window's bounds print as "At age" and the header print years
            # elapsed, three decimals truncated (the owner's ruling 75, with
            # ruling 13), so no shift prints below the window's printed start:
            # rounded, the eleventh year of the default chart (9.9999474 to
            # 10.9999491) printed 10.000 to 11.000.
            _w_from, _w_to = pn4['revolution_window']
            if pn4['iii2_transitions']:
                st.markdown(f"**Shifts inside this year of the distribution** (this revolution's year, "
                            f"{pn4_elapsed_text(_w_from)} to {pn4_elapsed_text(_w_to)} years elapsed from the "
                            f"birth hour):")
                st.dataframe(pd.DataFrame(_display_rows(pn4['iii2_transitions'])), hide_index=True, width='stretch',
                             height=_rows_height(len(pn4['iii2_transitions'])))
            else:
                st.markdown(f"**No shift of bound or management falls inside this year of the distribution** "
                            f"(this revolution's year, {pn4_elapsed_text(_w_from)} to {pn4_elapsed_text(_w_to)} "
                            f"years elapsed from the birth hour); "
                            f"the twenty-four of III.2, 55-86 do not arise.")
        if pn4.get('bound_transits') is not None:
            st.markdown("**Transits into the bound, in the revolution** (III.2, 34-35, 38, 43, 46-47, 54; III.8, 7):")
            st.dataframe(pd.DataFrame(_display_rows(pn4['bound_transits'])), hide_index=True, width='stretch',
                         height=_rows_height(len(pn4['bound_transits'])))
        _notes_expander("How the distribution is classified", [
            ("Method: the checklist, the types, the transitions, the ranking.",
             "III.2, 10-17: seven \"static\" types of distributor and partner, by "
             "fortune and infortune (Figure 66). III.2, 55-86: twenty-four transitions that can occur "
             "inside a year, by the natures of the outgoing and incoming bound lords and managers, and "
             "87-101 their twelve indications, quoted here one sentence each. III.2, 102-104 rank the "
             "three indicators: the distributor, then the partner by body, then by ray."),
            ("Classifications, and the three planets of neither nature.",
             "The Sun, Moon and Mercury are neither fortune nor infortune, and the "
             "types and transitions speak only of fortunes and infortunes, so a distribution under one of "
             "them reads \"no type by nature\" and a shift involving one \"not among the twenty-four\"; type 5 "
             "turns on conditions and is never assigned. Where the direction meets two bodies or rays at one "
             "position, both are partners (PN IV III.1, 50: \"if one of them was in the management of two planets "
             "or more, then the work in it is in accordance with their natures\"). The types and the twenty-four "
             "speak of one partner, so each partner is read by its own nature: a pair of one nature gives its one "
             "type and its one shift; a pair of a fortune and an infortune gives the type and the shift of each, all "
             "in force, each row saying which partner it is read for. A partner on both sides of a shift does not "
             "shift: the management shifts from each partner that leaves to each that comes -- from those that stay "
             "where none leaves, to those that stay where none comes -- and the same partners met again are no "
             "shift. A shift of bound is read for every partner after it, one that stays as well as one that "
             "comes, for it is numbered by who manages in the bound shifted into (\"in the management of a "
             "fortune\", PN IV III.2, 69); \"the four of them\" of PN IV III.2, 93 and 101 are counted only for a "
             "partner the management shifts to, save that a pair of one nature gives "
             "its one shift, with them where they hold. This is this app's reading of III.1, 50."),
            ("The transitions, and the transits into the bound.",
             "The transitions are read from the natal "
             "distribution above, as III.2, 105 requires; a revolutionary planet entering the bound is the "
             "table just above, each keyed by the static type to the one sentence that speaks of it "
             "(III.2, 34-35, 38, 43, 46-47, 54; III.8, 7's condition on the two lords as facts), the Sun, Moon and Mercury "
             "addressed by none, and 46-47 speaking of rays only."),
            ("Qualifications on the quoted conclusions.",
             "Every quoted indication that "
             "mentions death carries III.2, 110-111's gate: death only in the years the longevity indicator "
             "pointed out -- the years the house-master's direction reaches an infortune, on The "
             "releaser page."),
            ("No worked example.",
             "No worked example by the author; "
             "Figure 67 with fn 56 is Dykes's diagram of III.2, 33."),
        ])

        st.subheader("The distribution from the Midheaven and the fourth",
                     help="III.1, 12: \"what is in the Midheaven or the fourth is directed by the ascensions of "
                          "the right sphere\" -- right ascension, one degree to a year (III.1, 13), the lord of "
                          "the bound reached as distributor (III.1, 11) and the last body or ray met as partner "
                          "(III.1, 15-16), exactly as for the Ascendant.")
        with _prose():
            st.markdown("Right ascension has no latitude in it, so these two distributions are "
                        "defined at every latitude and are never refused.")
        for point in PN4_MERIDIAN_POINTS:
            m = pn4['meridian'][point]
            cur = m['current']
            _strip = generate_distribution_strip_svg(m['segments'], pn4['elapsed_years'], 'years',
                                                     PN4_DISTRIBUTION_SPAN_YEARS, f'The distribution from the {point}',
                                                     theme=WHEEL_THEME)
            st.image(_strip, width='stretch')
            st.download_button("Download this strip (SVG)", _strip, key=f"dl_strip_{point[:4].lower()}",
                               mime="image/svg+xml", file_name=f"distribution_{point[:4].lower()}.svg")
            if cur:
                st.markdown(
                    f"**{point}** at {get_degree_string(m['degree'])} -- **now** (age {pn4['age']}): distributor "
                    f"**{cur['distributor']}**, partner **{pn4_result_text(cur['partner'], 'none -- the distributor acts alone')}**"
                    f" &nbsp;|&nbsp; this period runs from age {' to '.join(pn4_span_text(cur, 'years'))}"
                    f" &nbsp;|&nbsp; opened standing on {get_degree_string(cur['from_lon'])}")
            else:
                st.markdown(f"**{point}** at {get_degree_string(m['degree'])} -- age {pn4['age']} is past the "
                            f"{PN4_DISTRIBUTION_SPAN_YEARS:g}-year table")
            st.dataframe(pd.DataFrame(_display_rows(pn4['meridian_rows'][point])), hide_index=True, width='stretch',
                         height=_rows_height(min(len(pn4['meridian_rows'][point]), 12)),
                         column_config=_date_columns(pd.DataFrame(pn4['meridian_rows'][point])))
        with _prose():
            st.markdown("**What PN IV does not supply here, stated rather than filled in.**")
        _notes_expander("Five things the book leaves unsaid of this distribution", [
            ("No topic from the author.",
             "Abu Ma'shar gives this "
             "distribution no topic: \"actions, profession, and life projects\" is Dykes (Appendix A, "
             "p. 673) and fn 4's al-Qabisi IV.12 (ITA VIII.2.2) -- editors' notes, not a sentence of the book."),
            ("Not among the year's indicators.",
             "It is "
             "not among the year's indicators: II.2, 6-7 and 12-13 name the Ascendant's and the releaser's "
             "distributions only, so it does not enter the indicators table above."),
            ("No worked example.",
             "No worked example of "
             "a meridian direction exists in PN IV -- III.1, 19-45 directs the Ascendant only -- so this "
             "app's directions are checked by arithmetic and against the editor's four-minutes-a-degree animation "
             "(Appendix A), not against the author's numbers."),
            ("The partner at birth, by analogy.",
             "The partner-at-birth rule of III.1, 23-25 "
             "is worded for the Ascendant and is carried here by analogy."),
            ("\"In\", read as on the axial degree itself.",
             "III.1, 12 assigns \"the Ascendant "
             "and the things in it\" to the oblique ascensions and \"what is in the Midheaven or the fourth\" to "
             "the right ascensions: \"in\" is read as **on the axial degree itself**, "
             "recognised with a numerical tolerance (floating-point equality), not an astrological "
             "orb -- no 3 degrees, no 5, no band; the Alchabitius division and the five-degree carry-over play no "
             "part in choosing the method. A planet on one of the three degrees is directed as that degree is, "
             "below; every other planet is \"what is not in these three positions\", the third case, "
             "directed by proportional semi-arcs in the next section. The Descendant is not one of the three "
             "positions (fn 15). Fn 14 reads \"the fourth\" as the IC degree itself."),
        ])
        st.subheader("The planets, each with its measure under PN IV III.1, 12",
                     help="A planet **on** an axial degree is directed as that degree is. Every "
                          "other planet is the third case, whose method PN IV defers to a book it does not "
                          "reproduce.")
        # The three positional cases from the engine's own rows (the same
        # rows the Fardar and ages page tabulates), the formula on a line
        # of its own, and the definitions and sign conventions beneath it.
        _cases = "| Point directed | Measured in |\n|---|---|\n" + "\n".join(
            f"| {r['Point directed']} | {r['Measured in']} |" for r in PN4_ASCENSION_ROWS)
        _notes_expander("The third case: proportional semi-arcs", [
            ("III.1, 12, whole.",
             "III.1, 12:\n\n> \"the Ascendant and the things in it are directed by degrees of ascensions of the "
             "country in which the native was born, while what is in the Midheaven or the fourth is "
             "directed by the ascensions of the right sphere, and what is not in these three positions "
             "is directed according to what we stated in our book [on that topic]\"."),
            ("The three positional cases.",
             _cases + "\n\nA planet **on** an axial degree is directed as that degree is."),
            ("The formula.",
             "Every "
             "other planet is the third case, whose method PN IV defers to a book it does not "
             "reproduce: Ptolemy's method as Dykes identifies it (PN IV III.1, 10 fn 13; PN IV III.1, 12 fn 16; PN IV VI.2, 21 fn 33), "
             "proportional semi-arcs, as al-Qabisi states it (Introduction IV, ITA VIII.2.2) and Dykes "
             "works it (ITA Appendix E): the significator's distance from the meridian, in proportion "
             "to its semi-arc, is carried to the promittor's semi-arc, and what the promittor has "
             "still to travel is the arc -- PromMD - (SigMD / SigSA) * PromSA -- a degree of it a year "
             "(PN IV III.1, 13).\n\n`PromMD - (SigMD / SigSA) * PromSA`"),
            ("Definitions.",
             "Here the planet's **degree** is the significator (latitude 0, as the two other "
             "cases direct degrees and as al-Qabisi's tables probably did: Appendix E fn 27), the bound starts, "
             "bodies and rays the promittors, the distributor and partner as in every distribution "
             "(III.1, 10-11, 15-16)."),
            ("Sign conventions.",
             "The meridian distance is signed, positive before the meridian in "
             "primary motion; the meridian and the semi-arcs are those of the significator's side of "
             "the horizon, the promittor's taken from the same meridian even when it stands on the "
             "other side; a promittor already past the proportional place comes round after a "
             "revolution and falls outside the table."),
            ("Not used, and not built.",
             "Al-Qabisi's join across quarters (IV.12c, in ITA VIII.2.2), for two points in different quarters: direct to the angle "
             "that comes next, then from that angle to the other point, and add the two arcs. It is "
             "not used: this app's one formula, with the meridian distance signed, gives the arc in every "
             "quarter, and this app treats the join as an approximation of it. Converse directions are not built."),
        ])
        for ap in pn4['angle_planets']:
            if ap['axis'] is None:
                st.markdown(f"**{ap['planet']}** at {get_degree_string(ap['degree'])}, {ap['where']}: its degree by "
                            f"{ap['how']}"
                            + (f" -- now: distributor **{ap['current']['distributor']}**, partner "
                               f"**{pn4_result_text(ap['current']['partner'], 'none')}**" if ap['current'] else '') + ":")
            else:
                st.markdown(f"**{ap['planet']}** on the degree of {ap['where']}, by the {ap['how']}"
                            + (f" -- now: distributor **{ap['current']['distributor']}**, partner "
                               f"**{pn4_result_text(ap['current']['partner'], 'none')}**" if ap['current'] else '') + ":")
            if ap['segments'] is None:
                st.warning(PN4_SEMIARCS_REFUSED if ap['axis'] is None
                           else "Refused at this latitude: the ascension has no unique inverse there.")
                continue
            st.dataframe(pd.DataFrame(_display_rows(ap['rows'])), hide_index=True, width='stretch',
                         height=_rows_height(min(len(ap['rows']), 8)),
                         column_config=_date_columns(pd.DataFrame(ap['rows'])))
            if ap['terms']:
                st.markdown(f"The arc and its terms for {ap['planet']} ({PN4_SEMIARCS_SOURCES}):")
                # The promittor cell is typed where two contacts opened the
                # period at once: the page boundary's words, as for the rows above.
                st.dataframe(pd.DataFrame(_display_rows(ap['terms'])), hide_index=True, width='stretch',
                             height=_rows_height(len(ap['terms'])))


def page_releaser():
    if not chart_ok:
        _recovery_panel("The releaser")
        return
    st.header("The releaser")
    _chart_strip(counts_from_the_ascendant=True)
    # As on the other Prediction pages: the frame, then (after the scope
    # line) what else the page applies. The second sentence points to the
    # Fardar and ages page's "What Persian Nativities IV does not settle",
    # whose rows on the releaser, the greater years and directing a point
    # other than the Ascendant are this page's.
    st.caption("The frame of this page is Sahl, *On Nativities*, cited as chapter, sentence. "
               "What *Persian Nativities* IV leaves open here (the choice of releaser and house-master, "
               "the house-master's years, and how the releaser is directed) is listed at the foot of the "
               "Fardar and ages page.")
    _sources_scope_line()
    st.caption("This page also applies PN IV's testimony #3 and turning of the house-master; al-Qabisi's "
               "proportional semi-arcs; Sahl's *Introduction*'s praised places and heart; the *Great "
               "Introduction*'s solar bands; Alchabitius divisions; Valens's fullness degree (in "
               "al-Qabisi); and, with the supplement, Abu 'Ali's ladder where Sahl is silent and, for display, "
               "his and 'Umar's additions and subtractions.")
    _year_under_examination("Releaser")

    # --- SAHL: the releaser and the house-master (2026-09-10) ---
    st.subheader("The releaser and the house-master (Sahl, *On Nativities* 1.15-1.16, 1.20)",
                 help="The choice here follows Sahl. PN IV lists the five candidates (III.3, 1); IX.8, 123 defers "
                      "the years to another book, rather than expressly deferring this choice.")
    # The method in one paragraph, from the sentences the readings note
    # below states in full; then the one qualification every result here
    # carries. The three notes after the results hold the readings whole.
    with _prose():
        st.markdown("PN IV defers the years, rather than expressly the choice of releaser, to another book: "
                    "\"the book which we worked on concerning nativities\" (IX.8, 123), his *Book of the "
                    "Judgments of Nativities* (Bodleian Hunt. 546, fn 315), not in hand, and not the *Great "
                    "Introduction*, which has only the Lot of the releaser.")
        st.markdown("Nawbakht's procedure in 1.15: by day the Sun, then the meeting, then the "
                    "Ascendant; by night the Moon, then the fullness, then the Lot of Fortune, then the Ascendant. "
                    "The places: \"a stake or what follows a stake\" (1.15, 6-16) is read as a test of the planet's power and "
                    "counted by the Alchabitius divisions with the five-degree allowance at the four axial degrees "
                    "only; the Lot of Fortune (a candidate by night, 1.15, 14) has no dynamic angularity and is "
                    "tested by its whole-sign place; the years the house-master grants are granted from "
                    "1.20, 7-34 read in full.")
        st.markdown("**Readings made here, each one Sahl leaves open.**")
        st.markdown("For dignity lords and fortunes, this page counts same-sign presence or a whole-sign sextile, "
                    "square, trine, or opposition as looking, and treats at least one fortune as sufficient for "
                    "1.15, 16; unrestricted same-sign looking and the one-fortune threshold are declared "
                    "interpretations of the supplied text.")
        st.markdown("The special bound-lord preference (1.20, 4) requires the releaser and its actual bound lord "
                    "in the natal rising sign; the five-degree strength allowance does not apply to this preference.")
    rel = pn4['releaser']
    # An election open on the Moon's orientality (1.20, 6; 1.22, 1-8) comes
    # from the engine as UnresolvedResults carrying both arms: the verdict,
    # the candidates' cells and the ranking (one block per arm) are shown as
    # the page's other unresolved results are, never as one name.
    _rel_open = 'orientation_alternatives' in rel
    st.markdown(f"**{_display_result(rel['verdict'])}**")
    _shown_cands = pd.DataFrame(_display_rows(rel['candidates']))
    st.dataframe(_shown_cands, hide_index=True, width='stretch',
                 height=_rows_height(len(rel['candidates'])),
                 column_config=_wide_text_columns(_shown_cands))
    if rel['ranking']:
        st.markdown("**The house-master under each arm of the Moon's easternness** (1.20, 6; 1.22, 1-8) -- the first row "
                    "of each arm is that arm's house-master:" if _rel_open else
                    "**The lords looking at the releaser, ranked** (1.15, 13; 1.20, 2-5) -- the first is the house-master:")
        st.dataframe(pd.DataFrame(rel['ranking']), hide_index=True, width='stretch',
                     height=_rows_height(len(rel['ranking'])))
    _sl = pn4['short_life']
    _sl_head, _sl_sep, _sl_rest, _sl_label = _short_life_headline(_sl)
    st.markdown(f"**{_sl_head}**{_sl_sep}{_sl_rest}")
    _shown_4 = pd.DataFrame(_display_rows(_sl['rows']))
    st.dataframe(_shown_4, hide_index=True, width='stretch', height=_rows_height(7),
                 column_config=_wide_text_columns(_shown_4))
    if pn4['hm_years']:
        _y = pn4['hm_years']
        _j = pn4['hm_years_jn']
        _conditional_j = (_j if _j and isinstance(_j.get('result'), UnresolvedResult) else None)
        _years_text = _display_result(
            _conditional_j['result']
            if _conditional_j and READING_DEPTH == READING_DEPTH_OPTIONS[1]
            else _y['text'])
        st.markdown(f"**The house-master's years** (1.20, 7-34, Nawbakht -- the section "
                    f"1.23, 68, Masha'allah, sends the reader to): **{_years_text}**.\n\nPlaced by division "
                    f"{_display_result(_named_empty_arms(_y['division'], SAHL_NO_HOUSE_MASTER))} (the **power** unit).\n\nThese are the years the infortunes may cut off "
                    f"(1.23, 53 and 61) and the input PN IV III.2, 110-111's gate names (\"only if those years matched the years of "
                    f"the lifespan which his indicator in the root had already pointed out\").")
        if isinstance(_y['grade'], UnresolvedResult):
            st.markdown("The supplied passages do not define the Moon’s orientality, so any grant or reduction that depends on it remains unresolved.")
        for _f in _y['flags']:
            st.markdown(f"- {_f}")
        _notes_expander("How 1.20 is read here", _sahl_1_20_readings_sections(_y['readings']))
        if ((_y['grade'] is None or isinstance(_y['grade'], UnresolvedResult)) and _j
                and READING_DEPTH == READING_DEPTH_OPTIONS[1]):
            if isinstance(_j['result'], UnresolvedResult):
                st.markdown(f"**The Sahl-first result, with the supplement's ladder used only in a silent alternative** "
                            f"({_j['citation'].replace('Sahl, On Nativities ', '')}): **{_display_result(_j['result'])}**.")
            else:
                st.markdown(f"**Where 1.20 is silent, the supplement's ladder** ({_j['citation']}): "
                            f"**{_display_result(_j['text'])}**. The place: \"{_j['jn']}\"")
                for _step, _sent in _j['steps']:
                    st.markdown(f"- {_step}: \"{_sent}\"")
                if _j['table_note']:
                    st.markdown(f"- {_j['table_note']}")
                for _u in _j['umar']:
                    st.markdown(f"- {_u.replace('<', chr(92) + '<')}")
            # The engine's note on the ladder: its first paragraph -- whose
            # ladder this is, and that Sahl's grade is never overridden --
            # visible at reading width; the rest under their headings.
            _jn_sections = _jn_years_note_sections()
            with _prose():
                st.markdown(f"**{_jn_sections[0][0]}** {_jn_sections[0][1]}")
            _notes_expander("The ladder's steps, this app's definitions, and the sources", _jn_sections[1:])
    # The stand-in is drawn for a chart with no releaser, and on an election
    # open on the Moon's easternness for the arm with none, under that arm's
    # label: that arm's verdict above promises the Moon "below".
    _standin_arm = pn4['standin_arm']
    if rel['releaser'] is None or _standin_arm is not None:
        st.markdown(f"**The stand-in{', ' + _standin_arm if _standin_arm else ''} (1.32, 11-14, "
                    "al-Andarzaghar).** "
                    + ("On that arm of the election there is no releaser, so the stand-in is drawn as for a chart with "
                       "none; nothing in it depends on the Moon's easternness. " if _standin_arm else "")
                    + "The Ascendant's "
                    "distribution on the Revolutions page, \"from the Ascendant\", is \"the first of them\" (13); the Moon, "
                    "\"then the Moon\", directed from her natal degree to the infortunes by the "
                    "same ascensional operation (1.32, 12: \"if you directed the Sun or Moon in their courses to the "
                    "infortunes ... it kills, whichever of these four connects first with the infortune\"; 14: "
                    "\"if the fortunes are not looking at it\" -- the aspect of the fortunes is not judged here):")
        st.caption("The Sun target in 1.23, 2 belongs to the house-master, not this stand-in. "
                   "This supports Sahl's fallback and is excluded from PN IV testimonies #3 and #4.")
        if pn4['standin_moon'] is None:
            st.warning("Refused at this latitude, as every direction by the oblique ascension is: it has no unique inverse there.")
        elif pn4['standin_moon']:
            st.dataframe(pd.DataFrame(pn4['standin_moon']), hide_index=True, width='stretch',
                         height=_rows_height(len(pn4['standin_moon'])),
                         column_config=_date_columns(pd.DataFrame(pn4['standin_moon'])))
        else:
            st.markdown("No target within the span for the Moon.")
    _syz = pn4['syzygies']
    st.markdown(f"The meeting (the last New Moon before birth) was at **{get_degree_string(_syz['meeting']['longitude'])}** "
                f"on {pn4_datetime_from_jd(_syz['meeting']['jd']):%Y-%m-%d} UT ({pn4_ut_calendar_note(_syz['meeting']['jd']).split(' (')[0]}); "
                f"the fullness (the last Full Moon) at **{get_degree_string(_syz['fullness']['longitude'])}** on "
                f"{pn4_datetime_from_jd(_syz['fullness']['jd']):%Y-%m-%d} UT ({pn4_ut_calendar_note(_syz['fullness']['jd']).split(' (')[0]}), "
                f"the degree of {_syz['fullness']['degree_of']}.")
    if is_unresolved(rel['longitude']):
        st.markdown(f"**The releaser is not distributed**: {_display_result(_named_empty_arms(rel['releaser'], SAHL_NO_RELEASER))}. The distribution "
                    "(1.15, 22; 1.18, 20-21) needs one releaser.")
    elif rel['longitude'] is not None:
        st.markdown(f"**The releaser distributed** (1.15, 22; 1.18, 20-21): {rel['releaser']} at "
                    f"{get_degree_string(rel['longitude'])} directed through the bounds by the ascensions of the "
                    f"birth latitude, as the Ascendant is on the Revolutions page's Distributions tab"
                    + (" -- and here the releaser IS the Ascendant, so this is that distribution again." if rel['releaser'] == 'the Ascendant' else '.'))
        if pn4['releaser_segments'] is None:
            st.warning("Refused at this latitude, as the Ascendant's distribution is: the ascension has no unique inverse there.")
        else:
            _rstrip = generate_distribution_strip_svg(pn4['releaser_segments'], pn4['elapsed_years'], 'years',
                                                      PN4_DISTRIBUTION_SPAN_YEARS, 'The distribution from the releaser',
                                                      theme=WHEEL_THEME)
            st.image(_rstrip, width='stretch')
            st.download_button("Download this strip (SVG)", _rstrip, key="dl_strip_releaser", mime="image/svg+xml",
                               file_name="distribution_releaser.svg")
            rcur = pn4['releaser_current']
            if rcur:
                st.markdown(
                    f"**Now** (age {pn4['age']}): distributor **{rcur['distributor']}**, partner "
                    f"**{pn4_result_text(rcur['partner'], 'none -- the distributor acts alone')}**, the direction standing in "
                    f"**{pn4['releaser_stand']['sign']}** (lord {pn4['releaser_stand']['lord']}) -- this feeds the "
                    f"luminary proxies on the Revolutions page. This is Sahl's local-ascension comparison, not testimony #3.")
            else:
                st.markdown(f"Age {pn4['age']} is past the {PN4_DISTRIBUTION_SPAN_YEARS:g}-year table.")
            st.dataframe(pd.DataFrame(_display_rows(pn4['releaser_rows'])), hide_index=True, width='stretch',
                         height=_rows_height(min(len(pn4['releaser_rows']), 12)),
                         column_config=_date_columns(pd.DataFrame(pn4['releaser_rows'])))
    st.markdown(PN4_RELEASER_EXPLANATION)
    _pdir = pn4['pn4_releaser']
    # What the governor counts: the releaser's distribution AT THE
    # REVOLUTION'S MOMENT (IX.9, 1; IX.9, 10; `releaser_sr` in the bundle),
    # not at the target date. The target's reading stays as the Now. The
    # line stands whenever the governor counts #3, so at the table's end --
    # the revolution inside the 120 years, the target past them -- the page
    # says both which the governor counts and that the Now is past it (F2-35,
    # lane F2's re-check 35). A target inside the table always has its
    # revolution inside it too, so the old clause for a revolution past
    # the table inside this branch could never print, and is gone (F2-41).
    # `releaser_sr` exists only where the releaser's distribution does, so it
    # alone decides; the identity is never asked for a truth value (an open
    # election's is an UnresolvedResult, which has none).
    _rsr = pn4['releaser_sr']
    if _rsr is not None:
        _rev_from = pn4['revolution_window'][0]
        st.markdown(f"**PN IV testimony #3:** {_pdir['identity']}, by {_pdir['method']}, at the revolution's moment, "
                    f"{pn4_elapsed_text(_rev_from)} years elapsed from the birth hour: "
                    f"distributor **{_rsr['distributor']}**, partner **{pn4_result_text(_rsr['partner'], 'none')}** "
                    f"for #4 -- what the governor on the Revolutions page counts. "
                    + (f"Now, at {pn4_elapsed_text(_pdir['elapsed'])} years elapsed: distributor "
                       f"**{_pdir['distributor']}**, partner **{pn4_result_text(_pdir['partner'], 'none')}**."
                       if _pdir['status'] == 'available' else
                       f"Now, at {pn4_elapsed_text(_pdir['elapsed'])} years elapsed, the direction is past the "
                       f"{PN4_DISTRIBUTION_SPAN_YEARS:g}-year table."))
        if _pdir['status'] == 'available':
            st.dataframe(pd.DataFrame(_display_rows(_pdir['rows'])), hide_index=True, width='stretch', height=_rows_height(8),
                         column_config=_date_columns(pd.DataFrame(_pdir['rows'])))
    else:
        st.markdown(_pdir['note'])
        # An election open on the Moon's easternness (R4): the governor
        # reads #3 on each arm, from that arm's releaser directed as a
        # settled one is (PN IV III.1, 12) and read at the revolution's
        # moment (`releaser_arms` in the bundle). Each arm's table is drawn
        # here under its arm's label, as the settled releaser's is above,
        # and the export files them with the same labels: display only, no
        # arm chosen (the follow-ups of 2026-10-05, K-28).
        _arms = _releaser_arm_directions()
        if _arms:
            st.markdown("Each arm's releaser, so directed, is shown below under its arm; neither arm is chosen.")
        for _arm_label, _arm_dir, _arm_sr in _arms:
            if _arm_sr is not None:
                st.markdown(
                    f"**{_arm_label}:** {_arm_dir['identity']}, by {_arm_dir['method']}, at the revolution's moment, "
                    f"{pn4_elapsed_text(pn4['revolution_window'][0])} years elapsed from the birth hour: "
                    f"distributor **{_arm_sr['distributor']}**, partner **{pn4_result_text(_arm_sr['partner'], 'none')}** "
                    f"for #4 -- what the governor on the Revolutions page counts on this arm. "
                    + (f"Now, at {pn4_elapsed_text(_arm_dir['elapsed'])} years elapsed: distributor "
                       f"**{_arm_dir['distributor']}**, partner **{pn4_result_text(_arm_dir['partner'], 'none')}**."
                       if _arm_dir['status'] == 'available' else
                       f"Now, at {pn4_elapsed_text(_arm_dir['elapsed'])} years elapsed, the direction is past the "
                       f"{PN4_DISTRIBUTION_SPAN_YEARS:g}-year table."))
                if _arm_dir['status'] == 'available':
                    st.dataframe(pd.DataFrame(_display_rows(_arm_dir['rows'])), hide_index=True, width='stretch',
                                 height=_rows_height(8), column_config=_date_columns(pd.DataFrame(_arm_dir['rows'])))
            else:
                # Past the table (or refused at this latitude) the arm has no
                # reading at the revolution; its line still names the arm's
                # releaser and how it is directed, as the lead sentence says
                # each arm's line does, and ends as a sentence. An arm with
                # no releaser has only its note.
                _arm_note = str(_arm_dir['note'])
                _arm_note = _arm_note if _arm_note.endswith('.') else _arm_note + '.'
                st.markdown(f"**{_arm_label}:** {_arm_dir['identity']}, by {_arm_dir['method']}: {_arm_note}"
                            if _arm_dir.get('identity') else f"**{_arm_label}:** {_arm_note}")
    _notes_expander("Place tests and candidate selection", [
        ("The placement convention.",
         "| Point or test | Convention |\n"
         "|---|---|\n"
         "| The places: \"a stake or what follows a stake\" (1.15, 6-16) | A test of the planet's power, counted by the Alchabitius divisions with the five-degree allowance at the four axial degrees only |\n"
         "| The Lot of Fortune (a candidate by night, 1.15, 14) | Its whole-sign place; it has no dynamic angularity |\n"
         "| The meeting's and the fullness's degrees (1.15, 6-8, 12) | The division, an open reading; they are neither planet nor Lot |\n"
         "| \"In good places\" for the Ascendant's lord (1.15, 16) | Sahl's seven praised places, counted by whole-sign place; the identification is an interpretation |\n\n"
         "The places: \"a stake or what follows a stake\" "
         "(1.15, 6-16) is read as a test of the planet's **power** and counted by the Alchabitius divisions with the "
         "five-degree allowance at the four axial degrees only -- a planet 0-5 degrees past the Ascendant, "
         "Midheaven, setting degree or fourth into the cadent division keeps the stake's power, measured from "
         "the axial degree, in longitude -- a proxy, though al-Qabisi's own unit: his rule reads \"five "
         "equal degrees\", the zodiac's (ITA VIII.1.3, al-Qabisi IV.4). The warrant for the unit is the "
         "translator's convention, adopted here: Dykes proposes it as his own solution -- whole signs for "
         "topics, quadrant divisions for power (ITA Introduction §6) -- and Alchabitius, and the five degrees "
         "at the four axial degrees only, are the course's (Lesson 3, A Chart Tour, §4-5; the Course Glossary "
         "s.v. Advancement), Alchabitius being this app's choice among the quadrant systems he names; the texts "
         "in hand give the dispatch: Carmen p. 108 fn 187, \"Dorotheus ... is using dynamic divisions to speak "
         "of the planets' power, because one can only move from a stake to a decline by primary motion\"; "
         "with fn 109 on On Nativities 1.15, 6 agreeing (\"quadrant divisions, not whole signs\"). These texts' own "
         "vocabulary counts **signs** -- Introduction 2, 31-35 defines the stakes, \"what follows the stakes\" and "
         "the falling places as counted signs, and On Nativities 1.20, 10 says \"the sign of the west\" -- so the division "
         "reading is the translator's, not Sahl's or Nawbakht's; 1.18, 19 (\"its strength will be in the "
         "Ascendant ... and likewise in all of the houses\") is about strength and is read as the four "
         "stakes; Aphorism #44 and 1.22, 9 witness the five degrees, not the house system. Al-Qabisi, in his own "
         "releaser procedure, states the same five degrees for every house -- before the degree of the "
         "Ascendant \"or any house\" (ITA VIII.1.3, al-Qabisi IV.4) -- and is the quadrant witness for that "
         "procedure: he looks for the releaser in the angles and their followers as the twelve houses are "
         "calculated through the degrees of the Ascendant's hours, a different author's method; here the five "
         "degrees stay at the four stakes and the places are Sahl's. The Lot of Fortune "
         "(a candidate by night, 1.15, 14) has no dynamic angularity and is tested by its whole-sign place. "
         "The meeting's and the fullness's degrees (1.15, 6-8, 12) are neither planet nor Lot: the division is "
         "used for them, an open reading. The day list is the five places 1.15, 6 names, the night list every "
         "stake and succedent."),
        ("The order of candidates by sect.",
         "| Sect | Candidates, in order |\n"
         "|---|---|\n"
         "| Day | the Sun, the meeting, then the Ascendant |\n"
         "| Night | the Moon, the fullness, the Lot of Fortune, then the Ascendant |\n\n"
         "Each needs its place -- "
         "by day \"the Ascendant, the Midheaven, the house of hope, or ... the stake of the "
         "west, or ... the eighth\" (6), by night \"a stake or what follows a stake\" (11) -- "
         "and \"the lord of the bound, house, exaltation, triplicity, or image looking at\" it "
         "(11); \"that one ... which is looking at the releaser, is the house-master\" (13). "
         "The day chart consults the Sun, the meeting, then the "
         "Ascendant (1.15, 9: \"if the meeting and the Sun were both falling, then the releaser at that time "
         "will be the Ascendant\"); the night chart the Moon, the fullness, the Lot, then the Ascendant "
         "(10-14). 1.15, 15 lists all five before the Ascendant and is read as the summary of the two lists; "
         "read as a procedure it would consult the other sect's candidates first, which changes the releaser "
         "in about one day chart in seven. The meeting's gate (1.15, 8) states a place test only; the "
         "looking-lord test this app applies to it is supplied from 15's general wording (a reading). "
         "In the same way 16's test -- \"the Ascendant being looked at by the fortunes, and the lord of the "
         "Ascendant in its own house or exaltation, or in its own bound, triplicity, or image, in good "
         "places\" -- is applied to the Ascendant that 9 names, a reading carried from 15-16: 15's premise, "
         "the Sun and the meeting falling, is 9's own case, and 16 is the sentence that says what the "
         "Ascendant then needs. When the Sun or the meeting was in place but unseen, 9's premise is not met "
         "and the chart reaches the Ascendant by 15 itself, so 16 follows it directly. A day chart can "
         "therefore end with no releaser, \"the native does not have a foundation for his lifespan\" (16); its "
         "Ascendant is still directed, as al-Andarzaghar's stand-in (1.32, 11, 13), and the verdict names, with "
         "16, the sentence that sent the chart to the Ascendant: 9 when the Sun and the meeting both fall, 15 "
         "when either was in place but unseen."
         # Where the Ascendant passed 16's test the verdict names the
         # releaser and no sentence, so the appended line says which
         # sentence reached it rather than point at the verdict (F6-T3,
         # lane F6's third re-check).
         + ((" On this chart the Ascendant was reached by 1.15, 9." if rel['releaser'] == 'the Ascendant'
             else " On this chart that sentence is 1.15, 9.") if rel.get('both_falling')
            else (" On this chart the Ascendant was reached by 1.15, 15." if rel['releaser'] == 'the Ascendant'
                  else " On this chart that sentence is 1.15, 15.")
            if rel['sect'] == 'Diurnal' and rel['releaser'] in (None, 'the Ascendant')
            else "")),
        ("Not applied, and named.",
         "\n".join(f"- {c} ({t})" for c, t in SAHL_RELEASER_NOT_APPLIED)),
    ])
    _notes_expander("Lunations, looking, and the house-master", [
        ("The meeting and the fullness, and the fullness's degree.",
         "The meeting is the last New Moon and the "
         "fullness the last Full Moon before birth; the fullness's degree is the luminary that was above the "
         "earth at the Full Moon: 1.7, 2 (\"take the portion of whichever of the two luminaries "
         "was above the earth\"), stated there for the Ascendant's degree and applied here by the same word, "
         "\"portion\" (1.15, 12); when both or neither is above the earth this app takes the Moon's degree. "
         "Al-Qabisi reports three opinions on the fullness's degree (ITA VIII.1.2, al-Qabisi IV.3): Ptolemy's, "
         "the degree of the luminary that was above the earth; certain sages', that when one luminary is on "
         "the eastern degree and the other on the western, the eastern degree is the prevention's; and "
         "Valens's, the Moon's degree. The Moon default is Valens's; the sages' tie rule is named here and "
         "not adopted."),
        ("Looking.",
         "For dignity lords and fortunes, this page counts same-sign presence or a whole-sign sextile, "
         "square, trine, or opposition as looking, and treats at least one fortune as sufficient for "
         "1.15, 16; unrestricted same-sign looking and the one-fortune threshold are declared "
         "interpretations of the supplied text. The rising-sign preference is separately 1.20, 4."),
        ("A candidate as its own house-master.",
         "A candidate is not its own house-master except in 1.16's four "
         "signs. 1.16: the Sun in Aries or Leo, the Moon in Taurus or Cancer, is both."),
        ("The triplicity lord.",
         "The triplicity lord is the lord of the sect."),
        ("The lords ranked.",
         "1.20, 2-4 rank the lords: bound, house, exaltation, triplicity, image; two shares beat one; the "
         "bound lord in the Ascendant with the releaser beats all."),
        ("The eastern lord with a share in the Ascendant.",
         "1.20, 6: \"if you found the releaser in a good position, and its lord eastern and having a share in the "
         "Ascendant (even if it was in the second from it, not looking at it), then it will assume the responsibility "
         "of being the house-master with it, unless in that nativity there was a planet preferable to it\" -- a "
         "candidate in the places with no lord looking keeps its standing when one of its dignity lords is eastern "
         "with a share (any of the five) at the Ascendant's degree, and that lord is the house-master; a looking "
         "lord, being preferable, comes first. 1.22, the chapter that defines easternness, defines it for the "
         "superiors (1-6) and the inferiors (7-8) by the degrees between each of them and the Sun, and the Moon is "
         "not among them. So the Moon cannot be that lord on her easternness alone: where she is the lord the rule "
         "would reach, the election is left open with both arms, as her years are under 1.20, 7-34. For the five "
         "planets, \"eastern\" in 1.20, 6 is read by those degrees, as Sahl writes them: Saturn and Jupiter 6° or "
         "more earlier in the zodiac than the Sun (\"if there were 6° between Saturn and Jupiter and the Sun, then "
         "they are considered to be eastern ... but if they were less than that, they will not be fit\", 1.22, 1); "
         "Mars 18° (\"he does not easternize until there are 18° between him and the Sun\", 1.22, 3); Venus and "
         "Mercury direct and 12° (\"Venus and Mercury are eastern [when] direct in course before rising, or in front "
         "of the Sun ([he being] in the west), and there are 12° between them and the Sun\", 1.22, 7), so a "
         "retrograde or stationary Venus or Mercury is not eastern here. 1.22, 7's \"or in front of the Sun ([he being] in "
         "the west)\" names the evening side: in Sahl I \"in front of the Sun\" is a later degree than the Sun "
         "(\"western (that is, in front of the Sun)\", Fifty Aphorisms #42, 82, with fn 49: \"in a later degree than "
         "the Sun, so as to set after him\", Sahl I p. 86), and \"he\" is the Sun. The 12° that 7 calls eastern is "
         "the morning's; for the evening side 1.22, 8 gives 15°: \"if there were 15° between them and the Sun, they "
         "will have gone out of the rays and become western [risers]\" (Sahl I pp. 305-306, with Sahl I Figure 54), as "
         "BA II.2 has 12° \"in the dawn rising\" and 15° \"in the west\" (PN I p. 21). So a Venus or Mercury later in "
         "the zodiac than the Sun is western, not eastern, for 1.20, 6. Nor is Saturn, Jupiter or Mars gone "
         "retrograde: \"[once eastern], the stars will increase in power and be fit until they go retrograde: for when "
         "they go retrograde they are corrupted\" (1.22, 5), and of the unfit 1.22, 4 says \"they will not be fit at "
         "that time to be the house-master, nor for the distribution of life\". A superior at its station has not "
         "gone retrograde, by the app's one station rule. The candidate's row names the sentence, the planet's motion "
         "and its distance from the Sun, and names a lord earlier in the zodiac than the Sun whom 1.22 does not make "
         "eastern. The same word is read otherwise where other sentences use it: in 1.20, 7-34 (the house-master's "
         "years) it is read by the side of the Sun, and in 1.7, 3's preference with Dykes's 15° for Mars (fn 174 on "
         "1.22, 3)."),
        ("\"In good places\" for the Ascendant's lord.",
         "\"In good places\" for the Ascendant's lord (1.15, 16): Sahl's seven praised "
         "places (Introduction 2, 37-44: \"praised, powerful\"; On Nativities 1.30, 71 names them; fn 372 calls them "
         "\"good or advantageous\"), counted by whole-sign place; no sentence of Sahl's defines 16's phrase, so "
         "the identification is an interpretation -- with Dykes's backing: the seven are the busy places of "
         "Timaeus and Dorotheus, which he says Sahl \"explicitly uses\" in the Introduction, calling them "
         "\"praiseworthy\" and \"stronger\" (ITA III.4, Dykes's comment; ITA Introduction §6)."),
    ])
    _notes_expander("Years granted and alternative procedures", [
        ("The natal grant.",
         "The **years** the house-master grants are granted from 1.20, 7-34 read in full, "
         "above: On Times 4 is a question-chart chapter (\"in the hour of the "
         "question\", 4, 2) and On Nativities 1.23, 68 sends the reader to \"the section on the house-master\", so the "
         "texts hold one natal grant, and the apparent disagreement was a tie between a horary rule and a "
         "natal one; the Fardar and ages page's Planetary years table shows 1.20's grade for every planet and On "
         "Times 4, 7 for comparison."),
        ("Other procedures in these texts, not built.",
         "On Times 4, 2-5's shorter list (victor by testimony, "
         "seven candidates) and Masha'allah's ray in the Ascendant (On Nativities 1.23, 46-50) are the other two "
         "procedures in these texts, not built. No worked example exists in Sahl. Al-Qabisi's own "
         "account of the releaser and the house-master (ITA VIII.1.3, al-Qabisi IV.4-6) is in hand "
         "and stands beside Sahl's in the Sources page's coverage table, not built."),
    ])
    if pn4['hm_years'] and READING_DEPTH == READING_DEPTH_OPTIONS[1]:
        # Abu 'Ali's additions follow the releaser's section under their own
        # heading: drawn before the releaser's distribution, they stood over it,
        # its Now line and PN IV's releaser table, which the export files under
        # the releaser's heading (the re-pass of 2026-10-04, L5R-02).
        # JN Ch. 4's second half, display only (2026-09-15): one row a planet, no sum.
        # The Mercury line qualifies a row of Abu 'Ali's finding, so it is
        # drawn under the finding's heading, at reading width under its table;
        # drawn before `_finding`, it stood as the last line under the
        # releaser's heading (the follow-ups of 2026-10-05, K-26).
        _add = pn4['hm_years_additions']
        _finding([], "Additions and subtractions to the house-master's years (Abu 'Ali)",
                 JN_CH4_ADDITIONS_CITATION,
                 _add,      # never empty under a house-master: a luminary row is always present
                 standing="Supplement · display only",
                 glance="What each planet joined to the house-master or looking at it would add to or subtract "
                        "from its years by Abu 'Ali's chapter.",
                 # The summary folded (owner's ruling on the preview): the
                 # glance sentence and the Witnesses sentence visible, the
                 # rule's detail whole under the first notes heading.
                 summary="What each planet joined to the house-master or looking at it would add to or subtract "
                         "from its years by Abu 'Ali's chapter. Abu Bakr "
                         "and 'Umar stand beside each row in the Witnesses column with their own conditions.",
                 qualifications=["**Display only:** no sum is formed, and Sahl's grant above is not changed."],
                 under_table=["Under the adopted reading of ‘which add,’ Mercury’s +20 requires both a benefic "
                              "companion that itself adds under JN Ch. 4 and Mercury’s sextile or trine to the "
                              "house-master."],
                 detail=_additions_detail, detail_key='Planet',
                 detail_placeholder="Select a planet to read its effect, grades, reading and witnesses",
                 note_sections=[
                     ("The chapter's rule, as read.",
                      "What each planet joined to the house-master or looking at it would add to or subtract "
                      "from its years by Abu 'Ali's chapter: a fortune joined, trine or sextile adds its "
                      "lesser years, at one of three grades the chapter leaves undefined (none chosen, none "
                      "defaulting to years); a bad one joined, square or opposite subtracts its lesser years; "
                      "a fortune's square or opposition and a bad one's sextile or trine are the chapter's "
                      "explicit zero; Mercury by Dykes's fn 28, a conjecture, the cases it does not pair "
                      "left undecided under it; the Sun and Moon, given no modifier by the chapter, carry "
                      "'Umar's solar rule and Abu Bakr's sentence on the luminaries as witnesses."),
                     ("Abu 'Ali's chapter, whole.",
                      f"Abu 'Ali, Judgments of Nativities Ch. 4, whole:\n\n> \"{JN_CH4_SENTENCES['fortune']}\" \"{JN_CH4_SENTENCES['infortune']}\" "
                      f"\"{JN_CH4_SENTENCES['nothing']}\" \"{JN_CH4_SENTENCES['mercury']}\" \"{JN_CH4_SENTENCES['mars']}\"\n\n"
                      f"Fn 27 on \"rays\":\n\n> \"{JN_CH4_SENTENCES['fn27']}\"\n\nFn 28 on Mercury:\n\n> \"{JN_CH4_SENTENCES['fn28']}\""),
                     *_jn_ch4_note_sections(),
                     ("Abu Bakr, a witness beside Abu 'Ali.",
                      f"Abu Bakr, On Nativities I.15, a witness beside Abu 'Ali (not applied):\n\n> \"{ABU_BAKR_I15_ADDITIONS['method']}\"\n\n"
                      f"He grades the aspecting planet by its place and condition where Abu 'Ali says \"middling\" and \"more unsound\" "
                      f"(a different grading, not a definition of Abu 'Ali's):\n\n"
                      f"> \"{ABU_BAKR_I15_ADDITIONS['grades']}\"\n\nAnd he differs on the bad one's trine and sextile and the fortune's square and "
                      f"opposition:\n\n> \"{ABU_BAKR_I15_ADDITIONS['differs']}\"\n\nOn the luminaries:\n\n> \"{ABU_BAKR_I15_ADDITIONS['luminaries']}\"\n\n"
                      f"On Mercury:\n\n> \"{ABU_BAKR_I15_ADDITIONS['mercury']}\""),
                     ("'Umar al-Tabari, a witness.",
                      f"'Umar al-Tabari, Book of Nativities I.4.4, a witness (not applied):\n\n> \"{TBN_I44_ADDITIONS['fortunes']}\" "
                      f"\"{TBN_I44_ADDITIONS['grades']}\" \"{TBN_I44_ADDITIONS['infortunes']}\" \"{TBN_I44_ADDITIONS['seized']}\"\n\n"
                      f"(fn 87 on \"seized\": \"{TBN_I44_ADDITIONS['fn87']}\") With Sahl 1.21, 8, and against Abu 'Ali, on the "
                      f"fortunes' square and opposition:\n\n> \"{TBN_I44_ADDITIONS['squares']}\"\n\nAnd the Sun, to whom Abu 'Ali's chapter gives no "
                      f"modifier:\n\n> \"{TBN_I44_ADDITIONS['sun']}\" \"{TBN_I44_ADDITIONS['sun_reception']}\""),
                 ])

    st.subheader("The house-master directed (Sahl, *On Nativities* 1.23, 1-11)",
                 help="This is the technique that needs no grant of "
                      "years -- Masha'allah's alternative, absent from PN IV and present in Sahl.")
    if pn4['house_master'] in ('Mars', 'Saturn'):
        _hm = pn4['house_master']
        _other = 'Saturn' if _hm == 'Mars' else 'Mars'
        st.markdown(f"Within the stated span, {_hm} is directed to {_other}'s body, squares and opposition, "
                    f"the Sun's degree, and {_hm}'s own squares and opposition as an interpretive choice; "
                    "its zero-arc self-conjunction is omitted, and its possible unreliability as governor "
                    "under 1.23, 12 is flagged separately.")
    with _prose():
        st.markdown("**Facts, not judgment:** "
                    "1.23, 4's verdict is quoted in the notes and not pronounced.")
    if is_unresolved(pn4['house_master']):
        st.markdown(f"No one house-master to direct: {_display_result(_named_empty_arms(pn4['house_master'], SAHL_NO_HOUSE_MASTER))}.")
    elif not pn4['house_master']:
        st.markdown("No house-master to direct (see the section above).")
    else:
        for flag in pn4['hm_flags']:
            st.markdown(f"- {flag}")
        if pn4['hm_direction'] is None:
            st.warning("Refused at this latitude, as every direction by the oblique ascension is: it has no unique inverse there.")
            st.markdown(f"With the direction refused, 1.23, 4 is not asked in the revolution's year (age "
                        f"{pn4['cycle']}). The house-master in the revolution (1.23, 3):")
        else:
            st.markdown(f"**{pn4['house_master']}**, the house-master, directed from its natal degree to the "
                        f"bodies, squares and oppositions of Saturn and Mars and to the Sun's degree, forward, "
                        f"a year to a degree of the birth latitude's ascensions, within {PN4_DISTRIBUTION_SPAN_YEARS:g} years:")
            if pn4['hm_direction']:
                _hstrip = generate_hit_strip_svg(pn4['hm_direction'], pn4['elapsed_years'],
                                                 PN4_DISTRIBUTION_SPAN_YEARS, 'The house-master directed',
                                                 theme=WHEEL_THEME)
                st.image(_hstrip, width='stretch')
                st.download_button("Download this strip (SVG)", _hstrip, key="dl_strip_hm", mime="image/svg+xml",
                                   file_name="house_master_directed.svg")
                st.dataframe(pd.DataFrame(pn4['hm_direction']), hide_index=True, width='stretch',
                             height=_rows_height(len(pn4['hm_direction'])),
                             column_config={**_wide_text_columns(pd.DataFrame(pn4['hm_direction'])),
                                            **_date_columns(pd.DataFrame(pn4['hm_direction']))})
            else:
                st.markdown("No target within the span.")
            # The revolution's year is the year of age it opens (`cycle`), matched
            # to the direction rows' "In the year of age" in the engine.
            if pn4['hm_this_year']:
                _burning = any(r['Target'] == SAHL_BURNING_TARGET for r in pn4['hm_this_year'])
                st.markdown(f"**The revolution's year (age {pn4['cycle']}) is one the direction points out:** "
                            + '; '.join(f"{r['Target']} at {r['Degree']}, arc {r['Arc (years)']}" for r in pn4['hm_this_year'])
                            + (". It reaches the degree of burning, so 1.23, 4 asks of the revolution:" if _burning else
                               ". None of these is the degree of burning, so 1.23, 4 is not asked: it asks only "
                               "\"if your calculation of this [by direction] and the revolution both indicate burning\". "
                               "The house-master in the revolution (1.23, 3):"))
            else:
                st.markdown(f"The revolution's year (age {pn4['cycle']}) is not one the direction points out, so "
                            f"1.23, 4 is not asked. The house-master in the revolution (1.23, 3):")
        # Drawn whether or not the direction is refused: where it is, the
        # rows say so, as both exports carry them.
        st.dataframe(pd.DataFrame(pn4['hm_revolution']), hide_index=True, width='stretch',
                     height=_rows_height(len(pn4['hm_revolution'])),
                     column_config=_wide_text_columns(pd.DataFrame(pn4['hm_revolution'])))
        # The join and the denial, folded (owner's ruling on the preview):
        # one sentence visible, the paragraph whole under "The join." and
        # "The denial." in the block's disclosure below.
        with _prose():
            st.markdown(
                "The house-master directed here is selected by **Nawbakht's** "
                "rule (1.15, 13: the dignity lord looking at the releaser) and directed by **Masha'allah's** operation "
                "(1.23, 2, \"direct it\" -- the governor). The join is this app's; no sentence "
                "states it.")
        st.markdown("PN IV IX.8, 30's turning, "
                    "the one operation Abu Ma'shar licenses for the indicator, follows as PN IV's:")
        if pn4['hm_turning']:
            st.dataframe(pd.DataFrame(pn4['hm_turning']), hide_index=True, width='stretch',
                         height=_rows_height(min(len(pn4['hm_turning']), 12)),
                         column_config=_wide_text_columns(pd.DataFrame(pn4['hm_turning'])))
        else:
            st.markdown("The turned sign reaches no cutter's body, opposition or square within the span.")
        with _prose():
            st.markdown(f"**{pn4['house_master']}** turned a year a sign from its natal sign (whole signs, as PN IV VI.2, 1), "
                        "the years in which the sign reaches a cutter's body, opposition or square: \"if the turning of "
                        "the years from any of the five releasers (or from the indicator of the lifespan) reached their "
                        "bodies, oppositions, or squares, then they also kill\" (IX.8, 30); \"the rest of the "
                        "rays' direction ... is a weak testimony\" (31) and is not shown.")
        st.caption("Read: \"their\" as Saturn's "
                   "and Mars's, the cutters the direction table targets.")
    _notes_expander("How the house-master is directed", [
        ("Masha'allah's operation, 1.23, 2-4.",
         "Masha'allah:\n\n> \"look at the position of the governor [fn 181: the house-master] relative "
         "to the Ascendant and its lord, and its position relative to burning and the infortunes; "
         "then direct it to the conjunction of the infortunes and the degree of burning, and its "
         "opposition and its square, a year for every degree of ascensions. Then calculate for "
         "the revolution of that year in which the governor of the native corresponds to the "
         "degree of the infortune ... for if your calculation of this [by direction] and the revolution both "
         "indicate burning, and then the governor is burned at the revolution, the native will "
         "be destroyed; and if it is not burned at the revolution but it is burned in one of the "
         "stakes of the Ascendant of the year, it indicates that [as well]; and it is worse for that "
         "in the Ascendant [itself]\" (1.23, 2-4)."),
        ("The join.",
         "The house-master directed here is selected by **Nawbakht's** "
         "rule (1.15, 13: the dignity lord looking at the releaser) and directed by **Masha'allah's** operation "
         "(1.23, 2, \"direct it\" -- the governor); 1.23, 40 and 43 call Masha'allah's governor \"the "
         "house-master\" in Sahl's own words, but his governor is found by reception (1.23, 1), and the two "
         "rules name different planets in about a third of charts. The join is this app's; no sentence "
         "states it."),
        ("The denial.",
         "Abu Ma'shar denies the direction:\n\n> \"the indicator of the lifespan alone is turned in "
         "the signs, sign-by-sign, and is not directed degree-by-degree\" (PN IV IX.8, 32; fn 129: \"Some "
         "texts say that one can also distribute the house-master itself, but to me that seems like a "
         "misunderstanding\").\n\nShown as Sahl's, with the denial beside it."),
        ("Limitations: two limits of the denial.",
         "Two limits of the denial: PN IV IX.8, 32 restricts the "
         "**role** -- the planet may still be directed in another capacity, since \"all of the planets and Lots "
         "are [also] directed\" (III.1, 5); and On Nativities 1.16, 4 (direct the luminary \"even if a house-master is "
         "not looking\") is a provision the 1.16 exception built above does not cover."),
        ("Current direction: the readings.",
         "Readings: \"the degree of burning\" is the Sun's natal degree; \"a year for every degree of "
         "ascensions\" is the oblique ascension of the birth latitude applied to the house-master's own "
         "degree, as 1.15, 17, 1.16, 4 and 1.18, 21 apply \"the ascensions in that city\" to the "
         "luminaries and the Ascendant alike (not PN IV III.1, 12's third case, the proportional "
         "semi-arcs, which is Abu Ma'shar's assignment and not Sahl's); \"in the year of age\" is the "
         "completed year the arc falls in."),
        ("Not applied, and the redirection applied.",
         "Not applied: 4.12, 6 (a retrograde "
         "planet's rays directed conversely); 1.23, 5-11's further witnesses (the lord of the "
         "revolution's Ascendant, the lord of the year, the profection reaching an infortune's sign), "
         "which are PN IV's II.3 examination and the indicators in that chapter; On Nativities 1.23, 13-14's turning from "
         "the house-master to the lord of the Ascendant when the house-master is unsuitable, directed as the "
         "house-master was (Dykes's reading, fnn 191 and 194), is **applied** below when a 1.23, 12 flag "
         "fires; when the lord of the Ascendant is the house-master itself, only 14's direction from the degree "
         "of the Ascendant is drawn; not applied: 1.23, 6; 1.23, 53-60's increase and "
         "decrease of years; and the 1.21 additions except 13, which is applied: a burned house-master "
         "has no indication, with the heart excluded. No worked example exists in Sahl."),
        ("The revolution's facts: the readings.",
         "\"Burned\" is this app's Burned band, a declared operational reading and not a definition any "
         "sentence here supplies: its widths are Gr. Intr. VII.2's, and the heart it leaves out is Sahl's one "
         "degree (The Introduction Ch. 3, 87; Fifty Aphorisms #40, 79). It is the reading 1.21, 13 is given for "
         "the house-master's years; under the rays is not read as burned. 4 asks of the revolution only whether "
         "the governor is burned; Dykes's \"(or perhaps, just harmed)\" in his comment is his own, and no fact "
         "here reads harm by the infortunes. 4 opens \"if your calculation of this [by direction] and the "
         "revolution both indicate burning\", so both its questions are asked only in a revolution's year that the "
         "direction above reaches at the Sun's degree, the degree of burning; in any other year the two rows say "
         "that 4 is not asked, and why. The year is matched by the revolution's age, the completed years it opens, "
         "against the direction's year of age, the completed years its arc falls in; when one year holds two "
         "targets, every one is named, and 4 is asked if one of them is the degree of burning. 4's second case, \"if it is not burned at the revolution but it is "
         "burned in one of the stakes of the Ascendant of the year\", is asked only when the first does not hold, "
         "and is read with fn 183, \"burned in one of them *later* in the year\": every spell of burning that "
         "begins after the revolution and before the next is listed, its dates in UT and in the calendar of their epoch "
         "(Julian before the reform of 1582-10-15, Gregorian from it), with the house its sign is "
         "from the revolution's Ascendant by whole sign, the stakes being the first, fourth, seventh and tenth "
         "and the first \"worse\"; a spell under way at the revolution is the first case, not the second."),
    ])
    if pn4['hm_redirect']:
        _rd = pn4['hm_redirect']
        if _rd['lord_is_house_master']:
            # The lord of the Ascendant is the house-master: 13 has no planet of its own to direct.
            st.markdown(f"**1.23, 13-14, the redirection** -- a 1.23, 12 flag stands on the house-master: \"one will "
                        f"not be able to be guided by the governor\" (12). 13 turns to \"the lord of the Ascendant\", "
                        f"and the lord of the Ascendant here is **{_rd['lord']}**, the house-master itself, so 13 has "
                        f"no other planet to direct in its stead. 14 follows: \"Now if there was nothing of what I have "
                        f"mentioned, then take from the degree of the Ascendant to the positions of the infortunes, and "
                        f"their squares and oppositions.\"")
            st.caption("Read: no sentence names another planet for 13 when the lord of the Ascendant is the "
                       "house-master; that 14 covers the case is this app's reading.")
            _redirect_tables = (("1.23, 14: the degree of the Ascendant", _rd['ascendant_direction']),)
        else:
            st.markdown(f"**1.23, 13-14, the redirection** -- a 1.23, 12 flag stands on the house-master, so \"look at "
                        f"the coinciding of the lord of the Ascendant with the degree of the infortune (or its square or "
                        f"opposition), or its entrance into burning\" (13); the lord of the Ascendant here is "
                        f"**{_rd['lord']}**, not the house-master, and is directed in the house-master's stead; then "
                        f"the degree of the Ascendant (14). "
                        f"13's aggravation -- \"if the infortune was the lord of the house of the lord of the Ascendant, or "
                        f"the infortune was the lord of the house of the eighth\" -- holds for: "
                        f"{', '.join(_rd['aggravators']) or 'neither infortune'}.")
            _redirect_tables = (("1.23, 13: the lord of the Ascendant, in the house-master's stead", _rd['lord_direction']),
                                ("1.23, 14: the degree of the Ascendant", _rd['ascendant_direction']))
        for _lab, _tab in _redirect_tables:
            st.markdown(f"*{_lab}*")
            if _tab is None:
                st.warning("Refused at this latitude: the ascension has no unique inverse there.")
            elif _tab:
                st.dataframe(pd.DataFrame(_tab), hide_index=True, width='stretch', height=_rows_height(min(len(_tab), 8)),
                             column_config={**_wide_text_columns(pd.DataFrame(_tab)), **_date_columns(pd.DataFrame(_tab))})
            else:
                st.markdown("No target within the span.")
    if pn4['father_lot']:
        _fl = pn4['father_lot']
        st.subheader("The father's Lot: its harmers and their direction (Sahl, *On Nativities* 4.20, 31-36)",
                     help="32: \"direct the degree of the Lot of the father and the "
                          "Sun by day, and by night the Lot and Saturn\".")
        with _prose():
            st.markdown(f"The Lot of the father stands at **{get_degree_string(_fl['lot'])}** ({_fl['selection']['source']}); the second point "
                        f"directed is **{_point_name(_fl['second'])}** (32). fn 288 -- Dykes: Mars the main malefic in both sects, "
                        f"Saturn barred by night because he indicates the father, Mercury when made unfortunate -- is the "
                        f"editor's reading and is quoted, not applied; 31 is applied as printed.")
        st.markdown(f"**Selected formula:** {_fl['selection']['formula']}. {_fl['selection']['order_note']}. {_fl['selection']['condition']}.")
        st.caption(_fl['selection']['condition_profile'] + '.')
        st.markdown(f'> “{FATHER_SUBSTITUTION_TEXT}” — 4.14, 2.')
        st.dataframe(pd.DataFrame(_fl['harmers']), hide_index=True, width='stretch', height=_rows_height(len(_fl['harmers'])),
                     column_config=_wide_text_columns(pd.DataFrame(_fl['harmers'])))
        for _lab, _tab in (("From the degree of the Lot of the father (32), to the harmers' bodies, squares and oppositions", _fl['from_lot']),
                           (f"From {_point_name(_fl['second'])} (32), to the same", _fl['from_second'])):
            st.markdown(f"*{_lab}*")
            if _tab is None:
                st.warning("Refused at this latitude: the ascension has no unique inverse there.")
            elif _tab:
                st.dataframe(pd.DataFrame(_tab), hide_index=True, width='stretch', height=_rows_height(min(len(_tab), 8)),
                             column_config={**_wide_text_columns(pd.DataFrame(_tab)), **_date_columns(pd.DataFrame(_tab))})
            else:
                st.markdown("No target within the span.")
        _notes_expander("The harmers, the points directed, and the readings", [
            ("Harmers, 4.20, 31.",
             "31: \"if the nativity was by day, the infortunes which harm his Lot are Mars and Saturn (and "
             "Mercury, if he was unfortunate); and if it was by night, the infortunes which harm them are Mars "
             "and Mercury (if he was unfortunate)\"."),
            ("Points directed, 4.20, 32.",
             "32: \"direct the degree of the Lot of the father and the "
             "Sun by day, and by night the Lot and Saturn\"."),
            ("The direction's verdict, and the ranking of two infortunes, 4.20, 33-36.",
             "33: \"if you found an infortune casting its rays "
             "upon the Sun and upon the Lot ... it will kill the father when the direction reaches the "
             "infortune which casts the rays\"; 34-35 rank two infortunes by enmity and power; 36: Saturn "
             "\"from hostility\" is \"more harmful for some of the injuries\"."),
            ("Interpretive choices.",
             "Readings: \"casting its rays\" is met by the direction's targets, the harmers' bodies, squares and "
             "oppositions (the same set as the house-master's direction; sextiles and trines are not directed); "
             "the Sun is not a target here (4.20, 32 directs him). 33-35's choice between two infortunes is not made."),
        ])


def page_days():
    if not chart_ok:
        _recovery_panel("Days and months")
        return
    st.header("Days and months")
    _chart_strip(counts_from_the_ascendant=True)
    # Ruling 147 (2): as on Revolutions -- PN IV the frame; the second
    # caption names the Lots page's Lot of Fortune (the month's indicators
    # and method 8, on every chart) and what the small and mighty days'
    # selector directs when chosen, the Lots page's Lots and the cusps.
    st.caption("The frame of this page is Abu Ma'shar, "
               "*On the Revolutions of the Years of Nativities* (*Persian Nativities* IV), "
               "cited as Book.chapter, sentence.")
    _sources_scope_line()
    st.caption("This page also applies the Lots page's Lot of Fortune, and any other of its Lots or this app's "
               "Alchabitius house cusps chosen to be directed for the small and mighty days.")
    _year_under_examination("Days and months")

    st.subheader("The small days: the revolution's Ascendant distributed round the year",
                 help="A second distribution, running inside the year at its own "
                      "rate; the Ascendant's distribution on the Revolutions page runs across the years.")
    # The method in one line -- start, rate, time origin -- from the
    # sentences the notes hold whole.
    with _prose():
        st.markdown("| Method | As applied |\n"
                    "|---|---|\n"
                    "| Start | the degree of the Ascendant of the revolution of the year (IX.7, 29) |\n"
                    "| Rate | 59' 08\" a day round the zodiac, returning to the degree in 365.28 days |\n"
                    "| Time origin | the days count from the moment of the revolution (fn 161 leaves a \"day\" undefined) -- read into the sentence rather than stated by it |")
    # IX.7, 31 / 27: the same two directions from any planet, house or Lot (order PN4R-4c-4)
    _sr_pd, _sr_ch = pn4['sr']['planetary_data'], pn4['sr']
    _origins = pn4_day_point_origins(chart_data, _sr_ch, READING_DEPTH == READING_DEPTH_OPTIONS[1])
    _day_points = {"the Ascendant (the tables below)": None}
    for _id, _origin in _origins.items():
        _label = f"{_origin['label']}"
        if _id.startswith('house:'):
            _label += f" (revolution cusp {get_degree_string(_origin['revolution'])})"
        _day_points[_label] = _origin
    # Through the store, like the View, Wheel layout and Inner wheel
    # controls beside it (M4 of the hostile pass of 2026-09-16): a plain
    # key is dropped by Streamlit the moment the page is not rendered,
    # so this one choice reset itself on every walk to another page and
    # back. The options are this revolution's own, so a stored choice
    # the current chart does not offer falls to the first option, which
    # is what _reading_select does with one.
    _day_choice = _reading_select("Also direct, for the small days (IX.7, 31) and the mighty days (IX.7, 27), from",
                               list(_day_points), "pn4_day_point", "_pn4_day_point",
                               help="IX.7, 31: \"you work like that with everything of the planets, Lots, and houses\". "
                                    "**A reading:** the \"houses\" are offered as this app's Alchabitius cusps: the "
                                    "revolution's for the small days, the natal ones profected for the mighty days. "
                                    "Neither IX.7, 31 nor 27 says which degree stands for a house.")
    st.caption("Small days start from the revolution (IX.7, 29-31); mighty days profect the natal point "
               "(IX.7, 27; VI.2, 1).")
    _extra = _day_points[_day_choice]
    if _extra is not None:
        _x_lon, _x_label = _extra['revolution'], "the revolution's " + _extra['label']
        _x_small = pn4_small_days(_sr_pd, _x_lon, _x_label, significator=_extra['significator'])
        _x_cur = pn4_distribution_at_age(_x_small, pn4['day_of_year'])
        st.markdown(f"**Small days from {_x_label}** at {get_degree_string(_x_lon)} (IX.7, 31)"
                    + (f" -- now: distributor **{_x_cur['distributor']}**, partner **{pn4_result_text(_x_cur['partner'], 'none')}**" if _x_cur else '') + ":")
        _x_small_df = pd.DataFrame(_display_rows(_pn4_distribution_rows(_x_small, _x_cur, unit='days', origin_jd=pn4['jd_sr'])))
        st.dataframe(_x_small_df, hide_index=True, width='stretch', height=_rows_height(8), column_config=_date_columns(_x_small_df))
        _x_prof = pn4_profect(_extra['natal'], pn4['cycle'])
        _natal_label = "the natal " + _extra['label']
        _x_mighty = pn4_mighty_days(_sr_pd, _x_prof, f"{_natal_label}, profected", significator=_extra['significator'])
        _x_mcur = pn4_distribution_at_age(_x_mighty, pn4['day_of_year'])
        st.markdown(f"**Mighty days from {_natal_label} profected** to {get_degree_string(_x_prof)} (IX.7, 27: the "
                    f"point turned {pn4['cycle']} signs, its degree kept)"
                    + (f" -- now: distributor **{_x_mcur['distributor']}**, partner **{pn4_result_text(_x_mcur['partner'], 'none')}**" if _x_mcur else '') + ":")
        _x_mighty_df = pd.DataFrame(_display_rows(_pn4_distribution_rows(_x_mighty, _x_mcur, unit='days', origin_jd=pn4['jd_sr'])))
        st.dataframe(_x_mighty_df, hide_index=True, width='stretch', height=_rows_height(8), column_config=_date_columns(_x_mighty_df))
    with _prose():
        st.markdown("The terminal degree is turned by the revolution's cycle -- the solar return most recently reached at the target "
                    "instant, PN IV I.2, 1-3's year -- and directed through that same revolution: \"you look in the revolution of the year at "
                    "the degree of the sign which the year terminated at\" (IX.7, 23). The civil birthday and the Sun's return can "
                    "fall either side of a date; the civil age is a label here, not a count any table on this page keys on.")
    sd_cur = pn4['small_days_current']
    sr_asc = pn4['sr']['ascendant']
    _strip = generate_distribution_strip_svg(pn4['small_days'], pn4['day_of_year'], 'days', None, 'The small days',
                                            theme=WHEEL_THEME)
    st.image(_strip, width='stretch')
    st.download_button("Download this strip (SVG)", _strip, key="dl_strip_small", mime="image/svg+xml",
                       file_name="small_days.svg")
    if sd_cur:
        st.markdown(
            f"**Ascendant of the revolution** at {get_degree_string(sr_asc)} -- **now** (day "
            f"{pn4_day_text(pn4['day_of_year'], pn4_span_places(sd_cur, 'days'))} of the year): distributor "
            f"**{sd_cur['distributor']}**, partner "
            f"**{pn4_result_text(sd_cur['partner'], 'none -- the distributor acts alone')}**"
            f" &nbsp;|&nbsp; this period runs from day {' to '.join(pn4_span_text(sd_cur, 'days'))}"
            f" &nbsp;|&nbsp; opened standing on {get_degree_string(sd_cur['from_lon'])}")
    else:
        st.markdown(f"**Ascendant of the revolution** at {get_degree_string(sr_asc)} -- day "
                    f"{pn4_day_text(pn4['day_of_year'])} is outside the year's circuit")
    st.dataframe(pd.DataFrame(_display_rows(pn4['small_days_rows'])), hide_index=True, width='stretch',
                 height=_rows_height(min(len(pn4['small_days_rows']), 12)),
                 column_config=_date_columns(pd.DataFrame(pn4['small_days_rows'])))
    _notes_expander("How the small days are read", [
        ("The sentences, IX.7, 29-31.",
         "IX.7, 29: \"you look at the degree of the Ascendant of the revolution of the year, so "
         "that you direct from it (for the knowledge of the conditions of the days), a day for "
         "every 59' 08\", until it returns to the degree of the Ascendant at the end of the "
         "year.\" IX.7, 30: a body or ray already in the bound of that degree manages until "
         "another meets it; otherwise the bound lords, until a planet or ray is reached. IX.7, 31 "
         "names it the small days."),
        ("Zodiacal, by the sentence.",
         "Zodiacal, by the sentence: 59' 08\" a day round the zodiac returns to the degree in 365.28 "
         "days, the year to within an hour."),
        ("Source and approximation.",
         "Abu Ma'shar grades it himself -- \"there is an "
         "approximation in it, but the correct [approach] is that this way of directing is like the "
         "direction of the Sun every day ... [with] no harm in the work\" (IX.7, 32); that exact form "
         "is not built, nor is Dykes's fn 178, which would direct by ascensions."),
        ("Read into the sentence.",
         "What is read into the "
         "sentence rather than stated by it: the bodies and rays are the revolution's; the days count "
         "from the moment of the revolution (fn 161 leaves a \"day\" undefined); the partner already "
         "in place is looked for behind the degree within its bound, the shape of III.1, 23-25 narrowed "
         "to the window IX.7, 30 names, since the sentence does not say whether a body ahead in the "
         "bound manages from the first day."),
        ("The selector, and the worked example.",
         "The table below directs the revolution's Ascendant; IX.7, 31 "
         "extends the method to every planet, Lot and house, and the selector above carries it out, "
         "printing the small days from the point chosen and its profected mighty days beside them. "
         "No worked example of it exists in PN IV."),
    ])

    st.subheader("The mighty days: the terminal degree of the year directed through the revolution",
                 help="The profected thirty degrees treated as a year, walked degree by degree.")
    with _prose():
        st.markdown(f"**Applied rate: {PN4_MIGHTY_DAYS_PER_DEGREE:g} days per degree** -- the author's parenthetical "
                    "(IX.7, 25); the three figures that sentence holds are compared in the notes.")
        st.markdown("The direction does not stop at the end of the sign of the year: it "
                    "starts at the terminal degree and runs thirty degrees, so its last part lies in the bounds "
                    "of the next sign, which is what \"then to the lord of the bound which follows it\" "
                    "describes.")
    md_cur = pn4['mighty_days_current']
    _strip = generate_distribution_strip_svg(pn4['mighty_days'], pn4['day_of_year'], 'days', None, 'The mighty days',
                                            theme=WHEEL_THEME)
    st.image(_strip, width='stretch')
    st.download_button("Download this strip (SVG)", _strip, key="dl_strip_mighty", mime="image/svg+xml",
                       file_name="mighty_days.svg")
    if md_cur:
        st.markdown(
            f"**Terminal point** at {get_degree_string(pn4['year']['longitude'])} -- **now** (day "
            f"{pn4_day_text(pn4['day_of_year'], pn4_span_places(md_cur, 'days'))} of the year): distributor "
            f"**{md_cur['distributor']}**, partner "
            f"**{pn4_result_text(md_cur['partner'], 'none -- the distributor acts alone')}**"
            f" &nbsp;|&nbsp; this period runs from day {' to '.join(pn4_span_text(md_cur, 'days'))}"
            f" &nbsp;|&nbsp; opened standing on {get_degree_string(md_cur['from_lon'])}")
    else:
        st.markdown(f"**Terminal point** at {get_degree_string(pn4['year']['longitude'])} -- day "
                    f"{pn4_day_text(pn4['day_of_year'])} is outside the thirty degrees ({PN4_MIGHTY_DAYS_SPAN_DEGREES * PN4_MIGHTY_DAYS_PER_DEGREE:.2f} days)")
    st.dataframe(pd.DataFrame(_display_rows(pn4['mighty_days_rows'])), hide_index=True, width='stretch',
                 height=_rows_height(min(len(pn4['mighty_days_rows']), 12)),
                 column_config=_date_columns(pd.DataFrame(pn4['mighty_days_rows'])))
    _notes_expander("How the mighty days are read, and why this rate", [
        ("The sentences, IX.7, 23-28.",
         "IX.7, 23: \"you look in the revolution of the year at the degree of the sign which the "
         "year terminated at, from the Ascendant of the root\" -- the terminal point -- and a body "
         "or ray already in its bound manages until another meets it, else the lord of the bound "
         "\"then the lord of the bound which follows it\" (IX.7, 24). IX.7, 25: the arc times "
         "\"12 days, <4 hours>, 10 minutes, and 30 seconds (and that is 1/6 of a day and half a sixth "
         "of a tenth of a day)\" -- the parenthetical's 12.175 d a degree is applied -- from the first day of the revolution; "
         "IX.7, 28: thirty of them are the year, \"approximately\", and this is the mighty days."),
        ("Why this rate.",
         "| Reading of IX.7, 25 | A degree is |\n"
         "|---|---|\n"
         "| The manuscript's 12;10,30 days (10 minutes and 30 seconds as sexagesimal fractions of a day) | 12.175 d |\n"
         "| The author's parenthetical, 12 + 1/6 + 1/120 | 12.175 d; thirty of which are 365 1/4 days exactly (IX.7, 28) |\n"
         "| Dykes's hybrid, his \"<4 hours>\" supplied and the minutes read as clock time | 12 d 4 h 10 m 30 s (12.17396 d); thirty of them 365 d 5 h 15 m |\n\n"
         "IX.7, 25 prints \"12 days, <4 hours>, 10 minutes, and 30 seconds (and that is 1/6 of "
         "a day and half a sixth of a tenth of a day)\". Three figures stand in that sentence: the "
         "manuscript's 12;10,30 days (10 minutes and 30 seconds as sexagesimal fractions **of a day**, "
         "12.175 d); the author's parenthetical, 12 + 1/6 + 1/120 = 12.175 d, thirty of which are "
         "365 1/4 days exactly (IX.7, 28); and Dykes's hybrid 12 d 4 h 10 m 30 s (12.17396 d; thirty "
         "of them 365 d 5 h 15 m), his \"<4 hours>\" supplied and the minutes read as clock time -- "
         "fn 177 gives 12 d 4 h 12 m for a 365 1/4-day year, which is the author's fraction again. "
         "**Applied**: the author's parenthetical, 12.175 d a degree."),
        ("Zodiacal by construction.",
         "Zodiacal by construction -- "
         "no ascension appears in the sentence; fn 175's report that ascensions would make more sense "
         "is an editor's note."),
        ("Read into the sentence.",
         "Read into the sentence, as for the small days: the revolution's bodies and rays; "
         "days from the moment of the revolution; the opening partner behind the degree within its "
         "bound."),
        ("The selector, and the worked example.",
         "IX.7, 27's extension to every planet, house and Lot is the selector above. "
         "No worked example of it exists in PN IV."),
    ])

    st.subheader("The nine methods for the days and hours (PN IV IX.7, 1-72)",
                 help="\"The days and hours have nine indicators\" (IX.7, 1). IX.7, 56: all in equal hours. "
                      "IX.7, 79 declines day and hour "
                      "charts and keeps these.")
    with _prose():
        st.markdown("**The day.** A \"day\" is a whole 24-hour period from the birth moment -- fn 161 says the book never says "
                    "whether from birth or from dawn -- and the moment read is the target date at noon UT, or, where "
                    "noon UT on the target date falls before the birth, the birth's own moment, so no clock here runs "
                    "backwards from a noon before the birth hour.")
    dm_rows, dm_month, dm_ninth = pn4['day_methods']
    st.dataframe(pd.DataFrame(dm_rows), hide_index=True, width='stretch', height=_rows_height(9),
                 column_config=_wide_text_columns(pd.DataFrame(dm_rows)))
    st.markdown("**8. The month's days** (IX.7, 34-39), from the four rooted monthly indicators (fn 181) and the month's Ascendant, Lot and Moon:")
    st.dataframe(pd.DataFrame(dm_month), hide_index=True, width='stretch', height=_rows_height(len(dm_month)),
                 column_config=_wide_text_columns(pd.DataFrame(dm_month)))
    st.caption("Way 2 uses full 2½-day blocks from each indicator's sign, with "
               "five-hour steps beginning in that sign; this ignores its degree and is an implementation choice "
               "because IX.7, 37–38 do not unambiguously fix the starting point.")
    st.markdown("**9. The ninth-parts** (IX.7, 43-72), from the three starts:")
    st.dataframe(pd.DataFrame(dm_ninth), hide_index=True, width='stretch', height=_rows_height(3),
                 column_config=_wide_text_columns(pd.DataFrame(dm_ninth)))
    _notes_expander("The nine methods, one by one, and how they are counted", [
        ("The nine methods.",
         "- 1: the days since birth in weeks "
         "from the lord of the natal Ascendant (2-6).\n"
         "- 2: seven days each from the lord of the orb "
         "(7-9).\n"
         "- 3: the year in greater and lesser sevenths from the lord of the revolution's "
         "Ascendant (10-13).\n"
         "- 4: the weeks to the signs (14-17).\n"
         "- 5: the days to the signs by "
         "twelves (18-20).\n"
         "- 6 and 7: the mighty and small days above.\n"
         "- 8: the month's days (34-39).\n"
         "- 9: the ninth-parts, from the terminal sign, the revolution's Ascendant and the Moon "
         "(43-72), worked at 57-69."),
        ("The hours.",
         "The "
         "hours are equal (IX.7, 56): 3 3/7 apiece among seven (fn 164), 14 to a sign in a week (fn "
         "173), two to a sign in a day (IX.7, 20), five to a sign in a sixty-hour slot (IX.7, 38)."),
        ("Methods 8 and 9.",
         "Method 8's four rooted indicators are the monthly profections above (fn 181). Method 9's "
         "partners are the domicile lords of the fifth and ninth signs from the ninth-part's, as the "
         "worked example does (Capricorn, Taurus, Virgo: Saturn, Venus, Mercury); its month is 30 d "
         "10 h 30 m and its ninth-part 3 d 9 h 10 m (IX.7, 54-55)."),
        ("The example's printed errors, and what is not built.",
         "Two of the example's printed "
         "fractions are wrong, and are shown as printed:\n\n"
         + "\n".join(f"- {c} prints {p} for {e} ({fn})" for c, p, e, fn in PN4_IX7_EXAMPLE_ERRATA)
         + "\n\nThe judgments of IX.7, 21-22 and 41 are not built; 42's rule -- the succession sign after sign from the starting sign, convertible or not -- is applied."),
    ])

    st.subheader("The seven indicators of the month",
                 help="IX.1, 35-39. Five are \"rooted\" -- turned from the positions they hold at the "
                      "revolution of the year -- and two are not, being cast fresh from each monthly "
                      "revolution.")
    with _prose():
        st.markdown("They decrease in universality in the order given (IX.1, 39). The sign of "
                    "the year is itself month 1 (IX.1, 10), and months run from the revolution dates, not "
                    "the calendar.")
    PN4_MONTHLY_TURN_LOCAL = _reading_radio(
        "Monthly profections turn", list(PN4_MONTHLY_TURN_OPTIONS),
        "pn4_monthly_turn", "_pn4_monthly_turn",
        help="Dykes rejects the "
             "whole rule as \"complicated, probably wrong\" and counts forward always; his reading is the "
             "default here. Abu Ma'shar's rule is in the notes under the table.")
    st.dataframe(pd.DataFrame(pn4['monthly_rows']), hide_index=True, width='stretch',
                 height=_rows_height(len(pn4['monthly_rows'])))
    # Indicator #2 is the month's own: the sign of the terminal point turned
    # forward to this month, and the lord of ITS first ninth-part -- the
    # row the table carries, not the year's (L4-08 of the hostile pass of
    # 2026-10-03). The parenthesis names the month's sign first, then the
    # sign of its first ninth-part, which the row's Sign column prints --
    # two signs, not one (the check of that fix, finding 13). At most 397
    # characters over the twelve signs: the caption ceiling is 400.
    _month_ninth = next(r for r in pn4['monthly_indicators'] if r['number'] == 2)
    st.caption(f"Month {pn4['month']} of 12. IX.1, 37: each is read against three positions -- the Ascendant "
               "of the root (the column above), the sign of the terminal point, and the Ascendant of the "
               "revolution. Indicator #2 is the lord of the first ninth-part of this month's sign "
               f"({_month_ninth['month_sign']}, the year's sign turned forward; that ninth-part is in "
               f"{_month_ninth['sign']}, lord {_month_ninth['lord']}); Abu Ma'shar "
               "ignores it through most of Book IX (fn 15).")
    _notes_expander("The turning rule the radio chooses between", [
        ("Abu Ma'shar's rule, IX.1, 26-34.",
         "IX.1, 26-34: Abu Ma'shar turns the monthly indicators **backwards** when the sign is convertible, "
         "and for a double-bodied sign forwards below 15°00' and backwards from it, because the first "
         "half of a common sign is of the nature of the fixed sign before it and the second half of the "
         "convertible sign after it (IX.1, 30). IX.1, 31 applies the test to each indicator's **own** sign, "
         "individually. Indicator #2, the ninth-part, always runs forward (IX.1, 32)."),
        ("Dykes's reading, the default.",
         "Dykes rejects the "
         "whole rule as \"complicated, probably wrong\" and counts forward always; his reading is the "
         "default here."),
    ])


def page_fardar():
    if not chart_ok:
        _recovery_panel("Fardar and ages")
        return
    st.header("Fardar and ages")
    _chart_strip(counts_from_the_ascendant=True)
    # B-11: as on Revolutions -- PN IV the frame, the other sources the
    # page applies in a second caption after the scope line (README: "with
    # the releaser and house-master from Sahl").
    st.caption("The frame of this page is Abu Ma'shar, "
               "*On the Revolutions of the Years of Nativities* (*Persian Nativities* IV), "
               "cited as Book.chapter, sentence.")
    _sources_scope_line()
    st.caption("This page also applies Sahl's lords of the sect light's triplicity, his releaser and his "
               "house-master's years; the *Great Introduction*'s planetary years and solar bands; "
               "al-Andarzaghar's triplicity lords (in al-Qabisi), the Ascendant's on request and the "
               "houses' with the supplement; and, with the supplement, Abu 'Ali's ladder where Sahl is "
               "silent.")
    _year_under_examination("Fardar and ages")

    st.subheader("Directing: which ascensions, and what a degree is worth")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**III.1, 12 -- the measure, by position**")
        st.dataframe(pd.DataFrame(PN4_ASCENSION_ROWS), hide_index=True, width='stretch')
        st.caption("The three cases do not stand alike.")
        st.markdown("**III.1, 6 -- the unit, by level of chart**")
        st.dataframe(pd.DataFrame(PN4_UNIT_ROWS), hide_index=True, width='stretch')
    with c2:
        st.markdown("**III.1, 13 -- the rate ladder**")
        st.dataframe(pd.DataFrame(PN4_LADDER_ROWS), hide_index=True, width='stretch')
        st.caption("An idealised year of twelve 30-day months (fn 17).")
    _notes_expander("How a degree is directed, and what it is worth", [
        ("By position, III.1, 12.",
         "The **Ascendant** and the **meridian** are the "
         "distributions on the Revolutions page, each applied to the degree of its point and to a planet standing on "
         "that degree itself (a numerical tolerance, no orb). The **third case** -- everything not on "
         "one of the three degrees -- has no method in PN IV: III.1, 12 sends the reader to \"what we "
         "stated in our book [on that topic]\", and Dykes's fn 16 (with PN IV VI.2, 21 fn 33) identifies it as "
         "Ptolemy's proportional semi-arcs, which are applied from the texts that state the method "
         "(" + PN4_SEMIARCS_SOURCES + "); no other ascension is substituted."),
        ("By level of chart, III.1, 6.",
         "PN IV keys the unit to the "
         "level of the chart (III.1, 6):\n\n"
         + "\n".join(f"- {r['Directed in the']}: a degree is {r['A degree is']}" for r in PN4_UNIT_ROWS)),
        ("The rate ladder, III.1, 13.",
         "The bottom rung is **25 thirds**, a "
         "sixtieth of a second of arc: 10″ is a day, so an hour is 10″/24 = 25‴ exactly. "
         "(25″ would make an hour two and a half days long; the printed page, p. 288, has 25‴.)"),
    ])

    st.subheader("The lords of the triplicity of the sect light, over the life",
                 help="The three lords of the sect light's triplicity (the Sun's by day, the Moon's by night) in the "
                      "day-night-partner order for a day birth and night-day-partner for a night birth, each with its "
                      "natal condition.")
    with _prose():
        st.markdown('**No numerical age ranges are calculated here.**' + LIFE_LORDS_PARAGRAPH[len('No numerical age ranges are calculated here.'):])
    _shown_8 = pd.DataFrame(_display_rows(pn4['life_lords_rows']))
    st.dataframe(_shown_8, hide_index=True, width='stretch',
                 height=_rows_height(len(pn4['life_lords_rows'])),
                 column_config=_wide_text_columns(_shown_8))
    if _reading_checkbox("Also show the Ascendant's triplicity lords",
                         "life_lords_ascendant", "_life_lords_ascendant",
                         help="Al-Andarzaghar through al-Qabisi I.57b (ITA I.13) gives these lords qualitative life-stage significations; their identities follow al-Qabisi I.16c (ITA I.7). The complete export includes these rows regardless of this display choice."):
        st.subheader(LIFE_LORDS_ASCENDANT_HEADING)
        st.dataframe(pd.DataFrame(_display_rows(pn4['life_lords_ascendant_rows'])), hide_index=True, width='stretch',
                     height=_rows_height(len(pn4['life_lords_ascendant_rows'])))
    _notes_expander("The source testimony on the lords over the life", [
        ("Sahl, On Nativities 2.11, 1-2 and 4.",
         "Sahl, On Nativities 2.11, 1-2 (Theophilus; fn 148: Carmen I.24): \"If you found both of "
         "the two lords of the triplicity of the luminary to be strong, they indicate high rank "
         "from the beginning of his life to its end. And if one of the two was strong and the "
         "other weak, his benefit will be in the time of the strong one of them, and his baseness "
         "in the time of the one of them [that is falling]\"; 4: \"the partnering lord of the "
         "triplicity supports them both in their elevation, through its strength (if it was "
         "strong), and brings [them] down (if it was a falling [place])\"."),
        ("On Nativities 2.13, 39 and 2.19, 5.",
         "On Nativities 2.13, 39: the supplied first (fn 181 calls the sentence unclear and suggests the second) "
         "lord \"indicates the end of the father's life, and the beginning of the native's "
         "life\". On Nativities 2.19, 5: \"if the third lord of the triplicity was in the house of marriage, he "
         "will gain good fortune at the end of his lifespan\"."),
        ("PN IV VI.2, 4.",
         "PN IV VI.2, 4 names the sect light's triplicity "
         "lords \"at that time of his lifespan\"."),
        ("The Ascendant's triplicity lords: life-stage significations.",
         "Al-Andarzaghar, reported by al-Qabīsī I.57b (ITA I.13), assigns the Ascendant's triplicity lords beginning, middle, and terminal-life significations. Sahl, On Nativities 1.29 also uses these lords in judging upbringing. "
         "Several passages relate life stages to the luminary's triplicity lords. Al-Qabīsī I.57b (ITA I.13) separately relates life stages to the Ascendant's triplicity lords; these attributions should retain their distinct sources. "
         "Appendix A, 9 fn 7 names the Ascendant's lords as indicating upbringing."),
    ])
    if READING_DEPTH == READING_DEPTH_OPTIONS[1]:
        # al-Andarzaghar's per-house triplicity lords (coverage gap 9,
        # 2026-09-15): a separate table from Sahl's lords over the life
        # above; the sect order of first/second/third is al-Qabisi's own
        # (I.16, ITA I.7; 3.10 of the reconciliation, 2026-09-15).
        _andarzaghar_rows = evaluate_andarzaghar_triplicity_lords(chart_data['ascendant'], sect)
        _andarzaghar_first = ANDARZAGHAR_TRIPLICITY_LORDS[1]['text']
        _finding([], "The triplicity lords of the twelve houses, al-Andarzaghar",
                 "in ITA I.13, al-Qabisi I.57b-68 (al-Andarzaghar)", _andarzaghar_rows,
                 standing="Supplement · display only",
                 glance="For each of the twelve houses, the three lords of its sign's triplicity beside what "
                        "al-Andarzaghar says each signifies, as al-Qabisi reports him house by house. Display "
                        "only; nothing scores it, and the lords' conditions are not read.",
                 notes="The identities follow al-Qabisi I.16c (ITA I.7), including Mars for Virgo; the lords (day lord, night lord, partner) are in the "
                       "chart's sect order -- by day the day lord first, by night the night lord first -- which "
                       "is the order al-Qabisi himself states for the lords of a triplicity (I.7, al-Qabisi "
                       "I.16: by day the Sun and then Jupiter, by night Jupiter and then the Sun; Abu Ma'shar the "
                       "same at Gr. Intr. V.14, 6 and Abbr. I.86; Sahl's On Nativities 10.2.7, 16 names the day "
                       "lord first in a day chart), so his "
                       "own table reads al-Andarzaghar's \"first\", \"second\" and \"third\" Lord of "
                       "the triplicity; the house is the whole sign counted from the Ascendant. Each row's "
                       "words are al-Andarzaghar's as al-Qabisi reports them in the section named. For the "
                       f"first house (ITA I.13, al-Qabisi I.57b) whole: \"{_andarzaghar_first}\" (fn 158: \"the matter\" reads "
                       "with the Arabic for \"life\"). For the house of assets (ITA I.13, al-Qabisi I.58) he adds a rule this "
                       "table does not apply: \"see which one of them is stronger in being and place: you "
                       "will make this one deservedly the authority over assets and the significator of their "
                       "acquisition. Which if it were in the Mid-heaven, he will find this from the king; and "
                       "if it were in the house of faith, it will be better.\" The third house adds \"and "
                       "their worthiness will be according to their places\"; the seventh's \"uniting [with "
                       "others]\" is glossed \"partnerships and agreements\" (fn 172); the twelfth's "
                       "\"labors\" is \"or, 'suffering'\" in the Arabic (fn 192). Sahl's lords of the sect "
                       "light's triplicity over the life, above, are a different doctrine and are kept apart.",
                 height=_rows_height(len(_andarzaghar_rows)))

    st.subheader("The *fardar* (PN IV IV.1)",
                 help="IV.1, 2-4: the years are Sun 10, Venus 8, Mercury 13, Moon 9, Saturn 11, Jupiter 12, "
                      "Mars 7, Head 3, Tail 2 -- 75 in all. The order runs down the spheres from the light of "
                      "the sect: by day from the Sun, by night from the Moon.")
    with _prose():
        st.markdown("**The nodes last, in both sects.** IV.7, 24: the Head and Tail come "
                    "**last in both sects**, \"whether the native was diurnal or nocturnal\" -- the point the "
                    "later tradition got wrong. IV.7, 25: after 75 the cycle returns to \"the luminary which "
                    "he began from at his birth\", not always to the Sun.")
    st.dataframe(pd.DataFrame(pn4['fardar_rows']), hide_index=True, width='stretch',
                 height=_rows_height(len(pn4['fardar_rows'])))
    st.caption("IV.1, 5-6: each planetary period divides into seven equal parts, the lord itself first, then "
               "\"the planet which is below it in the celestial circle\". IV.1, 8: the Nodes have no "
               "sub-periods, \"because they do not have houses\". I.8, 35 says the order follows the planets' "
               "exaltations; it does not, and Book IV governs -- an inconsistency inside PN IV, recorded.")

    st.subheader("When a natal indication comes out (PN IV III.7, 32-42)",
                 help="A planet may distribute or manage more than once in a lifetime (III.7, 32), and this "
                      "chapter asks how often what it promised in the root actually manifests, and at what "
                      "ages.")
    with _prose():
        st.markdown("**All three grades are shown and none is chosen.**")
    st.dataframe(pd.DataFrame(_display_rows(pn4['activation_rows'])), hide_index=True, width='stretch',
                 height=_rows_height(len(pn4['activation_rows'])))
    _notes_expander("How the manifestation is read: the grade, the looking, the confirmation", [
        ("How often, and at what age, III.7, 35-42.",
         "**How often** is keyed to the quadruplicity of its natal sign: fixed, \"in [only] a "
         "single time\" (35); convertible, \"in [only] one of the times\" (39); double-bodied, "
         "\"on an occasional basis\" (38). **At what age**: \"the number of ascensions of the sign in "
         "which it was in the root, or the amount of one of its own years\" (42). What Abu "
         "Ma'shar himself adds is the last column -- the effect is \"strong, evident, notable\" "
         "when such an age falls where that same planet is the distributor or the manager."),
        ("The grade choice.",
         "III.7, 35 picks among the greater, middle "
         "and lesser years \"in accordance with what its position in the rotation of the circle "
         "indicated in the root\" -- and never states that rule. It is the same placement question "
         "*On Times* 4, 7 and *On Nativities* 1.20 disagree about, which PN IV does not adjudicate. "
         "**Two things in Dykes's fn 191 are also absent**: the **sum** of the ascensions and the years, and "
         "a third, a half and two-thirds of it, are introduced with \"if we follow Valens\" and appear "
         "in no sentence of PN IV III.7; and his worked figure of 20.17 ascensional times for Taurus at 45N "
         "is not reproduced, the exact computation giving 20.09."),
        ("Looking.",
         "III.7, 35's \"once\" is for a fixed-sign "
         "planet \"not looking at the position of the distribution\"; the looking is computed here as the "
         "whole-sign aspect from the natal sign to the Ascendant's sign at birth (a planet in the sign counted "
         "as looking) -- whether the position is the current bound's sign or its degree, and whether "
         "co-presence counts, are silences -- and a looking fixed planet's row says III.7, 36 applies "
         "\"whenever it distributes\" **if** strong, which the chapter does not define, so no row is promoted."),
        ("Confirmation.",
         "The confirmation column (III.7, 42) is checked against the distributions of the Ascendant, the "
         "Midheaven, the fourth and the releaser, each named; the planets' own semi-arc directions are "
         "not among them, no sentence asking for a planet to confirm itself. "
         "III.7, 37 exempts the manager, which \"will produce its indication\" whenever it manages."),
    ])

    st.subheader("The Ages of Man",
                 help="I.8, 10-26 and Figure 53 (PN IV): the ancients' seven ages (I.8, 9; Dykes's fn 47, at I.8, 1, "
                      "compares *Tet.* IV.10), ordered by sphere from the lowest upward -- not the quadrant scheme of Sahl, "
                      "On Nativities 3.9.")
    st.dataframe(pd.DataFrame(pn4['age_rows']), hide_index=True, width='stretch',
                 height=_rows_height(len(pn4['age_rows'])))
    st.caption("The last age is open-ended: Figure 53 (PN IV) tabulates Saturn as 30 years and ages 68-97, but the "
               "prose governs -- the seventh age runs \"until the end of his lifespan\" (I.8, 25). Abu Ma'shar "
               "refuses to subdivide an age into sevenths the way a *fardar* is subdivided, so there is no "
               "sub-lord here (I.8, 34-35).")
    _notes_expander("How the spans are counted", [
        ("The spans, I.8, 9.",
         "Each span is a planet's "
         "lesser years, or a half or a tenth of its lesser or middle years (I.8, 9)."),
        ("The Moon's 4, a witness.",
         "The Moon's 4 "
         "is a tenth of her middle years, 39 ½ (I.8, 12) -- an independent witness for the "
         "luminary construction of the middle years used elsewhere in this app."),
    ])

    st.subheader('Chronocrator Matrix', help='The lord of the year by annual profection.')
    st.dataframe(pd.DataFrame(time_lords_data), hide_index=True, width='stretch')
    # The one heading the short-headings branch left carrying its
    # own metadata: the citation and the standing move to a
    # caption under it, the shape _finding() prints, so the
    # heading is the table's name and nothing else.
    st.subheader("Planetary years",
                 help="The lesser, middle, greater and mighty years and the fardar of each planet, beside its placement, "
                      "the grade On Nativities 1.20, 7-34 would give it as house-master (placed by the division, the "
                      "**power** unit) and what On Times 4, 7 -- a question-chart rule, 4, 2 -- would "
                      "give it, for comparison.")
    st.caption("Display only · Gr. Intr. VII.8, Figure 146")
    st.dataframe(pd.DataFrame(_display_rows(planetary_years_data)), hide_index=True, width='stretch',
                 height=_rows_height(len(planetary_years_data)))
    with _prose():
        st.markdown("**Applied to one planet only:** the house-master The releaser page names "
                    "from On Nativities 1.15, whose grant is printed there with its sentence.")
    if READING_DEPTH == READING_DEPTH_OPTIONS[1]:
        st.caption("The last column, beside each \"1.20 silent\" cell only: the class Abu 'Ali's ladder gives the "
                   "planet (JN Ch. 3), its count from Ch. 4's table, and the steps taken.")
        _notes_expander("Abu 'Ali's ladder, where On Nativities 1.20 is silent", _jn_years_note_sections(named=True))

    # The scope index: what the book leaves open, each item's state named
    # (source silence, the editor's proposal, another source used, display
    # only, not implemented -- different states), then the explanations
    # under their headings. The help icon marks this expander as a heading
    # for the table walker; no st.dataframe follows it on the page.
    with st.expander("What Persian Nativities IV does not settle", icon=":material/help:"):
        with _prose():
            st.markdown(
                "The Prediction pages leave these items open. "
                "Each is absent because **the book does not answer it**, not because the work was skipped.")
            st.markdown(
                "| Topic | State |\n"
                "|---|---|\n"
                "| The releaser and the house-master | Choice supplied by Sahl's On Nativities 1.15 and 1.23, 2; PN IV IX.8, 123 defers the years; al-Qabisi's choice stated in that text, not built; Abu 'Ali's additions and subtractions displayed, row by row, and not applied to Sahl's grant |\n"
                "| Where the greater years are granted | Source silence (PN IV IX.8, 123); another source used: *On Nativities* 1.20 |\n"
                "| Directing anything that is not the Ascendant or the meridian | Deferred to a book PN IV does not reproduce (PN IV III.1, 12); Dykes's identification of the method (PN IV III.1, 12 fn 16), applied from the texts that state it |\n"
                "| Revolutions of the day and the hour | Declined by the author (IX.7, 79); not implemented |\n"
                "| The unit of a directed degree by sign type, strength or planet | Source silence: PN IV answers a different question (III.1, 6) |\n"
                "| The Indian rule for the lord of the year | Reported without adoption (III.10, 1-5); used here only as monthly indicator #2 |")
        _note_sections([
            # One paragraph per step of the argument (the owner, 2026-09-22):
            # what PN IV says, what it defers, the two texts that answer
            # parts of it (one line each, a hard break between), what this
            # app builds from them, and where the choice is made. The
            # sentences are the ones the page always had; only the breaks
            # are new, and a hard break is whitespace to the nothing-lost
            # check, so every sentence is still whole.
            ("The releaser and the house-master.",
             "PN IV names five releasers -- \"the Sun, Moon, Ascendant, "
             "Lot of Fortune, or the degree of the meeting or degree of the opposition\" (III.3, 1) -- and says "
             "all five are directed (III.1, 3). This app borrows the choice from Sahl.\n\n"
             "The explicit deferral "
             "in IX.8, 123 concerns deriving the years of the lifespan, not the choice or direction method. "
             "Abu Ma'shar says those \"who look into it are "
             "wandering around in the dark; but a statement of the truth of that ... is found in the book which "
             "we worked on concerning nativities\" (IX.8, 123) -- a book not in hand.\n\n"
             "Two texts in hand do "
             "answer parts of it:  \n"
             "**al-Qabisi** states the choice among the five and the house-master's order with "
             "its tie-breaks -- the lord stronger in the releaser's place that looks at it, going down the "
             "order until one does; equal claimants decided by the stronger in its own place, then the nearer "
             "degree; and if no lord looks at the releaser it is unfit and the next is taken (ITA VIII.1.3, "
             "al-Qabisi IV.4-6);  \n"
             "**Abu 'Ali** states how the fortunes add and the infortunes subtract -- a fortune "
             "joined or in trine or sextile adds its lesser years, an infortune joined or in square or "
             "opposition subtracts its own, and the other rays of each add or subtract nothing (Judgments of "
             "Nativities Ch. 4).\n\n"
             "Al-Qabisi's choice is stated in that text, not built here; Abu 'Ali's additions "
             "and subtractions are displayed, row by row, and not applied to Sahl's grant; the choice stays Sahl's.\n\n"
             "Here "
             "the choice is made from **Sahl**, *On Nativities* 1.15 (Nawbakht), and the house-master is directed "
             "per 1.23, 2 (Masha'allah), on The releaser page, with every reading that step needed said "
             "there; PN IV's positional direction of that releaser feeds testimony #3 and its partner feeds #4 "
             "(II.2, 12-14; III.1, 12). Sahl's distribution remains the separate luminary-proxy input. "
             "The distribution **from the Ascendant** remains the *jar bakhtar* of II.2, 6-7."),
            ("Where the greater years are granted.",
             "*On Nativities* "
             "1.20, 7-34 is the one natal grant in these texts -- *On Times* 4 is a question-chart chapter (\"in the hour "
             "of the question\", 4, 2) and On Nativities 1.23, 68 sends the reader to \"the section on the house-master\" -- so "
             "the house-master's years are granted from 1.20 on The releaser page, placed by the division; the "
             "Planetary years table shows 1.20's grade for every planet and *On Times* 4, 7 for comparison; PN IV is "
             "silent (IX.8, 123) and III.2, 110-111's gate now has the input it names."),
            ("Directing anything that is not the Ascendant or the meridian.",
             "III.1, 12 sends the reader to "
             "\"what we stated in our book [on that topic]\" for every other point, and PN IV never states it. "
             "Dykes's fn 16 identifies the method as Ptolemy's proportional semi-arcs; it is applied from the "
             "texts in hand that state it (" + PN4_SEMIARCS_SOURCES + "), and the page says which choices "
             "those texts leave open."),
            ("Revolutions of the day and the hour.",
             "Defined in principle (I.3, 10-13) and then declined by "
             "the author: \"there is no need for us [to do] that, because these nine indicators ... are complete "
             "for everything needed\" (IX.7, 79)."),
            ("The unit of a directed degree by sign type, strength or planet.",
             "PN IV keys the unit to the "
             "level of the chart (III.1, 6) and answers a different question from the one the two authors' "
             "disagreements ask; it is not evidence on either side of them."),
            ("The Indian rule, reported and not adopted.",
             "The Indian rule for the lord of the year -- the lord of the first ninth-part of the sign of "
             "the year (III.10, 1-5), which would restrict the lord of the year to Mars, Venus, Saturn and the "
             "Moon. PN IV reports it without adopting it, so it is used here only as monthly indicator #2, "
             "which is where IX.1, 36 puts it. The ninth-parts themselves are al-Qabisi's and Abu Ma'shar's too "
             "-- each sign in nine divisions of 3 1/3 degrees, the first to the lord of the movable sign of the "
             "triplicity and the rest in the order of the signs (ITA VII.5, al-Qabisi IV.16-17 and Abbr. "
             "VII.22-23, Figure 110). PN III III.10 also carries the Indian year-lord rule; these are named witnesses, not an absence of testimony."),
        ])

    with st.expander("Sources and editorial notes", icon=":material/menu_book:"):
        _note_sections([
            ("The rate ladder's bottom rung, and the fardar order.",
             "**The rate ladder's bottom rung is 25‴** -- twenty-five thirds of a degree to the hour, III.1, 13 "
             "(25″ would make an hour two and a half days long; the arithmetic settles it) -- and **the *fardar* "
             "order is the prose's, IV.1, 2-4**, of which Figure 43 (p. 116) is the table."),
            ("One printed error is not reproduced.",
             "Intro Sect. 2 (PN IV p. 7) puts the monthly "
             "revolutions at 12° **23′** when the natal Sun is at 12° **22′**. The page "
             "genuinely prints that, and it is contradicted by the rule in its own sentence, by IX.1, 23, by "
             "IX.3, 2, and by Dykes's own worked example at Intro Sect. 9, PN IV p. 95. The degree **and minute** are "
             "carried unchanged into every sign."),
            ("The lord of the year is the lord of the sign of the year.",
             "**The lord of the year is the lord of the *sign* of the year** (PN IV II.3, 1), Persian *salkhudhah* "
             "-- not the lord of the revolution's Ascendant and not a victor. \"Governor\" (Ar. *mustawli*) "
             "is a different term, the indicator in which all the year's indicators combine: a sign for the first "
             "month (PN IV IX.2, 4-5), a planet for the year (PN IV IX.9, 10); one holding only most of them "
             "is \"primary\", not the governor. "
             "PN IV keeps \"Ascendant of the year\" and \"sign of the year\" carefully apart (Intro Sect. 8, "
             "p. 77) where Sahl's English does not."),
            ("Figure 146, On Times 4, 7 and On Nativities 1.20, 10-17.",
             "**Figure 146 (Gr. Intr. VII.8, p. 487)**, verified against the prose restatement at Gr. Intr. VII.8, 3-8 and the "
             "fardar total the text gives (\"that is 75 years\", Gr. Intr. VII.8, 3), agrees with PN IV's IV.1, 2 cell "
             "for cell. **On Times Ch. 4, 7:** \"if the ruler was in a stake, eastern, it grants its greater "
             "years; or if it was in what follows the stakes, it grants its middle years; and if it was "
             "falling, it grants its lesser years.\" **On Nativities 1.20, 10-17:** greater in the Ascendant, "
             "Midheaven, sign of the west or eleventh when enhanced (10), or under the earth, eastern, in a "
             "share, enhanced (11); middle in the second or eighth (16), or in the eleventh or fifth when not in a share "
             "and not eastern (17). The two disagree, PN IV does not adjudicate them, and no row is chosen; "
             "the house-master's years on The releaser page are Sahl's On Nativities 1.20 in full, On Times 4, 7 being a "
             "question-chart rule."),
        ])


GEONAMES_CREDIT = (
    "Place names, coordinates, and country and region names: [GeoNames](https://www.geonames.org/), licensed under "
    "[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). Zīj selects "
    "and reformats the data for its offline atlas. GeoNames provides the data as is, with no warranty of "
    "accuracy, timeliness or completeness.")
OPENSTREETMAP_CREDIT = (
    "The outlines of the areas whose historical clocks are read by a birthplace's coordinates: © OpenStreetMap "
    "contributors ([copyright and attribution](https://www.openstreetmap.org/copyright)), under the "
    "[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Zīj has edited them; they are "
    "published whole, as a data file of their own with its licence notice, with the app and its source.")


def page_sources():
    st.header("Sources and readings")
    _chart_strip()
    # The one place a version is printed on a page. Everywhere else the rule
    # holds that page text carries no build process; here it is the identity
    # an exported analysis is signed with, and a reader holding an older
    # export needs to be able to read the current one off the app itself.
    st.caption(f"This app {APP_VERSION}. "
               "What this app reads from, how it can be read, and what it does not cover.")
    # --- The readings in force (2026-09-10) ----------------------------
    st.subheader("Readings in force",
                 help="Every doctrinal switch, where it is set, what it says now and what the default "
                      "is. They are remembered between runs. Reset returns all of them to the defaults.")
    _reading_radio("Sources shown", READING_DEPTH_OPTIONS, "reading_depth", "_reading_depth",
                   format_func={READING_DEPTH_OPTIONS[0]: "Sahl's course texts",
                                READING_DEPTH_OPTIONS[1]: "With Abu Ma'shar's supplement"}.get,
                   help="Sahl's course texts: the tables of Sahl's Introduction and On Nativities alone. "
                        "With Abu Ma'shar's supplement: his tables are laid beside Sahl's on the same topic. "
                        "Full text under Configurable readings below.")
    # What the chart the picker names was saved under, beside what is in
    # force (F03). A dash where there is nothing to show: no record
    # selected, or one written before this app stored the readings with a
    # chart. Nothing here sets anything -- the choice is offered on the
    # load, beside the picker, and this is the reading of the two together.
    _saved_readings = chart_record_readings(_picked_record or {})
    _rows = [{'Reading': label, 'In force': _reading_value_text(_reading(wk, sk, default)),
              'Saved with this chart': _reading_value_text(_saved_readings[sk]) if sk in _saved_readings else '–',
              'Default': _reading_value_text(default),
              'Set on': page, 'Differs': 'yes' if _reading(wk, sk, default) != default else ''}
             for label, wk, sk, default, page in READINGS_REGISTRY]
    st.dataframe(pd.DataFrame(_rows), hide_index=True, width='stretch', height=_rows_height(len(_rows)),
                 column_config=_wide_text_columns(pd.DataFrame(_rows)))
    if st.button("Reset every reading to the defaults", icon=":material/restart_alt:"):
        for _label, wk, sk, _default, _page in READINGS_REGISTRY:
            st.session_state.pop(wk, None)
            st.session_state.pop(sk, None)
            _forget(sk)
        st.rerun()
    # --- How citations are written: the key, below the controls --------
    st.subheader("How citations are written")
    # The key is a three-column table and takes the page's width, as the
    # tables do; the sentences around it stand at reading width.
    with _prose():
        st.markdown("A locator names its volume, never the author alone.")
    st.markdown("| Citation form | Work | Example |\n"
                "|---|---|---|\n"
                "| Sahl, The Introduction | Sahl's *The Introduction* | Sahl, The Introduction Ch. 3, 85 |\n"
                "| Sahl, On Nativities | Sahl's *On Nativities* | Sahl, On Nativities 1.22, 9 |\n"
                "| Gr. Intr. | Abu Ma'shar's Great Introduction (Dykes) | Gr. Intr. VII.6, 27 |\n"
                "| PN IV | Abu Ma'shar's On the Revolutions of the Years of Nativities, Persian Nativities IV (Dykes) | PN IV IX.1, 26 |\n"
                "| ITA | Dykes's Introductions to Traditional Astrology, its section and the author excerpted there (al-Qabisi's own numbering, al-Qabisi IV.4, where it is given) | ITA I.18, al-Qabisi I.22 |\n"
                "| Abu Bakr, On Nativities | one of the four nativity treatises of Persian Nativities I and II (Dykes) | Abu Bakr, On Nativities II.5.14 |\n"
                "| 'Umar al-Tabari, Book of Nativities | one of the four nativity treatises of Persian Nativities I and II (Dykes) | 'Umar al-Tabari, Book of Nativities I.4.3 |\n"
                "| Masha'allah, Book of Aristotle | one of the four nativity treatises of Persian Nativities I and II (Dykes) | Masha'allah, Book of Aristotle III.1.8 |\n"
                "| Abu 'Ali al-Khayyat, Judgments of Nativities | one of the four nativity treatises of Persian Nativities I and II (Dykes) | Abu 'Ali al-Khayyat, Judgments of Nativities Ch. 4 |\n"
                "| JN | Abu 'Ali al-Khayyat's Judgments of Nativities, as the row above, by its chapter | JN Ch. 3 |\n"
                "| Abbr. | Abu Ma'shar's Abbreviation as ITA prints it | Abbr. II.27 |\n"
                "| Rhetorius | Rhetorius the Egyptian's Astrological Compendium (Holden), by its chapter | Rhetorius Ch. 57 |")
    with _prose():
        st.markdown("Both of Abu Ma'shar's volumes have a Book VII, which is why his name alone no longer locates anything. "
                    "On the Prediction pages other than The releaser, whose frame is PN IV, its locators are "
                    "bare Book.chapter, sentence; on The releaser, whose frame is Sahl's *On Nativities*, its "
                    "locators are bare chapter, sentence. Any other work cited there is named.")
    # The full comparison of the two connection tests. It was the
    # Connection rule radio's tooltip; the radio (Configurations page)
    # now carries a one-line help and points here.
    st.subheader("Connection rule: Sahl and Abu Ma'shar")
    with _prose():
        st.markdown(
            "Which author's rule decides whether a pair counts as Connected. The two agree that "
            "looking is sign-to-sign and connecting is degree-to-degree, but they part company at "
            "the sign boundary and on what activates a connection.")
    st.markdown(
        "| Question | Sahl, as implemented | Abu Ma'shar, as implemented |\n"
        "|---|---|---|\n"
        "| Which distance governs? | The Sun's 15° for a same-sign approach to him; otherwise the applying planet's own light (15/12/9/8/7 by planet) | Two flat distances: assembly within 15 degrees in one sign (Gr. Intr. VII.4, 3), aspects within 12 degrees of exact (VII.5, 27) |\n"
        "| What happens at a sign boundary? | A planet at the end of a sign that is not connecting with anything, whose light strikes into the next sign, is connected to the first planet there by body (20-21) | No out-of-sign connection at all: across a boundary the bodies merely 'mix their natures in a weak way' (Gr. Intr. VII.5, 14) |\n"
        "| Source | The Introduction Ch. 3, 6-21 | Gr. Intr. VII.4-5 |")
    with _prose():
        st.markdown(
            "This governs only the tables that deliberately present **both** authors -- the aspect grid, "
            "reception, blocking, cutting. Each author's own tables are computed under "
            "that author's rule whatever this is set to; the Configurations page has its own "
            "control for which author you want to **see**."
        )
    _notes_expander("The two rules in full, and the alternative reading", [
        ("Sahl's rule.",
         "**Sahl** (The Introduction Ch. 3, 6-21): the Sun's 15° admits a same-sign approach to him; otherwise the applying planet's **own** light governs "
         "(15/12/9/8/7 by planet), so the test is asymmetric. A planet at the end of a sign that "
         "is not connecting with anything, whose light strikes into the next sign, **is** connected "
         "to the first planet there by body (20-21) -- even though the two do not see each other. "
         "20 is read by Sahl's own usage, in which connecting is the lighter planet's act "
         "(\"a light, quick star is going straightaway to a heavy star\" (6)): where a heavier planet "
         "retrogrades away over the boundary while the lighter one moves on, the lighter one is named, and "
         "out of sign the pair is in aversion, its Connection \"–\" unless 20 admits what is left of their "
         "contact. So a planet only approached by another is still \"not connecting with anything\" (20), "
         "connecting being the lighter planet's act (6, 19, 24, 28, 35): the planet at the end of the sign connects "
         "as the lighter party approaching another, or, as this app reads it, as the sole closer by its own "
         "retrogradation, and where the lighter planet retrogrades back onto a heavier one over the boundary, "
         "the lighter one is named, as in one sign. "
         "It is this app's reading, too, that a lighter planet still inside the residue of a separation is "
         "connecting for 20, so that its light struck into the next sign does not connect there "
         "(Sahl, The Introduction Ch. 3, 9-10): from another sign, \"And the planet does not cease to be counted "
         "as being connected until it separates from the planet by a full degree\" (9); in one sign, until "
         "the light one departs from the heavy one by one-half of its body (10). "
         "Abu Ma'shar counts retrogradation \"at the assembly\" (Gr. Intr. VII.5, 24), in one sign; "
         "his planet that retrogrades over a boundary \"enters its sign, and conjoins with it\" (Gr. Intr. VII.5, 121)."),
        ("Abu Ma'shar's rule.",
         "**Abu Ma'shar** (Gr. Intr. VII.4-5): two flat distances instead -- assembly "
         "within 15 degrees in one sign (VII.4, 3), aspects within 12 degrees of exact (VII.5, 27, "
         "since aspect rays have no bodies of their own). No out-of-sign connection at all: across "
         "a boundary the bodies merely 'mix their natures in a weak way' (Gr. Intr. VII.5, 14)."),
        ("Entry, completion and departure.",
         "Under this app's reading of Sahl, the Sun's 15° counts for same-sign application, and the blanket begins at exactness, ending at the departing light planet's limit or at 1° across signs. "
         "The Sun's own sentence: \"so if there was from a degree to 15° between the Sun and one of the planets, then he has already shone his light, and he is connected with [the planet]\" (The Introduction Ch. 3, 13). "
         "Entry is inclusive; departure ends at equality. The listed lights are already half-bodies. Extending the one-degree residue to the bodily strike is an inference from The Introduction Ch. 3, 9–10. "
         "Sahl 22 establishes ordinary direct separation positionally, past the contact. Exceptional motion requires encounter evidence; revocation requires its full sequence. "
         "The standing light/heavy order is this app's role convention; actual motion identifies the applicant, and the striker supplies the strike's light. "
         "The Sun's rule is not generalized into reciprocal admission for every pair; Gr. Intr. VII.4, 7 keeps each body's power directional."),
    ])
    # The readings the sources leave open, one section each, in the
    # registry's order: the reading's own paragraph (its bold lead, its
    # source and alternatives, the views it affects), then the value in
    # force, the default and the page its control stands on, read from the
    # same state the table above prints. Each control sits on the page and
    # table it changes with a one-line help; the full text is here.
    st.subheader("Configurable readings")
    _reading_text = {
        "_eastern_rule": (
            "**Gr. Intr. VII.6, 27/45 'eastern/western relative to the Sun'** (Configurations page, Planetary Condition) -- "
            "'hemisphere': the whole half, excluding the rays (VII.2, 2; VII.6, 34); 'VII.2 band': only "
            "the easternizing band 15/18 to 90 degrees (VII.2, 14-21) and the westernizing band 90 down to "
            "15 degrees (VII.2, 29-31). Superiors: 52% vs 25% of placements.",
            "Affects: Planetary Condition (27, 45)."),
        "_moon_rays_15": (
            "**Moon under the rays to 15 degrees (Sahl, On Nativities 1.19, 6)** (Chart page, Planetary Positions) -- "
            "Gr. Intr. VII.2, 61 and 72-73 give 12; Sahl gives 15 for the Moon's fitness as releaser.",
            "Affects: the Solar phase column of Planetary Positions; on the Configurations page, "
            "Weakness of the Planets (93), Planetary Condition and the ray-dependent Moon conditions; also the prosperity triplicity lords (Sahl, On Nativities 2.11, 5). The separate Moon burning rule (103) remains within 12°. "),
        "_mars_west_18": (
            "**Mars under the rays to 18 degrees west (Dykes's table in On Nativities 1.22, fn 175)** (Chart page, Planetary Positions) -- "
            "Gr. Intr. VII.2, 31 has Mars under the rays at 15 on the western side; Dykes's chapter-head table for "
            "Sahl, with fn 175 working the 18 out from the 22 degrees of On Nativities 1.22, 2 and Mars's daily motion, has him at 18 "
            "(the same figure as Gr. Intr. VII.2, 30's westernizing boundary for Mars, which fn 175 does not cite); Sahl's own sentences "
            "are silent on Mars west. With this reading on, the table's paired 22-degree figure is the outer edge "
            "of the setting band. Both agree on 18 east.",
            "Affects: the Solar phase column and every test that "
            "reads it; a 3-degree band on one planet."),
        "_fitting_infortune": (
            "**Fitting infortune (Sahl, Choices Ch. 1, 12)** (Configurations page, beside the Connection test) -- "
            + '"' + FITTING_INFORTUNE_QUOTE + '" ' + FITTING_INFORTUNE_STANDING
            + " Off by default. Choices 1, 16-17 describes the infortunes' nature; their natural identity is retained where that is the test.",
            "When on, that malefic drops out of every 'afflicted by an infortune' test in these tables (Sahl's enclosure, "
            "strength and weakness 94-95; Abu Ma'shar's 3, 47-50 and enclosure; the Moon's 67-68 and 106)."),
        "_domain_rule": (
            "**Domain (hayz)** (Dignities and places page, Sect table) -- "
            "Gr. Intr. VII.1, 37 / VII.6, 13: a sign of the planet's own gender and the hemisphere of its "
            "sect, so Mars, male and nocturnal, needs a male sign and the nocturnal hemisphere -- this app's "
            "reading of his exception, where Dykes's note 24 on VII.1, 37 leaves open whether it is his "
            "hemisphere or his sign's gender. Gr. Intr. VII.6, 13's \"or male degrees\", and 36's \"or in the female "
            "degrees\", in domain's reverse (a weakness), are not applied: the schemes of gendered degrees "
            "disagree. Masha'allah, "
            "On Nativities 1.23, 17: a male planet by day above the earth in a male sign, by night under "
            "the earth in a **female** sign; feminine planets by hemisphere only.",
            "Affects: the Sect table, Dignity Evaluation and Topical Planets in Houses' Net and Lean on the Dignities "
            "and places page; Planetary Condition (13 and 36) on the Configurations page; and the accidental "
            "conditions of a planet picked on the Chart page's wheel. "
            "Not the PN IV I.7 and II.3 domain rows on the Revolutions page, which read plain sect, as PN IV's own "
            "glosses do: \"(of the diurnal [planets] and the nocturnal ones)\" (I.7, 17) and \"(of the "
            "condition of day or night)\" (PN IV II.3, 5), with Dykes's note there, \"simply of the sect of the "
            "chart\"."),
        "_lot_house_cusp": (
            "**House-based Lot construction** (Lots page). " + LOT_CONSTRUCTION_STANDING + " " + LOT_WHOLE_SIGN_HELP + " " + LOT_CUSP_HELP,
            "Affects: house-based Lots on every page, wheel and export. Alchabitius is this app's cusp calculation."),
        "_reading_depth": (
            "**Sources shown** (this page) -- Sahl's course texts: the tables of Sahl's Introduction and On Nativities alone, with "
            "Abu Ma'shar's Great Introduction VII kept apart in its own tab on the Configurations "
            "page and behind closed expanders elsewhere. With Abu Ma'shar's supplement: his tables "
            "are laid beside Sahl's on the same topic -- further findings, three more topical "
            "Lots, a reference table and the supplementary expanders open -- and the Configurations "
            "page folds his tab into the topic blocks it belongs to. "
            "Sources shown is stored under the two names the table prints: Course text, which is "
            "Sahl's course texts alone, and Course text and supplement, which is those texts with "
            "Abu Ma'shar's beside them.",
            None),
    }
    with _prose():
        for _label, _wk, _sk, _default, _page in READINGS_REGISTRY:
            _paragraph, _affects = _reading_text.get(_sk, (f"**{_label}**", None))
            st.markdown(_paragraph)
            if _affects:
                st.markdown(_affects)
            st.caption(f"In force: {_reading_value_text(_reading(_wk, _sk, _default))} · "
                       f"default: {_reading_value_text(_default)} · set on the {_page} page")
    # The place data's credits (PK-01, PK-02; rulings 98 and 172): GeoNames'
    # CC BY 4.0 credit with no date, the paragraph of the atlas-names return
    # (process/ui_review_sol_2026-10-13/atlas_names_return/
    # LICENCE_AND_CREDIT.md) as its check allows it; and the OpenStreetMap
    # credit for the outlines the zone code reads by coordinates, published
    # whole as data under the ODbL.
    st.subheader("Place data")
    with _prose():
        st.markdown(GEONAMES_CREDIT)
        st.markdown(OPENSTREETMAP_CREDIT)
    with st.expander("Coverage: what these sources contain that this app does not", expanded=False):
        st.caption(
            "Named explicitly so the absence is a stated scope limit rather than an "
            "implied claim of completeness."
        )
        st.dataframe(pd.DataFrame(
            [{'Passage': a, 'Not implemented': b} for a, b in NOT_IMPLEMENTED_COVERAGE]),
            hide_index=True, width='stretch')
    with st.expander("What the analysis export carries", expanded=False):
        st.markdown(EXPORT_SCOPE_NOTE)

# --- Reference tables (2026-09-10): the app's Handy Tables ---------------
# The course hands out the Handy Tables; the app holds every one of
# them as data and used to print them in five places. One static
# page, lesson-tagged, that reads no chart.
def page_reference():
    st.header("Reference tables")
    _chart_strip()
    st.caption("The reference tables, printed from the data this app computes with. Nothing on this "
               "page reads the chart in the sidebar.")
    _sources_scope_line()

    st.subheader("Dignities by sign",
                 help="Domicile, exaltation, the three triplicity lords (day, night, participating) "
                      "and the three faces of each sign, as this app holds them. The exaltation degrees are "
                      "the standard scheme (Gr. Intr. V.5, Figure 38) and are printed only here.")
    rows = []
    for i, sign in enumerate(SIGN_ORDER):
        exalted = next((p for p, signs in EXALTATIONS.items() if sign in signs), None)
        trip = triplicity_rulers(sign, table='Sahl')
        faces = [get_essential_rulers(i * 30 + d)['face'] for d in (5, 15, 25)]
        rows.append({'Sign': sign, 'Domicile': SIGN_TO_DOMICILE[sign],
                     'Exaltation': (f"{exalted} ({pn4_ordinal(EXALTATION_DEGREES[exalted])} degree of {sign})"
                                    if exalted else '-'),
                     'Triplicity, day': trip['Day'], 'Triplicity, night': trip['Night'],
                     'Partner — Sahl / al-Qabisi / Valens': trip['Participating'],
                     'Partner — Great Introduction': triplicity_rulers(sign, table='Great Introduction')['Participating'],
                     'Virgo source note': VIRGO_PARTNER_NOTE if sign == 'Virgo' else '',
                     'Faces (1st, 2nd, 3rd)': ' · '.join(faces)})
    # Abu Ma'shar's partner is the supplement's column, as his nobility
    # degrees are below: laid beside Sahl's only under Course text and
    # supplement (L5-05 of the hostile pass of 2026-10-03).
    _supplement = READING_DEPTH == READING_DEPTH_OPTIONS[1]
    if not _supplement:
        for row in rows:
            del row['Partner — Great Introduction']
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch', height=_rows_height(12))
    st.caption("Sources by column: domicile and exaltation Sahl, The Introduction Ch. 1; triplicity day/night lords common to Sahl, al-Qabisi, Valens and the Great Introduction, "
               + ("with partners distinguished above; " if _supplement else
                  "with Sahl's partner above; ")
               + "the exaltation degrees Gr. Intr. V.5 (Figure 38), the standard "
               "scheme -- Hermes's (V.7, Figure 39) differ only for Jupiter and Mercury, the 16th degree of Cancer and "
               "of Virgo against the 15th.")
    _notes_expander(NOTES_TITLE, [
        ("The triplicity lords.",
         "Source selection: Sahl, The Introduction Ch. 1, 35-41, Figure 4 supplies the sect-light life lords, prosperity and its ascensional grade. Al-Qabisi I.16c (ITA I.7) supplies the Ascendant life-stage lords (al-Qabisi I.57b, ITA I.13) and the twelve-house al-Andarzaghar table. Valens II.1–2 agrees on the identities. The Great Introduction V.14, 6-9 / Figure 53 supplies the dignity reference rulers and sign summaries, with Mercury for Virgo under V.14, 7 / fn 100. PN IV VI.2, 4–5's assets and siblings lords assume that Great Introduction table across works; PN IV does not name it. "
         "Abbreviation I.87: Mars; Mercury also has a share in Virgo (relation unspecified). This witness does not add a fourth operative lord."),
        ("The faces.", "Faces are read at 5, 15 and 25 degrees of each sign."),
    ])

    st.subheader("Egyptian bounds",
                 help="The bounds every distribution on the Prediction pages runs through (PN IV III.1, 11). The "
                      "same table this app directs by; four independent witnesses agree with it.")
    bound_rows = []
    for sign in SIGN_ORDER:
        row, start = {'Sign': sign}, 0
        for n, (limit, lord) in enumerate(EGYPTIAN_TERMS[sign], 1):
            row[f'{pn4_ordinal(n)} bound'] = f"{lord} {start}°–{limit - 1}°59′"
            start = limit
        bound_rows.append(row)
    st.dataframe(pd.DataFrame(bound_rows), hide_index=True, width='stretch', height=_rows_height(12))

    st.subheader("Orders of the dignities, and the good places",
                 help="How Sahl ranks the dignities in three of his works, and which "
                      "places each of his schemes calls good.")
    st.dataframe(pd.DataFrame([{'Context': k, 'Order, strongest first': ' > '.join(v)} for k, v in DIGNITY_ORDER.items()]),
                 hide_index=True, width='stretch')
    # The places as a list in words, in the scheme's own order ("1, 10, 7,
    # 4, ..."), and a grouped scheme's groups apart by semicolons -- not a
    # Python list printed whole (the re-pass of 2026-10-04, N-02).
    def _places(places):
        return ', '.join(str(p) for p in places)
    st.dataframe(pd.DataFrame([{'Scheme': k, 'Places': ('; '.join(f"{g}: {_places(p)}" for g, p in v.items())
                                                        if isinstance(v, dict) else _places(v))}
                               for k, v in GOOD_PLACE_SCHEMES.items()]), hide_index=True, width='stretch')
    # The engine's own note on the printed order: the manuscripts compared
    # in a table built from its two sentences, which stand whole beneath it.
    _seven = _paragraphs(SEVEN_PLACE_RANKING_NOTE, "Manuscript B reads")
    _notes_expander(NOTES_TITLE, [
        ("The seven praised places' printed order.",
         "| Witness | The order's end |\n"
         "|---|---|\n"
         "| Manuscripts H and L (the printed order) | ... 11, 9, 5 |\n"
         "| Manuscript B | ... 11, 5, 9, with the note that the ninth is the Sun's joy (Introduction Ch. 2, 42, fn 42) |\n"
         "| The printed text | H/L's order plus B's note -- Dykes's conflation, kept as printed |\n\n"
         + _seven[0] + "\n\n" + _seven[1]),
    ])

    st.subheader("Planetary years",
                 help="The lesser, middle, greater and mighty years of each planet, with the "
                      "fardar period (PN IV IV.1, 2). A reference table: the one grant of years this app makes, "
                      "the house-master's from On Nativities 1.20, is on The releaser page.")
    years = reference_planetary_years_rows()
    with _prose():
        st.markdown("**The middle years, this app's convention.** This app keeps 39 1/2, the Arabic Great Introduction's, "
                    "the table it reads for the rest of the row.")
    st.dataframe(pd.DataFrame(years), hide_index=True, width='content', height=_rows_height(len(years)))
    st.caption("Gr. Intr. VII.8, Figure 146; the fardar periods PN IV IV.1, 2.")
    # The two constructions and their witnesses at the page's width, each
    # witness under its own construction and no consensus drawn; the
    # sentences the table was built from stand whole beneath it.
    with st.expander("Why the middle years differ", icon=NOTES_ICON):
        with _prose():
            st.markdown("**Two constructions of the middle years.**")
            st.markdown("The middle years use two constructions, the ordinary mean for the planets and (least + great/2)/2 "
                        "for the luminaries, which Valens VII.5 states outright:\n\n> \"The sun has half of 120 years and hence "
                        "receives 60; its minimum period is 19. The total is 79, half of which is 39 years, 6 months.\"\n\n"
                        "The Moon's is the same, half of 108 with 25, 79 halved.")
            st.markdown("**The witnesses, kept apart.**")
        st.markdown(
            "| Construction | The luminaries' middle years | Witnesses |\n"
            "|---|---|---|\n"
            "| (least + great/2)/2 | 39 1/2 for both | Valens VII.5; Gr. Intr. VII.8, 3-8 with Figure 146; Abu Bakr, On Nativities I.16, "
            "the same construction in prose (half the greater years added to the lesser, the sum halved); PN IV I.8, 12, "
            "the Moon's 4 as a tenth of her middle years |\n"
            "| The ordinary mean | the Sun 69 1/2 and the Moon 66 1/2 | Masha'allah, Book of Aristotle III.1.8 (Dykes's substituted values, fn 103); Abu 'Ali al-Khayyat, "
            "Judgments of Nativities Ch. 4; the Latin Great Introduction's table of the years as Dykes prints it (ITA VII.2, Figure 108) |")
        _note_sections([
            ("Four witnesses, and three against.",
             "So the luminaries' 39 1/2 has four "
             "witnesses in hand -- Valens VII.5; Gr. Intr. VII.8, 3-8 with Figure 146; Abu Bakr, On Nativities I.16, the same "
             "construction in prose (half the greater years added to the lesser, the sum halved); PN IV I.8, 12, "
             "the Moon's 4 as a tenth of her middle years -- and three against it that take the ordinary mean, "
             "the Sun 69 1/2 and the Moon 66 1/2: Masha'allah, Book of Aristotle III.1.8 (Dykes's substituted values, fn 103); Abu 'Ali al-Khayyat, "
             "Judgments of Nativities Ch. 4; and the Latin Great Introduction's table of the years as Dykes prints "
             "it (ITA VII.2, Figure 108)."),
            ("A variant not adopted.",
             "Valens's Venus is a complete period of 84 (half 46), not Figure "
             "146's 82 -- a variant not adopted."),
        ])

    st.subheader("Degrees of nobility and rank",
                 help="Sahl, On Nativities 1.38, 39-41 and Figure 57 of his volume: the degrees in which, with the "
                      "Ascendant or a luminary in one, \"he will reach exaltation and power, or he will rule many "
                      "lands\". The Chart page checks this chart's points against it.")
    _nob_rows = [{'Sign': sg, 'Sahl (On Nativities 1.38, 41)': ', '.join(pn4_ordinal(d) for d in NOBILITY_DEGREES.get(sg, [])) or '-'}
                 for sg in SIGN_ORDER]
    if READING_DEPTH == READING_DEPTH_OPTIONS[1]:
        for row in _nob_rows:
            row["Abu Ma'shar (Gr. Intr. V.22, 4)"] = ', '.join(pn4_ordinal(d) for d in ELEVATION_DEGREES.get(row['Sign'], [])) or '-'
    with _prose():
        st.markdown("**This app's ordinal-degree convention.** Sahl's figure prints bare degrees, read here as ordinals -- "
                    "how Abu Ma'shar's Figure 64 prints the same rule's degrees.")
    st.dataframe(pd.DataFrame(_nob_rows), hide_index=True, width='content', height=_rows_height(12))
    _notes_expander(NOTES_TITLE, [
        ("The ordinal span, and the editor's endpoint reading.",
         "Dykes resolves the ordinal to a point: on the inconsistency between cardinal and ordinal numbers in "
         "these tables his sense is that the authors meant the end of the nineteenth degree, that is 19° (ITA I.3 "
         "fn 23), the endpoint. This app's ordinal interval is [18°, 19°), excluding the point 19°; fn 23 does not prescribe that interval."),
        ("The distinct source lists.",
         "Al-Qabisi's own table of the same rule "
         "(al-Qabisi I.53, ITA VII.9, Figure 118) is a third list, printed as ordinals and disagreeing with both "
         "Sahl's and Abu Ma'shar's; it is not tabled here. "
         + ("Abu Ma'shar's column is the supplement's: the same rule, stated at Gr. Intr. V.22, 4 with Figure 64's table, "
            "twelve signs to Sahl's eight, six of the eight disagreeing; the text reconciles none of it."
            if READING_DEPTH == READING_DEPTH_OPTIONS[1] else
            "Abu Ma'shar states the same rule with a table of his own; Course text and supplement lays it beside this one.")),
    ])

    if READING_DEPTH == READING_DEPTH_OPTIONS[1]:
        st.subheader("The natures of the planets (Gr. Intr. IV.1)",
                     help="Abu Ma'shar's report of what Ptolemy said of each planet's nature, hot or cold and "
                          "wet or dry (Gr. Intr. IV.1, 6-12), each sentence's words beside the reading. A "
                          "supplement table: this app computes with no planet's nature.")
        st.dataframe(pd.DataFrame(PLANET_NATURES_IV1), hide_index=True, width='content',
                     height=_rows_height(len(PLANET_NATURES_IV1)),
                     column_config=_wide_text_columns(pd.DataFrame(PLANET_NATURES_IV1)))
        st.caption("Display only: Abu Ma'shar's report of Ptolemy, \"this is what Ptolemy claimed about the "
                   "natures of the planets\" (Gr. Intr. IV.1, 13); his own objections follow at IV.1, 15-43 and "
                   "are not tabled. Nothing in this app reads a planet's nature. Active and Passive are Dykes's framing of hot/cold and wet/dry.")

    st.subheader("The Ages of Man",
                 help="PN IV I.8, 10-26: the seven ages, ordered by sphere from the lowest upward. Each span is "
                      "a planet's lesser years, or a half or a tenth of its lesser or middle years (PN IV I.8, 9), and "
                      "the last age is open-ended (I.8, 25). The Fardar and ages page marks the native's own age in it.")
    age_rows = pn4_ages_of_man_rows()
    st.dataframe(pd.DataFrame(age_rows), hide_index=True, width='stretch', height=_rows_height(len(age_rows)))
    st.caption("The last age is open-ended: PN IV Figure 53 tabulates Saturn's 30 "
               "(his lesser years, Gr. Intr. VII.8, Figure 146), but the prose governs -- "
               "the seventh age runs \"until the end of his lifespan\" (I.8, 25).")

pages = {
    "**The Nativity**": [
        # The default page is served at the ROOT path, never at
        # /chart: Page.url_path returns "" when default is set, and
        # st.navigation registers that empty pathname, so /chart is not
        # a route and the browser falls back to root. url_path= stays
        # all the same, because Page._script_hash is calc_hash of the
        # PRIVATE _url_path, which keeps the string it was given: it is
        # the page's identity inside the app (and the string the
        # regression harness hashes to select this page). Dropping it
        # would rename the page to "page_chart" for no gain.
        st.Page(page_chart, url_path="chart", title="Chart", icon=":material/explore:", default=True),
        st.Page(page_dignities, url_path="dignities", title="Dignities and places", icon=":material/shield:"),
        st.Page(page_findings, url_path="findings", title="Findings", icon=":material/menu_book:"),
        st.Page(page_configurations, url_path="configurations", title="Configurations", icon=":material/hub:"),
        st.Page(page_lots, url_path="lots", title="Lots", icon=":material/functions:"),
        st.Page(page_victors, url_path="victors", title="Lunation and victors", icon=":material/trophy:"),
    ],
    "**Prediction**": [
        st.Page(page_timing, url_path="timing", title="Revolutions", icon=":material/schedule:"),
        st.Page(page_releaser, url_path="releaser", title="The releaser", icon=":material/route:"),
        st.Page(page_days, url_path="days", title="Days and months", icon=":material/calendar_month:"),
        st.Page(page_fardar, url_path="fardar", title="Fardar and ages", icon=":material/timeline:"),
    ],
    "**Reference**": [
        st.Page(page_reference, url_path="reference", title="Reference tables", icon=":material/table_chart:"),
        st.Page(page_sources, url_path="sources", title="Sources and readings", icon=":material/menu_book:"),
    ],
}
# The page list is a header bar across the top, not the first thing in
# the sidebar: the sidebar is the nativity form, and it opens on the
# Date field with Save inside the fold. expanded= is read only when
# position="sidebar", so it goes with the move.
st.navigation(pages, position="top").run()
# K-1: a preference refused while the page was drawn is said now, in this run.
_say_preference_notices()
