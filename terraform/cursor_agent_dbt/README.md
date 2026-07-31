# Cursor Cloud Agent: Athena / dbt debug IAM (Terraform)

Creates a **least-privilege** IAM user, Athena workgroup, and Glue database so
Cursor Cloud Agents can run narrow `dbt build` / `dbt show` against a
**non-prod** schema without admin keys or write access to Streamlit's
`dbt_main`.

| Resource | Default name | Purpose |
|----------|--------------|---------|
| IAM user | `cursor-agent-dbt-debug` (`/agents/`) | Agent AWS principal |
| Athena workgroup | `cursor-agent` | Enforced 1 GiB/query scan limit + dedicated results prefix |
| Glue database | `dbt_agent` | Only schema agents may Create/Update/Delete tables in |
| S3 data prefix | `dbt_agent/` | Iceberg/dbt object writes |
| S3 results prefix | `logs/athena-results-agent/` | Workgroup query results |

**Access keys are not created by Terraform** (avoids secrets in state). Create
them with the AWS CLI after apply and inject into Cursor Cloud Agent secrets.

Ticket: [#198](https://github.com/danolen/fantasy-baseball-platform/issues/198)

## Manual steps (order matters)

### A. One-time: Terraform state backend

If you have not created the remote state bucket yet, follow
**[../bootstrap/README.md](../bootstrap/README.md)** first.

### B. Apply this module

```bash
cd terraform/cursor_agent_dbt

cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
# Edit only if prefixes / names must differ from defaults.

terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

Save outputs:

```bash
terraform output
terraform output -raw create_access_key_command
terraform output -raw cursor_secrets_snippet
```

### C. Create access keys (once)

```bash
aws iam create-access-key --user-name cursor-agent-dbt-debug
```

Save `AccessKeyId` / `SecretAccessKey` in a password manager temporarily.

### D. Inject Cursor Cloud Agent secrets

Paste into the Cursor Cloud / agent secrets for this repo (names only in
[`docs/security.md`](../../docs/security.md)):

| Name | Value |
|------|--------|
| `AWS_ACCESS_KEY_ID` | From create-access-key |
| `AWS_SECRET_ACCESS_KEY` | From create-access-key |
| `AWS_DEFAULT_REGION` | `us-east-1` |
| `ATHENA_DATABASE` | `AwsDataCatalog` |
| `ATHENA_SCHEMA` | `dbt_agent` |
| `ATHENA_REGION` | `us-east-1` |
| `ATHENA_WORKGROUP` | `cursor-agent` |
| `ATHENA_S3_OUTPUT` | `terraform output -raw athena_s3_output` |
| `ATHENA_S3_DATA_DIR` | `terraform output -raw athena_s3_data_dir` |

Do **not** put maintainer admin / SSO credentials on agent VMs.

### E. Smoke tests (record on #198)

**Allow** — from `dbt/` with agent secrets present:

```bash
dbt parse
dbt build --select <known_model>+ --target agent
# or: dbt show --select <known_model> --target agent --limit 5
```

**Deny** — expect `AccessDenied`:

```bash
# Glue DDL on prod schema (example; use AWS CLI with agent keys)
aws glue update-table --database-name dbt_main --table-input file://...

# Overwrite raw ingest
aws s3 cp ./probe.txt s3://dn-lakehouse-dev/nfbc/probe.txt
```

### F. Agent usage rules

Documented in [`AGENTS.md`](../../AGENTS.md): prefer `dbt parse`; then narrow
`dbt show` / `dbt build --select <changed>+ --target agent`; never
`--target` / `ATHENA_SCHEMA` pointing at `dbt_main`.

## What this module does **not** manage

| Not here | Notes |
|----------|--------|
| Cursor secret values | Injected out-of-band after create-access-key |
| Streamlit / freshness Athena results prefix | Still `logs/athena-results` |
| CloudWatch billing alarm on workgroup bytes | Optional follow-up |
| GHA PR `dbt build` workflow | Issue #198 §5 near-term unblock — separate PR |
| Maintainer admin user | Break-glass only; never on agent VMs |

## Destroy

```bash
terraform destroy
```

Deactivate Cursor agent AWS secrets first. Destroy removes the IAM user,
workgroup, and Glue database resource; it does **not** delete objects under
`s3://…/dbt_agent/` or historical query results.
