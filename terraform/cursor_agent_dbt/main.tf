data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id

  athena_results_key = trim(var.athena_results_prefix, "/")
  agent_data_key     = trim(var.agent_data_prefix, "/")

  lakehouse_bucket = "arn:aws:s3:::${var.s3_bucket}"
  lakehouse_arn    = "arn:aws:s3:::${var.s3_bucket}/*"

  athena_results_arn = "arn:aws:s3:::${var.s3_bucket}/${local.athena_results_key}/*"
  agent_data_arn     = "arn:aws:s3:::${var.s3_bucket}/${local.agent_data_key}/*"

  workgroup_arn = "arn:aws:athena:${var.aws_region}:${local.account_id}:workgroup/${var.workgroup_name}"

  glue_catalog_arn   = "arn:aws:glue:${var.aws_region}:${local.account_id}:catalog"
  glue_all_db_arn    = "arn:aws:glue:${var.aws_region}:${local.account_id}:database/*"
  glue_all_tbl_arn   = "arn:aws:glue:${var.aws_region}:${local.account_id}:table/*/*"
  glue_agent_db_arn  = "arn:aws:glue:${var.aws_region}:${local.account_id}:database/${var.agent_schema}"
  glue_agent_tbl_arn = "arn:aws:glue:${var.aws_region}:${local.account_id}:table/${var.agent_schema}/*"
  glue_main_db_arn   = "arn:aws:glue:${var.aws_region}:${local.account_id}:database/dbt_main"
  glue_main_tbl_arn  = "arn:aws:glue:${var.aws_region}:${local.account_id}:table/dbt_main/*"

  glue_mutation_actions = [
    "glue:CreateTable",
    "glue:UpdateTable",
    "glue:DeleteTable",
    "glue:BatchCreatePartition",
    "glue:BatchDeletePartition",
    "glue:CreatePartition",
    "glue:UpdatePartition",
    "glue:DeletePartition",
    "glue:CreateDatabase",
    "glue:UpdateDatabase",
    "glue:DeleteDatabase",
  ]

}

# ---------------------------------------------------------------------------
# Glue database for agent builds (created in Terraform so IAM can omit CreateDatabase)
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "dbt_agent" {
  name = var.agent_schema

  description = "Non-prod schema for Cursor Cloud Agent dbt builds (#198). Never used by Streamlit."
}

# ---------------------------------------------------------------------------
# Athena workgroup with enforced scan ceiling
# ---------------------------------------------------------------------------

resource "aws_athena_workgroup" "cursor_agent" {
  name = var.workgroup_name

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.bytes_scanned_cutoff_per_query

    result_configuration {
      output_location = "s3://${var.s3_bucket}/${local.athena_results_key}/"
    }
  }

  tags = {
    Project = "fantasy-baseball-platform"
    Ticket  = "198"
    Actor   = "cursor-agent"
  }
}

# ---------------------------------------------------------------------------
# IAM user (access keys created out-of-band — never in Terraform state)
# ---------------------------------------------------------------------------

resource "aws_iam_user" "agent" {
  name = var.iam_user_name
  path = var.iam_user_path

  tags = {
    Project = "fantasy-baseball-platform"
    Ticket  = "198"
    Actor   = "cursor-agent"
  }
}

data "aws_iam_policy_document" "agent" {
  # Athena: only the agent workgroup
  statement {
    sid    = "AthenaQueryAgentWorkgroup"
    effect = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
      "athena:GetWorkGroup",
      "athena:ListQueryExecutions",
      "athena:BatchGetQueryExecution",
    ]
    resources = [local.workgroup_arn]
  }

  # GetQueryResults / GetQueryExecution also need the query-execution ARN shape
  # when callers pass execution IDs; scope to this account's Athena queries.
  statement {
    sid    = "AthenaQueryExecutionRead"
    effect = "Allow"
    actions = [
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
      "athena:BatchGetQueryExecution",
    ]
    resources = [
      "arn:aws:athena:${var.aws_region}:${local.account_id}:query/*",
    ]
  }

  # Glue catalog read (sources + prod + agent)
  statement {
    sid    = "GlueReadCatalog"
    effect = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetTableVersion",
      "glue:GetTableVersions",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
    ]
    resources = [
      local.glue_catalog_arn,
      local.glue_all_db_arn,
      local.glue_all_tbl_arn,
    ]
  }

  # Glue mutate only dbt_agent (CreateDatabase omitted — DB exists via Terraform)
  statement {
    sid    = "GlueMutateAgentSchema"
    effect = "Allow"
    actions = [
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:BatchCreatePartition",
      "glue:BatchDeletePartition",
      "glue:CreatePartition",
      "glue:UpdatePartition",
      "glue:DeletePartition",
    ]
    resources = [
      local.glue_catalog_arn,
      local.glue_agent_db_arn,
      local.glue_agent_tbl_arn,
    ]
  }

  # Explicit deny on Streamlit prod schema
  statement {
    sid     = "DenyGlueMutateDbtMain"
    effect  = "Deny"
    actions = local.glue_mutation_actions
    resources = [
      local.glue_main_db_arn,
      local.glue_main_tbl_arn,
    ]
  }

  # Deny Glue mutation on anything that is not the agent schema
  statement {
    sid     = "DenyGlueMutateOutsideAgent"
    effect  = "Deny"
    actions = local.glue_mutation_actions
    not_resources = [
      local.glue_catalog_arn,
      local.glue_agent_db_arn,
      local.glue_agent_tbl_arn,
    ]
  }

  # Lakehouse source reads
  statement {
    sid    = "ReadLakehouseData"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [
      local.lakehouse_bucket,
      local.lakehouse_arn,
    ]
  }

  # Athena results prefix (ListBucket scoped)
  statement {
    sid    = "AthenaResultsBucket"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [local.lakehouse_bucket]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "${local.athena_results_key}/*",
        local.athena_results_key,
      ]
    }
  }

  statement {
    sid    = "AthenaResultsObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = [local.athena_results_arn]
  }

  # Agent Iceberg / dbt object prefix
  statement {
    sid    = "AgentDataBucket"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = [local.lakehouse_bucket]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "${local.agent_data_key}/*",
        local.agent_data_key,
      ]
    }
  }

  statement {
    sid    = "AgentDataObjects"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [local.agent_data_arn]
  }
}

# Object Put/Delete Deny must match object key ARNs (s3:prefix only applies to ListBucket).
data "aws_iam_policy_document" "agent_ingest_deny_objects" {
  statement {
    sid    = "DenyIngestObjectWrites"
    effect = "Deny"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      for p in var.ingest_deny_prefixes :
      "arn:aws:s3:::${var.s3_bucket}/${trim(p, "/")}/*"
    ]
  }
}

data "aws_iam_policy_document" "agent_combined" {
  source_policy_documents = [
    data.aws_iam_policy_document.agent.json,
    data.aws_iam_policy_document.agent_ingest_deny_objects.json,
  ]
}

resource "aws_iam_user_policy" "agent" {
  name   = "cursor-agent-dbt-debug"
  user   = aws_iam_user.agent.name
  policy = data.aws_iam_policy_document.agent_combined.json
}
