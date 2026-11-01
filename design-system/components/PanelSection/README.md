# PanelSection

The wrapper for each topic of the place panel below the fact tiles: a section whose heading row names the topic, can carry an info dot, and pushes one muted figure — the reference year, or a count — to the right.

## When to use

- One section per topic, in the app's order: Religion, Language, Ethnicity, Ancestry, Scheduled Caste / Tribe, the hint panel, the divisions list, Sources.
- Not for the header or the fact tiles, which sit above the first section.

## Anatomy

```html
<section class="panel">
  <div class="panel-head">
    <h3>Religion<button type="button" class="info" data-info-text="{note}" aria-label="About the religion figures">i</button></h3>
    <span class="panel-year">2011</span>
  </div>
  <!-- the body: a composition, a gap note, a list or the sources -->
</section>
```

- `.panel` — one topic; `panel-gap` below it.
- `.panel-head` — a flex row on the baseline, .45rem above the body.
- `.panel-head h3` — the title, with the dot inside it.
- `.panel-year` — one figure, pushed right with `margin-left: auto`.

## States and variants

- **With a year** — `.panel-year` straight after the `h3`, when a composition has a reference year and is a reading or an estimate (`2011`, `2012`, `2023`).
- **No figure** — gap sections, the hint panels and Sources. A composition whose record has no year shows none either: France's Language has a dot and no year.
- **With a count** — the divisions list reuses `.panel-year` for how many divisions there are (`14`, `13`, `36`). It is a count, not a year; the class name is the source's.
- **With an info dot** — inside the `h3`, right after the title, only when there is note text. Its label is `About the {title} figures`, title lower-cased: `About the scheduled caste / tribe figures`.
- Titles in use: `Religion`, `Language`, `Ethnicity`, `Ancestry`, `Scheduled Caste / Tribe`, `Why this is empty`, `Not gathered yet`, `First-level divisions`, `Second-level divisions`, `Sources`.

## Content

- Name the thing, in sentence case; proper names keep their capitals (`Scheduled Caste / Tribe`).
- Put one bare figure in `.panel-year` — `2011`, `14` — with no word before or after it. Years and counts never go in the `h3`.
- Never print a year beside a gap: “A reference year only belongs on a value. Printing one beside "not collected" implies a measurement that was never taken.” (`site/js/dashboard.js:319–320`)

## Tokens

- `panel-gap` (below each section), `ink-muted` (`.panel-year`), `ink-primary` (the title, inherited).
- Type: `text-section-title` (`h3`), `text-meta` (`.panel-year`).

## Accessibility

- Each `h3` sits under the panel's `h2`, the place name. The sections have no accessible name, so they are not landmarks.
- The dot sits inside the `h3`, so the heading's accessible name includes the dot's label: Chrome names it “Religion About the religion figures”.
- Hover or focus on the dot opens its note in a bubble; a click closes it, because `site/js/app.js:344–346` spares only `[data-info]`.
- `.panel-year` is a plain `span` after the heading, read as a bare “2011” or “14” with nothing to say which it is.
- Contrast: `.panel-year` is `ink-muted` on `surface-1`, 3.5:1 in light — below 4.5:1 at 10.9px (4.85:1 in dark).

## In the app

- Composition heads in `compositionPanel()` `site/js/dashboard.js:322–325`; `hintPanel()` `:408` and `:422`; `childrenPanel()` `:484–485`; `sourceList()` `:473`.
- CSS `site/css/app.css:481–484`. The `h3` lays out its dot with `display: flex; align-items: center`, and the dot drops the heading's letter-spacing (`site/css/app.css:668–671`).
- You provide the markup, the title, the note for the dot, and the year or count.

## Do / Don't

- Do put the dot inside the `h3`, directly after the title text.
- Do keep `.panel-year` to one bare number.
- Don't show a year on a gap or a hint panel.
- Don't nest sections or add a second heading to the head row.
