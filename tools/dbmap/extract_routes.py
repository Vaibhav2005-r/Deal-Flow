"""Extract route -> table read/write mapping from the API source.

Static, AST-based. Builds a call graph over app/api and app/services, then for
each route function resolves transitively which model classes it touches and
whether the touch is a read or a write.

A "write" is any of: session.add/add_all/delete/merge of a model, a model
constructor, a sqlalchemy update()/insert()/delete() statement, or an
attribute assignment on a local that was bound from a query of that model
(`quote = session.get(Quotation, id)` then `quote.state = ...`).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

API = Path("app/api")
SERVICES = Path("app/services")

MODELS: dict[str, str] = {}
tree = ast.parse(Path("app/models/tables.py").read_text())
for node in tree.body:
    if isinstance(node, ast.ClassDef):
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == "__tablename__"
                and isinstance(stmt.value, ast.Constant)
            ):
                MODELS[node.name] = stmt.value.value

QUERY_CALLS = {"get", "scalar", "scalars", "execute", "select", "one", "first", "all"}


class FnInfo:
    def __init__(self, name: str, module: str):
        self.name = name
        self.module = module
        self.reads: set[str] = set()
        self.writes: set[str] = set()
        self.calls: set[str] = set()
        self.route: tuple[str, str] | None = None
        self.doc: str = ""


def models_in(node: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in MODELS:
            out.add(n.id)
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in MODELS:
            out.add(n.value.id)
    return out


def analyse(path: Path) -> tuple[dict[str, FnInfo], str]:
    module = path.stem
    tree = ast.parse(path.read_text())

    prefix = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "APIRouter":
            for kw in node.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    prefix = kw.value.value

    fns: dict[str, FnInfo] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        info = FnInfo(node.name, module)
        info.doc = (ast.get_docstring(node) or "").strip().split("\n")[0]

        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == "router"
            ):
                method = dec.func.attr.upper()
                p = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else ""
                info.route = (method, prefix + p)

        # ---- local variable -> model, from queries and loops
        var_model: dict[str, str] = {}

        def bind(target: ast.AST, source: ast.AST) -> None:
            ms = models_in(source)
            if len(ms) != 1:
                return
            model = next(iter(ms))
            if isinstance(target, ast.Name):
                var_model[target.id] = model
            elif isinstance(target, (ast.Tuple, ast.List)):
                for el in target.elts:
                    if isinstance(el, ast.Name):
                        var_model[el.id] = model

        for n in ast.walk(node):
            if isinstance(n, ast.Assign) and len(n.targets) == 1:
                bind(n.targets[0], n.value)
            elif isinstance(n, ast.AnnAssign) and n.value is not None:
                bind(n.target, n.value)
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                bind(n.target, n.iter)
            elif isinstance(n, ast.comprehension):
                bind(n.target, n.iter)
            elif isinstance(n, ast.withitem) and n.optional_vars is not None:
                bind(n.optional_vars, n.context_expr)

        # a dict/list of ORM rows keyed by something: known[k] = row, then
        # known[k].field = ... . Bind the container to the model too.
        for n in ast.walk(node):
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                v = n.value
                if isinstance(v, (ast.DictComp, ast.ListComp, ast.SetComp, ast.GeneratorExp)):
                    ms = models_in(v)
                    if len(ms) == 1:
                        var_model[n.targets[0].id] = next(iter(ms))

        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if n.func.attr in {"add", "add_all", "delete", "merge"}:
                    for a in n.args:
                        info.writes |= models_in(a)
                        # session.delete(quote) where quote is a bound local
                        if isinstance(a, ast.Name) and a.id in var_model:
                            info.writes.add(var_model[a.id])
                elif n.func.attr in QUERY_CALLS:
                    for a in n.args:
                        info.reads |= models_in(a)
                info.calls.add(n.func.attr)
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                if n.func.id in MODELS:
                    info.writes.add(n.func.id)
                elif n.func.id in {"update", "insert"}:
                    for a in n.args:
                        info.writes |= models_in(a)
                elif n.func.id in {"select", "delete"}:
                    for a in n.args:
                        (info.writes if n.func.id == "delete" else info.reads).update(models_in(a))
                info.calls.add(n.func.id)

            # attribute assignment on a bound ORM local == an UPDATE
            targets: list[ast.AST] = []
            if isinstance(n, ast.Assign):
                targets = list(n.targets)
            elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
                targets = [n.target]
            for t in targets:
                if not isinstance(t, ast.Attribute):
                    continue
                base = t.value
                # unwrap known[k] / rows[0] so container[...] .field counts
                while isinstance(base, ast.Subscript):
                    base = base.value
                if isinstance(base, ast.Name) and base.id in var_model:
                    info.writes.add(var_model[base.id])

        info.reads |= models_in(node) - info.writes
        fns[node.name] = info
    return fns, prefix


all_fns: dict[str, FnInfo] = {}
for p in sorted(list(API.glob("*.py")) + list(SERVICES.glob("*.py"))):
    if p.name == "__init__.py":
        continue
    fns, _ = analyse(p)
    for name, info in fns.items():
        if name not in all_fns or (info.route and not all_fns[name].route):
            all_fns[name] = info


def resolve(name: str, seen: set[str]) -> tuple[set[str], set[str]]:
    if name in seen or name not in all_fns:
        return set(), set()
    seen.add(name)
    fn = all_fns[name]
    reads, writes = set(fn.reads), set(fn.writes)
    for callee in fn.calls:
        r, w = resolve(callee, seen)
        reads |= r
        writes |= w
    return reads, writes


rows = []
for name, fn in all_fns.items():
    if not fn.route:
        continue
    reads, writes = resolve(name, set())
    reads -= writes
    rows.append({
        "method": fn.route[0],
        "path": fn.route[1],
        "fn": name,
        "module": fn.module,
        "doc": fn.doc,
        "reads": sorted(MODELS[m] for m in reads),
        "writes": sorted(MODELS[m] for m in writes),
    })

rows.sort(key=lambda r: (r["module"], r["path"], r["method"]))
json.dump(rows, sys.stdout, indent=1)
