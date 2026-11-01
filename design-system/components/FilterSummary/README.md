# FilterSummary

A row of small chips naming what the map is shading right now (the view, the topic, the category width, the chosen group and the detail level), shown under the filters panel head and repeated on the map while the panel is hidden.

## When to use

- Always, in two places: directly under `.filters-head`, and at the top of the on-map legend when the panel is closed. "It is repeated outside the panel on purpose: the panel can be hidden, and a map shaded by "the Sikhism share of religion, second-level divisions only" says nothing without that line." (app.js:936-938)
- It reports the filter; it does not change it. Chips are `<span>`s, not buttons.

## Anatomy

```html
<p id="filter-summary" class="filter-summary"><span class="fchip">Share of one group</span><span class="fchip">Religion</span><span class="fchip fchip-key">Islam</span><span class="fchip">Detail follows zoom</span></p>

<!-- the on-map copy: same chips, first child of the legend card -->
<div id="map-legend" class="map-legend" aria-label="Map legend">
  <p id="map-legend-summary" class="filter-summary">…</p>
  …
</div>
```

The chips sit back to back with no whitespace or separators between them; `gap: .3rem` spaces them and `flex-wrap` breaks the row.

## States and variants

- **Order.** The view; the topic, when the view needs one; the category width, when it needs one; the chosen group, on Share of one group once a group is picked; the detail level, always last.
- **Neutral chip** `.fchip`: `ink-secondary` on `surface-sunken`, `hairline` edge, pill.
- **Key chip** `.fchip fchip-key`: the group being shaded, `accent-ink` on `accent`, weight 600. Only the group chip is ever keyed, the same accent the group chip takes in search results.
- **Detail chip**: "Detail follows zoom" until a level is pinned in Detail level, then "Countries only", "First-level only" or "Second-level only".
- **In the panel** `.filter-summary`: `margin: .6rem 0 0`, under the head's rule.
- **On the map** `.map-legend .filter-summary`: `margin: 0 0 .45rem`, above the key.

## Content

Each chip repeats a control's own label, so it can be traced to the control that set it:

- View: "Most populous group", "Data coverage", "Population", "Median age", "How concentrated", "Share of one group".
- Topic: "Religion", "Language", "Ethnicity".
- Category width: "Traditions", "Religions", "As reported" (religion); "Families", "Branches", "As reported" (language); "Ancestry", "Peoples", "As reported" (ethnicity).
- Group: the name as the group index spells it, for example "Islam", "Abrahamic religions".

Chip sets as the app writes them: `Population` `Detail follows zoom`; `Data coverage` `Religion` `Detail follows zoom`; `Most populous group` `Religion` `Religions` `First-level only`; `Share of one group` `Religion` `Abrahamic religions` (key) `Detail follows zoom`.

## Tokens

`surface-sunken`, `ink-secondary`, `hairline`, `radius-pill`, `accent`, `accent-ink`. Type: `text-chip` (.68rem, line height 1.5; the key chip at 600).

Neutral chips read 6.9:1 in light and 8.8:1 in dark. The key chip is `accent-ink` on `accent`: 4.4:1 in light and 3.6:1 in dark at .68rem, below 4.5:1. Kept from the source; flagged.

## Accessibility

- A `<p>` of `<span>`s reads as one run of words in chip order. Every chip is a word, so the key chip's fill is never the only signal: it is the one chip that names a group.
- The summary is not a live region, so a change of filter is not announced from it. Only the panel's legend, `#legend`, is `aria-live="polite"` (index.html:118); the on-map copy, `#map-legend-body`, is not live (index.html:138).
- On the map, `aria-label="Map legend"` sits on a role-less `div` and is not exposed (measured role: none).

## In the app

- `renderSummary()` app.js:940-964 builds the chips from state (view, field, depth, group, pinned level) and writes the same HTML to `#filter-summary` and `#map-legend-summary`. It also writes the view's blank note to `#blank-note` and `#map-legend-note`.
- It runs on every change of view, topic, category width, group and detail level (app.js:605, 652, 703, 1434, and from `renderGroupList` at 863, 882 and 929), so the chips never lag the map.
- The consumer provides the chip words (the controls' labels and the group name) and which chip, if any, is the key. Nothing is computed for colour.
- CSS: `site/css/app.css:206-221`; on the map, `app.css:383`.

## Do / Don't

Do:
- Write both copies from one function, so the panel and the map never disagree.
- Use each control's exact label, in sentence case.
- Key the chip that names the group being shaded, and only that one.

Don't:
- Don't make chips clickable or give them a ✕; the controls change the filter.
- Don't add separators or punctuation between chips.
- Don't key the view or the topic: the accent fill is reserved for the group the map is shading.
