"""The desktop build workflow: who holds the write token, and when a release
is made.

`.github/workflows/build.yml` installs and runs third-party build tools
(PyInstaller, its hooks, every package `pip` resolves for the app), so the
job that does it holds a read-only token and its checkout keeps no token on
disk. Writing to the repository is one separate job: it runs after both
platforms have built, only for a pushed `v*` tag, and creates one DRAFT
release with no generated notes -- the notes are the maintainer's own
wording, written before publishing by hand. A manual run builds and stops,
whatever ref it was started on, and nothing it can reach replaces a release's
files. Each build machine installs from its own hashed lock and nothing else,
and the macOS zip stores the app bundle's links as links. The release job's
commands are pinned whole, as an exact list.

The workflow is read as YAML, by the small loader below, and the `if:`
conditions are evaluated rather than matched as text. The loader reads only
the subset of YAML a workflow file uses (block mappings and sequences,
literal block scalars, quoted and plain scalars, one-line flow sequences)
and refuses anything else, so it cannot silently misread a construct it
does not know. A YAML library is not in the suite's pinned set.
"""
import json
import os
import re
import shlex
import subprocess
import sys

import pytest

from conftest import EXECUTABLE_DIR

WORKFLOW = EXECUTABLE_DIR / ".github" / "workflows" / "build.yml"
BUILD_REQUIREMENTS = EXECUTABLE_DIR / "requirements-build.txt"
BUILD_NOTES = EXECUTABLE_DIR / "docs" / "BUILD_NOTES.md"
REQUIREMENTS = EXECUTABLE_DIR / "requirements.txt"


# --------------------------------------------------------------------------
# A strict loader for the YAML subset a workflow uses.

class YamlSubsetError(ValueError):
    pass


def _strip_comment(text):
    """`text` without a trailing `# comment` (a `#` at the start or after
    whitespace, outside quotes)."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text.rstrip()


def _split_key(text):
    """(key, rest) when `text` is `key: value` or `key:`, else None."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"" and i == 0:
            quote = ch
        elif ch == ":" and (i + 1 == len(text) or text[i + 1] == " "):
            return _scalar(text[:i].strip()), text[i + 1:].strip()
    return None


def _split_flow(body):
    items, quote, start = [], None, 0
    for i, ch in enumerate(body):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch in "[]{}":
            raise YamlSubsetError(f"nested flow collection: [{body}]")
        elif ch == ",":
            items.append(body[start:i])
            start = i + 1
    items.append(body[start:])
    return [_scalar(item.strip()) for item in items if item.strip()]


def _scalar(text):
    if text == "":
        return None
    if text[0] == "'":
        if len(text) < 2 or text[-1] != "'":
            raise YamlSubsetError(f"unterminated single-quoted scalar: {text}")
        return text[1:-1].replace("''", "'")
    if text[0] == '"':
        if len(text) < 2 or text[-1] != '"':
            raise YamlSubsetError(f"unterminated double-quoted scalar: {text}")
        return json.loads(text)
    if text[0] == "[":
        if text[-1] != "]":
            raise YamlSubsetError(f"multi-line flow sequence: {text}")
        return _split_flow(text[1:-1])
    if text == "{}":
        return {}
    if text[0] in "{&*!|>%@`":
        raise YamlSubsetError(f"construct outside the subset: {text}")
    if ": " in text:
        raise YamlSubsetError(f"a plain scalar holding ': ': {text}")
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    if re.fullmatch(r"-?[0-9]+", text):
        return int(text)
    return text


class _Loader:
    def __init__(self, text):
        if "\t" in text:
            raise YamlSubsetError("a tab in the file")
        self.lines = text.split("\n")
        self.i = 0

    def _peek(self):
        """(indent, content) of the next line that is not blank or a whole
        comment, moving past those; None at the end."""
        while self.i < len(self.lines):
            line = self.lines[self.i]
            content = _strip_comment(line.strip())
            if content:
                if content in ("---", "...") or content.startswith("%"):
                    raise YamlSubsetError(f"document marker: {content}")
                return len(line) - len(line.lstrip(" ")), content
            self.i += 1
        return None

    def load(self):
        top = self._peek()
        if top is None or top[0] != 0:
            raise YamlSubsetError("the document does not start at column 0")
        node = self._block(0)
        if self._peek() is not None:
            raise YamlSubsetError(f"unparsed text at line {self.i + 1}")
        return node

    def _block(self, indent):
        _, content = self._peek()
        if content == "-" or content.startswith("- "):
            return self._sequence(indent)
        return self._mapping(indent)

    def _value(self, indent, rest):
        """The value of a key at `indent` whose text after the colon is
        `rest`."""
        self.i += 1
        if rest in ("|", "|-"):
            return self._literal(indent, keep_newline=(rest == "|"))
        if rest == "":
            nxt = self._peek()
            if nxt is None:
                return None
            if nxt[0] > indent:
                return self._block(nxt[0])
            if nxt[0] == indent and (nxt[1] == "-" or nxt[1].startswith("- ")):
                return self._sequence(indent)
            return None
        return _scalar(rest)

    def _mapping(self, indent):
        node = {}
        while True:
            nxt = self._peek()
            if nxt is None or nxt[0] < indent:
                return node
            if nxt[0] > indent:
                raise YamlSubsetError(f"unexpected indent at line {self.i + 1}")
            if nxt[1] == "-" or nxt[1].startswith("- "):
                return node
            pair = _split_key(nxt[1])
            if pair is None:
                raise YamlSubsetError(f"not a `key: value` line: {nxt[1]}")
            key, rest = pair
            if key in node:
                raise YamlSubsetError(f"duplicate key {key!r}")
            node[key] = self._value(indent, rest)

    def _sequence(self, indent):
        node = []
        while True:
            nxt = self._peek()
            if nxt is None or nxt[0] != indent:
                if nxt is not None and nxt[0] > indent:
                    raise YamlSubsetError(f"unexpected indent at line {self.i + 1}")
                return node
            if not (nxt[1] == "-" or nxt[1].startswith("- ")):
                return node
            line = self.lines[self.i]
            after = line[indent + 1:]
            item = after.lstrip(" ")
            if _strip_comment(item) == "":
                self.i += 1
                deeper = self._peek()
                if deeper is None or deeper[0] <= indent:
                    node.append(None)
                else:
                    node.append(self._block(deeper[0]))
                continue
            column = indent + 1 + (len(after) - len(item))
            if _split_key(_strip_comment(item)) is not None:
                # `- key: value` opens a mapping at the item's column.
                self.lines[self.i] = " " * column + item
                node.append(self._mapping(column))
            else:
                self.i += 1
                node.append(_scalar(_strip_comment(item)))

    def _literal(self, indent, keep_newline):
        body, block_indent = [], None
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.strip() == "":
                body.append("")
                self.i += 1
                continue
            here = len(line) - len(line.lstrip(" "))
            if here <= indent:
                break
            if block_indent is None:
                block_indent = here
            if here < block_indent:
                raise YamlSubsetError(f"block scalar dedent at line {self.i + 1}")
            body.append(line[block_indent:])
            self.i += 1
        while body and body[-1] == "":
            body.pop()
        return "\n".join(body) + ("\n" if keep_newline and body else "")


def load_yaml(text):
    return _Loader(text).load()


def test_the_loader_reads_the_constructs_the_workflow_uses():
    sample = (
        "on:\n  push:\n    tags: ['v*', \"x\"]\n  workflow_dispatch:\n"
        "permissions: {}\n"
        "jobs:\n  a:\n    needs: [b, c]  # comment\n    steps:\n"
        "      - uses: x/y@abc # v1\n        with:\n          k: false\n"
        "      - run: |\n          echo '# kept'\n\n          two\n        name: n\n"
        "      -\n        name: m\n"
    )
    assert load_yaml(sample) == {
        "on": {"push": {"tags": ["v*", "x"]}, "workflow_dispatch": None},
        "permissions": {},
        "jobs": {"a": {"needs": ["b", "c"], "steps": [
            {"uses": "x/y@abc", "with": {"k": False}},
            {"run": "echo '# kept'\n\ntwo\n", "name": "n"},
            {"name": "m"},
        ]}},
    }


def test_the_loader_refuses_what_it_does_not_know():
    refused = 0
    for text in ("a: &x 1\n", "a: {b: 1}\n", "a: 1\na: 2\n", "a: b: c\n",
                 "---\na: 1\n", "a: >\n  folded\n", "a:\n\t- 1\n"):
        try:
            load_yaml(text)
        except YamlSubsetError:
            refused += 1
    assert refused == 7


# --------------------------------------------------------------------------
# A small evaluator for the `if:` expressions the workflow uses.

_TOKEN = re.compile(r"\s*(?:(==|!=|&&|\|\||[!(),])|'((?:[^']|'')*)'|([A-Za-z_][\w.-]*))")


def _tokens(expr):
    expr = expr.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2]
    out, pos = [], 0
    expr = expr.rstrip()
    while pos < len(expr):
        match = _TOKEN.match(expr, pos)
        if not match or match.end() == pos:
            raise ValueError(f"cannot read the condition at {expr[pos:]!r}")
        op, string, name = match.groups()
        out.append(("op", op) if op else ("str", string.replace("''", "'"))
                   if string is not None else ("name", name))
        pos = match.end()
    return out


def evaluate(expr, context):
    """The truth of a GitHub `if:` expression under `context` (a dict from
    `github.event_name`, `github.ref`, `runner.os` to their values). String
    comparison is case-insensitive, as GitHub's is. A name or function this
    evaluator does not know is an error, never a guess."""
    tokens = _tokens(expr)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else (None, None)

    def take(kind=None, value=None):
        nonlocal pos
        tok = peek()
        if (kind and tok[0] != kind) or (value and tok[1] != value):
            raise ValueError(f"expected {value or kind} in {expr!r}, found {tok}")
        pos += 1
        return tok

    def primary():
        kind, value = peek()
        if kind == "op" and value == "!":
            take()
            return not truthy(primary())
        if kind == "op" and value == "(":
            take()
            result = disjunction()
            take("op", ")")
            return result
        if kind == "str":
            take()
            return value
        if kind == "name":
            take()
            if peek() == ("op", "("):
                take()
                args = [] if peek() == ("op", ")") else [disjunction()]
                while peek() == ("op", ","):
                    take()
                    args.append(disjunction())
                take("op", ")")
                low = [str(a).lower() for a in args]
                if value == "startsWith":
                    return low[0].startswith(low[1])
                if value == "endsWith":
                    return low[0].endswith(low[1])
                if value == "contains":
                    return low[1] in low[0]
                if value == "success" and not args:
                    return True
                raise ValueError(f"unknown function {value}")
            if value in ("true", "false"):
                return value == "true"
            if value not in context:
                raise ValueError(f"unknown name {value} in {expr!r}")
            return context[value]
        raise ValueError(f"cannot read {expr!r} at {peek()}")

    def comparison():
        left = primary()
        while peek() in (("op", "=="), ("op", "!=")):
            op = take()[1]
            right = primary()
            same = str(left).lower() == str(right).lower()
            left = same if op == "==" else not same
        return left

    def truthy(value):
        return bool(value)

    def conjunction():
        left = comparison()
        while peek() == ("op", "&&"):
            take()
            right = comparison()
            left = truthy(left) and truthy(right)
        return left

    def disjunction():
        left = conjunction()
        while peek() == ("op", "||"):
            take()
            right = conjunction()
            left = truthy(left) or truthy(right)
        return left

    result = disjunction()
    if pos != len(tokens):
        raise ValueError(f"unread text in {expr!r}")
    return truthy(result)


def test_the_evaluator_reads_the_workflow_shapes():
    tag_push = {"github.event_name": "push", "github.ref": "refs/tags/v1.0.0",
                "runner.os": "macOS"}
    assert evaluate("github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')", tag_push)
    assert not evaluate("${{ github.event_name == 'workflow_dispatch' }}", tag_push)
    assert evaluate("runner.os == 'macos' || !(github.ref == 'x')", tag_push)


# --------------------------------------------------------------------------
# The workflow.

PUSH_TAG = {"github.event_name": "push", "github.ref": "refs/tags/v1.0.0"}
DISPATCHES = [
    {"github.event_name": "workflow_dispatch", "github.ref": "refs/heads/main"},
    {"github.event_name": "workflow_dispatch", "github.ref": "refs/tags/v1.0.0"},
]
NOT_A_RELEASE = DISPATCHES + [
    {"github.event_name": "push", "github.ref": "refs/heads/main"},
    {"github.event_name": "push", "github.ref": "refs/tags/x1.0.0"},
]
OPERATING_SYSTEMS = ("Windows", "macOS", "Linux")
RELEASE_JOB = "release"


def _workflow():
    return load_yaml(WORKFLOW.read_text(encoding="utf-8"))


def _jobs():
    jobs = _workflow()["jobs"]
    assert jobs, "the workflow has no jobs"
    return jobs


def _steps():
    """(job name, step) for every step of every job."""
    steps = [(name, step) for name, job in _jobs().items() for step in job.get("steps") or []]
    assert steps, "the workflow has no steps"
    return steps


def _commands(script):
    """Every simple command in a shell script, as argv lists: lines joined at
    a trailing backslash, comments dropped, split at ; && || and |."""
    script = re.sub(r"\\\n", " ", script or "")
    commands = []
    for line in script.split("\n"):
        lexer = shlex.shlex(line, posix=True, punctuation_chars="();<>|&")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        current, tokens = [], list(lexer)
        skip = False
        for n, token in enumerate(tokens):
            if skip:
                skip = False
            elif token in (";", "&&", "||", "|", "&", "(", ")"):
                if current:
                    commands.append(current)
                current = []
            elif set(token) <= set("<>&") and set(token) & set("<>"):
                # a redirection: drop it, its target, and a file number
                if current and current[-1].isdigit() and n and tokens[n - 1] == current[-1]:
                    current.pop()
                skip = True
            else:
                current.append(token)
        if current:
            commands.append(current)
    for argv in commands:
        while argv and argv[0] in ("if", "then", "else", "elif", "!", "do", "while"):
            argv.pop(0)
    return [argv for argv in commands if argv and argv not in (["fi"], ["done"])]


def _gh_release_calls():
    """(job, step name, argv from `release` on) for every `gh release`
    command in any step."""
    calls = []
    for job, step in _steps():
        for argv in _commands(step.get("run")):
            if argv[:2] == ["gh", "release"]:
                calls.append((job, step.get("name"), argv[1:]))
    return calls


def _reachable(job_name, step, context):
    """Whether `step` of `job_name` runs under `context`, on some runner."""
    job = _jobs()[job_name]
    for system in OPERATING_SYSTEMS:
        ctx = dict(context, **{"runner.os": system})
        job_if = job.get("if")
        if job_if is not None and not evaluate(job_if, {k: v for k, v in ctx.items()
                                                        if k != "runner.os"}):
            continue
        step_if = step.get("if")
        if step_if is None or evaluate(step_if, ctx):
            return True
    return False


def _grants_write(permissions):
    if permissions in ("write-all",):
        return True
    if isinstance(permissions, dict):
        return any(value == "write" for value in permissions.values())
    return False


def test_the_top_level_grants_nothing_written():
    workflow = _workflow()
    top = workflow.get("permissions")
    assert top is None or top in ({}, "read-all") or (
        isinstance(top, dict) and set(top.values()) <= {"read", "none"}), top
    jobs = list(_jobs().values())
    assert jobs
    assert all("permissions" in job for job in jobs), "every job states its own permissions"


def test_only_the_release_job_can_write():
    top = _workflow().get("permissions")
    writers = sorted(name for name, job in _jobs().items()
                     if _grants_write(job.get("permissions", top)))
    assert writers == [RELEASE_JOB]
    assert _jobs()[RELEASE_JOB]["permissions"] == {"contents": "write"}


def test_every_checkout_keeps_no_token_on_disk():
    checkouts = [(job, step) for job, step in _steps()
                 if str(step.get("uses", "")).startswith("actions/checkout@")]
    assert checkouts, "the build checks the repository out"
    for job, step in checkouts:
        assert (step.get("with") or {}).get("persist-credentials") is False, job


def test_the_release_job_waits_for_both_builds():
    needs = _jobs()[RELEASE_JOB]["needs"]
    assert (needs if isinstance(needs, list) else [needs]) == ["build"]
    assert _jobs()["build"]["strategy"]["matrix"]["os"] == ["windows-latest", "macos-latest"]


def test_the_release_runs_only_for_a_pushed_v_tag():
    assert _workflow()["on"]["push"] == {"tags": ["v*"]}
    condition = _jobs()[RELEASE_JOB]["if"]
    assert evaluate(condition, PUSH_TAG)
    assert len(NOT_A_RELEASE) == 4
    for context in NOT_A_RELEASE:
        assert not evaluate(condition, context), context


# The release job, whole: its one action, with exactly these inputs, and its
# one script, line by line as written (quotes, redirections and all), with
# its shell and its environment. A command added, removed or changed in any
# token, a substitution inside a quoted word, an alias or a function fails
# here, however well it would match a pattern.
RELEASE_DOWNLOAD = {"uses": "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
                    "with": {"pattern": "release-*", "merge-multiple": True}}
RELEASE_STEP_KEYS = {"name": "Create the draft release", "shell": "bash",
                     "env": {"GH_TOKEN": "${{ github.token }}", "GH_REPO": "${{ github.repository }}"}}
RELEASE_LINES = [
    'tag="${GITHUB_REF_NAME}"',
    'if gh release view "$tag" >/dev/null 2>&1; then',
    'echo "::error::$tag already has a release; nothing was changed."',
    'exit 1',
    'fi',
    'sha256sum Zij-windows.zip Zij-macos.zip > SHA256SUMS',
    'gh release create "$tag" Zij-windows.zip Zij-macos.zip SHA256SUMS --draft --verify-tag '
    '--title "Z\u012bj (\u0632\u0650\u064a\u062c) $tag" --notes ""',
]
RELEASE_COMMANDS = [
    ["tag=${GITHUB_REF_NAME}"],
    ["gh", "release", "view", "$tag"],
    ["echo", "::error::$tag already has a release; nothing was changed."],
    ["exit", "1"],
    ["sha256sum", "Zij-windows.zip", "Zij-macos.zip"],
    ["gh", "release", "create", "$tag", "Zij-windows.zip", "Zij-macos.zip", "SHA256SUMS", "--draft", "--verify-tag",
     "--title", "Z\u012bj (\u0632\u0650\u064a\u062c) $tag", "--notes", ""],
]
_SUBSTITUTION = re.compile(r"\$\(|`|<\(|>\(")


def _script_lines(script):
    """A script's lines as written, each stripped, without blank lines and
    whole-line comments."""
    return [line.strip() for line in (script or "").split("\n")
            if line.strip() and not line.strip().startswith("#")]


def _release_job_differences(workflow):
    """Every way the release job differs from the exact list above, as
    sentences; none when it is exactly that."""
    job = workflow["jobs"][RELEASE_JOB]
    steps = job.get("steps") or []
    off = []
    if len(steps) != 2:
        return [f"the release job has {len(steps)} step(s), not the download and the one script"]
    download, create = steps
    if download != RELEASE_DOWNLOAD:
        off.append(f"the first step is {download!r}, not the pinned download")
    keys = {key: value for key, value in create.items() if key != "run"}
    if keys != RELEASE_STEP_KEYS:
        off.append(f"the script's step carries {keys!r}, not {RELEASE_STEP_KEYS!r}")
    if _script_lines(create.get("run")) != RELEASE_LINES:
        off.append(f"the script's lines are {_script_lines(create.get('run'))!r}")
    if _commands(create.get("run")) != RELEASE_COMMANDS:
        off.append(f"the script's commands are {_commands(create.get('run'))!r}")
    found = [text for _, text in _strings(job) if _SUBSTITUTION.search(text)]
    if found:
        off.append(f"a substitution in the release job: {found!r}")
    return off


def test_the_release_job_runs_no_build_tool():
    """The job that holds the write token runs exactly the pinned list: the
    download, the refusal of a tag that has a release, the checksums and the
    create. Nothing else, in any form."""
    assert _release_job_differences(_workflow()) == []


def test_the_release_is_one_draft_without_generated_notes():
    calls = _gh_release_calls()
    steps = {(job, name) for job, name, _ in calls}
    assert len(steps) == 1, f"one step calls gh release, not {sorted(steps)}"
    assert {job for job, _ in steps} == {RELEASE_JOB}
    creates = [argv for _, _, argv in calls if argv[1] == "create"]
    assert len(creates) == 1, creates
    create = creates[0]
    assert "--draft" in create and "--verify-tag" in create
    flags = [token.split("=")[0] for token in create if token.startswith("-")]
    for flag in ("--generate-notes", "--notes-from-tag", "--notes-file", "-F", "-n",
                 "--latest", "--discussion-category", "--prerelease", "-p", "-d"):
        assert flag not in flags, flag
    assert flags.count("--draft") == 1 and "--draft" in create, "--draft takes no value"
    assert flags.count("--notes") == 1 and create[create.index("--notes") + 1] == ""
    assert {"Zij-windows.zip", "Zij-macos.zip"} <= set(create)
    assert {argv[1] for _, _, argv in calls} <= {"create", "view"}


# The one line the release's commit and tag carry (docs/RELEASING.md step 3),
# less its version: the draft is titled the same way.
RELEASE_TITLE = "Z\u012bj (\u0632\u0650\u064a\u062c) "


def test_the_draft_is_titled_as_the_releases_commit_and_tag_are():
    """The draft's title is exactly the release's one line with the pushed
    tag: `Z\u012bj (\u0632\u0650\u064a\u062c) $tag`, set once, by its long flag."""
    create = [argv for _, _, argv in _gh_release_calls() if argv[1] == "create"]
    assert len(create) == 1, create
    create = create[0]
    assert [token for token in create if token.split("=")[0] in ("--title", "-t")] == ["--title"], create
    assert create[create.index("--title") + 1] == RELEASE_TITLE + "$tag", create


def test_no_clobber_where_a_dispatch_reaches():
    reachable = [(job, step) for job, step in _steps()
                 if any(_reachable(job, step, ctx) for ctx in DISPATCHES)]
    assert reachable, "a manual run builds"
    for job, step in reachable:
        for argv in _commands(step.get("run")):
            assert "--clobber" not in argv, (job, step.get("name"))
            assert argv[:2] != ["gh", "release"], (job, step.get("name"))
    calls = _gh_release_calls()
    assert calls
    for _, _, argv in calls:
        assert "--clobber" not in argv


def _pip_installs():
    installs = []
    for job, step in _steps():
        for argv in _commands(step.get("run")):
            if argv[:2] == ["pip", "install"] or argv[:4] == ["python", "-m", "pip", "install"]:
                installs.append((job, argv[argv.index("install") + 1:]))
    assert installs, "the build installs its dependencies"
    return installs


def test_the_build_installs_only_pinned_files():
    """Each install is of one hashed lock, checked against its hashes, and
    nothing else: one for Windows, one for macOS."""
    files, installs = [], _pip_installs()
    assert installs
    for job, args in installs:
        assert job == "build", job
        assert args[:2] == ["--require-hashes", "-r"] and len(args) == 3, \
            f"pip install of something not a hashed lock: {args}"
        files.append(args[2])
    assert files == ["requirements-build-windows.lock", "requirements-build-macos.lock"]


def test_every_build_requirement_is_pinned_exactly():
    lines = [line.split("#")[0].strip() for line in
             BUILD_REQUIREMENTS.read_text(encoding="utf-8").split("\n")]
    pins = [line for line in lines if line]
    assert pins
    names = set()
    for line in pins:
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][0-9A-Za-z.+!-]*)", line)
        assert match, f"not an exact pin: {line}"
        names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    assert {"pyinstaller", "pyinstaller-hooks-contrib"} <= names


def _macos_archivers():
    found = []
    for job, step in _steps():
        if not _reachable(job, step, dict(PUSH_TAG)):
            continue
        for argv in _commands(step.get("run")):
            if argv[0] in ("zip", "ditto") and "../Zij-macos.zip" in argv:
                found.append(argv)
    assert len(found) == 1, found
    return found[0]


def test_the_macos_zip_keeps_the_bundles_links():
    argv = _macos_archivers()
    if argv[0] == "zip":
        options = [a for a in argv[1:] if a.startswith("-")]
        short = "".join(a[1:] for a in options if not a.startswith("--"))
        assert "y" in short or "--symlinks" in options, argv
        assert "r" in short or "--recurse-paths" in options, argv
        assert argv[-2:] == ["../Zij-macos.zip", "Zij.app"], argv
    else:
        assert argv[:4] == ["ditto", "-c", "-k", "--keepParent"], argv
        assert argv[-2:] == ["Zij.app", "../Zij-macos.zip"], argv


def test_build_notes_state_that_pyswisseph_is_built_from_its_sdist():
    pins = [line for line in REQUIREMENTS.read_text(encoding="utf-8").split("\n")
            if line.startswith("pyswisseph==")]
    assert len(pins) == 1, pins
    version = pins[0].split("==")[1].strip()
    bullets = [b for b in BUILD_NOTES.read_text(encoding="utf-8").split("\n- ")
               if b.startswith("**pyswisseph is compiled from source")]
    assert len(bullets) == 1, "BUILD_NOTES has one bullet on the pyswisseph build"
    words = " ".join(bullets[0].split())
    assert f"`pyswisseph=={version}`" in words
    assert f"`pyswisseph-{version}.tar.gz`" in words
    assert "on Windows and on macOS pip downloads its" in words


# --------------------------------------------------------------------------
# The release job's own guards: the refusal of a tag that already has a
# release, the queue for two runs of one tag, the one action it uses, and
# the one token anything in the workflow is handed.

def _the_create_step():
    found = [(n, step) for n, step in enumerate(_jobs()[RELEASE_JOB]["steps"])
             if any(argv[:3] == ["gh", "release", "create"] for argv in _commands(step.get("run")))]
    assert len(found) == 1, f"one release step creates, not {len(found)}"
    return found[0]


# The refusal's `if` line: the view of "$tag" itself, with no other argument,
# not negated and chained to nothing, its output sent to /dev/null or merged
# (`>/dev/null`, `2>/dev/null`, `2>&1`, `&>/dev/null`), each a word of its own.
# The words share no first character with the space between them, so the
# pattern cannot backtrack (a line of a hundred redirections fails at once).
_VIEW_IF_LINE = re.compile(r'if gh release view "\$tag"(?: (?:[12]?>(?: ?/dev/null|&[12])|&> ?/dev/null))*; then')


def test_the_refusals_if_line_allows_a_redirection_and_refuses_a_chain():
    """Same-meaning redirections pass; every negation or chain fails."""
    harmless = ['if gh release view "$tag" >/dev/null 2>&1; then',
                'if gh release view "$tag" &>/dev/null; then',
                'if gh release view "$tag" &> /dev/null; then',
                'if gh release view "$tag"; then']
    planted = ['if ! gh release view "$tag" >/dev/null 2>&1; then',
               'if gh release view "$tag" >/dev/null 2>&1 || true; then',
               'if gh release view "$tag" &>/dev/null || true; then',
               'if gh release view "$tag" &>/dev/null && false; then',
               'if gh release view "$tag" &>/dev/null & then',
               'if gh release view "$tag" &>/dev/null; false; then',
               'if gh release view "$tag" | true; then',
               # the shape kept, the refusal defeated: another repository, another tag, a suffix
               'if gh release view "$tag" --repo nobody/none >/dev/null 2>&1; then',
               'if gh release view "$(exit 1)" >/dev/null 2>&1; then',
               'if gh release view "$tag"x >/dev/null 2>&1; then',
               'if gh release view "$tag" "$other" >/dev/null; then',
               'if gh release view "$tag" >/dev/null 2>&1 ; then',
               'if gh release view "$tag" >"$out"; then']
    assert [line for line in harmless if not _VIEW_IF_LINE.fullmatch(line)] == []
    assert [line for line in planted if _VIEW_IF_LINE.fullmatch(line)] == []


def test_the_refusals_if_line_pattern_does_not_backtrack():
    """A long line of redirections that does not end the way the pattern wants
    is refused at once (it took over twenty seconds at 28 repetitions)."""
    import time
    for line in ('if gh release view "$tag"' + " 2>&2" * 26 + "; done",     # seconds for the old pattern
                 'if gh release view "$tag"' + " 2>&2" * 2000 + "; done",
                 'if gh release view "$tag"' + " 2>&1" * 2000 + " ; then",
                 'if gh release view "$tag"' + "2>&2" * 2000):
        start = time.perf_counter()
        assert not _VIEW_IF_LINE.fullmatch(line)
        assert time.perf_counter() - start < 0.5, len(line)


def test_a_tag_that_already_has_a_release_is_refused_before_the_create():
    """The create step asks whether the tag already has a release, and exits
    non-zero when it has, before it creates anything: as commands (the view,
    nothing but messages, a non-zero exit, all before the create) and as the
    script's lines (the exit sits inside `if gh release view ...; then`, not
    its negation, and the `fi` closes before the create)."""
    _, step = _the_create_step()
    commands = _commands(step["run"])
    create_at = [i for i, argv in enumerate(commands) if argv[:3] == ["gh", "release", "create"]]
    assert len(create_at) == 1, create_at
    create_at = create_at[0]
    tag = commands[create_at][3]
    views = [i for i, argv in enumerate(commands) if argv[:3] == ["gh", "release", "view"]]
    assert len(views) == 1, "the step asks once whether the tag has a release"
    view_at = views[0]
    assert commands[view_at] == ["gh", "release", "view", tag], commands[view_at]
    exits = [i for i, argv in enumerate(commands) if argv[0] == "exit" and i > view_at]
    assert exits, "nothing exits after the view"
    exit_at = exits[0]
    assert view_at < exit_at < create_at, (view_at, exit_at, create_at)
    code = commands[exit_at][1:]
    assert len(code) == 1 and code[0].isdigit() and int(code[0]) != 0, commands[exit_at]
    between = commands[view_at + 1:exit_at]
    assert [argv[0] for argv in between] == ["echo"], between
    lines = [line.strip() for line in re.sub(r"\\\n", " ", step["run"]).split("\n")]
    view_line = [n for n, line in enumerate(lines) if "gh release view" in line]
    create_line = [n for n, line in enumerate(lines) if "gh release create" in line]
    assert len(view_line) == 1 and len(create_line) == 1, (view_line, create_line)
    view_line, create_line = view_line[0], create_line[0]
    assert _VIEW_IF_LINE.fullmatch(lines[view_line]), lines[view_line]
    assert tag == "$tag" and lines[0] == 'tag="${GITHUB_REF_NAME}"', lines[0]
    closes = [n for n in range(view_line + 1, len(lines)) if lines[n] == "fi"]
    assert closes, "the refusal's if is never closed"
    fi_line = closes[0]
    assert fi_line < create_line, (fi_line, create_line)
    body = [line for line in lines[view_line + 1:fi_line] if line and not line.startswith("#")]
    assert body and re.fullmatch(r"exit [1-9][0-9]*", body[-1]), body
    assert all(line.startswith("echo ") for line in body[:-1]), body


def test_two_runs_for_one_tag_queue_at_the_release():
    """The release job's concurrency group is per ref, and a second run waits
    for the first rather than cancelling it."""
    assert _jobs()[RELEASE_JOB]["concurrency"] == {
        "group": "release-${{ github.ref }}", "cancel-in-progress": False}


def test_the_release_job_uses_no_action_but_download_artifact():
    """The release job's only action is download-artifact, pinned to a full
    commit SHA, as many times as today; every other step is a `run:`."""
    job = _jobs()[RELEASE_JOB]
    assert "uses" not in job, "the release job is not a called workflow"
    steps = job["steps"]
    uses = [str(step["uses"]) for step in steps if "uses" in step]
    assert len(uses) == 1, uses
    for action in uses:
        assert re.fullmatch(r"actions/download-artifact@[0-9a-f]{40}", action), action
    assert steps and all(("uses" in step) != ("run" in step) for step in steps), steps


def _strings(node, path=()):
    """(path, text) for every key and every string value in the workflow."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                yield path + (key,), key
            yield from _strings(value, path + (key,))
    elif isinstance(node, list):
        for n, value in enumerate(node):
            yield from _strings(value, path + (n,))
    elif isinstance(node, str):
        yield path, node


_A_TOKEN = re.compile(r"\bsecrets\b|github\s*\.\s*token|github\s*\[|GITHUB_TOKEN|_PAT\b", re.IGNORECASE)


def _token_reads(workflow):
    return [(path, text) for path, text in _strings(workflow) if _A_TOKEN.search(text)]


def test_no_secret_is_read_and_the_only_token_is_the_release_steps():
    """No `secrets.` anywhere in the workflow, in a value or a key; the one
    token anything is handed is the create step's GH_TOKEN, and it is the
    run's own `github.token`."""
    found = _token_reads(_workflow())
    n, _ = _the_create_step()
    assert found == [(("jobs", RELEASE_JOB, "steps", n, "env", "GH_TOKEN"), "${{ github.token }}")], found


def test_every_secret_read_is_found_however_it_is_spelt():
    """The finder above catches every form that hands over secrets, the whole
    set (`toJSON(secrets)`) included, planted in the create step's env."""
    text = WORKFLOW.read_text(encoding="utf-8")
    anchor = "          GH_TOKEN: ${{ github.token }}\n"
    assert text.count(anchor) == 1
    n, _ = _the_create_step()
    for plant in ["${{ toJSON(secrets) }}", "${{ secrets.RELEASE_PAT }}", "${{ secrets['RELEASE_PAT'] }}",
                  "${{ toJson( secrets ) }}", "${{ join(secrets, ',') }}"]:
        planted = load_yaml(text.replace(anchor, anchor + f"          ALL: {plant}\n"))
        assert (("jobs", RELEASE_JOB, "steps", n, "env", "ALL"), plant) in _token_reads(planted), plant


# --------------------------------------------------------------------------
# Each build machine checks its own errno names, and scans the names the
# program reads, before it builds.

PLATFORM_CHECK = "tests/test_mac1_platform_names_2026_10_14.py"
# The two steps that run that file, each by its one command: its own check of
# this platform's errno module, and its tests by pytest, the scan of every
# errno name a shipped module reads among them.
PLATFORM_CHECK_COMMANDS = (f"python {PLATFORM_CHECK}", f"python -m pytest -q -p no:cacheprovider {PLATFORM_CHECK}")


def _platform_check_steps(workflow=None):
    """(index, step, argv) for each build step that runs the platform-name
    file, the argv it runs it with."""
    found = []
    jobs = (workflow or _workflow())["jobs"]
    for n, step in enumerate(jobs["build"]["steps"]):
        for argv in _commands(step.get("run")):
            if PLATFORM_CHECK in argv:
                found.append((n, step, argv))
    return found


# GitHub's own shells that end a step at its script's first failure, or with
# the exit status of its one command: bash and sh (-e), PowerShell (its last
# command's status). A custom shell line, or cmd, may not.
_SHELLS_THAT_STOP = (None, "bash", "sh", "pwsh", "powershell")


def _errno_step_lets_a_failure_pass(workflow):
    """Whatever would let the platform-name check fail without failing the
    build job, as sentences: a command beyond the one, which `|| true`,
    `|| :`, `|| exit 0` or `; true` would be; `continue-on-error` on the step
    or its job; a shell, the step's or a default, that does not stop; an
    `env` on the step, its job or the workflow, any value, in any form, since
    a variable can change what the check's interpreter imports and so what
    it does (`PYTHONPATH` and a `sitecustomize` there could end it with 0).
    A variable an earlier step writes to `GITHUB_ENV` is not seen here. Both
    steps that run the file (the check and the scan) are held to this, each
    to its own one command."""
    found = _platform_check_steps(workflow)
    if len(found) != len(PLATFORM_CHECK_COMMANDS):
        return [f"{len(found)} steps run the file, not the check and the scan"]
    job = workflow["jobs"]["build"]
    off = []
    for (_, step, _), command in zip(found, PLATFORM_CHECK_COMMANDS):
        if str(step.get("run", "")).strip() != command:
            off.append(f"the step runs {step.get('run')!r}, not the one command {command!r}")
        if "continue-on-error" in step:
            off.append(f"the step {command!r} has continue-on-error: {step['continue-on-error']!r}")
        if "env" in step:
            off.append(f"the step {command!r} sets env: {step['env']!r}")
        if step.get("shell") not in _SHELLS_THAT_STOP:
            off.append(f"the step {command!r}'s shell {step.get('shell')!r} may not stop on a failure")
    if "continue-on-error" in job:
        off.append(f"its job has continue-on-error: {job['continue-on-error']!r}")
    for where, holder in (("its job", job), ("the workflow", workflow)):
        if "env" in holder:
            off.append(f"{where} sets env: {holder['env']!r}")
    shells = [("its job's default", ((job.get("defaults") or {}).get("run") or {}).get("shell")),
              ("the workflow's default", ((workflow.get("defaults") or {}).get("run") or {}).get("shell"))]
    for where, shell in shells:
        if shell not in _SHELLS_THAT_STOP:
            off.append(f"{where} shell {shell!r} may not stop on a failure")
    return off


def test_both_build_legs_check_their_errno_names_before_building():
    """Two steps of the build job run the file, each its one command: the
    check of this platform's errno names (the file run as a script), then
    the file's tests by pytest, the scan of the names the program reads
    among them; on Windows and on macOS, for a tag push and a manual run
    alike, after the dependencies are installed (both import the engine)
    and before PyInstaller."""
    found = _platform_check_steps()
    assert [argv for _, _, argv in found] == [command.split() for command in PLATFORM_CHECK_COMMANDS], found
    contexts = [PUSH_TAG] + DISPATCHES
    assert len(contexts) == 3, contexts
    assert len(found) == 2, found
    for _, step, _ in found:
        for system in ("Windows", "macOS"):
            for context in contexts:
                step_if = step.get("if")
                assert step_if is None or evaluate(step_if, dict(context, **{"runner.os": system})), \
                    (system, context)
        assert "continue-on-error" not in step, "a failed check must fail the job"
    assert _errno_step_lets_a_failure_pass(_workflow()) == [], "a failed check must fail the job"
    steps = _jobs()["build"]["steps"]
    installs = [n for n, s in enumerate(steps) if any(a[:2] == ["pip", "install"] for a in _commands(s.get("run")))]
    builds = [n for n, s in enumerate(steps) if any(a[:1] == ["pyinstaller"] for a in _commands(s.get("run")))]
    assert installs and builds, (installs, builds)
    check, scan = (at for at, _, _ in found)
    assert max(installs) < check < scan < min(builds), (installs, check, scan, builds)


_ERRNO_STEP = "        run: python tests/test_mac1_platform_names_2026_10_14.py\n"
_SCAN_STEP = "        run: python -m pytest -q -p no:cacheprovider tests/test_mac1_platform_names_2026_10_14.py\n"
_BUILD_JOB = "    runs-on: ${{ matrix.os }}\n"


@pytest.mark.parametrize("anchor, planted", [
    (_ERRNO_STEP, "        run: python tests/test_mac1_platform_names_2026_10_14.py || true\n"),
    (_ERRNO_STEP, "        run: python tests/test_mac1_platform_names_2026_10_14.py || :\n"),
    (_ERRNO_STEP, "        run: python tests/test_mac1_platform_names_2026_10_14.py || exit 0\n"),
    (_ERRNO_STEP, "        run: python tests/test_mac1_platform_names_2026_10_14.py; true\n"),
    (_ERRNO_STEP, "        run: |\n          python tests/test_mac1_platform_names_2026_10_14.py\n          true\n"),
    (_ERRNO_STEP, _ERRNO_STEP + "        continue-on-error: true\n"),
    (_BUILD_JOB, _BUILD_JOB + "    continue-on-error: true\n"),
    (_BUILD_JOB, _BUILD_JOB + "    continue-on-error: ${{ matrix.os == 'macos-latest' }}\n"),
    (_ERRNO_STEP, _ERRNO_STEP + "        shell: bash {0}\n"),
    (_ERRNO_STEP, _ERRNO_STEP + "        shell: cmd\n"),
    (_BUILD_JOB, _BUILD_JOB + "    defaults:\n      run:\n        shell: bash --noprofile --norc {0}\n"),
    ("jobs:\n", "defaults:\n  run:\n    shell: python {0}\n\njobs:\n"),
    (_ERRNO_STEP, _ERRNO_STEP + "        env:\n          PYTHONPATH: tests/fixtures\n"),
    (_ERRNO_STEP, _ERRNO_STEP + "        env: ${{ fromJSON(vars.CHECK_ENV) }}\n"),
    (_ERRNO_STEP, _ERRNO_STEP + "        env: {}\n"),
    (_BUILD_JOB, _BUILD_JOB + "    env:\n      PYTHONSTARTUP: x.py\n"),
    ("jobs:\n", "env:\n  PYTHONPATH: x\n\njobs:\n"),
    (_SCAN_STEP, _SCAN_STEP.replace("\n", " || true\n")),
    (_SCAN_STEP, _SCAN_STEP.replace(" -q ", " -q -k nothing_at_all ")),
    (_SCAN_STEP, _SCAN_STEP + "        continue-on-error: true\n"),
    (_SCAN_STEP, _SCAN_STEP + "        shell: bash {0}\n"),
    (_SCAN_STEP, _SCAN_STEP + "        env:\n          PYTEST_ADDOPTS: --co\n"),
    (_SCAN_STEP, ""),
], ids=["or-true", "or-colon", "or-exit-0", "then-true", "a-second-line", "step-continue", "job-continue",
        "job-continue-expression", "step-shell", "step-cmd", "job-default-shell", "workflow-default-shell",
        "step-env", "step-env-expression", "step-env-empty", "job-env", "workflow-env",
        "scan-or-true", "scan-filtered", "scan-continue", "scan-shell", "scan-env", "scan-removed"])
def test_a_check_step_whose_failure_would_not_fail_the_job_is_caught(anchor, planted):
    """Each form planted in a copy of build.yml's text: the pin above
    refuses it, and refuses nothing in the workflow as it is."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count(anchor) == 1, anchor
    assert _errno_step_lets_a_failure_pass(load_yaml(text)) == []
    assert _errno_step_lets_a_failure_pass(load_yaml(text.replace(anchor, planted))) != [], planted


@pytest.mark.parametrize("planted", ["        env: {PYTHONPATH: x}\n", "        env: {PYTHONPATH: x, A: b}\n"])
def test_an_env_on_the_check_step_in_flow_style_is_refused_by_the_reader(planted):
    """Written in flow style, an `env` is outside the subset the workflow's
    reader takes: reading the workflow fails, so the pin above fails too,
    rather than reading past it."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count(_ERRNO_STEP) == 1
    load_yaml(text)
    with pytest.raises(YamlSubsetError, match="construct outside the subset"):
        load_yaml(text.replace(_ERRNO_STEP, _ERRNO_STEP + planted))


def _run_the_check(tmp_path, stub):
    """The check step's own command, run here with `stub` changing this
    interpreter's errno before the check reads it (a sitecustomize)."""
    (_, _, argv), _ = _platform_check_steps()
    site = tmp_path / "site"
    site.mkdir(parents=True)
    (site / "sitecustomize.py").write_text("import errno\n" + stub, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONSTARTUP", "PYTHONNOUSERSITE")}
    env["PYTHONPATH"] = str(site)
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")
    return subprocess.run([sys.executable, *argv[1:]], cwd=EXECUTABLE_DIR, env=env, capture_output=True,
                          text=True, timeout=300)


def test_the_check_passes_here_and_fails_on_a_name_missing_or_a_cell_wrong(tmp_path):
    clean = _run_the_check(tmp_path / "clean", "")
    assert clean.returncode == 0 and "the engine imports" in clean.stdout, (clean.stdout, clean.stderr[-2000:])
    lacking = _run_the_check(tmp_path / "lacking", "del errno.EDEADLK\n")
    assert lacking.returncode != 0 and "errno has no EDEADLK on this platform" in lacking.stderr, lacking.stderr
    assert "Traceback" not in lacking.stderr, "the check names the name before the engine's import fails on it"
    wrong = _run_the_check(tmp_path / "wrong", "errno.EACCES = 99\n")
    assert wrong.returncode != 0 and "errno.EACCES is 99 on this platform" in wrong.stderr, wrong.stderr
