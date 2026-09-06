"""Resolve each control's handler to the API calls it issues.

For every file, find each function/arrow definition, take its body by brace
matching, and collect the api.* paths inside it (following one level of local
helper calls, which is how Pipeline's act()/subscriptionAction() work).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SP = Path(__file__).parent
WEB = Path("src")

API_CALL = re.compile(
    r"api\.(get|getPaginated|post|put|patch|del)\s*(?:<[^(]*?>)?\s*\(\s*(`[^`]*`|\"[^\"]*\")",
    re.S,
)
METHOD = {"get": "GET", "getPaginated": "GET", "post": "POST",
          "put": "PUT", "patch": "PATCH", "del": "DELETE"}


def body_of(src: str, start: int) -> str:
    i = src.find("{", start)
    if i == -1:
        return ""
    depth, j = 0, i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
        j += 1
    return src[i:]


def normalise(raw: str) -> str:
    p = raw.strip("`\"")
    p = re.sub(r"\$\{[^}]*\}", "{id}", p)
    return p.split("?")[0]


def calls_in(text: str) -> list[tuple[str, str]]:
    return [(METHOD[m.group(1)], normalise(m.group(2))) for m in API_CALL.finditer(text)]


def functions(src: str) -> dict[str, str]:
    """name -> body text, for `function f()`, `const f = ...` and `async function f()`."""
    out: dict[str, str] = {}
    for m in re.finditer(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", src):
        out[m.group(1)] = body_of(src, m.end())
    for m in re.finditer(
        r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", src
    ):
        out.setdefault(m.group(1), body_of(src, m.end()))
    return out


buttons = json.load(open(SP / "buttons.json"))
out = []
cache: dict[str, tuple[str, dict[str, str]]] = {}

for b in buttons:
    path = WEB / b["file"]
    if b["file"] not in cache:
        src = path.read_text(encoding="utf-8")
        cache[b["file"]] = (src, functions(src))
    src, fns = cache[b["file"]]

    handler = b["onClick"]
    found: list[tuple[str, str]] = []

    if handler:
        # inline api call in the handler itself
        found += calls_in(handler)
        # named helpers referenced by the handler
        for name in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", handler) + re.findall(
            r"^\s*([A-Za-z_$][\w$]*)\s*$", handler
        ):
            if name in fns:
                found += calls_in(fns[name])
                # one more level (act -> api.post)
                for inner in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", fns[name]):
                    if inner in fns and inner != name:
                        found += calls_in(fns[inner])
        # a bare handler name: onClick={sendToPortal}
        bare = handler.strip()
        if bare in fns:
            found += calls_in(fns[bare])

    b["calls"] = sorted({f"{m} {p}" for m, p in found})
    out.append(b)

json.dump(out, open(SP / "buttons_resolved.json", "w"), indent=1)

n = sum(1 for b in out if b["calls"])
print(f"{n} of {len(out)} controls resolved to an API call")
for b in out:
    if b["calls"]:
        print(f"  {b['file']:28s} {b['label'][:34]:34s} -> {', '.join(b['calls'])[:80]}")
