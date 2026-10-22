# Docker hardening

This document is the container-hardening checklist for SabzBank, in the style of the CIS Docker Benchmark: each control that is applied, the line of [docker-compose.yml](../docker-compose.yml), [backend/Dockerfile](../backend/Dockerfile) or [frontend/Dockerfile](../frontend/Dockerfile) it lives in, and the evidence that it works. It then states the real results of hadolint, trivy and gitleaks, the policy for vulnerabilities that have no fix, what was considered and rejected, and what is not done. The evidence comes from a local build and run of the full stack (compose project `sabzci`, `DEMO_MODE=1`) with the tools pinned by digest.

## Checklist

| # | Control | Where | Evidence |
|---|---|---|---|
| 1 | **Non-root users, numeric.** backend uid 10001, frontend 1000:1000, edge 65534:65534; the `ops` jobs inherit 10001 | `backend/Dockerfile` `useradd -r -u 10001` and `USER 10001`; `frontend/Dockerfile` `USER 1000:1000`; compose `edge` `user: "65534:65534"` | `smoke.sh`: "backend: runs as uid 10001"; full mode: each of backend, frontend and edge non-root. `docker inspect` showed user 10001, 1000:1000, 65534:65534. hadolint DL3066 (non-numeric user) cleared |
| 2 | **Read-only root filesystem**, with tmpfs only where a process must write | compose `read_only: true` on backend, frontend, edge and the `x-ops` anchor; `tmpfs`: backend `/tmp`; frontend `/tmp`, `/app/.next/cache`; edge `/data` and `/config` owned by 65534 | `smoke.sh`: "writing /app fails"; full mode: read-only root on all three. Six pages, `icon.svg` and the JS and CSS chunks returned 200 from the read-only frontend, with no EROFS or EACCES in the logs |
| 3 | **All capabilities dropped**; the edge adds back only `NET_BIND_SERVICE` | compose `cap_drop: [ALL]` on every service; `edge` `cap_add: [NET_BIND_SERVICE]` | `docker inspect`. The caddy binary carries that file capability and its exec fails without it |
| 4 | **No privilege escalation** | compose `security_opt: [no-new-privileges:true]` on every service | `docker inspect` |
| 5 | **Process and memory limits** | compose `pids_limit`: backend 128 (threads count; anyio's pool grows to 40), frontend 128, edge 64, ops 32. `mem_limit`: 256m, 512m, 128m, 128m. `cpus: 1` on backend, frontend and edge | `docker inspect`. Idle process counts: backend 7, frontend 11, edge 8 |
| 6 | **Log rotation** | compose `x-logging` anchor: `json-file`, `max-size: 10m`, `max-file: 5`, on every service | `docker inspect` |
| 7 | **Images pinned by digest** | `FROM python:3.12-slim@sha256:05cda977…`; `FROM node:22-alpine@sha256:0a7108bf…` (both stages); `caddy:2-alpine@sha256:d8542f48…`; CI tool images and actions by digest or SHA | `grep @sha256` in both Dockerfiles and compose; Dependabot `docker` and `docker-compose` entries keep them fresh |
| 8 | **Healthchecks and ordered startup** | backend: Python `urlopen` of `/api/health` (readiness: a real write and free space); frontend: `wget` of `/` (server render); edge: `wget` of `/icon.svg` through Caddy and Next. `depends_on … condition: service_healthy` chains backend, frontend, edge | `up -d --wait` reached all healthy in 30 s. Each check passed by hand. With the frontend stopped, the edge check got `502 Bad Gateway` and exit 1 |
| 9 | **Minimal network exposure** | Only the edge publishes a public port (`${WEB_PORT:-3026}:80`). The backend publishes on loopback only (`${API_BIND:-127.0.0.1}:${API_PORT:-8026}`). The frontend publishes nothing | compose `ports`. `smoke.sh full`: 12 POSTs with a forged `X-Forwarded-For` through the edge still hit 429 |
| 10 | **Secrets from the environment, never in images** | compose `COLLECTOR_KEY: "${COLLECTOR_KEY:-}"`, `PARTNER_KEY: "${PARTNER_KEY:-}"`; `.dockerignore` excludes `.env*` in both images (and `*.db*`, `data` for the backend); `.gitignore` excludes `.env` and `.env.*`; weak keys stop startup | gitleaks clean on the history and the checked-out files; CI jobs get no keys |
| 11 | **Non-root, read-only edge** | compose `edge`: `user`, `read_only`, uid-owned tmpfs for `/data` and `/config` | Caddy writes only `/data/caddy/{instance.uuid,last_clean.json,locks}` and logs no errors. Without `uid=65534` on the tmpfs it failed with `mkdir /data/caddy: permission denied` |
| 12 | **Supply-chain hygiene in the build** | `pip install --no-cache-dir --require-hashes`; `npm ci --ignore-scripts` (0 of the lockfile's entries declare an install script); multi-stage frontend build; the runtime stage deletes npm, npx, corepack and yarn | trivy: frontend HIGH count from 11 to 0 after the npm removal |
| 13 | **No banner, no proxy trust, one access log** | `uvicorn … --no-server-header --no-proxy-headers --no-access-log`; Next `poweredByHeader: false` | `smoke.sh full`: "no X-Powered-By header" |
| 14 | **Read-only one-shot jobs** | `x-ops`: the backend image with `pull_policy: never`, `read_only`, `cap_drop`, `no-new-privileges`, `pids_limit: 32`, `mem_limit: 128m`, `restart: "no"` | `--profile ops run --rm ops`: `event=backup ok=1`, integrity check `ok` on the copy; `ledger-check`: `ok=1`. Into an unwritable directory: `ok=0`, exit 1 |

## Tool results

Tools: hadolint 2.15.1, trivy 0.76.1, gitleaks 8.30.1, actionlint 1.7.12, each run from its image pinned by digest.

**hadolint**, both Dockerfiles:

- Before: `DL3066 info: Non-numeric user-id` on `USER sabz` (backend) and `USER node` (frontend); exit 1 each.
- After `USER 10001` and `USER 1000:1000`: exit 0, no findings. (Dockerfile has no trailing comments, so the explanatory comments sit on their own lines.)

**trivy**, HIGH and CRITICAL, on the images built before this hardening:

| Image | Base | Findings | With a fix | What they are |
|---|---|---|---|---|
| backend | Debian 13.7 (`python:3.12-slim`) | 44 HIGH, 0 CRITICAL | 0 | OS packages: ncurses (CVE-2025-69720), libsystemd0 and libudev1 (CVE-2026-16742), libacl1 (CVE-2026-54369), the util-linux family (CVE-2026-76642, -78408, -78409, -78410), perl-base (CVE-2026-9538, fix deferred by Debian) |
| frontend | Alpine 3.24.2 (`node:22-alpine`) | 11 HIGH | 10 | All inside `/usr/local/lib/node_modules/npm`, the npm CLI bundled in the base image and unused at runtime: brace-expansion, picomatch, sigstore, ip-address, pacote, http-cache-semantics |

On freshly built images with the CI gate settings (`--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`): both exit 0. The backend still has the 44 unfixed HIGH findings above. The frontend has 0 HIGH or CRITICAL even without `--ignore-unfixed`, because the runtime stage now deletes npm. CycloneDX 1.7 SBOMs: 105 components (backend), 40 (frontend).

(The trivy database was fetched from `ghcr.io/aquasecurity/trivy-db:2` because the default mirror was not reachable from the build network; CI keeps the action's default.)

**gitleaks**, with `.gitleaks.toml`:

- History (`git` mode), at the time of the run: 5 commits, about 829 KB, no leaks; also no leaks with the default rules alone. The branch has more commits since; CI's `secrets` job scans the full history on every run.
- The checked-out files (`dir` mode, the 56 files git would have committed at the time of the run): no leaks.
- Canary: planted findings gave 5 with the default rules and 3 with the config; only the two intentional fake keys in `backend/test_api.py` are allowed.

**actionlint** (with shellcheck and pyflakes) on the workflows: 0 errors. shellcheck on `scripts/smoke.sh`: clean.

**Smoke** against the running stack: `scripts/smoke.sh full` 20 of 20 PASS, twice; `scripts/smoke.sh` (backend mode) 6 of 6. Negative controls fail as they should: `EXPECT_DEMO=0` gives `FAIL catalog: demo flag is false` and exit 1; a dead `API_URL` gives 3 FAIL and exit 1.

## Policy for vulnerabilities without a fix

- The CI gate fails only on HIGH or CRITICAL findings that have a fixed version (`ignore-unfixed: true`). An unfixed finding cannot be acted on by upgrading, and a gate that is always red stops being read.
- The weekly scheduled CI run rebuilds from the same pinned digests and scans again. When Debian or Alpine ships a fix, the finding becomes fixable in the old pinned image, the job turns red, and the Dependabot `docker` PR that bumps the digest is the fix.
- The 44 backend findings are in OS packages the app does not call directly (terminal, systemd, ACL, util-linux and perl libraries).
- Language packages are covered separately by pip-audit, npm audit and the threat brief ([THREAT_INTEL.md](THREAT_INTEL.md)).

## Considered and rejected

| Option | Why not here |
|---|---|
| A Caddyfile routing `/api` straight to FastAPI | It changes the verified trust chain for `X-Forwarded-For` (findings N1 and N8); revisit with the TLS topology |
| TLS with a persistent `caddy_data` volume, and an IP allowlist on the collector and partner routes | Need a real hostname and the collector and partner addresses |
| An edge access log | Client IPs are personal data; needs a retention policy first |
| A custom seccomp or AppArmor profile | Docker's default seccomp profile already applies; a custom one needs syscall profiling and upkeep |
| `daemon.json` changes and user-namespace remapping | Daemon-wide settings on a shared Docker host affect other projects |
| Image signing | There is no registry; images are built where they run |
| Distroless bases or chasing digests by hand | The 44 backend findings have no Debian fix; Dependabot bumps digests |
| `init: true` | uvicorn and node handle SIGTERM themselves |
| `.git` in `frontend/.dockerignore` | The build context is `./frontend`; `.git` is at the repository root and never enters it |

## Not done

- **Content trust.** `DOCKER_CONTENT_TRUST` is not used and images are not signed or verified by signature.
- **Custom seccomp profile.** Docker's default profile only.
- **Daemon-level settings.** No `icc: false`, `userns-remap`, `live-restore`, default ulimits or TLS on the daemon socket. These are host decisions.
- **docker-bench-security and Dockle.** Not run. Run docker-bench-security on the production host after deployment; it audits the host and daemon as much as the containers.
- **Network segmentation.** All services share the default compose network, so the edge can reach `backend:8000` directly. An internal network for frontend-to-backend traffic would narrow that.
- **File-based secrets.** Keys are environment variables, visible to `docker inspect` for anyone with access to the Docker daemon.

## Reproduce

```bash
export COMPOSE_PROJECT_NAME=sabzci DEMO_MODE=1 WEB_PORT=3226 API_PORT=8226
docker compose build
docker compose up -d --wait --wait-timeout 300
PROJECT=sabzci scripts/smoke.sh full
for s in backend frontend edge; do
  docker inspect -f "$s user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}} caps={{.HostConfig.CapDrop}}+{{.HostConfig.CapAdd}} secopt={{.HostConfig.SecurityOpt}} pids={{.HostConfig.PidsLimit}} mem={{.HostConfig.Memory}} log={{.HostConfig.LogConfig.Config}}" \
    "$(docker compose ps -q $s)"
done
docker compose --profile ops run --rm ledger-check
docker compose down -v      # the throwaway sabzci volume only
```

The hadolint, trivy and gitleaks commands are in [DEVSECOPS.md](DEVSECOPS.md).
