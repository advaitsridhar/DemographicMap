# StatusChip

A 12px square in a status colour that marks one of the three data states in a written key; the state's name follows it in bold, then one sentence saying what the state means.

## When to use

- In prose that explains the three states: the About dialog's “Gaps are data too” list (`ul.gap-key`) is the only place the app uses it.
- Not on the map or in the legend: the legend keys states with a `.legend-item` (glyph, swatch, words). Not in the place panel: there a gap is a gap note or a fact tile that leads with the status glyph and its words (“▲ Not yet available”).
- The chip's colour alone is never the signal. The word follows it, every time.

## Anatomy

```html
<ul class="gap-key">
  <li><span class="chip chip-present"></span><strong>Present</strong> — a value with a named source and reference year.</li>
  <li><span class="chip chip-missing"></span><strong>Not yet available</strong> — the figure exists somewhere but this build has not fetched it.</li>
  <li><span class="chip chip-notcollected"></span><strong>Not collected</strong> — the country does not gather it at all. …</li>
</ul>
```

The chip is an empty `span`: `display: inline-block`, 12px square, `margin-right: .4rem`, `vertical-align: -1px`. The line's type and colour come from the dialog (`dialog li`). You provide the markup and the words; the fill comes from the class.

## States and variants

| Class | Fill | State | Name in the About key |
| --- | --- | --- | --- |
| `.chip-present` | `status-good` (#0ca30c) | Recorded | “Present” |
| `.chip-missing` | `status-warning` (#fab219) | Not yet available | “Not yet available” |
| `.chip-notcollected` | `status-serious` (#ec835a) | Not collected | “Not collected” |

The three are written into the page; no script sets or changes them. The fills are the same in both themes. There is no chip for the estimate states (Derived, Modelled) or for Not applicable.

## Content

- Pattern: the chip, the state's name in `<strong>`, a spaced em dash, then one sentence in lower case that says what the state is. The last state adds why, by country: “France records neither ethnicity nor religion (barred by law); Germany records citizenship and migration background rather than ethnicity; Japan's census asks neither; …”
- Name drift: the About key calls the first state “Present”. The legend, the map popup (“● Recorded — religion”) and `Palette.STATUS.present` call it “Recorded”, and so does the brand book. Use “Recorded” in new work.
- Name the absence precisely: “the figure exists somewhere but this build has not fetched it” is a different fact from “the country does not gather it at all”.

## Tokens

- Fill: `status-good`, `status-warning`, `status-serious` (aliases `status-present`, `status-not-available`, `status-not-collected`).
- Edge and shape: `border-ring` (1px), `radius-swatch` (3px).
- The line: `text-dialog-body` in `ink-secondary` on `surface-1`; the name is bold.

## Accessibility

- The chip has no text, role or label, so assistive technology skips it and reads the name and sentence. It needs no label: the word after it is its name.
- It carries no glyph, unlike the legend's ● ▲ ◼, so the word is the only non-colour channel. Keep it.
- As a graphic against `surface-1` in light, `status-warning` measures 1.8:1 and `status-serious` 2.6:1, below the 3:1 minimum; `status-good` is 3.3:1. In dark they measure 9.5:1, 6.6:1 and 5.2:1. The `border-ring` edge keeps the square's outline, and the word carries the state.
- Not interactive: no focus, no hover.

## In the app

- Markup: site/index.html:176-179, in the About dialog (`#about-dialog`, index.html:160-201) under “Gaps are data too”. The dialog opens from “About & sources” (`showModal()`, site/js/app.js:1365).
- Styles: `.chip`, `.chip-present`, `.chip-missing`, `.chip-notcollected` in components/bundle.css (site/css/app.css:521-524); `.gap-key` (app.css:559-560) lays the lines out as a grid .4rem apart.
- Nothing is computed at runtime: the fills are the status tokens, the same values `Palette.STATUS` paints on the coverage map.

## Do / Don't

- Do follow every chip with the state's name and one sentence.
- Do keep each class to its state; the status colours mean these three states and nothing else.
- Don't use a chip without its word, as a bullet, or as a swatch for a group or a value.
- Don't confuse it with `.chip-basis` (the basis chip) or `.fchip` (filter chips): those are text pills, not colour keys.
