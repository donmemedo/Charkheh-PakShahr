# Dependency threat intelligence

`triage.json` holds the accepted risks for the weekly dependency brief (`scripts/threat_intel.py`, run by
`.github/workflows/threat-intel.yml`). The full process (the three intelligence requirements, collection, gate,
exit codes and metrics) is in [docs/THREAT_INTEL.md](../docs/THREAT_INTEL.md).

```sh
python3 scripts/threat_intel.py                 # Markdown brief on stdout; exit 1 means act
python3 scripts/test_threat_intel.py            # checks the parsing, triage and gate logic offline
```

Add an entry only after reading the advisory and confirming the vulnerable code path is not reachable here:

```json
{"id": "GHSA-xxxx-xxxx-xxxx", "package": "next", "reason": "image optimizer only; next/image is unused", "expires": "2027-01-15"}
```

Keep expiries at 90 days or less, and prefer upgrading: Dependabot opens the bump PRs (`.github/dependabot.yml`).
A KEV match cannot be triaged away.
