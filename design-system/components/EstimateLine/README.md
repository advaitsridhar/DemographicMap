# EstimateLine

The line at the top of an estimated composition: a badge saying "Modelled" or "Derived" in the estimate's status colour, then the first sentence of the note, which says what the figure is.

## When to use

- In a composition section whose value is an estimate with usable rows (status `modelled` or `derived`), between the heading and the bar.
- Only there. An estimate is drawn exactly like a reading in the bar, the list and on the map, so this line is where the caveat lives.
- Not for an estimate with no rows: it renders as a GapNote.

## Anatomy

```html
<p class="basis-line estimate-line"><span class="chip-basis chip-estimate" style="color:var(--status-modelled);border-color:var(--status-modelled)" title="Estimated, not published">◌ Modelled</span> <span class="estimate-why">No language figure for Bushehr itself has been found.</span></p>
```

The app writes the badge's colour as the hex `Palette.status()` returns (`#9b72cf` here); write the status token, as above.

- `p.basis-line.estimate-line`: one flex row, baseline-aligned, the badge and the sentence .45rem apart. The bar follows with no space between.
- `.chip-basis.chip-estimate`: the badge. The BasisChip pill on a transparent ground, its text and edge set inline to the status colour, holding the status glyph and one word.
- `.estimate-why`: the note's first sentence. It has no rule of its own and takes the line's `ink-secondary`.

## States and variants

| Variant | Status | Badge | Inline colour | `title` |
| --- | --- | --- | --- | --- |
| Modelled | `modelled` | ◌ Modelled | `#9b72cf` (`status-modelled`) | Estimated, not published |
| Derived | `derived` | ◐ Derived | `#4f9c8c` (`status-derived`) | Derived from published figures |

- The sentence ends at the first ".", "!" or "?" followed by a space or the end. Past 220 characters it keeps 217 and adds "…".
- With no note, `.estimate-why` is empty and the badge stands alone.
- The section's year is the estimate's own (`census_year`, else `year`), else the record's year for that field: Bushehr shows 2017, and Transnistria, which has neither, shows none.

## Content

- The badge words are fixed: "Modelled" and "Derived".
- The sentence says what the figure is, not how it was made: "No language figure for Bushehr itself has been found.", "This is not one published figure but the sum of Transnistria's seven left-bank rows of its own 2015 census, which is the republic's total less Bender."
- The method goes in the rest of the note, behind the heading's "i".

## Tokens

`text-note` at line-height 1.45 (the line, .72rem), `ink-secondary`, `text-basis-chip` and `radius-pill` (the badge, from `.chip-basis`), `status-modelled`, `status-derived`.

Contrast: as text on `surface-1` in light, the Modelled badge measures 3.6:1 and the Derived badge 3.2:1, below 4.5:1. In dark they measure 4.7:1 and 5.4:1.

## Accessibility

- The badge's glyph is text, not hidden: a screen reader reads the glyph, then "Modelled" or "Derived".
- The full status, "Estimated, not published" or "Derived from published figures", is only in `title`.
- The badge's word and the sentence carry the meaning; the colour repeats it.
- Not interactive.

## In the app

- `estimateLine(value, note)`, `site/js/dashboard.js:304–311`; `firstSentence` 297–302; `estimateRows` 287–293 decides whether a value takes this path. Placed at 331, before the bar.
- Badge colour, glyph and title: `Palette.status(gapStatus(value))` (`site/js/palette.js:70–80`), the same in both themes.
- CSS: `site/css/app.css:652–666`.
- You provide the status, the note and the rows. The colour comes from `Palette.status`.
- Why: an estimate "is drawn as figures: the same bar and list a reading gets, a badge that says "modelled" or "derived", and one sentence of the note in the open." (`dashboard.js:277–286`)

## Do / Don't

Do:
- Keep the line to the badge and one sentence. The full note under every panel drew the owner's complaint: "that giant block of text is so annoying".
- Draw the estimate's bar, list and map unit exactly like a reading's. A modelled unit "should look normal".
- Keep the badge on the estimate's own section, not on the place as a whole.

Don't:
- Don't hatch, fade or outline an estimate to mark it. The legend's hatched key predates that rule; don't copy it.
- Don't use the two badge colours for anything but these two statuses.
- Don't print the whole note in the line.
