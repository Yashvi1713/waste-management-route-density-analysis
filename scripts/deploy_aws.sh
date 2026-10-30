#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:-route-lab}"
AWS_REGION="${AWS_REGION:-eu-west-1}"
export AWS_REGION

for tool in aws terraform .venv/bin/python; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 1; }
done

echo "AWS caller identity:"
aws sts get-caller-identity

if [[ ! -f data/bronze/_manifest.json ]]; then
  .venv/bin/python generate_data.py --days 90 --seed 42
fi

terraform -chdir=infra init
terraform -chdir=infra apply -var="project=${PROJECT}" -var="aws_region=${AWS_REGION}"

BUCKET="$(terraform -chdir=infra output -raw bucket_name)"
BRONZE_JOB="$(terraform -chdir=infra output -raw bronze_to_silver_job)" # route-lab-bronze-to-silver
GOLD_JOB="$(terraform -chdir=infra output -raw silver_to_gold_job)"     # route-lab-silver-to-gold
SILVER_DATABASE="$(terraform -chdir=infra output -raw silver_database)"
GOLD_DATABASE="$(terraform -chdir=infra output -raw gold_database)"
ATHENA_WORKGROUP="$(terraform -chdir=infra output -raw athena_workgroup)"
GLUE_WORKFLOW="$(terraform -chdir=infra output -raw glue_workflow)"

aws s3 sync data/bronze/ "s3://${BUCKET}/bronze/" --region "$AWS_REGION"

run_glue_job() {
  local job_name="$1"
  local run_id state
  run_id="$(aws glue start-job-run --job-name "$job_name" --region "$AWS_REGION" --query JobRunId --output text)"
  echo "Started ${job_name}: ${run_id}"
  while true; do
    state="$(aws glue get-job-run --job-name "$job_name" --run-id "$run_id" --region "$AWS_REGION" --query 'JobRun.JobRunState' --output text)"
    echo "${job_name}: ${state}"
    case "$state" in
      SUCCEEDED) return 0 ;;
      FAILED|ERROR|TIMEOUT|STOPPED) return 1 ;;
    esac
    sleep 15
  done
}

# Ordered execution: bronze-to-silver must succeed before silver-to-gold starts.
run_glue_job "$BRONZE_JOB"
run_glue_job "$GOLD_JOB"

AWS_SILVER_DATABASE="$SILVER_DATABASE" \
AWS_GOLD_DATABASE="$GOLD_DATABASE" \
ATHENA_WORKGROUP="$ATHENA_WORKGROUP" \
.venv/bin/python scripts/validate_aws.py

cat <<SUMMARY
Deployment and AWS QA complete. Resources remain deployed.
S3 bucket: ${BUCKET}
Glue jobs: ${BRONZE_JOB}, ${GOLD_JOB}
Silver database: ${SILVER_DATABASE}
Gold database: ${GOLD_DATABASE}
Athena workgroup: ${ATHENA_WORKGROUP}
Glue Workflow: ${GLUE_WORKFLOW}
Local Streamlit: ANALYTICS_BACKEND=athena AWS_REGION=${AWS_REGION} AWS_SILVER_DATABASE=${SILVER_DATABASE} AWS_GOLD_DATABASE=${GOLD_DATABASE} ATHENA_WORKGROUP=${ATHENA_WORKGROUP} .venv/bin/streamlit run app.py --server.port 8503
SUMMARY

