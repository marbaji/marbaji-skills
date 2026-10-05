"""Finds personal data before it reaches this public repository.

Two uses:

  python3 tests/personal_data_scan.py --commits origin/main..HEAD
      Run by hand BEFORE pushing. Reads every commit in the range: each file in its tree
      (contents and path), the commit message, and the author and committer. A branch pushed
      to a public repository is public at once, so this is the check that acts in time.

  tests/test_no_personal_data.py
      Runs the same rules over the checked-out files in CI, as a regression check.

It finds known shapes of personal data, not all personal data. It does not replace reading
the diff.
"""
import re
import subprocess
import sys
from pathlib import Path

# Split so this file does not match itself.
OWNER_TOKENS = ["mar" + "baji", "mohan" + "nad", "arb" + "aji"]
# The only files where the owner's handle or name belongs: the install line, the copyright
# line and the plugin manifest.
OWNER_ALLOWED_PATHS = ("README.md", "LICENSE", ".claude-plugin/")
PRIVATE_WORDS = ["chalk" + "talk", "obsid" + "ian", "10-" + "projects", "20-" + "areas", "30-" + "repos",
                 "90-" + "archive", "work-" + "principles", "claude code obsid" + "ian"]
HOME_PATH = re.compile(rb"/(users|home)/[a-z0-9._-]+/")
EMAIL = re.compile(rb"[a-z0-9._%+-]{2,}@[a-z0-9-]{2,}(\.[a-z0-9-]+)*\.[a-z]{2,}")
ALLOWED_EMAIL_ENDINGS = (b"users.noreply.github.com", b"@noreply.github.com", b"noreply@github.com",
                         b"@noreply.anthropic.com", b"noreply@anthropic.com", b"@example.com", b"@example.org")
# Who may appear as a commit's author or committer: (name, email ending).
APPROVED_IDENTITIES = [
    ("Mohan" + "nad " + "Arb" + "aji", "mar" + "baji@users.noreply.github.com"),
    ("Mohan" + "nad", "mar" + "baji@users.noreply.github.com"),
    ("GitHub", "noreply@github.com"),
]


def _forms(word: str) -> list[bytes]:
    """The byte shapes a word can take in a file: plain, and UTF-16 in either byte order."""
    return [word.encode(), word.encode("utf-16-le"), word.encode("utf-16-be")]


def scan_bytes(data: bytes, where: str, owner_allowed: bool) -> list[str]:
    """Findings for one blob of bytes (a file's contents, a path, a commit message)."""
    low = data.lower()
    found = []
    for word in PRIVATE_WORDS:
        if any(form in low for form in _forms(word)):
            found.append(f"{where}: private word '{word}'")
    if not owner_allowed:
        for token in OWNER_TOKENS:
            if any(form in low for form in _forms(token)):
                found.append(f"{where}: owner's name or handle '{token}' outside {OWNER_ALLOWED_PATHS}")
    m = HOME_PATH.search(low)
    if m:
        found.append(f"{where}: home folder path '{m.group(0).decode()}'")
    for m in EMAIL.finditer(low):
        if not m.group(0).endswith(ALLOWED_EMAIL_ENDINGS):
            found.append(f"{where}: email address '{m.group(0).decode(errors='replace')}'")
    return found


def scan_file(path: str, data: bytes, label: str = "") -> list[str]:
    owner_allowed = path.startswith(OWNER_ALLOWED_PATHS)
    where = f"{label}{path}"
    return scan_bytes(path.encode(), f"{where} (file name)", owner_allowed) + scan_bytes(data, where, owner_allowed)


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def tracked_files(repo: Path) -> list[str]:
    return [p for p in _git(repo, "ls-files", "-z").decode().split("\0") if p]


def scan_tree(repo: Path) -> list[str]:
    """Every tracked file of the working tree, read as raw bytes whatever its extension."""
    found = []
    for path in tracked_files(repo):
        found += scan_file(path, (repo / path).read_bytes())
    return found


def scan_identity(name: str, email: str, where: str) -> list[str]:
    for ok_name, ok_ending in APPROVED_IDENTITIES:
        if name == ok_name and email.lower().endswith(ok_ending):
            return []
    return [f"{where}: '{name} <{email}>' is not an approved commit identity"]


def scan_commits(repo: Path, rev_range: str) -> list[str]:
    """Every commit in the range: its whole tree, its message, its author and committer."""
    found = []
    shas = _git(repo, "rev-list", rev_range).decode().split()
    for sha in shas:
        label = f"commit {sha[:9]}: "
        an, ae, cn, ce = _git(repo, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", sha).decode().rstrip("\n").split("\0")
        found += scan_identity(an, ae, f"{label}author") + scan_identity(cn, ce, f"{label}committer")
        # A message may name the repository; the owner's handle is allowed there.
        found += scan_bytes(_git(repo, "show", "-s", "--format=%B", sha), f"{label}message", owner_allowed=True)
        for path in [p for p in _git(repo, "ls-tree", "-r", "-z", "--name-only", sha).decode().split("\0") if p]:
            found += scan_file(path, _git(repo, "show", f"{sha}:{path}"), label)
    return sorted(set(found))


if __name__ == "__main__":
    here = Path(__file__).resolve().parent.parent
    if len(sys.argv) == 3 and sys.argv[1] == "--commits":
        commits = _git(here, "rev-list", sys.argv[2]).decode().split()
        problems = scan_commits(here, sys.argv[2])
        print(f"scanned {len(commits)} commit(s) in {sys.argv[2]}")
    elif len(sys.argv) == 1:
        problems = scan_tree(here)
        print(f"scanned {len(tracked_files(here))} tracked file(s)")
    else:
        sys.exit("usage: python3 tests/personal_data_scan.py [--commits <range>]")
    for line in problems:
        print("FOUND  " + line)
    print("CLEAN" if not problems else f"{len(problems)} finding(s); do not push")
    sys.exit(1 if problems else 0)
