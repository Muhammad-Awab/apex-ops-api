# Cost-aware path to cloud hosting

Constraint for this assessment: no paid cloud resources were used. Everything below is a **proposal**, and prices are **approximate on-demand list prices (USD/month)** to check against the provider's pricing calculator before committing.

## Principles
1. **Keep the artifact portable.** The same OCI image and the same env/secret-file contract run locally, on a VM or on a managed container platform. No rewrite at each step.
2. **Pay for managed state, not managed compute, first.** The database is the hardest part to operate well (backups, patching, PITR), so it is the first thing to hand to the provider.
3. **Scale to zero wherever traffic allows**, and avoid fixed-cost "taxes" (load balancers, NAT gateways) until they are needed.
4. **Budgets and alerts from day one.**

## Staged options

| Stage | Hosting | Approx. cost | When |
|-------|---------|--------------|------|
| 0. Local (this repo) | Docker Compose | $0 | dev, demos |
| 1. Single VM | 1 small VM (2 vCPU / 2 GB, e.g. AWS t4g.small, Lightsail, Hetzner) running **this same compose file**, Caddy for TLS, nightly `pg_dump` to object storage | **~$5–20** | internal tool, low traffic, uptime tolerance of minutes |
| 2. Serverless containers + managed DB **(recommended next step)** | Google Cloud Run / Azure Container Apps (scale-to-zero, built-in TLS and revisions) + smallest managed Postgres (Cloud SQL / Azure Flexible Server burstable) | **~$15–40** (compute often inside the free tier at low volume; the DB dominates) | real users, wants managed backups and zero-downtime deploys |
| 3. Containers on AWS | ECS Fargate (2 × 0.25 vCPU/0.5 GB) + RDS db.t4g.micro + ALB | **~$50–80** (the ALB alone is ~$16–20) | if the org standardises on AWS |
| 4. Kubernetes | EKS/GKE/AKS | $75+ control plane + nodes | only with many services or teams. Not justified for one API |

## How the current design maps to Stage 2

| Local | Cloud |
|-------|-------|
| `scripts/deploy.sh` + readiness/smoke gates | new **revision** with `--no-traffic`, smoke test the revision URL, then shift traffic (100%, or 10%→100% canary) |
| `scripts/rollback.sh` | shift traffic back to the previous revision (seconds; the old revision is still deployed) |
| GHCR image `:semver` | same image, or mirrored to Artifact Registry / ECR (with a lifecycle policy that keeps the last N versions) |
| `secrets/db_password.txt` | Secret Manager, mounted as a file. CI deploys through **OIDC workload identity federation** (no stored cloud keys) |
| `/healthz`, `/readyz` | platform liveness and startup/readiness probes |
| JSON stdout logs | Cloud Logging / Log Analytics, parsed automatically. **Retention set to 30 days** |
| Prometheus + alert rules | Managed Prometheus or the platform's metrics, with the same 4 alerts routed to on-call |
| Postgres volume | managed Postgres with automated backups + PITR, private IP only |

## Cost controls
- **Budget alerts** at 50/80/100% of a monthly budget, plus **cost-allocation tags** (`service=apex-ops-api`, `env=…`) on every resource.
- **Scale-to-zero** (min instances 0) in dev/staging. Production uses min 1 instance only if cold starts are unacceptable.
- **No NAT gateway** (~$30+/month each, plus data processing) unless private egress is truly required. Use serverless VPC connectors and private service access.
- **Start on the smallest DB tier**, set an alert on CPU and storage, and scale up on evidence rather than guesswork. Stop or delete non-prod DBs out of hours.
- **Registry lifecycle policies** (keep the last 10 versions and anything deployed in the last 30 days) and **log retention limits**. Logs are a classic silent cost growth.
- Revisit the stage decision every quarter based on actual traffic and the bill.
