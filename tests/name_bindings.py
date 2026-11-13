"""What each name in a file stands for, read from bindings written out with
literals: one resolver shared by the scans that ask it (the shipped-module
inventory, tests/shipped_modules.py; the split census, tests/split_census.py;
the errno scan of tests/test_mac1_platform_names_2026_10_14.py).

A value is a dotted path: a module and the attributes, items and copies taken
of it, written out (`importlib.import_module`, `sys.modules`, `json.__dict__`,
`unittest.mock.patch.dict`). An attribute of a module that is itself one of
the modules the scans ask about (MODULES) is that module, whatever module it
is reached through: `reprlib.builtins` is `builtins`, `os.sys.modules` is
`sys.modules`, `socket.errno` is `errno`; `__builtins__`, as a name or as an
attribute of a module, is `builtins.__dict__`. A name the resolver cannot
settle (a parameter without a default, a function's result, a computed
lookup) stands for itself, an opaque path starting "?" (`?exc.errno`); a name
bound to an attribute of one stands for that (`s = monkeypatch.setattr` is
`?monkeypatch.setattr`).

The bindings followed, over the whole file and to a fixed point (a name bound
anywhere stands for each of its values everywhere, which only finds more):
`import x [as y]`; `from x import y [as z]`, a module imported from another
module included (`from pkgutil import importlib`, `from sys import modules`);
assignment, annotated assignment, a tuple or list of names (none starred)
unpacked from a tuple or list written out with as many items, a walrus, a `for`
over a tuple or list written out, `with ... as` (`contextlib.nullcontext(x)`, x
given by position, is x; another manager is opaque), a parameter's default; an
augmented assignment rebinds to something unsettled. `global` and `nonlocal`
need nothing more: every binding is file-wide. These and no others: where a
name is bound by a form not listed, what it stands for is not read.
Of the scans that ask it, the inventory refuses a bare `exec`, `eval` or
`compile` wherever it is written, whatever binds the name (read `re.compile`
through its module).

The expressions read: a name; an attribute of a value; `getattr(<value>,
"<literal>"[, default])`; `operator.attrgetter("<literal>")(<value>)`;
`vars(<value>)` and `<value>.__dict__` (the value's namespace); a subscript or
`.get` by a literal key on a namespace, on sys.modules (or a copy of either),
or on a tuple or list written out (by a literal index); a copy of a mapping
(`dict(x)`, `x.copy()`, `{**x}`), which is x's path marked "~" (`sys.modules~`):
the same keys, so a lookup in it is a lookup in x, but not x, so a write to it
writes nothing of x's; `importlib.import_module("<literal>")` and `__import__("<literal>")`;
`a or b`, `a if c else b` (either); and a walrus (its value). A builtin's name
the file does not bind is `builtins.<name>` (`getattr`, `vars`, `setattr`), so
`ga = getattr` makes `ga` stand for `builtins.getattr`.

Not settled, so opaque: a name or key not written out (`getattr(json, name)`,
`globals()[name]`), a parameter without a default, a call's result but the
loads above. Not read at all, so a name bound only so is opaque: a star import
(`from sys import *`); a match pattern (`case object(modules=S)`, `case p`); a
starred name in unpacking (`p, *_ = mock.patch, 1`); a value held in a class
attribute or a dict written out (`class K: p = mock.patch`, `{"k":
socket}["k"]`); a value given by keyword
(`contextlib.nullcontext(enter_result=x)`, `__import__(name="socket")`). Nor is
a fetch by any method but those above (`x.__getattribute__(name)`,
`operator.getitem`, `.setdefault`, `inspect.getattr_static`,
`collections.ChainMap`): its result is opaque. What such a name does is checked
where it runs for two of the scans that ask this resolver: a
replacement of the engine by the tripwire in tests/conftest.py, a module loaded
or code run from a string by the import audit (tests/import_audit.py), each
within the limits it names; the errno scan has no such check. Standard library only.
"""
from __future__ import annotations

import ast
import builtins as _builtins_module

MODULES = ("builtins", "importlib", "sys", "errno")
LOADER_PATHS = ("importlib.import_module", "builtins.__import__")
_BUILTIN_NAMES = frozenset(dir(_builtins_module))
_LONGEST = 12            # path parts kept; a longer path is a cycle (`x = x.y`) and is dropped


def opaque(path: str) -> bool:
    return path.startswith("?")


def normal(path: str) -> str | None:
    """`path` with an attribute that is one of MODULES taken as that module, and
    `__builtins__` as builtins' namespace; None where it grows past _LONGEST."""
    parts = path.split(".")
    if len(parts) > _LONGEST:
        return None
    if opaque(path):
        return path
    for i in range(len(parts) - 1, 0, -1):
        if parts[i] in MODULES:
            return ".".join(parts[i:])
        if parts[i] == "__builtins__":
            return ".".join(["builtins", "__dict__"] + parts[i + 1:])
    return path


def _join(base: str, attr: str) -> str | None:
    return normal(f"{base}.{attr}")


def copy_of(path: str) -> str:
    return path if path.endswith("~") else path + "~"


def original(path: str) -> str:
    """The path a copy was taken of (the path itself where it is no copy)."""
    return path.rstrip("~")


def _literal(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)) else None


class Bindings:
    """The names of one parsed file and what each stands for (`paths`)."""

    def __init__(self, tree: ast.AST):
        self.tree = tree
        self.pairs = []          # (name, expression, how): how "value" or "element" (an item of what it iterates)
        self.direct = []         # (name, path): an import's binding, a definition's (opaque)
        self.bound = set()
        self._collect(tree)
        self.env = {}            # name -> set of paths
        self.unsettled = set()   # names with a binding the resolver cannot settle
        self._solve()

    # ------------------------------------------------------------------ the bindings

    def _target(self, target, value, how="value"):
        if isinstance(target, ast.Name):
            self.pairs.append((target.id, value, how))
            self.bound.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            if how == "value" and isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts) \
                    and not any(isinstance(e, ast.Starred) for e in target.elts + value.elts):
                for t, v in zip(target.elts, value.elts):
                    self._target(t, v)
            else:
                for t in target.elts:
                    self._target(t.value if isinstance(t, ast.Starred) else t, value, "element")
        elif isinstance(target, ast.Starred):
            self._target(target.value, value, "element")

    def _iterated(self, target, iterable):
        if isinstance(iterable, (ast.Tuple, ast.List, ast.Set)):
            for element in iterable.elts:
                self._target(target, element)
        else:
            self._target(target, iterable, "element")

    def _collect(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    name = a.asname or a.name.split(".")[0]
                    self.direct.append((name, normal(a.name if a.asname else a.name.split(".")[0])))
                    self.bound.add(name)
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    name = a.asname or a.name
                    path = normal(f"{node.module}.{a.name}") if node.module and not node.level else "?" + name
                    self.direct.append((name, path))
                    self.bound.add(name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    self._target(t, node.value)
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                self._target(node.target, node.value)
            elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                self.direct.append((node.target.id, "?" + node.target.id))
                self.bound.add(node.target.id)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                self._iterated(node.target, node.iter)
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                self._target(node.optional_vars, node.context_expr, "manager")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                args = node.args
                positional = args.posonlyargs + args.args
                defaults = dict(zip([a.arg for a in positional[len(positional) - len(args.defaults):]],
                                    args.defaults))
                defaults.update({a.arg: d for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is not None})
                for a in positional + args.kwonlyargs + [x for x in (args.vararg, args.kwarg) if x]:
                    if a.arg in defaults:
                        self.pairs.append((a.arg, defaults[a.arg], "value"))
                    else:
                        self.direct.append((a.arg, "?" + a.arg))
                    self.bound.add(a.arg)
                if not isinstance(node, ast.Lambda):
                    self.direct.append((node.name, "?" + node.name))
                    self.bound.add(node.name)
            elif isinstance(node, ast.ClassDef):
                self.direct.append((node.name, "?" + node.name))
                self.bound.add(node.name)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                self.direct.append((node.name, "?" + node.name))
                self.bound.add(node.name)

    def _solve(self):
        for name, path in self.direct:
            if path is None or opaque(path):
                self.unsettled.add(name)
            else:
                self.env.setdefault(name, set()).add(path)
        for _ in range(20):
            before = ({k: set(v) for k, v in self.env.items()}, set(self.unsettled))
            for name, expr, how in self.pairs:
                found = {p for p in self._value(expr, how)          # `x = x.a`: no path built on x's own opacity
                         if not (opaque(p) and p[1:].split(".")[0] == name)}
                if found:
                    self.env.setdefault(name, set()).update(found)    # an opaque path too: `s = monkeypatch.setattr`
                if not found or any(opaque(p) for p in found):
                    self.unsettled.add(name)
            if (self.env, self.unsettled) == before:
                break

    def _value(self, expr, how):
        if how == "element":
            return set()
        if how == "manager":
            if isinstance(expr, ast.Call) and self.paths(expr.func) & {"contextlib.nullcontext"} and expr.args:
                return self.paths(expr.args[0])
            return set()
        return self.paths(expr)

    # ------------------------------------------------------------------ what an expression stands for

    def paths(self, node) -> set[str]:
        """Every path `node` may stand for; an opaque one where it cannot be settled."""
        if isinstance(node, ast.Name):
            if node.id == "__builtins__" and node.id not in self.bound:
                return {"builtins.__dict__"}
            out = set(self.env.get(node.id, ()))
            if node.id not in self.bound and node.id in _BUILTIN_NAMES:
                out.add("builtins." + node.id)
            elif node.id in self.unsettled and not any(opaque(p) for p in out) or not out:
                out.add("?" + node.id)
            return out
        if isinstance(node, ast.Attribute):
            if node.attr == "__dict__":
                return {p for p in (_join(b, "__dict__") for b in self.paths(node.value)) if p}
            return {p for p in (_join(b, node.attr) for b in self.paths(node.value)) if p}
        if isinstance(node, ast.NamedExpr):
            return self.paths(node.value)
        if isinstance(node, ast.BoolOp):
            return set().union(*(self.paths(v) for v in node.values))
        if isinstance(node, ast.IfExp):
            return self.paths(node.body) | self.paths(node.orelse)
        if isinstance(node, ast.Subscript):
            return self._item(node.value, node.slice)
        if isinstance(node, ast.Dict) and len(node.keys) == 1 and node.keys[0] is None:
            return {copy_of(p) for p in self.paths(node.values[0])}             # {**x}
        if isinstance(node, ast.Call):
            return self._call(node)
        return set()

    def _item(self, container, key):
        literal = _literal(key)
        if literal is None:
            return set()
        if isinstance(container, (ast.Tuple, ast.List)) and isinstance(literal, int):
            return self.paths(container.elts[literal]) if -len(container.elts) <= literal < len(container.elts) \
                and not any(isinstance(e, ast.Starred) for e in container.elts) else set()
        out = set()
        for base in self.paths(container):
            if opaque(base) or not isinstance(literal, str):
                continue
            base = original(base)
            if base == "sys.modules":
                out.add(normal(literal) or literal)
            elif base.endswith(".__dict__"):
                joined = _join(base[:-len(".__dict__")], literal)
                if joined:
                    out.add(joined)
        return out

    def _call(self, node):
        func = self.paths(node.func)
        args = node.args
        if any(isinstance(a, ast.Starred) for a in args):
            return set()
        if func & {"builtins.getattr"} and len(args) in (2, 3) and isinstance(_literal(args[1]), str):
            return {p for p in (_join(b, args[1].value) for b in self.paths(args[0])) if p}
        if func & {"builtins.vars"} and len(args) == 1:
            return {p for p in (_join(b, "__dict__") for b in self.paths(args[0])) if p}
        if func & {"builtins.dict"} and len(args) == 1 and not node.keywords:
            return {copy_of(p) for p in self.paths(args[0])}
        if func & set(LOADER_PATHS) and args and isinstance(_literal(args[0]), str):
            name = args[0].value
            return {normal(name if func & {"importlib.import_module"} else name.split(".")[0]) or name}
        if isinstance(node.func, ast.Attribute) and node.func.attr == "copy" and not args:
            return {copy_of(b) for b in self.paths(node.func.value)
                    if original(b) == "sys.modules" or original(b).endswith(".__dict__")}
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and len(args) in (1, 2):
            return self._item(node.func.value, args[0])
        if isinstance(node.func, ast.Call) and self.paths(node.func.func) & {"operator.attrgetter"} \
                and len(node.func.args) == 1 and isinstance(_literal(node.func.args[0]), str) and len(args) == 1:
            out = self.paths(args[0])
            for attr in node.func.args[0].value.split("."):
                out = {p for p in (_join(b, attr) for b in out) if p}
            return out
        return set()

    def stands_for(self, node, path: str) -> bool:
        """Whether `node` may stand for `path`."""
        return path in self.paths(node)
