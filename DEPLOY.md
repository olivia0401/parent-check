# EC2 deployment: Secrets Manager + Docker Compose + Caddy

This runbook describes the new deployment configuration. It has not been applied
or validated on the live EC2 instance. See [SECURITY.md](SECURITY.md) for evidence
and remaining gaps. Keep the existing stack running until migration is ready.

## 1. Host and access prerequisites

Use a supported Linux host with Docker Engine, the Compose plugin, Python 3,
and an SSM Agent. Use Session Manager for management. Test a second SSM session
before removing SSH access; until then restrict port 22 to your own IP.
Allow public HTTPS 443, with 80 only for HTTP-to-HTTPS redirects and ACME HTTP
validation. Never open 8000, 5432 or 6379 to the internet. Avoid attaching another
permissive security group to the same instance.

Attach an EC2 instance profile with the trust policy in
[ops/ec2-role-trust.json](ops/ec2-role-trust.json). Its secret permission should
use [ops/ec2-secret-policy.example.json](ops/ec2-secret-policy.example.json),
replacing Resource with the **exact production secret ARN**, including its AWS
suffix. Do not grant ListSecrets, secret updates, or wildcard secret access.
Use a separate secret and role for staging. If a customer-managed KMS key is
used, also grant kms:Decrypt on that exact key, conditioned on
kms:ViaService=secretsmanager.<region>.amazonaws.com and the secret encryption
context. The role also needs the SSM Agent's management permissions (for
example AmazonSSMManagedInstanceCore); operator StartSession permissions belong
to the operator, not the application role.

Require IMDSv2, set HttpPutResponseHopLimit=1, and disable the metadata IPv6
endpoint. Only the host exporter needs role credentials; containers use Docker
bridge networking. Block container access to 169.254.169.254 in the host's
DOCKER-USER firewall chain and restrict host OUTPUT access to that address to
the root user. Preserve these rules through reboot using the host's firewall
manager and verify both negative tests below. Hop limits and an SDK environment
flag alone are not a process authorization mechanism. Root and Docker operators
are trusted administrators and can read mounted application secrets.

Official references: [EC2 metadata options](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html),
[Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html).

## 2. Create the production secret

In Secrets Manager, create a JSON SecretString with **exactly** these fields:

| Field | Value |
|---|---|
| SECRET_KEY | Independently generated random value, at least 32 characters |
| POSTGRES_PASSWORD | Database user's actual password, at least 32 characters |
| GEMINI_API_KEY | Production provider key; empty string disables AI |

Keep actual values out of command lines, Git, shell history, CI and chat. Enter
values through the AWS console or another approved secret provisioning process.
Do not copy a developer API key into production. The exporter validates this
schema, percent-encodes the database password when building DATABASE_URL, and
fetches AWSCURRENT once per deployment or rotation. It accepts only temporary
EC2 instance-role credentials; a local AWS access key/profile is rejected.

**Existing database:** POSTGRES_PASSWORD_FILE initializes a new Postgres volume;
it does **not** update the password of an existing database. First migrate the
current password into Secrets Manager. If it fails the strength check, arrange
a database password rotation and matching Secret update together before changing
traffic. Back up the database first and keep the existing Compose project name,
POSTGRES_USER, POSTGRES_DB, pgdata and Caddy certificate volumes. Do not use
down -v, rename the project, or create an empty replacement database.

## 3. Prepare the checkout and host-only exporter

Use the existing checkout for a migration. On a fresh host, place it at
/opt/parent-check (or adjust every path in the service example). Restrict write
access to the checkout, service unit and ops virtual environment to trusted
administrators: the exporter runs as root.

```bash
cd /opt/parent-check
sudo python3 -m venv /opt/parent-check-ops
sudo /opt/parent-check-ops/bin/python -m pip install --upgrade "pip>=26.2"
sudo /opt/parent-check-ops/bin/python -m pip install -r ops/requirements.txt
cp .env.prod.example .env
```

Set SITE_ADDRESS to the DNS name pointing at this instance. Set FRONTEND_ORIGIN
to the separately hosted Next.js origin if used. Match POSTGRES_USER and
POSTGRES_DB to the exporter flags; defaults are parentcheck. The new .env must
contain only these public settings and SECRETS_DIRECTORY. Remove its old secret
values only after validating the replacement; handle any rollback copy as a
secret outside the checkout. Never put credentials in NEXT_PUBLIC_* variables.

```bash
sudo /opt/parent-check-ops/bin/python ops/export_secrets.py \
  --secret-arn '<exact-production-secret-arn>' --region eu-west-2 \
  --db-user parentcheck --db-name parentcheck
```

The exporter publishes a versioned snapshot under /run/parent-check/current.
The parent directory is root-only (0700). Individual files are 0444 for the
non-root container user, and Compose grants each service only its required
read-only mounts. These are host bind mounts, not an encrypted Docker vault;
verify /run is volatile storage on your host. No values are written into the
Compose environment or image. The app loads mounted values into its process
memory/environment before DB/client initialization. ECS/Render environment
injection remains supported as a separate deployment mode.

Do not print a SecretString, cat a secret file, dump the process environment,
or use docker compose config against the old secret-bearing configuration in
shared terminals. [Docker documents the per-service mount semantics and file
permission limits](https://docs.docker.com/reference/compose-file/services/#secrets).

## 4. Start and survive reboots

Build the image and validate the Compose configuration after the export succeeds:

```bash
docker compose -p parent-check -f docker-compose.prod.yml config --quiet
docker compose -p parent-check -f docker-compose.prod.yml build web
```

Verify -p parent-check matches the existing deployment. The first migration
from the old environment-based deployment requires a database backup, a protected
copy of the previous configuration/image and a maintenance rollback plan. After
those preparations, perform the first switch explicitly:

```bash
sudo /opt/parent-check-ops/bin/python -m ops.deploy \
  --secret-arn '<exact-production-secret-arn>' --region eu-west-2 \
  --db-user parentcheck --db-name parentcheck --initial-migration
```

Do not use --initial-migration for normal updates. Copy
[ops/parent-check.service.example](ops/parent-check.service.example) to
/etc/systemd/system/parent-check.service, fill in the ARN/paths/project, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now parent-check
```

The unit intentionally has **no ExecStop hook**: restart/reload leaves the old
containers running during preparation. The deploy command validates the secret,
checks/builds a candidate image, publishes its snapshot, then uses Compose
--wait and /healthz to verify DB and shared limiter readiness. With a known
previous release, a failed switch restores its image and secret snapshot and
runs readiness again. A failed first migration has no compatible prior secret
baseline and requires the documented manual recovery; no data volumes are deleted.

Image IDs persist in the root-private /var/lib/parent-check/image. Secrets remain
under volatile /run/parent-check; boot fetches them again and reuses the persisted
image instead of accidentally reverting to the initial build tag. A single EC2
Compose replacement may briefly interrupt traffic; this is not zero-downtime
blue/green deployment. Check systemctl status/journalctl for status metadata only.

## 5. Acceptance checks before calling this deployed

- From outside AWS: valid HTTPS certificate; HTTP redirects if 80 is enabled;
  ports 22 (after SSM migration), 8000, 5432 and 6379 are unreachable.
- From the host: only Caddy publishes ports. The app runs as UID 10001 with a
  read-only root filesystem; /tmp is bounded tmpfs. Caddy/Redis have no secrets,
  DB gets only its password, and web gets only its session key, DB URL and LLM key.
- From a container **without a secret grant**: files are absent and IMDS token
  retrieval fails. From a non-root host process: it cannot traverse the secret
  directory or retrieve instance credentials. Never print successful credentials.
- With IAM simulation or a separate denied identity: GetSecretValue fails on the
  production secret. The instance role cannot read a different environment's
  secret. Do not test denial by removing the working role during live traffic.
- Two browser sessions: one cannot read, change feedback on or delete the other's
  history; missing and foreign record IDs both return 404. Form POSTs without
  CSRF are rejected. Public stateless analysis endpoints remain anonymous.
- Public /metrics returns 404. The app also denies forwarded/public metrics
  requests independently of Caddy. Scrape web:8000/metrics directly from a trusted container
  on the edge network; do not publish a metrics port. Confirm no-store headers
  on analysis/history responses and test invalid/oversized requests.
- Run a real text check, a screenshot check if AI is enabled, and inspect
  sanitized logs. Repeat after a service restart and after a planned reboot.

## 6. Updates, rotation and recovery

After reviewed code changes, prepare a candidate and switch through the deploy
command (from the trusted checkout):

```bash
sudo /opt/parent-check-ops/bin/python -m ops.deploy \
  --secret-arn '<exact-production-secret-arn>' --region eu-west-2 --build
```

Use `systemctl reload parent-check` to refresh a secret without rebuilding. A
plain `systemctl restart` also uses the preparation-first flow; it does not stop
Docker services before fetching credentials. For an intentional shutdown, use
`docker compose -p parent-check -f docker-compose.prod.yml stop` explicitly.
A regular Compose restart will retain old secret bind mounts: **recreate**
containers to use the new snapshot. SECRET_KEY rotation invalidates browser
sessions and makes old anonymous histories inaccessible through those cookies.
Normal deploys reject a database-password change against the current snapshot.
Coordinate DB password rotation separately with the database itself and an
explicit maintenance/recovery plan; merely editing Secrets Manager is insufficient. API keys can be rotated
by publishing AWSCURRENT, reloading the unit, verifying a request and
then revoking the old key. No automatic rotation is configured here.

Old snapshots remain under the root-only /run/parent-check directory so existing
bind mounts stay valid during rotation; after recreating all consumers, remove
obsolete version directories as root. A reboot clears all cached snapshots.
Document the successful secret version ID, deployed Git revision and acceptance
results, without recording values. Roll back the application image and previous
secret version together where required; do not restore a known exposed key.

## Other targets

Render can inject SECRET_KEY and DATABASE_URL via its protected environment.
The optional [Terraform ECS stack](infra/README.md) is a demo: it uses HTTP,
public subnets and state containing credentials. It is not covered by this EC2
hardening and must not be presented as the secured production target.
