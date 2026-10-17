"""The Python files the frozen app carries, found as the build finds them.

build.spec is executed, not parsed: PyInstaller is stood in for, so the
`datas` it hands Analysis and the scripts Analysis starts from are whatever
the spec computes, a literal tuple, a comprehension over the list or a name
built at run time alike. To those come the modules source_modules.txt names
(tests/source_list.py) and every module of the repository any of them
imports, at any depth of the code and transitively. Standard library only;
nothing here imports the program.
"""
from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from unittest import mock

import source_list


class _Stub:
    """PYZ, EXE, COLLECT, BUNDLE: called, never built."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return None


def run_spec(root: Path) -> dict:
    """build.spec of tree `root` executed with PyInstaller stood in for: the
    `datas` it hands Analysis, and the scripts each Analysis call starts from
    (its first argument). SystemExit where the spec stops the build."""
    scripts = []

    class _Analysis(_Stub):
        def __init__(self, *args, **kwargs):
            first = args[0] if args else kwargs.get("scripts", [])
            scripts.extend([first] if isinstance(first, str) else list(first))

    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.collect_all = lambda package: ([], [], [])
    hooks.collect_submodules = lambda package: []
    modules = {"PyInstaller": types.ModuleType("PyInstaller"),
               "PyInstaller.utils": types.ModuleType("PyInstaller.utils"),
               "PyInstaller.utils.hooks": hooks}
    space = {"SPECPATH": str(root), "__name__": "__main__", "Analysis": _Analysis, "PYZ": _Stub, "EXE": _Stub,
             "COLLECT": _Stub, "BUNDLE": _Stub}
    spec = Path(root) / "build.spec"
    with mock.patch.dict(sys.modules, modules), mock.patch.object(sys, "path", list(sys.path)):
        exec(compile(spec.read_text(encoding="utf-8"), str(spec), "exec"), space)
    return {"datas": space["datas"], "scripts": scripts}


def spec_datas(root: Path) -> list[tuple]:
    """build.spec executed with PyInstaller stood in for: the `datas` it hands Analysis."""
    return run_spec(root)["datas"]


def repository_module(root: Path, head: str) -> str | None:
    """What `import head` finds in the repository's own folder: `head.py` for a module file,
    `head/` for a folder of Python files (a package, which the list cannot name), else None.

    This is how the repository's modules are told from the standard library's and the
    installed packages': the app runs from the repository's folder, which Python puts first
    on sys.path, so a name the folder holds resolves there (even one the standard library
    also has), and a name it does not hold can only be found elsewhere."""
    if (root / f"{head}.py").is_file():
        return f"{head}.py"
    if (root / head).is_dir() and any((root / head).glob("*.py")):
        return f"{head}/"
    return None


LOADERS = ("__import__", "import_module")


class UnreadableImport(ValueError):
    """A module loaded in a way no reading of the code can name: a loader called
    with a name not written out, or a loader reached by a route this module does
    not follow. The inventory refuses it rather than miss the module."""


def _loader_aliases(tree: ast.AST) -> set[str]:
    """Every name the code binds to an import function: `from importlib import
    import_module [as x]`, `x = importlib.import_module`, `x = __import__`, and a
    name assigned from one of those, to a fixed point."""
    names = set(LOADERS)

    def is_loader(node):
        return (isinstance(node, ast.Name) and node.id in names
                or isinstance(node, ast.Attribute) and node.attr in LOADERS)

    while True:
        before = len(names)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("importlib", "builtins"):
                names.update(a.asname or a.name for a in node.names if a.name in LOADERS)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None \
                    and is_loader(node.value):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.update(t.id for t in targets if isinstance(t, ast.Name))
        if len(names) == before:
            return names


def _holds_a_loader(func: ast.AST, aliases: set[str]) -> bool:
    """Whether a callee that is not a plain name or attribute holds a loader not
    called inside it: `(f := importlib.import_module)`, `(a or load)`. A call
    through such a callee is read as a loader call."""
    if isinstance(func, (ast.Name, ast.Attribute)):
        return False
    called = {id(n.func) for n in ast.walk(func) if isinstance(n, ast.Call)}
    return any((isinstance(n, ast.Name) and n.id in aliases or isinstance(n, ast.Attribute) and n.attr in LOADERS)
               and id(n) not in called for n in ast.walk(func))


def imported_heads(tree: ast.AST) -> list[str]:
    """The top-level name of every import anywhere in the code (module level, inside a
    function, under a condition): `import a.b`, `from a.b import c` (absolute only: the
    repository's folder is no package), and a loader call written with a literal name: a
    call to `importlib.import_module` or `__import__`, to a plain name the code binds to
    either (`load = importlib.import_module`, then `load('x')`), or to an expression that
    holds one (`(f := importlib.import_module)('x')`).
    UnreadableImport for a module it cannot name: a loader called with anything but a
    literal; a loader used other than as the callee of a call or the value bound to a
    plain name (passed on, held in a container); a loader bound by a walrus that is not
    itself the callee, a whole expression statement or a whole `if`, `while` or `assert`
    test (`map(f := importlib.import_module, ...)`); a loader's name written out as a
    string (`getattr(importlib, 'import_module')`); `runpy`; `importlib.util`'s loading
    from a file. Neither read nor refused: a loader looked up by a name built at run
    time, and code run from a string (`exec`)."""
    aliases = _loader_aliases(tree)
    calls = set()
    heads = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            heads += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            heads.append(node.module)
        if isinstance(node, ast.Call) and (isinstance(node.func, ast.Name) and node.func.id in aliases
                                           or isinstance(node.func, ast.Attribute) and node.func.attr in LOADERS
                                           or _holds_a_loader(node.func, aliases)):
            calls.add(id(node.func))
            if not (node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                raise UnreadableImport(f"line {node.lineno}: a module loaded by a name not written out")
            heads.append(node.args[0].value)
    bindings = {id(t) for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
                for t in ([node.target] if not isinstance(node, ast.Assign) else node.targets)}
    for node in ast.walk(tree):
        loader = (isinstance(node, ast.Name) and node.id in aliases
                  or isinstance(node, ast.Attribute) and node.attr in LOADERS)
        if loader and id(node) not in calls and id(node) not in bindings and not _binds_a_loader(node, tree):
            raise UnreadableImport(f"line {node.lineno}: an import function reached other than by a call")
        if (isinstance(node, ast.Constant) and node.value in LOADERS + ("run_path", "run_module",
                                                                         "spec_from_file_location")
                or isinstance(node, ast.Attribute) and node.attr in ("run_path", "run_module",
                                                                     "spec_from_file_location")
                or isinstance(node, (ast.Import, ast.ImportFrom)) and any(
                    a.name in ("runpy", "run_path", "run_module", "spec_from_file_location")
                    or (getattr(node, "module", None) or "") == "runpy" for a in node.names)):
            raise UnreadableImport(f"line {node.lineno}: a module loaded by a route the inventory does not follow")
    return [h.split(".")[0] for h in heads]


def _binds_a_loader(node: ast.AST, tree: ast.AST) -> bool:
    """Whether `node` is the value of an assignment that binds a loader to a name
    (`x = importlib.import_module`): a binding _loader_aliases follows. A walrus
    (`f := importlib.import_module`) also hands its value on, so it counts only where
    that value goes nowhere unread: as the callee of a call, a whole expression
    statement, or a whole `if`, `while` or `assert` test."""
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and parent.value is node:
            targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            if isinstance(parent, ast.NamedExpr) and not any(
                    isinstance(n, ast.Call) and n.func is parent
                    or isinstance(n, ast.Expr) and n.value is parent
                    or isinstance(n, (ast.If, ast.While, ast.Assert)) and n.test is parent for n in ast.walk(tree)):
                return False
            return all(isinstance(t, ast.Name) for t in targets)
    return False


def program_modules(root: Path, start: list[str] | None = None) -> list[str]:
    """Every module in `start` (the listed modules when not given), and every module of the
    tree one of them imports, at any depth of the code and transitively (engine.py's
    glyph_font.py): what the frozen app needs beside its script. A package folder is named
    (`name/`) but not walked into."""
    need, todo = [], list(source_list.names(root) if start is None else start)
    while todo:
        name = todo.pop(0)
        if name in need:
            continue
        need.append(name)
        if name.endswith("/"):
            continue
        heads = imported_heads(ast.parse((root / name).read_text(encoding="utf-8")))
        todo += [m for m in (repository_module(root, h) for h in heads) if m]
    return need


def shipped_modules(root: Path) -> list[str]:
    """The Python files of tree `root` the frozen app carries: the scripts Analysis starts
    from and every `.py` the spec puts beside them (destination "."), from build.spec
    executed; the modules source_modules.txt names; and every module of the tree any of
    those imports, transitively. A package folder is named `name/`."""
    built = run_spec(root)
    start = list(built["scripts"])
    start += [src for src, dest, *_ in built["datas"] if dest == "." and str(src).endswith(".py")]
    start += source_list.names(root)
    return sorted(program_modules(root, list(dict.fromkeys(start))))
