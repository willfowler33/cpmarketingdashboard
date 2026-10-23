"""Generate the daily executive summary via OpenRouter from the day's changes + metrics."""
import datetime as dt
import json
import os

import requests

import db

# Free/cheap model on OpenRouter; override with OPENROUTER_MODEL in .env
MODEL = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

RULES = """STRICT RULES — this is a CEO report, accuracy matters more than color:
- Use ONLY the numbers given. Never invent, estimate, or round away from the data.
- Never dramatize. Do NOT use: stalled, plummeted, wild, crazy, spike, surge, collapse, skyrocket, fluctuate.
- Do NOT infer a trend from one day. One day at 0 leads is not "stalling."
- If leads are 0 or spend is tiny, state the number plainly and stop; do not speculate about causes.
- If a value is missing or 0, say so; do not guess.
- Prefer "no notable changes" over inventing a narrative.
- Output ONLY the finished summary. Do NOT show your reasoning, thinking, planning, or steps.
  No "Okay, let me...", no chain-of-thought, no meta commentary. Just the summary itself."""

PROMPT = f"""You are the paid-ads oversight analyst for The Concrete Protector. Your job is to
document the ad-management process so it doesn't live in one person's head — capture what the
specialist did and why, well enough that we could clone their decisions. Write the daily executive
summary in markdown across all active accounts for {{date}}.

{RULES}

The DATA has two parts: `accounts` (objective API changes + metrics) and `specialist_report`
(the ads specialist's own daily notes). Reconcile them: where the specialist explains a reason,
use it; where the API shows a change she didn't mention, note it; where she mentions work the API
can't see (creative, copy, audience), include it and attribute it to her notes.

Answer, briefly and factually:
1. **What happened** - one or two sentences: the most important activity across the portfolio (or "Quiet day").
2. **What changed & why** - accounts with activity: what was done (budget, pause, creative, copy, targeting, bid), and the reason — from the specialist's notes if given, otherwise a cautious inference tied to the metrics.
3. **What improved or declined** - real moves in CPL/CPC/CTR/conversion rate/spend/lead volume vs the prior period, with actual numbers.
4. **Not being managed** - accounts spending with no changes; flag worsening numbers (note paused accounts the specialist listed).
5. **Problems & opportunities** - anything needing a human decision today.

Keep it tight. This is a daily CEO brief, not an essay.

DATA:
{{data}}
"""


def build_data(con, date):
    prior = (dt.date.fromisoformat(date) - dt.timedelta(days=7)).isoformat()
    accounts = active_accounts(con)
    out = []
    for a in accounts:
        changes = [dict(r) for r in con.execute(
            "SELECT changed_at, actor, source, object_type, object_name, event_type, detail "
            "FROM changes WHERE account=? AND changed_at LIKE ?", (a["id"], f"{date}%"))]
        day = [dict(r) for r in con.execute(
            "SELECT campaign, spend, impressions, clicks, leads, ctr, cpc, cpl "
            "FROM metrics WHERE account=? AND date=?", (a["id"], date))]
        avg = con.execute(
            "SELECT AVG(spend) s, AVG(leads) l, AVG(cpl) c FROM metrics "
            "WHERE account=? AND date>=? AND date<?", (a["id"], prior, date)).fetchone()
        out.append({
            "account": a["name"], "platform": a["platform"], "client": a["client"],
            "changes": changes, "metrics_yesterday": day,
            "prior_7day_daily_avg": {"spend": avg["s"], "leads": avg["l"], "cpl": avg["c"]},
        })
    return out


def latest_specialist_report(con, on_or_before=None):
    if on_or_before:
        r = con.execute("SELECT * FROM specialist_reports WHERE date<=? ORDER BY date DESC LIMIT 1",
                        (on_or_before,)).fetchone()
    else:
        r = con.execute("SELECT * FROM specialist_reports ORDER BY date DESC LIMIT 1").fetchone()
    return dict(r) if r else None


import time

# Try these models in order; first that isn't rate-limited wins.
# Cheap paid, non-reasoning chat models (reliable, fast, ~cents/day). Reasoning models
# (deepseek-r1 etc.) are avoided — they leak chain-of-thought. OpenRouter caps the list at 3.
FALLBACK_MODELS = [
    "deepseek/deepseek-chat",
    "minimax/minimax-m3",
    "deepseek/deepseek-v3.2",
]


def _looks_degenerate(text):
    """Catch small-model meltdowns: apology loops, empty, repetition, or reasoning dumps."""
    if not text or len(text.strip()) < 40:
        return True
    low = text.lower()
    if low.count("sorry") + low.count("we apologize") >= 3:
        return True
    # Reasoning/meta-commentary dump: the model talks ABOUT the task instead of doing it.
    meta = ("we need to", "we must", "let me", "let's", "the instruction",
            "the format", "one bullet per change", "mmm d", "newest date first",
            "we can summarize", "we have many", "assuming today", "we should",
            "prohibited words", "not given", "inferred)?", "we will", "i need to")
    hits = sum(low.count(p) for p in meta)
    if hits >= 3:
        return True
    words = low.split()
    if len(words) >= 20:
        top = max((words.count(w) for w in set(words)), default=0)
        if top / len(words) > 0.25:  # one token is >25% of output
            return True
    return False


def _call_openrouter(prompt, _model=None):
    # OpenRouter routes across this list, skipping any that are rate-limited/down.
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://marketingdashboard.theconcreteprotector.com",
            "X-Title": "TCP Ads Visibility",
        },
        json={
            "models": FALLBACK_MODELS,
            "route": "fallback",
            "max_tokens": 4000,
            "reasoning": {"exclude": True},   # keep chain-of-thought out of the answer
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    r.raise_for_status()
    return _strip_reasoning(r.json()["choices"][0]["message"]["content"])


def _strip_reasoning(text):
    """Remove chain-of-thought that reasoning models leak into the answer."""
    if not text:
        return text
    import re
    # Drop <think>...</think> / <reasoning>...</reasoning> blocks.
    text = re.sub(r"(?is)<(think|reasoning|analysis)>.*?</\1>", "", text)
    # If the model wrote a reasoning preamble then a marked final answer, keep the answer.
    for marker in ("final answer:", "final summary:", "here is the summary", "here's the summary", "## "):
        idx = text.lower().rfind(marker)
        if idx > 120:  # only cut if there's a big preamble before it
            text = text[idx if marker == "## " else idx + len(marker):]
            break
    # Drop leading first-person reasoning lines ("Okay, let me...", "I need to...").
    lines = text.strip().splitlines()
    while lines and re.match(r"(?i)^\s*(okay|ok|so|let me|let's|i need|i will|i'll|first,|now,|alright)\b", lines[0]):
        lines.pop(0)
    return "\n".join(lines).strip()


_NOISE_EVENTS = ("deliver", "billed", "billing", "receipt", "spend", "review",
                 "ad delivered", "account billed")


def _is_mgmt_change(c):
    """True only for real management actions — not Meta's automatic delivery/billing events."""
    actor = (c.get("actor") or "").strip().lower()
    ev = (c.get("event_type") or "").lower()
    if actor in ("meta", "facebook", "system", ""):
        # Meta/automatic events are noise unless they're a real status/budget/creative change.
        if not any(k in ev for k in ("status", "budget", "paused", "active", "created",
                                     "removed", "updated", "targeting", "bid", "creative")):
            return False
    if any(n in ev for n in _NOISE_EVENTS):
        return False
    return True


def _fallback_story(data, date):
    """Deterministic story built straight from the data — used if every model is throttled."""
    active, idle, lines = [], [], []
    tot_spend = tot_leads = 0
    for a in data:
        sp = sum(m["spend"] for m in a["metrics_yesterday"])
        ld = sum(m["leads"] for m in a["metrics_yesterday"])
        tot_spend += sp
        tot_leads += ld
        mgmt = [c for c in a["changes"] if _is_mgmt_change(c)]
        if mgmt:
            active.append(a["account"])
            for c in mgmt[:3]:
                who = c.get("actor") or "specialist"
                lines.append(f"- **{a['account']}**: {c['event_type']} on {c.get('object_name') or c.get('object_type') or 'account'} ({who})")
        elif sp > 0:
            idle.append(f"{a['account']} (${sp:,.0f})")
    cpl = (tot_spend / tot_leads) if tot_leads else 0
    out = [f"**What happened.** ${tot_spend:,.0f} spend, {tot_leads:.0f} results, ${cpl:,.0f} blended CPL "
           f"across {len(data)} active accounts on {date}.", ""]
    if lines:
        out += ["**What changed.**", *lines, ""]
    if idle:
        out += ["**Not actively managed (spending, no changes).** " + ", ".join(idle), ""]
    out += ["_See the specialist notes below for the reasoning behind these moves._"]
    return "\n".join(out)


def summarize(con, date):
    data = build_data(con, date)
    text = None
    # AI brief is opt-in (USE_AI_BRIEF=1). Free models proved unreliable/slow for this, so the
    # deterministic brief is the default; Simi's notes panel carries the human 'why'.
    if os.environ.get("USE_AI_BRIEF") == "1":
        rep = latest_specialist_report(con, date)
        payload = {"accounts": data, "specialist_report": (rep or {}).get("body", "(none)")}
        prompt = PROMPT.format(date=date, data=json.dumps(payload, default=str))
        try:
            out = _call_openrouter(prompt)
            if not _looks_degenerate(out):
                text = out
        except Exception:
            pass
    if not text:
        text = _fallback_story(data, date)
    con.execute("INSERT OR REPLACE INTO summaries(date, exec_summary, generated_at) VALUES(?,?,?)",
                (date, text, dt.datetime.now().isoformat()))
    return text


# ---- Per-entity stories ------------------------------------------------------

ACCOUNT_PROMPT = f"""You are the paid-ads analyst for The Concrete Protector. Write a SHORT
current-status note (60-110 words, markdown, no headers) about ONE ad account for {{date}}:
{{name}} ({{platform}}).

{RULES}

If account_type is "ecommerce", report spend, REVENUE, ROAS (revenue/spend) and purchases — never
call them leads. If account_type is "lead-gen", report spend, leads, CPL and CTR. Cover what changed
yesterday (if anything) and a cautious why, versus the prior 7-day average, with the real numbers.
If nothing changed and numbers are steady, say exactly that in one or two sentences.

DATA:
{{data}}
"""

CHANGES_PROMPT = f"""You are the paid-ads analyst for The Concrete Protector. From the change log
for {{name}} ({{platform}}) over the last 30 days, produce a dated list of what was DONE and WHY,
for the CEO.

{RULES}

Format: a markdown bullet list, newest date first. Each bullet:
**MMM D** — <what was changed, specific: object + old→new if known> — done to <likely reason based on
the metrics, label it inferred>.
One bullet per change. Group multiple changes on the same day under that date. If there are no
changes in the last 30 days, write exactly: "No management changes logged in the last 30 days."
Do not invent changes that aren't in the log. Use real numbers when citing why.

DATA:
{{data}}
"""


def build_account_data(con, account, date):
    prior = (dt.date.fromisoformat(date) - dt.timedelta(days=7)).isoformat()
    changes = [dict(r) for r in con.execute(
        "SELECT changed_at, actor, object_type, object_name, event_type, detail "
        "FROM changes WHERE account=? AND changed_at LIKE ?", (account, f"{date}%"))]
    day = [dict(r) for r in con.execute(
        "SELECT campaign, spend, impressions, clicks, leads, ctr, cpc, cpl, revenue "
        "FROM metrics WHERE account=? AND date=?", (account, date))]
    avg = con.execute(
        "SELECT AVG(spend) s, AVG(leads) l, AVG(cpl) c, AVG(ctr) t, AVG(revenue) r FROM metrics "
        "WHERE account=? AND date>=? AND date<?", (account, prior, date)).fetchone()
    is_ecom = (con.execute("SELECT COALESCE(SUM(revenue),0) r FROM metrics WHERE account=?",
                           (account,)).fetchone()["r"] or 0) > 0
    return {"account_type": "ecommerce" if is_ecom else "lead-gen", "changes": changes,
            "metrics_yesterday": day,
            "prior_7day_daily_avg": {"spend": avg["s"], "leads": avg["l"], "cpl": avg["c"],
                                     "ctr": avg["t"], "revenue": avg["r"]}}


def _account_fallback(con, account, date):
    d = build_account_data(con, account, date)
    sp = sum(m["spend"] for m in d["metrics_yesterday"])
    ld = sum(m["leads"] for m in d["metrics_yesterday"])
    parts = [f"**${sp:,.0f} spend, {ld:.0f} leads** on {date}."]
    if d["changes"]:
        parts.append("Changes: " + "; ".join(
            f"{c['event_type']} on {c.get('object_name') or c.get('object_type') or 'account'}"
            for c in d["changes"][:4]))
    else:
        parts.append("No management changes logged.")
    parts.append("_AI narrative unavailable (model busy); showing data summary._")
    return " ".join(parts)


def summarize_account(con, account, name, platform, date):
    data = build_account_data(con, account, date)
    prompt = ACCOUNT_PROMPT.format(date=date, name=name, platform=platform,
                                   data=json.dumps(data, default=str))
    text = None
    for attempt in range(2):
        try:
            out = _call_openrouter(prompt)
            if not _looks_degenerate(out):
                text = out
                break
        except Exception as e:
            if getattr(getattr(e, "response", None), "status_code", None) == 429:
                time.sleep(5 * (attempt + 1))
    if not text:
        text = _account_fallback(con, account, date)
    con.execute("INSERT OR REPLACE INTO account_summaries(account, date, story, generated_at) VALUES(?,?,?,?)",
                (account, date, text, dt.datetime.now().isoformat()))
    return text


def build_account_history(con, account, date, days=30):
    start = (dt.date.fromisoformat(date) - dt.timedelta(days=days)).isoformat()
    changes = [dict(r) for r in con.execute(
        "SELECT changed_at, actor, object_type, object_name, event_type, substr(detail,1,300) detail "
        "FROM changes WHERE account=? AND changed_at>=? ORDER BY changed_at DESC", (account, start))]
    weekly = [dict(r) for r in con.execute(
        "SELECT substr(date,1,7)||'-w'||((cast(substr(date,9,2) as int)-1)/7+1) wk, "
        "MIN(date) frm, MAX(date) too, ROUND(SUM(spend),0) spend, ROUND(SUM(leads),0) leads, "
        "ROUND(SUM(spend)/NULLIF(SUM(leads),0),0) cpl "
        "FROM metrics WHERE account=? AND date>=? GROUP BY wk ORDER BY frm", (account, start))]
    campaigns = [dict(r) for r in con.execute(
        "SELECT campaign, ROUND(SUM(spend),0) spend, ROUND(SUM(leads),0) leads "
        "FROM metrics WHERE account=? AND date>=? GROUP BY campaign ORDER BY spend DESC LIMIT 8",
        (account, start))]
    return {"changes": changes, "weekly_totals": weekly, "top_campaigns": campaigns}


def _cpl_by_week(con, account):
    rows = con.execute(
        "SELECT date, ROUND(SUM(spend)/NULLIF(SUM(leads),0),0) cpl FROM metrics "
        "WHERE account=? GROUP BY date", (account,)).fetchall()
    return {r["date"]: r["cpl"] for r in rows if r["cpl"]}


def _reason_for(ev, detail, day, cpl_map, simi_hit):
    """A plain why clause (no 'inferred'), from Simi's note if present else metric direction."""
    if simi_hit:
        return simi_hit
    # CPL trend around the change day.
    d = dt.date.fromisoformat(day) if len(day) == 10 else None
    trend = ""
    if d and cpl_map:
        before = [v for k, v in cpl_map.items() if k < day][-7:]
        if before:
            recent = before[-1]
            base = sum(before) / len(before)
            if recent > base * 1.1:
                trend = "as cost per lead was climbing"
            elif recent < base * 0.9:
                trend = "while cost per lead was improving"
    e = ev.lower()
    if "budget" in e:
        return trend or "to adjust pacing"
    if "pause" in e or ("status" in e and "PAUSED" in (detail or "")):
        return "to stop spend on an underperformer"
    if "creative" in e or "ad" in e:
        return trend or "to refresh creative and hold performance"
    return trend


def _account_keywords(name):
    """Distinctive words from an account name for matching in Simi's prose."""
    stop = {"concrete", "coatings", "the", "and", "llc", "inc", "co", "floor", "decor",
            "products", "epoxy", "transformations", "protector"}
    words = [w.lower().strip("()") for w in name.split()]
    kws = [w for w in words if len(w) > 3 and w not in stop]
    # e.g. Sanitred, Columbus, Reveles, Tailored, Beckley, Fortress, Artisan, Bulldog, Graniflex
    return kws or words[:1]


def _simi_reason_map(con, account_name=None):
    """Specialist reason lines. If account_name given, only lines that mention that account."""
    reports = con.execute("SELECT date, body FROM specialist_reports ORDER BY date").fetchall()
    kws = _account_keywords(account_name) if account_name else None
    out = []
    for r in reports:
        for line in (r["body"] or "").splitlines():
            line = line.strip("-* ").strip()
            if len(line) <= 20:
                continue
            if kws and not any(k in line.lower() for k in kws):
                continue
            out.append((r["date"], line))
    return out


def _narrate(c, cpl_map):
    """Turn one change into a plain narrative sentence (what was done; reason only where it adds info)."""
    import re
    ev = (c.get("event_type") or "")
    obj = (c.get("object_type") or "").replace("_", " ").lower()
    name = c.get("object_name") or ""
    detail = c.get("detail") or ""
    day = (c.get("changed_at") or "")[:10]
    reason = ""

    amt = re.findall(r"amount_micros:\s*(\d+)", detail)
    if len(amt) >= 2:
        a, b = int(amt[0]) / 1e6, int(amt[1]) / 1e6
        verb = "Raised" if b > a else "Lowered"
        what = f"{verb} the daily budget from ${a:,.0f} to ${b:,.0f}"
        reason = _reason_for("budget", detail, day, cpl_map, "")
    elif "ENABLED" in detail and "PAUSED" in detail:
        what = f"Paused {obj}" + (f" “{name}”" if name else "")
    elif "CREATE" in ev.upper():
        what = f"Added {obj}" + (f" “{name}”" if name else "")
    elif "REMOVE" in ev.upper():
        what = f"Removed {obj}" + (f" “{name}”" if name else "")
    elif "target_cpa" in detail:
        what = "Removed the target CPA to give bidding more flexibility"
    else:
        what = f"{ev.replace('_',' ').capitalize()}" + (f" “{name}”" if name else f" on the {obj}")
    return what + (f" — {reason}" if reason else "") + "."


def _fmt_change(c):
    """One human line describing a single change, parsed from its detail."""
    import re
    ev = (c.get("event_type") or "").replace("_", " ").title()
    obj = (c.get("object_type") or "").replace("_", " ").lower()
    name = c.get("object_name") or ""
    detail = c.get("detail") or ""
    old_new = ""
    # Google detail: budget amounts in micros, status old/new.
    m_old = re.search(r"amount_micros:\s*(\d+)", detail)
    if m_old:
        pass
    old_amt = re.findall(r"amount_micros:\s*(\d+)", detail)
    if len(old_amt) >= 2:
        old_new = f" ${int(old_amt[0])/1_000_000:,.0f}→${int(old_amt[1])/1_000_000:,.0f}/day"
    elif "ENABLED" in detail and "PAUSED" in detail:
        old_new = " enabled→paused"
    elif "old_value" in detail:
        mo = re.search(r'"old_value":\s*"?([^",}]+)', detail)
        mn = re.search(r'"new_value":\s*"?([^",}]+)', detail)
        if mo and mn:
            old_new = f" {mo.group(1)}→{mn.group(1)}"
    label = obj or "item"
    if name:
        label += f" “{name}”"
    return f"{ev} {label}{old_new}".strip()


def _change_narrative(con, account, account_name=None):
    """One running bulleted narrative of every management action, all-time, newest first."""
    if not account_name:
        row = con.execute("SELECT name FROM accounts WHERE id=?", (account,)).fetchone()
        account_name = row["name"] if row else ""
    changes = [dict(r) for r in con.execute(
        "SELECT changed_at, actor, object_type, object_name, event_type, substr(detail,1,400) detail "
        "FROM changes WHERE account=? ORDER BY changed_at DESC", (account,))]
    changes = [c for c in changes if _is_mgmt_change(c)]
    if not changes:
        return "No management changes have been logged for this account yet."
    cpl_map = _cpl_by_week(con, account)
    from collections import OrderedDict
    by_day = OrderedDict()
    for c in changes:
        by_day.setdefault((c["changed_at"] or "")[:10], []).append(c)

    out = []
    for day, items in by_day.items():
        try:
            label = dt.date.fromisoformat(day).strftime("%b %-d, %Y")
        except Exception:
            label = day
        out.append(f"- **{label}** — {_narrate_day(items, '', cpl_map)}")
    return "\n".join(out)


def _narrate_day(items, simi_note, cpl_map):
    """One flowing narrative sentence for a day's work: what was done, and the why."""
    import re
    from collections import OrderedDict
    creates, budgets = OrderedDict(), []
    n_ad = n_adset = n_target = n_img = n_aud = 0
    for c in items:
        ev = (c.get("event_type") or "").lower()
        obj = (c.get("object_type") or "").replace("_", " ").lower()
        name = c.get("object_name") or ""
        detail = c.get("detail") or ""
        if re.findall(r"amount_micros:\s*(\d+)", detail):
            budgets.append(_narrate(c, cpl_map).rstrip("."))
        elif "create" in ev and name and "image" not in ev:
            kind = "campaign" if "campaign" in obj else "ad group"
            creates[(kind, name)] = 1
        elif "image" in ev:
            n_img += 1
        elif "target" in ev:
            n_target += 1
        elif "audience" in ev:
            n_aud += 1
        elif "ad set" in ev or "adset" in ev:
            n_adset += 1
        elif ev.startswith("ad") or "ad " in ev:
            n_ad += 1

    clauses = []
    if creates:
        camps = [n for (k, n) in creates if k == "campaign"]
        groups = [n for (k, n) in creates if k != "campaign"]
        if camps:
            clauses.append(("launched the campaign " if len(camps) == 1 else "launched campaigns ")
                           + _join([f"“{n}”" for n in camps]))
        if groups:
            if len(groups) == 1:
                clauses.append(f"added the ad group “{groups[0]}”")
            else:
                clauses.append(f"added {len(groups)} ad groups (" + ", ".join(f"“{n}”" for n in groups) + ")")
    for b in budgets:
        clauses.append(b[0].lower() + b[1:])
    if n_ad:
        clauses.append(f"updated {n_ad} ad{'s' if n_ad != 1 else ''}")
    if n_adset:
        clauses.append(f"adjusted {n_adset} ad set{'s' if n_adset != 1 else ''}")
    if n_target:
        clauses.append(f"refined targeting on {n_target} item{'s' if n_target != 1 else ''}")
    if n_img:
        clauses.append(f"added {n_img} creative image{'s' if n_img != 1 else ''}")
    if n_aud:
        clauses.append("updated the custom audience")
    if not clauses:
        clauses.append("made minor account changes")

    sentence = _join(clauses)
    sentence = sentence[0].upper() + sentence[1:] + "."
    if simi_note:
        sentence += f" *{simi_note.rstrip('.')}.*"
    return sentence


def _join(parts):
    parts = list(parts)
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _group_day(items, cpl_map):
    """Collapse a day's raw changes into a few readable bullets (named actions kept, bulk counted)."""
    import re
    from collections import defaultdict, OrderedDict
    budgets, named = [], OrderedDict()
    counts = defaultdict(int)
    for c in items:
        ev = (c.get("event_type") or "").lower()
        obj = (c.get("object_type") or "").replace("_", " ").lower()
        name = c.get("object_name") or ""
        detail = c.get("detail") or ""
        if re.findall(r"amount_micros:\s*(\d+)", detail):
            budgets.append(_narrate(c, cpl_map))
        elif "create" in ev and name and "image" not in ev:
            named[("Added", obj, name)] = 1
        elif "remove" in ev and name and "image" not in ev:
            named[("Removed", obj, name)] = 1
        elif "image" in ev:
            counts["images"] += 1
        elif "target" in ev:
            counts["targeting"] += 1
        elif "budget" in ev:
            counts["budget"] += 1
        elif "audience" in ev:
            counts["audience"] += 1
        elif "ad set" in ev or "adset" in ev:
            counts["adset"] += 1
        elif "ad " in ev or ev.startswith("ad"):
            counts["ad"] += 1
        else:
            counts["other"] += 1
    out = []
    for b in budgets:
        out.append(f"- {b}")
    for (verb, obj, name) in named:
        out.append(f"- {verb} {obj} “{name}”.")
    def plural(n, s):
        return f"{n} {s}" + ("s" if n != 1 else "")
    if counts["ad"]:
        out.append(f"- Updated status/settings on {plural(counts['ad'], 'ad')}.")
    if counts["adset"]:
        out.append(f"- Updated {plural(counts['adset'], 'ad set')}.")
    if counts["targeting"]:
        out.append(f"- Updated targeting on {plural(counts['targeting'], 'item')}.")
    if counts["audience"]:
        out.append(f"- Updated the custom audience.")
    if counts["images"]:
        out.append(f"- Added/updated {plural(counts['images'], 'creative image')} in the library.")
    if counts["budget"]:
        out.append(f"- Adjusted {plural(counts['budget'], 'budget')}.")
    if counts["other"]:
        out.append(f"- {plural(counts['other'], 'other change')}.")
    return out


NARRATIVE_PROMPT = """You are documenting how the ad account "{name}" has been managed, for a CEO
who is not a marketer. Below is a dated list of WHAT was done (newest first), the weekly
performance numbers, and the ad specialist's own notes.

Rewrite it as a plain-English narrative: ONE bullet per day, newest first, keeping every day that
appears. For each day, say what was done AND why, in plain English a non-marketer understands.

Rules:
- Translate jargon. CPL = cost per lead. "Hook" = the opening line/visual of an ad. "Creative" = the
  ad image or video. "Positive trend" — say what actually improved using the numbers (e.g. "cost per
  lead had been falling"). "Ad set" = an audience/budget group.
- Explain the WHY using the specialist's notes and the weekly numbers. Where no reason is stated,
  give the most likely reason from the numbers, said plainly (e.g. "to bring the cost per lead down
  after it rose to $X").
- Keep each day to 1–2 sentences. No jargon left unexplained, no "inferred", no bullet sub-lists.
- Do not invent numbers. Output only the bullet list.

WHAT WAS DONE:
{what}

WEEKLY PERFORMANCE (date range → spend, leads, cost per lead):
{weekly}
"""


def _weekly_perf(con, account):
    rows = con.execute(
        "SELECT MIN(date) frm, MAX(date) too, ROUND(SUM(spend)) spend, ROUND(SUM(leads)) leads, "
        "ROUND(SUM(spend)/NULLIF(SUM(leads),0)) cpl FROM metrics WHERE account=? "
        "GROUP BY strftime('%Y-%W', date) ORDER BY frm DESC", (account,)).fetchall()
    return "\n".join(f"- {r['frm']}→{r['too']}: ${r['spend'] or 0}, {r['leads'] or 0} leads, "
                     f"${r['cpl'] or 0} CPL" for r in rows[:10])


def summarize_account_history(con, account, name, platform, date):
    det = _change_narrative(con, account, name)
    # AI turns the factual 'what' + metrics + Simi's notes into a plain-English 'why' narrative.
    # Small structured input + reasoning excluded + hard validation; falls back to the plain 'what'.
    text = det
    if os.environ.get("USE_AI_NARRATIVE", "1") == "1" and "No management changes" not in det:
        prompt = NARRATIVE_PROMPT.format(name=name, what=det[:6000],
                                         weekly=_weekly_perf(con, account))
        try:
            out = _call_openrouter(prompt)
            if out and not _looks_degenerate(out) and out.count("-") >= 2:
                text = out
        except Exception:
            pass
    con.execute("INSERT OR REPLACE INTO account_summaries(account, date, story, generated_at) VALUES(?,?,?,?)",
                (account, "history", text, dt.datetime.now().isoformat()))
    return text


def active_accounts(con, days=30):
    """Accounts that actually spent in the trailing window — the live ones. Ordered by spend."""
    return [dict(r) for r in con.execute(
        "SELECT a.*, s.recent_spend FROM accounts a JOIN "
        "(SELECT account, SUM(spend) recent_spend FROM metrics "
        " WHERE date>=date('now', ?) GROUP BY account HAVING SUM(spend)>0) s "
        "ON s.account=a.id WHERE a.active=1 ORDER BY s.recent_spend DESC, a.name",
        (f"-{days} day",))]


def summarize_all(con, date):
    """Nightly: current + history story per active account, plus the aggregate home story."""
    for a in active_accounts(con):
        summarize_account(con, a["id"], a["name"], a["platform"], date)
        summarize_account_history(con, a["id"], a["name"], a["platform"], date)
        con.commit()
    summarize(con, date)
    con.commit()
