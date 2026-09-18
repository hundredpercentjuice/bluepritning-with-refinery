#!/usr/bin/env python3
"""
Rebuild The Aging Ledger (MSI open-AR top-100 page) from live Oracle EBS data.

Runs 3 `refinery` CLI calls total against connector 7357 (Oracle EBS) and one
local templating pass. See REBUILD.md for the full walkthrough and the
speed-up rationale.

Usage:
    python3 build_aging_ledger.py [--as-of YYYY-MM-DD] [--sandbox NAME] [--out FILE]

    --as-of    Date to age against. Defaults to today (UTC). Pass an explicit
               date to reproduce a past snapshot instead of "as of now".
    --sandbox  Named refinery sandbox to reuse (default: o2c-open-items).
               Reusing a name avoids the ~5-10s sandbox cold-start on rerun.
    --out      Output HTML path (default: aging-ledger.html, next to this script).

Requires: `refinery` CLI installed and authenticated (`refinery auth status`).
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

CONNECTOR_ID = 7357  # Oracle EBS
HERE = Path(__file__).resolve().parent
TEMPLATE_PATH = HERE / "aging-ledger.template.html"

Q_OPEN_ITEMS = """
SELECT
  ps.payment_schedule_id,
  trx.trx_number,
  trx.trx_date,
  ps.due_date,
  ps.amount_due_original,
  ps.amount_due_remaining,
  p.party_id AS customer_party_id,
  p.party_name AS customer_name
FROM ar.ar_payment_schedules_all ps
JOIN ar.ra_customer_trx_all trx ON trx.customer_trx_id = ps.customer_trx_id
JOIN hz.hz_cust_accounts c ON c.cust_account_id = trx.bill_to_customer_id
JOIN hz.hz_parties p ON p.party_id = c.party_id
WHERE ps.status = 'OP'
""".strip()
# NOTE: a handful of HZ_PARTIES.PARTY_NAME values are duplicated across
# distinct PARTY_IDs (seen 2026-09: "Pulse Automation SA", "Quantum Vision
# Co", and 4 others). Always dedupe/group customers by PARTY_ID, never by
# name alone, or you'll silently merge two different companies.

Q_PAID_DSO = """
SELECT ROUND(AVG(ps.gl_date - trx.trx_date), 1) AS days_to_collect
FROM ar.ar_payment_schedules_all ps
JOIN ar.ra_customer_trx_all trx ON trx.customer_trx_id = ps.customer_trx_id
WHERE ps.status = 'CL'
""".strip()

Q_REVENUE_TOP5 = """
SELECT customer_party_id, customer_name, revenue, ROUND(100 * revenue / SUM(revenue) OVER (), 1) AS pct
FROM (
  SELECT p.party_id AS customer_party_id, p.party_name AS customer_name, SUM(l.extended_amount) AS revenue
  FROM ar.ra_customer_trx_lines_all l
  JOIN ar.ra_customer_trx_all t ON t.customer_trx_id = l.customer_trx_id
  JOIN hz.hz_cust_accounts c ON c.cust_account_id = t.bill_to_customer_id
  JOIN hz.hz_parties p ON p.party_id = c.party_id
  GROUP BY p.party_id, p.party_name
)
ORDER BY revenue DESC
FETCH FIRST 5 ROWS ONLY
""".strip()

# Runs remotely in the sandbox via `refinery exec python`. Prints one line
# `@@RESULT@@<json>` that the local script extracts. Everything else on
# stdout is treated as noise.
AGG_SCRIPT = r"""
import pandas as pd, json

AS_OF = pd.Timestamp("__AS_OF_ISO__")

df = open_items.copy()
df['AMOUNT_DUE_ORIGINAL'] = df['AMOUNT_DUE_ORIGINAL'].astype(float)
df['AMOUNT_DUE_REMAINING'] = df['AMOUNT_DUE_REMAINING'].astype(float)
df['TRX_DATE'] = pd.to_datetime(df['TRX_DATE'])
df['DUE_DATE'] = pd.to_datetime(df['DUE_DATE'])
df['days_past_due'] = (AS_OF - df['DUE_DATE']).dt.days

BUCKET_EDGES = [-10**9, 30, 60, 90, 180, 365, 10**9]
BUCKET_LABELS = ["0-30d", "31-60d", "61-90d", "91-180d", "181-365d", "365d+"]
df['bucket'] = pd.cut(df['days_past_due'], bins=BUCKET_EDGES, labels=BUCKET_LABELS)

total_open_ar = round(df['AMOUNT_DUE_REMAINING'].sum(), 2)
total_open_items = int(len(df))
total_open_customers = int(df['CUSTOMER_PARTY_ID'].nunique())

top = df.sort_values('AMOUNT_DUE_REMAINING', ascending=False).head(100).reset_index(drop=True)
top100_total = round(top['AMOUNT_DUE_REMAINING'].sum(), 2)

register = []
for i, r in top.iterrows():
    register.append({
        "rank": i + 1,
        "invoice": r['TRX_NUMBER'],
        "customer": r['CUSTOMER_NAME'],
        "trx_date": r['TRX_DATE'].strftime("%Y-%m-%d"),
        "due_date": r['DUE_DATE'].strftime("%Y-%m-%d"),
        "amount": round(float(r['AMOUNT_DUE_REMAINING']), 2),
        "days_past_due": int(r['days_past_due']),
    })

def aging(frame, denom):
    g = frame.groupby('bucket', observed=False)['AMOUNT_DUE_REMAINING'].agg(['size', 'sum'])
    g = g.reindex(BUCKET_LABELS).fillna(0)
    out = []
    for label, row in g.iterrows():
        pct = round(100 * row['sum'] / denom, 1) if denom else 0.0
        out.append({"bucket": label.replace('-', '–'), "n": int(row['size']), "amount": round(float(row['sum']), 2), "pct": pct})
    return out

top100_aging = aging(top, top100_total)
full_aging = aging(df, total_open_ar)

def over90_amount(frame):
    return frame.loc[~frame['bucket'].isin(["0-30d", "31-60d", "61-90d"]), 'AMOUNT_DUE_REMAINING'].sum()

top100_over90_pct = round(100 * over90_amount(top) / top100_total, 1) if top100_total else 0.0
full_over90_pct = round(100 * over90_amount(df) / total_open_ar, 1) if total_open_ar else 0.0

peak = max(top100_aging, key=lambda b: b['amount'])

name_by_party = top.drop_duplicates('CUSTOMER_PARTY_ID').set_index('CUSTOMER_PARTY_ID')['CUSTOMER_NAME']
cust = top.groupby('CUSTOMER_PARTY_ID')['AMOUNT_DUE_REMAINING'].sum().sort_values(ascending=False)
top10_customers_raw = [{"party_id": int(pid), "customer": name_by_party[pid], "amount": round(float(v), 2)}
                       for pid, v in cust.head(10).items()]

rev_ids = set(int(x) for x in rev_top5['CUSTOMER_PARTY_ID'].tolist())
rev_top4_ids = set(int(x) for x in rev_top5['CUSTOMER_PARTY_ID'].tolist()[:4])
top_customers = []
for c in top10_customers_raw:
    tag = None
    if c['party_id'] in rev_top4_ids:
        tag = "Top-4 revenue"
    elif c['party_id'] in rev_ids:
        tag = "Top-5 revenue"
    top_customers.append({**c, "revTag": tag})

top5_customer_share_pct = round(100 * cust.head(5).sum() / top100_total, 1) if top100_total else 0.0

# holders needed to clear 50% of the top-100 cohort, preferring customers
# that are also top revenue accounts (the highest-leverage outreach set)
ranked = sorted(top_customers, key=lambda c: (c['revTag'] is None, -c['amount']))
running, chosen = 0.0, []
for c in ranked:
    chosen.append(c)
    running += c['amount']
    if running >= 0.5 * top100_total:
        break
top_holders_names = ", ".join(c['customer'].replace(" Inc", "").replace(" Co Ltd", "").replace(" LLC", "") for c in chosen)
top_holders_m = round(sum(c['amount'] for c in chosen), 2)
top_holders_share_pct = round(100 * top_holders_m / top100_total, 1) if top100_total else 0.0

partial_paid_mask = df['AMOUNT_DUE_ORIGINAL'] != df['AMOUNT_DUE_REMAINING']
n_partial = int(partial_paid_mask.sum())
if n_partial == 0:
    partial_sentence = ("not one shows a partial payment: amount_due_remaining equals "
                         "amount_due_original on every single row. Nothing here is a stalled "
                         "reconciliation; every open item is simply unpaid, in full.")
    dispute_headline = "Nothing here is a service or billing dispute."
else:
    partial_sentence = (f"{n_partial} show a partial payment (amount_due_remaining differs from "
                         f"amount_due_original) — worth separating short-paid/disputed invoices "
                         f"from invoices that are simply unpaid before running collections.")
    dispute_headline = f"{n_partial} of {total_open_items} open items are partially paid."

overlap = [c for c in top_customers if c['revTag'] == "Top-4 revenue"]
if overlap:
    names = ", ".join(c['customer'] for c in overlap)
    revenue_overlap_sentence = (
        f"{len(overlap)} of MSI's top revenue customers — {names} — also rank among the "
        f"largest holders of aged receivables inside this cohort."
    )
else:
    revenue_overlap_sentence = (
        "None of MSI's top-4 revenue customers currently rank among the largest holders in this "
        "cohort — the collections exposure here sits with a different set of accounts."
    )

apex_like = rev_top5.iloc[0]
revenue_risk_sentence = (
    f"Some of this cohort's largest holders can't be pressed the way a small, low-strategic-value "
    f"account can — {apex_like['CUSTOMER_NAME']} alone is {apex_like['PCT']}% of MSI's billed "
    f"revenue, so a credit hold there is a revenue decision, not just a collections one."
)

revenue_crossref_text = ", ".join(f"{r['CUSTOMER_NAME']} {r['PCT']}%" for _, r in rev_top5.iterrows())

result = {
    "AS_OF": AS_OF.strftime("%Y-%m-%d"),
    "TOTAL_OPEN_AR_M": f"${total_open_ar/1e6:.1f}M",
    "TOTAL_OPEN_ITEMS": total_open_items,
    "TOTAL_OPEN_CUSTOMERS": total_open_customers,
    "TOP100_TOTAL_M": f"${top100_total/1e6:.1f}M",
    "TOP100_SHARE_PCT": round(100 * top100_total / total_open_ar, 1) if total_open_ar else 0.0,
    "TOP100_ITEMS_SHARE_PCT": round(100 * 100 / total_open_items, 1) if total_open_items else 0.0,
    "TOP100_N_CUSTOMERS": int(top['CUSTOMER_PARTY_ID'].nunique()),
    "TOP5_SHARE_PCT": top5_customer_share_pct,
    "AVG_DPD": round(float(top['days_past_due'].mean()), 1),
    "PAID_DSO": float(dso_df['DAYS_TO_COLLECT'].iloc[0]),
    "TOP100_OVER90_PCT": top100_over90_pct,
    "FULL_OVER90_PCT": full_over90_pct,
    "PARTIAL_PAYMENT_SENTENCE": partial_sentence,
    "DISPUTE_HEADLINE": dispute_headline,
    "REVENUE_OVERLAP_SENTENCE": revenue_overlap_sentence,
    "REVENUE_RISK_SENTENCE": revenue_risk_sentence,
    "REVENUE_CROSSREF_TEXT": revenue_crossref_text,
    "TOP_N_HOLDERS": len(chosen),
    "TOP_HOLDERS_SHARE_PCT": top_holders_share_pct,
    "TOP_HOLDERS_NAMES": top_holders_names,
    "TOP_HOLDERS_M": f"${top_holders_m/1e6:.1f}M",
    "PEAK_BUCKET_LABEL": peak['bucket'],
    "PEAK_BUCKET_M": f"${peak['amount']/1e6:.1f}M",
    "PEAK_BUCKET_PCT": peak['pct'],
    "TOP100_AGING_JSON": top100_aging,
    "FULL_AGING_JSON": full_aging,
    "TOP_CUSTOMERS_JSON": top_customers,
    "REGISTER_JSON": register,
}
print("@@RESULT@@" + json.dumps(result))
"""


def run_refinery(args, label):
    print(f"  $ refinery {' '.join(args)}", file=sys.stderr)
    proc = subprocess.run(["refinery", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"refinery {label} failed (exit {proc.returncode}):", file=sys.stderr)
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        sys.exit(1)
    return json.loads(proc.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=datetime.date.today().isoformat())
    ap.add_argument("--sandbox", default="o2c-open-items")
    ap.add_argument("--out", default=str(HERE / "aging-ledger.html"))
    args = ap.parse_args()

    if not TEMPLATE_PATH.exists():
        sys.exit(f"Template not found: {TEMPLATE_PATH}")

    print(f"Rebuilding as of {args.as_of}, sandbox '{args.sandbox}'...", file=sys.stderr)

    run_refinery(
        ["connector", "db", "query", str(CONNECTOR_ID), "--sql", Q_OPEN_ITEMS,
         "--sandbox", args.sandbox, "--as", "open_items"],
        "open_items query",
    )
    run_refinery(
        ["connector", "db", "query", str(CONNECTOR_ID), "--sql", Q_PAID_DSO,
         "--sandbox", args.sandbox, "--as", "dso_df"],
        "paid-DSO query",
    )
    run_refinery(
        ["connector", "db", "query", str(CONNECTOR_ID), "--sql", Q_REVENUE_TOP5,
         "--sandbox", args.sandbox, "--as", "rev_top5"],
        "revenue-top5 query",
    )

    code = AGG_SCRIPT.replace("__AS_OF_ISO__", args.as_of)
    exec_result = run_refinery(
        ["exec", "python", "--sandbox", args.sandbox, code],
        "aggregation script",
    )
    if exec_result.get("error"):
        sys.exit(f"Aggregation script raised: {exec_result['error']}")

    marker = "@@RESULT@@"
    payload = None
    for line in exec_result.get("output", []):
        if isinstance(line, str) and line.startswith(marker):
            payload = json.loads(line[len(marker):])
            break
    if payload is None:
        sys.exit("Could not find @@RESULT@@ payload in exec output:\n" + json.dumps(exec_result, indent=2))

    data_window = "Jan 2024 – May 2026 (28 GL periods)"  # update if the source window changes

    html = TEMPLATE_PATH.read_text()
    for key in ("TOP100_AGING_JSON", "FULL_AGING_JSON", "TOP_CUSTOMERS_JSON", "REGISTER_JSON"):
        html = html.replace(f"__{key}__", json.dumps(payload[key], separators=(",", ":")))

    scalar_replacements = {k: v for k, v in payload.items() if not k.endswith("_JSON")}
    scalar_replacements["DATA_WINDOW"] = data_window
    for key, value in scalar_replacements.items():
        html = html.replace(f"__{key}__", str(value))

    leftover = re.findall(r"__[A-Z0-9_]*__", html)
    if leftover:
        print(f"WARNING: unfilled placeholders remain: {sorted(set(leftover))}", file=sys.stderr)

    out_path = Path(args.out)
    out_path.write_text(html)
    print(f"Wrote {out_path} ({len(html):,} bytes)", file=sys.stderr)
    print("Next: publish it with Claude Code's Artifact tool, or open the file directly — it's self-contained.", file=sys.stderr)


if __name__ == "__main__":
    main()
