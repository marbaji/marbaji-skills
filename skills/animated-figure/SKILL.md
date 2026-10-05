---
name: animated-figure
description: Use when someone wants a small animated explainer figure, an animated diagram, or a looping GIF that explains one concept (a process, a comparison, a before and after) for a blog post, Medium, LinkedIn, X, a README or a slide. Also use when an existing explainer animation feels busy, wordy or hard to follow.
---

# Animated figure

One drawn diagram, one thing moving at a time, a handful of words, a loop that ends on the point. The figure is a single inline SVG animated with CSS keyframes (no JavaScript), saved as an HTML file, and exported to a GIF with the script in this folder. The reader gets two files: the GIF to drop into a post, and the HTML source to edit or embed.

`<skill-dir>` below means the folder this file is in.

## What a good figure is

A figure is watched for a few seconds, usually on a phone, usually without reading the text around it. So:

- **One idea.** The figure makes one claim you can say in one sentence. A second idea is a second figure.
- **One picture.** One scene, drawn once. Not a scene plus a chart plus a legend.
- **One thing moving at a time.** Each beat finishes before the next begins. The eye should never have to choose. A cause arriving as its effect starts (a signal fading out while the lamp it reached lights up) is one event and is fine.
- **Few words, large.** Name the nouns (a label of one or two words under a thing) and state the point. Aim for under 15 words in the whole figure and never past 20; labels at 22px or more in a 960-wide drawing. No title, no caption sentence, no numbered steps, no legend inside the image: those belong in the post around it.
- **It reads from start to finish.** The loop opens on the bare scene (only the parts that never move, for the first twentieth of the loop or so), plays three to five beats in order, and the last beat is a short line that states the point.
- **It holds.** The finished picture, point included, stays still for about two seconds before a quick fade back to the start. Six to ten seconds for the whole loop.

## Workflow

1. **Say the idea in one sentence.** If it needs "and", choose the half that matters. That sentence, shortened, becomes the last frame.
2. **List the beats in words**, three to five, each one thing happening: "the question travels to the library", "the answer travels back and stays", "the question comes again", "the answer hops out of the notes", then the point. If a beat needs two things to move, split it.
3. **Check the tools once:** `node <skill-dir>/scripts/export.mjs --check`. It names what is missing and prints the line that installs it; run it again after installing, until it says Ready. Do this before drawing so a missing tool is not discovered at the end.
4. **Copy `<skill-dir>/template.html`** to the user's project as `<name>.html`. Read one file in `<skill-dir>/examples/` to see a finished figure: `answer-kept-nearby.html` (a thing travelling between places) or `halving-search.html` (a marker stepping through states).
5. **Draw the finished still picture first**, with no animation: the scene, the labels, the point line. Simple filled shapes; a person is a circle on a rounded rectangle. Use the template's colour variables so it works in light and dark. Working out coordinates with a small script is fine when a shape repeats many times; what you keep and hand over is still the one HTML file.
6. **Animate the beats**, following [recipes.md](recipes.md). Every animation shares one duration and runs forever; all waiting is written into keyframe percentages. Then rewrite the template's reduced-motion rule for your parts, so that with animation off each part sits where the loop ends.
7. **Export:** `node <skill-dir>/scripts/export.mjs <name>.html`. It writes `<name>.gif` and `<name>-frames.png` and prints a report with warnings. The sheet shows six moments of the loop from top to bottom, taken at about 8%, 25%, 42%, 58%, 75% and 92% of the way through.
8. **Look at `<name>-frames.png`** with your own eyes, and read the warnings. The warnings count words and motion; they cannot see a label sitting on top of a shape or text running off the edge, so the sheet is the only check for those. Check each line under "What a good figure is" against what you see: is anything overlapping or clipped (follow each moving part along its whole path, past every label), is the point on screen in the last panel, is any panel confusing on its own? Fix the HTML and export again until the sheet is clean and the warnings are gone or you can say why one does not apply.
9. **Hand over** the GIF path, the HTML path, and the report's size and dimensions. Mention that the SVG inside the HTML can be pasted into a web page and will animate there (two figures in one page need different class and keyframe names; see the traps in recipes.md).

## The exporter

`node <skill-dir>/scripts/export.mjs --help` lists the options. The defaults suit most posts: 1200 pixels wide, 10 frames a second. A typical figure comes out between 100 KB and 1 MB, far under the 15 MB that the exporter refuses to exceed (common upload limits for GIFs sit at or above that).

It refuses, and writes nothing, when the figure has no CSS animation; when an animation does not repeat forever, uses `animation-delay`, plays in a direction other than forwards, or has a duration that does not fit the loop a whole number of times; when the loop is longer than 30 seconds; when the GIF would be over the size limit; and when a prerequisite is missing. The message says what to change. Every run first removes the GIF and frame sheet of an earlier run at the same path, so after a refusal there is no stale picture to mistake for the new one.

It warns, and still exports, when the figure has more than 20 words, text under 16 pixels in the GIF, more than three parts moving at once, no still moment of at least a second, a loop over 12 seconds, or an animation whose keyframes do not all name the same properties (the part drifts). Treat a warning as a defect until you have looked at the frames and decided otherwise.

In the report, `maxMoving` is the largest number of things the eye had to follow between two neighbouring frames: each visible part whose position, size or colour changed counts one, and any number of parts fading in together count one more. Parts fading out are not counted. One or two is what a calm figure reports; `maxMovingAtMs` says where in the loop to look. `longestHoldMs` is the longest stretch in which nothing changed.

Prerequisites: Node 20 or newer, ffmpeg, and Playwright with its Chromium (`npm install` in `<skill-dir>/scripts`, then `npx playwright install chromium`; an installed Google Chrome is used if Playwright's own browser is absent). Tested on macOS and on Ubuntu Linux. Windows is untested.

## Common mistakes

| What goes wrong | What to do instead |
|---|---|
| A title, a caption sentence or numbered steps inside the image | Delete them. Labels name things; one short line states the point. |
| A scene and a chart side by side | Pick the one that carries the idea. |
| Everything animates from the first frame | Open on the bare scene; start one beat at a time. |
| Motion never stops | End on the finished picture and hold it. |
| Rendering each frame with a script or a canvas | Draw one SVG and let CSS move it; the source stays editable and embeddable. |
| Handing over the GIF without looking at the frame sheet | Read `<name>-frames.png` first; overlaps and clipped text only show there. |
| Reusing the example's subject or wording | The examples show the technique. Draw the user's subject from scratch. |
