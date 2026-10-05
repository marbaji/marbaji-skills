"""Every skill folder is listed in the plugin manifest and every listed skill exists, so a
skill cannot sit in the repository without being installed (or be listed without existing)."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def manifest_problems(root: Path, manifest: dict) -> list[str]:
    problems = []
    on_disk = {f"./skills/{p.parent.name}" for p in (root / "skills").glob("*/SKILL.md")}
    listed = [s for plugin in manifest.get("plugins", []) for s in plugin.get("skills", [])]
    for s in sorted(set(listed)):
        if listed.count(s) > 1:
            problems.append(f"{s} is listed more than once")
        if not (root / s / "SKILL.md").is_file():
            problems.append(f"{s} is listed but has no SKILL.md")
    for s in sorted(on_disk - set(listed)):
        problems.append(f"{s} exists but is not listed, so it would not be installed")
    return problems


def make(tmp_path, folders, listed):
    for name in folders:
        (tmp_path / "skills" / name).mkdir(parents=True)
        (tmp_path / "skills" / name / "SKILL.md").write_text("x")
    return manifest_problems(tmp_path, {"plugins": [{"skills": listed}]})


def test_a_matching_manifest_has_no_problems(tmp_path):
    assert make(tmp_path, ["a", "b"], ["./skills/a", "./skills/b"]) == []


def test_a_skill_folder_missing_from_the_list_is_reported(tmp_path):
    assert make(tmp_path, ["a", "b"], ["./skills/a"]) == ["./skills/b exists but is not listed, so it would not be installed"]


def test_a_listed_skill_that_does_not_exist_is_reported(tmp_path):
    assert make(tmp_path, ["a"], ["./skills/a", "./skills/ghost"]) == ["./skills/ghost is listed but has no SKILL.md"]


def test_a_duplicate_entry_is_reported(tmp_path):
    assert make(tmp_path, ["a"], ["./skills/a", "./skills/a"]) == ["./skills/a is listed more than once"]


def test_a_listed_folder_without_a_skill_file_is_reported(tmp_path):
    (tmp_path / "skills" / "empty").mkdir(parents=True)
    assert make(tmp_path, ["a"], ["./skills/a", "./skills/empty"]) == ["./skills/empty is listed but has no SKILL.md"]


def test_the_real_manifest():
    manifest = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert len(list((REPO / "skills").glob("*/SKILL.md"))) >= 2, "premise: the skills are on disk"
    assert manifest_problems(REPO, manifest) == []
    assert "email" not in manifest["owner"], "the owner is shown by name only"
