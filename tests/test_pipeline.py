"""The pipeline builds, its tests pass, and its tests actually catch broken data."""
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline import generate
from pipeline.runner import Project

ROOT = Path(__file__).resolve().parent.parent


class Built:
    tmp = Path(tempfile.mkdtemp())
    if not (ROOT / "seeds" / "payments_raw.csv").exists():
        generate.main()
    project = Project(db=tmp / "test.db")
    con = project.connect()
    project.load_seeds(con)
    built = project.build(con)


def failures(test_name, column=""):
    res = Built.project.test(Built.con)
    return [r for r in res if r["test"].startswith(test_name) and (not column or r["column"] == column)]


class TestBuild(unittest.TestCase):
    def test_dependency_order(self):
        order = Built.project.order()
        self.assertLess(order.index("stg_payments"), order.index("int_payments_enriched"))
        self.assertLess(order.index("fct_payments"), order.index("mart_kpis_monthly"))

    def test_all_tests_pass_on_clean_build(self):
        res = Built.project.test(Built.con)
        self.assertTrue(all(r["status"] == "pass" for r in res), [r["test"] for r in res if r["status"] != "pass"])

    def test_retried_events_collapse_to_final_status(self):
        q = Built.con.execute(
            "select count(*) from stg_payments s where s.status = 'pending' and s.payment_id in "
            "(select payment_id from payments_raw group by payment_id having count(*) > 1)").fetchone()[0]
        self.assertEqual(q, 0)

    def test_epoch_and_iso_timestamps_both_parse(self):
        q = Built.con.execute("select min(created_date), max(created_date) from stg_payments").fetchone()
        self.assertGreaterEqual(q[0], "2025-04-01")
        self.assertLessEqual(q[1], "2026-10-01")

    def test_weekend_fx_filled_from_friday(self):
        sat, fri = Built.con.execute(
            "select a.rate_to_usd, b.rate_to_usd from int_fx_daily a join int_fx_daily b "
            "on a.currency = b.currency and b.rate_date = date(a.rate_date, '-1 day') "
            "where a.currency = 'EUR' and strftime('%w', a.rate_date) = '6' limit 1").fetchone()
        self.assertEqual(sat, fri)


class TestTestsCatchProblems(unittest.TestCase):
    """Break the built tables on a copy and check the right test fails."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(Built.project.db_path, self.tmp / "broken.db")
        self.p = Project(db=self.tmp / "broken.db")
        self.con = self.p.connect()

    def run_tests(self):
        return {(r["model"], r["column"], r["test"]): r["status"] for r in self.p.test(self.con)}

    def test_duplicate_payment_is_caught(self):
        self.con.execute("insert into fct_payments select * from fct_payments limit 1")
        self.assertEqual(self.run_tests()[("fct_payments", "payment_id", "unique")], "fail")

    def test_orphan_merchant_is_caught(self):
        self.con.execute("update fct_payments set merchant_id = 'm_missing' where rowid = 1")
        self.assertEqual(self.run_tests()[("fct_payments", "merchant_id", "relationships: dim_merchants.merchant_id")], "fail")

    def test_gmv_drift_is_caught(self):
        self.con.execute("update mart_kpis_monthly set gmv_usd = gmv_usd + 1 where rowid = 1")
        res = self.run_tests()
        key = [k for k in res if k[2] == "assert_gmv_reconciles"][0]
        self.assertEqual(res[key], "fail")

    def test_unknown_status_is_caught(self):
        self.con.execute("update stg_payments set status = 'settled' where rowid = 1")
        key = ("stg_payments", "status", "accepted_values: succeeded, failed, pending")
        self.assertEqual(self.run_tests()[key], "fail")


if __name__ == "__main__":
    unittest.main()
