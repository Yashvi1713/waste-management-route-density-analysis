variable "project" {
  description = "Project prefix applied to every AWS resource name."
  type        = string
  default     = "route-lab"
}

variable "aws_region" {
  description = "AWS region for project resources."
  type        = string
  default     = "eu-west-1"
}

