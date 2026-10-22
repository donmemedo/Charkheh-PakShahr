"""Assert-based checks for threat_intel.py's pure functions, on canned data (no network). Prints ok."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import threat_intel as ti  # noqa: E402

# ---- requirements parsing: pins only, hash continuation lines and comments skipped --------------
REQ = """# Hash-locked runtime tree
--index-url https://pypi.org/simple
Annotated_Types==0.8.0 \\
    --hash=sha256:13b2beaad985e05e2d6407ee4c4f35590b11f8d693a258a561055cac8f64cab7 \\
    --hash=sha256:f072f4d804ea359e4eaf198b1af7a8b0943881a87f31bb764f8bf219bb9419e0
    # via pydantic
uvicorn[standard]==0.53.0 ; python_version >= "3.9"
uvloop==0.22.1 \\
    --hash=sha256:aaaa
    fake==9.9 is a continuation, not a pin
-r other.txt
"""
assert ti.parse_requirements(REQ) == [("annotated-types", "0.8.0"), ("uvicorn", "0.53.0"), ("uvloop", "0.22.1")]
assert ti.parse_requirements(REQ + "uvloop==0.22.1\n")[-1] == ("uvloop", "0.22.1")  # deduplicated
assert len(ti.parse_requirements(REQ + "uvloop==0.22.1\n")) == 3

# ---- lockfile parsing: root, links and version-less entries skipped; nested paths and aliases named ---
LOCK = {"lockfileVersion": 3, "packages": {
    "": {"name": "frontend", "version": "0.1.0"},
    "node_modules/next": {"version": "16.3.8"},
    "node_modules/@img/colour": {"version": "1.1.0", "dev": True},
    "node_modules/a/node_modules/semver": {"version": "6.3.1"},
    "node_modules/b/node_modules/semver": {"version": "6.3.1"},
    "node_modules/alias": {"name": "real-pkg", "version": "2.0.0"},
    "node_modules/ws-link": {"link": True, "resolved": "../ws"},
    "node_modules/broken": {},
}}
assert ti.parse_lockfile(LOCK) == [("next", "16.3.8"), ("@img/colour", "1.1.0"), ("semver", "6.3.1"),
                                   ("real-pkg", "2.0.0")]
try:
    ti.parse_lockfile({"lockfileVersion": 1, "dependencies": {}})
    raise AssertionError("a v1 lockfile must be refused, not read as empty")
except ValueError:
    pass

# ---- severity ranking -----------------------------------------------------------------------------
assert ti.severity({"id": "GHSA-1", "database_specific": {"severity": "HIGH"}}) == "HIGH"
assert ti.severity({"id": "GHSA-2", "database_specific": {"severity": "MODERATE"}}) == "MEDIUM"
assert ti.severity({"id": "PYSEC-3", "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N"}]}) == "UNKNOWN"
assert ti.severity({"id": "MAL-2026-1"}) == "CRITICAL"
assert ti.RANK["CRITICAL"] > ti.RANK["HIGH"] > ti.RANK["UNKNOWN"] > ti.RANK["MEDIUM"] > ti.RANK["LOW"]

# ---- processing: alias groups merge, fixed versions per package, KEV join -----------------------
pkgs = [("PyPI", "starlette", "0.1.0"), ("npm", "next", "16.0.0"), ("npm", "lodash", "4.0.0")]
hits = [["PYSEC-9", "GHSA-aaaa"], ["GHSA-bbbb"], ["GHSA-cccc", "GHSA-dddd"]]
vulns = {
    "PYSEC-9": {"id": "PYSEC-9", "aliases": ["CVE-2026-1", "GHSA-aaaa"], "affected": [
        {"package": {"ecosystem": "PyPI", "name": "Starlette"}, "ranges": [{"events": [{"introduced": "0"},
                                                                                      {"fixed": "0.2.0"}]}]}]},
    "GHSA-aaaa": {"id": "GHSA-aaaa", "aliases": ["CVE-2026-1"], "summary": "path traversal",
                  "database_specific": {"severity": "MODERATE"}},
    "GHSA-bbbb": {"id": "GHSA-bbbb", "aliases": ["CVE-2026-2"], "database_specific": {"severity": "CRITICAL"},
                  "affected": [{"package": {"ecosystem": "npm", "name": "other"},
                                "ranges": [{"events": [{"fixed": "9.9.9"}]}]}]},
    "GHSA-cccc": {"id": "GHSA-cccc", "database_specific": {"severity": "LOW"}},
    "GHSA-dddd": {"id": "GHSA-dddd", "withdrawn": "2026-01-01T00:00:00Z", "database_specific": {"severity": "HIGH"}},
}
f = ti.build_findings(pkgs, hits, vulns, kev={"CVE-2026-2": {}})
assert [(x["package"], x["id"], x["severity"]) for x in f] == [
    ("next", "GHSA-bbbb", "CRITICAL"), ("starlette", "GHSA-aaaa", "MEDIUM"), ("lodash", "GHSA-cccc", "LOW")], f
star = f[1]
assert star["aliases"] == ["CVE-2026-1", "PYSEC-9"] and star["fixed"] == ["0.2.0"] and star["kev"] == []
assert star["summary"] == "path traversal"
assert f[0]["kev"] == ["CVE-2026-2"] and f[0]["fixed"] == []  # the fix listed is for another package

# ---- triage: active entries suppress, expired and invalid ones do not, KEV is never suppressed ----
def fresh():
    return ti.build_findings(pkgs, hits, vulns, kev={"CVE-2026-2": {}})


today = date(2026, 10, 22)
f = fresh()
notes = ti.apply_triage(f, [
    {"id": "CVE-2026-1", "package": "Starlette", "reason": "not reachable: no StaticFiles", "expires": "2026-10-22"},
    {"id": "GHSA-bbbb", "package": "next", "reason": "we hope", "expires": "2027-01-01"},
    {"id": "GHSA-cccc", "package": "lodash", "reason": "old", "expires": "2026-10-21"},
    {"id": "GHSA-zzzz", "package": "left-pad", "reason": "gone", "expires": "2027-01-01"},
    {"id": "GHSA-cccc", "package": "lodash", "reason": "  ", "expires": "2027-01-01"},
    {"id": "GHSA-cccc", "package": "lodash", "reason": "x", "expires": "next year"},
], today)
by = {x["package"]: x for x in f}
assert by["starlette"]["suppressed_by"].startswith("not reachable")  # alias match; expiry day is inclusive
assert by["next"]["suppressed_by"] is None  # in KEV: triage cannot accept it
assert by["lodash"]["suppressed_by"] is None  # expired yesterday
assert any(n.startswith("expired 2026-10-21") for n in notes)
assert any(n.startswith("stale entry GHSA-zzzz") for n in notes)
assert sum(n.startswith("invalid entry") for n in notes) == 2

# ---- exit-code decision -------------------------------------------------------------------------
assert ti.exit_code([], collected=True, allow_offline=False) == 0
assert ti.exit_code([], collected=False, allow_offline=False) == 2
assert ti.exit_code([], collected=False, allow_offline=True) == 0
low = {"severity": "LOW", "kev": [], "suppressed_by": None}
assert ti.exit_code([low, {**low, "severity": "MEDIUM"}], True, False) == 0
for sev in ("HIGH", "CRITICAL", "UNKNOWN"):
    assert ti.exit_code([{**low, "severity": sev}], True, False) == 1
    assert ti.exit_code([{**low, "severity": sev, "suppressed_by": "accepted"}], True, False) == 0
assert ti.exit_code([{**low, "kev": ["CVE-2026-2"]}], True, False) == 1  # a LOW in KEV still fails

# ---- the brief renders every PIR and the verdict --------------------------------------------------
md = ti.render(["1 PyPI pin"], fresh(), "CISA KEV catalog x", [], ["stale entry y"], 1)
assert "## PIR-1" in md and "## PIR-2" in md and "## PIR-3" in md and "next 16.0.0: CVE-2026-2" in md
assert "**Verdict: FAIL" in md and "| CRITICAL | GHSA-bbbb CVE-2026-2 |" in md
assert "Unknown: collection failed." in ti.render([], [], "KEV unavailable", ["OSV: timeout"], [], 2)
assert "INCOMPLETE" in ti.render([], [], "KEV unavailable", ["OSV: timeout"], [], 0)
print("ok")
