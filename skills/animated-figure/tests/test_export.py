"""Tests for scripts/export.mjs, the GIF exporter of the animated-figure skill.

They run the real exporter (Node, Playwright's Chromium, ffmpeg), so those must be installed;
the first test says which is missing. Nothing is skipped: a skipped export test proves nothing.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
EXPORT = SKILL / "scripts" / "export.mjs"
EXAMPLES = sorted((SKILL / "examples").glob("*.html"))
TEMPLATE = SKILL / "template.html"
NODE = shutil.which("node") or "node"
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
GIF_LIMIT_BYTES = 15 * 1024 * 1024  # the upload limit the skill promises to stay under


def export(*args, env=None):
    return subprocess.run([NODE, str(EXPORT), *map(str, args)], capture_output=True, text=True,
                          check=False, env={**os.environ, **(env or {})})


def figure(css, body='<circle class="a" cx="100" cy="100" r="20"/>', words="Point"):
    """A minimal figure page. `css` carries the animation under test."""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0}}svg{{display:block;width:100%}}</style></head>
<body><figure id="figure"><svg viewBox="0 0 960 400" xmlns="http://www.w3.org/2000/svg"><style>{css}</style>
<rect width="960" height="400" fill="#fff"/>{body}<text x="480" y="350" font-size="30" text-anchor="middle">{words}</text></svg></figure></body></html>"""


# A figure the exporter must accept: one part crosses, then everything holds for two seconds.
GOOD = ".a{animation:a 4s linear infinite}@keyframes a{0%{transform:translateX(0)}50%,100%{transform:translateX(300px)}}"


def write(tmp_path, html, name="fig.html"):
    p = tmp_path / name
    p.write_text(html, encoding="utf8")
    return p


def frame_hashes(gif):
    """One hash per decoded frame, computed by ffmpeg, not by the exporter."""
    r = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(gif), "-f", "framemd5", "-"],
                       capture_output=True, text=True, check=True)
    return [line.split(",")[-1].strip() for line in r.stdout.splitlines() if line and not line.startswith("#")]


def gif_size(gif):
    data = gif.read_bytes()
    assert data[:6] in (b"GIF87a", b"GIF89a")
    return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")


def outputs(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir() if p.suffix in (".gif", ".png"))


def test_prerequisites_are_installed():
    r = export("--check")
    assert r.returncode == 0, f"the exporter's own check reports something missing:\n{r.stderr}"


def test_examples_exist():
    assert len(EXAMPLES) >= 2, "the skill ships at least two example figures"


@pytest.mark.parametrize("src", EXAMPLES, ids=lambda p: p.stem)
def test_example_exports_a_moving_looping_gif_with_no_warnings(src, tmp_path):
    out = tmp_path / "out.gif"
    r = export(src, "--out", out)
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)

    hashes = frame_hashes(out)
    assert len(hashes) == report["frames"] == round(report["loopMs"] / 1000 * report["fps"])
    assert len(set(hashes)) > len(hashes) // 4, "most of the loop should differ frame to frame somewhere"
    assert gif_size(out) == (report["width"], report["height"])
    assert report["width"] == 1200, "the documented default width"
    assert out.stat().st_size == report["bytes"] < GIF_LIMIT_BYTES
    assert b"NETSCAPE2.0\x03\x01\x00\x00" in out.read_bytes(), "the GIF must loop forever"
    assert Path(report["frameSheet"]).is_file()
    assert report["warnings"] == [], "a shipped example must follow the skill's own rules"

    committed = src.with_suffix(".gif")
    assert committed.is_file() and committed.stat().st_size < GIF_LIMIT_BYTES
    assert len(frame_hashes(committed)) == report["frames"], "the committed GIF is stale: export the example again"
    assert gif_size(committed) == gif_size(out), "the committed GIF is stale: export the example again"


def test_the_starter_template_exports_with_no_warnings(tmp_path):
    r = export(TEMPLATE, "--out", tmp_path / "out.gif")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["warnings"] == []


def test_width_option_sets_the_gif_width(tmp_path):
    src = write(tmp_path, figure(GOOD))
    r = export(src, "--width", 600)
    assert r.returncode == 0, r.stderr
    assert gif_size(tmp_path / "fig.gif")[0] == 600


def test_the_accepted_figure_really_moves_then_holds(tmp_path):
    """Premise for every refusal test below: without the defect, this figure exports."""
    src = write(tmp_path, figure(GOOD))
    r = export(src)
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    hashes = frame_hashes(tmp_path / "fig.gif")
    assert len(set(hashes[: len(hashes) // 2])) > 1, "first half: the part is crossing"
    assert len(set(hashes[len(hashes) // 2 + 1:])) == 1, "second half: it holds"
    assert report["longestHoldMs"] >= 1500
    assert report["warnings"] == []


REFUSED = {
    "no animation at all": ("", "No CSS animation"),
    "animation runs once": (GOOD.replace("infinite", "1"), "repeat forever"),
    "animation-delay": (GOOD.replace("linear infinite", "linear 1s infinite"), "animation-delay"),
    "animation-direction": (GOOD.replace("linear infinite", "linear infinite alternate"), "animation-direction"),
    "a loop over thirty seconds": (GOOD.replace("4s", "31s"), "the limit is 30s"),
    "durations that do not fit one loop": (
        GOOD + ".b{animation:b 3s linear infinite}@keyframes b{50%{opacity:.2}}", "whole number of times"),
}


@pytest.mark.parametrize("case", REFUSED, ids=list(REFUSED))
def test_a_figure_that_cannot_loop_is_refused_and_nothing_is_written(case, tmp_path):
    css, phrase = REFUSED[case]
    body = '<circle class="a" cx="100" cy="100" r="20"/><circle class="b" cx="100" cy="200" r="20"/>'
    src = write(tmp_path, figure(css, body))
    r = export(src)
    assert r.returncode == 1, r.stderr
    assert phrase in r.stderr
    assert r.stdout.strip() == ""
    assert outputs(tmp_path) == []


def test_a_refusal_leaves_no_picture_from_an_earlier_run(tmp_path):
    src = write(tmp_path, figure(GOOD))
    assert export(src).returncode == 0
    assert outputs(tmp_path) == ["fig-frames.png", "fig.gif"], "premise: the first run left both files"
    write(tmp_path, figure(""))
    assert export(src).returncode == 1
    assert outputs(tmp_path) == []


def test_a_selector_that_matches_nothing_is_refused(tmp_path):
    r = export(write(tmp_path, figure(GOOD)), "--selector", "#absent")
    assert r.returncode == 1 and "nothing matches the selector #absent" in r.stderr
    assert outputs(tmp_path) == []


def test_a_shorter_animation_that_fits_the_loop_is_accepted(tmp_path):
    css = GOOD + ".b{animation:b 2s linear infinite}@keyframes b{50%{opacity:.2}}"
    body = '<circle class="a" cx="100" cy="100" r="20"/><circle class="b" cx="100" cy="200" r="20"/>'
    r = export(write(tmp_path, figure(css, body)))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["loopMs"] == 4000


def test_missing_ffmpeg_is_named_with_its_fix_and_nothing_is_written(tmp_path):
    src = write(tmp_path, figure(GOOD))
    r = export(src, env={"FFMPEG": str(tmp_path / "no-such-ffmpeg")})
    assert r.returncode == 2
    assert re.search(r"MISSING\s+ffmpeg", r.stderr) and "install" in r.stderr
    assert "Nothing was exported" in r.stderr
    assert outputs(tmp_path) == []
    check = export("--check", env={"FFMPEG": str(tmp_path / "no-such-ffmpeg")})
    assert check.returncode == 2 and re.search(r"MISSING\s+ffmpeg", check.stderr)


def test_a_gif_over_the_size_limit_is_refused_and_nothing_is_written(tmp_path):
    src = write(tmp_path, figure(GOOD))
    r = export(src, "--max-mb", "0.001")
    assert r.returncode == 1
    assert "over the 0.001 MB limit" in r.stderr
    assert outputs(tmp_path) == []


def test_missing_input_and_unknown_option_are_refused(tmp_path):
    assert export(tmp_path / "absent.html").returncode == 1
    r = export(write(tmp_path, figure(GOOD)), "--speed", "2")
    assert r.returncode == 1 and "unknown option --speed" in r.stderr
    assert outputs(tmp_path) == []


def warning_ids(tmp_path, html, *args):
    r = export(write(tmp_path, html), *args)
    assert r.returncode == 0, r.stderr
    return {w["id"] for w in json.loads(r.stdout)["warnings"]}


def test_warns_about_too_many_words_and_small_text(tmp_path):
    crowded = figure(GOOD, words=" ".join(["word"] * 25)).replace('font-size="30"', 'font-size="9"')
    assert warning_ids(tmp_path, crowded) == {"too-many-words", "small-text"}


def test_warns_when_many_parts_move_at_once_but_not_when_they_take_turns(tmp_path):
    dots = "".join(f'<circle class="m m{i}" cx="100" cy="{60 + 50 * i}" r="15"/>' for i in range(5))
    together = ".m{animation:a 5s linear infinite}@keyframes a{0%{transform:translateX(0)}40%,100%{transform:translateX(300px)}}"
    assert warning_ids(tmp_path, figure(together, dots)) == {"busy"}

    turns = "".join(
        f".m{i}{{animation:t{i} 5s linear infinite}}@keyframes t{i}{{0%,{i * 12}%{{transform:translateX(0)}}{i * 12 + 12}%,100%{{transform:translateX(300px)}}}}"
        for i in range(5))
    assert warning_ids(tmp_path, figure(turns, dots)) == set()


def test_warns_when_nothing_ever_holds_still(tmp_path):
    restless = ".a{animation:a 4s linear infinite}@keyframes a{50%{transform:translateX(300px)}}"
    assert warning_ids(tmp_path, figure(restless)) == {"no-hold"}


def test_warns_about_a_long_loop(tmp_path):
    assert warning_ids(tmp_path, figure(GOOD.replace("4s", "13s")), "--fps", "4") == {"long-loop"}


RECIPES = re.findall(r"```css\n(.*?)```", (SKILL / "recipes.md").read_text(encoding="utf8"), re.S)
RECIPE_KEYFRAMES = [(name, block) for block in RECIPES for name in re.findall(r"@keyframes ([\w-]+)", block)]


def test_recipes_were_found():
    assert len(RECIPE_KEYFRAMES) >= 8, "premise: the recipe blocks in recipes.md were parsed"


@pytest.mark.parametrize("name,block", RECIPE_KEYFRAMES, ids=[n for n, _ in RECIPE_KEYFRAMES])
def test_each_recipe_exports_and_rests_somewhere(name, block, tmp_path):
    """A recipe that leaves a property out of some keyframes drifts for the whole loop, so
    nothing ever rests; every recipe as printed must show a still stretch of a second or more."""
    css = block + f".r{{animation:{name} 6s ease-in-out infinite}}"
    body = '<path class="r" pathLength="1" d="M100 100 H300 V140 H100 Z" fill="#888" stroke="#000" stroke-width="4"/>'
    r = export(write(tmp_path, figure(css, body)))
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["warnings"] == [], "a recipe as printed must be clean under the exporter's own checks"
    assert len(set(frame_hashes(tmp_path / "fig.gif"))) > 1, "premise: the recipe moved the part"


def test_warns_when_keyframes_of_one_animation_name_different_properties(tmp_path):
    drifting = ".a{animation:a 4s linear infinite}@keyframes a{0%{transform:translateX(0)}50%,90%{transform:translateX(300px)}100%{transform:translateX(300px);opacity:0}}"
    # The drift is real, so the same figure also never rests; both warnings are its symptoms.
    assert warning_ids(tmp_path, figure(drifting)) == {"uneven-keyframes", "no-hold"}


def test_dark_option_changes_the_picture(tmp_path):
    css = GOOD + "@media (prefers-color-scheme:dark){rect{fill:#111}}"
    src = write(tmp_path, figure(css))
    assert export(src, "--out", tmp_path / "light.gif").returncode == 0
    assert export(src, "--out", tmp_path / "dark.gif", "--dark").returncode == 0
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(tmp_path / "light.gif") != digest(tmp_path / "dark.gif")
