# SQL Analytics Pipeline

A tested SQL pipeline that turns messy payment-API extracts into documented KPI tables for finance.
It is built in the dbt style:
- **staging** models that clean and de-duplicate,
- **intermediate** models that convert currency and join slowly changing merchant plans,
- **marts** that serve monthly KPIs and cohorts,
- **data tests** on every layer,
- a **metrics layer** that defines each KPI once,
- a **lineage docs site**.

It runs on SQLite with a small Python runner (about 200 lines). The SQL itself is portable to
Snowflake, BigQuery or Postgres.

**[Open the docs site](https://martinogie.github.io/sql-analytics-pipeline/)**: click any model
in the lineage graph to see its SQL, columns and tests.

## Results

| | |
|---|---|
| Models | 13 (5 staging, 3 intermediate, 5 marts), built in about 8 seconds |
| Data tests | **28 of 28 passing**: 25 generic and 3 singular |
| Raw payment events | 258,344 |
| Rows in `fct_payments` | 247,840 |

What the pipeline fixed in the raw data:

| Problem in the extract | Rows | Fix |
|---|---|---|
| API retries (same payment sent as pending, then final) | 9,914 | `row_number()` over `payment_id`, keeping the latest `ingested_at` |
| Test-mode payments | 400 | Filtered in staging |
| Timestamps as epoch seconds instead of ISO | 77,735 | `case` parse to UTC |
| Amounts as text: "1,234.50", "$89.00" | 39,980 | Strip and cast |
| Lower-case currency codes | 51,769 | `upper(trim())` |
| Non-USD payments (EUR, GBP, CAD) | 146,695 | As-of FX join on a recursive date spine (weekends take Friday's rate) |
| Merchant plan changes | 189 | Type-2 slowly changing dimension with `lead()`; each payment is priced at the plan in force that day |
| Industry spelled 30 different ways | 24 variants merged | Trim and title-case |
| Unknown merchant or non-positive amount | 190 | Moved to `quarantine_payments` with a reason, not dropped silently |

## Models

```
sources (seeds/*.csv)      staging              intermediate              marts
payments_raw      ──▶  stg_payments   ─┐
fx_rates          ──▶  stg_fx_rates   ─┼─▶ int_fx_daily ─┐
merchants_raw     ──▶  stg_merchants  ─┤                 ├─▶ int_payments_enriched ─┬─▶ fct_payments ─┬─▶ dim_merchants
refunds_raw       ──▶  stg_refunds    ─┤                 │                          │                 ├─▶ mart_merchant_monthly ─┬─▶ mart_kpis_monthly
chargebacks_raw   ──▶  stg_chargebacks ┘                 │                          └─▶ quarantine_payments                     └─▶ mart_cohort_retention
```

`mart_kpis_monthly` reports, by month:
- GMV and net revenue,
- take rate, authorisation rate, refund rate and chargeback rate,
- active, new and churned merchants,
- month-over-month growth (`lag()`).

## Tests

- **Generic** (in `models/schema.yml`): `unique`, `not_null`, `accepted_values`, `relationships`, and `expression` (for example, `amount_usd > 0` or `take_rate between 0.02 and 0.04`).
- **Singular** (in `data_tests/`):
  - `assert_gmv_reconciles`: monthly GMV in the KPI mart equals the fact table to the cent.
  - `assert_every_payment_accounted_for`: every de-duplicated payment is in exactly one of the fact or quarantine tables.
  - `assert_one_plan_version_per_day`: plan versions never overlap, so the type-2 join returns one plan.
- **Unit tests** (`tests/`): break a copy of the warehouse (duplicate a payment, orphan a merchant, drift GMV, add an unknown status) and check that the right data test fails.

## Metrics layer

`metrics/metrics.yml` defines GMV, net revenue, take rate, refund rate, authorisation rate and
active merchants once. The runner compiles each into SQL ([reports/compiled_metrics.sql](reports/compiled_metrics.sql)),
for example:

```sql
select strftime('%Y-%m', created_date) as month,
       sum(fee_revenue_usd) * 1.0 / nullif(sum(case when status = 'succeeded' then amount_usd else 0 end), 0) as take_rate
from fct_payments
group by 1
order by 1;
```

## Quick start

```bash
pip install -r requirements.txt
python -m pipeline.run                    # generate raw extracts if missing, build, test, metrics, docs (~30s first time)
python -m unittest discover -s tests      # 9 tests
sqlite3 warehouse.db "select * from mart_kpis_monthly"
```

## Layout

```
models/staging, models/intermediate, models/marts   SQL models
models/schema.yml                                   column docs and generic tests
data_tests/                                         singular SQL tests
metrics/metrics.yml                                 metric definitions
pipeline/runner.py                                  ref parsing, DAG, build, tests, metric compiler
pipeline/generate.py                                synthetic raw extracts with realistic defects
pipeline/run.py                                     CLI and docs site
seeds/sample/                                       first 25 rows of each raw extract
```

## Data note

The source extracts are synthetic: 1,200 merchants and 18 months of payments, generated with the
defects listed above.

## How this was built

Built with AI-assisted coding (Claude). The modelling, tests and review are my own.

## License

MIT
