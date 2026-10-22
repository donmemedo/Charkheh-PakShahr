# Dependency threat intelligence

A small intelligence cycle for the one attack surface we fully control: the packages we pin.
It runs weekly in CI (`.github/workflows/threat-intel.yml`) and on demand:

```sh
python3 scripts/threat_intel.py                 # Markdown brief on stdout; exit 1 means act
python3 scripts/threat_intel.py --json brief.json
python3 scripts/test_threat_intel.py            # checks the parsing, triage and gate logic offline
```

## Priority intelligence requirements

| PIR | Question | Answered from |
|---|---|---|
| PIR-1 | Which of our pinned packages have known vulnerabilities, how severe, and which version fixes them? | OSV.dev (PyPI and npm ecosystems, GHSA, PYSEC and OpenSSF malicious-package records) |
| PIR-2 | Which of those are known to be exploited in the wild? | CISA Known Exploited Vulnerabilities feed, joined on CVE aliases |
| PIR-3 | Which accepted risks have expired or no longer match anything? | `threat-intel/triage.json` |

## Lifecycle phases

| Phase | Where | What happens |
|---|---|---|
| Direction | `scripts/threat_intel.py` docstring, this table | The three PIRs above; nothing outside them is collected. |
| Collection | `parse_requirements`, `parse_lockfile`, `query_osv`, `main` | Pins from `backend/requirements.txt` (hash lines skipped) and `frontend/package-lock.json`; one OSV `querybatch` per 1000 packages, then `/v1/vulns/ID` for each advisory; the KEV JSON with a 30 s timeout. An unreachable KEV is reported as "KEV unavailable"; an unreachable OSV is exit 2. |
| Processing | `build_findings` | One finding per package and advisory: PYSEC, GHSA and CVE ids that alias each other are merged, withdrawn records dropped, fixed versions taken only from that package's ranges. |
| Analysis | `severity`, `apply_triage`, `exit_code` | GHSA rating (MODERATE reads as MEDIUM); `MAL-` records are CRITICAL; no rating is UNKNOWN and gates like HIGH. KEV matches are flagged. Active triage entries mark findings accepted. |
| Dissemination | `render`, `main` | Markdown brief to stdout and `$GITHUB_STEP_SUMMARY`, the brief as a CI artifact, `--json FILE` for machines. |
| Feedback | `triage.json`, PIR-3 in the brief | Every accepted risk carries a reason and an expiry date; after it the gate fails again. The brief lists expired, invalid and stale entries for review. |

## Gate

Exit 1 on any open HIGH, CRITICAL or UNKNOWN finding, or any KEV match (a KEV match cannot be triaged away).
Exit 2 when OSV collection failed, unless `--allow-offline`. Exit 0 otherwise.

## Accepting a risk

Add an entry to `triage.json` only after reading the advisory and confirming the vulnerable code path is not
reachable here. Example:

```json
{"id": "GHSA-xxxx-xxxx-xxxx", "package": "next", "reason": "image optimizer only; next/image is unused", "expires": "2027-01-15"}
```

Keep expiries at 90 days or less, and prefer upgrading: Dependabot opens the bump PRs (`.github/dependabot.yml`).
