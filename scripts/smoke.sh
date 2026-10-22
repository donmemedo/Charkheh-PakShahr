#!/usr/bin/env bash
# Smoke checks against a running SabzBank stack. Rerunnable; prints PASS/FAIL per check, exits 1 on any FAIL.
#   scripts/smoke.sh        backend only: health, catalog demo flag, rate limit, container lockdown
#   scripts/smoke.sh full   also through the Caddy edge: security headers, CSP nonce, forged X-Forwarded-For
# Environment:
#   API_URL      backend base URL   (default http://127.0.0.1:${API_PORT:-8026})
#   WEB_URL      edge base URL      (default http://127.0.0.1:${WEB_PORT:-3026})
#   EXPECT_DEMO  1 or 0, the "demo" flag /api/catalog must report (default ${DEMO_MODE:-0})
#   PROJECT      compose project name for the container checks (default: compose's own default)
#   DOCKER       docker command (default "docker"; e.g. "docker --context default"); no docker = checks skipped
set -euo pipefail
cd "$(dirname "$0")/.."

mode=${1:-backend}
[[ $mode == backend || $mode == full ]] || { echo "usage: $0 [full]" >&2; exit 2; }
API_URL=${API_URL:-http://127.0.0.1:${API_PORT:-8026}}
WEB_URL=${WEB_URL:-http://127.0.0.1:${WEB_PORT:-3026}}
EXPECT_DEMO=${EXPECT_DEMO:-${DEMO_MODE:-0}}
read -ra DOCKER <<<"${DOCKER:-docker}"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

fails=0
check() { # check "name" command...: PASS when the command succeeds
  local name=$1; shift
  if "$@"; then echo "PASS $name"; else echo "FAIL $name"; fails=$((fails + 1)); fi
}
fetch() { curl -sS --max-time 10 "$@" 2>"$tmp/curl.err" || true; }
has() { grep -qiE -- "$1" "$2"; }
lacks() { ! grep -qiE -- "$1" "$2"; }

# 12 POSTs in a burst (BURST is 10 in main.py), extra curl args per request; prints the first 429's index or 0
burst() {
  local url=$1 i code; shift
  for i in $(seq 1 12); do
    code=$(fetch -o /dev/null -w '%{http_code}' -X POST -H 'content-type: application/json' "${@//\{i\}/$i}" \
      -d '{"choice":0}' "$url/api/missions/nope/answer")
    [ "$code" = 429 ] && { echo "$i"; return; }
  done
  echo 0
}

# ---- backend ----------------------------------------------------------------------------------
check "health: $API_URL/api/health is {\"ok\":true}" test "$(fetch "$API_URL/api/health")" = '{"ok":true}'
want=$([ "$EXPECT_DEMO" = 1 ] && echo true || echo false)
fetch "$API_URL/api/catalog" >"$tmp/catalog"
check "catalog: demo flag is $want" has "\"demo\":${want}[,}]" "$tmp/catalog"
n=$(burst "$API_URL")
check "rate limit: a 12-request burst to the backend hits 429 (first at #$n)" test "$n" -gt 0

# ---- containers (only when docker can see the compose project) ---------------------------------
dc=("${DOCKER[@]}" compose)
[ -n "${PROJECT:-}" ] && dc+=(-p "$PROJECT")
services=(backend)
[ "$mode" = full ] && services+=(frontend edge)
if command -v "${DOCKER[0]}" >/dev/null && cid=$("${dc[@]}" ps -q backend 2>/dev/null) && [ -n "$cid" ]; then
  check "backend: runs as uid 10001" test "$("${DOCKER[@]}" exec "$cid" id -u)" = 10001
  write_fails() { ! "${DOCKER[@]}" exec "$1" touch /app/.smoke 2>/dev/null; }
  check "backend: writing /app fails (read-only root filesystem)" write_fails "$cid"
  for s in "${services[@]}"; do
    cid=$("${dc[@]}" ps -q "$s" 2>/dev/null) || cid=""
    ro="" user="" health=""
    [ -n "$cid" ] && read -r ro user health < <("${DOCKER[@]}" inspect -f \
      '{{.HostConfig.ReadonlyRootfs}} {{if .Config.User}}{{.Config.User}}{{else}}root{{end}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid") || true
    check "$s: read-only root filesystem, non-root user ($user), healthy ($health)" \
      test "$ro:$health" = true:healthy -a "$user" != root -a "${user%%:*}" != 0
  done
else
  echo "SKIP container checks: no docker, or no backend container in this compose project"
fi

# ---- through the edge ---------------------------------------------------------------------------
if [ "$mode" = full ]; then
  fetch -D "$tmp/h1" -o "$tmp/b1" "$WEB_URL/" >/dev/null
  fetch -D "$tmp/h2" -o /dev/null "$WEB_URL/" >/dev/null
  nonce() { grep -i '^content-security-policy:' "$1" | grep -o "'nonce-[^']*'" | sed "s/'nonce-//; s/'//" || true; }
  n1=$(nonce "$tmp/h1"); n2=$(nonce "$tmp/h2")
  check "web: $WEB_URL/ answers 200" has '^HTTP/[0-9.]+ 200' "$tmp/h1"
  check "web: CSP carries a fresh nonce per request" test -n "$n1" -a -n "$n2" -a "$n1" != "$n2"
  check "web: the page's script tags carry that nonce" grep -qF "nonce=\"$n1\"" "$tmp/b1"
  csp_has() { grep -i '^content-security-policy:' "$tmp/h1" | grep -qF -- "$1"; }
  csp_strict() { csp_has "'strict-dynamic'" && csp_has "object-src 'none'" && csp_has "frame-ancestors 'none'"; }
  check "web: CSP has 'strict-dynamic', object-src 'none', frame-ancestors 'none'" csp_strict
  for h in 'x-content-type-options: nosniff' 'x-frame-options: deny' 'referrer-policy: strict-origin-when-cross-origin' \
    'permissions-policy: camera=\(\)' 'cross-origin-opener-policy: same-origin'; do
    check "web: header ${h//\\/}" has "^$h" "$tmp/h1"
  done
  check "web: no X-Powered-By header" lacks '^x-powered-by:' "$tmp/h1"
  fetch "$WEB_URL/api/catalog" >"$tmp/catalog_edge"
  check "edge: /api/catalog reaches the backend (demo flag $want)" has "\"demo\":${want}[,}]" "$tmp/catalog_edge"
  n=$(burst "$WEB_URL" -H 'X-Forwarded-For: 10.9.{i}.{i}')
  check "edge: 12 POSTs with forged X-Forwarded-For still hit 429 (first at #$n)" test "$n" -gt 0
fi

if [ "$fails" -gt 0 ]; then echo "smoke: $fails check(s) FAILED"; exit 1; fi
echo "smoke: all checks passed ($mode)"
