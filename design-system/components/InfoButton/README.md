# InfoButton

A small italic "i" in a ring at the end of a heading that opens a bubble holding the long note about that heading's control or figure, on hover, focus or click.

## When to use

- For text that is "worth keeping every word of and not worth reading every time, which is what a bubble is for" (dashboard.js:222-223): a filter control's caveat, a composition's note, a figure's note. In the filters panel, "Every one of these was a paragraph sitting permanently under the control it described" (app.js:191-192).
- Not for what a reader needs in order to read the figure correctly. That stays on the page: the basis chip, an estimate's first sentence, the blank note under the legend.

## Anatomy

```html
<!-- filter section heading: the text is a key into INFO -->
<h3 id="field-label">Topic
  <button type="button" class="info" data-info="topic"
          aria-label="About comparing topics across borders">i</button>
</h3>

<!-- place panel heading: the text travels with the button -->
<div class="panel-head"><h3>Religion<button type="button" class="info" data-info-text="Census of India 2011 table C-01. …"
                    aria-label="About the religion figures">i</button></h3><span class="panel-year">2011</span></div>

<!-- fact tile label -->
<div class="fact-label">Median age<button type="button" class="info" data-info-text="Census of India 2011 table C-13: …"
                    aria-label="About the median age figure">i</button></div>

<!-- the bubble, appended to <body> while open -->
<div class="info-bubble" role="note" style="top: 198px; left: 47px;">Religion, language and ethnicity are three separate census questions, …</div>
```

`.filter-section > h3`, `.panel-head h3` and `.fact-label` are `display: flex; align-items: center`, so the dot sits on the heading's line. In a fact label it also takes `flex: none; letter-spacing: 0`, because "The label is uppercase with a .05em tracking, which would push the "i" off its own circle." (app.css:673-674)

## States and variants

| State | Set by | Look |
|---|---|---|
| At rest | no `aria-expanded` (before the first open), or `"false"` | `ink-muted` "i", `axis` ring |
| Hover | `:hover` | "i" and ring turn `accent` |
| Open | `aria-expanded="true"` | `accent`; the bubble shows below |
| Focus | `:focus-visible` | 2px `accent` outline at 2px |

- **Opening.** Hover or focus opens the bubble unpinned, and an unpinned bubble lets the pointer through to whatever it covers. The pointer leaving closes it, unless its dot has keyboard focus: then it stays while the focus does, until the pointer opens another dot's bubble. A click pins it, and a second click closes it. Escape or a click outside a `[data-info]` element closes it. Only one bubble is open at a time.
- **Scrolling.** A scroll carries the bubble along with its dot. Once the dot is out of sight (outside the window, outside a panel that scrolls or clips it, or under something drawn over it, such as the filters panel's sticky head), the bubble closes; while the dot has keyboard focus it hides instead, and comes back with the dot.
- **Placement.** Fixed to the viewport, 6px below the button, its left edge 8px left of the button's and kept 8px inside the window; at most `min(var(--bubble-w), 100vw - 1rem)` wide. "Placed below the button and nudged back inside the viewport rather than anchored to the panel: at phone width the panel is narrower than the bubble needs to be." (app.js:276-278)
- **Text source.** `data-info="topic|depth|spread|group|estimates"` looks the text up in `INFO`; `data-info-text` carries it (every place panel dot, and the Legend dot, whose text is rewritten on each repaint).
- **Size.** `.95em` of its heading, so it scales with it: about 10.3px in a filter eyebrow, 12.9px in a panel heading, 10px in a fact label. "Small, quiet, and the same size as the heading it sits in, so it reads as punctuation rather than as another control." (app.css:617-618)
- **None.** No note, no dot: `infoDot` returns an empty string for empty text.

## Content

- The button's text is "i". Its `aria-label` says what the note is about, starting "About": "About comparing topics across borders", "About how the shading is scaled", "About estimated units", "About the religion figures", "About the median age figure". Place panel labels follow `About the ${title.toLowerCase()} figures` and `About the ${label.toLowerCase()} figure`.
- The bubble is plain text (set with `textContent`) in full sentences: "Some units have no read figure and carry an estimate instead. Their colour is what the estimate says, drawn like any other, and the panel names the status and how it was made."
- The Legend dot's note is the view's own note followed by "Colours are resolved from the data each time you change a control, so the key always describes what is on screen."

## Tokens

Dot: `ink-muted` and `axis` at rest, `accent` on hover, open and focus, `radius-round`; type `text-info`. Bubble: `surface-1`, `ink-primary`, `hairline`, `radius-sm`, `shadow`, `z-info-bubble`, `bubble-w`; type `text-legend` at line height 1.5.

At rest the "i" is 3.5:1 on `surface-1` in light (3.1:1 on a fact tile's `surface-sunken`), and the `axis` ring is 1.75:1 in light and 1.5:1 in dark, below 3:1 for a control's edge. Hover and open lift both to `accent` (4.3:1 light, 4.8:1 dark). Kept from the source; flagged.

## Accessibility

- A real `<button type="button">` with an `aria-label`; "i" alone is not a name. The legend's "Group not yet classified" line emits a dot with no `aria-label` (app.js:1086), so its name is "i". Don't copy it.
- `aria-expanded` is `"true"` while the bubble is open and `"false"` after it closes; it is absent until the first open.
- Focus opens the bubble, "because hover alone is unreachable by keyboard and unusable on a touchscreen" (app.js:198-199). Inside the filters panel, the Escape that closes a bubble also hides the panel.
- The bubble is a `role="note"` at the end of `<body>`, with no `aria-describedby` from the button, so a screen reader announces the label and state but not the note.
- Dots that carry only `data-info-text` cannot be pinned: the outside-click listener tests `closest("[data-info]")`, so a click or Enter closes the bubble instead of pinning it (app.js:344-346).
- A heading's "i" joins the name of whatever that heading labels; measured: "TOPIC About comparing topics across borders".

## In the app

- `INFO` app.js:202-234; `closeInfo` app.js:238-243; `openInfo` app.js:245-270 builds the bubble and `placeInfo` app.js:272-286 places it; `wireInfo` app.js:319-366 delegates every listener to `document`, because "most of these buttons do not exist yet: the sidebar rebuilds its panels on every selection" (app.js:316-317). Its scroll listener (app.js:347-365) moves the bubble with its button; `inSight` (app.js:288-306) says whether the button can still be seen, and `keyboardFocused` (app.js:308-314) whether to hide the bubble rather than close it.
- `infoDot(text, label)` dashboard.js:225-229 writes the place panel dots, for `factCard` (dashboard.js:83-84) and `compositionPanel` (dashboard.js:322-325). `updateLevelNote` app.js:1155-1162 rewrites the Legend dot's text.
- The consumer provides the note (or an `INFO` key) and the `aria-label`. The bubble's `top` and `left` are computed at runtime from the button's box.
- CSS: `site/css/app.css:617-637` (dot, bubble), 668-671 and 673-676 (heading layouts).

## Do / Don't

Do:
- Put the dot at the end of the heading's text, inside the heading element.
- Give every dot an "About …" label.
- Keep what changes how a figure is read on the page; move only the long explanation behind the dot.

Don't:
- Don't render a dot with no note.
- Don't put links or markup in a bubble; it is plain text.
- Don't anchor the bubble inside its panel; fix it to the viewport so it can be wider than the panel.
