"""Merge the dynamic SQL trace onto the static route list.

Dynamic wins where it has data (it is ground truth); static fills the gaps for
endpoints the suite never exercised, and those are flagged so nothing is
presented as verified when it was only inferred.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SP = Path(__file__).parent
routes = json.load(open(SP / "routes.json"))
trace = json.load(open(SP / "sqltrace.json"))


def to_regex(path: str) -> re.Pattern:
    pat = re.sub(r"\{[^}]+\}", r"[^/]+", path)
    return re.compile("^" + pat + "$")


compiled = [(r, to_regex(r["path"])) for r in routes]

merged: dict[tuple[str, str], dict] = {}
for r in routes:
    merged[(r["method"], r["path"])] = {
        **r,
        "dyn_reads": set(),
        "dyn_writes": set(),
        "observed": False,
    }

unmatched = []
for key, tables in trace.items():
    method, _, path = key.partition(" ")
    hit = None
    # Most specific template first: fewest placeholders wins, so a literal
    # /api/invoices/summary is not swallowed by /api/invoices/{invoice_id}.
    for r, rx in sorted(
        compiled,
        key=lambda x: (x[0]["path"].count("{"), -len(x[0]["path"])),
    ):
        if r["method"] == method and rx.match(path):
            hit = r
            break
    if hit is None:
        unmatched.append(key)
        continue
    slot = merged[(hit["method"], hit["path"])]
    slot["dyn_reads"] |= set(tables["reads"])
    slot["dyn_writes"] |= set(tables["writes"])
    slot["observed"] = True

out = []
for (method, path), slot in merged.items():
    if slot["observed"]:
        writes = sorted(slot["dyn_writes"])
        reads = sorted(slot["dyn_reads"] - slot["dyn_writes"])
        source = "observed"
    else:
        writes = sorted(slot["writes"])
        reads = sorted(set(slot["reads"]) - set(writes))
        source = "static"
    out.append({
        "method": method,
        "path": path,
        "fn": slot["fn"],
        "module": slot["module"],
        "doc": slot["doc"],
        "reads": reads,
        "writes": writes,
        "source": source,
    })

out.sort(key=lambda r: (r["module"], r["path"], r["method"]))
json.dump(out, open(SP / "endpoints.json", "w"), indent=1)

obs = sum(1 for r in out if r["source"] == "observed")
print(f"{len(out)} routes; {obs} observed, {len(out)-obs} static-only")
if unmatched:
    print(f"unmatched traced paths ({len(unmatched)}):")
    for u in sorted(set(unmatched))[:20]:
        print("  ", u)
print()
for r in out:
    if r["source"] != "observed":
        print(f"  STATIC-ONLY  {r['method']:6s} {r['path']}")
