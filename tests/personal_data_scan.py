"""Finds personal data before it reaches this public repository.

Three uses:

  python3 tests/personal_data_scan.py --commits origin/main..HEAD
      Reads every commit in the range BEFORE it is pushed: each file in its tree (contents
      and name), the commit message, and the author and committer. A branch pushed to a
      public repository is public at once, so this is the check that acts in time.
      Exit 0 clean, 1 findings, 2 nothing was scanned (an empty or mistyped range).

  .githooks/pre-push
      Runs the line above on every push, once `git config core.hooksPath .githooks` is set.

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
OWNER_HANDLE = "mar" + "baji"
OWNER_NAMES = ["mohan" + "nad", "arb" + "aji"]  # the handle contains the second, so it is covered too
# The only places where the owner's handle or name belongs: the install line, the copyright
# line and the plugin manifest.
OWNER_ALLOWED_FILES = ("README.md", "LICENSE")
OWNER_ALLOWED_FOLDER = ".claude-plugin/"
# A link to a private Claude Code session: harmless to click, but it does not belong in public history.
SESSION_LINK = "claude.ai/code/" + "session"
PRIVATE_WORDS = [SESSION_LINK, "chalk" + "talk", "obsid" + "ian", "10-" + "projects", "20-" + "areas", "30-" + "repos",
                 "90-" + "archive", "work-" + "principles"]
# A home folder followed by any user name, with or without anything after it.
HOME_PATH = re.compile(rb"/(users|home)/[^\s/\"'`<>)(,;]")
EMAIL = re.compile(rb"[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}")
ALLOWED_EMAIL_ENDINGS = (b"users.noreply.github.com", b"noreply@github.com", b"noreply@anthropic.com",
                         b"@example.com", b"@example.org")
# Who may appear as a commit's author or committer: (name, email ending).
APPROVED_IDENTITIES = [
    ("Mohan" + "nad " + "Arb" + "aji", OWNER_HANDLE + "@users.noreply.github.com"),
    ("Mohan" + "nad", OWNER_HANDLE + "@users.noreply.github.com"),
    ("GitHub", "noreply@github.com"),
]


def owner_allowed_in(path: str) -> bool:
    return path in OWNER_ALLOWED_FILES or path.startswith(OWNER_ALLOWED_FOLDER)


def scan_bytes(data: bytes, where: str, owner: str = "refuse") -> list[str]:
    """Findings for one blob of bytes: a file's contents, a file name, a commit message.

    owner: "refuse" (anywhere else), "allow" (the three places the name belongs), or
    "handle-only" (commit messages, which may name the repository but not the person).
    """
    low = data.lower()
    # Text saved as UTF-16 has a zero byte beside every plain character; with those removed
    # it reads like the plain form, so every rule below sees both.
    views = [low] if b"\x00" not in low else [low, low.replace(b"\x00", b"")]
    found = []
    for view in views:
        for word in PRIVATE_WORDS:
            if word.encode() in view:
                found.append(f"{where}: private word '{word}'")
        if owner != "allow":
            names_view = view.replace(OWNER_HANDLE.encode(), b"") if owner == "handle-only" else view
            for name in OWNER_NAMES:
                if name.encode() in names_view:
                    found.append(f"{where}: owner's name '{name}' where it does not belong")
        if HOME_PATH.search(view):
            found.append(f"{where}: home folder path")
        for m in EMAIL.finditer(view):
            if not m.group(0).endswith(ALLOWED_EMAIL_ENDINGS):
                found.append(f"{where}: email address '{m.group(0).decode(errors='replace')}'")
    return sorted(set(found))


def scan_file(path: str, data: bytes, label: str = "") -> list[str]:
    owner = "allow" if owner_allowed_in(path) else "refuse"
    where = f"{label}{path}"
    return scan_bytes(path.encode(), f"{where} (file name)", owner) + scan_bytes(data, where, owner)


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


def commits_in(repo: Path, rev_range: str) -> list[str]:
    return _git(repo, "rev-list", rev_range).decode().split()


def scan_commits(repo: Path, rev_range: str) -> list[str]:
    """Every commit in the range: its whole tree, its message, its author and committer."""
    found = []
    for sha in commits_in(repo, rev_range):
        label = f"commit {sha[:9]}: "
        an, ae, cn, ce = _git(repo, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce", sha).decode().rstrip("\n").split("\0")
        found += scan_identity(an, ae, f"{label}author") + scan_identity(cn, ce, f"{label}committer")
        found += scan_bytes(_git(repo, "show", "-s", "--format=%B", sha), f"{label}message", owner="handle-only")
        for path in [p for p in _git(repo, "ls-tree", "-r", "-z", "--name-only", sha).decode().split("\0") if p]:
            found += scan_file(path, _git(repo, "show", f"{sha}:{path}"), label)
    return sorted(set(found))


def main(argv: list[str], repo: Path) -> int:
    if len(argv) == 2 and argv[0] == "--commits":
        try:
            count = len(commits_in(repo, argv[1]))
        except subprocess.CalledProcessError:
            print(f"NOTHING SCANNED: git does not understand the range {argv[1]!r}")
            return 2
        if count == 0:
            print(f"NOTHING SCANNED: the range {argv[1]!r} holds no commits. Check the branch and that origin/main is fetched.")
            return 2
        problems = scan_commits(repo, argv[1])
        print(f"scanned {count} commit(s) in {argv[1]}")
    elif not argv:
        problems = scan_tree(repo)
        print(f"scanned {len(tracked_files(repo))} tracked file(s)")
    else:
        print("usage: python3 tests/personal_data_scan.py [--commits <range>]")
        return 2
    for line in problems:
        print("FOUND  " + line)
    print("CLEAN" if not problems else f"{len(problems)} finding(s); do not push")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], Path(__file__).resolve().parent.parent))
