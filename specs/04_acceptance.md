# Acceptance Criteria

## Generator

- AC-G1: Same seed produces byte-identical output. `tests/test_generate.py::test_same_seed_same_output`
- AC-G2: Planted pickup error rate is between 2% and 4%. `tests/test_generate.py::test_planted_error_rate`
- AC-G3: Clean rows reference existing dimensions. `tests/test_generate.py::test_clean_rows_reference_dimensions`

## Quality

- AC-Q1: Duplicate pickups are removed and counted. `tests/test_quality.py::test_duplicates_removed`
- AC-Q2: Invalid completed tonnage is rejected. `tests/test_quality.py::test_tons_rule`
- AC-Q3: Unknown trucks are rejected. `tests/test_quality.py::test_unknown_truck_rule`
- AC-Q4: Completed pickups outside the shift are rejected. `tests/test_quality.py::test_outside_shift_rule`
- AC-Q5: Invalid statuses are rejected. `tests/test_quality.py::test_bad_status_rule`
- AC-Q6: Non-positive route-day measures are rejected. `tests/test_quality.py::test_route_day_rule`
- AC-Q7: Bronze rows reconcile to Silver, rejects, and duplicates. `tests/test_pipeline_e2e.py::test_rows_reconcile`

## KPIs

- AC-K1: Worked-example KPIs match to four decimal places. `tests/test_kpis.py::test_worked_example`
- AC-K2: Ratios use sum-over-sum. `tests/test_kpis.py::test_ratios_are_sum_over_sum`
- AC-K3: Total pickups equals filtered completed plus missed pickup attempts. `tests/test_kpis.py::test_total_pickups_is_completed_plus_missed`

## End to end

- AC-E1: Gold dimensions, facts, and marts exist and are non-empty. `tests/test_pipeline_e2e.py::test_marts_built`
- AC-E2: The contract passes. `tests/test_pipeline_e2e.py::test_contract_passes`
- AC-E3: R-04, R-17, and R-29 are flagged. `tests/test_pipeline_e2e.py::test_planted_routes_flagged`
- AC-E4: Streamlit chart calls use arguments supported by the installed Streamlit version. `tests/test_app.py::test_altair_chart_arguments_match_installed_streamlit`
- AC-E5: Canonical storage zones are named Bronze, Silver, and Gold. `tests/test_aws_medallion.py::test_canonical_medallion_paths`
- AC-E6: Terraform creates separate Bronze-to-Silver and Silver-to-Gold Glue jobs, and Lambda does not perform batch ETL. `tests/test_aws_medallion.py::test_terraform_uses_two_glue_etl_jobs`
- AC-E7: Explicit Catalog tables expose all required Silver and Gold datasets. `tests/test_aws_medallion.py::test_catalog_has_silver_and_gold_tables`
- AC-E8: Streamlit supports local DuckDB and AWS Athena modes and preserves date types in filtered queries. `tests/test_aws_medallion.py::test_dashboard_supports_athena_gold_backend`, `tests/test_aws_medallion.py::test_athena_dashboard_preserves_service_date_type`
- AC-E9: Deployment uploads Bronze, executes both Glue jobs sequentially, runs AWS QA, and does not automatically destroy resources. `tests/test_aws_medallion.py::test_deploy_runs_ordered_jobs_and_never_destroys`
- AC-E10: An unscheduled Glue Workflow connects both jobs through a success-only condition and its start trigger is disabled at rest. `tests/test_aws_medallion.py::test_glue_workflow_visualises_job_dependency_without_schedule`
- AC-E11: Overview shows a Total pickups KPI and completed-versus-missed donut chart. `tests/test_app.py::test_overview_has_pickup_total_and_status_donut`

## Deterministic QA assertions

Each assertion returns violating records; zero rows means PASS:

- Silver audit rows reconcile.
- Completed-stop totals agree between `mart_route_day` and `mart_route_kpis`.
- Savings occur only above the service-line median.
- Every `mart_route_day` row contains at least one attempted stop.
- No rejected pickup appears in `fact_pickup`.

AWS QA additionally verifies unique `fact_pickup` keys, unique `fact_route_day` compound grains, and non-empty Gold marts.
