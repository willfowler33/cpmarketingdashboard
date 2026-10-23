"""Seed the specialist_reports table with Simi's daily updates pulled from Gmail."""
import datetime as dt
import db

REPORTS = [
    ("2026-08-12", "Daily Update 08/12", """Main items worked on today:
- Added a new creative and copy for GraniFlex; the campaign is already back up.
- Updated the Metallic copy as Aidan put it together.
- Building new creative direction for Columbus. We have a rise in CPL that I'm trying to correct with a more qualified audience and by testing new creatives, though it's expected given the budget.
- Noticed a 4-star review with a negative comment on the site that opens right on the home. We need to remove it and be careful this doesn't happen again."""),

    ("2026-08-11", "Daily Update 08/11", """Main items:
- Metallic Marble PSI running with results within expectations (below $5/lead), current CPL $3.77.
- GraniFlex PSI paused due to issues with the ad; awaiting greenlight.
- Sent the Training class lead-generation plan and a SANI-TRED plan (docs).
- Columbus: launched a new detailed-targeting adset testing a tighter segmentation to capture qualified leads and focus budget on higher-converting audiences, to lower CPL.
- Beckley: launched another creative to continue the positive trend, focused on a new hook."""),

    ("2026-08-10", "Daily Update 8/10", """Today's analysis:
- All active accounts/campaigns show improved CPL efficiency vs last week, except Columbus (up today) — expected since it was paused then resumed Aug 1 and is regaining traction.
- Bulldog and SLG remain paused, no client response yet.
- Strongest improvement: Tailored, -59% CPL to $15; then Reveles -54% at $24 CPL; Artisan -50%.
- Columbus the only account with CPL inflation, still near benchmark.
Per account: Reveles recovered CPL below $25 after a slow first week. Bulldog paused (watch a billing card change). Tailored big improvement in leads and CPL from July's new campaign. Columbus CPL fluctuation from pause/resume learning phase plus reduced investment (client aware). Artisan fluctuating but this peak was the lowest so far (client aware). Fortress stable and consistent, still new, no optimizations planned yet. SLG paused at client request.
Additional: working on Sani-tred plan; architecting a detailed-targeting adset for Training and reactivated historical adsets plus new RMKT audiences; launched GraniFlex and Metallic Marble in the account per budget."""),

    ("2026-08-05", "Daily Update 08/05", """Main items:
- Fortress: significant CPL improvement and lower frequency; would still benefit from a new creative (maybe replicate the Artisan model).
- Beckley: good performance but leaning on a single creative (frequency 3.8 over 30d), preparing a creative to test despite strong $21.41 CPL.
- Columbus: paused the clean creative — low performance and pulling a large share of budget at an inflated CPL vs others in the adset; ad copy update planned for the older ones.
- Artisan: launched new creatives to improve CTR and avoid creative fatigue, aiming to reduce CPL."""),

    ("2026-08-04", "Daily Update 8/4 | July Campaign Results", """July monthly analysis (legend: CTR = click quality, CVR = conversion rate, CPL = profitability):
- Reveles: CPL up, CVR down despite CTR rise (seasonal, hero creative dip). Building new creatives and an audience A/B test.
- Bulldog: weak start recovered late month at $18.29 CPL, but paused at its peak (hurts learning). Paused until greenlight.
- Tailored: lower volume from turbulent start, big improvement late — early August $22.72 CPL after fine adjustments.
- Columbus: improved in early August to $25.85 CPL despite weak July start; corrections applied and working.
- Artisan: MoM -32% CPL; early August weaker, building new creatives to improve below-benchmark CTR.
- Beckley: -58% CPL with big lead increase at same budget; strong August start.
- SLG: improved CPL and CTR but paused, awaiting client.
- Fortress: slight CPL/CTR improvement, small CVR drop, volume balanced; will test more qualified audiences to reduce CPL."""),

    ("2026-07-31", "Daily Update 7/31", """Main items:
- Artisan: despite funneling budget to the best creative, CPL rose with a performance drop on that creative vs last week — exogenous fluctuation amplified by low conversion volume. Monitoring; may test a new audience (short-term CPL impact) to stabilize on a more qualified audience.
- Fortress: CPL increase with cannibalization; will apply a frequency cap to avoid fatigue.
- Beckley: good performance but leaning on one creative; frequency elevated, need new creatives.
- Reveles: strong CTR increase last week but more expensive lead — possible seasonality or site issue; looking into escape points and conversion-rate optimizations.
- On 08/01 will turn on the Columbus campaigns as agreed."""),
]


def main():
    con = db.connect()
    for date, subject, body in REPORTS:
        con.execute(
            "INSERT OR REPLACE INTO specialist_reports(date, author, subject, body, source, received_at) "
            "VALUES(?,?,?,?,?,?)",
            (date, "Simi Brown", subject, body, "gmail-backfill", dt.datetime.now().isoformat()))
    con.commit()
    print("seeded", len(REPORTS), "specialist reports")


if __name__ == "__main__":
    main()
