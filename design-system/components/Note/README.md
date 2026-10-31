# Note

Small muted text under a figure or in place of one: it lists the groups a source named without shares, or says why a place has no figures at all.

## When to use

- At the end of a composition section, for groups the source names without a share ("Named without published shares: …"). With no shares at all, it is the section's only content.
- As the body of "Why this is empty", when a place has none of population, religion, language, ethnicity or median age and its record says why.
- As the body of "Not gathered yet", when a place has none of those figures, carries no reason but has an adapter hint, and some of its fields say nothing about why they are empty.
- Not for one field's gap: that is a GapNote.

## Anatomy

```html
<p class="note"><span style="color:var(--status-not-available)" aria-hidden="true">▲</span> Named without published shares:
        declining regional dialects and languages.</p>
```

- `p.note`: .72rem in `ink-muted`, .45rem below whatever precedes it.
- The ▲ span: the Not yet available glyph, coloured inline and hidden from screen readers. The app writes the hex `#fab219`; write the token, as above. Only the "Named without published shares" note has the glyph.
- In "Why this is empty" only, a link to the notes on each source.

## States and variants

- **Named after figures** (France, Language): follows the bar, the list and the table toggle.
- **Names only** (Gaza Strip, Language): no bar, list or table; the note is the whole section. At most ten names are printed.
- **Why this is empty** (heading "Why this is empty"): the record's reason, then "The notes on each source say what was tried." with "notes on each source" linked.
- **Not gathered yet** (heading "Not gathered yet"): "No figures for this unit have been gathered yet." when no field explains itself, or "No population or median age figure has been gathered for this unit yet; the other fields say why they are empty." when some do. No shipped place reaches this panel; the repository's tests do (`tests/test_frontend.js:358–396`).

## Content

- Open the note on names without shares with "Named without published shares:" and list the names as the source gives them, separated by commas, ending in a full stop.
- State a reason as a fact about the place and its source: "Not a canton: one of Ecuador's zonas no delimitadas, ground whose province was not settled when the map was drawn."
- Keep "Why this is empty" and "Not gathered yet" distinct: "The two are different claims and must not read alike."
- Never name a command or a file: "the panel is for a reader of the map".

## Tokens

`text-note` (.72rem, line-height 1.5), `ink-muted`, and `status-not-available` for the ▲ (inline `#fab219`).

Contrast: `ink-muted` measures 3.5:1 on `surface-1` in light, below 4.5:1, and in "Why this is empty" it is the only text the section has. That breaks the brand book's own rule for `ink-muted`. The link has no rule of its own: it takes the browser's link colour (`#0000ee` in light, `#9e9eff` in dark), not `accent`.

## Accessibility

- The ▲ is `aria-hidden="true"`. The words "Named without published shares" carry the meaning.
- The link opens a new tab (`target="_blank"`, `rel="noopener noreferrer"`) without saying so. Its text breaks across a line in the source and reads "notes on each source".
- Nothing else is interactive.

## In the app

- Names without shares (the code's `unlabelled`): `compositionPanel`, `site/js/dashboard.js:383–387`. The names are the rows with no share (`pct == null`), collected at 337.
- Hint panels: `hintPanel(record)`, `dashboard.js:402–424`, shown only when the record has a `gap_reason` or an `adapter_hint`. Link target `SOURCE_NOTES` (393); field words 426–427; `gapReason` 430–434; `listed` 436–439.
- CSS: `site/css/app.css:509`.
- You provide the names or the reason. The ▲ colour is `Palette.status("not_available").color`.

## Do / Don't

Do:
- Name the absence in words: "Named without published shares", "Why this is empty", "Not gathered yet".
- Make the reason specific to the place and the source.
- Set a reason the reader must read in `ink-secondary` in new work; the app's `ink-muted` fails contrast.

Don't:
- Don't draw a bar or percentages for names that came without shares. Nothing was published to draw.
- Don't put a figure's long caveat here. It goes behind the heading's "i".
- Don't call a field "Not gathered yet" when its gap already explains itself.
