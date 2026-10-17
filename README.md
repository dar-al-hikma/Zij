# Zīj

A *zīj* (زِيج) is a set of astronomical tables with the rules for using them. This one is a study
companion for traditional natal astrology: cast a chart, then check, table by table, what the
texts say about it.

The rules it applies come from the course's two books in Benjamin Dykes's translations — Sahl
b. Bishr, *The Astrology of Sahl b. Bishr*, vol. I, and Abū Ma'shar, *On the Revolutions of the
Years of Nativities* (*Persian Nativities* IV) — with his *Great Introduction to the Science of
the Judgments of the Stars* as the supplement, and a handful of witness texts (Rhetorius,
Firmicus, al-Qabīsī, Abū 'Alī, Abū Bakr, the other *Persian Nativities* volumes, Valens, Morin)
where the course texts leave a question open. Every one of them, with what it supplies and how
it is cited, is in [docs/REFERENCES.md](docs/REFERENCES.md).

Every rule a page applies names the sentence it comes from. Where a text leaves something open,
the page says so and shows the reading it made; where the texts settle nothing at all — Mercury
exactly with the Sun, a tie between two contacts that open a distribution, a question the book
defers to another book — the result is reported *unresolved*, with its reason, its source and
the alternatives, and every total that depends on it shows what is known and what is not.

The judgment of the chart is the astrologer's.

## Download

Portable builds for Windows and macOS are on the
[Releases](https://github.com/dar-al-hikma/Zij/releases) page: unzip, run `Zij`. No install, no
internet — place lookup uses a bundled atlas and the planets run on the built-in Moshier
ephemeris. Saved charts and preferences live in your user data folder and survive updates.

Every release after v1.0.0 also carries `SHA256SUMS`, the SHA-256 of each zip as the release
build made it. To check a download, compare its hash with its line there:
`shasum -a 256 Zij-macos.zip` on macOS, `Get-FileHash Zij-windows.zip` in PowerShell on Windows
(which prints it in capitals).

## What it computes

**The nativity**

- **Chart** — the wheel (square, or wide with a positions panel; clickable, with an SVG
  download), positions, the Alchabitius divisions beside the whole-sign places, solar phase,
  Sahl's sign categories, the special degrees, the prenatal lunation, sect, the lords of the
  day and hour. **Here & Now** casts a chart for a stored home place at this moment.
- **Dignities and places** — the essential dignities at each planet's own degree, sect and
  domain, planets in the places and the lords of the places with their delineations from
  Masha'allah, *PN* IV and Rhetorius.
- **Findings** — the delineations read off the cast chart: the fetus's stay, the Moon on the
  third day, Sahl's seven classes of fortune and livelihood, the lords of the triplicity of the
  sect light over the life, and, under the fuller reading depth, Mars by sect, the Moon's
  phases, Mercury's phase, Rhetorius's afflictions, Morin's aspect rules and the places harming
  the eyesight. Each cites its sentence; none is scored.
- **Configurations** — Sahl's connections and their states on his own sentences, receptions and
  their refusals, the handing-over, collection and reflection of light, prevented connections,
  strength and weakness, the corruption of the Moon; Abū Ma'shar's planetary conditions
  (Gr. Intr. VII) beside them, and the forward-looking conditions (revoking, resistance,
  escape) simulated against the ephemeris.
- **Lots** — the classical Lots and Sahl's topical Lots, each with its formula and its source;
  where Sahl gives a Lot twice with different formulas, both are shown.
- **Lunation and victors** — the prenatal syzygy, its lords and its governor (Sahl 1.7), the
  victor of the chart.

**Prediction** (Abū Ma'shar, *PN* IV, with the releaser and house-master from Sahl)

- **Revolutions** — the revolution of the year and of the month with their wheels; the
  indicators of the year in Abū Ma'shar's order; the distributions from the Ascendant and the
  meridian through the bounds, drawn as strips with the present marked; the lord of the year
  and the governor with their testimonies.
- **The releaser** — the releaser chosen from Sahl 1.15, the house-master and its years from
  1.20, its direction per 1.23, 2, and Abū 'Alī's additions and subtractions displayed beside
  Sahl's grant.
- **Days and months** — the profection of the month, the small days and the mighty days.
- **Fardar and ages** — the fardārs, the ages, the lord of the orb; and what the book does not
  settle, listed rather than filled in.

**Reference** — the dignity tables, the bounds, the planetary years, the ages, the triplicity
lords by source; and **Sources and readings**, which lists every doctrinal switch in force, the
readings the app makes, and the scope of the export.

Every page's tables can be exported as one analysis (JSON with typed results, or Markdown in
the pages' own words), versioned with the readings the chart was analysed under.

## Running from source

```bash
pip install -r requirements.txt
python run_source.py
```

Open the address it prints, and open it again after reloading the page: the app opens only at
that address, which carries a key made for this run alone. Ctrl-C stops it.
A source run serves this computer only, and other accounts on this computer can reach it.

`streamlit run app.py` is a developer's command, with no key: any program on this computer, a
web page served from it included, can open the app there and read, change or delete its saved
charts.

Python 3.14 is what the pins were resolved on and what the tests and the desktop build use.
The tests (`python -m pytest -q -n auto`) pin every rule to a fixture drawn from the texts' own
worked figures, with a near-miss beside each, and render every page under the states the texts
leave open.

## Building the desktop app

See [`docs/BUILD_NOTES.md`](docs/BUILD_NOTES.md) (PyInstaller, one folder per platform).
Releases are cut by tag; see [`docs/RELEASING.md`](docs/RELEASING.md).

## Repository

| Path | What |
|---|---|
| `engine.py` | the engine: the chart, the dignities, the evaluators, the lots, the timing, and the pictures drawn from them |
| `ephemeris.py` | Swiss Ephemeris: the private folder it reads from, the handle every calculation goes through, the built-in Moshier ephemeris every body is read from, and the calendar dates are read in |
| `time_zones.py` | the time-zone database the app reads (its pinned copy, never the computer's), the zones and dates where that database is not trusted, the zone each place takes, and the offline atlas's search |
| `app.py` | the Streamlit pages, after the marker `# 4. STREAMLIT UI INTEGRATION`; it takes the engine whole and is the file to run |
| `glyph_font.py`, `fonts/` | the symbol-font subset every picture embeds, and its licence |
| `tests/` | the suite; `tests/fixtures/tables.json` pins which tables each page renders |
| `ephe/` | the Swiss Ephemeris fixed-star catalogue the app ships (AGPL-3.0; see its README) |
| `atlas.db` | the offline place lookup |
| `GeoNames_Dataset.py` | the maintainer's tool that rebuilds `atlas.db` from GeoNames' dump, checking every row and recording its sources (the app never runs it) |
| `data/` | the outlines of the areas the app reads by coordinates for historical clocks, drawn from OpenStreetMap and published whole under the Open Database License, with their notice; and the list of the places whose zone is settled by a named source rather than by the boundaries alone, each with its source |
| `desktop_launcher.py`, `build.spec` | the desktop wrapper and the PyInstaller build |
| `docs/` | four documents: the references, the build notes, the release procedure, the hostile-pass checklist |

This repository carries the app and those four documents, and nothing else. Comments in the
source that cite `process/tae_docs/…` point at the maintainer's private notes — the build logs,
the audits and the working papers the rules were adjudicated from. They are not public.

The texts themselves are not here either: they are copyrighted translations and are worked from
privately. The pages cite them by volume, chapter and sentence so that anyone with the books can
check every rule.

## History

Zīj was developed as the Traditional Astrology Engine and renamed at its first release. Its
rules were read twice against the texts, cell by cell, before that release; where a reading
could not be settled from the texts in hand, the app says so rather than choosing. The
development history is kept privately.

## Licence

AGPL-3.0 — see [`LICENSE`](LICENSE). The fixed-star catalogue in `ephe/` is Swiss Ephemeris
data redistributed under the same licence. `glyph_font.py` embeds a 26-glyph subset of Google's
Noto Sans Symbols and Noto Sans Symbols 2 (SIL Open Font License 1.1) as base64 WOFF2, so every
picture the app draws carries its own zodiac and planet glyphs regardless of what is installed
on the viewing machine — see [`fonts/OFL.txt`](fonts/OFL.txt) for the licence notice. The
outlines in `data/` are drawn from OpenStreetMap (© OpenStreetMap contributors) and offered under the
Open Database License 1.0, apart from the code's licence — see [`data/NOTICE-ODBL.md`](data/NOTICE-ODBL.md).
