# Dependency threat intelligence

This document describes the threat-intelligence lifecycle SabzBank applies to the one attack surface it fully controls: the packages it pins. It walks the six phases (direction, collection, processing, analysis, dissemination, feedback) as implemented in [scripts/threat_intel.py](../scripts/threat_intel.py), the triage file and the weekly workflow, then lists metrics worth tracking and the limits of the approach. The run instructions and the triage format are in [../threat-intel/README.md](../threat-intel/README.md); this document explains the design.

## Scope

| In scope | Source file |
|---|---|
| Python runtime packages | `backend/requirements.txt` (the hash lock; dev-only packages in `requirements-dev.txt` are not included) |
| npm packages, runtime and build | `frontend/package-lock.json` (lockfile version 2 or 3; version 1 is refused) |

Out of scope here: OS packages in the images (trivy covers them in CI, see [DOCKER_HARDENING.md](DOCKER_HARDENING.md)), GitHub Actions (pinned by SHA and bumped by Dependabot), and threats to the running service (see [SECURITY.md](SECURITY.md)).

## 1. Direction: priority intelligence requirements

| PIR | Question | Consumer | Answered from |
|---|---|---|---|
| PIR-1 | Which of our pinned packages have known vulnerabilities, how severe are they, and which version fixes them? | Maintainers | OSV.dev (PyPI and npm: GHSA, PYSEC and OpenSSF malicious-package records) |
| PIR-2 | Which of those are known to be exploited in the wild? | Maintainers, tech lead | The CISA Known Exploited Vulnerabilities feed, joined on CVE aliases |
| PIR-3 | Which accepted risks have expired, are invalid, or no longer match anything? | Maintainers | `threat-intel/triage.json` |

Nothing outside these three questions is collected.

## 2. Collection

- **Pins.** `parse_requirements()` reads `name==version` lines at column 0 and skips hash continuation lines, comments and options; names are normalized per PEP 503. `parse_lockfile()` reads every installed package from the lockfile's `packages` map, skipping the project itself and workspace links.
- **OSV.** `query_osv()` sends one `POST https://api.osv.dev/v1/querybatch` per 1000 packages (OSV's documented maximum). A paged or partial answer is refused rather than half-read. Then `GET https://api.osv.dev/v1/vulns/<id>` fetches each advisory, with the id URL-quoted because it is external data.
- **KEV.** One `GET` of `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json`.
- **Resilience.** Every request has a 30 s timeout. If OSV fails, the run records `OSV: <error>` and the exit code is 2. If KEV fails, the brief says "KEV unavailable … PIR-2 is unanswered this run" and the run continues.
- **Dependencies.** Python 3.12 standard library only; no API keys.

## 3. Processing

`build_findings()` turns raw hits into findings:

- **One finding per package and advisory group.** Ids that share an alias (PYSEC, GHSA, CVE) are merged into one group, so a vulnerability published under three ids counts once. The primary id is the GHSA id when there is one.
- **Withdrawn advisories are dropped.**
- **Fixed versions** are taken only from the ranges that name this package in this ecosystem.
- **KEV join.** The group's CVE aliases are matched against the KEV catalogue.

## 4. Analysis

| Rule | Implementation |
|---|---|
| Severity is the GHSA rating in the advisory's `database_specific.severity`; `MODERATE` reads as `MEDIUM` | `severity()` |
| A `MAL-` record (OpenSSF malicious package) is `CRITICAL`: the release itself is the attack | `severity()` |
| No rating at all is `UNKNOWN`, which gates like `HIGH` until someone reads it (fail safe) | `severity()`, `GATING` |
| A group's severity is the highest rated one; a GHSA rating beats a bare PYSEC record without one | `build_findings()` |
| Known exploited (a KEV match) is flagged and can never be suppressed | `apply_triage()` |
| An active triage entry marks a matching finding as accepted | `apply_triage()` |

There is no CVSS vector calculation (a `ponytail:` comment names it as the upgrade if `UNKNOWN`s get noisy) and no EPSS score.

## 5. Dissemination

| Channel | Content | Audience |
|---|---|---|
| stdout | A Markdown brief: scope, sources, a PIR-1 table (severity, advisory and aliases, package and version, fixed in, known exploited, status), PIR-2, PIR-3, and a verdict line | Whoever runs it |
| `$GITHUB_STEP_SUMMARY` | The same brief on the workflow run page | Maintainers |
| `--json FILE` | Date, scope, KEV note, errors, triage notes, exit code and every finding | Machines, trend tracking |
| Artifact `threat-intel-brief` | The `.md` and `.json`, kept 90 days | History |
| Exit code | 0 PASS; 1 act: an open HIGH, CRITICAL or UNKNOWN finding, or any KEV match; 2 OSV collection failed (0 with `--allow-offline`, verdict INCOMPLETE) | The workflow: a red run means act |

```bash
python3 scripts/threat_intel.py                        # brief on stdout
python3 scripts/threat_intel.py --json brief.json      # also machine-readable
python3 scripts/threat_intel.py --allow-offline        # exit 0 instead of 2 when OSV is unreachable
python3 scripts/test_threat_intel.py                   # offline test of parsing, triage and the gate
```

`.github/workflows/threat-intel.yml` runs the brief every Monday at 04:41 UTC and on manual dispatch, with read-only permissions; the offline test runs in the CI backend job on pushes to main, pull requests and the weekly schedule.

## 6. Feedback

Accepted risks live in `threat-intel/triage.json`:

```json
{"entries": [
  {"id": "GHSA-xxxx-xxxx-xxxx", "package": "next", "reason": "image optimizer only; next/image is unused", "expires": "2027-01-15"}
]}
```

- **Every entry needs** `id` (any id of the group, GHSA or CVE), `package` (as in the lockfile), a non-empty `reason`, and `expires` as `YYYY-MM-DD`. An entry missing any of them is reported as invalid and suppresses nothing.
- **Expiry is inclusive.** The day after, the entry stops suppressing, the gate fails again, and someone decides anew. The policy is 90 days or less; the script does not enforce the length, so review it in the PR.
- **Stale entries** (matching no current finding) are listed for removal.
- **A KEV match is never accepted**, whatever the triage file says.
- **Before adding an entry**, read the advisory and confirm the vulnerable code path is not reachable here. Prefer the upgrade: Dependabot opens the bump PRs.

Review cadence: the weekly brief lists PIR-3 notes; act on them in the same week. Re-read every accepted risk when it is within two weeks of expiry.

## Results so far

- Live run against the repository: 16 PyPI pins and 101 npm packages; KEV catalogue 2026.10.21 (1754 CVEs); PIR-1, PIR-2 and PIR-3 all "None"; verdict PASS, exit 0.
- Positive control (old `jinja2` 2.10 and `lodash` 4.17.15 pins): 12 findings, 4 HIGH, aliases merged, fixed versions shown, exit 1.
- Network forced down: exit 2, or exit 0 marked INCOMPLETE with `--allow-offline`.

## Metrics worth tracking

From the `--json` artifacts, week over week:

| Metric | Why |
|---|---|
| Open findings by severity | The backlog the gate is holding back |
| Days from an advisory's first appearance in the brief to the merged fix | Remediation speed; set a target per severity |
| KEV matches | Should be zero; any one is an incident |
| `UNKNOWN` findings | Rating gaps that need a human read |
| Accepted risks: count, age, days to expiry | Triage debt; a growing count means upgrades are being avoided |
| Stale and invalid triage entries | Hygiene of the feedback loop |
| Runs with exit 2 | Collection reliability |
| Age of open Dependabot PRs and lock-refresh lag | Whether the fixes the brief points to are actually landing |

## Limits

- **No reachability analysis.** A finding means the vulnerable version is pinned, not that the vulnerable function is called. Reachability is a human judgement recorded in the triage `reason`.
- **Pins only.** Vendored code, OS packages and the Node and Python runtimes in the images are outside this script (trivy covers the image layers).
- **Development Python packages** (`requirements-dev.txt`, for example httpx) are not scanned; the npm lockfile includes development packages.
- **Severity is GHSA's.** No CVSS vector maths, no EPSS, no environmental scoring.
- **KEV joins on CVE ids only.** An exploited GHSA-only advisory is not flagged as known exploited.
- **Stateless.** Each run stands alone; trends exist only in the kept artifacts.
- **Source availability.** OSV and KEV are single sources; a CISA or OSV outage leaves PIR-2 or the whole run unanswered (reported, never silent).
