#!/usr/bin/env python3
"""Pull Nelson Mandela Cup weekly category totals from public Yahoo pages.

No Yahoo login and no API key: the league is public. Writes data.json and
index.html in this folder. Safe to run on a schedule or by hand.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

LEAGUE = "2670"
BASE = f"https://hockey.fantasysports.yahoo.com/hockey/{LEAGUE}"
UA = "Mozilla/5.0 (compatible; MandelaCupTable/1.0)"
ROOT = Path(__file__).resolve().parent
CATS = ["G", "A", "P", "+/-", "PIM", "PPP", "SOG", "FW", "HIT", "BLK", "W", "GAA", "SV", "SHO"]
# Yahoo column order on the matchup totals table. GA* is shown but not scored.
YAHOO_CATS = ["G", "A", "P", "+/-", "PIM", "PPP", "SOG", "FW", "HIT", "BLK", "W", "GA*", "GAA", "SV", "SHO"]


class Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.cur: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.cur = []
        elif self.cur is not None and tag == "tr":
            self.row = []
        elif self.row is not None and tag in ("td", "th"):
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            text = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            if text:
                self.row.append(text)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.cur.append(self.row)
            self.row = None
        elif tag == "table" and self.cur is not None:
            self.tables.append(self.cur)
            self.cur = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "replace")


def current_week(home: str) -> int:
    m = re.search(r"Week (\d+) Matchups", home)
    if not m:
        raise RuntimeError("Не нашёл текущую неделю на странице лиги")
    return int(m.group(1))


def totals_table(html: str) -> list[list[str]] | None:
    parser = Tables()
    parser.feed(html)
    for table in parser.tables:
        header = table[0] if table else []
        if "Team" in header and "SHO" in header and "GAA" in header:
            return table
    return None


def num(value: str):
    if value in ("-", "–", ""):
        return None
    value = value.replace(",", ".")
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return None


def scrape_week(week: int) -> dict:
    teams: dict[str, dict] = {}
    pairs: list[list[str]] = []
    seen_names: set[str] = set()
    for team_id in range(1, 15):
        if len(teams) >= 14:
            break
        html = fetch(f"{BASE}/matchup?date=totals&week={week}&mid1={team_id}")
        table = totals_table(html)
        time.sleep(0.35)
        if not table:
            continue
        names = []
        for row in table[1:]:
            if len(row) < 16:
                continue
            name = row[0]
            cats_won = num(row[-1]) if len(row) > 16 else None
            stats = {cat: num(row[i + 1]) for i, cat in enumerate(YAHOO_CATS)}
            teams[name] = {"name": name, "stats": stats, "cats": cats_won}
            names.append(name)
        if len(names) == 2 and names[0] not in seen_names:
            pairs.append(names)
            seen_names.update(names)
    return {"week": week, "teams": list(teams.values()), "pairs": pairs}


def load_previous() -> dict:
    path = ROOT / "data.json"
    if not path.exists():
        return {"weeks": {}}
    return json.loads(path.read_text())


def render(payload: dict) -> str:
    updated = payload["updated"]
    current = payload["current_week"]
    weeks_json = json.dumps(payload["weeks"], ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nelson Mandela Cup — категорийная таблица</title>
<style>
  :root {{ --ink:#1c2421; --muted:#5e6b66; --line:#d7e0db; --bg:#f4f6f4; --green:#1f7a45; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; color:var(--ink); background:var(--bg); }}
  header {{ background:#16352a; color:#f3f7f4; padding:22px 28px 18px; }}
  header h1 {{ margin:0 0 4px; font-size:22px; font-weight:650; }}
  header p {{ margin:0; color:#c5d5cc; font-size:13px; }}
  main {{ padding:18px 22px 40px; max-width:1280px; margin:0 auto; }}
  .bar {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:4px 0 14px; }}
  button, select {{ font:inherit; font-size:14px; border:1px solid var(--line); background:#fff; color:var(--ink); border-radius:8px; padding:7px 12px; cursor:pointer; }}
  button.active {{ background:#16352a; color:#fff; border-color:#16352a; }}
  .note, .tag {{ color:var(--muted); font-size:13px; }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:12px; overflow:auto; margin-bottom:18px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13.5px; font-variant-numeric:tabular-nums; }}
  th, td {{ padding:7px 8px; text-align:right; white-space:nowrap; border-bottom:1px solid #eef2ef; }}
  th {{ background:#f7faf8; font-weight:650; cursor:pointer; position:sticky; top:0; }}
  th:first-child, td:first-child {{ text-align:left; position:sticky; left:0; background:#fff; }}
  th:first-child {{ background:#f7faf8; }}
  h2 {{ font-size:16px; margin:8px 0 10px; }}
  .statrow {{ display:grid; grid-template-columns:92px 1fr 70px 1fr 92px; align-items:center; gap:8px; padding:6px 4px; border-bottom:1px solid #eef2ef; }}
  .statrow .name {{ text-align:center; font-weight:650; }}
  .barwrap {{ height:16px; background:#eef3f0; border-radius:4px; overflow:hidden; }}
  .barwrap.right {{ display:flex; justify-content:flex-end; }}
  .fill {{ height:100%; background:#8fbfa4; }}
  .fill.win {{ background:#1f7a45; }}
  .val {{ font-variant-numeric:tabular-nums; font-weight:650; }}
  .val.win {{ color:var(--green); }}
  .val.lose {{ color:#6d7672; font-weight:500; }}
  .summary b {{ font-size:28px; }}
  footer {{ color:var(--muted); font-size:12px; }}
</style>
</head>
<body>
<header>
  <h1>Nelson Mandela Cup — категорийные итоги</h1>
  <p>Лига Yahoo {LEAGUE}. Обновлено {updated}. Зеленее — лучше среди 14 команд, GAA наоборот.</p>
</header>
<main>
  <div class="bar" id="weeks"></div>
  <p class="note" id="note"></p>
  <div class="card"><table id="grid"></table></div>
  <h2>Сравнение 1 на 1</h2>
  <div class="bar">
    <select id="a"></select><span>против</span><select id="b"></select>
    <button id="opp">Соперник этой недели</button>
  </div>
  <div class="card" style="padding:14px 16px 8px;">
    <div class="summary" id="summary"></div>
    <div id="compare"></div>
  </div>
  <footer>Страница сама Yahoo не дёргает: браузеру это запрещено. Цифры подтягивает скрипт по расписанию или по кнопке Run workflow. CAT — категории против соперника этой недели, не против команды, выбранной снизу.</footer>
</main>
<script>
const CATS = {json.dumps(CATS)};
const LOWER = new Set(["GAA"]);
const CURRENT = {current};
const WEEKS = {weeks_json};
let week = String(CURRENT);
let sortKey = "name", sortDir = 1;
function fmt(v) {{
  if (v === null || v === undefined) return "–";
  if (typeof v === "number" && !Number.isInteger(v)) return v.toFixed(2).replace(".", ",");
  return String(v);
}}
function better(cat, a, b) {{
  if (a === null || b === null || a === b) return 0;
  return (LOWER.has(cat) ? a < b : a > b) ? 1 : -1;
}}
function shade(cat, value, values) {{
  const nums = values.filter(v => v !== null && v !== undefined);
  if (value === null || nums.length < 2) return "";
  const sorted = [...nums].sort((a,b) => a-b);
  let rank = sorted.indexOf(value) / (sorted.length - 1);
  if (!LOWER.has(cat)) rank = 1 - rank;
  const light = Math.round(232 - rank * 150);
  return `background:rgb(${{light}},${{Math.round(236-rank*40)}},${{Math.round(226-rank*150)}})`;
}}
function teamByName(name) {{ return WEEKS[week].teams.find(t => t.name === name); }}
function render() {{
  const data = WEEKS[week];
  document.getElementById("weeks").innerHTML = Object.keys(WEEKS).sort((a,b)=>a-b).map(w =>
    `<button data-w="${{w}}" class="${{w===week?"active":""}}">Неделя ${{w}}${{w==String(CURRENT)?" · сейчас":""}}</button>`).join("");
  document.querySelectorAll("#weeks button").forEach(b => b.onclick = () => {{ week = b.dataset.w; render(); renderCompare(); }});
  const empty = data.teams.every(t => t.stats.G === null);
  document.getElementById("note").textContent = empty
    ? "Неделя открыта, Yahoo ещё не насчитал статы."
    : "Итог или текущий срез матчапов. Клик по заголовку сортирует.";
  const rows = [...data.teams].sort((a,b) => {{
    const av = sortKey === "name" ? a.name : a.stats[sortKey] ?? a.cats;
    const bv = sortKey === "name" ? b.name : b.stats[sortKey] ?? b.cats;
    if (av === null) return 1; if (bv === null) return -1;
    return sortDir * (typeof av === "string" ? av.localeCompare(bv) : av - bv);
  }});
  const head = `<tr><th data-k="name">Team</th>${{CATS.map(c=>`<th data-k="${{c}}">${{c}}</th>`).join("")}}<th data-k="cats">CAT</th></tr>`;
  document.getElementById("grid").innerHTML = head + rows.map(r => `<tr><td>${{r.name}}</td>${{
    CATS.map(c => `<td><span style="${{shade(c, r.stats[c], data.teams.map(t => t.stats[c]))}}">${{fmt(r.stats[c])}}</span></td>`).join("")
  }}<td>${{r.cats ?? "–"}}</td></tr>`).join("");
  document.querySelectorAll("#grid th").forEach(th => th.onclick = () => {{
    sortDir = sortKey === th.dataset.k ? -sortDir : (th.dataset.k === "name" ? 1 : -1);
    sortKey = th.dataset.k; render();
  }});
  const names = data.teams.map(t => t.name).sort();
  for (const id of ["a","b"]) {{
    const sel = document.getElementById(id);
    const prev = sel.value;
    sel.innerHTML = names.map(n => `<option>${{n}}</option>`).join("");
    if (names.includes(prev)) sel.value = prev;
  }}
  if (!document.getElementById("b").value || document.getElementById("a").value === document.getElementById("b").value) {{
    const pair = data.pairs[0] || names.slice(0,2);
    document.getElementById("a").value = pair[0];
    document.getElementById("b").value = pair[1] || names[1];
  }}
}}
function renderCompare() {{
  const A = teamByName(document.getElementById("a").value);
  const B = teamByName(document.getElementById("b").value);
  if (!A || !B) return;
  let aw=0,bw=0,ties=0;
  document.getElementById("compare").innerHTML = CATS.map(c => {{
    const d = better(c, A.stats[c], B.stats[c]);
    if (d>0) aw++; else if (d<0) bw++; else if (A.stats[c] !== null) ties++;
    const max = Math.max(Math.abs(A.stats[c]||0), Math.abs(B.stats[c]||0)) || 1;
    return `<div class="statrow">
      <div class="val ${{d>0?"win":"lose"}}">${{fmt(A.stats[c])}}</div>
      <div class="barwrap right"><div class="fill ${{d>0?"win":""}}" style="width:${{Math.abs(A.stats[c]||0)/max*100}}%"></div></div>
      <div class="name">${{c}}${{LOWER.has(c)?" ↓":""}}</div>
      <div class="barwrap"><div class="fill ${{d<0?"win":""}}" style="width:${{Math.abs(B.stats[c]||0)/max*100}}%"></div></div>
      <div class="val ${{d<0?"win":"lose"}}">${{fmt(B.stats[c])}}</div>
    </div>`;
  }}).join("");
  document.getElementById("summary").innerHTML = A.stats.G === null
    ? `<span class="tag">Статов за эту неделю ещё нет.</span>`
    : `<b>${{aw}}–${{bw}}${{ties?`–${{ties}}`:""}}</b><div class="tag">${{A.name}} против ${{B.name}}</div>`;
}}
document.getElementById("a").onchange = renderCompare;
document.getElementById("b").onchange = renderCompare;
document.getElementById("opp").onclick = () => {{
  const name = document.getElementById("a").value;
  const pair = (WEEKS[week].pairs || []).find(p => p.includes(name));
  if (pair) document.getElementById("b").value = pair[0] === name ? pair[1] : pair[0];
  renderCompare();
}};
render(); renderCompare();
</script>
</body>
</html>
"""


def main() -> None:
    home = fetch(BASE)
    week_now = current_week(home)
    previous = load_previous()
    weeks = previous.get("weeks", {})
    # Current week always, previous week in case of stat corrections, missing weeks once.
    wanted = set(range(1, week_now + 1))
    refresh = {week_now, max(1, week_now - 1)}
    for week in sorted(wanted):
        key = str(week)
        if week in refresh or key not in weeks or len(weeks[key].get("teams", [])) < 14:
            print(f"week {week}")
            weeks[key] = scrape_week(week)
    payload = {
        "league": LEAGUE,
        "current_week": week_now,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "weeks": weeks,
    }
    (ROOT / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    (ROOT / "index.html").write_text(render(payload))
    print(f"updated week {week_now}, {sum(len(w['teams']) for w in weeks.values())} team-rows")


if __name__ == "__main__":
    main()
