# EmptyState

What the place panel says before anything is chosen: how to pick a place, and the promise that every field will be a value or a marked gap. The same box reports a failed start.

## When to use

- In the place panel's body when no place is selected. It is the page's initial HTML.
- In the same body when the app cannot start, carrying the error.
- Not for a place with no figures. That place still gets its header, its gap notes and its sources.

## Anatomy

```html
<div class="empty-state">
  <h2>Pick a place</h2>
  <p>Click any country, state or district on the map, or search above. Zooming in
     swaps the map from countries to first-level divisions, then to second-level ones.</p>
  <p class="empty-note">Every field here is either a value with its source and year,
     or an explicit marker saying whether the data is <em>not yet gathered</em> or
     <em>not collected at all</em> by that country.</p>
</div>
```

- `h2`: the instruction.
- `p`: how to choose, and what zooming does.
- `p.empty-note`: the promise about gaps, smaller and in `ink-muted`.

## States and variants

- **Pick a place**: the static markup in `site/index.html:148–155`. Nothing brings it back once a place has been shown; closing the panel keeps the last place.
- **Could not start**: `<div class="empty-state"><h2>Could not start</h2><p>Error: admin0.json: HTTP 404</p></div>`. The paragraph is the escaped error, here a failed load of the country file. There is no `.empty-note`.

## Content

- Heading: a short instruction in sentence case, no full stop: "Pick a place".
- Lede: the two ways in, then what zoom does. "Click any country, state or district on the map, or search above."
- Note: the gap promise, with the two absences in italics: *not yet gathered*, *not collected at all*.
- Failure: "Could not start", then the error exactly as the app produced it. Do not rewrite it, soften it or apologise.

## Tokens

`text-empty-title` (h2, 1rem, bold), `text-lede` (p, .82rem, line-height 1.55), `text-subtitle` (`.empty-note`, .76rem; it keeps the lede's 1.55 line height from `.empty-state p`), `ink-primary`, `ink-secondary`, `ink-muted`. The box sits on `surface-1` inside `gutter-sidebar`.

Contrast: `.empty-note` is `ink-muted`, 3.5:1 on `surface-1` in light, below 4.5:1, and it carries the panel's key promise about gaps. In dark it measures 4.9:1.

## Accessibility

- The heading is an `h2`, the same level as a place's name (`.entity-name`), so the panel's outline is the same before and after a selection.
- Nothing is interactive or hidden. The panel around it (`aside`, "Selected place details") is the skip link's target.
- The failure replaces the panel's HTML with no live region, so it is not announced.

## In the app

- Markup: `site/index.html:148–155`, inside the place panel's body.
- Failure: the `catch` on `start()` in `site/js/app.js:1347–1351` sets the body to `<div class="empty-state"><h2>Could not start</h2><p>${esc(String(err))}</p></div>`.
- CSS: `site/css/app.css:447–449`. `.empty-note` needs `!important` to beat `.empty-state p`, which is more specific.
- You provide the copy. In the failure state the text is `String(err)`, escaped. No colour is computed.

## Do / Don't

Do:
- Show the gap promise from the first screen. It tells a reader that a blank will never be silent.
- Keep the error text verbatim, so a report of it can be searched.

Don't:
- Don't use it for a place with no data. Say why with a GapNote or a "Why this is empty" Note.
- Don't add a third paragraph or a button. The map and the search box are the ways in.
- Don't write "Oops", "Sorry" or an exclamation mark. The voice is plain.
