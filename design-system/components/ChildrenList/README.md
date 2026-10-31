# ChildrenList

The ranked list of a place's divisions one level down: each row is a button that opens that division, with its population on the right.

## When to use

- Under a country ("First-level divisions") or a first-level division ("Second-level divisions") in the place panel.
- Only once the level below has loaded. Until then leave the section out rather than drawing it empty.
- Not under a second-level division: it has no children in this map, so render nothing.
- Not for groups or anything else that is not a place.

## Anatomy

```html
<section class="panel"><div class="panel-head"><h3>Second-level divisions</h3>
  <span class="panel-year">14</span></div>
  <ul class="children-list">
    <li><button type="button" data-goto="76128533B83861010847920">
      <span>Malappuram</span>
      <span class="c-count">4.1M</span></button></li>
  </ul></section>
```

- `.children-list`: the list. It scrolls inside `children-h` (260px), about ten rows.
- `button[data-goto]`: one division. `data-goto` holds the division's id.
- The first `<span>`: the name. `.c-count`: the population, pushed right with `margin-left: auto`.
- The heading row is PanelSection. Here `.panel-year` holds the number of divisions, not a year.

## States and variants

- **Rest**: name in `ink-secondary`, count in `ink-muted`, no fill.
- **Hover** (`:hover`): the row fills `surface-sunken` and the name turns `ink-primary`. There is no selected state: choosing a row replaces the whole panel.
- **No count** (`.c-count` left empty): the app writes `pop ? number(pop) : ""`, so a population that is missing, not applicable or zero leaves the cell blank. Antarctica's one division shows this.
- **Long list**: rows past about ten scroll inside the list. The heading counts every division, but only the first 400 rows are rendered.
- **Heading**: "First-level divisions" when the place is a country (`level` is `admin0`), otherwise "Second-level divisions".

## Content

- Order rows by population, largest first, then by name (`localeCompare`).
- Print names as the record has them, escaped: "Île-de-France", "Provence-Alpes-Côte d'Azur".
- Print counts with `Fmt.number`: compact from 10,000 ("4.1M", "817.4K", "2M", "362.3K"), grouped below that.
- The heading count is the bare number: "14", "13", "1".
- A count carries no year or source. Those are on the division's own panel, one click away.

## Tokens

`text-row` (the row, .78rem), `text-count` (`.c-count`, .7rem, tabular figures), `ink-secondary`, `ink-primary`, `ink-muted`, `surface-sunken`, `radius-sm`, `children-h`. The list sits on `surface-1` inside `gutter-sidebar`.

Contrast: the `ink-muted` counts measure 3.5:1 on `surface-1` and 3.1:1 on the hover fill in light, below 4.5:1. In dark they pass on `surface-1` (4.9:1).

## Accessibility

- Each row is a real `<button type="button">`. Its accessible name is the place's name followed by its count.
- There is no `:focus-visible` rule for these buttons. Keyboard focus shows the browser's default ring, not the 2px `accent` outline the other controls use. Give it the house outline when you reuse the list.
- Tabbing moves through the rows and scrolls the list to keep the focused row in view.
- Nothing is `aria-hidden`.

## In the app

- `childrenPanel(record)`, `site/js/dashboard.js:477–492`: `DataStore.children(record.id)` filtered to a different level, sorted, first 400 rendered.
- `render()` wires every `[data-goto]` button (`dashboard.js:556–558`) to the navigator set in `site/js/app.js:1263–1266`, which calls `selectEntity(id, { fly: true, bbox: record && record.bbox })`. The map flies there and the panel re-renders.
- The list appears when the level below arrives: `afterLoad` re-renders the panel (`app.js:1194–1198`; the loads start at 1183 and 1185).
- CSS: `site/css/app.css:526–534`.
- You provide each child's id, name and population, the formatted count, and the total for the heading. No colour is computed.

## Do / Don't

Do:
- Keep counts right-aligned in tabular figures, so magnitudes line up down the column.
- Put the number of divisions in the heading, so a scrolled list still says how long it is.
- Sort by population, so the list reads as a ranking.

Don't:
- Don't copy the blank count into new work. It makes zero, not applicable and not yet available look alike, and the brand book says "never leave a field blank". Say which absence it is.
- Don't style a row as selected. The list navigates; it does not hold a choice.
- Don't truncate names or add a second line under them. The count is the row's only figure.
