#!/usr/bin/env node
// Export one CSS-animated figure (an HTML file holding an inline SVG) as a looping GIF.
//
//   node export.mjs --check
//   node export.mjs figure.html [--out figure.gif] [--width 1200] [--fps 10]
//                               [--selector "#figure"] [--dark] [--max-mb 15]
//
// Writes <out> and a review sheet <out minus .gif>-frames.png (six frames, top to bottom).
// Prints a JSON report on stdout; everything meant for a person goes to stderr.
// Exit codes: 0 exported, 1 the figure or the arguments are wrong, 2 a prerequisite is missing.
// Every run first removes <out> and its sheet if an earlier run left them; they are written
// again only when the whole export succeeded, so a refusal never leaves a stale picture.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const FFMPEG = process.env.FFMPEG || 'ffmpeg';

// Review thresholds. They produce warnings, never refusals: the person looking at the frame
// sheet decides. Sizes are in pixels of the exported GIF.
const MAX_WORDS = 20;
const MIN_TEXT_PX = 16;
const MAX_MOVING = 3;
const MIN_HOLD_MS = 1000;
const MAX_LOOP_MS = 30000;
const LONG_LOOP_MS = 12000;

class Refusal extends Error {
  constructor(message, code = 1) { super(message); this.code = code; }
}

function parseArgs(argv) {
  const o = { width: 1200, fps: 10, maxMb: 15, dark: false, check: false, help: false };
  const value = { '--out': 'out', '--width': 'width', '--fps': 'fps', '--selector': 'selector', '--max-mb': 'maxMb' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--check') o.check = true;
    else if (a === '--dark') o.dark = true;
    else if (a === '--help' || a === '-h') o.help = true;
    else if (a in value) {
      if (i + 1 >= argv.length) throw new Refusal(`${a} needs a value`);
      o[value[a]] = argv[++i];
    } else if (a.startsWith('--')) throw new Refusal(`unknown option ${a}`);
    else if (o.input) throw new Refusal(`one figure per run; got a second file: ${a}`);
    else o.input = a;
  }
  for (const k of ['width', 'fps', 'maxMb']) {
    o[k] = Number(o[k]);
    if (!(o[k] > 0)) throw new Refusal(`--${k === 'maxMb' ? 'max-mb' : k} must be a positive number`);
  }
  return o;
}

const USAGE = `Usage:
  node export.mjs --check                 say which prerequisites are present
  node export.mjs figure.html [options]   export the figure as a looping GIF

Options:
  --out FILE       where to write the GIF (default: beside the figure, same name, .gif)
  --width N        GIF width in pixels (default 1200)
  --fps N          frames per second (default 10; 10 is exact in the GIF format)
  --selector CSS   the element to capture (default: #figure, else the first figure, else the first svg)
  --dark           render with the dark colour scheme
  --max-mb N       refuse a GIF larger than this (default 15)

Environment: FFMPEG=/path/to/ffmpeg, CHROME=/path/to/a/chromium-based/browser`;

// ---------- prerequisites ----------

function ffmpegStatus() {
  const r = spawnSync(FFMPEG, ['-version'], { encoding: 'utf8' });
  if (r.error || r.status !== 0) {
    return { name: 'ffmpeg', ok: false, fix: 'macOS: brew install ffmpeg   Debian/Ubuntu: sudo apt-get install -y ffmpeg   (or set FFMPEG=/path/to/ffmpeg)' };
  }
  return { name: 'ffmpeg', ok: true, detail: r.stdout.split('\n')[0] };
}

async function loadPlaywright() {
  const bases = [here, process.cwd()];
  const g = spawnSync('npm', ['root', '-g'], { encoding: 'utf8', shell: process.platform === 'win32' });
  if (!g.error && g.status === 0 && g.stdout.trim()) bases.push(path.dirname(g.stdout.trim()));
  for (const base of bases) {
    try {
      const entry = createRequire(path.join(base, 'noop.js')).resolve('playwright');
      const mod = await import(pathToFileURL(entry).href);
      const chromium = mod.chromium || (mod.default && mod.default.chromium);
      if (chromium) return chromium;
    } catch { /* try the next place */ }
  }
  return null;
}

async function launchBrowser(chromium) {
  const tries = process.env.CHROME ? [{ executablePath: process.env.CHROME }] : [{}, { channel: 'chrome' }];
  let last;
  for (const opts of tries) {
    try { return await chromium.launch(opts); } catch (e) { last = e; }
  }
  throw last;
}

// Returns { statuses, browser }. A later prerequisite is not probed once an earlier one it
// depends on is missing. The browser is left open for the export; the caller closes it.
async function prerequisites() {
  const statuses = [];
  const major = Number(process.versions.node.split('.')[0]);
  statuses.push(major >= 20
    ? { name: 'node', ok: true, detail: process.version }
    : { name: 'node', ok: false, fix: `Node 20 or newer is needed; this is ${process.version}` });
  statuses.push(ffmpegStatus());
  const chromium = await loadPlaywright();
  if (!chromium) {
    statuses.push({ name: 'playwright', ok: false, fix: `cd "${here}" && npm install && npx playwright install chromium   (Linux also: npx playwright install-deps chromium)` });
    return { statuses, browser: null };
  }
  statuses.push({ name: 'playwright', ok: true });
  let browser = null;
  try {
    browser = await launchBrowser(chromium);
    statuses.push({ name: 'browser', ok: true, detail: browser.version() });
  } catch (e) {
    statuses.push({ name: 'browser', ok: false, fix: `cd "${here}" && npx playwright install chromium   (Linux also: npx playwright install-deps chromium; or set CHROME=/path/to/chrome). Launch error: ${String(e.message).split('\n')[0]}` });
  }
  return { statuses, browser };
}

function printStatuses(statuses) {
  for (const s of statuses) {
    console.error(s.ok ? `ok       ${s.name}${s.detail ? '  ' + s.detail : ''}` : `MISSING  ${s.name}\n         fix: ${s.fix}`);
  }
}

// ---------- the figure, inside the page ----------

// Installed in the page. Finds the animations, validates nothing (the caller does), and lets
// the caller move every animation to one moment of the loop.
function pageSetup(selector) {
  const el = selector ? document.querySelector(selector)
    : document.querySelector('#figure') || document.querySelector('figure') || document.querySelector('svg');
  if (!el) return { error: selector ? `nothing matches the selector ${selector}` : 'the page has no element with id="figure", no figure element and no svg element; the file may be empty or its markup broken (compare it with template.html)' };
  const anims = el.getAnimations({ subtree: true }).filter(a => a.effect && a.effect.target);
  const skip = new Set(['offset', 'computedOffset', 'easing', 'composite']);
  const targets = [];
  const propsOf = new Map();
  const uneven = new Set();
  for (const a of anims) {
    const t = a.effect.target;
    if (!propsOf.has(t)) { propsOf.set(t, new Set()); targets.push(t); }
    const sets = a.effect.getKeyframes().map(kf => Object.keys(kf).filter(k => !skip.has(k)).sort().join(' '));
    for (const set of sets) for (const k of set.split(' ')) if (k) propsOf.get(t).add(k);
    // Keyframes of one animation that name different properties: the browser fills each gap
    // by blending toward the part's resting value, which shows as a slow drift.
    if (new Set(sets.filter(Boolean)).size > 1) uneven.add(a.animationName || '(unnamed)');
    a.pause();
  }
  window.__figure = {
    el,
    seek(ms) {
      for (const a of anims) a.currentTime = ms;
      return targets.map(t => {
        const cs = getComputedStyle(t);
        const o = {};
        for (const p of propsOf.get(t)) o[p] = cs[p];
        return o;
      });
    },
  };
  const box = el.getBoundingClientRect();
  const texts = [...el.querySelectorAll('text')];
  let words = 0, smallest = null;
  for (const t of texts) {
    const s = t.textContent.trim();
    if (!s) continue;
    words += s.split(/\s+/).length;
    // Scaled by the drawing's own zoom, not the text's: a label that pops in with a scale
    // animation is measured at full size.
    const ctm = (t.ownerSVGElement || t).getScreenCTM();
    const px = parseFloat(getComputedStyle(t).fontSize) * (ctm ? Math.hypot(ctm.a, ctm.b) : 1);
    if (smallest === null || px < smallest.px) smallest = { px, text: s };
  }
  return {
    cssWidth: box.width, cssHeight: box.height, words, smallest, uneven: [...uneven],
    animations: anims.map(a => {
      const t = a.effect.getTiming();
      return { name: a.animationName || a.id || '(unnamed)', duration: Number(t.duration) || 0, delay: t.delay || 0, iterations: t.iterations, direction: t.direction };
    }),
  };
}

function validateLoop(animations, where) {
  if (!animations.length) {
    throw new Refusal(`No CSS animation found in ${where}. A figure needs at least one element with an "animation:" rule that runs forever; a still picture is not exported as a GIF.`);
  }
  const finite = animations.filter(a => a.iterations !== Infinity);
  if (finite.length) throw new Refusal(`These animations do not repeat forever, so the GIF could not loop: ${[...new Set(finite.map(a => a.name))].join(', ')}. Give each one "infinite".`);
  const delayed = animations.filter(a => a.delay !== 0);
  if (delayed.length) throw new Refusal(`These animations use animation-delay, which shifts them out of step on every loop after the first: ${[...new Set(delayed.map(a => a.name))].join(', ')}. Remove the delay and put the waiting inside the keyframes (for example "0%,30%{opacity:0}").`);
  const turned = animations.filter(a => a.direction !== 'normal');
  if (turned.length) throw new Refusal(`These animations set animation-direction (${[...new Set(turned.map(a => `${a.name}: ${a.direction}`))].join(', ')}), so one pass of the keyframes is not one loop. Remove the direction and write the way back into the keyframes.`);
  const cycle = Math.max(...animations.map(a => a.duration));
  if (!(cycle > 0)) throw new Refusal('Every animation has a duration of zero.');
  const off = animations.filter(a => !(a.duration > 0) || Math.abs(cycle / a.duration - Math.round(cycle / a.duration)) > 1e-6);
  if (off.length) {
    throw new Refusal(`The loop is ${cycle / 1000}s long, but these animations do not fit into it a whole number of times, so the loop would jump: ${[...new Set(off.map(a => `${a.name} (${a.duration / 1000}s)`))].join(', ')}. Give every animation the same duration.`);
  }
  if (cycle > MAX_LOOP_MS) throw new Refusal(`The loop is ${cycle / 1000}s long; the limit is ${MAX_LOOP_MS / 1000}s. Shorten it: most figures read well in 6 to 10 seconds.`);
  return cycle;
}

// Counts what the eye has to follow in one frame: every visible part whose position, size or
// colour changed since the frame before, plus one if anything is fading in. Parts fading in
// together read as one event, parts fading out are not followed at all, and a part that is
// invisible before and after may jump freely (that is how a loop resets).
function motionStats(snapshots, frameMs) {
  let maxMoving = 0, maxAt = 0, hold = 0, longestHold = 0;
  for (let i = 1; i < snapshots.length; i++) {
    let moving = 0, changed = false, fadingIn = false;
    snapshots[i].forEach((now, k) => {
      const before = snapshots[i - 1][k];
      const hidden = 'opacity' in now && parseFloat(now.opacity) === 0 && parseFloat(before.opacity) === 0;
      if (hidden) return;
      let moves = false;
      for (const p of Object.keys(now)) {
        if (now[p] === before[p]) continue;
        changed = true;
        if (p !== 'opacity') moves = true;
        else if (parseFloat(now[p]) > parseFloat(before[p])) fadingIn = true;
      }
      if (moves) moving++;
    });
    if (fadingIn) moving++;
    if (moving > maxMoving) { maxMoving = moving; maxAt = i * frameMs; }
    hold = changed ? 0 : hold + 1;
    longestHold = Math.max(longestHold, hold);
  }
  return { maxMoving, maxMovingAtMs: Math.round(maxAt), longestHoldMs: Math.round(longestHold * frameMs) };
}

function run(cmd, args) {
  const r = spawnSync(cmd, args, { encoding: 'utf8' });
  if (r.error || r.status !== 0) throw new Refusal(`${path.basename(cmd)} failed: ${(r.stderr || String(r.error)).trim().split('\n').slice(-3).join(' | ')}`);
}

async function exportFigure(o, browser) {
  const input = path.resolve(o.input);
  if (!fs.existsSync(input)) throw new Refusal(`no such file: ${input}`);
  const src = path.parse(input);
  const out = path.resolve(o.out || path.join(src.dir, src.name + '.gif'));
  if (!out.toLowerCase().endsWith('.gif')) throw new Refusal(`--out must end in .gif: ${out}`);
  if (out === input) throw new Refusal('the figure to export is itself a .gif; give the HTML file');
  const sheet = out.slice(0, -4) + '-frames.png';
  fs.rmSync(out, { force: true });
  fs.rmSync(sheet, { force: true });
  const where = o.selector || 'the figure';
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'animated-figure-'));
  try {
    const page = await browser.newPage({
      viewport: { width: Math.round(o.width), height: 900 }, deviceScaleFactor: 1,
      colorScheme: o.dark ? 'dark' : 'light', reducedMotion: 'no-preference',
    });
    await page.goto(pathToFileURL(input).href, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready.then(() => true));
    const info = await page.evaluate(pageSetup, o.selector || null);
    if (info.error) throw new Refusal(info.error);
    const cycleMs = validateLoop(info.animations, where);

    const frames = Math.max(2, Math.round((cycleMs / 1000) * o.fps));
    const frameMs = cycleMs / frames;
    const handle = await page.evaluateHandle(() => window.__figure.el);
    const el = handle.asElement();
    const snapshots = [];
    for (let i = 0; i < frames; i++) {
      snapshots.push(await page.evaluate(ms => window.__figure.seek(ms), i * frameMs));
      await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
      await el.screenshot({ path: path.join(tmp, `frame-${String(i).padStart(4, '0')}.png`) });
    }

    const width = Math.round(o.width / 2) * 2;
    const tmpGif = path.join(tmp, 'out.gif');
    run(FFMPEG, ['-y', '-loglevel', 'error', '-framerate', String(o.fps), '-i', path.join(tmp, 'frame-%04d.png'),
      '-vf', `scale=${width}:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3`,
      '-loop', '0', tmpGif]);
    const bytes = fs.statSync(tmpGif).size;
    if (bytes > o.maxMb * 1024 * 1024) {
      throw new Refusal(`The GIF came out at ${(bytes / 1048576).toFixed(1)} MB, over the ${o.maxMb} MB limit. Lower --width or --fps, shorten the loop, or use fewer colours and gradients.`);
    }

    // Six moments from the middle of each sixth of the loop, so the sheet shows neither the empty
    // first frame nor the fade at the very end.
    const picks = [...new Set([0, 1, 2, 3, 4, 5].map(k => Math.min(frames - 1, Math.floor(((k + 0.5) * frames) / 6))))];
    const tmpSheet = path.join(tmp, 'sheet.png');
    const args = ['-y', '-loglevel', 'error'];
    for (const k of picks) args.push('-i', path.join(tmp, `frame-${String(k).padStart(4, '0')}.png`));
    const scaled = picks.map((_, k) => `[${k}:v]scale=640:-2,pad=iw:ih+8:0:0:color=0x888888[s${k}]`).join(';');
    args.push('-filter_complex', `${scaled};${picks.map((_, k) => `[s${k}]`).join('')}vstack=inputs=${picks.length}`, '-frames:v', '1', '-update', '1', tmpSheet);
    run(FFMPEG, args);

    const scale = width / info.cssWidth;
    const stats = motionStats(snapshots, frameMs);
    const smallestPx = info.smallest ? Math.round(info.smallest.px * scale * 10) / 10 : null;
    const warnings = [];
    if (info.uneven.length) warnings.push({ id: 'uneven-keyframes', message: `These animations name a property in some keyframes and leave it out of others, so the part drifts toward its resting look in between: ${info.uneven.join(', ')}. Write the same properties in every keyframe.` });
    if (info.words > MAX_WORDS) warnings.push({ id: 'too-many-words', message: `${info.words} words are drawn in the figure; more than ${MAX_WORDS} is hard to read while something moves. Cut labels until only the nouns are left.` });
    if (smallestPx !== null && smallestPx < MIN_TEXT_PX) warnings.push({ id: 'small-text', message: `The smallest text ("${info.smallest.text}") is ${smallestPx}px tall in the GIF; under ${MIN_TEXT_PX}px it is lost on a phone. Enlarge it or drop it.` });
    if (stats.maxMoving > MAX_MOVING) warnings.push({ id: 'busy', message: `${stats.maxMoving} parts are moving at the same moment (around ${(stats.maxMovingAtMs / 1000).toFixed(1)}s); the eye follows one. Stagger them so one finishes before the next starts.` });
    if (stats.longestHoldMs < MIN_HOLD_MS) warnings.push({ id: 'no-hold', message: `Nothing holds still for a full second (longest pause ${stats.longestHoldMs}ms). End the loop on the finished picture and hold it for two seconds or so before the reset.` });
    if (cycleMs > LONG_LOOP_MS) warnings.push({ id: 'long-loop', message: `The loop is ${cycleMs / 1000}s; past ${LONG_LOOP_MS / 1000}s few people watch it through.` });

    fs.mkdirSync(path.dirname(out), { recursive: true });
    try {
      fs.copyFileSync(tmpSheet, sheet);
      fs.copyFileSync(tmpGif, out);
    } catch (e) {
      fs.rmSync(out, { force: true });
      fs.rmSync(sheet, { force: true });
      throw e;
    }
    const height = Math.round((info.cssHeight * scale) / 2) * 2;
    return {
      gif: out, frameSheet: sheet, width, height, frames, fps: o.fps, loopMs: Math.round(cycleMs), bytes,
      animations: info.animations.length, words: info.words, smallestTextPx: smallestPx, ...stats, warnings,
    };
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

async function main() {
  const o = parseArgs(process.argv.slice(2));
  if (o.help || (!o.check && !o.input)) { console.error(USAGE); return o.help ? 0 : 1; }
  const { statuses, browser } = await prerequisites();
  let report;
  try {
    const missing = statuses.filter(s => !s.ok);
    if (o.check || missing.length) printStatuses(statuses);
    if (missing.length) {
      console.error(`\nNot ready: ${missing.map(s => s.name).join(', ')} missing. Nothing was exported.`);
      return 2;
    }
    if (o.check) { console.error('\nReady.'); return 0; }
    report = await exportFigure(o, browser);
  } finally {
    if (browser) await browser.close();
  }
  for (const w of report.warnings) console.error(`warning (${w.id}): ${w.message}`);
  console.error(`Wrote ${report.gif} (${report.width}x${report.height}, ${report.frames} frames, ${(report.bytes / 1024).toFixed(0)} KB). Look at ${report.frameSheet} before handing it over.`);
  console.log(JSON.stringify(report, null, 1));
  return 0;
}

main().then(code => process.exit(code), e => {
  console.error(e instanceof Refusal ? `Refused: ${e.message}` : e);
  process.exit(e instanceof Refusal ? e.code : 1);
});
