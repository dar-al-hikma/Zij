"""The census of engine replacements, by `ast`, in test code and in the scripts
tests hand to a subprocess (tests/test_split_astro_2026_10_14.py, the guard of
every module split out of engine.py, uses it).

A site is a place that replaces an attribute of the engine module, or an item
of the `engine` fixture's namespace: monkeypatch.setattr / setitem / delattr,
setattr / delattr, mock.patch.object, mock.patch("engine.X"), assignment to or
deletion of `R.X` or `R["X"]`, and mock.patch.dict(R, ...) or R.update(...),
R being the engine (vars() or __dict__ of it among them). A site's name is the
name it replaces where the site writes it; "<dynamic>" where it does not (a
variable; a mapping that is not written out; patch.dict's clear=True, which
touches every name). pytest's string form, monkeypatch.setattr("engine.X",
value) and monkeypatch.delattr("engine.X") (no name beside the target), is
read as mock.patch("engine.X") is, and mock.patch.multiple(R or "engine",
X=...) replaces each name it is given. R is the engine
where it is a name the file binds to it -- `import engine [as R]`, the module
from importlib.import_module("engine") (or __import__, under any name the file
binds either to), sys.modules["engine"],
importlib.reload of it, vars() or __dict__ of it, a local function that
returns it -- or one of the names the suite gives it by convention
(ENGINE_NAMES: the fixture's `engine` among them); or any expression, a bare
name among them, that the shared resolver settles as the engine, a module's
attribute named for it or the engine's namespace (`app.engine`, `getattr(app,
"engine")`, `S = sys.modules; S["engine"]`, `E, n = sys.modules["engine"], 1`,
`for E in (app.engine,)`).

What every name and expression stands for, beyond the engine's own reading,
is asked of one resolver shared with the shipped-module inventory and the
errno scan (tests/name_bindings.py): through the bindings it lists, to a
fixed point over the file. Here and below, "under any name" means under a name
one of those bindings binds. So sys.modules is sys.modules under any name or
copied (`S = sys.modules`, `from sys import modules`, `dict(sys.modules)`, `m =
sys; m.modules`), importlib and builtins are themselves as another module's
attribute or imported from one, a loader is a loader under any name, and a
member of the patch family is that member under any name (`from unittest.mock
import patch as p`, `p = getattr(mock, "patch")`, `(p := mock.patch)(...)`, `s =
monkeypatch.setattr`, a parameter's default).

A module the census cannot name is a site of its own, "<dynamic module>".
Loads: a call to import_module or __import__ or a `.get` on sys.modules (each
under any name) whose module is given and is not a string literal; a subscript
of sys.modules (under any name, or a copy) whose key is neither a string
literal nor `__name__` (the file's own module); and a loader reached by getattr
(`getattr(importlib, "import_module")`, getattr under any name), or by a
subscript or `.get(...)` on the namespace of importlib or builtins (vars(),
__dict__, `__builtins__`, under any name) whose key is not written out, whether
it is called there or bound to a name. A loader reached by a written name
(`getattr(importlib, "import_module")("engine")`) is read as the load it is.
Patches, by one rule (family_target, resolved): every call of the patch
family -- mock.patch and any attribute of it called with a target
(patch.object, patch.dict, patch.multiple), and setattr, delattr, setitem and
delitem (monkeypatch's methods, the builtins, operator's), each also through any
name or expression the resolver settles as it -- whose target the census cannot
name: a target that can only be a dotted string (patch itself, pytest's
string form) and is not a string literal; any other target that is neither a
string literal nor the engine nor an attribute or item, at any depth, of the
engine, of a module the file imports or of a module loaded by name (a
computed string, an f-string, a call, a bare variable); a target fetched by a
name not written out (computed_lookup: a getattr, under any name, whose name
is not a literal, or getattr handed on, `functools.reduce(getattr, ...)`;
`operator.attrgetter` given a name not written out; a key not written out on
vars(), a __dict__ or sys.modules, each under any name; sys.modules copied or
iterated), whether inline or through a name the file binds from such a lookup
by any binding the resolver follows, or from a name so bound (`R = getattr(t,
name)`, `S = sys.modules; R = S[name]`, `Q = R`, a parameter's default `R=getattr(t,
name)`, then `monkeypatch.setattr(R, "X", value)`); and arguments unpacked (`*args`,
`**kwargs`). The one member the rule leaves unread: the object form of
setattr, delattr, setitem and delitem given any other bare variable (or
attributes on one) the census does not resolve (`monkeypatch.setattr(module,
"X", value)`, `module` a helper's or fixture's return): the suite's own tests
patch many such names, and a row for each would mark them all.
Not read: what the resolver cannot settle, a name never written out
(`getattr(mod, name)` for a loader, `globals()[name]`) or a parameter without a
default; a loader reached through importlib's or builtins' namespace handed to
a call (`dict.get(vars(importlib), name)`, `operator.itemgetter(name)(
__builtins__)`); and a patching function handed in as a parameter without a
default or wrapped (`functools.partial(monkeypatch.setattr, ...)`), whose calls
are not read at all; a name bound by a form the resolver does not list: a star
import (`from sys import *`, then `modules[name]`), a match pattern (`case
object(modules=S)`, `match getattr(t, name): case R`, `match mock.patch: case
p`), a starred name in unpacking (`p, *_ = mock.patch, 1`), a class attribute
or a dict written out holding a patcher (`class K: p = mock.patch`, then
`K.p(...)`; `{"k": mock.patch}["k"](...)`), a value given by keyword
(`contextlib.nullcontext(enter_result=mock.patch)`); a target fetched by a
method the census does not read (`t.__getattribute__(name)`,
`operator.getitem(vars(t), name)`, `vars(t).setdefault(name)`,
`inspect.getattr_static(t, name)`, `collections.ChainMap(vars(t))[name]`); and
a writing view of the engine's namespace
(`collections.ChainMap(vars(engine))["swe"] = None`). What such a site loads
may be the engine, and nothing tells what is replaced through it. At run time
each of these forms is seen where it replaces an attribute of the engine in a
test the suite runs in its own process: the tripwire in tests/conftest.py
watches the engine's namespace, applies the split guard's rule to what it
sees, and names by its line every replacement this census has no row for
(each form above is planted for it), but a decorator's patch, which has no
line: that is named by its file alone, and any row of its name in the test's
function counts as its row. They remain limits of this reading in a script
handed to a subprocess, in a test that does not run, on an engine imported
afresh within a test (watched only from the next test's start), and in a
change made from a frame of a program file (code compiled under its name, or a
writer a test hands to a program function), taken for the program's own.
A function that only
hands its parameter on to a loader (`def _tool(name): return
importlib.import_module(name)`) is a loader itself: each call of it is read,
and the call inside it is not a site.

Each name is resolved in its own scope: a name a function binds to something
else (by an import, an assignment to a single name or a definition) is not
the engine there, whatever the file binds it to elsewhere; a name the scope
does not so bind is the engine where the shared resolver settles it as the
engine through any binding in the file it lists (unpacking, a `for`, a `with`,
a walrus, a parameter's default), which can only find more sites; and a name
the scope so binds while the resolver settles it as the engine elsewhere is
not resolved by being settled (resolved). A test's
parameter named for a fixture that returns the engine is the engine, and so is
the element of a tuple a fixture or helper returns the engine in, once
unpacked (`module, chart = chart`).

Scripts: every string constant of a test file (an f-string with each
placeholder written as a name) that reads as engine code -- it says `import
engine`, or runs to more than one line and says `engine.` or `engine[` -- is
read as Python: as it stands, dedented
(a fragment of a function's body, its `return` included, parses so); else as a
str.format template with each field written as a name. A string neither
reads is grepped instead, by the regular expressions below; the census says
which was done for each string (METHODS). Standard library only.
"""
from __future__ import annotations

import ast
import re
import string
import textwrap
from pathlib import Path

import name_bindings

ENGINE_NAMES = frozenset({"engine", "engine_module", "E", "_engine", "eng"})
# The names each module split out of engine.py rebinds as it runs, which the
# engine does not re-export: read in their
# module, never through the engine, where they would hold the value they had
# at the engine's import. WITHHELD is all of them, in this order.
WITHHELD_BY_MODULE = {
    "ephemeris.py": ("_EPHEMERIS_FOLDER", "_DELTA_T_REFERENCE"),
    "time_zones.py": (),
    "user_data.py": ("DATA_DIR_ERROR", "LAST_STORE_ERROR", "LAST_STORE_UNREADABLE", "LAST_PREFERENCES_ERROR",
                     "LAST_PREFERENCES_UNREADABLE", "LAST_PREFERENCES_BUSY"),
    "markup.py": (),
    "wheel.py": (),
    "export_html.py": (),
}
WITHHELD = tuple(name for names in WITHHELD_BY_MODULE.values() for name in names)
_CODE = re.compile(r"\bimport engine\b|\bengine\s*[.\[]")
_ENGINE_RX = "|".join(sorted(ENGINE_NAMES))
GREP_SITES = (
    re.compile(rf"\b(?:{_ENGINE_RX})\s*\.\s*(\w+)\s*(?:[-+*/]?=)(?!=)"),
    re.compile(rf"\bsetattr\(\s*(?:{_ENGINE_RX})\s*,\s*[\"'](\w+)[\"']"),
    re.compile(rf"\b(?:{_ENGINE_RX})\s*\[\s*[\"'](\w+)[\"']\s*\]\s*=(?!=)"),
)
GREP_REBOUND = (
    re.compile(rf"\b(?:{_ENGINE_RX})\s*\.\s*({'|'.join(WITHHELD)})\b"),
    re.compile(rf"\b(?:{_ENGINE_RX})\s*\[\s*[\"']({'|'.join(WITHHELD)})[\"']"),
    re.compile(rf"\b(?:get|set|has|del)attr\(\s*(?:{_ENGINE_RX})\s*,\s*[\"']({'|'.join(WITHHELD)})[\"']"),
)


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _const(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


_CURRENT = [None]        # the shared resolver of the file being read (scopes() sets it; sites() and rebound() too)


def _paths(node):
    """What the shared resolver (tests/name_bindings.py) says `node` stands for;
    opaque paths with their mark taken off."""
    bindings = _CURRENT[0]
    return {p.lstrip("?") for p in bindings.paths(node)} if bindings is not None else set()


def _settled(node):
    bindings = _CURRENT[0]
    return {p for p in bindings.paths(node) if not name_bindings.opaque(p)} if bindings is not None else set()


def _bind(tree):
    if getattr(tree, "census_bindings", None) is None:
        tree.census_bindings = name_bindings.Bindings(tree)
    _CURRENT[0] = tree.census_bindings


def _settled_engine(node):
    """Whether the shared resolver settles `node` as the engine, a module's
    attribute named for it, or the engine's namespace (one of its paths, so a
    name bound to the engine anywhere in the file by any binding it follows)."""
    return any(p == "engine" or p.endswith(".engine") or p == "engine.__dict__" for p in _settled(node))


def is_engine(node, names, returning=frozenset()):
    """Whether `node` evaluates to the engine module or its namespace. Beside the
    forms below, any expression the shared resolver settles as the engine, a
    module's attribute named for it or the engine's namespace (`S = sys.modules;
    S["engine"]`, `app.engine`, `getattr(app, "engine")`). A bare name is resolved
    by scope (`names`), and is the engine too where the resolver settles it so and
    the scope does not bind it to something else by a form the scope reading
    follows (`names.rebinds`): so through unpacking, a `for`, a `with` (`E, n =
    sys.modules["engine"], 1`, `for E in (app.engine,)`, `with
    contextlib.nullcontext(engine) as E`), a walrus or a parameter's default."""
    if isinstance(node, ast.Name):
        return node.id in names or node.id not in getattr(names, "rebinds", ()) and _settled_engine(node)
    if _settled_engine(node):
        return True
    if isinstance(node, ast.Subscript):
        return _dotted(node.value) == "sys.modules" and _const(node.slice) == "engine"
    if isinstance(node, ast.Attribute) and node.attr == "__dict__":
        return is_engine(node.value, names, returning)
    if isinstance(node, ast.Call):
        func = _dotted(node.func)
        last = func.split(".")[-1]
        if last in ("import_module", "__import__") and node.args and _const(node.args[0]) == "engine":
            return True
        if func == "sys.modules.get" and node.args and _const(node.args[0]) == "engine":
            return True
        if last in ("reload", "vars") and node.args and is_engine(node.args[0], names, returning):
            return True
        return isinstance(node.func, ast.Name) and node.func.id in returning
    return False


def _direct(nodes):
    """Every node under `nodes`, not entering the body of a nested function
    or class (its decorators, defaults and bases are entered)."""
    stack = list(nodes)[::-1]
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            children = list(node.decorator_list)
            if isinstance(node, ast.ClassDef):
                children += node.bases + [k.value for k in node.keywords]
            else:
                children += node.args.defaults + [d for d in node.args.kw_defaults if d is not None]
            stack.extend(children[::-1])
            continue
        stack.extend(list(ast.iter_child_nodes(node))[::-1])


def _targets(target):
    """The names a binding target binds (not an attribute's or an item's base)."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_targets(t) for t in target.elts)) if target.elts else set()
    if isinstance(target, ast.Starred):
        return _targets(target.value)
    return set()


def _params(node):
    args = node.args
    return {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}


def _unpacked(value, params, tuples):
    """The indices of the engine in a tuple `value` evaluates to: a call to a
    function returning such a tuple, or a parameter a fixture of that name
    fills (pytest hands a test the fixture's return value by its name)."""
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        return tuples.get(value.func.id, frozenset())
    if isinstance(value, ast.Name) and value.id in params:
        return tuples.get(value.id, frozenset())
    return frozenset()


class _Scope(frozenset):
    """The engine names of one scope, with `rebinds`: the names the scope binds
    to something else by a form _names follows (an import of another module, an
    assignment to a single name, a definition)."""
    rebinds = frozenset()


def _names(nodes, inherited, returning, params, tuples=None):
    """The names bound to the engine in one scope (`nodes`, its own nodes):
    inherited ones it does not rebind to something else, its own `import
    engine`, its parameters of the conventional names (the fixture) or named
    for a fixture that returns the engine, what it assigns from the engine,
    and what it unpacks from a tuple holding the engine (`module, chart =
    chart`, a fixture returning both)."""
    tuples = tuples or {}
    base = set(inherited) | (params & ENGINE_NAMES) | (params & set(returning))
    current = frozenset(base)
    plain = set()
    for _ in range(4):
        engine_bound, other_bound, plain = set(), set(), set()
        for node in nodes:
            if isinstance(node, ast.Import):
                for a in node.names:
                    (engine_bound if a.name == "engine" else other_bound).add(a.asname or a.name.split(".")[0])
                    plain.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                other_bound |= {a.asname or a.name for a in node.names}
                plain |= {a.asname or a.name for a in node.names}
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                here = set().union(*(_targets(t) for t in targets))
                indices = _unpacked(node.value, params, tuples)
                if indices and len(targets) == 1 and isinstance(targets[0], (ast.Tuple, ast.List)):
                    for i, elt in enumerate(targets[0].elts):
                        (engine_bound if i in indices else other_bound).update(_targets(elt))
                    continue
                (engine_bound if is_engine(node.value, current, returning) else other_bound).update(here)
                plain.update(t.id for t in targets if isinstance(t, ast.Name))
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                other_bound |= _targets(node.target)
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                other_bound |= _targets(node.optional_vars)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                other_bound.add(node.name)
                plain.add(node.name)
        new = frozenset((base - (other_bound - engine_bound)) | engine_bound)
        if new == current:
            break
        current = new
    scope = _Scope(current)
    scope.rebinds = frozenset(plain - engine_bound)
    return scope


_LOADERS = ("import_module", "__import__")


def _name_the_loaders(tree):
    """Every call through a name the file binds to an import function (`from
    importlib import import_module as load`, `load = importlib.import_module`,
    `load = __import__`, a name assigned from one of those) is rewritten in
    place as a call to `import_module`, so is_engine reads `load("engine")` as
    it reads `importlib.import_module("engine")`; so is a call through an
    expression that holds one (`(f := importlib.import_module)("engine")`).
    Over the whole file: a name bound to a loader anywhere is a loader
    everywhere, which can only find more sites, never fewer."""
    names = set(_LOADERS) | {name for name, paths in tree.census_bindings.env.items()
                             if paths & set(name_bindings.LOADER_PATHS)}

    def is_loader(node):
        return (isinstance(node, ast.Name) and node.id in names
                or isinstance(node, ast.Attribute) and node.attr in _LOADERS
                or isinstance(node, ast.expr) and bool(_settled(node) & set(name_bindings.LOADER_PATHS)))

    while True:
        before = len(names)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("importlib", "builtins"):
                names.update(a.asname or a.name for a in node.names if a.name in _LOADERS)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None \
                    and is_loader(node.value):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.update(t.id for t in targets if isinstance(t, ast.Name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # `def _tool(name): ... return importlib.import_module(name)`: a loader too
                params = {a.arg for a in node.args.posonlyargs + node.args.args}
                for ret in ast.walk(node):
                    if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Call) and is_loader(ret.value.func) \
                            and ret.value.args and isinstance(ret.value.args[0], ast.Name) \
                            and ret.value.args[0].id in params:
                        names.add(node.name)
                        ret.value.census_forwards = True       # read at each call of the function instead
        if len(names) == before:
            break

    def holds_a_loader(func):          # `(f := importlib.import_module)`: a loader not called inside it
        if isinstance(func, (ast.Name, ast.Attribute)):
            return False
        called = {id(n.func) for n in ast.walk(func) if isinstance(n, ast.Call)}
        return any(is_loader(n) and id(n) not in called for n in ast.walk(func))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (isinstance(node.func, ast.Name) and node.func.id in names - set(_LOADERS)
                                           or holds_a_loader(node.func)
                                           or not (isinstance(node.func, (ast.Name, ast.Attribute))
                                                   and _dotted(node.func).split(".")[-1] in _LOADERS)
                                           and _settled(node.func) & set(name_bindings.LOADER_PATHS)):
            node.func = ast.copy_location(ast.Name(id="import_module", ctx=ast.Load()), node.func)


def scopes(tree):
    """[(the scope's own nodes, its engine names, the functions it sees that
    return the engine)] for the module and every function and class body.
    The file's names are first settled by the shared resolver, and calls
    through another name for an import function are named (_name_the_loaders)."""
    _bind(tree)
    _name_the_loaders(tree)
    out, cache = [], {}

    def own(body):
        if id(body) not in cache:
            cache[id(body)] = list(_direct(body))
        return cache[id(body)]

    def returns(fn, names, returning, tuples):
        """(whether `fn` returns the engine, the indices of the engine in a
        tuple it returns)."""
        if isinstance(fn, ast.ClassDef):
            return False, frozenset()
        nodes = own(fn.body)
        results = [r.value for r in nodes if isinstance(r, ast.Return) and r.value is not None]
        if not results:
            return False, frozenset()
        candidates = names | ENGINE_NAMES | returning | set(tuples)
        if not any((isinstance(n, ast.Name) and n.id in candidates) or _const(n) == "engine"
                   or (isinstance(n, ast.Import) and any(a.name == "engine" for a in n.names)) for n in nodes):
            return False, frozenset()
        inner = _names(nodes, names, returning, _params(fn), tuples)
        whole = any(is_engine(v, inner, returning) for v in results)
        indices = set()
        for v in results:
            if isinstance(v, ast.Tuple):
                indices |= {i for i, elt in enumerate(v.elts) if is_engine(elt, inner, returning)}
            else:
                indices |= _unpacked(v, set(), tuples)
        return whole, frozenset(indices)

    def visit(body, inherited, inherited_returning, inherited_tuples, params):
        nodes = own(body)
        nested = [n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        returning, tuples = set(inherited_returning), dict(inherited_tuples)
        current = _names(nodes, inherited, frozenset(returning), params, tuples)
        for _ in range(3):
            changed = False
            for fn in nested:
                whole, indices = returns(fn, current, frozenset(returning), tuples)
                if whole and fn.name not in returning:
                    returning.add(fn.name)
                    changed = True
                if indices and tuples.get(fn.name) != indices:
                    tuples[fn.name] = indices
                    changed = True
            if not changed:
                break
            current = _names(nodes, inherited, frozenset(returning), params, tuples)
        out.append((nodes, current, frozenset(returning)))
        for fn in nested:
            visit(fn.body, current, returning, tuples, set() if isinstance(fn, ast.ClassDef) else _params(fn))

    visit(tree.body, ENGINE_NAMES, frozenset(), {}, set())
    return out


def _mapping_names(mapping, keywords):
    """The names a mapping argument and keyword arguments write: each key of
    a dict written out with constant keys, each keyword; "<dynamic>" for
    anything else (a mapping held in a variable, ** of one, clear=True)."""
    names = []
    if mapping is not None:
        if isinstance(mapping, ast.Dict) and all(_const(k) for k in mapping.keys):
            names += [_const(k) for k in mapping.keys]
        else:
            names.append("<dynamic>")
    for keyword in keywords:
        if keyword.arg is None or keyword.arg == "clear":
            if keyword.arg is None or not (isinstance(keyword.value, ast.Constant) and not keyword.value.value):
                names.append("<dynamic>")
        else:
            names.append(keyword.arg)
    return names or ["<dynamic>"]


DYNAMIC_MODULE = "<dynamic module>"
_IMPORT_MODULES = ("importlib", "builtins", "__builtins__")


def _on_an_import_module(node):
    """Whether `node` is importlib, a module of it or builtins: by its own name, or
    as the shared resolver settles it (`from pkgutil import importlib as I`)."""
    return _dotted(node).split(".")[0] in _IMPORT_MODULES or any(
        p.split(".")[0] in ("importlib", "builtins") and not name_bindings.original(p).endswith(".__dict__")
        for p in _settled(node))


def _namespace(node):
    """Whether `node` is the namespace of importlib, a module of it or builtins:
    vars() or __dict__ of one, or `__builtins__` (a dict outside the main module),
    under any name the shared resolver settles."""
    return (isinstance(node, ast.Call) and _dotted(node.func) == "vars" and node.args
            and _on_an_import_module(node.args[0])
            or isinstance(node, ast.Attribute) and node.attr == "__dict__" and _on_an_import_module(node.value)
            or isinstance(node, ast.Name) and node.id == "__builtins__"
            or any(p.split(".")[0] in ("importlib", "builtins") and name_bindings.original(p).endswith(".__dict__")
                   for p in _settled(node)))


def _member(path):
    """Whether a dotted path names a member of the patch family."""
    parts = path.split(".")
    return parts[-1] == "patch" or parts[-2:-1] == ["patch"] or parts[-1] in _MONKEYPATCH


def callee(node):
    """The dotted name a call's callee is read as: as written, where that names a
    member of the patch family; else the member the shared resolver says it stands
    for (`from unittest.mock import patch as p`, `p = getattr(mock, "patch")`,
    `(p := mock.patch)(...)`, `s = monkeypatch.setattr`); else as written; a method
    on anything not a dotted name is "?.<method>"."""
    found = _dotted(node.func)
    if found and _member(found):
        return found
    members = sorted(p for p in _paths(node.func) if _member(p))
    if members:
        return members[0]
    if not found and isinstance(node.func, ast.Attribute):
        found = "?." + node.func.attr
    return found


def string_target(node):
    """The dotted target of pytest's string form of monkeypatch.setattr / delattr
    (`monkeypatch.setattr("engine.X", value)`, `monkeypatch.delattr("engine.X")`:
    no name given beside the target, so the target is a dotted path), else None.
    Builtin setattr and delattr (a bare name) never take that form."""
    if not isinstance(node, ast.Call) or any(isinstance(a, ast.Starred) for a in node.args):
        return None
    func = callee(node)
    method = func.rsplit(".", 1)[-1]
    if "." not in func or method not in ("setattr", "delattr"):
        return None
    keywords = {k.arg for k in node.keywords}
    target = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "target"), None)
    given = len(node.args) + len(keywords & {"target", "name", "value"})
    if target is None or None in keywords or given != (2 if method == "setattr" else 1):
        return None
    return target


_MULTIPLE_OPTIONS = ("spec", "create", "spec_set", "autospec", "new_callable")
_MONKEYPATCH = ("setattr", "delattr", "setitem", "delitem")
_TARGET_KEYWORDS = ("target", "in_dict", "dic")


def family_target(node):
    """(member, target, kind) for a call of the patch family, else None: every
    member of mock.patch (`patch` itself and any attribute of it called with a
    target: `patch.object`, `patch.dict`, `patch.multiple`), and setattr, delattr,
    setitem and delitem (monkeypatch's methods, the builtins, operator's). `target`
    is what the call patches, its first argument or `target=` / `in_dict=` / `dic=`;
    None where the arguments are unpacked (`*args`, `**kwargs`). `kind` is "string"
    where the target can only be a dotted string (`patch` itself, pytest's string
    form of setattr / delattr), "attribute" for the object form of setattr,
    delattr, setitem and delitem, and "object" for the other members of patch."""
    if not isinstance(node, ast.Call):
        return None
    func = callee(node)
    parts = func.split(".") if func else []
    if parts[-1:] == ["patch"]:
        kind = "string"
    elif parts[-2:-1] == ["patch"]:
        kind = "object"
    elif parts[-1:] and parts[-1] in _MONKEYPATCH:
        kind = "string" if string_target(node) is not None else "attribute"
    else:
        return None
    unpacked = any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords)
    if node.args and not isinstance(node.args[0], ast.Starred):
        target = node.args[0]
    else:
        target = next((k.value for k in node.keywords if k.arg in _TARGET_KEYWORDS), None)
    if target is None and not unpacked:
        return None                                   # no target at all: patch.stopall()
    return func, target, kind


def _modules_table(node):
    """Whether `node` is sys.modules or a copy of it: by its name, `vars(sys)['modules']`,
    `sys.__dict__['modules']`, `getattr(sys, 'modules')`, or any name or expression
    the shared resolver settles as it (`S = sys.modules`, `from sys import modules`,
    `dict(sys.modules)`, `sys.modules.copy()`, `m = sys; m.modules`)."""
    if _dotted(node) == "sys.modules" or "sys.modules" in {name_bindings.original(p) for p in _settled(node)}:
        return True
    if isinstance(node, ast.Subscript) and _const(node.slice) == "modules":
        base = node.value
        return (isinstance(base, ast.Call) and _dotted(base.func) == "vars" and base.args
                and _dotted(base.args[0]) == "sys" or isinstance(base, ast.Attribute) and base.attr == "__dict__"
                and _dotted(base.value) == "sys")
    return (isinstance(node, ast.Call) and _dotted(node.func).split(".")[-1] == "getattr" and len(node.args) >= 2
            and _dotted(node.args[0]) == "sys" and _const(node.args[1]) == "modules")


def _written(key):
    return _const(key) is not None or isinstance(key, ast.Name) and key.id == "__name__"


def computed_lookup(expr):
    """Whether `expr` fetches an object by a name not written out: a getattr whose
    name is not a literal; a subscript or `.get(...)` whose key is not written out
    on vars(), a __dict__ or sys.modules; or sys.modules used other than by a
    written key (copied, iterated: `dict(sys.modules)`, `sys.modules.items()`)."""
    parents = {id(child): node for node in ast.walk(expr) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(expr):
        parent = parents.get(id(node))
        getattr_ = isinstance(node, ast.expr) and (_dotted(node) == "getattr" or "builtins.getattr" in _settled(node))
        if isinstance(node, ast.Call) and (_dotted(node.func).split(".")[-1] == "getattr"
                                           or "builtins.getattr" in _settled(node.func)) \
                and len(node.args) >= 2 and _const(node.args[1]) is None:
            return True
        if getattr_ and not (isinstance(parent, ast.Call) and parent.func is node):
            return True                       # getattr handed on (`functools.reduce(getattr, ...)`)
        if isinstance(node, ast.Call) and "operator.attrgetter" in _settled(node.func) \
                and not (len(node.args) == 1 and _const(node.args[0]) is not None):
            return True
        namespace = (_modules_table(node) or isinstance(node, ast.Call) and (_dotted(node.func) == "vars"
                                                                            or "builtins.vars" in _settled(node.func))
                     or isinstance(node, ast.Attribute) and node.attr == "__dict__"
                     or any(name_bindings.original(p).endswith(".__dict__") for p in _settled(node)))
        if not namespace:
            continue
        call = parents.get(id(parent))
        if isinstance(parent, ast.Subscript) and parent.value is node:
            if not _written(parent.slice):
                return True
        elif isinstance(parent, ast.Attribute) and parent.attr == "get" and isinstance(call, ast.Call) \
                and call.func is parent:
            if not (call.args and _written(call.args[0])):
                return True
        elif _modules_table(node) and not (isinstance(parent, ast.Subscript) and _const(parent.slice) == "modules"):
            return True
    return False


def computed_names(tree):
    """The names the file binds, by any binding the shared resolver follows, from a
    computed lookup (assignment, unpacking, a walrus, a `for` or comprehension over
    one, `with ... as`, a parameter's default), or from a name so bound, re-bound
    plainly or through attributes and items (`Q = R`, `Q = R.sub`), to a fixed
    point. Over the whole file: a name so bound in one scope is a computed name in
    every scope, which can only find more rows."""
    pairs = tree.census_bindings.pairs
    out = set()
    while True:
        before = len(out)
        for name, expr, _how in pairs:
            root = expr
            while isinstance(root, (ast.Attribute, ast.Subscript, ast.Starred)):
                root = root.value
            if computed_lookup(expr) or isinstance(root, ast.Name) and root.id in out:
                out.add(name)
        if len(out) == before:
            return out


def resolved(target, kind, names, returning, imported, computed=frozenset()):
    """Whether the census can name what a patch-family call patches: a string
    literal (read as its site where it is the engine's); for an object, the engine
    (read as its site), or an attribute or item, at any depth, of the engine, of a
    module the file imports (sys.modules[...] among them: a key not written out is a
    row of its own), of a module loaded by name (named, or a row of its own), or of
    vars() of any of these; or a bare name the shared resolver settles, but never
    one it settles as the engine where is_engine does not take it. For the object form of setattr, delattr, setitem and
    delitem, a bare name, or attributes on one, the census does not resolve is let
    through too, unless the file binds it from a computed lookup (`computed`:
    computed_names), or a lookup on the way to it is one (`vars(t)[name]`): see the
    module's docstring."""
    if target is None:
        return False
    if _const(target) is not None:
        return True
    if kind == "string":
        return False
    if is_engine(target, names, returning):
        return True
    if computed_lookup(target) and not _modules_table(target):    # the table itself is patched by its key
        return False
    root = target
    while isinstance(root, (ast.Attribute, ast.Subscript)) and not is_engine(root, names, returning):
        root = root.value
    if is_engine(root, names, returning):
        return True                                   # an object the engine holds, not the engine
    if isinstance(root, ast.Name):
        paths = _CURRENT[0].paths(root) if _CURRENT[0] is not None else set()
        settled = bool(paths) and not any(name_bindings.opaque(p) for p in paths) and not _settled_engine(root)
        return root.id not in computed and (settled or root.id in imported or kind == "attribute")
    if isinstance(root, ast.Call):
        func = _dotted(root.func)
        if func.split(".")[-1] in _LOADERS or func == "sys.modules.get":
            return True
        if func == "vars" and root.args:
            return resolved(root.args[0], kind, names, returning, imported, computed)
    return False


def _imported(tree):
    """Every name an import in `tree` binds."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.asname or a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out |= {a.asname or a.name for a in node.names}
    return out


def dynamic_module(node):
    """The form of a site that loads or names a module the census cannot name
    (a DYNAMIC_MODULE row), or None."""
    if isinstance(node, ast.Subscript):
        own = isinstance(node.slice, ast.Name) and node.slice.id == "__name__"
        if _modules_table(node.value) and _const(node.slice) is None and not own:
            return "sys.modules"
        # a loader looked up in importlib's or builtins' namespace, called or bound
        if (_const(node.slice) is None or _const(node.slice) in _LOADERS) and _namespace(node.value):
            return "vars"
        return None
    if not isinstance(node, ast.Call) or getattr(node, "census_forwards", False):
        return None
    func = _dotted(node.func)
    last = func.split(".")[-1]
    first = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg in ("name", "target")), None)
    table_get = isinstance(node.func, ast.Attribute) and node.func.attr == "get" and _modules_table(node.func.value)
    if (last in _LOADERS or func == "sys.modules.get" or table_get) and first is not None and _const(first) is None:
        return func or "sys.modules.get"
    if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and _namespace(node.func.value) \
            and (not node.args or _const(node.args[0]) is None or _const(node.args[0]) in _LOADERS):
        return "get"                   # a loader looked up by .get() in importlib's or builtins' namespace
    if (last == "getattr" or "builtins.getattr" in _settled(node.func)) and len(node.args) >= 2:
        # a loader reached by getattr, called or bound
        key = _const(node.args[1])
        if key in _LOADERS or (key is None and _on_an_import_module(node.args[0])):
            return "getattr"
    return None


def sites(tree, scoped=None):
    """(line, form, name) for each replacement of an engine attribute in `tree`,
    and (line, form, DYNAMIC_MODULE) for each module it cannot name."""
    out = []
    imported = _imported(tree)
    scoped = scoped if scoped is not None else scopes(tree)
    _bind(tree)
    computed = computed_names(tree)
    for nodes, names, returning in scoped:
        for node in nodes:
            form = dynamic_module(node)
            if form is not None:
                out.append((node.lineno, form, DYNAMIC_MODULE))
            family = family_target(node)
            if family is not None and not resolved(family[1], family[2], names, returning, imported, computed):
                out.append((node.lineno, family[0], DYNAMIC_MODULE))   # a patch target the census cannot name
            if isinstance(node, ast.Call):
                func = callee(node)
                last = func.split(".")[-1]
                target = family[1] if family is not None else None
                if last == "dict" and func.split(".")[-2:-1] == ["patch"] and target is not None \
                        and (is_engine(target, names, returning) or (_const(target) or "").split(".")[0] == "engine"):
                    mapping = node.args[1] if len(node.args) > 1 else next(
                        (k.value for k in node.keywords if k.arg == "values"), None)
                    out += [(node.lineno, func, n) for n in _mapping_names(
                        mapping, [k for k in node.keywords if k.arg not in ("in_dict", "values")])]
                elif isinstance(node.func, ast.Attribute) and node.func.attr == "update" \
                        and is_engine(node.func.value, names, returning):
                    out += [(node.lineno, "update", n)
                            for n in _mapping_names(node.args[0] if node.args else None, node.keywords)]
                elif last == "multiple" and func.split(".")[-2:-1] == ["patch"] and target is not None \
                        and (_const(target) == "engine" or is_engine(target, names, returning)):
                    out += [(node.lineno, func, k.arg or "<dynamic>") for k in node.keywords
                            if k.arg not in _MULTIPLE_OPTIONS + ("target",)]
                elif last in ("setattr", "setitem", "delattr", "delitem", "object") and len(node.args) >= 2 \
                        and is_engine(node.args[0], names, returning):
                    out.append((node.lineno, func, _const(node.args[1]) or "<dynamic>"))
                elif last in ("setattr", "patch") and node.args and (_const(node.args[0]) or "").startswith("engine."):
                    out.append((node.lineno, func, _const(node.args[0])[len("engine."):]))
                elif (_const(string_target(node)) or "").startswith("engine."):       # monkeypatch.delattr("engine.X")
                    out.append((node.lineno, func, _const(string_target(node))[len("engine."):]))
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            elif isinstance(node, ast.Delete):
                targets = node.targets
            for target in targets:
                for t in ast.walk(target):
                    if isinstance(t, ast.Attribute) and isinstance(t.ctx, (ast.Store, ast.Del)) \
                            and is_engine(t.value, names, returning):
                        out.append((t.lineno, "del" if isinstance(t.ctx, ast.Del) else "assignment", t.attr))
                    elif isinstance(t, ast.Subscript) and isinstance(t.ctx, (ast.Store, ast.Del)) \
                            and is_engine(t.value, names, returning):
                        out.append((t.lineno, "del item" if isinstance(t.ctx, ast.Del) else "item assignment",
                                    _const(t.slice) or "<dynamic>"))
    return sorted(set(out))


def rebound(tree, scoped=None):
    """(line, how, name) for each read or write of a withheld name through the engine."""
    out = []
    scoped = scoped if scoped is not None else scopes(tree)
    _bind(tree)
    for nodes, names, returning in scoped:
        for node in nodes:
            if isinstance(node, ast.Attribute) and node.attr in WITHHELD and is_engine(node.value, names, returning):
                out.append((node.lineno, type(node.ctx).__name__.lower(), node.attr))
            elif isinstance(node, ast.Subscript) and _const(node.slice) in WITHHELD \
                    and is_engine(node.value, names, returning):
                out.append((node.lineno, "item " + type(node.ctx).__name__.lower(), _const(node.slice)))
            elif isinstance(node, ast.Call) and len(node.args) >= 2 \
                    and _dotted(node.func).split(".")[-1] in ("getattr", "setattr", "hasattr", "delattr", "setitem",
                                                             "delitem") \
                    and _const(node.args[1]) in WITHHELD and is_engine(node.args[0], names, returning):
                out.append((node.lineno, _dotted(node.func), _const(node.args[1])))
    return sorted(set(out))


def _candidates(tree):
    """(line, text) of every string in `tree` that reads as engine code."""
    out = []
    inside = {id(v) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for v in node.values}
    for node in ast.walk(tree):
        text = None
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in inside:
            text = node.value
        elif isinstance(node, ast.JoinedStr):
            text = "".join(v.value if isinstance(v, ast.Constant) else "__field__" for v in node.values)
        if text and ("import engine" in text or ("\n" in text and _CODE.search(text))):
            out.append((node.lineno, text))
    return out


def read_script(text):
    """(how, tree or None): the script read as Python, or None where it must be grepped."""
    body = textwrap.dedent(text)
    try:
        return "parsed", ast.parse(body)
    except SyntaxError:
        pass
    try:
        fields = string.Formatter().parse(body)
        formatted = "".join(lit + ("__field__" if name is not None else "") for lit, name, _spec, _conv in fields)
        return "formatted", ast.parse(formatted)
    except (SyntaxError, ValueError):
        return "grepped", None


def census(paths):
    """{'sites': [...], 'rebound': [...], 'methods': {file: {how: n}}} over
    `paths`: each row (file, line, where, form, name), where = 'code' or
    'script (how)'."""
    found, reb, methods = [], [], {}
    for path in paths:
        path = Path(path)
        _read_one(path.name, path.read_text(encoding="utf-8"), found, reb, methods)
    return {"sites": sorted(set(found)), "rebound": sorted(set(reb)), "methods": methods}


def census_of_module(module, paths):
    """The same reading of the replacements of another module's attributes:
    (file, line, where, form, name) for each. Each file that names `module`
    is read with that module's name written where the engine's was, and the
    engine's written out of the way, so that every form the census knows is
    read for it; what the engine's conventional names (E, eng ...) would be
    read as without it is taken off."""
    named = re.compile(rf"\b{re.escape(module)}\b")
    found = set()
    for path in paths:
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if not named.search(text):
            continue
        hidden = re.sub(r"\bengine\b", "not_the_program", text)
        as_it_is, swapped = [], []
        _read_one(path.name, hidden, as_it_is, [], {})
        _read_one(path.name, named.sub("engine", hidden), swapped, [], {})
        found |= set(swapped) - set(as_it_is)
    return sorted(found)


def _read_one(name, text, found, reb, methods):
    """One file's sites and reads, added to the three collections."""
    tree = ast.parse(text)
    scoped = scopes(tree)
    found += [(name, line, "code", form, attr) for line, form, attr in sites(tree, scoped)]
    reb += [(name, line, "code", how, attr) for line, how, attr in rebound(tree, scoped)]
    for start, script in _candidates(tree):
        how, script_tree = read_script(script)
        methods.setdefault(name, {}).setdefault(how, 0)
        methods[name][how] += 1
        if script_tree is not None:
            offset = start - 1
            scoped = scopes(script_tree)
            found += [(name, offset + line, f"script ({how})", form, attr)
                      for line, form, attr in sites(script_tree, scoped)]
            reb += [(name, offset + line, f"script ({how})", h, attr)
                    for line, h, attr in rebound(script_tree, scoped)]
        else:
            for n, line in enumerate(script.splitlines(), start):
                for rx in GREP_SITES:
                    found += [(name, n, "script (grepped)", "grep", m.group(1)) for m in rx.finditer(line)]
                for rx in GREP_REBOUND:
                    reb += [(name, n, "script (grepped)", "grep", m.group(1)) for m in rx.finditer(line)]
