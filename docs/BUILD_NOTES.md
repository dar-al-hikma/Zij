# Packaging Zij as a portable desktop app

## Files
- `desktop_launcher.py` — spawns Streamlit headlessly, opens it in a pywebview window.
- `build.spec` — PyInstaller build configuration.
- `app.py` — the Streamlit script, bundled as a data file (not imported).

## 1. Test in dev mode first
Before packaging anything:
```
pip install pywebview
python desktop_launcher.py
```
This should open a native window showing the app. Fix any issues here —
they'll be much harder to debug once frozen.

## 2. Why onedir instead of onefile
PyInstaller's `--onefile` mode self-extracts to a temp directory on *every
launch*, adding a real startup delay, and its unsigned self-extracting
`.exe`s are flagged by antivirus heuristics far more often than a plain
folder of files. `build.spec` uses `--onedir` (via `COLLECT`) instead:

- **Windows:** the build is a folder (`dist/Zij/`) containing
  `Zij.exe` plus its dependencies. Zip the folder — that *is* the
  portable, no-install form. Users unzip and double-click the `.exe`.
- **macOS:** the spec's `BUNDLE` step wraps that same folder into a proper
  `Zij.app`, which behaves as a single double-clickable icon even
  though it's technically a directory. Zip or `.dmg` it for distribution.

If a folder of files is unwanted, `--onefile` still
works for personal use — change `EXE(..., exclude_binaries=True)`
to a single onefile `EXE(...)` per PyInstaller's docs and drop `COLLECT`.

## 3. Platform-specific requirements

### Windows
pywebview uses the **Qt (PySide6/QtWebEngine)** backend, which bundles its
own Chromium build via the `PySide6` pip package — no external runtime
dependency like WebView2, no version detection, nothing to install on the
end user's machine beyond the app itself.

Unsigned `.exe`s trigger a Windows SmartScreen warning ("Windows protected
your PC"). Users can click **More info → Run anyway**. A proper fix requires
a code-signing certificate (~$100+/yr) — not necessary for personal/private
distribution.

### macOS
pywebview uses the built-in WebKit — no extra runtime needed, which is a
genuine advantage for portability here.

Unsigned `.app` bundles trigger Gatekeeper's "unidentified developer"
block. First run: **right-click the app → Open → Open** (this only needs
doing once). Removing that friction needs an Apple Developer ID ($99/yr)
and a notarized build; the releases are not notarized.

## 4. Gotchas specific to this app's dependencies

- **Windows GUI backend: Qt (PySide6), not WebView2.** Earlier versions of
  this project used pywebview's EdgeChromium backend, which depends on the
  Microsoft Edge WebView2 Runtime being present on the end user's machine
  (usually true on stock Windows 10/11, but not guaranteed — debloated
  installs, locked-down corporate images, or older systems can be missing
  it entirely, and there's no way to know in advance whose machine it'll
  run on). We switched to pywebview's Qt backend instead: `PySide6`
  bundles its own complete Chromium build (QtWebEngine) directly in the
  pip wheel, so there's nothing external to detect, download, or bundle
  separately — `requirements-desktop.txt`, from which the Windows build's lock is made, is the
  whole story.
  `desktop_launcher.py` forces `gui="qt"` on Windows; macOS keeps using
  its native Cocoa/WebKit backend, since that already works well there
  with no equivalent runtime-availability problem.
- **pyswisseph / ephemeris precision:** the planets run on the built-in
  Moshier ephemeris (no external `.se1` files needed). This is
  arc-second-level precision, which is far finer than anything the app
  displays (minutes of arc) — no need to bundle Swiss Ephemeris planetary
  files unless there is a specific reason to want JPL-grade precision.
  The invariant that matters is that NO `.se1` FILE IS BUNDLED OR NEEDED
  and the planets stay on Moshier: every body is read with `FLG_MOSEPH`.
  Swiss Ephemeris still opens other files by name from the folders on its
  ephemeris path -- above all a Delta T table (`swe_deltat.txt`,
  `sedeltat.txt`), which moves every value -- and a thread's path starts
  at the working directory. So `ephemeris.py`, which the engine imports
  first, makes a private folder of its own before it imports `swisseph`
  (`tempfile.mkdtemp`, its mode then set to 0700 and its catalogue copy's
  to 0600 whatever the umask, removed at a normal exit by an `atexit` hook;
  a killed process leaves it behind, and so does a Windows server stopped
  by `terminate()`) and sets `$SE_EPHE_PATH` to it, and every call into the
  library goes through its `swe` handle, which the engine takes whole and
  which points the calling thread at that folder before the thread's first
  calculation. `app.py`
  takes `swe` from the engine and must not import `swisseph` itself. The
  folder holds nothing but a copy of the star catalogue the app ships,
  `ephe/sefstars.txt` (137 KB, the Swiss Ephemeris fixed-star file, copied
  unmodified from the `kerykeion` package, which redistributes it under
  AGPL-3.0 -- the app's own licence; see `ephe/README.md`), checked
  against the SHA-256 `engine.py` records (`FIXED_STAR_CATALOGUE_SHA256`).
  No other catalogue is looked for (`$SE_EPHE_PATH`, the user data
  directory and installed packages were searched once). The copy is a
  plain file written into the temporary folder, with no link (the first
  Windows build of the branch failed at a symlink-or-copy into
  `%APPDATA%`). `build.spec` lists the file in `datas` so the frozen app
  carries it at `_internal/ephe/sefstars.txt`. The fixed-star tables (PN
  IV I.6, 7 and III.8, 9) therefore render identically on every checkout
  and in the frozen app; when the page says "Not computed" it says only
  that the fixed-star file could not be read, and why stays off the page,
  in `_FIXED_STAR_STATE['why']`. The Linux build keeps Swiss Ephemeris's
  state per thread; whether the Windows and macOS builds do has not been
  checked (where a build shares one state, every thread is pointed at the
  same folder all the same).
- **pyswisseph is compiled from source on every platform.** The pinned
  `pyswisseph==2.10.3.2` publishes ready-made wheels only up to CPython
  3.11, and the build runs CPython 3.14, so on Windows and on macOS pip
  downloads its 2.10.3.2 sdist (`pyswisseph-2.10.3.2.tar.gz`) and builds
  the wheel on the runner itself, with that runner's compiler. The last
  release build's log shows it on both runners ("Downloading
  pyswisseph-2.10.3.2.tar.gz", then "Building wheel for pyswisseph",
  ending in a `cp314` wheel built there). The local and CI test venvs
  on Linux are built from the same sdist. So the Swiss Ephemeris code a
  release carries is the unmodified upstream source, compiled per
  platform at build time: no downloaded binary of it is involved, and the
  suite, which runs on Linux, never runs the Windows or macOS build of it.
  The build's stop check holds one value each download computes with it,
  where the example chart's wheel puts Jupiter, to the value the app draws
  on Linux, within a hundred-thousandth of a degree.
- **timezonefinder:** answers from a sizeable boundary dataset (tens of
  MB) that, since timezonefinder 8, is a distribution of its own,
  `timezonefinder-data` (pinned in `requirements.txt`), imported as the
  separate top-level package `timezonefinder_data`.
  `collect_all("timezonefinder")` does not reach it, so `build.spec`
  lists `timezonefinder_data` in `collect_pkgs` beside it; without that
  the build would carry the polygons only if a PyInstaller hook for the
  package happened to be installed. This is the single biggest
  contributor to final build size. For a much smaller build at the cost
  of coarser timezone boundaries, `TimezoneFinderL` is a lighter drop-in
  alternative; it trades accuracy for size and is not used.
- **Geocoding is offline.** Place lookup reads the bundled `atlas.db`
  (SQLite, ~25 MB, listed in `build.spec`'s `datas`), opened read-only, so
  the packaged app needs no internet access and no geopy/Nominatim or
  certifi -- neither is a dependency any more, and neither is in
  `requirements*.txt` or the spec. Swapping the atlas for a live geocoder
  would bring both back: a network requirement at runtime, and certifi's CA
  bundle for frozen HTTPS calls.
- **Rebuilding the atlas.** `GeoNames_Dataset.py` builds `atlas.db` from
  GeoNames' `cities500` dump; it is a maintainer's tool, never run by the
  app. Run it with the app's interpreter, `python -I GeoNames_Dataset.py`:
  it fetches the dump and GeoNames' country and region name lists over HTTPS
  into a fresh temporary folder, checks every row (a failing row stops the
  build and is named), writes the database beside itself through a
  temporary file, and records its sources in the database's `metadata`
  table: each file's address, Last-Modified, SHA-256 and size, the row
  count, the dump's date, and the Python, Unicode, SQLite and tzdata
  versions it was built with. The tests pin the database's SHA-256, row
  count, schema and dump, a digest of every place's coordinates and five
  places' coordinates exactly, so a rebuild is a reviewed change that
  updates those pins in the same commit.
- **The outline data.** `time_zones.py` reads the outlines of the areas it
  judges by coordinates (areas that kept their own time, cities with dates
  of their own, areas outside the country a zone's notes describe) from
  `data/mean_time_outlines.json` beside it, once, at import: an
  OpenStreetMap derivative published under the ODbL, with its notice,
  `data/NOTICE-ODBL.md`. `build.spec` lists both in `datas` under `data`,
  so the frozen app carries them at `_internal/data/`. Without the file the
  module's import fails, loudly, rather than judging without the outlines.
  Beside them, `data/place_zones.tsv` is the hand-kept list of the atlas's
  places whose zone is settled by a named source rather than by the
  boundaries alone, each with its reason and source; `time_zones.py` reads it at
  import the same way, and `build.spec` ships it in the same folder.

## 5. Building for both platforms without owning both machines
PyInstaller does not cross-compile — a build run on Linux/Mac cannot
produce a Windows `.exe`, and vice versa. Without both machines the
standard solution is a CI matrix, which this repository has:
`.github/workflows/build.yml` runs on `windows-latest` (x86-64) and
`macos-latest` (Apple silicon), installs that system's lock and nothing
else (`pip install --require-hashes -r requirements-build-windows.lock`, or
`requirements-build-macos.lock`), runs
`tests/test_mac1_platform_names_2026_10_14.py` as a script and then under
pytest (the platform's errno names, and the names the program reads), runs
`pyinstaller build.spec`, zips `dist/` (the macOS zip with `zip -y`, so the
links inside `Zij.app` stay links), and starts, reaches and stops the
download it built (`.github/scripts/stop_check.py`). That build job can
only read the repository, and its checkout keeps no token on disk. For a
pushed `v*` tag, a second job, which runs no build tool and is the only one
allowed to write, waits for both platforms and creates one draft release
with both zips and `SHA256SUMS`, the SHA-256 of each, attached and no
notes; a manual run builds the zips and stops. How it is triggered and
where the zips go is in `docs/RELEASING.md`.

**The locks.** Each lock is made from `requirements-desktop.txt` (which
includes `requirements.txt`) and `requirements-build.txt` for its system,
so PyInstaller, its hooks and everything pip would resolve for any of them
are pinned there, each with the SHA-256 of every file of that version; the
command that makes it is in its header. After a pin moves in any of the
three files, rewrite both locks with those commands, and keep every
version they share with the set the tests run on the same (uv keeps the
pins a lock already holds; `--upgrade-package NAME` moves one). `pyswisseph`,
`timezonefinder` and `proxy-tools` publish no wheel for CPython 3.14 on
either system, so pip builds them on the runner from the source archives
the lock hashes; the build tools it fetches to do that (setuptools and
the like) come from the package index with no hash check.

## 6. Debugging a frozen build that fails silently
Set `console=True` in `build.spec` temporarily — this gives a terminal
window showing Streamlit's actual startup errors/tracebacks, which are
otherwise invisible with `console=False`. Switch back to `False` for the
release build once it's working.
