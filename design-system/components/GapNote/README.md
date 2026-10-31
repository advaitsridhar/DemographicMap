# GapNote

A sunken box that stands in for a missing figure and says which absence it is and why: Not collected, Not yet available or Not applicable. With ⓘ, the same box carries a note about the place's record itself.

## When to use

- In place of a composition (Religion, Language, Ethnicity…) whose value is a gap. The box is the section's whole body.
- At the top of a place panel, under the header, for a note about the record: disputed ground, a territory drawn inside the state that administers it, a lake drawn as a unit.
- Not for a figure that exists with a caveat. That goes behind the heading's "i", or in an EstimateLine.

## Anatomy

```html
<div class="gap-note">
  <span class="gap-icon" style="color:var(--status-not-collected)" aria-hidden="true">◼</span>
  <span><strong>Not collected.</strong> France does not collect ethnicity; statistiques ethniques are barred by law (Loi Informatique et Libertes 1978, Conseil constitutionnel 2007).</span>
</div>
```

- `.gap-note`: the box, `surface-sunken` with a `border-ring` edge and `radius-sm`, glyph and text side by side.
- `.gap-icon`: the status glyph, coloured inline, hidden from screen readers. The app writes the hex `Palette.status()` returns (`#ec835a` here); write the state's token, as above.
- `<strong>`: the state's label and a full stop, in `ink-primary`. The sentence after it is `ink-secondary`.

## States and variants

Glyph, colour and label come together from `Palette.status(gapStatus(value))`, the same in both themes.

| State | Glyph | Inline colour | Lead-in |
| --- | --- | --- | --- |
| Not collected | ◼ | `#ec835a` (`status-not-collected`) | **Not collected.** |
| Not yet available | ▲ | `#fab219` (`status-not-available`) | **Not yet available.** |
| Not applicable | – | `#898781` (`status-not-applicable`) | **Not applicable.** |
| Record note | ⓘ | none, so it takes the box's `ink-secondary` | none |

- The record note also carries `style="margin-bottom:1rem"`, which spaces it from what follows: the fact tiles, or Sources on a disputed or water unit.
- A gap with no sentence of its own falls back to "This country does not collect religion." (Not collected) or "No religion figure has been fetched for this unit yet." (any other state), with the section's name in lower case. Every gap in the shipped data has its own sentence.
- Two more paths exist in `gapBlock` that no shipped value reaches. An estimate with no usable rows draws this box with its own glyph, colour and label: ◌ `status-modelled` **Estimated, not published.** or ◐ `status-derived` **Derived from published figures.** And a gap of any other status that carries estimate rows gets a closed `<details class="estimate">` table after the box, which has no CSS.

## Content

- Lead with the state's label and a full stop, then say why in one or two sentences: "**Not applicable.** Redonda is uninhabited; the census counts no one there."
- Name the source, the census or the law: "The CIA World Factbook gives only the words “Palestinian Arab”."
- A record note says what the map draws and what the figures cover: "geoBoundaries' global composite has no separate outline for this territory -- it is drawn as part of the state that administers it. The figures below are still its own."
- Put no year on the section's heading: “Printing one beside "not collected" implies a measurement that was never taken.” (`site/js/dashboard.js:319–320`)

## Tokens

`surface-sunken`, `border-ring`, `radius-sm`, `text-gap-note` (.76rem, line-height 1.5), `ink-secondary`, `ink-primary`, and for the glyph `status-not-collected`, `status-not-available`, `status-not-applicable`.

The glyph colours are not text colours: ▲ is 1.6:1 on `surface-sunken` in light. The word beside each glyph carries the meaning. The sentence passes (`ink-secondary`, 6.9:1 in light).

## Accessibility

- The glyph is `aria-hidden="true"`. The `<strong>` label says the state in words, so nothing rests on hue or shape.
- The record note has no label: a screen reader hears only its sentence.
- Not interactive and never focusable.

## In the app

- `gapBlock(value, fieldLabel)`, `site/js/dashboard.js:28–50`, called by `compositionPanel` when the value is a gap with no estimate rows (327–330).
- Record note: `render()`, `dashboard.js:506–510`, whenever `record.note` is set. For a disputed or water unit, Sources is all that follows it (512–518).
- Glyphs, colours and labels: `STATUS` in `site/js/palette.js:70–80`, read through `Palette.status()` (267).
- CSS: `site/css/app.css:499–507`.
- You provide the status, the section's name and the sentence. The glyph's colour is computed by `Palette.status`.

## Do / Don't

Do:
- Use the exact label and glyph for the state. "Not collected" and "Not yet available" are different claims.
- Say why, naming the source, the census or the law.
- Keep the section's heading above a gap, so the reader knows which figure is missing.

Don't:
- Don't infer Not collected from an empty value. It is asserted from a policy table.
- Don't draw a gap as a zero-width bar or an empty list.
- Don't colour the sentence or the box with the status colour. Only the glyph takes it.
