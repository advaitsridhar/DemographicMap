# Search

The topbar's one search box: a combobox that finds places (countries, first- and second-level divisions) and groups (religions, languages, ethnicities) and lists them in a floating list under the box.

## When to use

- To go to a named place, or to shade the map by a named group, from anywhere in the app. It is the only place search; the filters panel's group search only filters its own list.

## Anatomy

```html
<div class="search" role="search">
  <label class="visually-hidden" for="search-input">Search for a country, state or district</label>
  <input id="search-input" type="search" autocomplete="off" spellcheck="false"
         placeholder="Search places and groups — “Kerala”, “Islam”, “Tamil”, “Harris County”"
         aria-describedby="search-status" aria-expanded="false" aria-controls="search-results"
         role="combobox" aria-autocomplete="list">
  <ul id="search-results" class="search-results" role="listbox" aria-label="Search results" hidden>
    <li role="option" id="sr-1" aria-selected="false" data-group="religion|Indian religions">
      <span class="r-level r-group">Religion</span>
      <span class="r-name">Indian religions</span>
      <span class="r-context">Shade the map · 79 countries</span>
    </li>
    <li role="option" id="sr-3" aria-selected="false" data-id="IND">
      <span class="r-level">Country</span>
      <span class="r-name">India</span>
      <span class="r-context"></span>
    </li>
  </ul>
  <p id="search-status" class="visually-hidden" role="status" aria-live="polite"></p>
</div>
```

- The list is `position: absolute`, `6px` under the box and as wide as it, so it floats over the panels and the map. It is at most `min(60vh, var(--results-h))` tall and scrolls.
- A row is a baseline flex row: chip, name, then the context pushed right with `margin-left: auto`.

## States and variants

- **Closed** — `ul[hidden]`, input `aria-expanded="false"`. It closes on Escape, on a pick (which writes the row's name into the box), and on a click outside `.search`.
- **Open** — the list repaints on every keystroke, and on focus when the box already holds two or more characters; `aria-expanded="true"`. The box has focus while the list is open, so it shows the focus ring and, in Chromium, the browser's own clear button (✕) at its right end. app.css does not style that button, and a static card cannot show it, so the preview draws only the ring.
- **Group row** — `data-group` holds the field and the name (`religion|Indian religions`); chip `r-level r-group` on `accent`. Picking it switches the view to "Share of one group" for that group, opens the filters panel above 900px, and leaves the map where it is. At most three, always first.
- **Place row** — `data-id`, neutral chip `r-level` reading "Country", "Admin 1" or "Admin 2". Up to twelve, countries and first-level units ahead of districts with the same score.
- **Active row** — `aria-selected="true"`, moved by ArrowDown and ArrowUp (wrapping); it takes the hover fill, `surface-sunken`. On that fill the neutral chip keeps only its `hairline` edge.
- **Empty** — one `li.r-empty` (`role="option"`, `aria-disabled="true"`): "Type at least two letters", "No match yet — still loading second-level divisions" while the district index is still arriving, then "No match".

## Content

- The placeholder names both kinds, with examples in curly quotes after an em dash: "Search places and groups — “Kerala”, “Islam”, “Tamil”, “Harris County”".
- Chips are typed in sentence case and set in capitals by CSS: "Country", "Admin 1", "Admin 2"; "Religion", "Language", "Ethnicity".
- A group row says what picking it does and how far it reaches: "Shade the map · 1 country", "Shade the map · 79 countries". When several census labels fold into one group they follow, comma-separated, after another " · ". "Say what picking it does and how far it reaches, because "Islam" in a box that has only ever returned places reads as a place." (search.js:155-156)
- A place row's context is parent and country: "Paphos · Cyprus", "Guinea"; empty for a country.
- The status line reads "15 results", "1 result" or "No results".

## Tokens

- Input: `surface-sunken`, `hairline`, `radius`, `ink-primary`, `text-search` (.875rem; 1rem at 640px and below).
- List: `surface-1`, `hairline`, `radius`, `shadow`, `results-h`, `z-search-results`; rows `radius-sm`, `text-result` (.85rem, name 600), hover and active `surface-sunken`.
- Chips: `text-level-chip` (.65rem, capitals, .04em), `radius-pill`; neutral `ink-secondary` on `surface-sunken`; group `accent-ink` on `accent`.
- Context and empty text: `ink-muted`. The context line is `text-context` (.75rem); the empty message keeps the row's `text-result`.
- Contrast: the group chip is 4.4:1 in light and 3.6:1 in dark at .65rem regular weight; the context line is 3.5:1 on `surface-1` and 3.1:1 on the active row in light. Both are below 4.5:1.

## Accessibility

- `role="combobox"`, `aria-autocomplete="list"`, `aria-controls` naming the list and `aria-expanded` kept in step. The box has no visible label: the `<label>` is visually hidden and the placeholder stands in for it.
- The count is spoken through the `role="status"` paragraph, which is also the input's `aria-describedby`.
- Keys: ArrowDown and ArrowUp move the active row and scroll it into view; Enter picks it, or the first row; Escape closes the list and blurs the box. A `mousedown` on a row picks it.
- Gaps to know: the input never sets `aria-activedescendant`, so the active row is not announced while arrowing; and "No match" is a disabled `option`.
- There is no `::placeholder` rule, so the placeholder is the browser's grey (#757575 in Chromium: 4.0:1 on `surface-sunken` in light, 3.4:1 in dark).
- Focus: a 2px `accent` outline offset 1px on the input.

## In the app

- `attach(input, list)` search.js:134-226 wires the box; `paint(results)` search.js:145-187 writes the rows, the empty message and the status.
- `query(text, limit)` search.js:111-122 searches names with MiniSearch (prefix, fuzzy 0.2); `queryGroups(text, limit)` search.js:78-109 scans the group index and every census label, so "muslim" finds Islam.
- app.js:1434-1441 starts it: a group row calls `applyGroupFilter`, a place row calls `selectEntity` and flies there.
- Runtime values: the rows, their counts and contexts, the active row and the status text. Nothing is coloured inline.

## Do / Don't

- Do lead with group rows and cap them at three: "Tamil" is a language and a place, and "burying Nadu under a list of group matches would be its own kind of wrong." (search.js:118-120)
- Do keep the accent chip for rows that shade the map: "it shades the map instead of moving it -- so its chip is the accent colour rather than the neutral one" (app.css:162-164).
- Don't drop the hidden label or the status paragraph: they are the box's name and its count.
- Don't put anything a reader must read in the context line; `ink-muted` is for hints.
