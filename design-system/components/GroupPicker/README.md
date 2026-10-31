# GroupPicker

A searchable tree of every group one topic names (religion, language or ethnicity), used to choose the single group that the Share of one group view shades on the map.

You provide the markup, one row per group (name, colour, reach counts, parent, number of children, depth), the count sentence and which row is chosen. The colour is precomputed per group; see In the app.

## When to use

- In the filters panel's Group section, only while the view needs a group (`metric.needsGroup`, the Share of one group view). The app sets `hidden` on the section otherwise.
- To choose one entry from a classification that is a tree and runs to thousands of names (religion 372 groups, language 2,673, ethnicity 2,610). For a few fixed choices use an option list or a segmented control.

## Anatomy

```html
<section class="filter-section">
  <h3 id="group-label">Group <button type="button" class="info" data-info="group" aria-label="About choosing a group">i</button></h3>
  <div class="group-search">
    <label class="visually-hidden" for="group-search">Search groups</label>
    <input id="group-search" type="search" autocomplete="off" spellcheck="false"
           placeholder="Search — “Islam”, “Muslim”, “te reo”…" aria-controls="group-list" aria-describedby="group-count">
  </div>
  <p id="group-count" class="control-note group-count" role="status" aria-live="polite">372 groups, widest reach first. 15 of them open to show what is inside.</p>
  <div id="group-list" class="group-list" role="tree" aria-labelledby="group-label">
    <div class="g-row" style="--g-depth:0"><button type="button" class="g-twist" data-branch="Abrahamic religions" aria-expanded="false" aria-label="Show the 7 groups inside Abrahamic religions" tabindex="-1">▸</button>
      <button type="button" role="treeitem" class="g-opt" data-value="Abrahamic religions" aria-selected="false" tabindex="0" aria-checked="true">
        <span class="g-swatch" style="background:#0072B2" aria-hidden="true"></span><span class="g-name">Abrahamic religions</span>
        <span class="g-reach">219 countries · 26.4K areas · 73 modelled</span>
      </button></div>
    <div role="group" aria-label="Residual answers: other, and not stated"><p class="group-divider"><strong>Residual answers</strong> <span>…</span></p> …rows… </div>
  </div>
</section>
```

- `.g-row` is a grid of the twist (1.1rem) and the choice. `--g-depth` indents the whole row .85rem a level: "Indenting the row rather than the button keeps the whole hit area aligned with its level".
- `.g-opt` lays out `.g-swatch` and `.g-name` on one line, `.g-reach` under the name, and `.g-parent` under that.
- `.group-list` scrolls past `min(46vh, 380px)` (`group-list-h`). The ids are the app's; keep each unique on the page.

## States and variants

- **Closed / open branch**: `.g-twist` with `aria-expanded="false"`, ▸ and "Show the {n} groups inside {name}", or `"true"`, ▾ and "Hide the {n} groups inside {name}". Only for a group with children on an unsearched row.
- **Leaf, or a search hit**: `<span class="g-twist g-twist-empty" aria-hidden="true"></span>` holds the column.
- **Search hit**: flat rows at depth 0, each with `<span class="g-parent">in Abrahamic religions</span>` when the group has a parent. The count reads "6 of 6 match “Islam”.", the query as typed.
- **Unplaced group** (no family yet): `class="g-swatch g-swatch-none"` with `title="Not yet placed in the classification"` and the `unplaced` colour inline.
- **Residual answers**: top-level residual rows go last inside `<div role="group" aria-label="Residual answers: other, and not stated">`, under a `.group-divider`.
- **Still on the map**: when the rows on show leave out the chosen group (a search, a closed branch or the 150-row cut), it is appended, flat, inside `<div role="group" aria-label="Still on the map">` with its own `.group-divider`. When a search matches nothing this block is the whole list and the count reads "0 of 0 match “zzzzqq”.".
- **Loading**: before `groups.json` lands, the list is `<p class="group-empty">Loading the worldwide group list…</p>` and the count is empty.
- **Chosen**: `aria-checked="true"` and `tabindex="0"`; every other row `aria-checked="false"`, `tabindex="-1"`. Known bug: nothing shows it. The rule is `.g-opt[aria-selected="true"]` (accent border, accent name), but `markChoice` writes `aria-checked` on a treeitem and the template's `aria-selected="false"` stays, so the chosen row looks like the rest.
- **Hover**: `surface-sunken` fill on `.g-opt` and on `.g-twist` (whose glyph turns `ink-primary`). **Focus**: 2px `accent` outline, at -1px on rows and twists and 1px on the search box.
- **Phone (≤640px)**: `.g-opt` padding .42rem .5rem, the input at 1rem so iOS does not zoom, the list at most 50vh.
- **Dead**: `.g-labels` (italic, one clipped line of source labels) is styled but nothing emits it. The no-match sentence `No {field} group matches “{query}”. Try a census's own word — “Muslim”, “te reo”, “Pardo”.`, with the count "0 groups", shows only while no group is chosen: in practice, a search typed before the list loaded. The first render with rows picks a group, and after that a search that matches nothing shows the Still on the map block instead.

## Content

- Group names are the classification's own: "Abrahamic religions", "Muslim/Jewish", "Not stated".
- Reach line: "{N} countries · {areas}" or "1 country · {areas}", where areas is "{n} area(s)" plus " · {n} modelled" when non-zero ("209 countries · 26.3K areas · 73 modelled", "52 countries · 6,319 areas", "1 country · 1 area"). Compact from 10,000 (26.4K), grouped below (6,319).
- Parent line: lower-case "in", then the parent's name.
- Count with no search: "{n} groups, widest reach first. {m} of them open to show what is inside.", where m counts groups that have children.
- Divider copy, verbatim: "Residual answers" / "“Other” and “not stated” are the absence of an answer, not a group anyone belongs to. They are here because leaving them out would hide people, and last because nobody is looking for them." and "Still on the map" / "Outside the list above, and shading the map until you pick something else."
- Order: residuals last, then by countries reporting, then units, then name. "How many countries report a group is what makes it comparable across a border, so that is the sort."
- At most 150 rows: "few enough that a field with 793 ethnicity groups does not build 793 nodes on every keystroke". In language the cut drops the Residual answers block.

## Tokens

`surface-1`, `surface-sunken`, `hairline`, `ink-primary`, `ink-secondary`, `ink-muted`, `accent`, `border-ring` (the dot's ring), `shadow-swatch-provisional`, `unplaced`, `radius-sm` (input, list), `radius-xs` (row), `radius-swatch` (twist), `radius-dot` (dot), `group-list-h`. Type: `text-control` (input), `text-group-name`, `text-reach`, `text-aside` (parent), `text-count` (divider name), `text-fine` (divider sentence), `text-note` (`.group-empty`), `text-control-note` (count), `text-twist` (the twist glyph, .7rem on a 1.9 line height).

## Accessibility

- `role="tree"` named by the heading through `aria-labelledby`, so the name absorbs the "i" button's label: Chrome computes "GROUP About choosing a group". Rows are `role="treeitem"`; divider blocks are `role="group"` with an `aria-label`.
- One tab stop, the chosen row. Arrow keys move and pick at once (the radio pattern, selection follows focus), Home and End jump, Enter and Space click. ArrowDown in the search box focuses the first row.
- Known bug: twists are `tabindex="-1"` and outside the arrow-key wiring, so a keyboard cannot open a branch; ArrowRight moves to the next row instead. Treeitems carry no `aria-level` or `aria-expanded`.
- The count is `role="status"`, `aria-live="polite"` and the input's description, so each search result count is announced. The dot is `aria-hidden`; the name carries the meaning.
- `ink-muted` reach, parent and count text is 3.5:1 on `surface-1` in light, below 4.5:1; the placeholder is 3.1:1 on `surface-sunken`.

## In the app

- Markup: `site/index.html:97-111`. Rows: `groupRowHTML`, `site/js/app.js:661-701`. List, dividers and count: `renderGroupList`, `app.js:703-780`. Which rows: `visibleRows`, `app.js:638-659` (`byReach` 618-623, `GROUP_LIMIT` 580).
- Search input `app.js:467-479`; twist click (capture phase, re-render, refocus the twist) `app.js:481-495`; pick `app.js:497-504`, which does not re-render the list, so a Still on the map block goes stale after a pick; on a click at ≤900px the drawer closes (`app.js:506-512`).
- `markChoice` `app.js:317-331`, `wireChoice` `app.js:333-356`. CSS: `site/css/app.css:277-355`, phone rules 579-581.
- Computed at runtime: the dot is `group.hue` from `site/data/groups.json`, written by `scripts/group_tree.py` (`TIER_HUE`, `FAMILY_HUE`) and painted flat only here; with no hue it is `Palette.unplaced()`, #a48fbb in light and #6b5980 in dark, read when the list is drawn and not redrawn on a theme switch. Counts come from `Fmt.number` (`site/js/data.js:296-299`).
- Colour in markup: a dot is the group's own hue exactly as `groups.json` spells it (upper-case hex for most groups). It is the same in both themes, so the markup keeps the hex; the tree's named hues are also tokens (`religion-islam` is #1e8449), but a group such as "Muslim/Jewish" (#1067bb) has none. The unplaced dot is written `var(--unplaced)`, which resolves to the hex the app writes on a fresh load in each theme.

## Do / Don't

- Do keep the twist a separate button beside the choice: "opening a branch and choosing it are two different intentions, and a reader who wants Christianity whole must not have to avoid the arrow."
- Do keep the chosen group in the list when a search hides it: "dropping it would colour the map by something the picker denied was selected."
- Do mark the chosen row with `aria-selected="true"` if it should look chosen; only that attribute reaches the selected style.
- Do name the parent on every search hit; a bare "Cushitic languages" says nothing about where it sits.
- Don't draw a group with no family in the neutral grey: "A grey dot in a list of coloured ones reads as "nothing here"".
- Don't open on, or sort in, a residual answer: "Never a residual".
- Don't let the dot carry meaning alone; it is `aria-hidden` and the name is the label.
