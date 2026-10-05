#!/usr/bin/env bash
# Check whether domain names are registered.
#
#   bash check.sh [--tlds "com ai io"] name-or-domain [...]
#
# A bare name (acme) is checked with each ending in --tlds (default: com). A full domain
# (acme.co.uk) is checked as given. One line per domain, AVAILABLE first:
#
#   AVAILABLE  acme-example.com  (registry: no registration record)
#   TAKEN      example.com       (registry: registered)
#   UNCLEAR    example.xyz       (whois timed out)
#
# How it decides: it asks rdap.org, which forwards the question to the registry that runs the
# ending. A registry's own answer is trusted. Where rdap.org has no registry to forward to, is
# rate-limited or times out, the system whois is asked instead. It never answers AVAILABLE on
# a guess: anything it cannot read is UNCLEAR.
#
# Exit codes: 0 every domain got an answer line, 1 bad arguments, 2 curl is missing,
# 3 a lookup died (its domain is printed as UNCLEAR).
#
# Environment: RDAP_BASE (default https://rdap.org/domain), WHOIS_CMD (default whois),
# DOMAIN_CHECK_TIMEOUT in seconds for each lookup (default 10).
set -u

RDAP_BASE="${RDAP_BASE:-https://rdap.org/domain}"
WHOIS_CMD="${WHOIS_CMD:-whois}"
LIMIT="${DOMAIN_CHECK_TIMEOUT:-10}"

say() { printf '%-9s  %s  (%s)\n' "$1" "$2" "$3"; }

host_of() { printf '%s' "$1" | sed -E 's#^[a-zA-Z]+://([^/]+).*#\1#'; }

# Runs whois under the time limit (macOS has no `timeout` command). Prints its output.
# Returns 127 when whois is not installed, 124 on timeout, otherwise whois's own status.
run_whois() {
  command -v "$WHOIS_CMD" >/dev/null 2>&1 || return 127
  local out pid rc ticks=0
  out=$(mktemp) || return 70
  "$WHOIS_CMD" "$1" >"$out" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$ticks" -ge $((LIMIT * 10)) ]; then
      kill "$pid" 2>/dev/null
      wait "$pid" 2>/dev/null
      rm -f "$out"
      return 124
    fi
    sleep 0.1
    ticks=$((ticks + 1))
  done
  wait "$pid"
  rc=$?
  cat "$out"
  rm -f "$out"
  return "$rc"
}

# $1 domain, $2 why whois is being asked
from_whois() {
  local domain=$1 why=$2 out rc low taken free
  out=$(run_whois "$domain")
  rc=$?
  case $rc in
    127) say UNCLEAR "$domain" "$why; whois is not installed"; return ;;
    124) say UNCLEAR "$domain" "$why; whois timed out"; return ;;
    70)  exit 70 ;;
  esac
  low=$(printf '%s\n' "$out" | tr '[:upper:]' '[:lower:]')
  # Some whois programs (the one on macOS) first print the record of the ending itself, from
  # the root registry, then a "# server" line and the registry's answer about the domain. The
  # first part has created: and status: lines that are about the ending, so it is dropped.
  if printf '%s\n' "$low" | grep -q '^% iana whois server'; then
    low=$(printf '%s\n' "$low" | awk 'seen {print} /^# [a-z0-9.-]+$/ {seen=1}')
  fi
  # Lines that only a registered domain's record carries.
  taken=$(printf '%s\n' "$low" | grep -cE '^[[:space:]]*(registrar:|creation date:|created:|registry domain id:|registered on:|status:[[:space:]]*(connect|active|registered))')
  # Lines that say there is no record, leaving out ones about a name server or host: those
  # say something else was not found, not the domain.
  free=$(printf '%s\n' "$low" | grep -E '^[[:space:]%>]*(no match|not found|domain not found|no entries found|no object found|no data found|the queried object does not exist|status:[[:space:]]*(free|available))' | grep -cvE 'name ?server|nserver|host')
  if [ "$taken" -gt 0 ] && [ "$free" -gt 0 ]; then
    say UNCLEAR "$domain" "$why; whois gave both a record and a not-found line"
  elif [ "$taken" -gt 0 ]; then
    say TAKEN "$domain" "$why; whois: registered"
  elif [ "$rc" -ne 0 ]; then
    say UNCLEAR "$domain" "$why; whois failed with status $rc"
  elif [ "$free" -gt 0 ]; then
    say AVAILABLE "$domain" "$why; whois: no registration record"
  else
    say UNCLEAR "$domain" "$why; whois answer not recognised"
  fi
}

check_one() {
  local domain=$1 body meta code redirects final ctype
  body=$(mktemp) || exit 70
  meta=$(curl -sL --max-time "$LIMIT" --max-redirs 5 -o "$body" \
    -w '%{http_code} %{num_redirects} %{url_effective} %{content_type}' "$RDAP_BASE/$domain" 2>/dev/null)
  read -r code redirects final ctype <<<"$meta"
  case "${code:-000}" in
    200)
      # A registration record, not just any page that answers 200.
      if printf '%s' "${ctype:-}" | grep -qi 'rdap+json' && grep -qE '"objectClassName"[[:space:]]*:[[:space:]]*"domain"' "$body"; then
        say TAKEN "$domain" "registry: registered"
      else
        from_whois "$domain" "lookup answered without a registration record"
      fi ;;
    404)
      # Only a registry's own 404 means "no record". A 404 from the lookup service itself
      # means it has no registry for this ending, which says nothing about the domain.
      if [ "$(host_of "${final:-}")" != "$(host_of "$RDAP_BASE")" ]; then
        say AVAILABLE "$domain" "registry: no registration record"
      else
        from_whois "$domain" "no registry lookup for this ending"
      fi ;;
    429) from_whois "$domain" "lookup rate-limited" ;;
    000) from_whois "$domain" "lookup timed out or unreachable" ;;
    *)   from_whois "$domain" "lookup answered ${code}" ;;
  esac
  rm -f "$body"
}

if [ "${1:-}" = "--one" ]; then
  check_one "$2"
  exit 0
fi

tlds="com"
names=()
while [ $# -gt 0 ]; do
  case "$1" in
    --tlds)
      [ $# -ge 2 ] || { echo "--tlds needs a value, for example --tlds \"com ai\"" >&2; exit 1; }
      tlds=$2; shift 2 ;;
    -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --*) echo "unknown option $1" >&2; exit 1 ;;
    *) names+=("$1"); shift ;;
  esac
done
[ ${#names[@]} -gt 0 ] || { echo "usage: bash check.sh [--tlds \"com ai\"] name-or-domain [...]" >&2; exit 1; }

label='[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?'
domains=()
for raw in "${names[@]}"; do
  name=$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')
  case "$name" in
    *.*) candidates=("$name") ;;
    *)   candidates=(); for t in $tlds; do candidates+=("$name.$(printf '%s' "$t" | tr '[:upper:]' '[:lower:]' | sed 's/^\.//')"); done ;;
  esac
  for d in "${candidates[@]}"; do
    printf '%s' "$d" | grep -qE "^${label}(\.${label})+$" || { echo "not a domain name: $raw" >&2; exit 1; }
    case " ${domains[*]:-} " in *" $d "*) ;; *) domains+=("$d") ;; esac
  done
done

command -v curl >/dev/null 2>&1 || { echo "curl is not installed; it is needed for the lookups" >&2; exit 2; }

results=$(printf '%s\n' "${domains[@]}" | xargs -P 4 -n 1 bash "$0" --one 2>/dev/null)
status=0
for d in "${domains[@]}"; do
  if ! printf '%s\n' "$results" | grep -qF "  $d  ("; then
    results="${results}${results:+
}$(say UNCLEAR "$d" "the lookup died before answering")"
    status=3
  fi
done
printf '%s\n' "$results" | sort
exit $status
