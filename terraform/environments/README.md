# Multi-Environment IaC

## Environments

| Environment | Branch | Service Name | Model |
|---|---|---|---|
| stg | HW3-final | chat-client-service-stg | gpt-4o-mini |
| prod | main | chat-client-service-prod | gpt-4o |

## Promotion Path

HW3-final → all tests pass on CircleCI → peer review approved → main (production)

## Bootstrap Staging

```bash
export RENDER_API_KEY="rnd_..."
cd terraform
terraform init
terraform plan -var-file=environments/stg/terraform.tfvars
terraform apply -var-file=environments/stg/terraform.tfvars
```

## Bootstrap Production

```bash
export RENDER_API_KEY="rnd_..."
cd terraform
terraform init
terraform plan -var-file=environments/prod/terraform.tfvars
terraform apply -var-file=environments/prod/terraform.tfvars
```

## Secrets

All secrets set manually in Render dashboard — never committed to source control.
