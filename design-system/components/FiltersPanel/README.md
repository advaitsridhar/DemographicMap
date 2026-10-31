# FiltersPanel

The left-hand panel that says what the map is shading and holds the controls that change it: a sticky head, the current filter as chips, then one titled section per control, the legend and the detail level.

## When to use

- Use one per map. It is the map's key as well as its controls: open on wide screens because "a first-time reader who never presses the button would otherwise be looking at coloured shapes with no key", closed on phones "because at that width it covers the map it describes" (app.js:126-129).
- Give each control its own `filter-section`, and show a section only in the views it applies to. The old panel kept a "Group" row in every view and quietly changed its label, "which meant the same control did two different jobs depending on a setting three rows up" (app.js:572-573).

## Anatomy

```html
<aside id="filters" class="filters" aria-label="Map filters" tabindex="-1">
  <div class="filters-head">
    <h2>What the map shows</h2>
    <button id="filters-close" class="ghost-button" type="button"
            aria-label="Hide the filters panel">✕</button>
  </div>
  <p id="filter-summary" class="filter-summary"><!-- FilterSummary --></p>

  <section class="filter-section" id="field-section" hidden>
    <h3 id="field-label">Topic
      <button type="button" class="info" data-info="topic"
              aria-label="About comparing topics across borders">i</button>
    </h3>
    <div id="field-options" class="segmented" role="radiogroup" aria-labelledby="field-label"></div>
  </section>

  <section class="filter-section">
    <h3 id="metric-label">View</h3>
    <div id="metric-options" class="option-list" role="radiogroup" aria-labelledby="metric-label"></div>
  </section>
  <!-- then Categories, Shading, Estimates, Group, Legend, Detail level -->
</aside>
```

Sections, top to bottom: Topic (SegmentedControl), View (OptionList), Categories and Shading (SegmentedControl), Estimates (CheckRow), Group (group picker), Legend, Detail level (OptionList).

## States and variants

| State | Set by | When the app sets it |
|---|---|---|
| Open | no `hidden` on the aside; `.filters-open` on `.app` | `setPanel(true)`: `wdm-filters` is `open`, or nothing is stored and the window is wider than 900px; also when a group is picked from search above 900px |
| Closed | `hidden` on the aside; `.app` drops `.filters-open` | the topbar toggle, the ✕, Escape inside the panel, or a click on a group row at 900px or less |
| Drawer | `@media (max-width: 900px)` | the panel turns `position: fixed` from `var(--topbar-h)` to the bottom, `min(var(--drawer-w), 90vw)` wide, with `shadow` at `z-drawer` |
| Section hidden | `hidden` on a `section.filter-section` | `syncSections()`, per view (below) |
| Focused | `.filters:focus-visible` | the skip link moves focus to the aside: 2px `accent` outline at -2px |

When the panel closes, the on-map legend opens with the same chips and key: "Hiding the controls is a request for more map, not for a map whose colours mean nothing" (app.js:177-178).

| View | Topic | Categories | Shading | Estimates | Group |
|---|---|---|---|---|---|
| Most populous group | yes | yes | yes | yes | – |
| Data coverage | yes | – | – | – | – |
| Population, Median age | – | – | – | – | – |
| How concentrated | yes | – | – | – | – |
| Share of one group | yes | – | yes | yes | yes |

View, Legend and Detail level are always shown.

## Content

- The head names the thing: "What the map shows". Section headings are one or two words typed in sentence case and uppercased by CSS: "Topic", "View", "Categories", "Shading", "Estimates", "Group", "Legend", "Detail level".
- The close button is the glyph ✕ with its words in `aria-label`: "Hide the filters panel". The topbar toggle's title reads "Hide the filter panel" / "Show the filter panel"; the two wordings have drifted, so pick one.
- Keep prose out of the panel. Every caveat goes behind its section's "i" (InfoButton); as paragraphs, "the effect was a filter panel that read as a document, where the controls were the things between the prose" (app.js:193-195).

## Tokens

`surface-1` (panel and sticky head), `hairline` (right rule, rule under the head), `ink-primary` (head), `ink-muted` (section headings), `accent` (focus ring), `gutter-panel`, `section-gap`, `filters-w`, `drawer-w`, `topbar-h`, `shadow`, `z-filters`, `z-drawer`, `z-sticky-head`. Type: `text-panel-heading` for `.filters-head h2`, `text-eyebrow` for `.filter-section > h3`.

The section headings are `ink-muted` at .68rem: 3.5:1 on `surface-1` in light, below the 4.5:1 that text this small needs (4.85:1 in dark). Kept from the source; flagged.

The legend's grey ramp is `leading-share-0` to `-4` and its "No figure" swatch is `neutral`. Its group swatches have no token: `Palette.group(hue, peak)` (app.js:1038) computes each for the theme on screen. The preview declares each as a frame-local property named after its light hex (`--shade-204272`), set to the light shade on `:root` and the dark one under `[data-theme="dark"]` (Christianity `#2e60a4`), so they theme like the app.

## Accessibility

- The aside is a complementary landmark named "Map filters". `tabindex="-1"` lets `<a class="skip-link" href="#filters">Skip to the filters</a>` move focus into it; keep `id="filters"` for that link and for the toggle's `aria-controls="filters"`.
- The topbar toggle carries `aria-expanded="true|false"`.
- ✕ and Escape (focus inside the panel, any width) close it and return focus to the toggle. Two gaps: opening the drawer leaves focus on the toggle, and the same Escape that closes an info bubble also closes the panel.
- Topic, View, Categories, Shading and Detail level are each a `role="radiogroup"` named by the section's `h3` through `aria-labelledby`; the group list is a `role="tree"` named the same way, and Estimates is a checkbox inside its `<label>`. A heading that holds an "i" lends the button's label to the group's name; measured in Chromium: "TOPIC About comparing topics across borders".

## In the app

- Markup: `site/index.html:48-128`. The consumer provides the sections and their controls, and the panel computes nothing itself; the drawer starts at `--topbar-h`, which `trackTopbarHeight` (app.js:136-143) measures from the topbar and writes on `<html>`.
- `setPanel` app.js:171-185 sets `hidden`, `.filters-open`, the toggle's `aria-expanded` and title, the on-map legend and `wdm-filters`. `panelDefault` app.js:145-151; the closing paths (group row, toggle, ✕, Escape) app.js:547-561; `syncSections` app.js:575-593.
- CSS: `site/css/app.css:186-204` (panel, head), 223-227 (sections), 591-595 (drawer), 670 (a heading with an "i").

## Do / Don't

Do:
- Keep the head sticky and the summary chips right under it, so the current filter is always one glance away.
- Hide a section that does not apply to the current view rather than disabling or relabelling it.
- Return focus to the toggle whenever the panel closes.

Don't:
- Don't put explanatory paragraphs between controls; use the heading's "i".
- Don't type section headings in capitals; `text-eyebrow` uppercases them.
- Don't put `.filters` on anything but the page's left column: below 900px the class makes it a fixed drawer.
