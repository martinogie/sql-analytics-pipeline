"""Generate raw data if needed, build every model, run tests and metrics, and write the docs site.

    python -m pipeline.run              # build + test + docs
    python -m pipeline.run --regenerate # also regenerate the raw seed extracts
"""
import argparse
import json
import time
from pathlib import Path

import pandas as pd

from . import generate
from .runner import Project

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def quality_funnel(con):
    q = lambda sql: con.execute(sql).fetchone()[0]
    raw = q("select count(*) from payments_raw")
    distinct = q("select count(distinct payment_id) from payments_raw")
    tests = q("select count(distinct payment_id) from payments_raw where lower(is_test) = 'true'")
    stg = q("select count(*) from stg_payments")
    quarantine = q("select count(*) from quarantine_payments")
    fct = q("select count(*) from fct_payments")
    return [
        {"step": "Raw payment events", "rows": raw, "note": "as delivered by the API extract"},
        {"step": "Retried events collapsed", "rows": distinct, "note": f"{raw - distinct:,} duplicate events (pending then final status)"},
        {"step": "Test-mode payments removed", "rows": stg, "note": f"{tests:,} test payments"},
        {"step": "Valid, in fct_payments", "rows": fct, "note": f"{quarantine:,} quarantined: unknown merchant or non-positive amount"},
    ], {
        "epoch_timestamps": q("select count(*) from payments_raw where created_at not like '%-%'"),
        "text_amounts": q("select count(*) from payments_raw where amount like '%,%' or amount like '$%'"),
        "lowercase_currency": q("select count(*) from payments_raw where currency <> upper(currency)"),
        "non_usd_payments": q("select count(*) from fct_payments where currency <> 'USD'"),
        "weekend_fx_days_filled": q("select count(*) from int_fx_daily where strftime('%w', rate_date) in ('0','6')"),
        "plan_changes": q("select count(*) from stg_merchants where is_current = 0"),
        "industry_variants_fixed": q("select count(distinct industry) from merchants_raw") - q("select count(distinct industry) from stg_merchants"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerate", action="store_true")
    args = ap.parse_args(argv)
    if args.regenerate or not (ROOT / "seeds" / "payments_raw.csv").exists():
        print("seeds:", generate.main())
    REPORTS.mkdir(exist_ok=True)
    t0 = time.time()
    p = Project()
    con = p.connect()
    seeds = p.load_seeds(con)
    built = p.build(con)
    build_s = time.time() - t0
    tests = p.test(con)
    metrics = p.run_metrics(con)
    funnel, fixes = quality_funnel(con)
    kpis = pd.read_sql_query("select * from mart_kpis_monthly", con)
    cohorts = pd.read_sql_query("select cohort_month, months_since_first, retention from mart_cohort_retention", con)
    plans = pd.read_sql_query("select payment_month, plan, round(sum(case when status='succeeded' then amount_usd end), 2) as gmv "
                              "from fct_payments group by 1, 2 order by 1, 2", con)

    docs = p.columns_doc()
    rows = {r["model"]: r for r in built}
    nodes = [{"id": s, "layer": "sources", "rows": n, "description": "Raw extract loaded from seeds/" + s + ".csv", "columns": [],
              "sql": "", "refs": []} for s, n in seeds.items()]
    for name in p.order():
        m = p.models[name]
        d = docs.get(name, {})
        nodes.append({"id": name, "layer": m.layer, "rows": rows[name]["rows"], "seconds": rows[name]["seconds"],
                      "description": m.description or d.get("description", ""), "sql": m.raw,
                      "refs": m.refs + m.sources,
                      "columns": [{"name": c, "description": d.get("columns", {}).get(c, "")} for c in rows[name]["columns"]]})
    run_results = {
        "built_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "models": len(built),
        "build_seconds": round(build_s, 1), "tests": len(tests), "passed": sum(t["status"] == "pass" for t in tests),
        "seed_rows": seeds, "model_rows": {r["model"]: r["rows"] for r in built},
    }
    (REPORTS / "run_results.json").write_text(json.dumps(run_results, indent=2))
    pd.DataFrame(tests).drop(columns="sql").to_csv(REPORTS / "test_results.csv", index=False)
    kpis.to_csv(REPORTS / "kpis_monthly.csv", index=False)
    (REPORTS / "compiled_metrics.sql").write_text("\n\n".join(f"-- {k}: {v['label']}\n{v['sql']};" for k, v in metrics.items()))

    page = {"run": run_results, "nodes": nodes, "tests": tests, "metrics": metrics, "funnel": funnel, "fixes": fixes,
            "kpis": kpis.where(kpis.notna(), None).to_dict("records"),
            "cohorts": cohorts.to_dict("records"), "plans": plans.to_dict("records")}
    html = (ROOT / "web" / "template.html").read_text().replace("/*DATA*/null", json.dumps(page, separators=(",", ":")))
    (ROOT / "index.html").write_text(html)
    print(json.dumps(run_results, indent=1))
    print(funnel, fixes)
    fails = [t for t in tests if t["status"] != "pass"]
    if fails:
        raise SystemExit(f"{len(fails)} tests failed: {[t['test'] for t in fails]}")


if __name__ == "__main__":
    main()
