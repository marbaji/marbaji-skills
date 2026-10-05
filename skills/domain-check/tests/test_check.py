"""Tests for scripts/check.sh. Offline: two local HTTP servers stand in for the lookup service
and for a registry, and a stub program stands in for whois, through the script's environment
variables. Every run has an outer time limit, so a lookup that never returns fails the test
instead of hanging the suite."""
import os
import stat
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check.sh"
OUTER_LIMIT = 30  # seconds; far above anything a passing run needs
RECORD = b'{"objectClassName": "domain", "ldhName": "x"}'


class Registry(BaseHTTPRequestHandler):
    def do_GET(self):
        name = self.path.rsplit("/", 1)[-1]
        if name.startswith("taken"):
            self._send(200, "application/rdap+json", RECORD)
        elif name.startswith("page"):
            self._send(200, "text/html", b"<html>" + RECORD + b"</html>")
        else:
            self._send(404, "application/rdap+json", b"{}")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Service(Registry):
    """Forwards .com to the registry; has no registry for other endings."""
    registry_port = None
    seen = []

    def do_GET(self):
        name = self.path.rsplit("/", 1)[-1]
        Service.seen.append(name)
        if "limited" in name:
            self._send(429, "text/plain", b"slow down")
        elif name.startswith("slow"):
            time.sleep(OUTER_LIMIT * 2)
        elif "selfloop" in name:
            # A redirect that stays on the service, then its own 404.
            if "hop" in self.path:
                self._send(404, "text/plain", b"")
            else:
                self.send_response(302)
                self.send_header("Location", f"/hop/{name}")
                self.send_header("Content-Length", "0")
                self.end_headers()
        elif name.endswith(".com"):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{Service.registry_port}/domain/{name}")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._send(404, "text/plain", b"")


@pytest.fixture(scope="module")
def servers():
    registry = ThreadingHTTPServer(("127.0.0.1", 0), Registry)
    service = ThreadingHTTPServer(("127.0.0.1", 0), Service)
    Service.registry_port = registry.server_address[1]
    for s in (registry, service):
        s.daemon_threads = True
        threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{service.server_address[1]}/domain"
    registry.shutdown()
    service.shutdown()


WHOIS_STUB = r"""#!/usr/bin/env bash
case "$1" in
  taken*)    echo "Domain Name: $1"; echo "Registrar: Example Registrar"; echo "Creation Date: 2001-01-01" ;;
  free*|slow*) echo "Domain not found." ;;
  quoted*)   echo "No match for domain \"$1\"." ;;
  preamble*) echo "% IANA WHOIS server"; echo "status:       ACTIVE"; echo "created:      1985-01-01"; echo; echo "# whois.registry.example"; echo; echo "Domain not found." ;;
  rootonly*) echo "% IANA WHOIS server"; echo "status:       ACTIVE"; echo "created:      1985-01-01" ;;
  both*)     echo "Not found: $1"; echo "Registrar: Example Registrar" ;;
  nshost*)   echo "Not found: name server ns1.$1" ;;
  failed*)   echo "Domain not found."; exit 2 ;;
  odd*)      echo "Query rate exceeded, try later." ;;
  stall*)    exec sleep 60 ;;
esac
"""


@pytest.fixture()
def run(servers, tmp_path):
    stub = tmp_path / "whois-stub"
    stub.write_text(WHOIS_STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    def _run(*args, script=SCRIPT, **env):
        Service.seen.clear()
        full = {**os.environ, "RDAP_BASE": servers, "WHOIS_CMD": str(stub), "DOMAIN_CHECK_TIMEOUT": "1", **env}
        r = subprocess.run(["bash", str(script), *args], capture_output=True, text=True, check=False,
                           env=full, timeout=OUTER_LIMIT)
        answers = {}
        for line in r.stdout.splitlines():
            status, domain, reason = line.split(None, 2)
            answers[domain] = (status, reason)
        return r, answers

    return _run


CASES = {
    # domain: (status, a phrase the reason must carry)
    "taken.com": ("TAKEN", "registry"),
    "free.com": ("AVAILABLE", "registry"),
    "page.com": ("UNCLEAR", "without a registration record"),       # a 200 that is not a record
    "taken.io": ("TAKEN", "whois: registered"),                      # the service's own 404 is not an answer
    "free.io": ("AVAILABLE", "whois: no registration record"),
    "quoted.io": ("AVAILABLE", "whois: no registration record"),
    "preamble.io": ("AVAILABLE", "whois: no registration record"),   # the ending's own record is ignored
    "rootonly.io": ("UNCLEAR", "not recognised"),
    "taken-selfloop.io": ("TAKEN", "no registry lookup"),            # a redirect inside the service proves nothing
    "taken-limited.com": ("TAKEN", "rate-limited"),
    "both.io": ("UNCLEAR", "both"),
    "nshost.io": ("UNCLEAR", "not recognised"),                      # "not found" about a name server
    "failed.io": ("UNCLEAR", "failed with status 2"),
    "odd.io": ("UNCLEAR", "not recognised"),
    "stall.io": ("UNCLEAR", "whois timed out"),
    "slow.com": ("AVAILABLE", "timed out or unreachable; whois: no registration record"),
}


@pytest.mark.parametrize("domain", CASES, ids=list(CASES))
def test_each_situation_gets_the_right_status(domain, run):
    r, answers = run(domain)
    assert r.returncode == 0, r.stderr
    status, phrase = CASES[domain]
    assert domain in answers, r.stdout
    assert answers[domain][0] == status, answers[domain]
    assert phrase in answers[domain][1], answers[domain]


def test_whois_missing_is_unclear_not_available(run, tmp_path):
    r, answers = run("free.io", WHOIS_CMD=str(tmp_path / "no-such-whois"))
    assert r.returncode == 0
    assert answers["free.io"][0] == "UNCLEAR" and "not installed" in answers["free.io"][1]


def test_bare_names_get_every_requested_ending_and_available_sorts_first(run):
    r, answers = run("--tlds", "com io", "taken", "free")
    assert set(answers) == {"taken.com", "taken.io", "free.com", "free.io"}
    statuses = [line.split()[0] for line in r.stdout.splitlines()]
    assert statuses == sorted(statuses) and statuses[0] == "AVAILABLE"


def test_default_ending_is_com_and_a_full_domain_is_used_as_given(run):
    _, answers = run("taken", "free.io")
    assert set(answers) == {"taken.com", "free.io"}


@pytest.mark.parametrize("bad", ["two words", "semi;colon", "-lead.com", "under_score.com", "a..b.com", "$(id).com"])
def test_invalid_input_is_refused_before_any_lookup(bad, run):
    r, answers = run("taken.com", bad)
    assert r.returncode == 1 and "not a domain name" in r.stderr
    assert answers == {} and Service.seen == [], "nothing may be looked up when any argument is invalid"


def test_no_arguments_and_unknown_option_are_refused(run):
    assert run()[0].returncode == 1
    assert run("--fast", "taken.com")[0].returncode == 1


def test_a_lookup_that_dies_is_reported_unclear_with_exit_3(run, tmp_path):
    # A stand-in xargs that starts no lookups at all: every worker's answer is missing.
    fake = tmp_path / "bin" / "xargs"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\ncat >/dev/null\nexit 1\n")
    fake.chmod(0o755)
    r, answers = run("taken.com", "free.com", PATH=f"{fake.parent}{os.pathsep}{os.environ['PATH']}")
    assert r.returncode == 3
    assert {a[0] for a in answers.values()} == {"UNCLEAR"} and set(answers) == {"taken.com", "free.com"}


def test_runs_from_a_path_with_a_space(run, tmp_path):
    spaced = tmp_path / "a folder" / "check.sh"
    spaced.parent.mkdir()
    spaced.write_bytes(SCRIPT.read_bytes())
    r, answers = run("taken.com", "free.com", script=spaced)
    assert r.returncode == 0, r.stderr
    assert (answers["taken.com"][0], answers["free.com"][0]) == ("TAKEN", "AVAILABLE")
