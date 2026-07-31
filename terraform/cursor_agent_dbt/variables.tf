variable "aws_region" {
  description = "AWS region for Athena, Glue, and IAM ARNs."
  type        = string
  default     = "us-east-1"
}

variable "s3_bucket" {
  description = "Lakehouse bucket (Athena source data + agent query results + dbt_agent objects)."
  type        = string
  default     = "dn-lakehouse-dev"
}

variable "athena_results_prefix" {
  description = <<-EOT
    S3 key prefix for the agent Athena workgroup query results
    (ATHENA_S3_OUTPUT without s3://bucket/). Keep separate from Streamlit /
    freshness results (logs/athena-results).
  EOT
  type        = string
  default     = "logs/athena-results-agent"
}

variable "agent_data_prefix" {
  description = <<-EOT
    S3 key prefix for Iceberg/dbt objects written by agent builds
    (ATHENA_S3_DATA_DIR without s3://bucket/).
  EOT
  type        = string
  default     = "dbt_agent"
}

variable "iam_user_name" {
  description = "IAM user for Cursor Cloud Agent dbt/Athena debug."
  type        = string
  default     = "cursor-agent-dbt-debug"
}

variable "iam_user_path" {
  description = "IAM path for the agent user."
  type        = string
  default     = "/agents/"
}

variable "workgroup_name" {
  description = "Athena workgroup name for agent queries."
  type        = string
  default     = "cursor-agent"
}

variable "agent_schema" {
  description = "Glue/Athena schema agents may materialize into (never dbt_main)."
  type        = string
  default     = "dbt_agent"
}

variable "bytes_scanned_cutoff_per_query" {
  description = "Per-query Athena bytes-scanned limit enforced by the agent workgroup (default 1 GiB)."
  type        = number
  default     = 1073741824
}

variable "ingest_deny_prefixes" {
  description = "S3 key prefixes agents must not Put/Delete (raw ingest roots)."
  type        = list(string)
  default = [
    "nfbc",
    "fangraphs",
    "razzball",
    "ftn",
    "mapping",
  ]
}
