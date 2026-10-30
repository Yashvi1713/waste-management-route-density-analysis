"""AWS Glue 4.0 Silver-to-Gold dimensional model and marts."""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import Window
from pyspark.sql import functions as F


args = getResolvedOptions(sys.argv, ["JOB_NAME", "BUCKET"])
bucket = args["BUCKET"]
silver = f"s3://{bucket}/silver"
gold = f"s3://{bucket}/gold"
context = GlueContext(SparkContext.getOrCreate())
spark = context.spark_session
job = Job(context)
job.init(args["JOB_NAME"], args)


def read(name):
    return spark.read.parquet(f"{silver}/{name}/")


def write(frame, name):
    frame.write.mode("overwrite").parquet(f"{gold}/{name}/")


trucks, routes, customers = read("trucks"), read("routes"), read("customers")
pickups, route_days, rejects = read("pickups"), read("route_days"), read("rejects")
dim_truck, dim_route, dim_customer = trucks, routes, customers
bounds = pickups.agg(F.min("service_date").alias("start"), F.max("service_date").alias("end"))
dim_date = bounds.select(F.explode(F.sequence("start", "end")).alias("service_date")).select(
    "service_date",
    F.date_format("service_date", "EEEE").alias("day_of_week"),
    F.weekofyear("service_date").alias("iso_week"),
    F.month("service_date").alias("month"),
    (F.dayofweek("service_date").isin(1, 7)).alias("is_weekend"),
)
fact_pickup = pickups.select(
    "pickup_id", "service_date", "route_id", "truck_id", "customer_id",
    F.col("completed_at").cast("timestamp").alias("completed_at"), "tons",
    (F.col("status") == "completed").alias("is_completed"),
    (F.col("status") == "missed").alias("is_missed"),
)
fact_route_day = route_days.withColumn(
    "total_cost", F.col("labour_cost") + F.col("fuel_cost") + F.col("maint_cost")
)
pickup_rollup = fact_pickup.groupBy("service_date", "route_id", "truck_id").agg(
    F.sum(F.col("is_completed").cast("long")).alias("completed_stops"),
    F.sum(F.col("is_missed").cast("long")).alias("missed_stops"),
    F.coalesce(F.sum("tons"), F.lit(0.0)).alias("tons"),
)
mart_route_day = (
    pickup_rollup.join(fact_route_day, ["service_date", "route_id", "truck_id"], "inner")
    .join(dim_route.select("route_id", "depot", "service_line"), "route_id")
    .join(dim_truck.select("truck_id", "fuel_type"), "truck_id")
    .select(
        "service_date", "route_id", "truck_id", "depot", "service_line", "fuel_type",
        "completed_stops", "missed_stops", "tons", "shift_hours", "km_driven",
        "labour_cost", "fuel_cost", "maint_cost", "total_cost",
    )
)
mart_rejects_summary = rejects.groupBy("source", "rule").agg(
    F.count("*").alias("rejected_rows")
)

route_totals = mart_route_day.groupBy("route_id", "depot", "service_line").agg(
    F.sum("completed_stops").alias("completed_stops"),
    F.sum("missed_stops").alias("missed_stops"),
    F.sum("tons").alias("tons"),
    F.sum("shift_hours").alias("shift_hours"),
    F.sum("total_cost").alias("total_cost"),
)
service_days = mart_route_day.select("service_date").distinct().count()
route_totals = (
    route_totals.withColumn("service_days_in_data", F.lit(service_days))
    .withColumn("stops_per_hour", F.col("completed_stops") / F.col("shift_hours"))
    .withColumn("tons_per_hour", F.col("tons") / F.col("shift_hours"))
    .withColumn(
        "missed_rate",
        F.col("missed_stops") / (F.col("completed_stops") + F.col("missed_stops")),
    )
    .withColumn("cost_per_stop", F.col("total_cost") / F.col("completed_stops"))
)
service_window = Window.partitionBy("service_line")
route_totals = route_totals.withColumn(
    "median_cost_per_stop", F.percentile_approx("cost_per_stop", 0.5).over(service_window)
)
route_totals = route_totals.withColumn(
    "annual_savings",
    F.greatest(F.col("cost_per_stop") - F.col("median_cost_per_stop"), F.lit(0.0))
    * F.col("completed_stops") * F.lit(260) / F.col("service_days_in_data"),
)
density_window = Window.partitionBy("service_line").orderBy("stops_per_hour")
cost_window = Window.partitionBy("service_line").orderBy("cost_per_stop")
mart_route_kpis = (
    route_totals.withColumn("low_density", F.percent_rank().over(density_window) <= 0.10)
    .withColumn("high_cost", F.percent_rank().over(cost_window) >= 0.90)
    .withColumn("is_flagged", F.col("low_density") | F.col("high_cost"))
    .withColumn(
        "flag_reason",
        F.when(F.col("low_density") & F.col("high_cost"), "low_density+high_cost")
        .when(F.col("low_density"), "low_density")
        .when(F.col("high_cost"), "high_cost")
        .otherwise(""),
    )
)
mart_fuel_kpis = mart_route_day.groupBy("fuel_type").agg(
    F.sum("fuel_cost").alias("fuel_cost"),
    F.sum("maint_cost").alias("maint_cost"),
    F.sum("km_driven").alias("km_driven"),
).select(
    "*",
    (F.col("fuel_cost") / F.col("km_driven")).alias("fuel_cost_per_km"),
    (F.col("maint_cost") / F.col("km_driven")).alias("maint_cost_per_km"),
    ((F.col("fuel_cost") + F.col("maint_cost")) / F.col("km_driven")).alias("vehicle_cost_per_km"),
)

for frame, name in [
    (dim_truck, "dim_truck"), (dim_route, "dim_route"),
    (dim_customer, "dim_customer"), (dim_date, "dim_date"),
    (fact_pickup, "fact_pickup"), (fact_route_day, "fact_route_day"),
    (mart_route_day, "mart_route_day"), (mart_rejects_summary, "mart_rejects_summary"),
    (mart_route_kpis, "mart_route_kpis"), (mart_fuel_kpis, "mart_fuel_kpis"),
]:
    write(frame, name)

job.commit()
