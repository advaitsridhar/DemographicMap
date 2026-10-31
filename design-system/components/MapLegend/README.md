# MapLegend

A translucent card in the bottom-left corner of the map that repeats the filter chips, the legend and the blank note while the filters panel is hidden, so a map without its controls still says what it shades.

## When to use

- Show it exactly while the filters panel is closed, and never beside the panel's own legend. "Hiding the controls is a request for more map, not for a map whose colours mean nothing, so the legend and the sentence saying what is being shaded come with it."
- Fill it from the same strings as the panel, at the same moment. Its three parts are the panel's summary chips, the panel's legend body and the panel's blank note, byte for byte.

## Anatomy

```html
<div class="map-legend" aria-label="Map legend">
  <p class="filter-summary">
    <span class="fchip">Most populous group</span><span class="fchip">Religion</span><span class="fchip">Religions</span><span class="fchip">Detail follows zoom</span>
  </p>
  <div class="map-legend-body"><!-- the Legend markup, identical to the panel's --></div>
  <p class="control-note">Grey areas publish no composition for this field at this level.</p>
</div>
```

In the app these carry ids: `#map-legend`, `#map-legend-summary`, `#map-legend-body`, `#map-legend-note`. The chips are FilterSummary, the body is Legend, the note is a ControlNote; this component owns the card and the chips' spacing inside it (`.map-legend .filter-summary`, no top margin and .45rem below).

You provide the markup, the same chip texts, legend HTML and note as the panel, and the legend's computed colours (see Legend). Where the card can meet controls in the map's bottom-right corner, you also provide `--map-controls-h` on it: the lift that clears them, measured.

## States and variants

- **Hidden**: the `hidden` attribute, set while the panel is open (`els.miniLegend.hidden = open`). The panel's state is remembered in `localStorage` as `wdm-filters`.
- **Content**: any legend type — status, ramp, group, empty — rewritten with the panel's on every repaint. The card grows upward from its corner: with the nine-group religion legend it is about 335px tall, with the five-row coverage key about 210px.
- **Desktop**: `left` at `overlay-inset` (12px) and `bottom` at `overlay-inset` plus the lift (see Lifted), width `min(legend-w, 100% - 2 × overlay-inset)`, 280px.
- **900px and below**: the full map width less the two insets.
- **Lifted**: where the card would cover MapLibre's scale bar and attribution, its `bottom` grows by `--map-controls-h`, the controls' height above the map's bottom edge, so `overlay-inset` stays between them and the card. That is every width of 900px and below, and a desktop map too narrow for the card beside the open attribution (a 1024px window with the filters closed) until the first drag collapses the attribution to its button. Measured in Chromium with the filters closed: 96px on a 390px phone, where the attribution wraps to two lines, and 76px there once a drag collapses it; 76px at 768px and 900px, before and after a drag, and on a landscape phone; 76px on a desktop map from 901px to 1160px until the first drag, and 0 after it; 0 from 1170px up. Its `max-height` is the map's height less the two insets and the lift, and past that it scrolls (`overflow-y: auto`), so on a short screen it never runs under the topbar.
- **640px and below**: padding drops from .6rem .7rem to .5rem .6rem.

## Content

- Chips name the view, then the topic, the categories and the chosen group where they apply, then the detail level: “Data coverage”, “Religion”, “Detail follows zoom”. The chosen group of a share map is the one keyed chip (`fchip fchip-key`).
- The note is the view's blank sentence: “Grey means no record for that unit at all, not even a gap marker.”, “Grey areas have no published population at this level.”, “Blank means the figure is missing at this level — not that the share is zero.”
- Write nothing for the map that the panel does not say. The chips are there because “a map shaded by "the Sikhism share of religion, second-level divisions only" says nothing without that line.”

## Tokens

- Card: `surface-1` mixed to 92% over the map (`color-mix(in srgb, var(--surface-1) 92%, transparent)`) under an 8px backdrop blur, a 1px `border-ring` edge, `radius`, `shadow`.
- Place and size: `overlay-inset`, `legend-w`, `z-map-legend` (10, below `z-map-status`). `--map-controls-h` is measured, not a token, and defaults to 0px.
- Inside: `text-chip` (chips), `text-legend` and the rest of Legend's tokens, `text-control-note` in `ink-muted` (note).

## Accessibility

- `aria-label="Map legend"` sits on a `div` with no role. Its computed role is `generic`, which ARIA does not allow to be named: Chromium keeps the label on a generic node, Playwright's ARIA snapshot drops it, and it is no landmark. The chips, legend and note are read as plain content after the map.
- `.map-legend-body` has no `aria-live`; only the panel's legend announces changes, and it is hidden while this card shows.
- Text on the card: `ink-secondary` 7.6:1 in light; `ink-muted` (ends, counts, note) 3.4:1 in light, below 4.5:1, and 4.9:1 in dark.
- Every colour on the card is named in words, as in the panel.

## In the app

- Container: site/index.html:133-140, after the map inside `#map-wrap`, with the comment quoted above.
- `setPanel(open)`, site/js/app.js:171-185, toggles `hidden` (179); `renderSummary()`, app.js:828-852, writes the chips (844-845) and the note (847-851) to both copies; `renderLegend()`, app.js:1020-1095, writes the body (1093-1094).
- The lift: `keepClearOfControls(element)`, site/js/map.js:614-631, writes `--map-controls-h` on the card and re-measures with a `ResizeObserver` on the card, the controls and the map; `controlsClearance()`, map.js:600-604, returns 0 while the card ends 12px or more left of the controls and their height otherwise. `start()` calls it once for the card (app.js:1336); app.css:373 and 375 add the lift to `bottom` and take it off `max-height`.
- Computed at runtime: the body's colours come from `Palette`, and all but the status colours differ by theme (see Legend). The card's light background resolves to `color(srgb 0.988235 0.988235 0.984314 / 0.92)` over the map.
- In the preview the status rows, the shade ramp and the missing swatch are tokens (`status-*`, `leading-share-0` … `leading-share-4`, `neutral`), so they theme as the app does. The nine group swatches have no token, so each is a frame-local property named after its light hex (`--shade-204272`), set to the shade `Palette.group` computes in each theme (Christianity `#204272` in light, `#2e60a4` in dark); they theme like the app too.

## Do / Don't

- Do keep it in the bottom-left corner at `overlay-inset`, 280px wide on desktop, and lift it above the scale bar and the attribution wherever it would cover them.
- Do write the card and the panel from one string each, so they cannot drift.
- Don't show it while the filters panel is open.
- Don't cover the attribution, even at phone width: CC BY requires it to stay readable, so the card moves.
- Don't drop the chips or the note to save room: without them the colours have no subject.
- Don't count on `aria-label` alone to name it: on a role-less `div` it is not announced.
