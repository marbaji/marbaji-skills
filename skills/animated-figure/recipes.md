# Animation recipes

All motion is CSS keyframes inside the SVG's own `<style>`. The loop is one timeline from 0% to 100%; each part has its own `@keyframes` that says where it is at each moment of that one timeline.

## Three rules for a clean loop

The exporter refuses a figure that breaks the first two. The third it cannot see: check it on the frame sheet and by watching the GIF restart.

1. **One duration for everything, running forever.** Put it in one rule:
   ```css
   .token,.card,.point{animation-duration:8s;animation-iteration-count:infinite;animation-timing-function:ease-in-out}
   ```
   A shorter animation is accepted only if it fits the loop a whole number of times (a 2s pulse in an 8s loop).
2. **No `animation-delay`.** A delay happens once, so every loop after the first is out of step. Write the wait into the keyframes instead: `0%,30%{opacity:0}` means "invisible for the first 30% of the loop".
3. **The loop must be able to restart unseen.** Every part ends the loop (100%) looking the way it starts (0%), or invisible.

## Planning the timeline

Give each beat a slice of the loop and leave a gap between slices. For five beats in 10 seconds:

| Beat | Starts | Ends |
|---|---|---|
| 1 | 5% | 25% |
| 2 | 30% | 50% |
| 3 | 55% | 62% |
| 4 | 64% | 72% |
| the point appears | 74% | 78% |
| hold, everything still | 78% | 96% |
| fade for the restart | 96% | 100% |

## Recipes

Appear and stay until the reset:
```css
@keyframes card{0%,30%{opacity:0}34%,96%{opacity:1}100%{opacity:0}}
```

Travel from A to B and stay (draw the part at A; the distance is in the drawing's own units):
```css
@keyframes token{0%,5%{opacity:0;transform:translateX(0)}10%{opacity:1;transform:translateX(0)}45%,96%{opacity:1;transform:translateX(520px)}100%{opacity:0;transform:translateX(520px)}}
```

Travel and vanish on arrival (a message that is consumed):
```css
@keyframes msg{0%,4%{opacity:0;transform:translateX(0)}8%{opacity:1;transform:translateX(0)}26%{opacity:1;transform:translateX(410px)}30%,100%{opacity:0;transform:translateX(410px)}}
```

Pop in (scale needs the two extra properties so the part grows from its own centre):
```css
.badge{transform-box:fill-box;transform-origin:center}
@keyframes badge{0%,58%{opacity:0;transform:scale(.6)}62%,96%{opacity:1;transform:scale(1)}100%{opacity:0;transform:scale(1)}}
```

Step a marker through several states, pausing at each (a bar that narrows, a highlight that moves):
```css
.bar{transform-box:fill-box;transform-origin:left center}
@keyframes bar{0%,8%{opacity:1;transform:translateX(0) scaleX(1)}16%,28%{opacity:1;transform:translateX(432px) scaleX(.5)}36%,96%{opacity:1;transform:translateX(432px) scaleX(.25)}98%{opacity:0;transform:translateX(432px) scaleX(.25)}99%{opacity:0;transform:translateX(0) scaleX(1)}100%{opacity:1;transform:translateX(0) scaleX(1)}}
```
The last three keyframes are the unseen restart: fade out, jump home while invisible, fade in.

Fill or drain a level (a gauge, a tank, a bar that grows from its base):
```css
.level{transform-box:fill-box;transform-origin:center bottom}
@keyframes level{0%,10%{transform:scaleY(1)}30%,50%{transform:scaleY(.4)}70%,100%{transform:scaleY(1)}}
```
Draw the part at its fullest and scale it down; a mark it has to line up with sits at the part's top edge minus the scaled height.

Rule something out (it goes pale and stays pale):
```css
@keyframes out{0%,18%{opacity:1}22%,96%{opacity:.18}100%{opacity:1}}
```

Draw a line or an arrow along its path (set `pathLength="1"` on the `<path>`):
```css
.wire{stroke-dasharray:1;animation-name:wire}
@keyframes wire{0%,20%{opacity:1;stroke-dashoffset:1}40%,96%{opacity:1;stroke-dashoffset:0}100%{opacity:0;stroke-dashoffset:0}}
```

The point line, last:
```css
@keyframes point{0%,74%{opacity:0;transform:translateY(8px)}78%,96%{opacity:1;transform:translateY(0)}100%{opacity:0;transform:translateY(0)}}
```

## Traps

- **`transform` on an SVG part replaces its `transform` attribute.** Position parts with `x`, `y`, `cx`, `cy` or a wrapping `<g transform="...">`, and animate a class on an inner or outer group.
- **Scale and rotate pivot on the drawing's corner** unless the part has `transform-box:fill-box;transform-origin:center`.
- **Write the same properties in every keyframe of one animation.** A keyframe that omits `transform` makes the browser blend toward the part's resting value, which shows as a drift.
- **Text is `<text>` inside the SVG**, in the system font stack the template sets. No web fonts: they may not load when the GIF is rendered.
- **Keep colours flat.** Gradients and shadows make the GIF larger and band in its 128-colour palette.
- **Class and keyframe names are shared by the whole web page**, even though the `<style>` sits inside the SVG. One figure per page needs nothing. When two figures will be embedded in the same page, give each its own prefix on every class and `@keyframes` name (`f1-token`, `f2-token`); the GIFs are unaffected.
- **Reduced motion.** The template turns animation off under `prefers-reduced-motion` and the rule beside it should put each part where the loop ends, so the still shows the finished picture: a part that has travelled gets its final `transform`, and a part that is gone by the end gets `opacity:0`. This affects the embedded SVG only; the GIF always moves.
- **Dark mode.** The embedded SVG follows the reader's colour scheme through the template's variables. The GIF is exported in light unless you pass `--dark`.
