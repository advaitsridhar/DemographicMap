# Legend

The key to the map's colours: it says what each colour or shade stands for in the view on screen, and how many units have no figure at all.

## When to use

- Under the "Legend" heading of the filters panel and, as the same markup, inside the on-map copy while that panel is hidden (see MapLegend).
- Rebuild it from the pass that painted the map, on every repaint, so it lists only what is drawn: "Colours are resolved from the data each time you change a control, so the key always describes what is on screen."
- One type per view: `status` for Data coverage, `ramp` for Population, Median age, How concentrated and Share of one group, `group` for Most populous group, `empty` when no unit at the level has a value on a `ramp` view (metrics.js:511-513). A group view with no leader at all still draws `group`: the shade ramp and the missing line.

## Anatomy

The app's container is `<div id="legend" aria-live="polite">`; here it is `.legend` (`.map-legend-body` on the map). It holds one type.

```html
<!-- status: five rows -->
<div class="legend" aria-live="polite">
  <div class="legend-item">
    <span class="legend-icon" style="color:var(--status-present)" aria-hidden="true">●</span>
    <span class="legend-swatch" style="background:var(--status-present)"></span>
    <span>Recorded</span>
  </div>
</div>
<!-- ramp: 11 stops (var(--sequential-0) … var(--sequential-10), or on a share map the group's
     own shades, as here for Islam), the ends, the fitted note (share maps, Fit to view), the missing line -->
<div class="legend" aria-live="polite">
  <div class="legend-scale" role="img" aria-label="Colour scale from 0% to 100%">
    <span style="background:#bef0d3"></span><!-- 9 more --><span style="background:#114d2a"></span>
  </div>
  <div class="legend-ends"><span>0%</span><span>100%</span></div>
  <p class="legend-fitted-note">Fitted to the range on screen.</p>
  <div class="legend-item">
    <span class="legend-swatch" style="background:var(--neutral)"></span>
    <span>No value for 128 units</span>
  </div>
</div>
<!-- group: up to 12 leading groups, the more line, the shade ramp, the missing line -->
<div class="legend" aria-live="polite">
  <ul class="legend-groups">
    <li><span class="legend-swatch" style="background:#47440b"></span>
        <span class="legend-group-name">Romance languages</span>
        <span class="legend-group-count">288</span></li>
    <li class="legend-more">+55 more groups lead somewhere</li>
  </ul>
  <div class="legend-shade">
    <span class="legend-shade-label">Share of the leading group</span>
    <div class="legend-scale" role="img" aria-label="Paler is a smaller share, darker is a larger one">
      <span style="background:var(--leading-share-0)"></span><!-- 3 more --><span style="background:var(--leading-share-4)"></span>
    </div>
    <div class="legend-ends"><span>25% or less</span><span>100%</span></div>
  </div>
  <div class="legend-item"><span class="legend-swatch" style="background:var(--neutral)"></span><span>No figure for 1,106 units</span></div>
</div>
```

You provide the markup, the words and numbers (labels, group names, units led, the two ends, each N) and every colour as an inline style. Where `Palette` reads a fixed slot, write the token: `status-*` for the status rows, `sequential-0` … `sequential-10` for the magnitude ramp, `leading-share-0` … `leading-share-4` for the shade ramp, `neutral` and `unplaced`. A group's swatch and a share map's stops are shades `Palette.group` computes from the group's hue; they have no token, so write the hex. The blank note under the legend is a `.control-note`, not part of it.

## States and variants

- **status** (Data coverage): Recorded, Derived from published figures, Estimated, not published, Not yet available, Not collected, in that order. Not applicable (–) is never listed.
- **ramp**: Population and Median age end at the 2nd and 98th percentile of the units at the level: "Percentiles rather than min/max: one Tokyo-sized outlier should not flatten the rest of the map into a single shade." How concentrated and Share of one group run 0–100%; a share map uses the group's own hue.
- **group**: ordered by units led, capped at 12, then `li.legend-more`, because "the tail of a group legend is groups that lead one district each, and a reader who needs those is reading the map, not the key." One grey ramp from 25% explains the shade for every group.
- **Fitted** (Shading: Fit to view): the group legend adds `<em class="legend-fitted">fitted to this view</em>` to the shade label and drops " or less" (`19%` / `100%`); a share ramp adds `p.legend-fitted-note`. It is called out because "a shade that means something different from one view to the next has to say so where the shade is explained."
- **Missing line**, whenever a unit has no figure: `No figure for {N} units` (group) or `No value for {N} units` (ramp), swatch `neutral`.
- **Unplaced line** (group only): `Group not yet classified in {N} units`, swatch `unplaced`, then an "i".
- **empty**: `<p class="control-note">No values at this level yet.</p>`.
- **Estimate line, stale.** With estimates on, a group or share map adds `div.legend-item.legend-estimate` with `.legend-swatch-hatched` and “Estimated, not published — hatched, 60 units”. Since 21 September 2026 the map draws an estimate exactly like a reading, so this keys a hatch that is no longer drawn. `legend-estimate` has no CSS.

## Content

- Status words are the palette's own, in sentence case: “Recorded”, “Derived from published figures”, “Estimated, not published”, “Not yet available”, “Not collected”.
- Counts are compact numbers with their noun: “No figure for 26.9K units”, “Group not yet classified in 1 unit”.
- Ends are formatted values: “1,739” and “257M”, “16.6 yrs” and “48.8 yrs”, “0%” and “100%”. A fitted end is the whole-number floor or ceiling of the shares in view.
- Scale labels: “Colour scale from {low} to {high}”; on the group map “Paler is a smaller share, darker is a larger one”.
- Known slips: one extra group reads “+1 more group lead somewhere”; a fitted share ramp can end at “101%”.

## Tokens

- Type: `text-legend` (rows), `text-meta` (ends), `text-reach` (counts, shade label, the italic more line), `text-fitted` (badge, note).
- Colour: `ink-secondary` (rows), `ink-muted` (ends, counts, shade label, more line, fitted), `border-ring` (swatch and scale edge), `hairline` (badge edge). Shape: `radius-swatch`, `radius-pill` (badge).
- Data: `status-present`, `status-derived`, `status-modelled`, `status-not-available`, `status-not-collected`, `sequential-0` … `sequential-10`, `leading-share-0` … `leading-share-4` (the shade ramp: the same five greys whether or not it is fitted), `neutral`, `unplaced`, `group-any` (the grey the shade ramp is computed from); `hatch-dark`, `hatch-light` (stale estimate key only).

## Accessibility

- The panel copy is `aria-live="polite"` and is rewritten on every repaint: each control pick, theme change, map move in Fit to view, and at most every 700 ms while data streams in.
- Each scale is `role="img"`, labelled with its ends or its direction; the stops are empty spans. Glyphs are `aria-hidden`; the words carry the state.
- Hue is never alone: status rows carry a glyph and words, group rows a name. "Every unit names its own group on hover, so nothing is unreachable."
- Ends, counts, shade label and fitted text are `ink-muted`: 3.5:1 on surface-1 and 3.4:1 on the on-map card in light, below 4.5:1 at 10.7–11px (4.9:1 in dark). Kept from the source.
- In light, `status-warning` (1.8:1) and `status-serious` (2.6:1) fail 3:1 against surface-1 as glyph or swatch; their words carry those rows. The `neutral` swatch is 1.4:1 by design and keeps its edge from `border-ring`.
- The unplaced line's "i" has no `aria-label`, so its accessible name is "i". It carries only `data-info-text`, so hover and focus open its bubble but a click closes it at once (app.js:327-329).

## In the app

- `renderLegend(legend)`, site/js/app.js:1020-1095, writes one HTML string to `#legend` and `#map-legend-body` (1093-1094); `estimateLegendHTML`, app.js:1007-1018. `refreshColors()`, app.js:1099-1121, calls it after each paint.
- The `legend` object comes from `Metrics.paint`, site/js/metrics.js:414-582 (`statusLegend` 584-593; `spanOf` 400-412 sets floor, ceiling and `fitted`).
- Computed at runtime: status rows `Palette.status(key).color` (the same in both themes); ramp stops `Palette.ramp()`, or `Palette.groupRamp(hue, 11, floor, top)` on a share map; group swatches `Palette.group(item.hue, item.peak)`, the group's hue at its highest share among the units it leads; the shade ramp `Palette.groupRamp("#6b6b6b", 5, floor, ceiling)`; `Palette.neutral()`; `Palette.unplaced()`. All but the status colours change with the theme: dark emits `#33332f` for the missing swatch and `#2e60a4` where light emits `#204272`.
- In the preview the slot colours are tokens, so they theme as the app does on a fresh load. The group swatches and the Islam share ramp have no token, so each is a frame-local property named after its light hex (`--shade-204272`), set on `:root` to the shade the app emits in light and under `[data-theme="dark"]` to the one it emits in dark: swatches `#204272` … `#edb998` and `#2e60a4` … `#ecb28d`, ramp `#bef0d3` … `#114d2a` and `#a0eabf` … `#196e3d`. They theme like the app too.
- The heading's "i" reads the view's note plus the sentence quoted above (app.js:1130-1136).

## Do / Don't

- Do order groups by units led: "A legend in alphabetical order, or in the index's order, buries the four colours that cover half the world under thirty that cover a district each."
- Do say a scale is fitted on the scale itself, with the badge or the note.
- Do take every colour from `Palette`, so the key matches the map in both themes.
- Don't draw "no value" in a status colour: "on a sequential map the status palette would read as a value at one end of the ramp."
- Don't add the hatched estimate line or `.legend-swatch-hatched` to new work.
- Don't scroll the group list or lift the 12-row cap.
