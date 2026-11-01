# AppShell

The page frame: a topbar over three columns (the filters panel, the map and the place panel), which at 900px and below becomes one full-width map with the filters as a drawer from the left and the place panel as a sheet from the bottom.

## When to use

- Once per page, as the root of the app. The topbar, filters panel, map and place panel go into its named grid areas; the About dialog sits outside it.
- Not as an embeddable block: `.app` is `height: 100vh` (`100dvh` where supported) and owns the window.

## Anatomy

```html
<a class="skip-link" href="#filters">Skip to the filters</a>
<a class="skip-link" href="#sidebar">Skip to the data panel</a>

<div class="app filters-open">
  <header class="topbar">…</header>                                         <!-- area: top -->
  <aside id="filters" class="filters" aria-label="Map filters" tabindex="-1">…</aside>  <!-- filters -->
  <main class="map-wrap">                                                    <!-- map -->
    <div class="map" role="application" aria-label="Map of world administrative divisions"></div>
    <div class="map-legend" aria-label="Map legend" hidden>…</div>
    <div class="map-status" role="status" aria-live="polite" hidden></div>
  </main>
  <aside id="sidebar" class="sidebar is-open" aria-label="Selected place details" tabindex="-1">  <!-- side -->
    <button class="ghost-button sidebar-close" type="button" aria-label="Close the details panel">✕</button>
    <div class="sidebar-body">…</div>
  </aside>
</div>

<dialog aria-labelledby="about-title">…</dialog>
```

- Grid: columns `0 1fr var(--sidebar-w)`, rows `auto 1fr`, areas `"top top top" "filters map side"`.
- `.map-wrap` is `position: relative; min-width: 0`; `.map` fills it (`inset: 0`) on `water`.
- `.sidebar` scrolls itself (`overflow-y: auto`) on `surface-1` with a `hairline` left rule; `.sidebar-body` pads it `1rem var(--gutter-sidebar) 3rem`.

## States and variants

The preview draws the desktop shell in a 1200 × 900 window: the topbar, the filters panel open on Most populous group, the map's water ground and Kerala in the place panel, each panel scrolling on its own. A card laid out 1200px wide never meets the 900px rules, so the drawer and the sheet are described below, not drawn. Its colours theme as the app's do: slot colours are tokens, and the legend's group swatches are frame-local `--shade-*` properties set to the shade `Palette.group` computes in each theme (see Legend).

- **Filters open** — `.app.filters-open` sets the first column to `var(--filters-w)` (330px). `setPanel(true)` adds it, removes `hidden` from `#filters`, hides the on-map legend and sets the toggle to `aria-expanded="true"`.
- **Filters closed** — no class: the column is zero-width and `#filters` is `hidden`; the on-map legend shows instead.
- **Default** — the stored choice (`localStorage` key `wdm-filters`, `open` or `closed`) wins; otherwise open when the window is wider than 900px.
- **Place shown** — `.sidebar.is-open`, added on every selection and removed by the sheet's ✕. Above 900px it changes nothing: the place panel is always on screen.
- **900px and below** — one column (`"top" "map"`).
  - `.filters` becomes a drawer: `position: fixed; inset: var(--topbar-h) auto 0 0; width: min(var(--drawer-w), 90vw)`, with `shadow` and `z-drawer`.
  - `.sidebar` becomes a bottom sheet: `height: min(62vh, var(--sheet-h))`, top rule, `radius` top corners, `shadow`. It waits at `translateY(100%)` with `pointer-events: none`, and `.is-open` slides it to `translateY(0)` with `transition: transform .22s ease`.
  - `.sidebar-close` shows.
  - In a window 760px wide the topbar wraps to 63px. With a place picked in a window 540px tall, the sheet covers the bottom 335px (62vh) of the map, its top corners rounded and its ✕ at the top right, the on-map legend under it; with the filters opened in a window 496px tall, the drawer runs 340px wide from under the topbar to the bottom edge, over the map.
- **640px and below** — the topbar collapses to glyphs (see Topbar).
- **Reduced motion** — `prefers-reduced-motion: reduce` sets every duration to `.001ms`.
- **`--topbar-h`** — 52px until measured; the app writes the topbar's rounded height on `<html>` and re-measures on resize: 54px from 767px up, 63px from 641px to 766px where the topbar labels wrap, 55px at 640px and below (measured in Chromium with the system font).

## Content

The frame holds no copy of its own. Landmark names, verbatim: "Map filters", "Selected place details", "Map of world administrative divisions"; the sheet's ✕ is "Close the details panel".

## Tokens

- Colour: `surface-2` (page), `surface-1` (panels), `hairline` (column rules, sheet top), `water` (map ground), `shadow` (drawer and sheet only).
- Size: `filters-w`, `sidebar-w`, `topbar-h`, `drawer-w`, `sheet-h`; radius `radius` (sheet corners).
- Spacing: `gutter-sidebar`.
- Z-index: `z-sidebar` 15 < `z-filters` 16 < `z-topbar` 20 < `z-drawer` 30 < `z-skip-link` 100.

## Accessibility

- Landmarks: `header` (banner), two `aside`s (complementary, each with an `aria-label`), `main`, and `role="search"` in the topbar. The map is `role="application"`.
- Both asides take `tabindex="-1"` so the skip links can move focus to them. `.filters:focus-visible` draws a 2px `accent` outline inset 2px; `.sidebar` has no rule and shows the browser's ring.
- Escape inside the filters panel closes it and returns focus to the toggle, at every width; the panel's ✕ does the same. Opening the drawer does not move focus into it.
- Nothing closes the sheet from the keyboard but its ✕, which is absolute inside the scrolling sheet and scrolls away with the content.

## In the app

- `start()` app.js:1354-1456 applies the theme, calls `trackTopbarHeight()` (app.js:136-143) and builds the controls.
- `setPanel(open)` app.js:171-185 toggles `.filters-open`, `#filters[hidden]`, the toggle's `aria-expanded` and `title`, the on-map legend, stores `wdm-filters` and calls `map.resize()`. `panelDefault()` app.js:145-151.
- Toggle, ✕ and Escape: app.js:648-657. A click on a group row closes the drawer at 900px and below (app.js:643-646).
- `selectEntity()` app.js:1237-1288 renders the place with `Dashboard.render(record, els.sidebarBody)` and adds `is-open` (app.js:1270); the sheet's ✕ removes it (app.js:1364).
- Runtime values: `--topbar-h`, both classes, the two `hidden` attributes. The place panel content is `dashboard.js`.
- Why the column stays: "The left column is zero-width rather than absent when the panel is hidden, so showing it is a column resize the map can follow rather than a reflow of the whole grid." (app.css:88-90)
- Why the default depends on width: "Wide screens get it open: it is the map's legend and its caveats … Phones get it closed, because at that width it covers the map it describes." (app.js:126-129)

## Do / Don't

- Do keep `id="filters"` and `id="sidebar"`: the skip links and the toggle's `aria-controls` point at them.
- Do call the map's `resize()` after changing the columns, as `setPanel` does.
- Do start anything fixed under the topbar at `var(--topbar-h)` and keep that value measured: "it has to start below the topbar or it covers the button that opened it" (app.js:131-132). The CSS comment that says the drawer "covers the topbar too" is out of date.
- Don't remove the filters column when the panel closes; set it to zero.
- Don't reset scroll on `.sidebar-body`: `.sidebar` is the element that scrolls.
- Don't use `.is-open` to show or hide the place panel above 900px: the class does nothing there.
