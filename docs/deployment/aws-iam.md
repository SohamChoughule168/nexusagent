# AWS IAM Permissions Documentation

IAM for the NexusAgent AWS deployment (Milestone 7, Phase 4). Companion to
[`aws.md`](aws.md). The deployment is single-instance and builds images on the
host, so the EC2 instance needs **no IAM permissions to function** by default.
The policy below is a **least-privilege, optional** instance role that adds
operational conveniences (SSM access, optional CloudWatch Logs, optional ECR
pull, optional S3 uploads bucket).

Policy JSON: [`deploy/iam-policy.json`](../deploy/iam-policy.json).

---

## 1. Instance role (optional but recommended)

Attach this role to the EC2 instance at launch (step 3.1 in
[`aws.md`](aws.md)). Statements:

| Statement           | Permissions                                                | Required? | Purpose |
|---------------------|------------------------------------------------------------|-----------|---------|
| `SSMSessionManager` | `ssm:*`, `ssmmessages:*`, `ec2messages:*`                  | Optional  | Use SSM Session Manager instead of opening SSH (22). |
| `CloudWatchAgentLogs` | `logs:CreateLogGroup/Stream`, `PutLogEvents`, `DescribeLogStreams` | Optional | Ship container logs to CloudWatch (scoped to `/nexusagent/*`). |
| `ECRPullOptional`  | `ecr:GetAuthorizationToken`, `BatchGetImage`, etc.         | Optional  | Only if you push images to ECR and reference them in compose. |
| `S3UploadsBucketOptional` / `...ObjectsOptional` | `s3:ListBucket`, `GetObject`, `PutObject`, `DeleteObject` | Optional | Only for the future S3 upload backend (see [`aws.md` §6](aws.md)). |

### Why each is scoped
- **SSM/ec2messages/ssmmessages** — the minimum set for Session Manager to open
  a shell without a public SSH port. If you prefer SSH, drop this statement and
  open port 22 in the security group instead.
- **CloudWatch Logs** — restricted to `log-group:/nexusagent/*` so the instance
  can only create/write its own log group.
- **ECR** — only needed if you move off host-building to an ECR-pushed image.
  Remove entirely for the MVP.
- **S3** — the app currently stores uploads on the EBS volume, not S3, so these
  statements are inert today. Keep them only when you adopt the S3 backend.

---

## 2. Apply the policy

```bash
# Create the policy
aws iam create-policy \
  --policy-name nexusagent-ec2-policy \
  --policy-document file://deploy/iam-policy.json

# Create a role for EC2 and attach it
aws iam create-role \
  --role-name nexusagent-ec2-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy \
  --role-name nexusagent-ec2-role \
  --policy-arn arn:aws:iam::<account-id>:policy/nexusagent-ec2-policy

# Attach the role to the instance (at launch, or via console/CLI after)
aws ec2 associate-iam-instance-profile \
  --instance-id <ec2-id> \
  --iam-instance-profile Name=nexusagent-ec2-role
```

---

## 3. Database / Redis access (security groups, not IAM)

RDS and ElastiCache access is controlled by **security groups**, not IAM:

- `nexusagent-rds` allows **5432 inbound from `nexusagent-ec2`** only.
- `nexusagent-redis` allows **6379 inbound from `nexusagent-ec2`** only.

The EC2 instance authenticates to RDS with the `POSTGRES_PASSWORD` from
`.env.production` (password auth). IAM database authentication is a documented
hardening option (grant `rds-db:connect` in this role) but is not used by the
MVP.

---

## 4. Least-privilege guidance
- Start with **no instance role** if you use SSH + host-built images + EBS
  uploads — the app runs fine.
- Add `SSMSessionManager` to avoid exposing port 22.
- Add `CloudWatchAgentLogs` only if you ship logs.
- Add `ECR*` / `S3*` only when you actually adopt ECR / S3. Remove them
  otherwise to keep the role minimal.

Never attach `AdministratorAccess` or `AmazonS3FullAccess` to this instance.
