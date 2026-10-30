"""AWS Glue 4.0 Bronze-to-Silver validation, quarantine, and reconciliation."""

import sys
from datetime import datetime, timezone

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType


args = getResolvedOptions(sys.argv, ["JOB_NAME", "BUCKET"])
bucket = args["BUCKET"]
bronze = f"s3://{bucket}/bronze"
silver = f"s3://{bucket}/silver"
context = GlueContext(SparkContext.getOrCreate())
spark = context.spark_session
job = Job(context)
job.init(args["JOB_NAME"], args)
loaded_at = datetime.now(timezone.utc).replace(tzinfo=None)


def read_csv(path):
    return spark.read.option("header", True).option("inferSchema", False).csv(path)


def write(frame, name):
    frame.write.mode("overwrite").parquet(f"{silver}/{name}/")


trucks_raw = read_csv(f"{bronze}/trucks.csv")
routes_raw = read_csv(f"{bronze}/routes.csv")
customers_raw = read_csv(f"{bronze}/customers.csv")
pickups_raw = read_csv(f"{bronze}/pickups/*.csv")
route_days_raw = read_csv(f"{bronze}/route_days/*.csv")

trucks = trucks_raw.withColumn("model_year", F.col("model_year").cast(IntegerType()))
routes = routes_raw.withColumn("planned_stops", F.col("planned_stops").cast(IntegerType()))
customers = customers_raw.withColumn("monthly_rate", F.col("monthly_rate").cast(DoubleType()))
truck_ids = trucks.select("truck_id").withColumn("known_truck", F.lit(True))


def deduplicate(frame, keys):
    # Exact planted duplicates are interchangeable; hash provides a stable tie order.
    payload = F.to_json(F.struct(*[F.col(name) for name in frame.columns]))
    ranked = frame.withColumn("_payload", payload).withColumn(
        "_rank", F.row_number().over(Window.partitionBy(*keys).orderBy(F.col("_payload").desc()))
    )
    return ranked.filter(F.col("_rank") == 1).drop("_rank", "_payload")


pickups = deduplicate(pickups_raw, ["pickup_id"])
route_days = deduplicate(route_days_raw, ["service_date", "route_id", "truck_id"])
pickup_duplicates = pickups_raw.count() - pickups.count()
route_day_duplicates = route_days_raw.count() - route_days.count()

pickups_checked = pickups.join(F.broadcast(truck_ids), "truck_id", "left")
tons = F.col("tons").cast(DoubleType())
completed_at = F.to_timestamp("completed_at")
pickup_rule = (
    F.when(~F.col("status").isin("completed", "missed"), "bad_status")
    .when(F.col("known_truck").isNull(), "unknown_truck")
    .when(
        (F.col("status") == "completed") & (tons.isNull() | (tons < 0) | (tons > 12)),
        "tons_out_of_range",
    )
    .when(
        (F.col("status") == "completed")
        & (
            completed_at.isNull()
            | (F.hour(completed_at) < 5)
            | (F.hour(completed_at) >= 20)
        ),
        "outside_shift",
    )
)
pickups_checked = pickups_checked.withColumn("rule", pickup_rule).drop("known_truck")

route_checked = route_days.join(F.broadcast(truck_ids), "truck_id", "left")
hours = F.col("shift_hours").cast(DoubleType())
km = F.col("km_driven").cast(DoubleType())
route_rule = (
    F.when(F.col("known_truck").isNull(), "unknown_truck")
    .when(hours.isNull() | km.isNull() | (hours <= 0) | (km <= 0), "nonpositive_measure")
)
route_checked = route_checked.withColumn("rule", route_rule).drop("known_truck")


def rejects(frame, source):
    source_columns = [name for name in frame.columns if name != "rule"]
    return frame.filter(F.col("rule").isNotNull()).select(
        F.lit(source).alias("source"),
        "rule",
        F.to_json(F.struct(*source_columns)).alias("record"),
        F.lit(loaded_at).cast("timestamp").alias("loaded_at"),
    )


pickup_rejects = rejects(pickups_checked, "pickups")
route_rejects = rejects(route_checked, "route_days")
all_rejects = pickup_rejects.unionByName(route_rejects)

valid_pickups = pickups_checked.filter(F.col("rule").isNull()).select(
    "pickup_id",
    F.to_date("service_date").alias("service_date"),
    "route_id",
    "truck_id",
    "customer_id",
    F.to_timestamp("completed_at").alias("completed_at"),
    tons.alias("tons"),
    "status",
)
valid_route_days = route_checked.filter(F.col("rule").isNull()).select(
    F.to_date("service_date").alias("service_date"),
    "route_id",
    "truck_id",
    *[
        F.col(name).cast(DoubleType()).alias(name)
        for name in ["shift_hours", "km_driven", "labour_cost", "fuel_cost", "maint_cost"]
    ],
)

audit_rows = [
    ("trucks", trucks_raw.count(), 0, 0, trucks.count(), loaded_at),
    ("routes", routes_raw.count(), 0, 0, routes.count(), loaded_at),
    ("customers", customers_raw.count(), 0, 0, customers.count(), loaded_at),
    (
        "pickups",
        pickups_raw.count(),
        pickup_duplicates,
        pickup_rejects.count(),
        valid_pickups.count(),
        loaded_at,
    ),
    (
        "route_days",
        route_days_raw.count(),
        route_day_duplicates,
        route_rejects.count(),
        valid_route_days.count(),
        loaded_at,
    ),
]
audit = spark.createDataFrame(
    audit_rows,
    "source string, raw_rows long, duplicates_removed long, rejected_rows long, silver_rows long, loaded_at timestamp",
)
failures = audit.filter(
    F.col("raw_rows")
    != F.col("silver_rows") + F.col("rejected_rows") + F.col("duplicates_removed")
).count()
if failures:
    raise RuntimeError(f"Silver reconciliation failed for {failures} sources")

for frame, name in [
    (trucks, "trucks"),
    (routes, "routes"),
    (customers, "customers"),
    (valid_pickups, "pickups"),
    (valid_route_days, "route_days"),
    (all_rejects, "rejects"),
    (audit, "load_audit"),
]:
    write(frame, name)

job.commit()

