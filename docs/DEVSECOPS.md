# DevSecOps pipeline

This document explains the security checks around SabzBank's code: what each CI job checks, how to read its output and run it locally with the same command, the gates and exit codes, how actions and images are pinned and updated, how Dependabot behaves and how to refresh the hash locks it cannot regenerate, the secret-scanning rules and their allowlist, the SBOM, and how to add a suppression without hiding a real finding. It maps the checks to the shift-left stages: before commit, in CI, and on a schedule. The pipeline lives in [.github/workflows/ci.yml](../.github/workflows/ci.yml), [.github/workflows/threat-intel.yml](../.github/workflows/threat-intel.yml) and [.github/dependabot.yml](../.github/dependabot.yml).

## Stages

| Stage | What runs | Where |
|---|---|---|
| Before commit (suggested, not installed) | gitleaks on staged changes; the backend suite for backend edits | A local pre-commit hook, below |
| Every push to `main`, every pull request, manual dispatch | `ci.yml`: backend, frontend, secrets, sast, docker, smoke, gate | GitHub Actions |
| Weekly, Monday 03:23 UTC | `ci.yml` again on unchanged code: new CVEs in pinned images and packages | GitHub Actions schedule |
| Weekly, Monday 04:41 UTC, and on demand | `threat-intel.yml`: the dependency threat brief | GitHub Actions schedule ([THREAT_INTEL.md](THREAT_INTEL.md)) |
| Weekly | Dependabot bump PRs for pip, npm, Docker digests, the compose image digest and actions | GitHub Dependabot |

## Workflow-wide settings (`ci.yml`)

- Triggers: `push` to `main`, `pull_request` (never `pull_request_target`, so fork code never runs with a write token or secrets), `workflow_dispatch`, `schedule`.
- `permissions: contents: read` at the top; no job asks for more.
- Every checkout sets `persist-credentials: false`.
- `concurrency` cancels an in-progress run for the same ref.
- `shell: bash`, which GitHub runs as `bash -eo pipefail`.
- Every job has a `timeout-minutes` and runs on `ubuntu-24.04`.
- No job receives the collector or partner keys. The tests make their own fake keys.
- `COMPOSE_PROJECT_NAME=sabzci`, so images are `sabzci-backend` and `sabzci-frontend`.

## Jobs

### backend

| Step | Checks | Fails when |
|---|---|---|
| `pip install --require-hashes -r requirements-dev.txt` | Every installed file matches a hash in the lock | A hash or a pin is missing or wrong |
| Lock check (inline Python) | Every `name==version` pin in `requirements.in` and `requirements-dev.in` appears identically in its `.txt` lock | A `.in` pin was bumped without relocking; the message names the stale pins |
| `python test_api.py` | The 47-section regression suite | Any section fails; failures print `FAIL <section>` with a traceback |
| `python ../scripts/test_threat_intel.py` | The threat-brief parser, triage and gate logic, offline | Any assertion fails |
| `pipx run --spec pip-audit==2.10.1 pip-audit --require-hashes --disable-pip -r requirements.txt` | Known vulnerabilities in the runtime lock, in an isolated environment | Any known vulnerability |

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements-dev.txt
.venv/bin/python test_api.py
.venv/bin/python ../scripts/test_threat_intel.py
pipx run --spec pip-audit==2.10.1 pip-audit --require-hashes --disable-pip -r requirements.txt
```

The lock check is the `python - <<'PY'` block in `ci.yml`; copy it to run it locally.

### frontend

| Step | Checks |
|---|---|
| `npm ci --ignore-scripts` | Installs exactly the lockfile; no package install script runs (none in the lockfile has one) |
| `npx tsc --noEmit` | Type check |
| `npm run build` | Production build |
| `npm audit --audit-level=high` | Fails on any high or critical advisory in the lockfile |

```bash
cd frontend
npm ci --ignore-scripts && npx tsc --noEmit && npm run build && npm audit --audit-level=high
```

### secrets

gitleaks 8.30.1 from its image, pinned by digest, over the whole history (`fetch-depth: 0`). The official gitleaks action scans only the pushed or PR commit range, so the job runs the binary directly.

```bash
docker run --rm -v "$PWD:/repo:ro" \
  zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f \
  git --redact --verbose --no-banner --config /repo/.gitleaks.toml /repo
```

Output: one block per finding with rule, file, line and commit, the secret redacted. Exit 1 on any leak.

### sast

semgrep 1.182.0 from its image, pinned by digest, with the packs `p/python`, `p/typescript`, `p/react`, `p/nextjs`, `p/secrets` and `p/owasp-top-ten`, excluding `graphify-out`. `--error` makes any finding fail the job; `--metrics=off` sends no telemetry.

```bash
docker run --rm -v "$PWD:/src" -w /src \
  semgrep/semgrep:1.182.0@sha256:4a34048c04fef049f71665047f074cffb00cc3d89482f965a5cd151d589237af \
  semgrep scan --metrics=off --error --exclude graphify-out \
  --config p/python --config p/typescript --config p/react --config p/nextjs \
  --config p/secrets --config p/owasp-top-ten
```

Pattern rules cannot see authorization or race bugs; the regression suite covers those.

### docker

| Step | Checks |
|---|---|
| hadolint (action v3.5.0) on `backend/Dockerfile` and `frontend/Dockerfile` | Dockerfile lint; any finding fails |
| `docker compose --profile ops config -q` | The compose file, including the `ops` profile, is valid |
| `docker compose build` | Both images build |
| trivy (action v0.36.0) on both images, `severity: HIGH,CRITICAL`, `ignore-unfixed: true`, `exit-code: 1` | No HIGH or CRITICAL vulnerability that has a fix |
| trivy CycloneDX SBOM for both images, uploaded as artifact `sbom-cyclonedx` | The bill of materials |

```bash
docker run --rm -i hadolint/hadolint@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d < backend/Dockerfile
docker run --rm -i hadolint/hadolint@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d < frontend/Dockerfile
COMPOSE_PROJECT_NAME=sabzci docker compose --profile ops config -q
COMPOSE_PROJECT_NAME=sabzci docker compose build
# trivy without mounting the Docker socket: save the image, scan the tarball
mkdir -p scan && docker save -o scan/backend.tar sabzci-backend:latest
docker run --rm -v "$PWD/scan:/in:ro" \
  aquasec/trivy@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c \
  image --input /in/backend.tar --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1
```

The hadolint digest is release 2.15.1 and the trivy digest is 0.76.1, the versions used for the local evidence in [DOCKER_HARDENING.md](DOCKER_HARDENING.md). Repeat the trivy lines for `sabzci-frontend`.

How to read trivy: a table per target (OS packages, then language packages) with the vulnerability id, installed and fixed versions, and severity. With `--ignore-unfixed`, rows without a fixed version are hidden and do not fail the job.

### smoke

Starts the full stack with `DEMO_MODE=1` on ports 3226 and 8226, runs `scripts/smoke.sh full`, prints the compose logs on failure and always tears down with `down -v`.

```bash
export COMPOSE_PROJECT_NAME=sabzci DEMO_MODE=1 WEB_PORT=3226 API_PORT=8226
docker compose up -d --build --wait --wait-timeout 300
PROJECT=sabzci scripts/smoke.sh full
docker compose down -v      # this project's throwaway volume only
```

Output: one `PASS` or `FAIL` line per check, then `smoke: all checks passed (full)` or `smoke: N check(s) FAILED`. Each check is one `check` line in `scripts/smoke.sh`; [QA_PLAN.md](QA_PLAN.md) describes the modes and the variables.

### gate

`if: always()`, needs all six jobs, and fails unless every result is `success`. Make this the one required status check on `main`; it also fails when a job was skipped or canceled.

## Gates and exit codes

| Tool | Gate | Exit |
|---|---|---|
| `test_api.py` | Any failing section | 1 |
| Lock check | Any `.in` pin missing or different in the lock | non-zero with the stale pins |
| pip-audit | Any known vulnerability in `requirements.txt` | 1 |
| npm audit | Any advisory at high or above | non-zero |
| gitleaks | Any leak not covered by `.gitleaks.toml` | 1 |
| semgrep | Any finding (`--error`) | 1 |
| hadolint | Any finding | 1 |
| trivy | HIGH or CRITICAL with a fix | 1 (`exit-code`) |
| `smoke.sh` | Any failed check / bad usage | 1 / 2 |
| `threat_intel.py` | Open HIGH, CRITICAL or UNKNOWN, or any KEV match / OSV unreachable | 1 / 2 (0 with `--allow-offline`) |
| gate | Any needed job not `success` | 1 |

## Pinning and updates

- **Actions** are pinned by full commit SHA with the version in a comment, for example `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`. Tags can be moved; a SHA cannot. The trivy action is pinned at v0.36.0, a release after the tag-hijack incident its v0.35.0 notes describe.
- **Tool images** run in CI (gitleaks, semgrep) are pinned by digest.
- **Base images** are pinned by tag and digest: `python:3.12-slim@sha256:…` in `backend/Dockerfile`, `node:22-alpine@sha256:…` in both stages of `frontend/Dockerfile`, `caddy:2-alpine@sha256:…` in `docker-compose.yml`.
- **Python dependencies** are hash-locked; npm dependencies are locked by `package-lock.json` integrity hashes.
- **Updates** come only through Dependabot PRs, which CI then checks.

| Pinned item | Action |
|---|---|
| actions/checkout | v7.0.1 |
| actions/setup-python | v7.0.0 |
| actions/setup-node | v7.1.0 |
| actions/upload-artifact | v7.0.2 |
| aquasecurity/trivy-action | v0.36.0 |
| hadolint/hadolint-action | v3.5.0 |

## Dependabot

`.github/dependabot.yml` opens one grouped PR per ecosystem per week:

| Ecosystem | Directory | Bumps |
|---|---|---|
| pip | `/backend` | `==` pins in `requirements.in` and `requirements-dev.in` (`versioning-strategy: increase`) |
| npm | `/frontend` | `package.json` and `package-lock.json` |
| docker | `/backend`, `/frontend` | `FROM image:tag@sha256:…` digests |
| docker-compose | `/` | The caddy digest in `docker-compose.yml` |
| github-actions | `/` | Action SHAs, keeping the version comments |

`cooldown: default-days: 7` on every entry: a release must be 7 days old before Dependabot proposes it, so a hijacked release is usually yanked first. Security updates ignore the cooldown.

Dependabot cannot regenerate the uv hash lock. Its pip PRs bump the `.in` files, and CI's lock check stays red until someone relocks on the PR branch:

```bash
cd backend
uv pip compile requirements.in --generate-hashes --python-version 3.12 --python-platform linux -o requirements.txt
uv pip compile requirements-dev.in --generate-hashes --python-version 3.12 --python-platform linux -o requirements-dev.txt
git commit -am "relock after the dependabot bump" && git push
```

(`requirements-dev.in` includes `requirements.in`, so a runtime bump needs both locks.)

## Secret scanning

`.gitleaks.toml` extends gitleaks' default rules with three narrow allowlists, each matching one exact value shape, so any other secret in the same file is still reported:

| Allowlist | Scope | Matches |
|---|---|---|
| Fake test keys | rule `generic-api-key`, file `backend/test_api.py` only, `condition = "AND"` | `^(collector\|partner)-0123456789-abcdefghij-[A-Z]+$` |
| Python lock hashes | whole line | `--hash=sha256:<64 hex>` with an optional trailing backslash |
| npm integrity | whole line | `"integrity": "sha512-<86 base64>=="` |

Path-scoped entries use `targetRules`. In gitleaks 8.30.1 `dir` mode, a global allowlist with `paths` skips the whole file even under `condition = "AND"` (open upstream as PR #2227); rule-scoped allowlists are evaluated correctly. A canary run confirmed it: with the default rules, 5 planted findings; with this config, 3 (only the two fake keys inside `test_api.py` are allowed; the same key in another file, a random-looking key in `test_api.py` and a token in a lock file are still reported).

If the fake keys in `test_api.py` change shape, update the regex, or gitleaks will flag them.

`.gitignore` keeps `.env`, `.env.*`, `*.db`, `*.db-wal`, `*.db-shm`, `backups/` and local working notes out of git.

## SBOM

The docker job writes `sbom-backend.cdx.json` and `sbom-frontend.cdx.json` (CycloneDX) with trivy and uploads both as the artifact `sbom-cyclonedx` (`if-no-files-found: error`). The local run produced CycloneDX 1.7 with 105 components for the backend image and 40 for the frontend image. Use them to answer "are we affected" when a new advisory names a package, for example with `trivy sbom sbom-backend.cdx.json`.

## Adding a suppression safely

A suppression is a decision with an owner, a reason and an end date. Prefer the upgrade.

| Tool | How | Rules |
|---|---|---|
| semgrep | `# nosemgrep: <full rule id>` on the flagged line, with a comment saying why | Never a bare `nosemgrep`, never `--exclude-rule` in CI, never exclude a whole directory of code |
| gitleaks | A new `[[allowlists]]` entry with `targetRules`, a `paths` regex for one file and a `regexes` entry for the exact value shape, plus a comment | Never a global `paths` entry (see above); test with a planted canary that a real-looking secret next to it is still reported |
| trivy | There is no `.trivyignore` today. If one is needed: one CVE id per line, a comment with the reason and a review date | Only for a finding with a fix that cannot be taken yet; unfixed findings are already ignored by the gate |
| Dependency advisories | An entry in `threat-intel/triage.json` with `id`, `package`, `reason` and `expires` ([THREAT_INTEL.md](THREAT_INTEL.md)) | Expiry 90 days or less by policy; a CISA KEV match can never be suppressed |
| pip-audit, npm audit | Not suppressed in CI | Upgrade, or triage through the threat brief |

## Before commit (suggested)

Nothing is installed in the repository. A minimal hook with the pre-commit framework:

```yaml
# .pre-commit-config.yaml (suggestion)
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks
```

```bash
pipx run pre-commit install
pipx run pre-commit autoupdate --freeze   # replaces the tag with a commit SHA
```

For backend changes, `cd backend && .venv/bin/python test_api.py` before pushing.

## Not run by CI

- **actionlint.** It ran locally on the workflows (release 1.7.12, with shellcheck and pyflakes): 0 errors. To repeat: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667`.
- **DAST.** No ZAP or similar scan of a running stack. The smoke job checks headers, the CSP nonce and the rate limit through the edge.
- **Frontend tests.** None exist yet ([QA_PLAN.md](QA_PLAN.md)).

## Known state on this branch

CI has not run on GitHub yet; the first run on pull request 2 is the check of every job. The local runs that back these docs used the files this branch commits, including the frontend Dockerfile (numeric `USER`, digest pins, npm removed) and `next` 16.3.8.
