# Business Goal

All reported numbers are based on synthetic data.

## Primary question

Which collection routes cost the most per stop, and what would we save per year by bringing them to the median route of the same service line?

## Secondary questions

- Are low-density routes also worse at missed pickups?
- Is CNG cheaper per kilometre than diesel?

## Scope

The project models a waste-collection company that earns revenue per stop and pays for driver time, fuel, and truck wear. It uses 40 synthetic routes across Vaughan, Brampton, and Mississauga, with residential and commercial routes compared only within their own service line. R-04, R-17, and R-29 are deliberately inefficient residential routes.

## Architecture and guarantees

The canonical architecture is **Bronze → Silver → Gold**.

### Bronze

- Immutable, replayable source extracts under `data/bronze` or `s3://<bucket>/bronze/`.
- Original CSV values are preserved, including malformed values.
- Planted errors survive long enough to be evaluated.

### Silver

- Typed, deduplicated, contract-valid operational data under `data/silver` or `s3://<bucket>/silver/`.
- Invalid records are retained in `rejects`; every source is represented in `load_audit`.
- For every source: `raw_rows = silver_rows + rejected_rows + duplicates_removed`.

### Gold

- Conformed dimensions, natural-grain facts, and additive marts under `data/gold` or `s3://<bucket>/gold/`.
- Pickup facts and route-day cost facts remain separate to prevent duplicated costs.
- Marts contain counts and sums only; all ratios are calculated in `kpis.py` using sum-over-sum.

## Delivery

The local implementation uses Python, Parquet, and DuckDB. The AWS implementation uses S3, Glue Spark, explicit Glue Catalog tables, and Athena. Streamlit runs locally against either DuckDB or Athena. AWS resources default to project `route-lab` in `eu-west-1`.
