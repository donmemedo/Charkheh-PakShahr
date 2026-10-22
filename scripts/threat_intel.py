#!/usr/bin/env python3
"""Dependency threat-intelligence brief for SabzBank. Stdlib only, Python 3.12.

Priority intelligence requirements (Direction):
  PIR-1  Which of our pinned packages (backend/requirements.txt, frontend/package-lock.json)
         have known vulnerabilities, how severe are they, and which version fixes them?
  PIR-2  Which of those are known to be exploited in the wild (CISA KEV)?
  PIR-3  Which accepted risks in threat-intel/triage.json have expired or no longer match anything?

Lifecycle (docs/THREAT_INTEL.md maps each phase to code):
  Collection     pins from the two lockfiles; OSV querybatch, then /v1/vulns/ID per advisory; the CISA KEV feed
  Processing     one finding per package and advisory, PYSEC/GHSA/CVE aliases merged; CVE aliases joined to KEV
  Analysis       severity rank, known-exploited flag, accepted-risk triage with expiry dates
  Dissemination  Markdown brief on stdout and in $GITHUB_STEP_SUMMARY; --json FILE for machines
  Feedback       triage entries carry a reason and an expiry, so every accepted risk comes back for review

Exit: 1 on any unsuppressed HIGH, CRITICAL or UNKNOWN finding, or any KEV match (triage cannot hide those);
      2 when OSV collection failed and --allow-offline was not given; 0 otherwise.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
BATCH = 1000  # OSV's documented querybatch maximum
TIMEOUT = 30
RANK = {"CRITICAL": 5, "HIGH": 4, "UNKNOWN": 3, "MEDIUM": 2, "LOW": 1}
# ponytail: no CVSS vector maths. GHSA records carry a rating; one without any ranks UNKNOWN and gates like
# HIGH (fail safe) until someone reads it and triages it. Add a CVSS 3.1 calculator if UNKNOWNs get noisy.
GATING = {"CRITICAL", "HIGH", "UNKNOWN"}
ROOT = Path(__file__).resolve().parent.parent


# ---- collection: parsing (pure) -----------------------------------------------------------------

def pypi_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()  # PEP 503


def parse_requirements(text: str) -> list[tuple[str, str]]:
    """name==version pins from a pip/uv lock; hash continuation lines, comments and options are skipped."""
    pins = []
    for line in text.splitlines():
        if m := re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;\\]+)", line):  # col 0 only
            pins.append((pypi_name(m[1]), m[2]))
    return list(dict.fromkeys(pins))


def parse_lockfile(lock: dict) -> list[tuple[str, str]]:
    """(name, version) for every installed package in an npm v2/v3 lockfile, deduplicated."""
    if "packages" not in lock:
        raise ValueError("package-lock.json has no 'packages' (lockfileVersion 1 is not supported)")
    pkgs = []
    for path, meta in lock["packages"].items():
        if not path or meta.get("link") or "version" not in meta:
            continue  # "" is the project itself; links point at a workspace folder
        pkgs.append((meta.get("name") or path.rsplit("node_modules/", 1)[-1], meta["version"]))
    return list(dict.fromkeys(pkgs))


# ---- processing and analysis (pure) -------------------------------------------------------------

def severity(vuln: dict) -> str:
    if vuln.get("id", "").startswith("MAL-"):
        return "CRITICAL"  # OpenSSF malicious-package report: the release itself is the attack
    s = str((vuln.get("database_specific") or {}).get("severity", "")).upper()
    s = {"MODERATE": "MEDIUM"}.get(s, s)
    return s if s in RANK else "UNKNOWN"


def fixed_versions(vuln: dict, ecosystem: str, name: str) -> list[str]:
    out = []
    for aff in vuln.get("affected", []):
        pkg = aff.get("package", {})
        if pkg.get("ecosystem") != ecosystem or norm(ecosystem, pkg.get("name", "")) != norm(ecosystem, name):
            continue
        out += [e["fixed"] for r in aff.get("ranges", []) for e in r.get("events", []) if "fixed" in e]
    return list(dict.fromkeys(out))


def norm(ecosystem: str, name: str) -> str:
    return pypi_name(name) if ecosystem == "PyPI" else name


def build_findings(pkgs: list[tuple[str, str, str]], hits: list[list[str]], vulns: dict, kev: dict) -> list[dict]:
    """One finding per (package, advisory group): ids that share an alias (PYSEC, GHSA, CVE) are merged."""
    findings = []
    for (eco, name, version), ids in zip(pkgs, hits):
        groups: list[dict] = []
        for vid in sorted(set(ids)):
            v = vulns.get(vid, {"id": vid})
            if v.get("withdrawn"):
                continue
            names = {vid, *v.get("aliases", [])}
            g = next((g for g in groups if g["ids"] & names), None)
            if g is None:
                g = {"ids": set(), "sevs": [], "fixed": [], "summary": ""}
                groups.append(g)
            g["ids"] |= names
            g["sevs"].append(severity(v))
            g["fixed"] = list(dict.fromkeys(g["fixed"] + fixed_versions(v, eco, name)))
            g["summary"] = g["summary"] or v.get("summary", "")
        for g in groups:
            rated = [s for s in g["sevs"] if s != "UNKNOWN"] or ["UNKNOWN"]  # a GHSA rating beats a bare PYSEC
            cves = sorted(i for i in g["ids"] if i.startswith("CVE-"))
            primary = next((i for i in sorted(g["ids"]) if i.startswith("GHSA-")), min(g["ids"]))
            findings.append({
                "ecosystem": eco, "package": name, "version": version, "id": primary,
                "aliases": sorted(g["ids"] - {primary}), "severity": max(rated, key=RANK.__getitem__),
                "fixed": g["fixed"], "summary": g["summary"] or "(no summary)",
                "kev": [c for c in cves if c in kev], "suppressed_by": None,
            })
    return sorted(findings, key=lambda f: (-RANK[f["severity"]], f["package"], f["id"]))


def apply_triage(findings: list[dict], entries: list[dict], today: date) -> list[str]:
    """Marks findings an active accepted-risk entry covers; returns the review notes (Feedback)."""
    notes, used = [], set()
    for n, e in enumerate(entries):
        label = f"{e.get('id', '?')} ({e.get('package', '?')})"
        try:
            expires = date.fromisoformat(e["expires"])
            if not (e["id"] and e["package"] and e["reason"].strip()):
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError):
            notes.append(f"invalid entry {label}: needs id, package, reason and expires YYYY-MM-DD")
            continue
        if expires < today:
            notes.append(f"expired {expires} — {label} no longer suppresses; decide again")
            continue
        for f in findings:
            if e["id"] in (f["id"], *f["aliases"]) and norm(f["ecosystem"], e["package"]) == f["package"]:
                used.add(n)
                if not f["kev"]:  # known exploited is never an accepted risk
                    f["suppressed_by"] = f"{e['reason'].strip()} (until {expires})"
        if n not in used:
            notes.append(f"stale entry {label}: matches no current finding; remove it")
    return notes


def exit_code(findings: list[dict], collected: bool, allow_offline: bool) -> int:
    if not collected and not allow_offline:
        return 2
    return int(any(f["kev"] or (f["severity"] in GATING and not f["suppressed_by"]) for f in findings))


def render(scope: list[str], findings: list[dict], kev_note: str, errors: list[str], notes: list[str], code: int) -> str:
    out = [f"# Dependency threat brief, {date.today()}", "", "Scope: " + "; ".join(scope) + ".",
           f"Sources: OSV.dev; {kev_note}.", ""]
    out += [f"> **Collection failed:** {e}" for e in errors] + ([""] if errors else [])
    out += ["## PIR-1: known vulnerabilities in our pins", ""]
    if findings:
        out += ["| Severity | Advisory | Package | Fixed in | Known exploited | Status |", "|---|---|---|---|---|---|"]
        for f in findings:
            status = f"accepted: {f['suppressed_by']}" if f["suppressed_by"] else "**open**"
            out.append(f"| {f['severity']} | {f['id']} {' '.join(f['aliases'])} | {f['ecosystem']} {f['package']} "
                       f"{f['version']} | {', '.join(f['fixed']) or 'no fix yet'} | {', '.join(f['kev']) or 'no'} "
                       f"| {status} |")
    else:
        out.append("None." if not errors else "Unknown: collection failed.")
    exploited = [f for f in findings if f["kev"]]
    out += ["", "## PIR-2: known exploited in the wild (CISA KEV)", ""]
    out += [f"- {f['package']} {f['version']}: {', '.join(f['kev'])}" for f in exploited] or ["None."]
    out += ["", "## PIR-3: triage review", ""] + ([f"- {n}" for n in notes] or ["Nothing to review."])
    verdict = {0: "PASS", 1: "FAIL: act on the open findings above", 2: "FAIL: collection incomplete"}[code]
    if code == 0 and errors:
        verdict = "INCOMPLETE: collection failed, allowed by --allow-offline"
    return "\n".join(out + ["", f"**Verdict: {verdict}** (exit {code})", ""])


# ---- collection: network ------------------------------------------------------------------------

def http_json(url: str, body: dict | None = None):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "sabzbank-threat-intel"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def query_osv(pkgs: list[tuple[str, str, str]]) -> list[list[str]]:
    hits = []
    for i in range(0, len(pkgs), BATCH):
        queries = [{"package": {"ecosystem": e, "name": n}, "version": v} for e, n, v in pkgs[i:i + BATCH]]
        results = http_json(OSV_BATCH, {"queries": queries})["results"]
        if len(results) != len(queries) or any(r.get("next_page_token") for r in results):
            raise ValueError("OSV returned a paged or partial batch; refusing an incomplete answer")
        hits += [[v["id"] for v in r.get("vulns", [])] for r in results]
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", metavar="FILE", help="also write the findings as JSON")
    ap.add_argument("--allow-offline", action="store_true", help="exit 0 instead of 2 when OSV is unreachable")
    args = ap.parse_args(argv)

    py = parse_requirements((ROOT / "backend/requirements.txt").read_text())
    js = parse_lockfile(json.loads((ROOT / "frontend/package-lock.json").read_text()))
    pkgs = [("PyPI", n, v) for n, v in py] + [("npm", n, v) for n, v in js]
    scope = [f"{len(py)} PyPI pins (backend/requirements.txt)", f"{len(js)} npm packages (frontend/package-lock.json)"]

    errors, hits, vulns = [], [[] for _ in pkgs], {}
    try:
        hits = query_osv(pkgs)
        # ponytail: one request per advisory, sequential; a thread pool if a lockfile ever has hundreds
        ids = sorted({i for ids in hits for i in ids})
        vulns = {i: http_json(OSV_VULN + urllib.parse.quote(i, safe="")) for i in ids}  # ids are external data
    except (OSError, ValueError, KeyError) as e:  # URLError and timeouts are OSError; bad JSON is ValueError
        errors.append(f"OSV: {e}")
        hits = [[] for _ in pkgs]
    try:
        feed = http_json(KEV_URL)
        kev = {v["cveID"]: v for v in feed["vulnerabilities"]}
        kev_note = f"CISA KEV catalog {feed.get('catalogVersion', '?')} ({len(kev)} CVEs)"
    except (OSError, ValueError, KeyError) as e:
        kev, kev_note = {}, f"KEV unavailable ({e}), so PIR-2 is unanswered this run"

    findings = build_findings(pkgs, hits, vulns, kev)
    triage_file = ROOT / "threat-intel/triage.json"
    entries = json.loads(triage_file.read_text()).get("entries", []) if triage_file.exists() else []
    notes = apply_triage(findings, entries, date.today())
    code = exit_code(findings, not errors, args.allow_offline)

    brief = render(scope, findings, kev_note, errors, notes, code)
    print(brief)
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(brief)
    if args.json:
        Path(args.json).write_text(json.dumps({"date": str(date.today()), "scope": scope, "kev": kev_note,
                                               "errors": errors, "triage_notes": notes, "exit": code,
                                               "findings": findings}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
