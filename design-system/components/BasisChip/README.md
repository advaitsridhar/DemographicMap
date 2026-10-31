# BasisChip

A small pill under a composition bar that says how its shares relate to the population when they do not simply add up to it: "more than one answer allowed" or "describes 10.6% of the population".

## When to use

- Directly under a composition's stacked bar, before its list, when the shares sum well past 100% (more than one answer per person) or well short of it (only part of the population is described).
- Not for a set that partitions the population to within rounding: it gets no chip.
- Not as an estimate's badge: that is the EstimateLine, which reuses `.chip-basis` with `.chip-estimate`. An estimate's bar runs the same tests, so an estimate whose shares fell short or overlapped would take this chip too; no shipped estimate does.

## Anatomy

```html
<p class="basis-line"><span class="chip-basis chip-basis-partial" title="Shares sum to 10.6%">
                describes 10.6% of the population</span></p>
```

- `.basis-line`: the paragraph that holds the chip, .3rem under the bar.
- `.chip-basis`: the pill, `surface-sunken` with a `hairline` edge and `radius-pill`.
- `.chip-basis-partial`: turns the text and the edge `status-serious`.
- `title`: the sum the chip is based on, "Shares sum to 10.6%".

## States and variants

| Variant | Classes | Text | The app sets it when |
| --- | --- | --- | --- |
| Multi-response | `chip-basis` | more than one answer allowed | the shares sum past 105%, leaving out upper-bound ("<") rows |
| Partial | `chip-basis chip-basis-partial` | describes {total} of the population | otherwise, the bar's rows sum below 95% |
| None | — | — | otherwise |

- The multi-response test reads the rows before any are folded into "Other groups"; the partial test reads the rows the bar draws.
- A partial chip always comes with the bar's hatched "not accounted for" segment. A set between 95% and 99.5% gets the hatched segment and no chip (Armenia's religion, 96.9%).
- A multi-response bar is stretched to full width: Afghanistan's "Afghan Persian or Dari 77.0%" is drawn at 50.33%.

## Content

- Write the chip as a lower-case phrase with no full stop that reads on from its bar: "more than one answer allowed", "describes 10.6% of the population". The brand book sets basis chips this way, apart from the sentence case it gives filter chips.
- Shares to one decimal (`Fmt.pct1`), in the text and in the title: "Shares sum to 152.0%". The multi-response sum leaves bound rows out and the table's total counts them, so Afghanistan's chip says 152.0% over a table that totals 153.0%.

## Tokens

`text-basis-chip` (.66rem, 600, .01em tracking), `ink-secondary`, `surface-sunken`, `hairline`, `radius-pill`, `status-serious` (partial).

Contrast: the partial chip's `status-serious` text measures 2.3:1 on its `surface-sunken` fill in light, below 4.5:1 and below 3:1. In dark it is 6.0:1. It also borrows the Not collected orange for a different meaning. The neutral chip passes (`ink-secondary`, 6.9:1 in light).

## Accessibility

- The chip is plain text in a `<p>`. A screen reader reaches it after the bar, whose `aria-label` already ends ", not accounted for 89.4%" for a partial set.
- On the multi-response chip the sum is only in `title`, which touch and keyboard users cannot reach. The visible words must carry the meaning on their own. The partial chip prints its sum in the text as well.
- Not interactive.

## In the app

- `basisChip(total, value)`, `site/js/dashboard.js:239–257`, wrapped in `<p class="basis-line">` at 365–366, after the stack bar and before the list.
- CSS: `site/css/app.css:652–661`.
- You provide the rows, with any "<" bounds, and the two sums. No colour is computed.
- Why it is on the page: "A reader who sees six ethnic groups totalling 114% and no explanation is looking at what appears to be an error." (`dashboard.js:231–238`)

## Do / Don't

Do:
- Put the chip under the bar it qualifies, before the list.
- Leave "<" rows out of the multi-response test: "only shares can show that answers overlap".
- Keep the full explanation behind the heading's "i"; the chip is the one fact that changes how the bar is read.

Don't:
- Don't add a chip to a set that is off 100% only by rounding.
- Don't spend the partial orange on anything else. It is already the Not collected colour.
- Don't normalise a short set to full width to hide the gap. The hatched segment and the chip say it is partial.
