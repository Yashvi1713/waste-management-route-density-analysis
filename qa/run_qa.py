"""Validate local Silver and Gold data against the contract and SQL assertions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import DATA_DIR  # noqa: E402


TYPE_FAMILIES = {
    "text": ("VARCHAR",),
    "integer": ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UBIGINT"),
    "float": ("FLOAT", "DOUBLE", "DECIMAL"),
    "date": ("DATE",),
    "timestamp": ("TIMESTAMP",),
    "boolean": ("BOOLEAN",),
}


def _quote(value) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _data_path(spec_path: str, data_dir: Path) -> Path:
    parts = Path(spec_path).parts
    return data_dir.joinpath(*parts[1:]) if parts and parts[0] == "data" else Path(spec_path)


def _contract_checks(connection: duckdb.DuckDBPyConnection, data_dir: Path) -> list[tuple[str, bool, str]]:
    contract = yaml.safe_load((PROJECT_ROOT / "specs/02_data_contract.yaml").read_text())
    results: list[tuple[str, bool, str]] = []
    paths: dict[str, Path] = {}
    for table_name, table in contract["tables"].items():
        path = _data_path(table["path"], data_dir).resolve()
        paths[table_name] = path
        if not path.exists():
            results.append((f"contract:{table_name}", False, f"missing {path}"))
            continue
        relation = f"read_parquet('{path}')"
        schema = {
            row[0]: row[1]
            for row in connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
        }
        violations: list[str] = []
        for column, rules in table["columns"].items():
            if column not in schema:
                violations.append(f"missing column {column}")
                continue
            expected = TYPE_FAMILIES[rules["type"]]
            if not schema[column].startswith(expected):
                violations.append(f"{column} type {schema[column]} != {rules['type']}")
            if not rules.get("nullable", True):
                count = connection.execute(
                    f'SELECT count(*) FROM {relation} WHERE "{column}" IS NULL'
                ).fetchone()[0]
                if count:
                    violations.append(f"{column} has {count} nulls")
            if rules.get("unique"):
                count = connection.execute(
                    f'SELECT count(*)-count(DISTINCT "{column}") FROM {relation}'
                ).fetchone()[0]
                if count:
                    violations.append(f"{column} has {count} duplicate values")
            if "accepted_values" in rules:
                accepted = ",".join(_quote(value) for value in rules["accepted_values"])
                count = connection.execute(
                    f'SELECT count(*) FROM {relation} WHERE "{column}" NOT IN ({accepted})'
                ).fetchone()[0]
                if count:
                    violations.append(f"{column} has {count} unaccepted values")
            for key, operator in (("minimum", "<"), ("maximum", ">"), ("minimum_exclusive", "<=")):
                if key in rules:
                    count = connection.execute(
                        f'SELECT count(*) FROM {relation} WHERE "{column}" {operator} {rules[key]}'
                    ).fetchone()[0]
                    if count:
                        violations.append(f"{column} has {count} values breaking {key}")
        if "minimum_row_count" in table:
            count = connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
            if count < table["minimum_row_count"]:
                violations.append(f"row count {count} below minimum")
        if "compound_unique_key" in table:
            columns = ",".join(f'"{name}"' for name in table["compound_unique_key"])
            count = connection.execute(
                f"SELECT count(*) FROM (SELECT {columns}, count(*) n FROM {relation} GROUP BY {columns} HAVING n > 1)"
            ).fetchone()[0]
            if count:
                violations.append(f"{count} duplicate compound keys")
        results.append((f"contract:{table_name}", not violations, "; ".join(violations)))

    for table_name, table in contract["tables"].items():
        if not paths[table_name].exists():
            continue
        source = f"read_parquet('{paths[table_name]}')"
        for column, rules in table["columns"].items():
            if "foreign_key" not in rules:
                continue
            target_table, target_column = rules["foreign_key"].rsplit(".", 1)
            target = f"read_parquet('{paths[target_table]}')"
            count = connection.execute(
                f'''SELECT count(*) FROM {source} s LEFT JOIN {target} t
                    ON s."{column}" = t."{target_column}"
                    WHERE s."{column}" IS NOT NULL AND t."{target_column}" IS NULL'''
            ).fetchone()[0]
            results.append(
                (
                    f"foreign_key:{table_name}.{column}",
                    count == 0,
                    f"{count} orphan rows" if count else "",
                )
            )
    return results


def _assertions(connection: duckdb.DuckDBPyConnection, data_dir: Path) -> list[tuple[str, bool, str]]:
    silver = data_dir.resolve() / "silver"
    gold = data_dir.resolve() / "gold"
    queries = {
        "silver_rows_reconcile": f"""
            SELECT * FROM read_parquet('{silver / 'load_audit.parquet'}')
            WHERE raw_rows <> silver_rows + rejected_rows + duplicates_removed
        """,
        "completed_stops_match": f"""
            SELECT 1 WHERE
              (SELECT sum(completed_stops) FROM read_parquet('{gold / 'mart_route_day.parquet'}')) <>
              (SELECT sum(completed_stops) FROM read_parquet('{gold / 'mart_route_kpis.parquet'}'))
        """,
        "savings_only_above_median": f"""
            SELECT * FROM read_parquet('{gold / 'mart_route_kpis.parquet'}')
            WHERE annual_savings > 0 AND cost_per_stop <= median_cost_per_stop
        """,
        "route_day_has_attempt": f"""
            SELECT * FROM read_parquet('{gold / 'mart_route_day.parquet'}')
            WHERE completed_stops + missed_stops < 1
        """,
        "rejected_pickup_absent_from_fact": f"""
            SELECT f.pickup_id
            FROM read_parquet('{gold / 'fact_pickup.parquet'}') f
            INNER JOIN read_parquet('{silver / 'rejects.parquet'}') r
              ON f.pickup_id = json_extract_string(r.record, '$.pickup_id')
            WHERE r.source = 'pickups'
        """,
    }
    results = []
    for name, query in queries.items():
        count = len(connection.execute(query).fetchall())
        results.append((f"assertion:{name}", count == 0, f"{count} violations" if count else ""))
    return results


def run_qa(data_dir: str | Path = DATA_DIR, report_path: str | Path = "qa_report.md") -> bool:
    """Run deterministic QA, write a Markdown report, and return overall success."""
    root = Path(data_dir)
    connection = duckdb.connect()
    results = _contract_checks(connection, root) + _assertions(connection, root)
    connection.close()
    lines = ["# QA Report", "", "Synthetic data validation.", ""]
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"{status} {name}{suffix}")
        lines.append(f"- {status}: `{name}`{suffix}")
    success = all(passed for _, passed, _ in results)
    lines.extend(["", f"Overall: {'PASS' if success else 'FAIL'}", ""])
    Path(report_path).write_text("\n".join(lines))
    return success


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raise SystemExit(0 if run_qa() else 1)


if __name__ == "__main__":
    main()
