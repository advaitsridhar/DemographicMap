# SegmentedControl

A row of two or three equal buttons in a sunken track, the chosen one raised onto the panel surface; the filters panel uses it for Topic, Categories and Shading.

## When to use

- For two or three mutually exclusive alternatives of one kind, each short enough to fit a third of the panel. "Three mutually exclusive fields read better side by side than stacked: they are alternatives of one kind, not a menu of different things." (app.css:260-261)
- If each choice needs a sentence to explain it, use OptionList. Explain the control as a whole behind its heading's "i".

## Anatomy

```html
<section class="filter-section" id="spread-section">
  <h3 id="spread-label">Shading
    <button type="button" class="info" data-info="spread"
            aria-label="About how the shading is scaled">i</button>
  </h3>
  <div id="spread-options" class="segmented" role="radiogroup" aria-labelledby="spread-label"><button type="button" role="radio" class="seg" data-value="absolute" aria-checked="true" tabindex="0">Full range</button><button type="button" role="radio" class="seg" data-value="fit" aria-checked="false" tabindex="-1">Fit to view</button></div>
</section>
```

The segments share the track equally (`flex: 1`), 2px apart inside a 2px padding.

## States and variants

| State | Set by | Look |
|---|---|---|
| Not chosen | `aria-checked="false"`, `tabindex="-1"` | `ink-secondary` on the track |
| Hover | `:hover` | text turns `ink-primary` |
| Focus | `:focus-visible` | 2px `accent` outline, inset 1px |
| Chosen | `aria-checked="true"`, `tabindex="0"` | `surface-1` tile with `shadow-seg`, `ink-primary`, weight 600 |

The three in the app:

- **Topic**: "Religion", "Language", "Ethnicity"; starts on Religion. Shown in every view but Population and Median age.
- **Categories**: three tiers whose labels follow the topic: religion "Traditions", "Religions", "As reported"; language "Families", "Branches", "As reported"; ethnicity "Ancestry", "Peoples", "As reported". Starts on the middle tier. Shown for Most populous group only.
- **Shading**: "Full range", "Fit to view"; starts on Full range, "because a shade that means the same thing everywhere is the more honest starting point" (app.js:63-64). Shown for Most populous group and Share of one group.

## Content

- One to three words in sentence case that name the alternative itself: "Religion", "As reported", "Fit to view".
- Name what a tier is in this topic, not its number: "a control that said "Tier 1" would be asking the reader to hold the abstraction rather than the question" (app.js:447-448).
- Keep labels short enough not to clip. Segments ellipsise, and "The longer "Ethnicity / race" was ellipsed to "Ethnicity / ra…", which is worse than the shorter word" (metrics.js:375-377).

## Tokens

`surface-sunken` (track), `hairline` (track edge), `radius-sm` (track), `radius-xs` (segment), `surface-1` and `shadow-seg` (chosen segment), `ink-secondary`, `ink-primary`, `accent` (focus). Type: `text-segment` (.76rem; 600 when chosen).

Labels pass at 6.9:1 or more. The chosen tile differs from the track by only 1.1:1 in fill, and in dark `surface-1` sits darker than the track, so the weight and ink change carry the state; keep both.

## Accessibility

- The track is a `role="radiogroup"` named by its section `h3` through `aria-labelledby`; each segment is a `<button role="radio">` with `aria-checked`.
- One tab stop on the chosen segment. Arrow Right or Down chooses the next segment and Left or Up the previous, wrapping; Home and End jump to the ends. Selection follows focus.
- All three headings hold an "i", whose label joins the group's name; measured: "TOPIC About comparing topics across borders", "SHADING About how the shading is scaled".

## In the app

- Topic: built at app.js:480-497 from `window.Metrics.FIELDS` (metrics.js:379-383). Picking a different topic remembers the group chosen in the old one, restores the new one's, clears the group search, rebuilds Categories and repaints.
- Categories: `renderDepths()` app.js:621-627 from `DEPTH_LABELS` app.js:450-454, rebuilt on every topic change and keeping its value; picking one re-renders the summary and repaints (app.js:516-521).
- Shading: the literal list at app.js:499-508; picking one repaints. While Fit to view is on, every map move repaints (app.js:1353).
- `markChoice` and `wireChoice` (app.js:381-420) are shared with OptionList.
- The consumer provides each segment's value and label, the chosen value, and the heading id for `aria-labelledby`. No colour is computed.
- CSS: `site/css/app.css:260-275`.

## Do / Don't

Do:
- Keep to two or three segments with short, concrete labels.
- Keep exactly one segment chosen.
- Change the labels with the topic when the same tier means a different thing.

Don't:
- Don't put a choice that needs a sentence in a segment.
- Don't let a label ellipsise; shorten it and put the nuance behind the "i".
- Don't signal the chosen segment by fill alone.
