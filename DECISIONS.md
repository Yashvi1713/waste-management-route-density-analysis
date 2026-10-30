# Decisions

## D-001: Untrusted-cost route days

`mart_route_day` uses an inner join from pickup aggregates to `fact_route_day` on `service_date + route_id + truck_id`. Pickups belonging to a rejected route-day are excluded because they have no trusted cost. The pipeline logs the excluded route-day count.

## D-002: Unspecified implementation details

Where the specification is silent, use the simplest deterministic implementation that preserves the data contract and acceptance criteria.
