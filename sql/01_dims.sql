COPY (SELECT * FROM read_parquet('{silver}/trucks.parquet'))
TO '{gold}/dim_truck.parquet' (FORMAT PARQUET);

COPY (SELECT * FROM read_parquet('{silver}/routes.parquet'))
TO '{gold}/dim_route.parquet' (FORMAT PARQUET);

COPY (SELECT * FROM read_parquet('{silver}/customers.parquet'))
TO '{gold}/dim_customer.parquet' (FORMAT PARQUET);

COPY (
    WITH bounds AS (
        SELECT min(service_date) AS first_date, max(service_date) AS last_date
        FROM read_parquet('{silver}/pickups.parquet')
    )
    SELECT
        day::DATE AS service_date,
        strftime(day, '%A') AS day_of_week,
        week(day)::INTEGER AS iso_week,
        month(day)::INTEGER AS month,
        dayofweek(day) IN (0, 6) AS is_weekend
    FROM bounds, generate_series(first_date, last_date, INTERVAL 1 DAY) dates(day)
)
TO '{gold}/dim_date.parquet' (FORMAT PARQUET);

