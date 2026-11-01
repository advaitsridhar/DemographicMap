# OptionList

A vertical list of radio choices, one per row, each a name with a one-sentence hint under it that shows only on the chosen row and the row under the pointer; the filters panel uses it for View and Detail level.

## When to use

- For choices that are different things, each needing a sentence to say what it does: six maps under View, four levels under Detail level. "One choice per row, with room for the sentence that says what it does. The <select> this replaced had room for neither." (app.css:229-230)
- For two or three alternatives of one kind, use SegmentedControl. For one on/off choice, use CheckRow.

## Anatomy

```html
<section class="filter-section">
  <h3 id="metric-label">View</h3>
  <div id="metric-options" class="option-list" role="radiogroup" aria-labelledby="metric-label">
    <button type="button" role="radio" class="opt" data-value="coverage"
            aria-checked="true" tabindex="0">
      <span class="opt-name">Data coverage</span><span class="opt-hint">Where a figure exists — and whether a gap is unfetched or never collected.</span></button>
    <button type="button" role="radio" class="opt" data-value="population"
            aria-checked="false" tabindex="-1">
      <span class="opt-name">Population</span><span class="opt-hint">Latest published count, on a log scale.</span></button>
  </div>
</section>
```

## States and variants

| State | Set by | Look |
|---|---|---|
| Not chosen | `aria-checked="false"`, `tabindex="-1"` | name only, `ink-secondary`, no fill |
| Hover | `:hover` | `surface-sunken` fill; the hint appears |
| Focus | `:focus-visible` | 2px `accent` outline at 1px; the hint appears |
| Chosen | `aria-checked="true"`, `tabindex="0"` | `surface-sunken` fill, 1px `accent` border, name in `accent`, hint shown |
| Phone | `@media (max-width: 640px)` | padding `.5rem .55rem` instead of `.4rem .5rem` |

Hints stay hidden on the other rows: "Six of them at once ran the list to 300px and pushed the legend -- the thing that says what the colours mean -- below the fold on a laptop. Hovering brings a hint back for the option under the pointer, so the list is still browsable without choosing." (app.css:250-253)

View starts on Data coverage and Detail level on Follow zoom. Neither choice is kept in the URL or in storage.

## Content

- **Name**: a short noun phrase in sentence case: "Most populous group", "How concentrated", "Follow zoom", "First-level divisions".
- **Hint**: one sentence, present tense, ending in a full stop, saying what the choice draws or does: "One colour per group, darker where its share is larger." "Latest published count, on a log scale." "One shade per country at every zoom."
- Add a second sentence only for a cost or side effect: "Districts and counties. Pinning this loads every country's shard."
- Use the em dash for a gloss: "States, provinces, regions — wherever they are tiled."

## Tokens

`surface-sunken`, `accent`, `ink-primary`, `ink-secondary`, `ink-muted` (hint), `radius-sm`. Type: `text-option` for `.opt-name` (.82rem, 600), `text-hint` for `.opt-hint` (.69rem, line height 1.4).

The chosen name is `accent` on `surface-sunken`: 3.8:1 in light, 4.3:1 in dark. The hint is `ink-muted` on `surface-sunken`: 3.1:1 in light, 4.4:1 in dark. Both are below 4.5:1 at these sizes; kept from the source, flagged. The `accent` border clears 3:1 in both themes.

## Accessibility

- The list is a `role="radiogroup"` named by its section `h3` through `aria-labelledby`; each row is a `<button role="radio">` with `aria-checked`.
- One tab stop: the chosen row has `tabindex="0"`, the others `-1`; if nothing is chosen the first row takes `0`, "or the whole control drops out of the keyboard order" (app.js:436-437).
- Arrow Down or Right moves to the next row and chooses it, wrapping; Up or Left goes back; Home and End jump to the ends; Enter and Space press the button. "a single tab stop, arrows to move, and moving selects. That is the WAI-ARIA radio pattern" (app.js:414-415).
- The hint sits inside the button, so it joins the accessible name wherever it is displayed: the chosen, hovered or focused row.

## In the app

- `optionHTML(role, cls, value, label, hint)` app.js:466-472 writes each row; `markChoice(host, value)` app.js:425-439 sets `aria-checked` and `tabindex`; `wireChoice(host, onPick)` app.js:441-464 handles clicks and keys.
- View: one row per entry of `window.Metrics.METRICS` (`label`, `hint`; metrics.js:270-373), built at app.js:513-522. Picking one runs `syncSections()` and `refreshColors()`.
- Detail level: `DETAIL_LEVELS` app.js:505-510, built at app.js:567-573. Picking one calls `WorldMap.setPinnedLevel`, with `null` for "auto".
- The consumer provides each row's value, name and hint, and the chosen value. No colour is computed.
- CSS: `site/css/app.css:229-258`; phone padding `app.css:578`.

## Do / Don't

Do:
- Write every hint for the moment its row is chosen.
- Keep exactly one row chosen.
- Name the cost of a heavy choice in its hint.

Don't:
- Don't show every hint at once.
- Don't use it for two or three alternatives of one kind; use SegmentedControl.
- Don't put a caveat in a hint. View and Detail level have no "i" of their own; the app puts each view's caveat behind the Legend's "i" instead (app.js:1196-1206).
