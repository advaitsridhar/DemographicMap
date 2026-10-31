# AboutDialog

The modal "About this map" dialog, opened from "About & sources": what the map shows, a key to the three data states (present, not yet available, not collected), the comparability warning, the sources with their licences, and the caveats.

## When to use

- For the app's standing explanation and credits. One per page, outside `.app`.
- Not for notes about one figure or one control: those belong in info bubbles and the place panel's notes.

## Anatomy

```html
<dialog aria-labelledby="about-title">
  <article>
    <header class="dialog-head">
      <h2 id="about-title">About this map</h2>
      <button class="ghost-button" type="button" aria-label="Close">✕</button>
    </header>

    <h3>What it shows</h3>
    <p>…</p>

    <h3>Gaps are data too</h3>
    <p>…</p>
    <ul class="gap-key">
      <li><span class="chip chip-present"></span><strong>Present</strong> — a value with a named source and reference year.</li>
      <li><span class="chip chip-missing"></span><strong>Not yet available</strong> — …</li>
      <li><span class="chip chip-notcollected"></span><strong>Not collected</strong> — …</li>
    </ul>

    <h3>Comparability warning</h3>
    <p>…</p>

    <h3>Sources &amp; licences</h3>
    <ul class="source-list">
      <li><a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener noreferrer">Natural Earth</a> - Public domain (CC0) - code concordance and largest-settlement points.</li>
    </ul>

    <h3>Caveats worth knowing</h3>
    <ul class="caveat-list"><li>…</li></ul>
  </article>
</dialog>
```

- `dialog`: at most `dialog-w` (640px) wide, `calc(100% - 2rem)` on narrow screens, at most 84vh tall; no padding of its own.
- `article`: padding `1rem var(--gutter-dialog) 1.6rem`; it scrolls (also at most 84vh).
- `.dialog-head`: a flex row that sticks to the top of the scrolling article on `surface-1`; its button takes `margin-left: auto`.
- `.gap-key` is an unbulleted grid with a `.4rem` gap; `.caveat-list` keeps its bullets, indented `1.1rem`.

## States and variants

- **Closed** — no `open` attribute; not rendered.
- **Open** — `showModal()`: centred in the top layer over `dialog::backdrop` (`backdrop`), the rest of the page inert. Chromium puts focus on the scrolling `article`; Tab then reaches the ✕.
- **Closing** — the ✕ (`close()`), a click on the backdrop (a click whose target is the dialog element itself), or Escape. Focus returns to "About & sources".

## Content

- Title "About this map". Headings name the thing: "What it shows", "Gaps are data too", "Comparability warning", "Sources & licences", "Caveats worth knowing".
- The gap key is a chip, the state's words in bold, an em dash and one definition: "Not yet available — the figure exists somewhere but this build has not fetched it."
- The key calls the recorded state "Present"; the legend and the map popups call it "Recorded". New copy should say "Recorded".
- The key's lead-in says the three states are "shown wherever a value is absent" (index.html:175), but the first of them is a value that is there.
- A source line is the linked name, the licence and what it supplies: "Natural Earth - Public domain (CC0) - code concordance and largest-settlement points." These lines use ASCII " - " where the rest of the app uses "—".
- Caveats are dated facts: "The Factbook was retired in February 2026, so country figures are a frozen snapshot."
- Italics mark a contrast or a census's own term: *not*, *cor ou raça*, *minzu*, *suku*.

## Tokens

- `surface-1` (dialog and sticky head), `hairline` (border), `radius`, `shadow`, `backdrop`.
- `ink-primary` (headings), `ink-secondary` (paragraphs, list items, source lines), `accent` (links).
- Gap-key chips: `status-good`, `status-warning`, `status-serious` fills, `border-ring` edge, `radius-swatch`, 12px square.
- Size and spacing: `dialog-w`, `gutter-dialog`.
- Type: `text-dialog-title` (1.05rem), `text-dialog-heading` (.84rem), `text-dialog-body` (.8rem, line height 1.6), `text-note` for source lines (.72rem, line height 1.45).

## Accessibility

- `aria-labelledby="about-title"` names the dialog; the opener carries `aria-haspopup="dialog"`; the ✕ is `aria-label="Close"`.
- Colour is never alone in the key: each chip is an empty span and the bold words carry the state.
- Source links open a new tab (`target="_blank" rel="noopener noreferrer"`) without saying so.
- `accent` link text on `surface-1` is 4.3:1 in light, below 4.5:1; it passes in dark (4.8:1).

## In the app

- Static markup, index.html:160-201. Only the source list is generated: `renderAboutSources()` app.js:1321-1340 maps a fixed list of seven `[name, url, note]` entries into `<li>`s.
- Wiring in `start()`, app.js:1231-1235: open with `showModal()`, close on the ✕ and on a click whose target is the dialog.
- CSS: app.css:539-554 for the dialog, app.css:511-518 for the source list and the chips.

## Do / Don't

- Do open it with `showModal()`. Setting `open` gives no backdrop, no inert page and no Escape.
- Do give every source its licence and what it supplies.
- Don't show a gap colour without its words.
- Don't move per-figure caveats here; a caveat belongs here only when it holds for the whole map.
