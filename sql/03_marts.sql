COPY (
    WITH pickup_rollup AS (
        SELECT
            service_date,
            route_id,
            truck_id,
            count(*) FILTER (WHERE is_completed)::BIGINT AS completed_stops,
            count(*) FILTER (WHERE is_missed)::BIGINT AS missed_stops,
            coalesce(sum(tons), 0)::DOUBLE AS tons
        FROM read_parquet('{gold}/fact_pickup.parquet')
        GROUP BY service_date, route_id, truck_id
    )
    SELECT
        p.service_date,
        p.route_id,
        p.truck_id,
        r.depot,
        r.service_line,
        t.fuel_type,
        p.completed_stops,
        p.missed_stops,
        p.tons,
        f.shift_hours,
        f.km_driven,
        f.labour_cost,
        f.fuel_cost,
        f.maint_cost,
        f.total_cost
    FROM pickup_rollup p
    INNER JOIN read_parquet('{gold}/fact_route_day.parquet') f
      USING (service_date, route_id, truck_id)
    INNER JOIN read_parquet('{gold}/dim_route.parquet') r USING (route_id)
    INNER JOIN read_parquet('{gold}/dim_truck.parquet') t USING (truck_id)
)
TO '{gold}/mart_route_day.parquet' (FORMAT PARQUET);

COPY (
    SELECT source, rule, count(*)::BIGINT AS rejected_rows
    FROM read_parquet('{silver}/rejects.parquet')
    GROUP BY source, rule
)
TO '{gold}/mart_rejects_summary.parquet' (FORMAT PARQUET);

