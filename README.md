# Route Density Lab

A complete synthetic-data project for identifying waste-collection routes with high cost per completed stop and estimating annual savings from reaching the median route in the same service line.

> All data and dashboard numbers are synthetic.

## Architecture

`Bronze → Silver → Gold`

- Bronze contains immutable replayable CSV extracts.
- Silver contains typed, deduplicated operational records, rejects, and load audit.
- Gold contains conformed dimensions, separate natural-grain facts, additive marts, and KPI tables.
- Ratios are defined once in `kpis.py` and always use sum-over-sum.

Local processing uses Python, Parquet, and DuckDB. AWS processing uses S3, two Glue Spark jobs, explicit Glue Catalog tables, and Athena. Streamlit remains local and supports either backend.

## Local workflow

Python 3.11 or newer is required.

```bash
make setup
make all
make app
```

Individual commands are `make data`, `make pipeline`, `make test`, and `make qa`.

Local dashboard:

```bash
ANALYTICS_BACKEND=local .venv/bin/streamlit run app.py
```

## AWS deployment

Review the Terraform plan before approval:

```bash
terraform -chdir=infra init
terraform -chdir=infra plan -var='project=route-lab' -var='aws_region=eu-west-1'
```

Deploy only after reviewing the plan:

```bash
PROJECT=route-lab AWS_REGION=eu-west-1 make deploy
```

The deployment script prints caller identity, provisions Terraform, uploads Bronze, runs Bronze-to-Silver and then Silver-to-Gold, runs Athena QA, and leaves resources deployed.

AWS-backed local dashboard:

```bash
ANALYTICS_BACKEND=athena \
AWS_REGION=eu-west-1 \
AWS_SILVER_DATABASE=route_lab_silver \
AWS_GOLD_DATABASE=route_lab_gold \
ATHENA_WORKGROUP=route-lab \
.venv/bin/streamlit run app.py --server.port 8503
```

Destroy only when finished testing:

```bash
PROJECT=route-lab AWS_REGION=eu-west-1 make destroy
```

The destroy command removes only resources tracked in this project’s Terraform state.
