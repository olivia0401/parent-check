# Security engineering status

This is an anonymous public scam checker. Analysis endpoints intentionally accept
public requests; CORS is a browser policy, not authentication. Saved HTML history
is scoped by an unguessable ID in a signed session cookie, and every repository
read/update/delete filters by that ID. There are no account or administrator
APIs. Foreign and absent history records return the same 404 response. Loss of
the cookie loses access to that anonymous history; this is not account login.

## Evidence collected on 2026-10-30

Read-only AWS/GitHub checks were performed; no cloud configuration was changed.

| Check | Observed state |
|---|---|
| GitHub secret scanning | Enabled |
| GitHub push protection | Enabled |
| GitHub secret scanning alerts | No alerts returned |
| Full local Git history, 42 commits | Gitleaks 8.30.1 found two false positives on Ed25519 constructor type annotations; exact code-line exception added; rerun clean |
| EC2 tagged `parent check`, eu-west-2 | Running; no instance profile attached |
| Attached security group's ingress | TCP 443 and **22 from 0.0.0.0/0**; no 8000/5432/6379 ingress rules |
| Instance metadata | IMDSv2 required, response hop limit 2, IPv6 metadata disabled |
| SSM instance status | Not verified: current AWS caller lacks DescribeInstanceInformation |
| Secrets Manager inventory | Not verified: current caller lacks ListSecrets; no secret values were requested |

**Priority operational gap:** restrict public SSH immediately through an approved
change; establish and test SSM before removing the last management route. The
proposed IAM profile, secret migration, hop limit/firewall changes and container
recreation still require deployment and live acceptance checks. Do not claim
Secrets Manager is already protecting this EC2 deployment.

## Changes prepared in this checkout

The reviewed code defects R1–R19 have now been addressed locally; see
[BUGFIXES.md](BUGFIXES.md) for the implementation and validation matrix.
Cloud migration and live production acceptance remain separate.

- Host-only Secrets Manager exporter using temporary EC2 role credentials and
  one exact-secret GetSecretValue policy; no AWS keys given to application
  containers. Snapshot caching avoids an AWS request per user request.
- Atomic, root-private snapshots in /run and read-only, per-service secret
  mounts. Explicit *_FILE configuration loads before DB/client initialization;
  missing/ambiguous sources fail closed. Production rejects missing, short and
  known placeholder session keys.
- Only Caddy publishes production ports. PostgreSQL/Redis use an internal data
  network; Caddy cannot attach directly to it. Local development ports bind to
  loopback. Web runs as UID 10001, drops capabilities and uses a read-only root
  filesystem with bounded temporary storage.
- Backend request size/type checks before expensive processing; existing CSRF,
  scoped history queries and rate limiting retained. Cross-session history and
  feedback denial returns 404; API throttling returns JSON 429 with Retry-After.
- Sensitive responses use no-store. Security headers, secret-value log redaction
  and type-only DB initialization errors reduce accidental disclosure. Unmatched
  request paths and arbitrary client request IDs no longer become log fields.
- Git/Docker exclusions cover environment files, private keys and Terraform state.
  Next.js receives only public API-origin configuration.
- Security regression tests run through existing CI; a dedicated workflow scans
  full history and checkout and exercises production Compose with synthetic
  secrets, a real DB, a non-root process and the read-only mounts.

The native Windows suite skips Linux filesystem tests; GitHub Linux CI passes
all 196 backend tests without skips, plus frontend checks, dependency audits and
the 61-case evaluation ([CI evidence](https://github.com/olivia0401/parent-check/actions/runs/41064384891)).
Production-shaped Docker Compose integration and full-history/checkout secret
scanning also pass ([security evidence](https://github.com/olivia0401/parent-check/actions/runs/41064384875)).
These runs use synthetic secrets and do not validate the live AWS deployment.
Follow [DEPLOY.md](DEPLOY.md) for live acceptance, migration, rotation,
reboot recovery and the trusted root/Docker operator boundary.

## Scope and remaining work

- Stateless /api/check and /api/check-image do not store history or accept a
  caller-selected history owner. They remain anonymous; production must retain
  quota limits. Production refuses POST processing with 503 while the shared limiter is
  unavailable and retries Redis. Development alone can use memory. Daily cost
  budgets and alert delivery remain separate operational work.
- /api/policy-check is a synthetic policy/audit demonstration. Its caller-supplied
  principal and owner strings are **not authenticated identities**, and its signed
  decisions do not authorize real user data or tool access. Never use it as an
  authorization boundary without binding it to an authenticated principal.
- Uploads now decode/validate format, dimensions and frames and are re-encoded
  without metadata before OCR. Tools validate arguments and return fixed error
  codes. Langfuse records metadata by default; capturing prompt/output requires
  LANGFUSE_CAPTURE_CONTENT=1. AI-generated free text is not persisted in history.
  Broader PII minimization and history retention/deletion policies remain product
  privacy work beyond the reviewed defects.
- The DB application currently uses the initialization DB user. Split migration
  and runtime DB roles for least privilege. TLS/authentication for data stores,
  encrypted storage, backups and restore drills need separate verification.
- The optional ECS Terraform stack still uses HTTP, public subnets and secrets
  in state. It has separate roles and is not certified by the EC2 work.
- CI now audits Python and Node dependencies; operational alert delivery still
  requires configuration and live acceptance.

## Reproduce checks

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m ruff check .
python -m pytest -q
python evaluate.py
gitleaks git --redact --no-banner .
```

Use Gitleaks 8.30.1 as pinned in .github/workflows/security.yml. The narrowly
scoped .gitleaks.toml exception covers only a constructor annotation whose
private_key argument defaults to None; it does not suppress key values or whole
files. A clean scan is evidence for these detectors and this history, not a
guarantee that every possible secret format has been recognized. If a real key
is exposed, revoke/rotate it first, inspect usage, and then clean tracked copies
and history as appropriate. Never put the value in an issue or CI artifact.
