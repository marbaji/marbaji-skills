"""The repository is public and installed by strangers: no home paths, private project words,
personal email addresses, or the owner's name outside the three places that need it."""
import subprocess
from pathlib import Path

import pytest

from tests import personal_data_scan as scan

REPO = Path(__file__).resolve().parents[1]
OWNER_ID = ("Mohan" + "nad " + "Arb" + "aji", "mar" + "baji@users.noreply.github.com")


def test_the_repository_is_clean():
    files = scan.tracked_files(REPO)
    assert len(files) >= 10 and sum(f.endswith("/SKILL.md") for f in files) >= 2, "premise: the scan saw the skills"
    assert scan.scan_tree(REPO) == []


def git(repo, *args, identity=OWNER_ID):
    name, email = identity
    subprocess.run(["git", "-C", str(repo), "-c", f"user.name={name}", "-c", f"user.email={email}", *args],
                   check=True, capture_output=True)


def commit(repo, files: dict, message="add a file", identity=OWNER_ID, remove=()):
    for path, data in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if isinstance(data, bytes) else data.encode())
    for path in remove:
        (repo / path).unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message, identity=identity)


@pytest.fixture()
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    commit(tmp_path, {"skills/a/SKILL.md": "a clean skill\n"}, "first")
    git(tmp_path, "branch", "base")
    return tmp_path


# Typed here on its own, one planted string per rule, NOT read from the scanner's lists: if a
# rule is deleted from the scanner, its case below goes red instead of disappearing.
PLANTED = {
    "home path, macOS": "/" + "Users/someone/notes.txt",
    "home path, Linux": "/" + "home/someone/notes.txt",
    "employer": "Chalk" + "Talk",
    "notes app": "my Obsid" + "ian notes",
    "workspace folder 10": "10-" + "projects/x",
    "workspace folder 20": "20-" + "areas/x",
    "workspace folder 30": "30-" + "repos/x",
    "workspace folder 90": "90-" + "archive/x",
    "principles file": "work-" + "principles.md",
    "notes folder": "Claude Code Obsid" + "ian",
    "owner handle": "github.com/mar" + "baji/x",
    "owner first name": "Mohan" + "nad",
    "owner surname": "Arb" + "aji",
    "personal email": "someone" + "@" + "gmail.com",
}


@pytest.mark.parametrize("rule", PLANTED, ids=list(PLANTED))
def test_each_rule_fires_on_a_planted_file(rule, repo):
    assert scan.scan_tree(repo) == [], "premise: the repository starts clean"
    commit(repo, {"skills/a/notes.md": f"see {PLANTED[rule]} for details\n"})
    assert scan.scan_tree(repo), f"nothing found for: {rule}"
    assert scan.scan_commits(repo, "base..HEAD"), f"the commit scan found nothing for: {rule}"


def test_a_text_file_named_like_an_image_is_still_read(repo):
    commit(repo, {"skills/a/notes.png": PLANTED["employer"]})
    assert scan.scan_tree(repo)


def test_utf16_text_is_still_read(repo):
    commit(repo, {"skills/a/notes.txt": PLANTED["employer"].encode("utf-16")})
    assert scan.scan_tree(repo)


def test_a_file_name_is_checked(repo):
    commit(repo, {"skills/a/" + PLANTED["employer"].lower() + "-setup.md": "clean contents\n"})
    assert scan.scan_tree(repo)


def test_a_file_added_then_deleted_is_found_by_the_commit_scan(repo):
    commit(repo, {"skills/a/oops.md": PLANTED["home path, macOS"]})
    commit(repo, {}, "remove it", remove=["skills/a/oops.md"])
    assert scan.scan_tree(repo) == [], "premise: the final tree is clean"
    assert scan.scan_commits(repo, "base..HEAD")


def test_a_commit_message_is_checked(repo):
    commit(repo, {"skills/a/more.md": "clean\n"}, message="copied from " + PLANTED["workspace folder 10"])
    assert scan.scan_tree(repo) == []
    assert any("message" in f for f in scan.scan_commits(repo, "base..HEAD"))


def test_a_personal_author_email_is_refused_and_the_approved_identity_passes(repo):
    commit(repo, {"skills/a/more.md": "clean\n"})
    assert scan.scan_commits(repo, "base..HEAD") == [], "the approved identity with a clean commit must pass"
    commit(repo, {"skills/a/again.md": "clean\n"}, identity=(OWNER_ID[0], "someone" + "@" + "gmail.com"))
    found = scan.scan_commits(repo, "base..HEAD")
    assert any("not an approved commit identity" in f for f in found)


def test_the_owner_name_passes_only_where_it_belongs(repo):
    line = "install from github.com/mar" + "baji/x\n"
    commit(repo, {"README.md": line, "LICENSE": line, ".claude-plugin/marketplace.json": line})
    assert scan.scan_tree(repo) == []
    commit(repo, {"skills/a/SKILL.md": line})
    assert scan.scan_tree(repo)


def test_allowed_email_shapes_pass(repo):
    commit(repo, {"skills/a/x.md": "Co-Authored-By: A <noreply@anthropic.com>\nwrite to you@example.com\n"})
    assert scan.scan_tree(repo) == []
