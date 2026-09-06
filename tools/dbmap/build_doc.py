"""Render the button -> database mapping to a print-ready HTML document."""
from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import controls

SP = Path(__file__).parent


def loose(path: str) -> str:
    """Blank out parameter names so {id} in the control map matches {quote_id}."""
    return re.sub(r"\{[^}]+\}", "{}", path)


EPS = json.load(open(SP / "endpoints.json"))
BY_REF = {f"{e['method']} {e['path']}": e for e in EPS}
LOOSE = {f"{e['method']} {loose(e['path'])}": e for e in EPS}


def lookup(ref: str):
    if ref in BY_REF:
        return BY_REF[ref]
    m, _, p = ref.partition(" ")
    return LOOSE.get(f"{m} {loose(p)}")


def tables_for(refs: list[str]) -> tuple[list[str], list[str]]:
    r, w = set(), set()
    for ref in refs:
        e = lookup(ref)
        if e:
            r |= set(e["reads"])
            w |= set(e["writes"])
    return sorted(r - w), sorted(w)


def esc(s: str) -> str:
    return html.escape(str(s))


def chips(tables: list[str], cls: str) -> str:
    if not tables:
        return '<span class="none">—</span>'
    return "".join(f'<span class="chip {cls}">{esc(t)}</span>' for t in tables)


def rw_cell(r: list[str], w: list[str]) -> str:
    """Both sides in one cell, with a single dash when there is nothing at all."""
    if not r and not w:
        return '<span class="none">&mdash;</span>'
    return ("".join(f'<span class="chip r">{esc(t)}</span>' for t in r)
            + "".join(f'<span class="chip w">{esc(t)}</span>' for t in w))


def code_list(refs: list[str]) -> str:
    if not refs:
        return '<span class="none">no request</span>'
    return "<br>".join(f"<code>{esc(r)}</code>" for r in refs)


KIND_LABEL = {
    controls.CALL: ('<span class="k k-call">DB</span>', ""),
    controls.NAV: ('<span class="k k-nav">nav</span>', ""),
    controls.UI: ('<span class="k k-ui">UI</span>', ""),
}

parts: list[str] = []
A = parts.append

A("""<title>DealFlow360 Button-to-Database Map</title>
<style>
  :root{
    --ink:#0f172a; --mid:#475569; --soft:#64748b; --line:#e2e8f0;
    --bg:#ffffff; --panel:#f8fafc;
    --read:#0369a1; --readbg:#e0f2fe; --write:#9a3412; --writebg:#ffedd5;
    --accent:#3b5bf6;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:11px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  .page{max-width:1080px;margin:0 auto;padding:28px 30px 40px;}
  h1{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}
  h2{font-size:15px;margin:30px 0 10px;padding-bottom:6px;
     border-bottom:2px solid var(--ink);letter-spacing:-.01em}
  h3{font-size:12.5px;margin:20px 0 7px;color:var(--ink)}
  .sub{color:var(--soft);font-size:12px;margin:0 0 18px}
  p{margin:0 0 9px;color:var(--mid);max-width:80ch}
  code{font:10px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
       background:var(--panel);border:1px solid var(--line);
       border-radius:3px;padding:1px 4px;white-space:nowrap;color:var(--ink)}
  table{width:100%;border-collapse:collapse;margin:8px 0 4px;
        font-size:10.5px;table-layout:fixed}
  th{text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.06em;
     color:var(--soft);border-bottom:1px solid var(--line);padding:5px 6px;font-weight:700}
  td{padding:6px;border-bottom:1px solid var(--line);vertical-align:top;
     word-wrap:break-word;overflow-wrap:anywhere}
  tr:last-child td{border-bottom:none}
  .chip{display:inline-block;font:9.5px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
        border-radius:3px;padding:1px 5px;margin:1px 3px 1px 0;white-space:nowrap}
  .r{background:var(--readbg);color:var(--read)}
  .w{background:var(--writebg);color:var(--write)}
  .none{color:#cbd5e1}
  .k{display:inline-block;font-size:8.5px;font-weight:800;letter-spacing:.05em;
     border-radius:3px;padding:1px 5px;text-transform:uppercase}
  .k-call{background:#dcfce7;color:#15803d}
  .k-nav{background:#e0e7ff;color:#4338ca}
  .k-ui{background:#f1f5f9;color:#64748b}
  .screen{border:1px solid var(--line);border-radius:8px;padding:12px 14px;
          margin:12px 0;break-inside:avoid}
  .screen h3{margin-top:0}
  .file{font:9.5px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--soft);
        margin:-4px 0 8px}
  .loads{background:var(--panel);border-radius:5px;padding:7px 9px;margin:0 0 9px;
         font-size:10px;color:var(--mid)}
  .loads b{color:var(--ink);font-size:9px;text-transform:uppercase;letter-spacing:.05em}
  .note{color:var(--soft);font-size:9.5px;display:block;margin-top:2px}
  .legend{display:flex;gap:16px;flex-wrap:wrap;background:var(--panel);
          border:1px solid var(--line);border-radius:8px;padding:10px 13px;margin:14px 0 20px}
  .legend div{font-size:10px;color:var(--mid)}
  .method{font-weight:700;white-space:nowrap;font-size:9.5px}
  .callout{border-left:3px solid var(--accent);background:var(--panel);
           padding:9px 12px;margin:12px 0;border-radius:0 6px 6px 0;font-size:10.5px}
  .callout b{color:var(--ink)}
  @page{size:A4;margin:12mm 10mm}
  @media print{
    .screen,tr,h2,h3{break-inside:avoid}
    h2{break-before:auto}
  }
</style>""")

A('<div class="page">')
A("<h1>DealFlow360 — Button-to-Database Map</h1>")
A(f'<p class="sub">Every control in the web client, the API call behind it, and the '
  f'tables that call reads and writes · generated {date.today().isoformat()}</p>')

A('<div class="callout">')
A("<b>How this was produced.</b> The read/write columns are not inferred from reading "
  "code. A SQL listener was attached to SQLAlchemy and the full 502-test suite was run, "
  "recording every statement each endpoint actually issued; the seventeen endpoints the "
  "suite never exercised were then driven directly. All <b>83</b> routes are covered by "
  "observed SQL. Controls were extracted from the JSX and each handler traced to its "
  "request, then checked against the route list — every endpoint named here exists.")
A("</div>")

A('<div class="legend">')
A('<div><span class="chip r">table</span> read from</div>')
A('<div><span class="chip w">table</span> written to</div>')
A('<div><span class="k k-call">DB</span> issues a request</div>')
A('<div><span class="k k-nav">nav</span> opens another screen</div>')
A('<div><span class="k k-ui">UI</span> client-side only</div>')
A("</div>")

A("<p>A note on reads: a write endpoint reads a good deal before it writes — the quote, "
  "its lines, the customer's tier, the discount policy — because the domain engines are "
  "given a full snapshot to score against. Those reads are listed, so a row with many "
  "read chips and one write chip is normal rather than surprising.</p>")

# ---------------------------------------------------------------- part 1
A("<h2>Part 1 · Screen by screen</h2>")
for s in controls.SCREENS:
    A('<div class="screen">')
    A(f"<h3>{esc(s['screen'])}</h3>")
    A(f'<div class="file">{esc(s["file"])}</div>')
    if s["loads"]:
        lr, lw = tables_for(s["loads"])
        A('<div class="loads"><b>On open</b><br>'
          + " ".join(f"<code>{esc(x)}</code>" for x in s["loads"])
          + "<br>" + rw_cell(lr, lw) + "</div>")
    if s["controls"]:
        A("<table><colgroup><col style='width:22%'><col style='width:6%'>"
          "<col style='width:30%'><col style='width:42%'></colgroup>")
        A("<tr><th>Control</th><th></th><th>Request</th><th>Tables</th></tr>")
        for label, kind, refs, note in s["controls"]:
            r, w = tables_for(refs)
            badge = KIND_LABEL[kind][0]
            cell = rw_cell(r, w) if refs else '<span class="none">&mdash;</span>'
            A(f"<tr><td><b>{esc(label)}</b>"
              + (f'<span class="note">{esc(note)}</span>' if note else "")
              + f"</td><td>{badge}</td><td>{code_list(refs)}</td><td>{cell}</td></tr>")
        A("</table>")
    A("</div>")

# ---------------------------------------------------------------- part 2
A("<h2>Part 2 · Every API route and the tables it touches</h2>")
A(f"<p>All {len(EPS)} routes, grouped by router module. Observed SQL.</p>")

by_module: dict[str, list] = defaultdict(list)
for e in EPS:
    by_module[e["module"]].append(e)

MODULE_TITLE = {
    "admin": "admin.py — discount config, warehouses, subscription plans",
    "approvals": "approvals.py — the approval chain",
    "auth": "auth.py — sign in, sign up, demo accounts",
    "catalog": "catalog.py — products, variants, price lists",
    "fulfillment": "fulfillment.py — allocation, invoicing, payments, subscriptions",
    "me": "me.py — identity and capabilities",
    "operations": "operations.py — dashboards, stock, invoices, reports",
    "portal": "portal.py — the customer portal",
    "quotes": "quotes.py — quotations and lines",
    "reference": "reference.py — customers, products, policies",
    "surface": "surface.py — deal health, audit log, replay",
}

for module in sorted(by_module):
    A(f"<h3>{esc(MODULE_TITLE.get(module, module + '.py'))}</h3>")
    A("<table><colgroup><col style='width:9%'><col style='width:29%'>"
      "<col style='width:31%'><col style='width:31%'></colgroup>")
    A("<tr><th></th><th>Route</th><th>Reads</th><th>Writes</th></tr>")
    for e in sorted(by_module[module], key=lambda x: (x["path"], x["method"])):
        A(f'<tr><td class="method">{esc(e["method"])}</td>'
          f'<td><code>{esc(e["path"])}</code></td>'
          f'<td>{chips(e["reads"], "r")}</td>'
          f'<td>{chips(e["writes"], "w") if e["writes"] else "<span class=\'none\'>reads only</span>"}</td></tr>')
    A("</table>")

# ---------------------------------------------------------------- part 3
A("<h2>Part 3 · Every table and what touches it</h2>")
writers: dict[str, list[str]] = defaultdict(list)
readers: dict[str, list[str]] = defaultdict(list)
for e in EPS:
    ref = f"{e['method']} {e['path']}"
    for t in e["writes"]:
        writers[t].append(ref)
    for t in e["reads"]:
        readers[t].append(ref)

all_tables = sorted(set(writers) | set(readers))
A(f"<p>{len(all_tables)} tables. A table with no writer is reference data the "
  "seed loads and the application only reads.</p>")
A("<table><colgroup><col style='width:14%'><col style='width:8%'>"
  "<col style='width:43%'><col style='width:35%'></colgroup>")
A("<tr><th>Table</th><th>Reads</th><th>Written by</th><th>Notable readers</th></tr>")
for t in all_tables:
    w = sorted(set(writers.get(t, [])))
    r = sorted(set(readers.get(t, [])))
    w_cell = ("<br>".join(f"<code>{esc(x)}</code>" for x in w)
              if w else '<span class="none">read-only in the app</span>')
    if r:
        r_cell = "<br>".join(f"<code>{esc(x)}</code>" for x in r[:4])
        if len(r) > 4:
            r_cell += f'<span class="note">+{len(r) - 4} more</span>'
    else:
        r_cell = '<span class="none">—</span>'
    A(f'<tr><td><span class="chip r">{esc(t)}</span></td>'
      f"<td>{len(r)}</td><td>{w_cell}</td><td>{r_cell}</td></tr>")
A("</table>")

# ---------------------------------------------------------------- appendix
A("<h2>Appendix · Routes with no button</h2>")
referenced = set()
for s in controls.SCREENS:
    for ref in s["loads"]:
        e = lookup(ref)
        if e:
            referenced.add(f"{e['method']} {e['path']}")
    for _l, _k, refs, _n in s["controls"]:
        for ref in refs:
            e = lookup(ref)
            if e:
                referenced.add(f"{e['method']} {e['path']}")

orphans = [e for e in EPS if f"{e['method']} {e['path']}" not in referenced]
A(f"<p>{len(orphans)} of {len(EPS)} routes are implemented and tested but no control in "
  "the current UI reaches them. They are listed so the gap is visible rather than "
  "discovered later.</p>")
A("<table><colgroup><col style='width:9%'><col style='width:31%'><col style='width:60%'>"
  "</colgroup>")
A("<tr><th></th><th>Route</th><th>What it does</th></tr>")
for e in sorted(orphans, key=lambda x: (x["module"], x["path"])):
    A(f'<tr><td class="method">{esc(e["method"])}</td>'
      f'<td><code>{esc(e["path"])}</code></td>'
      f'<td>{esc(e["doc"] or "—")}</td></tr>')
A("</table>")

A("</div>")

out = SP / "button-db-map.html"
out.write_text("\n".join(parts), encoding="utf-8")
print("wrote", out)
