"""The release build: what it installs, what it attaches, and what its stop
check asks the download it built.

* Each build machine installs one hashed lock and nothing else: `pip install
  --require-hashes -r requirements-build-<system>.lock`, the lock for the
  system the matrix runs it on, a file of this tree. Each lock holds every
  name its inputs give (requirements-desktop.txt, which includes
  requirements.txt, and requirements-build.txt), at the pinned version and
  for its own system, each entry with its hashes, and its header holds the
  one command that rewrites it, for the Python the build sets up.
* The release job attaches SHA256SUMS beside the two zips: the SHA-256 of
  exactly the files it attaches, made in that job, after the download that
  brings the last of them and before the create.
* The stop check asks the download's server what a page of another site
  and a client without the window's key would ask: an opening from another
  site's Origin is refused, and a session with no key, or with a key one
  letter off the launch's, is told one sentence and shown nothing else. It
  holds the example chart's Jupiter, as the download draws it, to the value
  the app draws here, in the degree and minute the engine's own tests pin.
  Each is pinned live, against the app run from source with that property
  taken out (or, for the ephemeris, a stand-in for a build of it that
  computes every longitude a degree off): the check fails, naming it. And
  the check's log is UTF-8 whatever its output's encoding would be, so a
  place's accented letters reach the log.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

from conftest import EXECUTABLE_DIR, make_app, natal_wheel_envelope
from test_sec4_build_workflow_2026_10_13 import (DISPATCHES, PUSH_TAG, RELEASE_JOB, _commands, _jobs, _reachable,
                                                 _script_lines, _steps, _workflow, load_yaml)
# _outside: the watch every test here runs under.
from test_stop_check_2026_10_13 import LOADS_ITS_PAGE, NO_WAY_OUT, SCRIPT, STAND_IN_WEBVIEW, _module, _outside
from test_stop_check_atlas_2026_10_15 import _copy, _failure_and_details

WORKFLOW = EXECUTABLE_DIR / ".github" / "workflows" / "build.yml"
README = EXECUTABLE_DIR / "README.md"
RELEASING = EXECUTABLE_DIR / "docs" / "RELEASING.md"
BUILD_NOTES = EXECUTABLE_DIR / "docs" / "BUILD_NOTES.md"
INPUTS = ("requirements-desktop.txt", "requirements-build.txt")
# Each runner the matrix names: (runner.os, its lock, the platform the lock is
# resolved for, sys.platform there). windows-latest is x86-64; macos-latest
# is Apple silicon.
SYSTEMS = {
    "windows-latest": ("Windows", "requirements-build-windows.lock", "x86_64-pc-windows-msvc", "win32"),
    "macos-latest": ("macOS", "requirements-build-macos.lock", "aarch64-apple-darwin", "darwin"),
}
LOCKS = [lock for _, lock, _, _ in SYSTEMS.values()]
ZIPS = ["Zij-windows.zip", "Zij-macos.zip"]


def _name(text):
    return re.sub(r"[-_.]+", "-", text.strip().lower())


# --------------------------------------------------------------------------
# Every install, on each system: its own lock, hash-checked, and nothing else.

_INSTALLERS = {"pip", "pip3", "uv", "pipx", "conda", "mamba", "micromamba", "easy_install", "poetry", "pdm"}


def _installs(argv):
    """Whether a command installs packages, by any tool this check knows."""
    tool = os.path.basename(argv[0]).lower().removesuffix(".exe")
    if tool in _INSTALLERS or re.fullmatch(r"pip3(\.\d+)?", tool):
        return True
    return tool.startswith("python") and "-m" in argv[:-1] and argv[argv.index("-m") + 1] in (
        "pip", "ensurepip", "uv", "pipx")


def _install_differences(workflow):
    """Every install that is not `pip install --require-hashes -r <a lock of
    this tree>`, and every system and trigger on which the build does not
    install its own lock exactly once, as sentences."""
    off = []
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps") or []:
            for argv in _commands(step.get("run")):
                if not _installs(argv):
                    continue
                if argv[:4] != ["pip", "install", "--require-hashes", "-r"] or len(argv) != 5:
                    off.append(f"{job_name}: {' '.join(argv)!r} is not one hash-checked install of a lock")
                elif argv[4] not in LOCKS:
                    off.append(f"{job_name}: {argv[4]} is not a build lock")
    build = workflow["jobs"]["build"]
    if build["strategy"]["matrix"]["os"] != list(SYSTEMS):
        off.append(f"the build runs on {build['strategy']['matrix']['os']}, not {list(SYSTEMS)}")
    for runner, (system, lock, _, _) in SYSTEMS.items():
        for context in [PUSH_TAG] + DISPATCHES:
            ctx = dict(context, **{"runner.os": system})
            ran = [argv for step in build.get("steps") or []
                   if step.get("if") is None or _evaluate(step["if"], ctx)
                   for argv in _commands(step.get("run")) if _installs(argv)]
            if ran != [["pip", "install", "--require-hashes", "-r", lock]]:
                off.append(f"on {system} ({context['github.event_name']}, {context['github.ref']}) the build "
                           f"installs {ran}, not its own lock once")
    return off


def _evaluate(expr, context):
    from test_sec4_build_workflow_2026_10_13 import evaluate
    return evaluate(expr, context)


def test_each_system_installs_its_own_lock_once_hash_checked_and_nothing_else():
    assert _install_differences(_workflow()) == []
    tracked = subprocess.run(["git", "ls-files", "--", *LOCKS], cwd=EXECUTABLE_DIR, capture_output=True, text=True,
                             check=True).stdout.split()
    assert sorted(tracked) == sorted(LOCKS), "each lock the build installs is a file of this tree"


_INSTALL = "        run: pip install --require-hashes -r requirements-build-windows.lock\n"


@pytest.mark.parametrize("planted", [
    "        run: pip install -r requirements-build-windows.lock\n",
    "        run: pip install --require-hashes -r requirements-build-windows.lock pyinstaller\n",
    "        run: pip install --require-hashes -r requirements-desktop.txt\n",
    "        run: python -m pip install -r requirements-build-windows.lock\n",
    "        run: pip install --require-hashes -r requirements-build-macos.lock\n",
    _INSTALL + "      - run: pip3 install pyinstaller\n",
    _INSTALL + "      - run: uv pip install pyinstaller\n",
    _INSTALL + "      - run: python3.14 -m pip install --upgrade pip\n",
    "        if: runner.os == 'Linux'\n" + _INSTALL,
], ids=["no-hashes", "an-extra-package", "not-a-lock", "python-m-pip", "the-other-systems-lock", "pip3", "uv",
        "upgrade-pip", "never-on-windows"])
def test_an_install_that_is_not_its_systems_lock_hash_checked_is_caught(planted):
    text = WORKFLOW.read_text(encoding="utf-8")
    anchor = "        if: runner.os == 'Windows'\n" + _INSTALL
    assert text.count(anchor) == 1
    planted = planted if planted.startswith("        if:") else "        if: runner.os == 'Windows'\n" + planted
    assert _install_differences(load_yaml(text.replace(anchor, planted))) != [], planted


# --------------------------------------------------------------------------
# Each lock: every name of its inputs at its pin, hashed, for its system.

def _inputs(path, seen=None):
    """(name, version, marker or None) for every exact pin in a requirements
    file and the files it includes."""
    seen = set() if seen is None else seen
    out = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        line = line.split("#")[0].strip()
        if not line:
            continue
        if line.startswith("-r "):
            included = path.parent / line[3:].strip()
            assert included not in seen, included
            seen.add(included)
            out += _inputs(included, seen)
            continue
        requirement, _, marker = line.partition(";")
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", requirement.strip())
        assert match, f"{path.name}: not an exact pin: {line}"
        out.append((_name(match[1]), match[2], marker.strip() or None))
    return out


def _entries(path):
    """name -> (version, hashes) for every entry of a lock, its continuation
    lines joined; an entry it cannot read fails here."""
    text = re.sub(r"\\\n", " ", path.read_text(encoding="utf-8"))
    found = {}
    for line in text.split("\n"):
        line = line.split("#")[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)((?:\s+--hash=sha256:[0-9a-f]{64})+)", line)
        assert match, f"{path.name}: an entry without its hashes, or with a marker or another option: {line[:120]}"
        name = _name(match[1])
        assert name not in found, f"{path.name} names {name} twice"
        found[name] = (match[2], re.findall(r"[0-9a-f]{64}", match[3]))
    return found


def _missing(lock_path, platform):
    """Every pin of the inputs, for `platform`, that the lock does not hold at
    its version, as `name==version`."""
    from packaging.markers import Marker

    environment = {"sys_platform": platform, "python_version": "3.14", "python_full_version": "3.14.0",
                   "implementation_name": "cpython", "platform_python_implementation": "CPython",
                   "os_name": "nt" if platform == "win32" else "posix",
                   "platform_system": "Windows" if platform == "win32" else "Darwin"}
    entries = _entries(lock_path)
    wanted = [(name, version) for path in INPUTS for name, version, marker in _inputs(EXECUTABLE_DIR / path)
              if marker is None or Marker(marker).evaluate(environment)]
    return [f"{name}=={version}" for name, version in wanted if entries.get(name, (None,))[0] != version]


@pytest.mark.parametrize("runner", list(SYSTEMS))
def test_each_lock_holds_every_pin_of_its_inputs_for_its_system(runner):
    _, lock, _, platform = SYSTEMS[runner]
    entries = _entries(EXECUTABLE_DIR / lock)
    assert len(entries) >= 60, sorted(entries)
    assert _missing(EXECUTABLE_DIR / lock, platform) == []
    # PyInstaller and its hooks; the two data packages whose releases decide
    # answers; the Windows-only Qt binding on Windows alone.
    assert {"pyinstaller", "pyinstaller-hooks-contrib", "tzdata", "timezonefinder-data", "pyswisseph"} <= set(entries)
    assert ("pyside6" in entries) is (platform == "win32")


def test_a_lock_missing_a_name_or_holding_another_version_is_caught(tmp_path):
    lock = (EXECUTABLE_DIR / "requirements-build-macos.lock").read_text(encoding="utf-8")
    planted = tmp_path / "requirements-build-macos.lock"
    without = re.sub(r"(?m)^tzdata==.*\n(?:    .*\n)*", "", lock)
    assert without != lock
    planted.write_text(without, encoding="utf-8")
    assert _missing(planted, "darwin") == ["tzdata==2026.5"]
    planted.write_text(lock.replace("\npyinstaller==6.22.3 ", "\npyinstaller==6.22.2 "), encoding="utf-8")
    assert _missing(planted, "darwin") == ["pyinstaller==6.22.3"]


@pytest.mark.parametrize("runner", list(SYSTEMS))
def test_each_lock_says_how_it_is_rewritten_for_its_system_and_the_builds_python(runner):
    _, lock, platform, _ = SYSTEMS[runner]
    python = _jobs()["build"]["steps"][1]["with"]["python-version"]
    assert python == "3.14", python
    command = (f"uv pip compile --python-version {python} --python-platform {platform} --generate-hashes "
               f"{' '.join(INPUTS)} -o {lock}")
    head = (EXECUTABLE_DIR / lock).read_text(encoding="utf-8").split("\n")[:2]
    assert head == ["# This file was autogenerated by uv via the following command:", f"#    {command}"], head


# --------------------------------------------------------------------------
# SHA256SUMS: the checksums of exactly the files the draft carries.

def _checksum_differences(workflow):
    """Every way the release job's checksums fall short, as sentences: the
    file is made of exactly the zips the create attaches, by one
    `sha256sum` into SHA256SUMS in the create's own step, after the step
    that downloads the zips and before the create, and the create attaches
    it once."""
    steps = workflow["jobs"][RELEASE_JOB].get("steps") or []
    at = [n for n, step in enumerate(steps)
          if any(argv[:3] == ["gh", "release", "create"] for argv in _commands(step.get("run")))]
    if len(at) != 1:
        return [f"{len(at)} steps create the release"]
    downloads = [n for n, step in enumerate(steps) if str(step.get("uses", "")).startswith("actions/download-artifact@")]
    commands, lines = _commands(steps[at[0]]["run"]), _script_lines(steps[at[0]]["run"])
    create = [argv for argv in commands if argv[:3] == ["gh", "release", "create"]][0]
    off = []
    if not downloads or max(downloads) > at[0]:
        off.append("the zips are not downloaded before the step that creates the release")
    sums = [n for n, argv in enumerate(commands) if argv[0] == "sha256sum"]
    if len(sums) != 1:
        return off + [f"{len(sums)} sha256sum commands, not one"]
    files = commands[sums[0]][1:]
    attached = [token for token in create[4:] if not token.startswith("-")]
    values = {create[i + 1] for i, token in enumerate(create) if token in ("--title", "--notes")}
    attached = [token for token in attached if token not in values]
    if files != ZIPS or attached != ZIPS + ["SHA256SUMS"]:
        off.append(f"the checksums cover {files}, the draft attaches {attached}")
    if [line for line in lines if line.startswith("sha256sum ")] != [f"sha256sum {' '.join(ZIPS)} > SHA256SUMS"]:
        off.append("the checksums are not written to SHA256SUMS")
    if not sums[0] < commands.index(create):
        off.append("the checksums are made after the create")
    return off


def test_the_draft_carries_the_checksums_of_exactly_the_zips_it_attaches():
    assert _checksum_differences(_workflow()) == []
    # The zips are the ones the build legs package and hand over.
    packaged = [argv for _, step in _steps() for argv in _commands(step.get("run"))
                if argv[0] in ("zip", "Compress-Archive")]
    assert [argv for argv in packaged if any(name in " ".join(argv) for name in ZIPS)], packaged


_SUMS = "          sha256sum Zij-windows.zip Zij-macos.zip > SHA256SUMS\n"


@pytest.mark.parametrize("anchor, planted", [
    (_SUMS, ""),
    (_SUMS, "          sha256sum Zij-windows.zip > SHA256SUMS\n"),
    (_SUMS, "          sha256sum Zij-*.zip > SHA256SUMS\n"),
    (_SUMS, "          sha256sum Zij-windows.zip Zij-macos.zip > CHECKSUMS\n"),
    ("Zij-macos.zip SHA256SUMS --draft", "Zij-macos.zip --draft"),
], ids=["removed", "one-zip", "a-pattern", "another-file", "not-attached"])
def test_checksums_that_do_not_cover_what_the_draft_carries_are_caught(anchor, planted):
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count(anchor) == 1
    assert _checksum_differences(load_yaml(text.replace(anchor, planted))) != [], planted


def _replay_the_create_step(tmp_path, zips):
    """The create step's own script, run as the runner runs a bash step
    (`bash --noprofile --norc -eo pipefail`), in a folder holding `zips`
    (name -> bytes), with a stand-in `gh` first on the PATH: it says the tag
    has no release, and records each call with whether SHA256SUMS then
    stood beside it and what it held. (exit status, the calls, the
    folder)."""
    import hashlib

    (_, step), = [(n, s) for n, s in enumerate(_jobs()[RELEASE_JOB]["steps"]) if "run" in s]
    folder, bin_ = tmp_path / "work", tmp_path / "bin"
    folder.mkdir()
    bin_.mkdir()
    for name, data in zips.items():
        (folder / name).write_bytes(data)
    calls = tmp_path / "calls.jsonl"
    (bin_ / "gh").write_text(
        "#!" + sys.executable + "\nimport json, os, sys\n"
        "sums = 'SHA256SUMS'\n"
        "held = open(sums).read() if os.path.exists(sums) else None\n"
        f"open({str(calls)!r}, 'a').write(json.dumps([sys.argv[1:], held]) + '\\n')\n"
        "sys.exit(1 if sys.argv[1:3] == ['release', 'view'] else 0)\n", encoding="utf-8")
    (bin_ / "gh").chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(step["run"], encoding="utf-8")
    env = {"PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}", "GITHUB_REF_NAME": "v9.9.9", "HOME": str(tmp_path),
           "LC_ALL": "C"}
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)], cwd=folder, env=env,
                          capture_output=True, text=True, timeout=60)
    recorded = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
    sums = {name: hashlib.sha256(data).hexdigest() for name, data in zips.items()}
    return done, recorded, folder, sums


def test_replayed_the_checksums_cover_exactly_the_zips_and_stand_before_the_create(tmp_path):
    zips = {"Zij-windows.zip": b"PK windows " * 1000, "Zij-macos.zip": b"PK macos " * 1000,
            "Zij-other.zip": b"not attached"}
    done, calls, folder, sums = _replay_the_create_step(tmp_path, zips)
    assert done.returncode == 0, done.stderr
    assert [argv for argv, _ in calls] == [
        ["release", "view", "v9.9.9"],
        ["release", "create", "v9.9.9", *ZIPS, "SHA256SUMS", "--draft", "--verify-tag", "--title",
         "Z\u012bj (\u0632\u0650\u064a\u062c) v9.9.9", "--notes", ""]]
    expected = "".join(f"{sums[name]}  {name}\n" for name in ZIPS)
    assert calls[0][1] is None, "no checksums before the refusal's question"
    assert calls[1][1] == expected, "the checksums of exactly the two zips, whole, before the create"
    assert (folder / "SHA256SUMS").read_text() == expected


@pytest.mark.parametrize("present", [["Zij-windows.zip"], ["Zij-macos.zip"], []], ids=["no-macos", "no-windows",
                                                                                     "none"])
def test_replayed_a_zip_missing_stops_the_step_before_the_create(tmp_path, present):
    done, calls, _, _ = _replay_the_create_step(tmp_path, {name: b"PK" for name in present})
    assert done.returncode != 0
    assert [argv[:2] for argv, _ in calls] == [["release", "view"]], "nothing is created"


def test_the_documents_say_what_the_draft_and_the_build_carry():
    """The README's download section and the release routine name the
    checksums file; the build notes and the routine's checklist name both
    locks and the hash check."""
    download = README.read_text(encoding="utf-8").split("## Download", 1)[1].split("\n## ", 1)[0]
    assert "`SHA256SUMS`" in download
    releasing = " ".join(RELEASING.read_text(encoding="utf-8").split())
    notes = " ".join(BUILD_NOTES.read_text(encoding="utf-8").split())
    for text in (releasing, notes):
        assert "`SHA256SUMS`" in text
        assert sorted(lock for lock in LOCKS if lock in text) == sorted(LOCKS) == [
            "requirements-build-macos.lock", "requirements-build-windows.lock"]
        assert "--require-hashes" in text
    assert "is byte-for-byte what the tag would produce" not in releasing
    assert "not a byte-for-byte copy of this one" in releasing, "the tag's build is a build of its own"


# --------------------------------------------------------------------------
# The stop check: the known value, read here as the download reads it.

def test_the_known_longitude_is_the_one_the_app_draws_here_in_the_minute_the_engine_tests_pin(engine):
    """The app opened as a reader opens it (the example chart, its city from
    the atlas) draws Jupiter at the stop check's value, to the six places
    the wheel gives; and that value is 20 Aries 52, the degree and minute
    the engine's own tests pin for the example chart."""
    from streamlit.testing.v1 import AppTest
    from conftest import APP_PATH, sync_engine_to_environment

    module = _module()
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300).run()
    assert not at.exception, [e.value for e in at.exception]
    svg = natal_wheel_envelope(at.main)["svg"]
    found = re.findall(rf'data-point="{module.KNOWN_POINT}" data-lon="([^"]+)"', svg)
    assert found == [f"{module.KNOWN_LONGITUDE:.6f}"], found
    assert engine["get_degree_string"](module.KNOWN_LONGITUDE) == "20° Ari 52'"
    assert 0 < module.KNOWN_TOLERANCE <= 1e-4, "within a third of an arc-second, never a whole minute"


def _wheel(svg_points):
    svg = "".join(f'<g class="pt" data-point="{name}" data-lon="{lon}"></g>' for name, lon in svg_points)
    return ("component", "natal_wheel", json.dumps({"svg": f"<svg>{svg}</svg>", "width": 1, "signs": []}))


@pytest.mark.parametrize("elements, said", [
    ([_wheel([("Sun", "69.165257"), ("Jupiter", "20.876328")])], None),
    ([_wheel([("Jupiter", "20.876335")])], None),
    ([_wheel([("Jupiter", "21.876328")])], "puts Jupiter at 21.876328, not 20.876328"),
    ([_wheel([("Jupiter", "20.876350")])], "puts Jupiter at 20.876350, not 20.876328"),
    ([_wheel([("Jupiter", "nan")])], "puts Jupiter at nan, not 20.876328"),
    ([], "drew no chart wheel(s), not one"),
    ([_wheel([("Jupiter", "20.876328")])] * 2, "drew 2 chart wheel(s), not one"),
    ([_wheel([("Sun", "69.165257")])], "places Jupiter 0 time(s) in a form that can be read, not once"),
    ([_wheel([("Jupiter", "x")])], "places Jupiter 1 time(s) in a form that can be read, not once"),
    ([("component", "natal_wheel", "not json")], "holds no drawing that can be read"),
    ([("component", "another_component", "{}")], "drew no chart wheel(s), not one"),
], ids=["read", "within-the-bound", "a-degree-off", "beyond-the-bound", "not-a-number", "no-wheel", "two-wheels",
        "no-jupiter", "unreadable-value", "unreadable-data", "another-component"])
def test_the_known_value_is_read_from_the_one_wheel_and_held_to_its_bound(elements, said):
    module = _module()
    check = object.__new__(module.Check)
    launch = type("Launch", (), {"number": 3})()
    if said is None:
        assert check._known_value(launch, elements).startswith("the example chart's wheel puts Jupiter at ")
    else:
        with pytest.raises(module.CheckFailed) as failed:
            check._known_value(launch, elements)
        assert said in str(failed.value), str(failed.value)


def test_a_component_is_read_by_its_name_and_data():
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    module = _module()
    msg = ForwardMsg()
    msg.metadata.delta_path.extend([1, 0, 3])
    msg.delta.new_element.bidi_component.component_name = "natal_wheel"
    msg.delta.new_element.bidi_component.json = '{"svg": "<svg/>"}'
    data = msg.SerializeToString()
    assert module.read_forward(data) == ("element", ("component", "natal_wheel", '{"svg": "<svg/>"}'))
    assert module.message_kind(data) == ("element", "a component 'natal_wheel'")


# --------------------------------------------------------------------------
# The stop check, live: each refusal and the known value taken out in turn.

_SWISSEPH_A_DEGREE_OFF = '''"""A stand-in for a build of Swiss Ephemeris that computes otherwise: the
real extension, every longitude it gives a degree further on."""
import importlib.machinery
import importlib.util
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _entry in sys.path:
    if os.path.abspath(_entry or ".") == _here:
        continue
    _spec = importlib.machinery.PathFinder.find_spec("swisseph", [_entry])
    if _spec is not None and _spec.origin and not _spec.origin.endswith(".py"):
        break
else:
    raise ImportError("no swisseph extension found")
_me = sys.modules[__name__]
_real = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_real)
sys.modules[__name__] = _me          # loading the extension put it in this module's place
globals().update({k: v for k, v in vars(_real).items() if not k.startswith("__")})


def _shifted(call):
    def shifted(*args, **kwargs):
        values, flags = call(*args, **kwargs)
        return ((values[0] + 1.0) % 360.0,) + tuple(values[1:]), flags
    return shifted


calc_ut = _shifted(_real.calc_ut)
calc = _shifted(_real.calc)
'''


def _whole_check(tmp_path, program, pythonpath=(), extra=()):
    """The whole check run as the runner runs it, but on a command: the
    copy's launcher from source, its window a stand-in; nothing the app's
    server looks up leaves this computer."""
    windows, work = tmp_path / "windows", tmp_path / "work"
    windows.mkdir()
    work.mkdir()
    short = tempfile.mkdtemp(dir="/tmp")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("STREAMLIT_")}
    env.pop("ZIJ_LAUNCH_KEY", None)
    env.update(NO_WAY_OUT, **LOADS_ITS_PAGE, TMPDIR=short, PYTHONPATH=os.pathsep.join([*map(str, pythonpath), str(STAND_IN_WEBVIEW)]))
    try:
        argv = [sys.executable, str(SCRIPT), "--work", str(work), "--reach-seconds", "120", "--stop-seconds", "15",
                "--orphan-seconds", "10", "--margin-seconds", "10", *extra, "--stand-in-windows", str(windows),
                "--command", sys.executable, str(program / "desktop_launcher.py")]
        done = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=600)
    finally:
        shutil.rmtree(short, ignore_errors=True)
    assert done.stderr == "", done.stderr
    assert str(tmp_path) not in done.stdout and os.listdir(work) == []
    return done.returncode, done.stdout


def _with_launcher(tmp_path, old, new):
    """A copy of this checkout whose launcher has `old` replaced by `new`."""
    program = _copy(tmp_path)
    text = (EXECUTABLE_DIR / "desktop_launcher.py").read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    (program / "desktop_launcher.py").unlink()
    (program / "desktop_launcher.py").write_text(text.replace(old, new), encoding="utf-8")
    return program


def _with_app(tmp_path, old, new):
    text = (EXECUTABLE_DIR / "app.py").read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    return _copy(tmp_path, app=text.replace(old, new))


def test_live_a_server_that_opens_a_session_from_another_sites_origin_fails_the_check(tmp_path):
    """The origin check off in the launcher's server options: the first
    launch's door fails, naming the Origin."""
    program = _with_launcher(tmp_path, '"--server.enableCORS", "true",', '"--server.enableCORS", "false",')
    code, out = _whole_check(tmp_path, program)
    assert code == 1, out
    failure, _ = _failure_and_details(out)
    assert re.fullmatch(r"stop check FAILED: launch 1: a WebSocket opening under the window's own address from the "
                        r"Origin http://evil\.example was answered 101, not refused with 403: a page of another site "
                        r"could open a session", failure), out


@pytest.mark.parametrize("old, new, who", [
    ("def _admit_only_the_window():\n", "def _admit_only_the_window():\n    return\n",
     "with no key in its address"),
    ("        if not hmac.compare_digest(shown.encode(\"utf-8\", \"surrogatepass\"),\n"
     "                                   expected.encode(\"utf-8\", \"surrogatepass\")):\n",
     "        if len(shown) != len(expected):\n",
     "with a key one letter off the launch's"),
], ids=["no-key-check", "a-length-check"])
def test_live_a_server_that_lets_in_a_session_without_its_key_fails_the_check(tmp_path, old, new, who):
    """The app's key check taken out, or made a check of the key's length
    alone: the third launch's typed place still passes, and then the
    session the server should have refused fails the check, by name."""
    code, out = _whole_check(tmp_path, _with_app(tmp_path, old, new))
    assert code == 1, out
    failure, _ = _failure_and_details(out)
    assert re.fullmatch(rf"stop check FAILED: launch 3: the first run of a session {re.escape(who)} was not "
                        rf"refused: the server never told it that the app can be used only in its own window, and "
                        rf"showed it (\d+) element\(s\)", failure), out
    assert int(re.search(r"showed it (\d+) element", failure)[1]) > 10, "the whole app, let in"
    assert "launch 3: with 'évora' typed in the city search, the run ended after " in out


def test_live_a_server_that_tells_a_session_without_its_key_the_sentence_and_more_fails_the_check(tmp_path):
    """The app's refusal that says its sentence but does not stop there: the
    session without the key is shown the app after it, and the check fails
    on the sentence not standing alone."""
    old = "            st.info(_LAUNCH_KEY_REFUSAL)\n            st.stop()\n"
    code, out = _whole_check(tmp_path, _with_app(tmp_path, old, "            st.info(_LAUNCH_KEY_REFUSAL)\n"))
    assert code == 1, out
    failure, _ = _failure_and_details(out)
    assert re.fullmatch(r"stop check FAILED: launch 3: the first run of a session with no key in its address was "
                        r"told that the app can be used only in its own window, but shown (\d+) element\(s\), not "
                        r"that sentence alone", failure), out


def test_live_a_build_whose_swiss_ephemeris_computes_otherwise_fails_the_check(tmp_path):
    """A stand-in for a build of Swiss Ephemeris that puts every longitude a
    degree further on, first on the path of every process of the launch:
    the place is still found, and the check fails on the example chart's
    Jupiter."""
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "swisseph.py").write_text(_SWISSEPH_A_DEGREE_OFF, encoding="utf-8")
    code, out = _whole_check(tmp_path, _copy(tmp_path), pythonpath=[shim])
    assert code == 1, out
    failure, _ = _failure_and_details(out)
    assert failure.startswith("stop check FAILED: launch 3: the example chart's wheel puts Jupiter at 21.87632"), out
    assert failure.endswith(", not 20.876328 (within 1e-05 of a degree), where the app draws it on the system the "
                            "suite runs on: this build's Swiss Ephemeris computes otherwise"), out
    assert "launch 3: with 'évora' typed in the city search, the run ended after " in out


def test_live_a_window_that_is_shown_the_refusal_fails_the_check(tmp_path):
    """The launcher's window given an address whose key is one letter more
    than its server's: the window's session is refused, its server never
    computes for it, and the first launch fails on the window's admission;
    the door and the window log held before it."""
    program = _with_launcher(tmp_path, 'window_url = f"{url}/?{LAUNCH_KEY_PARAMETER}={secret}"',
                             'window_url = f"{url}/?{LAUNCH_KEY_PARAMETER}={secret}x"')
    code, out = _whole_check(tmp_path, program, extra=["--run-seconds", "15"])
    assert code == 1, out
    failure, _ = _failure_and_details(out)
    assert re.fullmatch(r"stop check FAILED: launch 1: the window's own session never ran the app within 15 s: the "
                        r"server holds no file the app's page hands its window, which a session it lets in is given "
                        r"on its first run \(\d+ session\(s\) open, [1-9]\d* opened in all\): the window shows the "
                        r"refusal, or never loaded the page", failure), out
    assert "launch 1: window log found in the app's data folder" in out and "closed by" not in out


def test_live_the_window_that_loads_its_page_with_its_key_is_seen_to_run_the_app(tmp_path):
    """The launcher as it is: in each of the two window launches the check
    sees the window's own session run the app, naming what the engine
    computed for it."""
    code, out = _whole_check(tmp_path, _copy(tmp_path))
    assert code == 0, out
    lines = [line for line in out.splitlines() if "the window's own session ran the app" in line]
    assert [line.split(":", 1)[0] for line in lines] == ["launch 1", "launch 2"], out
    assert len(lines) == 2, out
    for line in lines:
        assert re.search(r"the server holds [1-9]\d* byte\(s\) of files the app's page hands its window, which "
                         r"only a session it lets in is given, and (?:[1-9]\d* result\(s\) of the engine's \(|no "
                         r"result of the engine's yet)", line), line
        assert line.endswith("; this check opened no session that ran the app"), line


_METRICS = """# TYPE cache_memory_bytes gauge
cache_memory_bytes{cache_type="st_session_state",cache=""} 46
cache_memory_bytes{cache_type="st_cache_data",cache="engine._sin_altitude"} 3402
cache_memory_bytes{cache_type="st_cache_data",cache="engine.calculate_prenatal_syzygy"} 593
cache_memory_bytes{cache_type="st_cache_data",cache="app.something_else"} 10
cache_memory_bytes{cache_type="st_memory_media_file_storage",cache=""} 1314176
session_events_total{type="connect"} 2
session_events_total{type="reconnect"} 0
active_sessions 2
# EOF
"""


# As the server shows them, past its metrics' five-second cache: refused sessions (no key, a key a letter off,
# another query) each leave a unit of state and nothing else; an admitted one, files and the engine's results,
# or only files where the example's city cannot be found (the atlas taken away).
_REFUSED_THREE = 'cache_memory_bytes{cache_type="st_session_state",cache=""} 3\nactive_sessions 3\n'
_ADMITTED_WITHOUT_A_CHART = ('cache_memory_bytes{cache_type="st_memory_media_file_storage",cache=""} 28631\n'
                             'cache_memory_bytes{cache_type="st_session_state",cache=""} 34\nactive_sessions 4\n')


@pytest.mark.parametrize("status, body, media, found, sessions", [
    (200, _METRICS, 1314176, ["_sin_altitude", "calculate_prenatal_syzygy"], "2 session(s) open, 2 opened in all"),
    (200, "session_events_total{type=\"connect\"} 1\nactive_sessions 1\n# EOF\n", 0, [],
     "1 session(s) open, 1 opened in all"),
    (200, _REFUSED_THREE, 0, [], "3 session(s) open, ? opened in all"),
    (200, _ADMITTED_WITHOUT_A_CHART, 28631, [], "4 session(s) open, ? opened in all"),
    (200, _METRICS.replace("engine.", "engine_").replace("st_memory_media", "st_other_media"), 0, [],
     "2 session(s) open, 2 opened in all"),
    (404, "no", 0, [], "its metrics did not answer"),
], ids=["admitted", "no-session", "three-refused", "admitted-without-a-chart", "other-names", "no-metrics"])
def test_the_sessions_are_read_from_the_servers_metrics(status, body, media, found, sessions):
    import http.server
    import threading

    class Metrics(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            data = body.encode("utf-8") if self.path == "/_stcore/metrics" else b""
            self.send_response(status if self.path == "/_stcore/metrics" else 404)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Metrics)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert _module()._sessions_seen(server.server_address[1]) == (media, found, sessions)
    finally:
        server.shutdown()
        server.server_close()


# --------------------------------------------------------------------------
# The log is UTF-8, whatever the output's own encoding.

_SAYS_A_PLACE = "import sys; sys.stdout.buffer.write('\\u00e9vora\\n'.encode('utf-8')); sys.exit(3)"


def test_the_checks_log_is_utf8_where_its_output_would_be_a_code_page(tmp_path):
    """Its output a pipe in Windows' ANSI code page (cp1252 here): a launcher
    that ends at once having written a place's name, which a failure prints,
    reaches the log as UTF-8, not as the code page's byte."""
    windows, work = tmp_path / "windows", tmp_path / "work"
    windows.mkdir()
    work.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("STREAMLIT_")}
    env.update(PYTHONIOENCODING="cp1252")
    argv = [sys.executable, str(SCRIPT), "--work", str(work), "--reach-seconds", "5", "--stand-in-windows",
            str(windows), "--command", sys.executable, "-c", _SAYS_A_PLACE]
    done = subprocess.run(argv, capture_output=True, env=env, timeout=120)
    assert done.returncode == 1, done.stdout
    # Ended before or after the check first saw it: either way it ended, and its output is printed.
    assert re.search(rb"stop check FAILED: launch 1: the launcher ended (?:at once )?\(exit 3\)", done.stdout), \
        done.stdout
    assert b"\n    | \xc3\xa9vora\n" in done.stdout, done.stdout
    assert b"\xe9vora" not in done.stdout.replace(b"\xc3\xa9vora", b""), done.stdout
