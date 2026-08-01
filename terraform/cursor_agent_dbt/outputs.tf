output "iam_user_name" {
  description = "IAM user for Cursor Cloud Agents. Create access keys out-of-band."
  value       = aws_iam_user.agent.name
}

output "iam_user_arn" {
  description = "ARN of the Cursor Cloud Agent IAM user."
  value       = aws_iam_user.agent.arn
}

output "iam_policy_arn" {
  description = "Customer-managed policy ARN attached to the agent user."
  value       = aws_iam_policy.agent.arn
}

output "platform_secret_arn" {
  description = "Secrets Manager secret ARN the agent may GetSecretValue (issue PAT + other JSON keys in the blob)."
  value       = data.aws_secretsmanager_secret.platform.arn
}

output "workgroup_name" {
  description = "Athena workgroup agents must use (ATHENA_WORKGROUP)."
  value       = aws_athena_workgroup.cursor_agent.name
}

output "agent_schema" {
  description = "Glue/Athena schema for agent dbt builds (ATHENA_SCHEMA). Never dbt_main."
  value       = aws_glue_catalog_database.dbt_agent.name
}

output "athena_s3_output" {
  description = "ATHENA_S3_OUTPUT for the agent workgroup (must match Cursor secrets)."
  value       = "s3://${var.s3_bucket}/${local.athena_results_key}/"
}

output "athena_s3_data_dir" {
  description = "ATHENA_S3_DATA_DIR for agent Iceberg/dbt objects."
  value       = "s3://${var.s3_bucket}/${local.agent_data_key}/"
}

output "bytes_scanned_cutoff_per_query" {
  description = "Enforced per-query scan limit in bytes."
  value       = var.bytes_scanned_cutoff_per_query
}

output "create_access_key_command" {
  description = "Command to create access keys after apply (do not store keys in Terraform state)."
  value       = "aws iam create-access-key --user-name ${aws_iam_user.agent.name}"
}

output "cursor_secrets_snippet" {
  description = "Env var names/values to inject into Cursor Cloud Agent secrets (fill AWS keys after create-access-key)."
  value       = <<-EOT
    AWS_ACCESS_KEY_ID=<from create-access-key>
    AWS_SECRET_ACCESS_KEY=<from create-access-key>
    AWS_DEFAULT_REGION=${var.aws_region}
    ATHENA_DATABASE=AwsDataCatalog
    ATHENA_SCHEMA=${aws_glue_catalog_database.dbt_agent.name}
    ATHENA_REGION=${var.aws_region}
    ATHENA_WORKGROUP=${aws_athena_workgroup.cursor_agent.name}
    ATHENA_S3_OUTPUT=s3://${var.s3_bucket}/${local.athena_results_key}/
    ATHENA_S3_DATA_DIR=s3://${var.s3_bucket}/${local.agent_data_key}/
  EOT
}
