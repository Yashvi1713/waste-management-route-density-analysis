# KPI Definitions

All numbers are derived from synthetic data. Ratios are calculated from filtered additive measures using sum-over-sum, never by averaging daily ratios. Filters may include `depot`, `service_line`, `fuel_type`, `start`, and `end`.

## Operational KPIs

```text
total_pickups = Σ completed_stops + Σ missed_stops
stops_per_hour = Σ completed_stops / Σ shift_hours
tons_per_hour = Σ tons / Σ shift_hours
missed_rate = Σ missed_stops / (Σ completed_stops + Σ missed_stops)
cost_per_stop = Σ total_cost / Σ completed_stops
fuel_cost_per_km = Σ fuel_cost / Σ km_driven
maint_cost_per_km = Σ maint_cost / Σ km_driven
vehicle_cost_per_km = (Σ fuel_cost + Σ maint_cost) / Σ km_driven
```

Labour is excluded from vehicle cost per kilometre because labour depends on the route rather than the vehicle. Fuel KPIs are calculated by `fuel_type`.

## Route baseline and annual savings

For each route, first calculate its route-level `cost_per_stop`. Then calculate:

```text
median_cost_per_stop = median(route-level cost_per_stop) within service_line
service_days_in_data = count(distinct service_date) in the filtered dataset
annual_savings = max(cost_per_stop - median_cost_per_stop, 0)
                 × completed_stops × 260 / service_days_in_data
```

Residential and commercial routes are never compared with one another. Savings are zero for routes at or below their service-line median.

## Flagging

Within each service line:

- `percent_rank(stops_per_hour) <= 0.10` means `low_density`.
- `percent_rank(cost_per_stop) >= 0.90` means `high_cost`.
- A route is flagged if either condition holds.
- `flag_reason` is `low_density`, `high_cost`, `low_density+high_cost`, or an empty string.

## Worked example

For two R-01/T-001/CNG route days totaling 8 completed stops, 1 missed stop, 4.0 tons, 5.0 hours, 30 km, $150 labour, $18 fuel, and $12 maintenance:

| KPI | Expected |
|---|---:|
| completed_stops | 8 |
| missed_stops | 1 |
| missed_rate | 0.1111 |
| stops_per_hour | 1.6000 |
| tons_per_hour | 0.8000 |
| total_cost | 180.0000 |
| cost_per_stop | 22.5000 |
| fuel_cost_per_km | 0.6000 |
| maint_cost_per_km | 0.4000 |
| vehicle_cost_per_km | 1.0000 |

The incorrect average of daily cost-per-stop ratios is 22.6667 and must not be returned.

## Overview pickup status visual

The Overview displays `total_pickups` as a KPI and a donut chart split into
completed and missed pickup attempts. Both use the same filtered additive
counts as the other dashboard KPIs and respond to depot, service-line,
fuel-type, and date filters.
