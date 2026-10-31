# CompositionPanel

One place's population broken down by one classification — religion, language, ethnicity, ancestry or Scheduled Caste / Tribe — as a stacked bar with a labelled list under it, so every share has a colour, a name and a percentage.

## When to use

- For a set of shares from one source and one classification, inside a PanelSection titled with that classification.
- One bar per classification and place. Never set two countries' categories in one bar: percentages do not cross borders.
- Not for a gap (the section holds a gap note instead) and not for names without shares (they go in the note `Named without published shares:` after the table).

## Anatomy

```html
<div class="stack-bar" role="img" aria-label="Scheduled Caste 9.1%, Scheduled Tribe 1.5%, not accounted for 89.4%">
  <span style="flex:0 0 9.10%;background:var(--categorical-1)" title="Scheduled Caste 9.1%"></span>
  <span style="flex:0 0 1.50%;background:var(--categorical-2)" title="Scheduled Tribe 1.5%"></span>
  <span class="stack-rest" style="flex:0 0 89.40%" title="Not accounted for by these categories 89.4%"></span>
</div>
<ul class="composition-list">
  <li><span class="swatch" style="background:var(--categorical-1)" aria-hidden="true"></span>
      <span class="label">Scheduled Caste</span>
      <span class="pct">9.1%</span></li>
</ul>
```

The app writes each fill as the hex `Palette.categorical(i)` returns for the theme of the moment (slot 1 is `#2a78d6` in light, `#3987e5` in dark). Write the slot's token instead, `categorical-1` for the first group, so the fill follows the theme.

In the section the order is: head, an estimate's line when there is one, `.stack-bar`, the basis chip when there is one, `.composition-list`, the table toggle (DataTable), then any names-only note.

## States and variants

The data sets every state, through the inline styles and one class.

- **Partition** — shares within half a point of 100. Widths are the shares. Rounding is put back into the largest groups so the column reads `100.0%`, and the heading's “i” gains “Shares are published rounded to one decimal and came to a tenth of a point off 100%; …”. When the published shares miss 100 by less than about a twentieth of a point, a tenth can still move with no sentence: Bali's ethnicity sums to 100.01 and shows Balinese, published as 85.97, at `85.9%`.
- **Folded** — more than eight groups: the first seven, then `Other groups (2)` in slot 8 with the tail's sum. The bar's `aria-label` and title say `Other groups` without the count; the table lists every group.
- **Short** — total above 0 and below 99.5: true widths, and the remainder as `span.stack-rest`, hatched, titled `Not accounted for by these categories 89.4%`. The bar's label ends `, not accounted for 89.4%`. Below 95 the basis chip `describes 10.6% of the population` follows the bar.
- **More than one answer** — total above 100.5: normalised to the full bar. When the shares, bounds left out, sum past 105, the basis chip reads `more than one answer allowed`.
- **Upper bound** — a row with a `<` bound prints `<0.9%` in the list, the title, the label and the table.
- **Estimate** — the same bar and list, after a `◌ Modelled` or `◐ Derived` line.
- **Zero rows** — `0.0%` rows leave the bar and the list and stay in the table.

## Content

- Name groups exactly as the source does, case included: `unspecified`, `other`, `Roman Catholic`.
- One decimal on every share: `54.7%`, `100.0%`, `0.3%`. “One decimal always: these are the figures in a column, and the column has to be seen to add up.” (`site/js/dashboard.js:17–18`)
- Sort by share, largest first; the folded row goes last.
- Say what the classification really is in the note behind the heading's “i”. Kerala's Ethnicity counts country of birth, and its note says the census “asks no ethnicity”.
- Escape the bound in markup (`&lt;0.9%`). The app inserts `<` raw, which the HTML parser happens to keep as text.

## Tokens

- Fills: `categorical-1` to `categorical-8`, written inline as hex by `Palette.categorical(i)` in the current theme.
- `border-ring` (swatch edge), `radius-xs` (bar ends), `radius-swatch` (swatch), `hairline` (the rest's hatch and inset edge), `ink-secondary` (`.pct`).
- Type: `text-row` (list rows). The bar is 16px high with 2px gaps and a 10px swatch, literals in `bundle.css`.

## Accessibility

- The bar is `role="img"`. Its `aria-label` names every shown group with its share, and the shortfall; segment `title`s reach the pointer only.
- Swatches are `aria-hidden="true"`. The list carries each name and share as text, so hue is never the only channel.
- `.label` truncates with an ellipsis and has no `title`. A screen reader still reads the whole name from the list; on screen, a cut name is whole only in its segment's `title` (when the bar has not clipped that segment) and in the table.
- The table is the full record for assistive technology: “A table view of the same numbers is one click away for screen readers, print and forced-colours.” (`site/js/dashboard.js:7–8`)

## In the app

- `compositionPanel()` `site/js/dashboard.js:313–389`: bar `339–364`, list `368–371`. `toHundred()` `:169`, `foldGroups()` `:200`.
- Computed at render: each width is share ÷ scale × 100 to two decimals, the scale being 100 for a short set and the total otherwise. Colours come from `Palette.categorical(i)` (`site/js/palette.js:107`) in the theme of the moment, so a dark render writes `#3987e5`, `#d95926` and so on. A theme change repaints the map and legend but not the panel, so the colours keep the old theme until the panel next renders.
- Known bug, kept as the source has it: segments are `flex: 0 0 X%` with `gap: 2px` and `min-width: 2px`, so with many segments they add up past the bar and `overflow: hidden` clips the tail. In the 400px panel France's religion bar needs 378px of 363.8px: `Judaism`, `Other religions` and `Other groups` vanish, and Gaza loses `Christian`. The list and the table still carry them.
- You provide the markup, each group's name and share (and its bound), the year, the note and the colours.

## Do / Don't

- Do keep a short set's true widths and hatch the rest: “Hatched rather than a flat colour so it reads as absence and never as another group” (`site/css/app.css:490–491`).
- Do fold past eight groups into `Other groups (n)`. A ninth slot returns the neutral “so a bug shows up as grey rather than as a fabricated ninth identity” (`site/js/palette.js:105–106`).
- Don't stretch a short set to the full bar: that “asserts the population is entirely described” (`site/js/dashboard.js:342–343`).
- Don't give the rest a swatch or a list row.
