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
import tempfile
import types
from pathlib import Path
from unittest import mock

import name_bindings
import source_list


class _Stub:
    """PYZ, EXE, COLLECT, BUNDLE: called, never built."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return None


# The build's work folder when a run names none: one for the test process.
_WORKPATH = tempfile.TemporaryDirectory(prefix="zij-spec-")


def run_spec(root: Path, toc: dict | None = None, workpath: Path | None = None) -> dict:
    """build.spec of tree `root` executed with PyInstaller stood in for: the
    `datas` it hands Analysis, the scripts each Analysis call starts from
    (its first argument), and "toc_datas", the analysis's files once the spec
    has added its own. `toc` holds what the stood-in analysis found ("pure",
    "binaries", "datas"; nothing when not given), and `workpath` is the
    build's work folder. SystemExit where the spec stops the build."""
    scripts = []
    toc = toc or {}

    class _Analysis(_Stub):
        def __init__(self, *args, **kwargs):
            first = args[0] if args else kwargs.get("scripts", [])
            scripts.extend([first] if isinstance(first, str) else list(first))
            self.pure, self.binaries, self.datas = (list(toc.get(key, ())) for key in ("pure", "binaries", "datas"))

    hooks = types.ModuleType("PyInstaller.utils.hooks")
    hooks.collect_all = lambda package: ([], [], [])
    hooks.collect_submodules = lambda package: []
    modules = {"PyInstaller": types.ModuleType("PyInstaller"),
               "PyInstaller.utils": types.ModuleType("PyInstaller.utils"),
               "PyInstaller.utils.hooks": hooks}
    space = {"SPECPATH": str(root), "workpath": str(workpath or _WORKPATH.name), "__name__": "__main__",
             "Analysis": _Analysis, "PYZ": _Stub, "EXE": _Stub, "COLLECT": _Stub, "BUNDLE": _Stub}
    spec = Path(root) / "build.spec"
    with mock.patch.dict(sys.modules, modules), mock.patch.object(sys, "path", list(sys.path)):
        exec(compile(spec.read_text(encoding="utf-8"), str(spec), "exec"), space)
    return {"datas": space["datas"], "scripts": scripts, "toc_datas": space["a"].datas}


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


# Routes to a module this module does not follow, refused wherever they are named: as a
# name, an attribute, an import or a string.
ROUTES = ("machinery", "SourceFileLoader", "SourcelessFileLoader", "ExtensionFileLoader", "find_spec",
          "load_module", "exec_module", "module_from_spec", "spec_from_loader", "meta_path")
RUN_FROM_TEXT = ("exec", "eval", "compile")
IMPORT_MODULES = ("importlib", "builtins")
# What of builtins the code may import by name: anything but code run from a string and its dunders
# (__import__ excepted: a loader, read as one).
_BUILTINS_REFUSED = RUN_FROM_TEXT + ("__dict__", "__builtins__", "__loader__", "__spec__")


def _allowed(path: str) -> bool:
    """Whether a settled path of the import machinery is on the allowlist:
    `importlib.import_module`, and a builtin by its name (not exec, eval or
    compile, nor builtins' namespace or another of its dunders); the two modules
    themselves pass here and are judged by where they stand."""
    path = name_bindings.original(path)
    parts = path.split(".")
    if path in IMPORT_MODULES:
        return True                       # the module itself: _refuse_unfollowed asks where it stands
    if parts[0] == "importlib":
        return path == "importlib.import_module"
    if parts[0] == "builtins":
        return len(parts) >= 2 and parts[1] not in _BUILTINS_REFUSED
    return True


def _refuse_unfollowed(tree: ast.AST, bindings: name_bindings.Bindings) -> None:
    """UnreadableImport for any use of the import machinery outside an allowlist,
    and for code run from a string and every ROUTES name.

    What each expression stands for is asked of the shared resolver
    (tests/name_bindings.py), through the bindings it lists: so importlib and
    builtins under a name one of those binds, as another module's attribute
    (`reprlib.builtins`), imported from another module (`from pkgutil import
    importlib`), fetched by a written name (`getattr(json, '__builtins__')`,
    `sys.modules['builtins']`) or copied, are each the module itself. A bare
    `exec`, `eval` or `compile` is refused wherever it is written, whatever binds
    the name (read `re.compile` through its module).
    The allowlist: importlib only as the base of `.import_module` (called or bound,
    as imported_heads reads it); builtins only as the base of a builtin's name, and
    a builtin by its own name, but exec, eval and compile, builtins' namespace and its
    other dunders (`__import__` excepted: a loader, read as one). Refused, with its
    line, is every other appearance: importlib or builtins handed on, bound again,
    looked into (`vars(importlib)`, `reprlib.builtins.__dict__`), any other attribute
    of importlib (`importlib.util`, `importlib.reload`), builtins' namespace
    (`__builtins__`, `json.__builtins__`, `vars(builtins)`); `__builtins__`,
    `builtins` and `importlib` as an attribute of anything, the resolver able to
    settle it or not; a submodule of either imported (`import importlib.util`,
    `from importlib.machinery import ...`), and from either anything off the
    allowlist; and the strings "__builtins__", "importlib", "importlib.*" and
    "builtins"."""
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] in IMPORT_MODULES and "." in a.name
                                                for a in node.names):
            raise UnreadableImport(f"line {line}: a submodule of the import machinery imported")
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in IMPORT_MODULES \
                and not all(node.module in IMPORT_MODULES and _allowed(f"{node.module}.{a.name}") for a in node.names):
            raise UnreadableImport(f"line {line}: the import machinery imported other than by the allowlist")
    parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def off_the_allowlist(node):
        settled = {p for p in bindings.paths(node) if not name_bindings.opaque(p)}
        if not all(_allowed(p) for p in settled):
            return True
        if settled & set(IMPORT_MODULES):                    # the module itself: only as an allowed attribute's base
            parent = parents.get(id(node))
            return not (isinstance(parent, ast.Attribute) and parent.value is node
                        and all(_allowed(p) for p in bindings.paths(parent) if not name_bindings.opaque(p)))
        return False

    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.expr) and not isinstance(getattr(node, "ctx", None), (ast.Store, ast.Del)) \
                and off_the_allowlist(node) \
                or isinstance(node, ast.Name) and node.id == "__builtins__" \
                or isinstance(node, ast.Attribute) and node.attr in ("__builtins__",) + IMPORT_MODULES \
                or isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and (node.value in ("__builtins__", "builtins", "importlib") or node.value.startswith("importlib.")):
            raise UnreadableImport(f"line {line}: the import machinery used other than by the allowlist")
        if isinstance(node, ast.Name) and node.id in RUN_FROM_TEXT:
            raise UnreadableImport(f"line {line}: code run from a string, whose imports no reading can name")
        if isinstance(node, ast.Name) and node.id in ROUTES or isinstance(node, ast.Attribute) and node.attr in ROUTES \
                or isinstance(node, ast.Constant) and node.value in ROUTES \
                or isinstance(node, ast.Import) and any(set(a.name.split(".")) & set(ROUTES) for a in node.names) \
                or isinstance(node, ast.ImportFrom) and (set((node.module or "").split(".")) & set(ROUTES)
                                                         or any(a.name in ROUTES for a in node.names)):
            raise UnreadableImport(f"line {line}: a module loaded by a route the inventory does not follow")


def _loader_aliases(tree: ast.AST, bindings: name_bindings.Bindings) -> set[str]:
    """Every name the code binds to an import function, as the shared resolver
    settles it: `from importlib import import_module [as x]`, `x =
    importlib.import_module`, `x = __import__`, a name assigned from one of those,
    unpacked, a parameter's default."""
    return set(LOADERS) | {name for name, paths in bindings.env.items()
                           if paths & set(name_bindings.LOADER_PATHS)}


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
    either by a binding the shared resolver of tests/name_bindings.py lists (`load =
    importlib.import_module`, then `load('x')`; unpacking; a parameter's default), or to an
    expression that holds one (`(f := importlib.import_module)('x')`).
    UnreadableImport for a module it cannot name: a loader called with anything but a
    literal; a loader used other than as the callee of a call or the value bound to a
    plain name (passed on, held in a container); a loader bound by a walrus that is not
    itself the callee, a whole expression statement or a whole `if`, `while` or `assert`
    test (`map(f := importlib.import_module, ...)`); a loader's name written out as a
    string (`getattr(importlib, 'import_module')`); `runpy`; a bare `exec`, `eval` or
    `compile`, wherever it is written, whatever binds the name (read `re.compile`
    through its module); every use of `importlib.machinery`, the file loaders, `find_spec`,
    `load_module`, `exec_module`, `module_from_spec`, `spec_from_loader` and
    `sys.meta_path` (ROUTES), by name, attribute, import or string; and any use of the
    import machinery outside the allowlist _refuse_unfollowed gives (`import
    importlib` with `importlib.import_module`, builtins by a written attribute,
    `__import__`): `__builtins__` anywhere, importlib or builtins handed on or looked
    into, another attribute or submodule of importlib, the strings that name them.
    Neither read nor refused: the machinery reached by a name never written out
    (`getattr(json, name)`, `globals()[name]`, `vars(json)[name]`), which no reading
    tells from the ordinary lookups the program makes; the machinery or a loader bound
    by a form the resolver does not list: a star import (`from site import *`, then
    `vars(builtins)[name]`; `from modulefinder import *`, then `importlib.reload`), a
    match pattern (`case object(importlib=I)`, then `I.__dict__[name]`), a class
    attribute (`class K: load = importlib.import_module`, then `K.load(name)`); code run
    from a string through a builtin reached as another builtin's attribute
    (`print.__self__.exec(...)`); and a module loaded through another library, among it
    `pkgutil.resolve_name`, `pydoc.locate`, `pickle` loading a global,
    `code.InteractiveInterpreter().runsource`, a `mock.patch` target in program code,
    `zipimport`, `sys.path_hooks` and a C library.
    At run time the import audit (tests/import_audit.py, a fresh interpreter with an
    audit hook installed before the program's first import) sees each of these where it
    runs: a module of the tree loaded by any route must be one this inventory names, and
    exec, eval or compile called from a file the frozen app carries is refused (a library
    that runs code on the program's behalf makes the call itself; only the modules it
    loads are checked). Each form above is planted for it but three it has not been tried on:
    `zipimport`, `sys.path_hooks` and a C library; and `importlib.reload`, which loads
    no module the run had not loaded, so the audit has nothing there to refuse. On a
    path the audit does not run they all remain limits of this reading."""
    bindings = name_bindings.Bindings(tree)
    _refuse_unfollowed(tree, bindings)
    aliases = _loader_aliases(tree, bindings)
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
