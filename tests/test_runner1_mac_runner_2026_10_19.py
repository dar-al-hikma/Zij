"""Where the macOS build runs, and what it builds from there.

* In a private repository, the development one, the macOS leg asks for the
  project's own Mac by `colophon`, the one label no other runner carries:
  never by `self-hosted`, which the test suite's jobs ask for, nor by a
  label another runner could carry. One label, not the Mac's list of them:
  a list an entry's expression yields is spliced into the matrix, a leg for
  each item, and a run that asked for `macOS`, `ARM64` and `colophon` so
  built on the Mac three times. In a public repository, where a release tag
  builds and GitHub's macOS minutes are free, it asks for GitHub's
  `macos-26`, the arm64 image, by its own name: the Mac is registered to the development repository
  alone, so a tag asking for it there would wait until GitHub gave up and
  no release would be drafted. The choice is read from the repository's
  visibility, as the expression in the matrix says; Windows builds on
  `windows-2025-vs2026` in both. Each form that would send a
  leg elsewhere, planted in a copy of the workflow, is refused.
* On the Mac the Python that setup-python finds is the machine's own and
  outlives the run, so the macOS leg makes an environment from it in the
  job's temporary folder, which the runner empties after every job, and
  puts that environment first on the path before anything is installed.
  The step is pinned whole: the two lines, on macOS for every trigger and
  never on Windows, after setup-python and before the install, with nothing
  that could let its failure pass. Each form that would build from the
  machine's own packages, or from no environment at all, planted, is
  refused.
"""
import pytest

from test_sec4_build_workflow_2026_10_13 import (BUILD_RUNNERS, DISPATCHES, PUSH_TAG, WORKFLOW, _commands,
                                                 _runner_differences, _script_lines, _workflow, evaluate, load_yaml)


# --------------------------------------------------------------------------
# The runner each leg asks for.

_MAC_ENTRY = "          - ${{ github.event.repository.private && 'colophon' || 'macos-26' }}\n"
_RUNS_ON = "    runs-on: ${{ matrix.os }}\n"


def test_each_leg_asks_for_its_runner_by_the_repositorys_visibility():
    assert _runner_differences(_workflow()) == []
    assert BUILD_RUNNERS["private"][1] == "colophon", "the premise: the Mac is asked for by its own label alone"
    assert BUILD_RUNNERS["public"] == ["windows-2025-vs2026", "macos-26"], \
        "the premise: a public repository asks for GitHub's runners alone, each by its image's name"


@pytest.mark.parametrize("anchor, planted", [
    (_MAC_ENTRY, "          - colophon\n"),
    (_MAC_ENTRY, "          - macos-26\n"),
    (_MAC_ENTRY, _MAC_ENTRY.replace("'macos-26'", "'macos-latest'")),
    (_MAC_ENTRY, _MAC_ENTRY.replace("'macos-26'", "'macos-26-intel'")),
    (_MAC_ENTRY, _MAC_ENTRY.replace("${{ github", "${{ !github")),
    (_MAC_ENTRY, _MAC_ENTRY.replace("github.event.repository.private", "github.repository != 'dar-al-hikma/Zij'")),
    (_MAC_ENTRY, _MAC_ENTRY.replace("'colophon'", "fromJSON('[\"macOS\", \"ARM64\", \"colophon\"]')")),
    (_MAC_ENTRY, _MAC_ENTRY.replace("'colophon'", "'self-hosted'")),
    (_MAC_ENTRY, _MAC_ENTRY.replace("'colophon'", "'macOS'")),
    (_MAC_ENTRY, _MAC_ENTRY + "          - ubuntu-latest\n"),
    (_RUNS_ON, "    runs-on: macos-26\n"),
], ids=["always-the-mac", "never-the-mac", "a-moving-label", "the-intel-image", "visibility-reversed", "by-name",
        "the-labels-as-a-list", "a-self-hosted-label", "any-mac", "a-third-leg", "runs-on-fixed"])
def test_a_leg_sent_to_another_runner_is_caught(anchor, planted):
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count(anchor) == 1, anchor
    assert _runner_differences(load_yaml(text.replace(anchor, planted))) != [], planted


# --------------------------------------------------------------------------
# The environment the macOS build installs into.

ENVIRONMENT_STEP_KEYS = {"name": "Start from an empty environment (macOS)", "shell": "bash"}
ENVIRONMENT_LINES = [
    'python -m venv "$RUNNER_TEMP/build-venv"',
    'echo "$RUNNER_TEMP/build-venv/bin" >> "$GITHUB_PATH"',
]
_ALLOWED_KEYS = {"name", "if", "shell", "run"}


def _environment_differences(workflow):
    """Every way the build's environment step differs from the pin, as
    sentences: one step makes an environment; it is exactly the name, the
    shell and the two lines above, with no key beyond those and its `if`;
    it runs on macOS for a tag push and a manual run alike, and never on
    Windows; and on macOS it runs after setup-python and before the first
    install."""
    steps = workflow["jobs"]["build"]["steps"]
    found = [n for n, step in enumerate(steps) if "venv" in str(step.get("run", ""))]
    if len(found) != 1:
        return [f"{len(found)} steps make an environment, not one"]
    at = found[0]
    step = steps[at]
    off = []
    if set(step) - _ALLOWED_KEYS:
        off.append(f"the step carries {sorted(set(step) - _ALLOWED_KEYS)}")
    keys = {key: value for key, value in step.items() if key in ENVIRONMENT_STEP_KEYS}
    if keys != ENVIRONMENT_STEP_KEYS:
        off.append(f"the step carries {keys!r}, not {ENVIRONMENT_STEP_KEYS!r}")
    if _script_lines(step.get("run")) != ENVIRONMENT_LINES:
        off.append(f"the step's lines are {_script_lines(step.get('run'))!r}")
    for context in [PUSH_TAG] + DISPATCHES:
        for system, wanted in (("macOS", True), ("Windows", False)):
            ctx = dict(context, **{"runner.os": system})
            try:
                runs = step.get("if") is None or evaluate(step["if"], ctx)
            except ValueError as error:
                off.append(f"the step's condition cannot be read: {error}")
                return off
            if runs is not wanted:
                off.append(f"on {system} ({context['github.event_name']}, {context['github.ref']}) the step "
                           f"{'does not run' if wanted else 'runs'}")
    mac = dict(PUSH_TAG, **{"runner.os": "macOS"})
    setups = [n for n, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/setup-python@")]
    installs = [n for n, s in enumerate(steps) if (s.get("if") is None or evaluate(s["if"], mac))
                and any(argv[:2] == ["pip", "install"] for argv in _commands(s.get("run")))]
    if not setups or not installs or not max(setups) < at < min(installs):
        off.append(f"the step is step {at}, not between setup-python {setups} and the install {installs}")
    return off


def test_the_macos_build_installs_into_an_environment_of_its_own():
    assert _environment_differences(_workflow()) == []


_VENV_LINE = '          python -m venv "$RUNNER_TEMP/build-venv"\n'
_PATH_LINE = '          echo "$RUNNER_TEMP/build-venv/bin" >> "$GITHUB_PATH"\n'
_STEP_HEAD = ("      - name: Start from an empty environment (macOS)\n        if: runner.os == 'macOS'\n"
              "        shell: bash\n")
_ENVIRONMENT_STEP = _STEP_HEAD + "        run: |\n" + _VENV_LINE + _PATH_LINE
_MAC_INSTALL = ("      - name: Install dependencies (macOS)\n        if: runner.os == 'macOS'\n"
                "        run: pip install --require-hashes -r requirements-build-macos.lock\n")

PLANTS = {
    "the-machines-packages": [(_VENV_LINE, _VENV_LINE.replace("venv ", "venv --system-site-packages "))],
    "outside-the-temporary-folder": [(_VENV_LINE, _VENV_LINE.replace("$RUNNER_TEMP", "$HOME")),
                                     (_PATH_LINE, _PATH_LINE.replace("$RUNNER_TEMP", "$HOME"))],
    "not-on-the-path": [(_PATH_LINE, _PATH_LINE.replace("GITHUB_PATH", "GITHUB_ENV"))],
    "a-line-more": [(_PATH_LINE, _PATH_LINE + "          python -m pip install --upgrade pip\n")],
    "on-windows-too": [(_STEP_HEAD, _STEP_HEAD.replace("        if: runner.os == 'macOS'\n", ""))],
    "self-hosted-only": [(_STEP_HEAD, _STEP_HEAD.replace("runner.os == 'macOS'",
                                                         "runner.environment == 'self-hosted'"))],
    "let-fail": [(_STEP_HEAD, _STEP_HEAD + "        continue-on-error: true\n")],
    "an-env": [(_STEP_HEAD, _STEP_HEAD + "        env:\n          PIP_CONFIG_FILE: pip.conf\n")],
    "after-the-install": [(_ENVIRONMENT_STEP + "\n", ""), (_MAC_INSTALL, _MAC_INSTALL + "\n" + _ENVIRONMENT_STEP)],
    "removed": [(_ENVIRONMENT_STEP, "")],
}


@pytest.mark.parametrize("plant", list(PLANTS))
def test_an_environment_step_that_would_not_isolate_the_build_is_caught(plant):
    text = WORKFLOW.read_text(encoding="utf-8")
    planted = text
    for anchor, replacement in PLANTS[plant]:
        assert planted.count(anchor) == 1, anchor
        planted = planted.replace(anchor, replacement)
    assert planted != text
    assert _environment_differences(load_yaml(planted)) != [], plant
