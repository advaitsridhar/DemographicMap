# ControlNote

A small muted paragraph under a control or key that says what its current state covers: how many units are loaded, what a blank on the map means, how many groups match a search, and how far the chosen group's figures reach.

You provide the markup and the text. Every number and name in it is computed from the data at the moment the control changes.

## When to use

- Directly under the control or key it qualifies, never above it. "What the chosen filter covers. Sits at the foot of the panel because it qualifies the map that is already drawn, not the next thing the reader does."
- For counts and caveats a reader can skim. Nothing a reader needs in order to use the control goes here: the text is `ink-muted`.

## Anatomy

```html
<p class="control-note">269 countries loaded</p>

<p id="group-count" class="control-note group-count" role="status" aria-live="polite">6 of 6 match “Islam”.</p>

<p class="control-note group-reach">At this level: 6 countries. Everything else is blank because the figure is missing, not zero. 7 countries report it nationally.<details class="reach-labels"><summary>Combines 9 source labels</summary>African American/umbanda, Saio/Zione, Spiritism, Spiritism and Afro-Brazilian religions, Spirtism, Umbanda and Candomblé, Vodou, Vodoun, Winti</details></p>
```

`.group-count` (top margin .35rem) and `.group-reach` (.45rem) are the app's `#group-count` and `#group-reach`; every other note keeps the base .5rem.

## States and variants

- **Level note**, under Detail level: "{count} countries loaded", with "first-level divisions" or "second-level divisions" in place of "countries" ("269 countries loaded", "2,830 first-level divisions loaded"). Rewritten on every repaint; the count is every record loaded at the level, water units included.
- **Blank note**, under the legend and again in the on-map legend: the view's `blank` sentence, `hidden` when the view has none.

  | View | Blank note |
  | --- | --- |
  | Most populous group, How concentrated | Grey areas publish no composition for this field at this level. |
  | Data coverage | Grey means no record for that unit at all, not even a gap marker. |
  | Population | Grey areas have no published population at this level. |
  | Median age | Grey areas have no published median age at this level. |
  | Share of one group | Blank means the figure is missing at this level — not that the share is zero. |

- **Empty legend**: `<p class="control-note">No values at this level yet.</p>` in place of the key when no unit loaded at this level has a value. Only the four ramp views reach it (Population, Median age, How concentrated, Share of one group; metrics.js:511-513): Data coverage always draws its five-line key, and Most populous group always draws its ramp.
- **Group count**, between the group search and the list: "372 groups, widest reach first. 15 of them open to show what is inside." with no search; "6 of 6 match “Islam”." with one; "0 groups" when nothing matches and nothing is chosen; empty while the group list loads.
- **Reach note**, under the group list, only while the view needs a group and one is chosen; `hidden` otherwise. Its sentences, in order:
  1. "At this level: 6 countries." at country level, or "At this level: 131 first-level divisions across 18 countries." below it, then "Everything else is blank because the figure is missing, not zero." Where the level has no figure: "No countries carry this figure. It is reported for 42 first-level divisions and 839 second-level divisions — change Detail level to see them. The map is blank here because the figure is missing at this level, not because the share is zero."
  2. "{n} countries report it nationally." when fewer report at this level.
  3. 2–6 source labels: "Combines: Gypsy, Roma, Romani." More than 6: the closed disclosure `<details class="reach-labels">` with "Combines {n} source labels", appended after every sentence.
  4. One sentence per country whose figures count something other than self-identification: "Within Pakistan, the figures below the country count sectarian affiliation rather than answers people gave, so they are not on the same footing as the rest."
- **Disclosure open**: `<details class="reach-labels" open>` lists the labels, comma-separated, at .68rem.

## Content

- Sentences end in a full stop; a bare count ("269 countries loaded") does not. Name what a blank means at this level, always as "missing, not zero".
- Numbers through `Fmt.number`: "2,830", "26.4K". Quote a search query in curly quotes, as typed.
- Known slips in the source to avoid copying: a country-level count is never made singular ("At this level: 1 countries." for Jainism, Shinto and Pardo), and basis sentences paste the raw basis in ("count survey estimate: self-identification, residents aged 15 and over in private households rather than answers people gave"), which contradicts the rule that self-identification is "the ordinary case and naming it would tell a reader nothing". With 18 such sentences, Abrahamic religions' note runs to 3,673 characters.

## Tokens

`text-control-note` (.7rem, line height 1.45), `ink-muted`. The disclosure: `text-meta` (.68rem; line height 1.5 in the rule), `ink-primary` for the summary on hover, and a 2px `accent` outline at 1px offset on focus.

The legend above the notes in the preview is the app's own markup for a Share of one group map of Islam. Its eleven ramp stops are the shades `Palette.groupRamp` computes from Islam's hue for the theme on screen. A group's shade has no token, so the preview declares each stop as a frame-local property named after its light hex (`--shade-bef0d3` … `--shade-114d2a`), set to the light band's shade on `:root` and the dark band's under `[data-theme="dark"]` (palette.js:206-212): `#bef0d3` … `#114d2a` in light, `#a0eabf` … `#196e3d` in dark. They theme like the app. The swatch for units with no value is `Palette.neutral()`, written as `var(--neutral)` so it themes as it does on a fresh load. The group dots are each group's own hue from `groups.json`, the same in both themes.

## Accessibility

- The group count is `role="status"` and `aria-live="polite"`, and the search box's `aria-describedby`, so each new count is announced.
- The reach note is not live: picking a group changes it silently.
- `ink-muted` at 11.2px is 3.5:1 on `surface-1` in light, below 4.5:1, and 4.85:1 in dark.
- `<details>` is not phrasing content, so a paragraph cannot hold it. The app sets the reach note with `innerHTML`, which nests it anyway; written into a page as static HTML, `<details>` ends the `<p>` and the closing `</p>` adds an empty paragraph. Insert it with the DOM, as the app does, or use a `<div>`.
- The summary is the browser's own disclosure control: Enter and Space toggle it.

## In the app

- Markup: `site/index.html:108` (count), `:110` (reach), `:119` (blank), `:125` (level), `:139` (the on-map legend's note).
- Level: `updateLevelNote`, `site/js/app.js:1219-1221`. Blank: `renderSummary`, `app.js:943-947`, from each view's `blank` (`site/js/metrics.js:286-358`). Empty legend: `renderLegend`, `app.js:1119`. Count: `renderGroupList`, `app.js:845-846`, `:865` and `:898-901`. Reach: `describeReach`, `app.js:970-1059`, set with `innerHTML` at `:1057`.
- CSS: `site/css/app.css:384` (`.control-note`), `:387-388` (`#group-reach`, `#group-count`), `:357-360` (`.reach-labels`).

## Do / Don't

- Do count for the level on screen: "a map pinned to districts that claims 124 tells the reader the opposite of what it is showing".
- Do say where the figure does exist when the level has none: "Saying only that it is missing here leaves the reader stuck in front of a blank map."
- Do fold a long label list into the disclosure: "hidden it would be a claim the reader cannot check, and inline it would bury the sentence above".
- Don't explain how the view encodes its numbers here; that "belongs to the legend, and behind the legend's own "i"".
- Don't use a note for anything that must be read: it fails contrast in light.
