"""Marketing HUD: aggregate home + a page per active account.

Each page: date-adjustable metric tiles on top, that entity's own AI story below,
plus change history and campaign detail. Only accounts with recent spend are shown.
Served at marketingdashboard.theconcreteprotector.com via the skald-box tunnel.
Run: python dashboard.py  (0.0.0.0:8090)
"""
import datetime as dt
import json
import os
import re

import markdown as md
from flask import Flask, request, render_template_string, abort, jsonify

import db
import summarize

app = Flask(__name__)

INGEST_SECRET = os.environ.get("INGEST_SECRET", "tcp-ads-ingest")


def _text_from_raw(raw):
    """Extract the plain-text body from a raw MIME email."""
    import email
    from email import policy
    try:
        msg = email.message_from_string(raw, policy=policy.default)
        part = msg.get_body(preferencelist=("plain",))
        if part:
            return (part.get_content() or "").strip()
        part = msg.get_body(preferencelist=("html",))
        if part:
            import re
            return re.sub(r"<[^>]+>", "", part.get_content() or "").strip()
    except Exception:
        pass
    return ""


@app.route("/ingest/email", methods=["POST"])
def ingest_email():
    """Receives a specialist's emailed report (Cloudflare Email Worker CCs here)."""
    if request.headers.get("X-Ingest-Secret") != INGEST_SECRET:
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    subject = data.get("subject", "")
    author = data.get("from", "")
    body = (data.get("text") or data.get("body") or "").strip()
    if not body and data.get("raw"):
        body = _text_from_raw(data["raw"])
    if not body:
        return jsonify({"ok": False, "error": "empty body"}), 400
    # Date from subject "Daily Update MM/DD" else today.
    m = re.search(r"(\d{1,2})/(\d{1,2})", subject)
    if m:
        mo, dy = int(m.group(1)), int(m.group(2))
        yr = dt.date.today().year
        date = dt.date(yr, mo, dy).isoformat()
    else:
        date = dt.date.today().isoformat()
    con = db.connect()
    con.execute("INSERT OR REPLACE INTO specialist_reports(date, author, subject, body, source, received_at) "
                "VALUES(?,?,?,?,?,?)", (date, author, subject, body, "email-cc", dt.datetime.now().isoformat()))
    con.commit()
    return jsonify({"ok": True, "date": date})

WINDOWS = [("1", "Yesterday"), ("7", "7 days"), ("14", "14 days"), ("30", "30 days")]

PAGE = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>TCP Marketing HUD</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
 :root{--bg:#0b0f14;--panel:#141b24;--line:#26313f;--txt:#e8edf2;--mut:#8ba0b4;--accent:#31c48d;--warn:#f6a609;--bad:#ef5350;--good:#31c48d}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,Segoe UI,Roboto,sans-serif}
 a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
 header{padding:16px 28px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:16px;flex-wrap:wrap}
 header .brand{font-size:18px;font-weight:600;letter-spacing:.3px;color:var(--txt)}
 header .date{color:var(--mut);font-size:13px} header nav{margin-left:auto;display:flex;gap:16px;flex-wrap:wrap}
 header nav a{color:var(--mut);font-size:14px}
 main{max-width:1180px;margin:0 auto;padding:22px 28px}
 h1{font-size:20px;margin:0 0 4px} .sub{color:var(--mut);font-size:14px;margin:0 0 18px}
 .range{display:flex;gap:8px;margin:0 0 18px}
 .range a{padding:5px 12px;border:1px solid var(--line);border-radius:20px;color:var(--mut);font-size:13px}
 .range a.on{background:var(--accent);color:#08110c;border-color:var(--accent);font-weight:600}
 .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-bottom:22px}
 .tile{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
 .tile .l{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
 .tile .v{font-size:25px;font-weight:600;margin-top:4px} .tile .d{font-size:12px;margin-top:2px}
 .up{color:var(--good)} .down{color:var(--bad)}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:18px}
 .card h2{font-size:15px;margin:0 0 12px;font-weight:600}
 .grid{display:grid;grid-template-columns:1.25fr 1fr;gap:18px}
 @media(max-width:820px){.grid{grid-template-columns:1fr}}
 .story :is(h1,h2,h3){font-size:15px;color:var(--accent);margin:12px 0 6px}
 .story p,.story li{font-size:14px;line-height:1.6;color:#d3dde6} .story strong{color:#fff}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
 th{color:var(--mut);font-weight:500;text-transform:uppercase;font-size:11px;letter-spacing:.5px}
 .num{text-align:right;font-variant-numeric:tabular-nums}
 .badge{display:inline-block;padding:1px 8px;border-radius:20px;font-size:11px;margin-left:6px}
 .b-meta{background:rgba(49,120,196,.18);color:#7fb2ee} .b-google{background:rgba(246,166,9,.16);color:var(--warn)}
 canvas{max-height:210px}
</style></head><body>
<header><span class="brand">TCP MARKETING HUD</span><span class="date">{{ today }}</span>
<nav><a href="/">Home</a>{{ nav|safe }}</nav></header>
<main>{{ body|safe }}</main></body>
<script>{{ script|safe }}</script></html>
"""


def _days():
    d = request.args.get("days", "7")
    return d if d in {w[0] for w in WINDOWS} else "7"


def _range(con, days):
    last = con.execute("SELECT MAX(date) d FROM metrics").fetchone()["d"] or dt.date.today().isoformat()
    end = dt.date.fromisoformat(last)
    start = end - dt.timedelta(days=int(days) - 1)
    return start.isoformat(), end.isoformat()


def _agg(con, start, end, account=None):
    q = ("SELECT COALESCE(SUM(spend),0) s, COALESCE(SUM(leads),0) l, COALESCE(SUM(clicks),0) c, "
         "COALESCE(SUM(impressions),0) i, COALESCE(SUM(revenue),0) rev FROM metrics WHERE date>=? AND date<=?")
    p = [start, end]
    if account:
        q += " AND account=?"
        p.append(account)
    r = con.execute(q, p).fetchone()
    s, l, c, i, rev = r["s"], r["l"], r["c"], r["i"], r["rev"]
    return {
        "spend": s, "leads": l, "clicks": c, "impr": i, "revenue": rev,
        "cpl": (s / l) if l else 0,
        "cpc": (s / c) if c else 0,
        "cpm": (s / i * 1000) if i else 0,
        "ctr": (c / i * 100) if i else 0,
        "cvr": (l / c * 100) if c else 0,      # conversion rate: results / clicks
        "roas": (rev / s) if s else 0,
        "cpa": (s / l) if l else 0,
    }


def _is_ecom(con, account):
    r = con.execute("SELECT COALESCE(SUM(revenue),0) rev FROM metrics WHERE account=?", (account,)).fetchone()
    return (r["rev"] or 0) > 0


def _prev_range(start, end):
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    span = (e - s).days + 1
    return (s - dt.timedelta(days=span)).isoformat(), (s - dt.timedelta(days=1)).isoformat()


def _delta(cur, prv, inverse=False):
    if not prv:
        return ""
    pct = (cur - prv) / prv * 100
    good = (pct < 0) if inverse else (pct > 0)
    cls = "up" if good else "down"
    return f'<span class="{cls}">{"+" if pct>=0 else ""}{pct:.0f}% vs prior</span>'


def _tile(label, value, cur, prv, inverse=False):
    return (f'<div class="tile"><div class="l">{label}</div><div class="v">{value}</div>'
            f'<div class="d">{_delta(cur,prv,inverse)}</div></div>')


def _tiles(con, start, end, account=None):
    m = _agg(con, start, end, account)
    ps, pe = _prev_range(start, end)
    p = _agg(con, ps, pe, account)
    ecom = account and _is_ecom(con, account)
    t = ['<div class="tiles">']
    t.append(_tile("Spend", f"${m['spend']:,.0f}", m['spend'], p['spend']))
    if ecom:
        t.append(_tile("Revenue", f"${m['revenue']:,.0f}", m['revenue'], p['revenue']))
        t.append(_tile("ROAS", f"{m['roas']:.1f}x", m['roas'], p['roas']))
        t.append(_tile("Purchases", f"{m['leads']:,.0f}", m['leads'], p['leads']))
        t.append(_tile("Cost / Purchase", f"${m['cpa']:,.0f}", m['cpa'], p['cpa'], inverse=True))
    else:
        t.append(_tile("Lead volume", f"{m['leads']:,.0f}", m['leads'], p['leads']))
        t.append(_tile("CPL", f"${m['cpl']:,.0f}", m['cpl'], p['cpl'], inverse=True))
        t.append(_tile("Conv. rate", f"{m['cvr']:.1f}%", m['cvr'], p['cvr']))
    t.append(_tile("CPC", f"${m['cpc']:.2f}", m['cpc'], p['cpc'], inverse=True))
    t.append(_tile("CPM", f"${m['cpm']:.2f}", m['cpm'], p['cpm'], inverse=True))
    t.append(_tile("CTR", f"{m['ctr']:.1f}%", m['ctr'], p['ctr']))
    t.append('</div>')
    return "".join(t)


def _range_bar(base, days):
    sep = "&" if "?" in base else "?"
    links = "".join(
        f'<a class="{"on" if d==days else ""}" href="{base}{sep}days={d}">{label}</a>'
        for d, label in WINDOWS)
    return f'<div class="range">{links}</div>'


def _nav(con):
    return "".join(
        f'<a href="/account/{a["id"]}">{a["name"]}</a>'
        for a in summarize.active_accounts(con))


def render(con, body, script=""):
    return render_template_string(
        PAGE, body=body, script=script, nav=_nav(con),
        today=dt.date.today().strftime("%A, %b %-d, %Y"))


@app.route("/")
def home():
    con = db.connect()
    days = _days()
    start, end = _range(con, days)
    accts = summarize.active_accounts(con)

    rows = ""
    for a in accts:
        m = _agg(con, start, end, a["id"])
        plat = f'<span class="badge b-{a["platform"]}">{a["platform"]}</span>'
        if _is_ecom(con, a["id"]):
            result = f'<td class="num">${m["revenue"]:,.0f} rev</td><td class="num">{m["roas"]:.1f}x ROAS</td>'
        else:
            result = f'<td class="num">{m["leads"]:,.0f} leads</td><td class="num">${m["cpl"]:,.0f} CPL</td>'
        rows += (f'<tr><td><a href="/account/{a["id"]}?days={days}">{a["name"]}</a>{plat}</td>'
                 f'<td class="num">${m["spend"]:,.0f}</td>{result}<td class="num">{m["ctr"]:.1f}%</td></tr>')

    summ = con.execute("SELECT * FROM summaries ORDER BY date DESC LIMIT 1").fetchone()
    story = md.markdown(summ["exec_summary"]) if summ else "<p style='color:var(--mut)'>Portfolio brief runs after tonight's collection.</p>"

    reps = con.execute("SELECT * FROM specialist_reports ORDER BY date DESC").fetchall()
    feed = ""
    for rp in reps:
        try:
            lbl = dt.date.fromisoformat(rp["date"]).strftime("%A, %b %-d, %Y")
        except Exception:
            lbl = rp["date"]
        feed += (f'<div class="card"><h2>{lbl} — {rp["author"] or "Simi"}</h2>'
                 f'<div class="story">{md.markdown(rp["body"])}</div></div>')
    if not feed:
        feed = '<div class="card"><p style="color:var(--mut)">Specialist reports will appear here as they arrive.</p></div>'

    body = (f'<h1>Portfolio</h1><p class="sub">{len(accts)} active accounts · {start} to {end}</p>'
            + _range_bar("/", days)
            + _tiles(con, start, end)
            + '<div class="grid"><div>'
            + '<div class="card"><h2>Active accounts</h2><table>'
            + '<tr><th>Account</th><th class="num">Spend</th><th class="num">Results</th><th class="num">Efficiency</th><th class="num">CTR</th></tr>'
            + rows + '</table></div>'
            + '<div class="card"><h2>Spend &amp; leads</h2><canvas id="trend"></canvas></div></div>'
            + f'<div><div class="card"><h2>Portfolio brief</h2><div class="story">{story}</div></div></div></div>'
            + '<h1 style="margin-top:28px">Specialist reports</h1>'
            + '<p class="sub">Daily updates from the ads specialist, newest first.</p>'
            + feed)
    return render(con, body, _trend_script(con, start, end))


def _trend_script(con, start, end, account=None):
    q = "SELECT date, ROUND(SUM(spend),2) s, ROUND(SUM(leads),0) l FROM metrics WHERE date>=? AND date<=?"
    p = [start, end]
    if account:
        q += " AND account=?"
        p.append(account)
    q += " GROUP BY date ORDER BY date"
    rows = con.execute(q, p).fetchall()
    labels = [r["date"][5:] for r in rows]
    spend = [r["s"] for r in rows]
    leads = [r["l"] for r in rows]
    return f"""
    const ctx=document.getElementById('trend'); if(ctx){{new Chart(ctx,{{
      data:{{labels:{json.dumps(labels)},datasets:[
        {{type:'bar',label:'Spend $',data:{json.dumps(spend)},backgroundColor:'#2b6cb0',yAxisID:'y'}},
        {{type:'line',label:'Leads',data:{json.dumps(leads)},borderColor:'#31c48d',backgroundColor:'#31c48d',yAxisID:'y1',tension:.3}}]}},
      options:{{plugins:{{legend:{{labels:{{color:'#8ba0b4'}}}}}},scales:{{
        x:{{ticks:{{color:'#8ba0b4'}},grid:{{color:'#141b24'}}}},
        y:{{position:'left',ticks:{{color:'#8ba0b4'}},grid:{{color:'#141b24'}}}},
        y1:{{position:'right',ticks:{{color:'#8ba0b4'}},grid:{{display:false}}}}}}}}}});}}"""


@app.route("/account/<path:acct>")
def account(acct):
    con = db.connect()
    a = con.execute("SELECT * FROM accounts WHERE id=?", (acct,)).fetchone()
    if not a:
        abort(404)
    days = _days()
    start, end = _range(con, days)

    cur = con.execute("SELECT story FROM account_summaries WHERE account=? AND date!='history' "
                      "ORDER BY date DESC LIMIT 1", (acct,)).fetchone()
    hist = con.execute("SELECT story FROM account_summaries WHERE account=? AND date='history'", (acct,)).fetchone()
    cur_html = md.markdown(cur["story"]) if cur else "<p style='color:var(--mut)'>Generates after tonight's run.</p>"
    hist_html = md.markdown(hist["story"]) if hist else "<p style='color:var(--mut)'>Narrative builds as changes accumulate.</p>"

    body = (f'<h1>{a["name"]} <span class="badge b-{a["platform"]}">{a["platform"]}</span></h1>'
            f'<p class="sub">{a["client"] or a["platform"]} · {start} to {end}</p>'
            + _range_bar(f"/account/{acct}", days)
            + _tiles(con, start, end, acct)
            + '<div class="card"><h2>Spend &amp; leads</h2><canvas id="trend"></canvas></div>')

    ecom = _is_ecom(con, acct)
    h2, h3 = ("Revenue", "ROAS") if ecom else ("Leads", "CPL")
    body += f'<div class="card"><h2>Campaigns (in range)</h2><table><tr><th>Campaign</th><th class="num">Spend</th><th class="num">{h2}</th><th class="num">{h3}</th><th class="num">CTR</th></tr>'
    for m in con.execute(
        "SELECT campaign, ROUND(SUM(spend),0) s, ROUND(SUM(leads),0) l, ROUND(SUM(revenue),0) rev, "
        "ROUND(SUM(clicks)*100.0/NULLIF(SUM(impressions),0),1) ctr, "
        "ROUND(SUM(spend)/NULLIF(SUM(leads),0),0) cpl "
        "FROM metrics WHERE account=? AND date>=? AND date<=? GROUP BY campaign ORDER BY s DESC",
            (acct, start, end)):
        if ecom:
            roas = (m["rev"] / m["s"]) if m["s"] else 0
            c2 = f'<td class="num">${m["rev"] or 0:,.0f}</td><td class="num">{roas:.1f}x</td>'
        else:
            c2 = f'<td class="num">{m["l"] or 0:,.0f}</td><td class="num">${m["cpl"] or 0:,.0f}</td>'
        body += (f'<tr><td>{m["campaign"]}</td><td class="num">${m["s"] or 0:,.0f}</td>'
                 f'{c2}<td class="num">{m["ctr"] or 0}%</td></tr>')
    body += '</table></div>'

    # Summary paragraph, then the one running narrative of every action (all-time, newest first).
    body += f'<div class="card"><h2>Summary</h2><div class="story">{cur_html}</div></div>'
    body += f'<div class="card"><h2>Management narrative — every action</h2><div class="story">{hist_html}</div></div>'
    return render(con, body, _trend_script(con, start, end, acct))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
