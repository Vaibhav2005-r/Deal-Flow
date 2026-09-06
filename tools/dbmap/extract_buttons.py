"""Pull every interactive control out of the frontend, with its handler.

A small scanner rather than a regex: JSX attributes contain `>` inside
expressions (`disabled={n > 0}`), which cuts a naive regex in the wrong place
and yields attribute fragments instead of labels.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WEB = Path("src")
TAGS = ("button", "NavLink", "Link", "a")


def find_tag_end(src: str, i: int) -> int:
    """Index just past the '>' that closes the open tag starting at i."""
    depth_brace = 0
    quote = ""
    while i < len(src):
        c = src[i]
        if quote:
            if c == quote and src[i - 1] != "\\":
                quote = ""
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth_brace += 1
        elif c == "}":
            depth_brace -= 1
        elif c == ">" and depth_brace == 0:
            return i + 1
        i += 1
    return -1


def find_close(src: str, i: int, tag: str) -> int:
    """Index of the matching </tag>, honouring nesting."""
    depth = 1
    open_re = re.compile(r"<" + tag + r"\b")
    close = f"</{tag}>"
    while i < len(src):
        nxt_close = src.find(close, i)
        if nxt_close == -1:
            return -1
        m = open_re.search(src, i, nxt_close)
        if m:
            depth += 1
            i = m.end()
            continue
        depth -= 1
        if depth == 0:
            return nxt_close
        i = nxt_close + len(close)
    return -1


def attr(attrs: str, name: str) -> str:
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else ""


def handler(attrs: str) -> str:
    i = attrs.find("onClick=")
    if i == -1:
        return ""
    j = attrs.find("{", i)
    if j == -1:
        return ""
    depth, k = 0, j
    while k < len(attrs):
        if attrs[k] == "{":
            depth += 1
        elif attrs[k] == "}":
            depth -= 1
            if depth == 0:
                return " ".join(attrs[j + 1 : k].split())[:200]
        k += 1
    return ""


def text_of(inner: str) -> str:
    inner = re.sub(r"<svg\b.*?</svg>", "", inner, flags=re.S)
    inner = re.sub(r"\{/\*.*?\*/\}", "", inner, flags=re.S)
    inner = re.sub(r"<[^>]+>", " ", inner)
    # keep simple ternary string literals: {busy ? "Saving…" : "Save"} -> Save
    def pick(m: re.Match) -> str:
        lits = re.findall(r'"([^"]{2,})"', m.group(0))
        return lits[-1] if lits else " "
    inner = re.sub(r"\{[^{}]*\}", pick, inner)
    inner = (inner.replace("&rarr;", "->").replace("&nbsp;", " ")
                  .replace("&amp;", "&").replace("&larr;", "<-"))
    return " ".join(inner.split())[:70]


rows = []
for p in sorted(WEB.rglob("*.tsx")):
    src = p.read_text(encoding="utf-8")
    rel = str(p.relative_to("src"))
    for tag in TAGS:
        for m in re.finditer(r"<" + tag + r"\b", src):
            start = m.start()
            tag_end = find_tag_end(src, start)
            if tag_end == -1:
                continue
            attrs = src[m.end() : tag_end - 1]
            if src[tag_end - 2] == "/":  # self-closing
                inner = ""
            else:
                close = find_close(src, tag_end, tag)
                if close == -1:
                    continue
                inner = src[tag_end:close]
            rows.append({
                "file": rel,
                "line": src[:start].count("\n") + 1,
                "kind": tag,
                "label": text_of(inner),
                "type": attr(attrs, "type"),
                "to": attr(attrs, "to") or attr(attrs, "href"),
                "testid": attr(attrs, "data-testid"),
                "onClick": handler(attrs),
            })

rows.sort(key=lambda r: (r["file"], r["line"]))
json.dump(rows, open(sys.argv[1], "w"), indent=1)
print(f"{len(rows)} controls")
