"""Generate raw source extracts with the problems real ones have.

- merchants_raw: one row per plan change (slowly changing), industry in mixed case with stray
  spaces, signup dates in two formats.
- payments_raw: the same payment re-sent by the API with a later ingested_at (pending, then
  succeeded), amounts as text ("1,234.50", "$89.00"), currency codes in mixed case, timestamps as
  ISO strings or epoch seconds, test-mode payments, a few payments for merchants missing from the
  merchant extract, and a handful of zero or negative amounts.
- refunds_raw, chargebacks_raw: linked to payments by id.
- fx_rates: business-day rates only (no weekends), so conversion needs an as-of join.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "seeds"
START, END = pd.Timestamp("2025-04-01"), pd.Timestamp("2026-09-30")
PLANS = ["standard", "growth", "enterprise"]
INDUSTRIES = ["Retail", "Restaurants", "Software", "Travel", "Health", "Education"]


def merchants(rng, n=1200):
    rows = []
    for i in range(n):
        mid = f"m_{i:05d}"
        signup = START + pd.Timedelta(days=int(rng.integers(0, (END - START).days - 5)))
        ind = rng.choice(INDUSTRIES)
        ind_raw = rng.choice([ind, ind.lower(), ind.upper(), ind + " ", " " + ind])
        country = rng.choice(["US", "US", "US", "GB", "DE", "FR", "CA"])
        fmt = "%Y-%m-%d" if rng.random() < 0.7 else "%m/%d/%Y"
        plan = rng.choice(PLANS, p=[0.7, 0.25, 0.05])
        rows.append((mid, f"Merchant {i:05d} LLC", country, signup.strftime(fmt), ind_raw, plan, signup.strftime("%Y-%m-%d")))
        if plan != "enterprise" and rng.random() < 0.25:             # upgrade later
            up = signup + pd.Timedelta(days=int(rng.integers(30, 300)))
            if up < END:
                rows.append((mid, f"Merchant {i:05d} LLC", country, signup.strftime(fmt), ind_raw,
                             PLANS[PLANS.index(plan) + 1], up.strftime("%Y-%m-%d")))
    return pd.DataFrame(rows, columns=["merchant_id", "legal_name", "country", "signup_date", "industry", "plan", "plan_effective_from"])


def fx(rng):
    days = pd.bdate_range(START - pd.Timedelta(days=10), END)
    rows = []
    for cur, base in (("EUR", 1.08), ("GBP", 1.27), ("CAD", 0.73)):
        r = base * np.exp(np.cumsum(rng.normal(0, 0.003, len(days))))
        rows += [(d.strftime("%Y-%m-%d"), cur, round(v, 5)) for d, v in zip(days, r)]
    rows += [(d.strftime("%Y-%m-%d"), "USD", 1.0) for d in days]
    return pd.DataFrame(rows, columns=["rate_date", "currency", "rate_to_usd"])


def payments(rng, mer):
    first = mer.drop_duplicates("merchant_id")
    cur_by_country = {"US": "USD", "GB": "GBP", "DE": "EUR", "FR": "EUR", "CA": "CAD"}
    rows, pid = [], 0
    for m in first.itertuples(index=False):
        signup = pd.Timestamp(m.plan_effective_from)
        size = rng.lognormal(0, 1.0)
        churn_day = signup + pd.Timedelta(days=int(rng.exponential(420)))
        avg_ticket = rng.lognormal(5.1, 0.7)
        cur = cur_by_country[m.country]
        day = signup
        while day <= min(END, churn_day):
            for _ in range(rng.poisson(0.6 * size)):
                ts = day + pd.Timedelta(seconds=int(rng.integers(0, 86400)))
                amt = round(max(rng.lognormal(np.log(avg_ticket), 0.6), 1.0), 2)
                status = rng.choice(["succeeded", "failed"], p=[0.94, 0.06])
                rows.append([f"py_{pid:07d}", m.merchant_id, ts, amt, cur, status, rng.choice(["visa", "mastercard", "amex"], p=[0.55, 0.35, 0.10]), False])
                pid += 1
            day += pd.Timedelta(days=1)
    p = pd.DataFrame(rows, columns=["payment_id", "merchant_id", "created_at", "amount", "currency", "status", "card_brand", "is_test"])
    return p


def make_messy(rng, p):
    p = p.copy()
    p["ingested_at"] = p["created_at"] + pd.to_timedelta(rng.integers(5, 600, len(p)), unit="s")
    # API retries: pending first, the final status re-sent later
    dup = p.sample(frac=0.04, random_state=1).copy()
    dup["status"] = "pending"
    dup["ingested_at"] = dup["created_at"] + pd.Timedelta(seconds=2)
    p = pd.concat([p, dup], ignore_index=True)
    # test-mode payments
    test = p.sample(400, random_state=2).copy()
    test["payment_id"] = ["py_test_" + str(i) for i in range(len(test))]
    test["is_test"] = True
    # orphans and bad amounts
    orphan = p.sample(150, random_state=3).copy()
    orphan["payment_id"] = ["py_orphan_" + str(i) for i in range(len(orphan))]
    orphan["merchant_id"] = ["m_9" + f"{i:04d}" for i in range(len(orphan))]
    bad = p.sample(40, random_state=4).copy()
    bad["payment_id"] = ["py_bad_" + str(i) for i in range(len(bad))]
    bad["amount"] = rng.choice([0.0, -5.0, -120.0], len(bad))
    p = pd.concat([p, test, orphan, bad], ignore_index=True)
    # formatting mess
    epoch = rng.random(len(p)) < 0.3
    p["created_at"] = np.where(epoch, p["created_at"].astype("datetime64[s]").astype("int64").astype(str),
                               p["created_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    p["ingested_at"] = p["ingested_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    fmt = rng.random(len(p))
    p["amount"] = np.where(fmt < 0.6, p["amount"].map(lambda v: f"{v:.2f}"),
                           np.where(fmt < 0.85, p["amount"].map(lambda v: f"{v:,.2f}"), p["amount"].map(lambda v: f"${v:,.2f}")))
    p["currency"] = np.where(rng.random(len(p)) < 0.2, p["currency"].str.lower(), p["currency"])
    p["status"] = np.where(rng.random(len(p)) < 0.1, p["status"].str.upper(), p["status"])
    return p.sample(frac=1, random_state=5).reset_index(drop=True)


def refunds_chargebacks(rng, p):
    ok = p[p["status"] == "succeeded"]
    r = ok.sample(frac=0.045, random_state=6)
    ramt = r["amount"] * np.where(rng.random(len(r)) < 0.7, 1.0, rng.uniform(0.2, 0.8, len(r)))
    rts = r["created_at"] + pd.to_timedelta(rng.integers(1, 20, len(r)), unit="D")
    refunds = pd.DataFrame({"refund_id": [f"re_{i:06d}" for i in range(len(r))], "payment_id": r["payment_id"].to_numpy(),
                            "amount": ramt.round(2).to_numpy(), "created_at": rts.dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy()})
    refunds = refunds[(rts <= END + pd.Timedelta(days=1)).to_numpy()]
    c = ok.sample(frac=0.006, random_state=7)
    cts = c["created_at"] + pd.to_timedelta(rng.integers(5, 60, len(c)), unit="D")
    cbs = pd.DataFrame({"chargeback_id": [f"cb_{i:05d}" for i in range(len(c))], "payment_id": c["payment_id"].to_numpy(),
                        "amount": c["amount"].round(2).to_numpy(),
                        "reason_code": rng.choice(["fraudulent", "product_not_received", "duplicate", "subscription_canceled"], len(c)),
                        "opened_at": cts.dt.strftime("%Y-%m-%d").to_numpy(),
                        "status": rng.choice(["lost", "won", "open"], len(c), p=[0.6, 0.3, 0.1])})
    cbs = cbs[(cts <= END).to_numpy()]
    return refunds, cbs


def main(seed=17):
    rng = np.random.default_rng(seed)
    SEEDS.mkdir(exist_ok=True)
    mer = merchants(rng)
    clean = payments(rng, mer)
    refunds, cbs = refunds_chargebacks(rng, clean)
    p = make_messy(rng, clean)
    mer.to_csv(SEEDS / "merchants_raw.csv", index=False)
    p.to_csv(SEEDS / "payments_raw.csv", index=False)
    refunds.to_csv(SEEDS / "refunds_raw.csv", index=False)
    cbs.to_csv(SEEDS / "chargebacks_raw.csv", index=False)
    fx(rng).to_csv(SEEDS / "fx_rates.csv", index=False)
    return {"merchants_raw": len(mer), "payments_raw": len(p), "refunds_raw": len(refunds), "chargebacks_raw": len(cbs)}


if __name__ == "__main__":
    print(main())
