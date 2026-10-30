COPY (
    SELECT
        pickup_id,
        service_date,
        route_id,
        truck_id,
        customer_id,
        completed_at::TIMESTAMP AS completed_at,
        tons,
        status = 'completed' AS is_completed,
        status = 'missed' AS is_missed
    FROM read_parquet('{silver}/pickups.parquet')
)
TO '{gold}/fact_pickup.parquet' (FORMAT PARQUET);

COPY (
    SELECT
        service_date,
        route_id,
        truck_id,
        shift_hours,
        km_driven,
        labour_cost,
        fuel_cost,
        maint_cost,
        labour_cost + fuel_cost + maint_cost AS total_cost
    FROM read_parquet('{silver}/route_days.parquet')
)
TO '{gold}/fact_route_day.parquet' (FORMAT PARQUET);

