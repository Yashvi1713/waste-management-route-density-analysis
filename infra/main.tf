terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name     = "${var.project}-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  database_prefix = replace(var.project, "-", "_")
  silver_database = "${local.database_prefix}_silver"
  gold_database   = "${local.database_prefix}_gold"

  silver_tables = {
    trucks = [
      ["truck_id", "string"], ["depot", "string"], ["fuel_type", "string"],
      ["model_year", "int"], ["body_type", "string"]
    ]
    routes = [
      ["route_id", "string"], ["depot", "string"], ["service_line", "string"],
      ["planned_stops", "int"]
    ]
    customers = [
      ["customer_id", "string"], ["route_id", "string"], ["segment", "string"],
      ["service_day", "string"], ["monthly_rate", "double"]
    ]
    pickups = [
      ["pickup_id", "string"], ["service_date", "date"], ["route_id", "string"],
      ["truck_id", "string"], ["customer_id", "string"], ["completed_at", "timestamp"],
      ["tons", "double"], ["status", "string"]
    ]
    route_days = [
      ["service_date", "date"], ["route_id", "string"], ["truck_id", "string"],
      ["shift_hours", "double"], ["km_driven", "double"], ["labour_cost", "double"],
      ["fuel_cost", "double"], ["maint_cost", "double"]
    ]
    rejects = [
      ["source", "string"], ["rule", "string"], ["record", "string"],
      ["loaded_at", "timestamp"]
    ]
    load_audit = [
      ["source", "string"], ["raw_rows", "bigint"], ["duplicates_removed", "bigint"],
      ["rejected_rows", "bigint"], ["silver_rows", "bigint"], ["loaded_at", "timestamp"]
    ]
  }

  gold_tables = {
    dim_truck    = local.silver_tables.trucks
    dim_route    = local.silver_tables.routes
    dim_customer = local.silver_tables.customers
    dim_date = [
      ["service_date", "date"], ["day_of_week", "string"], ["iso_week", "int"],
      ["month", "int"], ["is_weekend", "boolean"]
    ]
    fact_pickup = [
      ["pickup_id", "string"], ["service_date", "date"], ["route_id", "string"],
      ["truck_id", "string"], ["customer_id", "string"], ["completed_at", "timestamp"],
      ["tons", "double"], ["is_completed", "boolean"], ["is_missed", "boolean"]
    ]
    fact_route_day = [
      ["service_date", "date"], ["route_id", "string"], ["truck_id", "string"],
      ["shift_hours", "double"], ["km_driven", "double"], ["labour_cost", "double"],
      ["fuel_cost", "double"], ["maint_cost", "double"], ["total_cost", "double"]
    ]
    mart_route_day = [
      ["service_date", "date"], ["route_id", "string"], ["truck_id", "string"],
      ["depot", "string"], ["service_line", "string"], ["fuel_type", "string"],
      ["completed_stops", "bigint"], ["missed_stops", "bigint"], ["tons", "double"],
      ["shift_hours", "double"], ["km_driven", "double"], ["labour_cost", "double"],
      ["fuel_cost", "double"], ["maint_cost", "double"], ["total_cost", "double"]
    ]
    mart_rejects_summary = [
      ["source", "string"], ["rule", "string"], ["rejected_rows", "bigint"]
    ]
    mart_route_kpis = [
      ["route_id", "string"], ["depot", "string"], ["service_line", "string"],
      ["completed_stops", "bigint"], ["missed_stops", "bigint"], ["tons", "double"],
      ["shift_hours", "double"], ["total_cost", "double"], ["service_days_in_data", "bigint"],
      ["stops_per_hour", "double"], ["tons_per_hour", "double"], ["missed_rate", "double"],
      ["cost_per_stop", "double"], ["median_cost_per_stop", "double"],
      ["annual_savings", "double"], ["low_density", "boolean"], ["high_cost", "boolean"],
      ["is_flagged", "boolean"], ["flag_reason", "string"]
    ]
    mart_fuel_kpis = [
      ["fuel_type", "string"], ["fuel_cost", "double"], ["maint_cost", "double"],
      ["km_driven", "double"], ["fuel_cost_per_km", "double"],
      ["maint_cost_per_km", "double"], ["vehicle_cost_per_km", "double"]
    ]
  }
}

resource "aws_s3_bucket" "project" {
  bucket        = local.bucket_name
  force_destroy = true
  tags          = { Project = var.project }
}

resource "aws_s3_bucket_public_access_block" "project" {
  bucket                  = aws_s3_bucket.project.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "project" {
  bucket = aws_s3_bucket.project.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "project" {
  bucket = aws_s3_bucket.project.id
  rule {
    id     = "expire-athena-results"
    status = "Enabled"
    filter { prefix = "athena-results/" }
    expiration { days = 7 }
  }
}

resource "aws_iam_role" "glue" {
  name = "${var.project}-glue-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "glue.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "glue" {
  name = "${var.project}-glue-policy"
  role = aws_iam_role.glue.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.project.arn },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.project.arn}/*" },
      { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], Resource = "*" },
      { Effect = "Allow", Action = ["glue:GetDatabase", "glue:GetTable", "glue:CreatePartition", "glue:UpdatePartition", "glue:BatchCreatePartition"], Resource = "*" }
    ]
  })
}

resource "aws_s3_object" "bronze_to_silver_script" {
  bucket = aws_s3_bucket.project.id
  key    = "scripts/bronze_to_silver.py"
  source = "${path.module}/../glue/bronze_to_silver.py"
  etag   = filemd5("${path.module}/../glue/bronze_to_silver.py")
}

resource "aws_s3_object" "silver_to_gold_script" {
  bucket = aws_s3_bucket.project.id
  key    = "scripts/silver_to_gold.py"
  source = "${path.module}/../glue/silver_to_gold.py"
  etag   = filemd5("${path.module}/../glue/silver_to_gold.py")
}

resource "aws_glue_job" "bronze_to_silver" {
  name              = "${var.project}-bronze-to-silver"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 30
  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.project.id}/${aws_s3_object.bronze_to_silver_script.key}"
    python_version  = "3"
  }
  default_arguments = { "--BUCKET" = aws_s3_bucket.project.id, "--job-language" = "python" }
}

resource "aws_glue_job" "silver_to_gold" {
  name              = "${var.project}-silver-to-gold"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 30
  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.project.id}/${aws_s3_object.silver_to_gold_script.key}"
    python_version  = "3"
  }
  default_arguments = { "--BUCKET" = aws_s3_bucket.project.id, "--job-language" = "python" }
}

resource "aws_glue_catalog_database" "silver" { name = local.silver_database }
resource "aws_glue_catalog_database" "gold" { name = local.gold_database }

resource "aws_glue_catalog_table" "silver" {
  for_each      = local.silver_tables
  name          = each.key
  database_name = aws_glue_catalog_database.silver.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { classification = "parquet", EXTERNAL = "TRUE" }
  storage_descriptor {
    location      = "s3://${aws_s3_bucket.project.id}/silver/${each.key}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
    dynamic "columns" {
      for_each = each.value
      content {
        name = columns.value[0]
        type = columns.value[1]
      }
    }
  }
}

resource "aws_glue_catalog_table" "gold" {
  for_each      = local.gold_tables
  name          = each.key
  database_name = aws_glue_catalog_database.gold.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { classification = "parquet", EXTERNAL = "TRUE" }
  storage_descriptor {
    location      = "s3://${aws_s3_bucket.project.id}/gold/${each.key}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
    dynamic "columns" {
      for_each = each.value
      content {
        name = columns.value[0]
        type = columns.value[1]
      }
    }
  }
}

resource "aws_athena_workgroup" "project" {
  name = var.project
  configuration {
    enforce_workgroup_configuration = true
    result_configuration {
      output_location = "s3://${aws_s3_bucket.project.id}/athena-results/"
      encryption_configuration { encryption_option = "SSE_S3" }
    }
  }
}

resource "aws_glue_workflow" "medallion" {
  name = "${var.project}-medallion-workflow"
}

resource "aws_glue_trigger" "start" {
  # type = "ON_DEMAND" and enabled = false keep this visual workflow dormant.
  name          = "${var.project}-disabled-start"
  type          = "ON_DEMAND"
  workflow_name = aws_glue_workflow.medallion.name
  enabled       = false
  actions { job_name = aws_glue_job.bronze_to_silver.name }
}

resource "aws_glue_trigger" "silver_to_gold" {
  name          = "${var.project}-silver-to-gold-on-success"
  type          = "CONDITIONAL"
  workflow_name = aws_glue_workflow.medallion.name
  enabled       = true
  predicate {
    conditions {
      job_name = aws_glue_job.bronze_to_silver.name
      state    = "SUCCEEDED"
    }
  }
  actions { job_name = aws_glue_job.silver_to_gold.name }
}

