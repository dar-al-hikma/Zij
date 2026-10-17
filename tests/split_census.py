"""The census of engine replacements, by `ast`, in test code and in the scripts
tests hand to a subprocess (tests/test_split_astro_2026_10_14.py uses it).

A site is a place that replaces an attribute of the engine module, or an item
of the `engine` fixture's namespace: monkeypatch.setattr / setitem / delattr,
setattr / delattr, mock.patch.object, mock.patch("engine.X"), assignment to or
deletion of `R.X` or `R["X"]`, and mock.patch.dict(R, ...) or R.update(...),
R being the engine (vars() or __dict__ of it among them). A site's name is the
name it replaces where the site writes it; "<dynamic>" where it does not (a
variable; a mapping that is not written out; patch.dict's clear=True, which
touches every name). R is the engine
where it is a name the file binds to it -- `import engine [as R]`, the module
from importlib.import_module("engine") (or __import__, under any name the file
binds either to), sys.modules["engine"],
importlib.reload of it, vars() or __dict__ of it, a local function that
returns it -- or one of the names the suite gives it by convention
(ENGINE_NAMES: the fixture's `engine` among them).

Each name is resolved in its own scope: a name a function binds to something
else is not the engine there, whatever the file binds it to elsewhere. A test's
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

ENGINE_NAMES = frozenset({"engine", "engine_module", "E", "_engine", "eng"})
WITHHELD = ("_EPHEMERIS_FOLDER", "_DELTA_T_REFERENCE")
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


def is_engine(node, names, returning=frozenset()):
    """Whether `node` evaluates to the engine module or its namespace."""
    if isinstance(node, ast.Name):
        return node.id in names
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
    for _ in range(4):
        engine_bound, other_bound = set(), set()
        for node in nodes:
            if isinstance(node, ast.Import):
                for a in node.names:
                    (engine_bound if a.name == "engine" else other_bound).add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                other_bound |= {a.asname or a.name for a in node.names}
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                here = set().union(*(_targets(t) for t in targets))
                indices = _unpacked(node.value, params, tuples)
                if indices and len(targets) == 1 and isinstance(targets[0], (ast.Tuple, ast.List)):
                    for i, elt in enumerate(targets[0].elts):
                        (engine_bound if i in indices else other_bound).update(_targets(elt))
                    continue
                (engine_bound if is_engine(node.value, current, returning) else other_bound).update(here)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                other_bound |= _targets(node.target)
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                other_bound |= _targets(node.optional_vars)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                other_bound.add(node.name)
        new = frozenset((base - (other_bound - engine_bound)) | engine_bound)
        if new == current:
            break
        current = new
    return current


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
    names = set(_LOADERS)

    def is_loader(node):
        return (isinstance(node, ast.Name) and node.id in names
                or isinstance(node, ast.Attribute) and node.attr in _LOADERS)

    while True:
        before = len(names)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("importlib", "builtins"):
                names.update(a.asname or a.name for a in node.names if a.name in _LOADERS)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None \
                    and is_loader(node.value):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names.update(t.id for t in targets if isinstance(t, ast.Name))
        if len(names) == before:
            break

    def holds_a_loader(func):          # `(f := importlib.import_module)`: a loader not called inside it
        if isinstance(func, (ast.Name, ast.Attribute)):
            return False
        called = {id(n.func) for n in ast.walk(func) if isinstance(n, ast.Call)}
        return any(is_loader(n) and id(n) not in called for n in ast.walk(func))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (isinstance(node.func, ast.Name) and node.func.id in names - set(_LOADERS)
                                           or holds_a_loader(node.func)):
            node.func = ast.copy_location(ast.Name(id="import_module", ctx=ast.Load()), node.func)


def scopes(tree):
    """[(the scope's own nodes, its engine names, the functions it sees that
    return the engine)] for the module and every function and class body.
    Calls through another name for an import function are named first
    (_name_the_loaders)."""
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


def sites(tree, scoped=None):
    """(line, form, name) for each replacement of an engine attribute in `tree`."""
    out = []
    for nodes, names, returning in scoped if scoped is not None else scopes(tree):
        for node in nodes:
            if isinstance(node, ast.Call):
                func = _dotted(node.func)
                last = func.split(".")[-1]
                if last == "dict" and func.split(".")[-2:-1] == ["patch"] and node.args \
                        and (is_engine(node.args[0], names, returning)
                             or (_const(node.args[0]) or "").split(".")[0] == "engine"):
                    out += [(node.lineno, func, n)
                            for n in _mapping_names(node.args[1] if len(node.args) > 1 else None, node.keywords)]
                elif isinstance(node.func, ast.Attribute) and node.func.attr == "update" \
                        and is_engine(node.func.value, names, returning):
                    out += [(node.lineno, "update", n)
                            for n in _mapping_names(node.args[0] if node.args else None, node.keywords)]
                elif last in ("setattr", "setitem", "delattr", "delitem", "object") and len(node.args) >= 2 \
                        and is_engine(node.args[0], names, returning):
                    out.append((node.lineno, func, _const(node.args[1]) or "<dynamic>"))
                elif last in ("setattr", "patch") and node.args and (_const(node.args[0]) or "").startswith("engine."):
                    out.append((node.lineno, func, _const(node.args[0])[len("engine."):]))
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
    for nodes, names, returning in scoped if scoped is not None else scopes(tree):
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
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        name = path.name
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
    return {"sites": sorted(set(found)), "rebound": sorted(set(reb)), "methods": methods}
