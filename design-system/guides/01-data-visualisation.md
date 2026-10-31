# Data visualisation

Four palettes, each with one job. Never borrow one palette's colour for another's job, and never let hue be the only thing that carries a meaning.

| Palette | Answers | Tokens | Used in |
| --- | --- | --- | --- |
| Sequential | How large is this number? | `sequential-0` … `sequential-10` | Population, Median age, How concentrated |
| Status | Is there a figure here, and what kind? | `status-present`, `status-not-available`, `status-not-collected`, `status-not-applicable`, `status-derived`, `status-modelled` | Data coverage, gap notes, the About key, popups |
| Categorical | Which group is this row? | `categorical-1` … `categorical-8` | Composition bars and their lists, nowhere else |
| Group | Which group leads here, and by how much? | `religion-*`, `language-*`, `ethnicity-*`, drawn through the luminance band | Most populous group, Share of one group, the group picker's dots |

Two more colours sit outside the palettes, and both mean something exact. `neutral` means this view has no figure for a unit that has a record: nobody counted, or the composition cannot name a leader (the DRC's six listed religions cover 6.8% of its people). A unit with no record at all falls back to `land-base`. `unplaced` means a figure exists but the classification has not yet placed its group in the tree. Never draw an unplaced group in `neutral`. That would turn “the number is known, the family is not” into “nobody counted”, the one confusion this map exists to prevent.

## Darker always means more

Every ramp runs pale to dark **in both themes**. A shade's meaning belongs to the data and must not flip when the furniture goes dark. Twice the app shipped a dark-mode ramp that ran the other way, on the usual “brighter is more on a dark screen” instinct, and twice every reading of the map was upside down for dark-mode readers. `scripts/check_shading.js` now fails the build if any ramp runs backwards.

- Ramps are cut in **relative luminance** (WCAG), not HSL lightness, so equal steps look equally dark whatever the hue. At the same HSL lightness, yellow and blue differ more than four times in luminance. A ramp cut in lightness made a county 80% gold look lighter than one 50% red.
- The band: light theme from luminance 0.78 (pale) to 0.055 (deep); dark theme from 0.70 to 0.115. The dark theme stops well above its own ground (`land-base` #26262a is 0.020 and `neutral` #33332f is 0.033), so a full-share unit never sinks into the ground beneath it.
- `Palette.group(hex, share)` keeps a group's hue and saturation (saturation clamped to 0.35–0.95; a grey stays grey) and bisects HSL lightness until the colour hits the target luminance for that share.
- The pale end is not the surface colour. A district of four thousand people has been counted, so small is not missing; only `neutral` means the view has no figure. In the light theme `neutral` is actually darker than the palest blue step, so the two are told apart by hue, grey against blue. No check covers that pair.

## The sequential ramp

`sequential-0` … `sequential-10` are the eleven steps `palette.js` computes from the hue #3987e5 along the band. Step *n* is t = n/10. Use them for magnitudes only: population (log scale), median age, how concentrated. A legend shows the full scale as eleven equal cells between its two ends (`1,739` … `257M`).

## Status: colour, glyph and words together

| State | Token | Glyph | Words |
| --- | --- | --- | --- |
| A value with a source and year | `status-present` (= `status-good`) | ● | Recorded |
| Exists somewhere, not fetched by this build | `status-not-available` (= `status-warning`) | ▲ | Not yet available |
| The country does not gather it | `status-not-collected` (= `status-serious`) | ◼ | Not collected |
| The question does not apply | `status-not-applicable` | – | Not applicable |
| Computed from published figures | `status-derived` | ◐ | Derived from published figures |
| Modelled, not published | `status-modelled` | ◌ | Estimated, not published |

Always ship all three: the colour, the glyph (`aria-hidden`) and the words. The status colours fail as text on light surfaces (▲'s yellow is 1.8:1), so they colour glyphs, swatches and fills, never words, except where the source keeps a known exception (see Accessibility).

## Categorical: eight fixed slots

- Slot order is row order: the largest row takes `categorical-1`, the next `categorical-2`, and so on. Slots are never cycled.
- A composition with more than eight rows shows the first seven and folds the rest into **“Other groups (n)”** in the eighth. A ninth slot falls back to `neutral`, so a folding bug shows up as grey rather than as an invented identity.
- Use categorical colour only where every mark also carries its text label and percentage: the stacked bar always sits above its labelled list.
- The share a composition does not describe (a real shortfall, not rounding) is a hatched **rest** segment in `hairline`. It has no swatch and no list row, because it is not a group.

## Group hues

The most-populous-group map colours each unit by its leading group: **hue says which group, darkness says how much of it**.

- **Bands (tier 1).** Each field has a band per top grouping, `religion-abrahamic`, `language-indo-european` or `ethnicity-african` for example. The hues were hand-picked from the Okabe–Ito colour-blind-safe set where it stretches, with the widest-reaching bands placed furthest apart. The map then reads as regions, not confetti.
- **Families (tier 2), by convention.** Religion keeps the colours printed atlases use, because a reader arrives expecting them: Catholic red (`religion-catholicism`), Protestant blue, Orthodox purple, Islamic green (`religion-islam`), Hindu saffron and Buddhist gold. Deriving every religion family from its band had turned the whole religion map one Abrahamic blue.
- **Families (tier 2), by rotation.** Every family without a conventional colour takes its band's hue turned by its place among its siblings. That covers all language and ethnicity families, and religion families such as Eastern religions or Cheondoism. The turns are 0, +30, −30, +15, −15, +22, −22, +8, −8, +26, −26, +12, −12 degrees. Saturation is scaled by the same index (1.0, 0.72, 1.0, 0.78, 0.94, 0.68, 1.0, 0.84, 0.9, 0.74, 1.0). HLS lightness is set to the band's plus 0.05, capped at 0.60, so a pale band's families come out darker than the band. The turn is capped at ±30° because a wider one flung a band across the wheel and the region stopped reading as one. One family is the exception: `ethnicity-tibeto-burman-peoples-of-china-and-southeast-asia`.
- **Deeper groups** take their family's colour. A census that names one Catholic order is still drawn Catholic red.
- **Lightness belongs to the share.** Most populous group starts its ramp at 25% (`SHARE_FLOOR`): every share below it is drawn at the palest step, because a plurality of 26% is a fact about the place, not a near-absence. Share of one group starts at 0%, because 3% is a real answer that must not look like 0%.
- **Fit to view** stretches the ramp to the range on screen, so a screenful of districts that are all 85–95% one group reads as the spread it is. The legend then says so. On Most populous group, “Share of the leading group” takes a “fitted to this view” badge, and its ends read the fitted range without “or less” (“19%” … “100%”). On Share of one group a note says “Fitted to the range on screen.”

The flat hue is painted only as the group picker's dot. Everywhere else a group colour is a shade from `Palette.group`. On Most populous group every unit names its group and share in the popup (“Christianity 55%”); on Share of one group the popup gives the share and the filter chips name the group. The legend names each colour in the order it leads the most units, and the panel names it a third time.

## Legends

The panel legend and the on-map legend are the same markup, so they never drift apart. Each view has one form:

- **Sequential**: an eleven-cell scale, its two ends, and “No value for *N* units” in `neutral`.
- **Status**: one row per state, with glyph, swatch and words.
- **Most populous group**: the groups in the order they lead the most units, each with a count; “+*N* more groups lead somewhere”; then “Share of the leading group” as a five-step grey ramp (`leading-share-0` … `leading-share-4`, computed from `group-any`) from “25% or less” to “100%”; then “No figure for *N* units”.
- **Share of one group**: the group's own eleven-step ramp from 0% to 100%. With Fit to view on, it runs over the fitted range under the note “Fitted to the range on screen.”, with no badge.

A note under each legend says what grey means at this level: “Grey areas have no published population at this level.”

## Numbers in charts

- **A column of shares takes one decimal** (54.7%, 0.3%), so the column can be seen to add up. A share read on its own (a popup, a legend end) is rounded: whole numbers from 10 (91%), one decimal below (9.9%).
- **A partition adds to exactly 100.0.** A set less than half a point from 100 is a rounding effect, so the tenths are put back, largest rows first. At exactly half a point the floating-point sum decides: India's languages add to 99.5 and keep a 99.5% total and a 0.5% hatched rest. When the published sum misses 100 by about a twentieth of a point or more, the info dot says the tenths were moved. A sum further below 100 is a real shortfall. It keeps its true widths with the gap drawn as the hatched rest, and below 95% a chip says “describes 10.6% of the population”.
- **A multi-response set sums past 100% on purpose.** Its categories overlap and there is no remainder, so the bar stretches the shares to full width, but the list and table keep the true percentages. When the measured shares pass 105%, a chip says “more than one answer allowed”.
- **An upper bound stays a bound**: `<0.3%`, `<1.0%`.
- **Counts are compact** from 10,000 and grouped below, in the reader's locale: 12.3K, 68.5M, 1.4B and 1,739 in US English. A missing number is an em dash, never 0.

## Charts are DOM

Draw a composition as a flex stacked bar (`.stack-bar`) plus a labelled list (`.composition-list`), and offer the same rows as a table under “Table view”. Every value stays in the DOM, where screen readers, find-in-page and copy-paste can reach it. There is no charting library and no canvas outside the map.
