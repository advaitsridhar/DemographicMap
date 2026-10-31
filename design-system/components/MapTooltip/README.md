# MapTooltip

The hover readout over the map: the unit's name in bold and one muted line with the current view's reading for that unit, plus the country's name below country level.

You provide the name and the meta line. Both are computed per unit from the same metric functions that colour the map, so the readout and the shade cannot disagree.

## When to use

- On pointer hover over a unit of the level on screen, one readout at a time, removed when the pointer leaves the layer.
- For a glance, not for reading: the figures with their sources and years belong in the place panel, which a click opens.

## Anatomy

MapLibre's `Popup` builds the wrapper and positions it; the app supplies only the two spans inside.

```html
<div class="maplibregl-popup maplibregl-popup-anchor-bottom" style="max-width: 240px; transform: …">
  <div class="maplibregl-popup-tip"></div>
  <div class="maplibregl-popup-content"><span class="tip-name">Zhytomyr Oblast</span><span class="tip-meta">◼ Not collected — religion · Ukraine</span></div>
</div>
```

- `.maplibregl-popup-content` is the box: `surface-1`, a 1px `hairline` border, `radius-sm`, `shadow`, .5rem .65rem padding, .78rem type.
- `.tip-name` is a 600-weight block; `.tip-meta` is the muted inline line under it.
- `.maplibregl-popup-tip`, MapLibre's arrow, is `display: none`; the box floats 8px from the pointer with no arrow.
- MapLibre writes the anchor class, `max-width: 240px` and a `transform` that follows the pointer. Its stylesheet makes the wrapper absolute and shrink-to-fit, and the map container's `font:12px/20px Helvetica Neue,Arial,Helvetica,sans-serif` gives both lines a 20px line height. The app's classes draw the whole box without that stylesheet; outside MapLibre, set `line-height: 20px` on the container and let the wrapper shrink to fit.

The attribution is MapLibre's compact control, bottom right; the app sets only its size (.68rem):

```html
<details class="maplibregl-ctrl maplibregl-ctrl-attrib maplibregl-compact maplibregl-compact-show" open=""><summary class="maplibregl-ctrl-attrib-button" title="Toggle attribution" aria-label="Toggle attribution"></summary><div class="maplibregl-ctrl-attrib-inner"><a href="https://www.geoboundaries.org/" target="_blank" rel="noopener">geoBoundaries</a> CC BY 4.0 · <a href="https://www.cia.gov/the-world-factbook/" target="_blank" rel="noopener">CIA World Factbook</a> (public domain) · <a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener">Natural Earth</a></div></details>
```

Everything else about it is MapLibre's: a white pill, black text, links at 75% black, Helvetica Neue or Arial, the same in both themes, and an "i" toggle. Without MapLibre's stylesheet it falls back to a bare disclosure with browser-blue links, so it is not previewed.

## States and variants

| View | Meta line | Example |
| --- | --- | --- |
| Data coverage | {glyph} {status} — {topic in lower case} | ● Recorded — religion |
| Population | Population: {count} | Population: 9.5M |
| Median age | Median age: {age} yrs | Median age: 42.5 yrs |
| How concentrated | How concentrated: {share} | How concentrated: 48% |
| Most populous group | {group} {share} | Christianity 47% |
| Share of one group | Share of one group: {share} | Share of one group: 55% |

- **Below country level**: " · {country}" is appended ("◼ Not collected — religion · Ukraine", "Median age: 39.9 yrs · Ukraine").
- **No value**: "—" in Most populous group ("Ukraine" over "—"; "— · Ukraine" for a first-level unit); "{view}: no value" in the other numeric views.
- **Most populous group** adds " (no group named)" when the leading answer is a residual. In both group views an estimate adds its status in brackets, " (derived)" or " (modelled)".
- **Not loaded yet**: the meta reads "Loading", and the name falls back to the tile's own `shapeName`.
- **Anchor**: MapLibre picks the side that keeps the box on the map (`maplibregl-popup-anchor-bottom` over Belarus, `-right` and `-left` near the edges). A corner anchor (`-top-left`, `-top-right`, `-bottom-left`, `-bottom-right`) squares that corner of the box: MapLibre's `border-*-radius: 0` rule for it is more specific than the app's `radius-sm` (`site/vendor/maplibre-gl.css`).
- A share read alone is rounded: whole from 10% ("55%"), one decimal below ("6.9%"). An approximate share reads "about {share}", a range "{low}–{high}", and a bound keeps its sign.

## Content

- The unit's own name, as the record spells it ("Bourgogne-Franche-Comté").
- The view's name in sentence case and a colon, then the value with its unit; parts joined by a spaced middle dot. No full stop.
- Absence is an em dash or the words "no value", never 0. In Data coverage the status word always follows its glyph (● ▲ ◼); the popup itself adds no colour.

## Tokens

`surface-1`, `ink-primary` (name), `ink-muted` (meta), `hairline`, `radius-sm`, `shadow`, `--font-sans`. Type: `text-row` (.78rem, the box), `text-note` (.72rem, the meta line; its line height here is MapLibre's 20px), `text-meta` (.68rem, the attribution).

## Accessibility

- Pointer only. It is built on `mousemove`, so keyboard, touch and screen-reader users never get it; the place panel carries the same figures with their sources.
- The meta line in `ink-muted` is 3.5:1 on `surface-1` in light, below 4.5:1 at 11.5px, and 4.85:1 in dark. The name is 19.2:1 in light and 17.4:1 in dark.
- The popup has no close button and does not close on click; nothing in it is focusable.
- The attribution keeps MapLibre's white pill and black text in the dark theme.

## In the app

- `hoverHTML(id, properties)`, `site/js/app.js:1202-1235`, passed to the map as `onHover` (`app.js:1329`).
- The popup: `new window.maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 })`, `site/js/map.js:483`; filled with `setHTML` on `mousemove` over the active level's fill (`map.js:530-546`), removed on `mouseleave` (`map.js:547-552`).
- Attribution: the source's `attribution` string `map.js:324-326`, `attributionControl: { compact: true }` `map.js:476`.
- CSS: `site/css/app.css:430-439`. MapLibre's own: `site/vendor/maplibre-gl.css`.
- Computed at runtime: the value (`metric.evaluate`, `display` or `format` in `site/js/metrics.js`), the status glyph and label (`Palette.status`), the country name, and MapLibre's anchor and transform.

## Do / Don't

- Do read what the map painted: "The readout reads what the map painted, estimates included, and the display functions append the status word wherever that is what it is."
- Do append the country below country level, so a district can be placed.
- Do keep the glyph and the status word together in Data coverage.
- Don't put links or controls in the box; it follows the pointer and vanishes when the pointer leaves.
- Don't write a readout's value by hand. A share read alone goes through `Fmt.pct`, not the panel's one-decimal column format, "where "91%" is easier to take in than "90.9%" and the tenth adds nothing".
