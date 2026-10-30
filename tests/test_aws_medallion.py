from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text()


def test_canonical_medallion_paths() -> None:
    config = _read("config.py")
    assert all(zone in config for zone in ('"bronze"', '"silver"', '"gold"'))
    assert "raw" not in config.lower()
    assert "curated" not in config.lower()


def test_terraform_uses_two_glue_etl_jobs() -> None:
    terraform = _read("infra/main.tf")
    assert terraform.count('resource "aws_glue_job"') == 2
    assert "bronze-to-silver" in terraform
    assert "silver-to-gold" in terraform
    assert "aws_lambda" not in terraform


def test_catalog_has_silver_and_gold_tables() -> None:
    terraform = _read("infra/main.tf")
    expected = {
        "trucks", "routes", "customers", "pickups", "route_days", "rejects",
        "load_audit", "dim_truck", "dim_route", "dim_customer", "dim_date",
        "fact_pickup", "fact_route_day", "mart_route_day", "mart_rejects_summary",
        "mart_route_kpis", "mart_fuel_kpis",
    }
    for table in expected:
        assert table in terraform
    assert "aws_glue_catalog_table" in terraform
    assert "crawler" not in terraform.lower()


def test_dashboard_supports_athena_gold_backend() -> None:
    analytics = _read("analytics.py")
    app = _read("app.py")
    assert "ANALYTICS_BACKEND" in analytics + app
    assert "athena" in analytics.lower()
    assert "duckdb" in analytics.lower()


def test_athena_dashboard_preserves_service_date_type() -> None:
    analytics = _read("analytics.py").lower()
    assert "service_date" in analytics
    assert "date" in analytics
    assert "cast" in analytics or "to_datetime" in analytics


def test_deploy_runs_ordered_jobs_and_never_destroys() -> None:
    deploy = _read("scripts/deploy_aws.sh")
    bronze = deploy.find("bronze-to-silver")
    gold = deploy.find("silver-to-gold")
    validate = deploy.find("validate_aws.py")
    assert -1 < bronze < gold < validate
    assert "get-job-run" in deploy
    assert "destroy_aws" not in deploy
    assert "terraform destroy" not in deploy


def test_glue_workflow_visualises_job_dependency_without_schedule() -> None:
    terraform = _read("infra/main.tf")
    assert "aws_glue_workflow" in terraform
    assert 'type     = "ON_DEMAND"' in terraform or 'type = "ON_DEMAND"' in terraform
    assert "enabled" in terraform and "false" in terraform
    assert "SUCCEEDED" in terraform
    assert "CONDITIONAL" in terraform

