import db, summarize
c = db.connect()
print("--- 144 campaigns (leads) ---")
for r in c.execute("SELECT campaign, ROUND(SUM(leads)) l, ROUND(SUM(spend)) s FROM metrics "
                   "WHERE account LIKE '%144305066%' GROUP BY campaign ORDER BY s DESC"):
    print(f"  {r['campaign'][:40]:40} leads {r['l']} spend ${r['s']}")
print("--- Sanitred revenue ---")
r = c.execute("SELECT ROUND(SUM(spend)) s, ROUND(SUM(leads)) l, ROUND(SUM(revenue)) rev "
              "FROM metrics WHERE account LIKE '%2823564937%'").fetchone()
print(f"  spend ${r['s']} purchases {r['l']} revenue ${r['rev']}")
print()
print("distinct days of metrics:", c.execute("select count(distinct date) from metrics").fetchone()[0])
print("accounts shown:", len(summarize.active_accounts(c)))
for a in summarize.active_accounts(c):
    row = c.execute(
        "select round(sum(spend)) s, round(sum(leads)) l from metrics "
        "where account=? and date>=date('now','-30 day')", (a["id"],)).fetchone()
    print(f"  {a['name'][:34]:34} 30d spend ${row['s'] or 0:>7} leads {row['l'] or 0}")
