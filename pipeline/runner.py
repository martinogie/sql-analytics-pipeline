"""A small dbt-style runner for SQLite.

- Models are .sql files under models/<layer>/. They reference each other with {{ ref('name') }}
  and raw tables with {{ source('raw', 'name') }}; the runner builds the dependency graph from
  those references and builds models in order, as tables.
- The first comment lines of each model are its description.
- models/schema.yml holds column docs and generic tests (unique, not_null, accepted_values,
  relationships, expression). data_tests/*.sql are singular tests: any row returned is a failure.
- metrics/metrics.yml holds metric definitions that are compiled to SQL by month.
"""
import re
import sqlite3
import time
from graphlib import TopologicalSorter
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
REF = re.compile(r"\{\{\s*ref\('(\w+)'\)\s*\}\}")
SOURCE = re.compile(r"\{\{\s*source\('(\w+)',\s*'(\w+)'\)\s*\}\}")


class Model:
    def __init__(self, path):
        self.path = path
        self.name = path.stem
        self.layer = path.parent.name
        self.raw = path.read_text()
        self.refs = sorted(set(REF.findall(self.raw)))
        self.sources = sorted({t for _, t in SOURCE.findall(self.raw)})
        lines = []
        for line in self.raw.splitlines():
            if line.startswith("--"):
                lines.append(line[2:].strip())
            else:
                break
        self.description = " ".join(lines)

    def compiled(self):
        return SOURCE.sub(lambda m: m.group(2), REF.sub(lambda m: m.group(1), self.raw))


class Project:
    def __init__(self, root=ROOT, db=None):
        self.root = root
        self.db_path = db or root / "warehouse.db"
        self.models = {m.stem: Model(m) for m in sorted((root / "models").rglob("*.sql"))}
        self.schema = yaml.safe_load((root / "models" / "schema.yml").read_text())["models"]
        self.metrics = yaml.safe_load((root / "metrics" / "metrics.yml").read_text())["metrics"]
        self.singular = {p.stem: p.read_text() for p in sorted((root / "data_tests").glob("*.sql"))}

    def order(self):
        ts = TopologicalSorter({n: set(m.refs) for n, m in self.models.items()})
        return list(ts.static_order())

    def connect(self):
        return sqlite3.connect(self.db_path)

    def load_seeds(self, con):
        out = {}
        for p in sorted((self.root / "seeds").glob("*.csv")):
            df = pd.read_csv(p, dtype=str, keep_default_na=False)
            df.to_sql(p.stem, con, if_exists="replace", index=False)
            out[p.stem] = len(df)
        return out

    def build(self, con):
        results = []
        for name in self.order():
            m = self.models[name]
            t0 = time.time()
            con.execute(f"drop table if exists {name}")
            con.execute(f"create table {name} as {m.compiled()}")
            # post-hook: index id columns so joins and tests downstream stay fast
            cols = [r[1] for r in con.execute(f"pragma table_info({name})")]
            for c in ("payment_id", "merchant_id"):
                if c in cols:
                    con.execute(f"create index if not exists ix_{name}_{c} on {name}({c})")
            rows = con.execute(f"select count(*) from {name}").fetchone()[0]
            results.append({"model": name, "layer": m.layer, "rows": rows, "seconds": round(time.time() - t0, 2),
                            "columns": cols})
        con.commit()
        return results

    def _generic(self, model, column, test):
        if isinstance(test, str):
            kind, arg = test, None
        else:
            kind, arg = next(iter(test.items()))
        if kind == "unique":
            sql = f"select {column}, count(*) from {model} group by {column} having count(*) > 1"
        elif kind == "not_null":
            sql = f"select * from {model} where {column} is null"
        elif kind == "accepted_values":
            vals = ", ".join(f"'{v}'" for v in arg["values"])
            sql = f"select {column}, count(*) from {model} where {column} not in ({vals}) group by {column}"
        elif kind == "relationships":
            sql = (f"select c.{column} from {model} c left join {arg['to']} p on p.{arg['field']} = c.{column} "
                   f"where c.{column} is not null and p.{arg['field']} is null")
        elif kind == "expression":
            sql = f"select * from {model} where not ({arg['expr']})"
        else:
            raise ValueError(kind)
        label = kind if kind != "expression" else f"expression: {arg['expr']}"
        if kind == "accepted_values":
            label = "accepted_values: " + ", ".join(arg["values"])
        if kind == "relationships":
            label = f"relationships: {arg['to']}.{arg['field']}"
        return label, sql

    def test(self, con):
        results = []
        for m in self.schema:
            for col in m.get("columns", []):
                for t in col.get("tests", []):
                    label, sql = self._generic(m["name"], col["name"], t)
                    n = con.execute(f"select count(*) from ({sql})").fetchone()[0]
                    results.append({"model": m["name"], "column": col["name"], "test": label, "failures": n,
                                    "status": "pass" if n == 0 else "fail", "sql": sql})
        for name, raw in self.singular.items():
            sql = SOURCE.sub(lambda mm: mm.group(2), REF.sub(lambda mm: mm.group(1), raw))
            body = "\n".join(l for l in sql.splitlines() if not l.startswith("--"))
            n = con.execute(f"select count(*) from ({body})").fetchone()[0]
            results.append({"model": ", ".join(sorted(set(REF.findall(raw)))), "column": "", "test": name, "failures": n,
                            "status": "pass" if n == 0 else "fail", "sql": body.strip()})
        return results

    def compile_metric(self, m):
        flt = f"\nwhere {m['filter']}" if m.get("filter") else ""
        if m["type"] == "sum":
            agg = f"sum({m['expression']})"
        elif m["type"] == "count_distinct":
            agg = f"count(distinct {m['expression']})"
        elif m["type"] == "ratio":
            agg = f"sum({m['numerator']}) * 1.0 / nullif(sum({m['denominator']}), 0)"
        return (f"select strftime('%Y-%m', created_date) as month,\n       {agg} as {m['name']}\n"
                f"from {m['model']}{flt}\ngroup by 1\norder by 1")

    def run_metrics(self, con):
        out = {}
        for m in self.metrics:
            sql = self.compile_metric(m)
            df = pd.read_sql_query(sql, con)
            out[m["name"]] = {"label": m["label"], "description": m["description"], "sql": sql,
                              "values": df.to_dict("records")}
        return out

    def columns_doc(self):
        docs = {}
        for m in self.schema:
            docs[m["name"]] = {"description": m.get("description", ""),
                               "columns": {c["name"]: c.get("description", "") for c in m.get("columns", [])}}
        return docs
