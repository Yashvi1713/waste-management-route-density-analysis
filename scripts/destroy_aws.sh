#!/usr/bin/env bash
set -euo pipefail

PROJECT="${PROJECT:?Set PROJECT to the same value used for deployment}"
AWS_REGION="${AWS_REGION:-eu-west-1}"

echo "AWS caller identity:"
aws sts get-caller-identity
echo "Target project: ${PROJECT}"
echo "Region: ${AWS_REGION}"
terraform -chdir=infra destroy -var="project=${PROJECT}" -var="aws_region=${AWS_REGION}"

