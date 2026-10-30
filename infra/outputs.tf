output "bucket_name" { value = aws_s3_bucket.project.id }
output "bronze_to_silver_job" { value = aws_glue_job.bronze_to_silver.name }
output "silver_to_gold_job" { value = aws_glue_job.silver_to_gold.name }
output "silver_database" { value = aws_glue_catalog_database.silver.name }
output "gold_database" { value = aws_glue_catalog_database.gold.name }
output "athena_workgroup" { value = aws_athena_workgroup.project.name }
output "glue_workflow" { value = aws_glue_workflow.medallion.name }
