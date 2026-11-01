# FactCard

A two-column grid of six tiles with a place's headline figures — population, capital, largest settlement, median age, sex ratio and life expectancy — each with its year and source, or the state of its absence.

## When to use

- Directly under EntityHeader (and the record note, when there is one), once per place.
- Always all six tiles, in the order above. A missing figure becomes a gap tile; never drop a tile or leave one blank.
- Not for shares (CompositionPanel), and not for disputed ground or water, which show no tiles.

## Anatomy

```html
<div class="facts">
  <div class="fact">
    <div class="fact-label">Median age<button type="button" class="info" data-info-text="{note}" aria-label="About the median age figure">i</button></div>
    <div class="fact-value">31.8 yrs</div>
    <div class="fact-meta">2011 · Census of India 2011</div>
  </div>
  <div class="fact">
    <div class="fact-label">Life expectancy</div>
    <div class="fact-value is-gap">
      <span style="color:var(--status-not-available)" aria-hidden="true">▲</span> Not yet available
    </div>
  </div>
</div>
```

`.facts` is the grid; each `.fact` is a tile holding `.fact-label`, `.fact-value` and an optional `.fact-meta`. `{note}` is the figure's note.

## States and variants

- **Value with meta** — `.fact-meta` follows the value. Population, median age, sex ratio and life expectancy get year · source, the sex ratio with its unit in front; the largest settlement gets its own population (`1.5M people`).
- **Value without meta** — leave the `.fact-meta` element out (Capital: `Thiruvananthapuram`, `Paris`).
- **Gap** — `.fact-value.is-gap`, set when the value is missing, an empty list or a gap status. The glyph takes the status colour and is `aria-hidden="true"`; the words follow. A gap never has a meta line.
  - `▲` `status-not-available` (`#fab219`) `Not yet available`
  - `◼` `status-not-collected` (`#ec835a`) `Not collected`
  - `–` `status-not-applicable` (`#898781`) `Not applicable`
  - Estimates would print `◐ Derived from published figures` or `◌ Estimated, not published`; no shipped record reaches a tile with one.
- **With a note** — an info dot at the end of `.fact-label`, only when there is note text. A gap's own note wins over the field's note.
- **Long value** — `overflow-wrap: break-word` breaks a word that cannot fit: `Thiruvananthapuram` wraps inside the word in a half-width tile.

## Content

- Labels in sentence case; CSS uppercases them: `Population`, `Capital`, `Largest settlement`, `Median age`, `Sex ratio`, `Life expectancy`.
- Populations compact: `34.5M`, `68.5M`, `1.4B`, `43.3K`. Ages with ` yrs`: `31.8 yrs`.
- The sex ratio is a bare number (`92.3`, `96`) and its unit opens the meta: `males per 100 females · 2011 · Census of India 2011`.
- Meta is year, then the source up to its first comma, joined with ` · `: `2025 · CIA World Factbook (public domain)`. A measure with no year prints the source alone (`CIA World Factbook (public domain)`); give the year whenever the source has one.
- Gap words come from `Palette.STATUS`. Never write your own, and never show a dash or a zero for a missing figure.
- Keep notes out of the tile. They go behind the dot: “These run to a hundred words apiece and the tiles are a two-column grid; the bubble is the pattern this panel already uses for exactly that trade.” (`site/js/dashboard.js:74–76`)

## Tokens

- Tile: `surface-sunken` fill, `border-ring` edge, `radius-sm`; tiles sit `tile-gap` apart.
- Text: `ink-muted` (label, meta, gap words), `ink-primary` (value, inherited).
- Glyphs: `status-not-available` (`status-warning`), `status-not-collected` (`status-serious`), `status-not-applicable`. The app writes `Palette.status(s).color` inline as hex; write the token, `style="color:var(--status-not-available)"`, which has the same value in both themes.
- Type: `text-fact-label`, `text-fact-value`, `text-fact-gap`, `text-fine` (meta).

## Accessibility

- Tiles are plain `div`s, read in order: label, value, meta. A gap reads “Life expectancy Not yet available”; the glyph is hidden and the words carry the state.
- The info dot is a `button` named `About the {label} figure`, label lower-cased: `About the median age figure`. Hover or focus opens its note; a click closes it, because `site/js/app.js:464–466` spares only `[data-info]`.
- Contrast: label, meta and gap words are `ink-muted` on `surface-sunken`: 3.1:1 in light and 4.4:1 in dark, below 4.5:1 at 10.6–12.5px. A gap's words must be read, so this breaks the brand book's own rule for `ink-muted`; it is the source's value, flagged.

## In the app

- `factCard()` `site/js/dashboard.js:78`, `unitLabel()` `:111`, `measureCard()` `:116`, `figureNote()` `:138`; the six tiles in `render()` `site/js/dashboard.js:520–535`. CSS `site/css/app.css:471–479`, `673–676`.
- Computed at render: the population through `Fmt.number()` (`site/js/data.js:296`), which formats in the reader's locale; the glyph, colour and words from `Palette.status()` (`site/js/palette.js:267`); the meta from the measure's `unit`, `year` and `source`.
- You provide the markup; each label; the formatted value or its gap status; the meta parts; the note; and the status token.

## Do / Don't

- Do keep all six tiles in the fixed order, with a gap tile for any missing figure.
- Do spell the unit out at the start of the meta line.
- Don't print a year or a source on a gap tile.
- Don't colour the gap words; only the glyph takes the status colour.
