"""The repository is public and installed by strangers: no home paths, private project words,
personal email addresses, or the owner's name outside the three places that need it."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import personal_data_scan as scan

REPO = Path(__file__).resolve().parents[1]
OWNER_ID = ("Mohan" + "nad " + "Arb" + "aji", "mar" + "baji@users.noreply.github.com")
STRANGER = ("Someone Else", "someone" + "@" + "gmail.com")
# Planted commits must not depend on this machine's git settings (signing, hooks).
QUIET = ["-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]


def test_the_repository_is_clean():
    files = scan.tracked_files(REPO)
    assert len(files) >= 10 and sum(f.endswith("/SKILL.md") for f in files) >= 2, "premise: the scan saw the skills"
    assert scan.scan_tree(REPO) == []


def git(repo, *args, author=OWNER_ID, committer=OWNER_ID):
    env = {**os.environ, "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
           "GIT_COMMITTER_NAME": committer[0], "GIT_COMMITTER_EMAIL": committer[1]}
    subprocess.run(["git", "-C", str(repo), *QUIET, *args], check=True, capture_output=True, env=env)


def commit(repo, files: dict, message="add a file", remove=(), **who):
    for path, data in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if isinstance(data, bytes) else data.encode())
    for path in remove:
        (repo / path).unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message, **who)


@pytest.fixture()
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "symbolic-ref", "HEAD", "refs/heads/main")
    commit(tmp_path, {"skills/a/SKILL.md": "a clean skill\n"}, "first")
    git(tmp_path, "branch", "base")
    return tmp_path


# Typed here on its own, one planted string per rule, NOT read from the scanner's lists: if a
# rule is deleted from the scanner, its case below goes red instead of disappearing. Each case
# names the words its finding must carry, so one rule cannot pass on another rule's finding.
PLANTED = {
    "home path, macOS": ("/" + "Users/someone/notes.txt", "home folder path"),
    "home path, Linux": ("/" + "home/someone/notes.txt", "home folder path"),
    "home path with nothing after the name": ("HOME=/" + "Users/someone", "home folder path"),
    "home path, name with a space": ("/" + "home/some one/notes", "home folder path"),
    "employer": ("Chalk" + "Talk", "private word 'chalk"),
    "notes app": ("my Obsid" + "ian notes", "private word 'obsid"),
    "workspace folder 10": ("10-" + "projects/x", "private word '10-"),
    "workspace folder 20": ("20-" + "areas/x", "private word '20-"),
    "workspace folder 30": ("30-" + "repos/x", "private word '30-"),
    "workspace folder 90": ("90-" + "archive/x", "private word '90-"),
    "principles file": ("work-" + "principles.md", "private word 'work-"),
    "owner first name": ("Mohan" + "nad", "owner's name 'mohan"),
    "owner surname": ("Arb" + "aji", "owner's name 'arb"),
    "owner handle": ("github.com/mar" + "baji/x", "owner's name 'arb"),
    "personal email": ("someone" + "@" + "gmail.com", "email address 'someone"),
    "session link": ("https://claude.ai/code/" + "session_01ABC", "private word 'claude.ai/code/"),
    "one-letter email": ("a" + "@" + "t.co", "email address 'a"),
}


@pytest.mark.parametrize("rule", PLANTED, ids=list(PLANTED))
def test_each_rule_fires_on_a_planted_file(rule, repo):
    text, expected = PLANTED[rule]
    assert scan.scan_tree(repo) == [], "premise: the repository starts clean"
    commit(repo, {"skills/a/notes.md": f"see {text} for details\n"})
    assert any(expected in f for f in scan.scan_tree(repo)), f"no '{expected}' finding for: {rule}"
    assert any(expected in f for f in scan.scan_commits(repo, "base..HEAD")), f"the commit scan missed: {rule}"


def test_a_text_file_named_like_an_image_is_still_read(repo):
    commit(repo, {"skills/a/notes.png": PLANTED["employer"][0]})
    assert scan.scan_tree(repo)


@pytest.mark.parametrize("rule", ["employer", "home path, macOS", "personal email", "owner surname"])
@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_utf16_text_is_read_by_every_kind_of_rule(rule, encoding, repo):
    text, expected = PLANTED[rule]
    commit(repo, {"skills/a/notes.txt": f"see {text} here".encode(encoding)})
    assert any(expected in f for f in scan.scan_tree(repo))


def test_a_file_name_is_checked(repo):
    commit(repo, {"skills/a/" + PLANTED["employer"][0].lower() + "-setup.md": "clean contents\n"})
    assert any("(file name)" in f for f in scan.scan_tree(repo))


def test_a_file_added_then_deleted_is_found_by_the_commit_scan(repo):
    commit(repo, {"skills/a/oops.md": PLANTED["home path, macOS"][0]})
    commit(repo, {}, "remove it", remove=["skills/a/oops.md"])
    assert scan.scan_tree(repo) == [], "premise: the final tree is clean"
    assert scan.scan_commits(repo, "base..HEAD")


def test_a_commit_message_is_checked(repo):
    commit(repo, {"skills/a/more.md": "clean\n"}, message="copied from " + PLANTED["workspace folder 10"][0])
    assert scan.scan_tree(repo) == []
    assert any("message" in f for f in scan.scan_commits(repo, "base..HEAD"))


def test_a_commit_message_may_name_the_repository_but_not_the_person(repo):
    commit(repo, {"skills/a/more.md": "clean\n"}, message="see github.com/mar" + "baji/mar" + "baji-skills")
    assert scan.scan_commits(repo, "base..HEAD") == []
    commit(repo, {"skills/a/again.md": "clean\n"}, message="thanks, " + PLANTED["owner first name"][0])
    assert any("message: owner's name" in f for f in scan.scan_commits(repo, "base..HEAD"))


def test_the_approved_identity_passes(repo):
    commit(repo, {"skills/a/more.md": "clean\n"})
    commit(repo, {"skills/a/merge.md": "clean\n"}, committer=("GitHub", "noreply@github.com"))
    assert scan.scan_commits(repo, "base..HEAD") == []


@pytest.mark.parametrize("field", ["author", "committer"])
def test_an_unapproved_author_or_committer_is_reported_by_field(field, repo):
    commit(repo, {"skills/a/more.md": "clean\n"}, **{field: STRANGER})
    found = scan.scan_commits(repo, "base..HEAD")
    assert len(found) == 1 and f"{field}: " in found[0] and "not an approved commit identity" in found[0]


def test_the_approved_email_under_another_name_is_refused(repo):
    commit(repo, {"skills/a/more.md": "clean\n"}, author=("Someone Else", OWNER_ID[1]), committer=OWNER_ID)
    assert any("author" in f for f in scan.scan_commits(repo, "base..HEAD"))


def test_the_owner_name_passes_only_where_it_belongs(repo):
    line = "install from github.com/mar" + "baji/x, by " + OWNER_ID[0] + "\n"
    commit(repo, {"README.md": line, "LICENSE": line, ".claude-plugin/marketplace.json": line})
    assert scan.scan_tree(repo) == []


@pytest.mark.parametrize("path", ["skills/a/SKILL.md", "README.md.backup", "LICENSE-notes.txt", "docs/README.md",
                                  ".claude-plugin-old/x.json"])
def test_the_owner_name_is_refused_in_a_file_that_only_looks_like_an_allowed_one(path, repo):
    commit(repo, {path: "by " + OWNER_ID[0] + "\n"})
    assert any("owner's name" in f for f in scan.scan_tree(repo))


def test_allowed_email_shapes_pass(repo):
    commit(repo, {"skills/a/x.md": "Co-Authored-By: A <noreply@anthropic.com>\nwrite to you@example.com\n"})
    assert scan.scan_tree(repo) == []


def cli(repo, *args):
    return subprocess.run([sys.executable, str(REPO / "tests" / "personal_data_scan.py"), *args],
                          capture_output=True, text=True, check=False, cwd=repo)


@pytest.mark.parametrize("bad_range", ["HEAD..HEAD", "HEAD^{tree}", "no-such-branch..HEAD"])
def test_the_command_line_refuses_to_call_an_empty_or_wrong_range_clean(bad_range, repo):
    assert scan.main(["--commits", bad_range], repo) == 2


def test_the_command_line_reports_findings_and_clean_by_exit_status(repo, capsys):
    commit(repo, {"skills/a/more.md": "clean\n"})
    assert scan.main(["--commits", "base..HEAD"], repo) == 0 and "CLEAN" in capsys.readouterr().out
    commit(repo, {"skills/a/oops.md": PLANTED["personal email"][0]})
    assert scan.main(["--commits", "base..HEAD"], repo) == 1 and "do not push" in capsys.readouterr().out


def push_hook(repo, sha):
    hook = REPO / ".githooks" / "pre-push"
    return subprocess.run(["sh", str(hook)], input=f"refs/heads/x {sha} refs/heads/x {'0' * 40}\n",
                          capture_output=True, text=True, check=False, cwd=repo)


def head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def test_the_pre_push_hook_blocks_a_push_with_findings_and_lets_a_clean_one_through(repo):
    (repo / "tests").mkdir()
    (repo / "tests" / "personal_data_scan.py").write_bytes((REPO / "tests" / "personal_data_scan.py").read_bytes())
    commit(repo, {}, "add the scanner")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    commit(repo, {"skills/a/more.md": "clean\n"})
    assert push_hook(repo, head(repo)).returncode == 0
    commit(repo, {"skills/a/oops.md": PLANTED["home path, macOS"][0]})
    blocked = push_hook(repo, head(repo))
    assert blocked.returncode == 1 and "nothing was pushed" in blocked.stderr


def test_the_pre_push_hook_refuses_when_it_cannot_tell_what_is_outgoing(repo):
    commit(repo, {"skills/a/oops.md": PLANTED["home path, macOS"][0]})
    refused = push_hook(repo, head(repo))   # no origin/main in this repository
    assert refused.returncode == 1 and "origin/main is not fetched" in refused.stderr
