# CheckRow

A single on/off choice laid out like an option row (a checkbox, its name, and a sentence under the name); the filters panel uses it for "Show estimates".

## When to use

- For one independent on/off choice that sits among option rows. "A single on/off choice, laid out like the option rows around it so the panel keeps one rhythm: the name on the first line, the sentence under it." (app.css:410-411)
- For one of several alternatives, use OptionList or SegmentedControl.

## Anatomy

```html
<section class="filter-section" id="estimates-section" hidden>
  <h3 id="estimates-label">Estimates
    <button type="button" class="info" data-info="estimates"
            aria-label="About estimated units">i</button>
  </h3>
  <label class="check-row" for="estimates-toggle">
    <input id="estimates-toggle" type="checkbox" checked>
    <span class="check-name">Show estimates</span>
    <span class="check-hint">Hatched, in the colour the estimate gives. Off, they are gaps.</span>
  </label>
</section>
```

The label wraps the input and both spans, so the whole row is the hit area. The grid puts the box in the first column and the name and hint in the second.

## States and variants

| State | Set by | When, and how it looks |
|---|---|---|
| On | `checked` | at start, unless `localStorage["wdm-estimates"]` is `off`; also when storage cannot be read. The box is filled in `accent` |
| Off | not checked | after the reader unticks; stored as `off`. An empty box |
| Hover | `.check-row:hover` | `surface-sunken` fill on the whole row |
| Focus | `.check-row input:focus-visible` | 2px `accent` outline at 1px around the box |

The Estimates section shows only on Most populous group and Share of one group: "those are the two maps that can read an estimate's rows" (app.js:694-695).

## Content

- **Name**: what ticking does, as a verb phrase: "Show estimates".
- **Hint**: what each state draws, in one or two short sentences.
- The app's hint is stale. "Hatched, in the colour the estimate gives. Off, they are gaps." describes a map that no longer exists: "An estimate is drawn exactly like a reading, by the owner's decision of 21 September 2026" (map.js:229-230). The section's own "i" already says the new rule: "Their colour is what the estimate says, drawn like any other" (app.js:234-235). Drop "Hatched" and say only what on and off draw. The legend's estimate line still says "hatched" for the same reason (app.js:1127).

## Tokens

`surface-sunken` (hover), `radius-sm`, `accent` (the box's `accent-color`, focus ring), `ink-primary` (name), `ink-secondary` (row), `ink-muted` (hint). Type: `text-option` for `.check-name` (.82rem, 600), `text-hint` for `.check-hint` (.69rem, line height 1.4).

The hint is `ink-muted`: 3.5:1 on `surface-1` and 3.1:1 on the hover fill in light, and 4.4:1 on the hover fill in dark, all below 4.5:1. Only dark at rest passes, at 4.85:1 on `surface-1`. Kept from the source; flagged.

## Accessibility

- A native checkbox inside its `<label>`: Tab reaches the box, Space toggles it, and a click anywhere on the row toggles it.
- Because the label holds both spans, the hint is part of the accessible name; measured: "Show estimates Hatched, in the colour the estimate gives. Off, they are gaps." Keep the hint short.
- `accent-color: var(--accent)` colours the native box; the dark theme's `color-scheme: dark` gives it a dark ground.

## In the app

- Static markup at `site/index.html:85-95`. app.js sets the box's `checked` property from state (app.js:596) and listens for `change` (app.js:597-599).
- `estimatesDefault()` app.js:158-164 reads the stored choice; `setEstimates(on)` app.js:166-173 stores `wdm-estimates` as `on` or `off` and repaints the map.
- `syncSections()` hides the section on every other view (app.js:693-697).
- The consumer provides the name, the hint and the starting state. No colour is computed.
- CSS: `site/css/app.css:410-421`.

## Do / Don't

Do:
- Name the row with a verb phrase that says what ticking does.
- Wrap the input and both spans in one label.
- Remember the reader's choice, and start on when storage is unavailable.

Don't:
- Don't copy the "Hatched" hint into new work; the map stopped hatching estimates.
- Don't use a check row for one of several alternatives.
- Don't put the caveat in the hint; it belongs behind the section's "i".
