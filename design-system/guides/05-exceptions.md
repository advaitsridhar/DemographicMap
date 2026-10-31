# Exceptions in the app

Places where the app today departs from the rules in this system. The components here reproduce the app exactly, so a few of these are visible in the previews. When you build something new, follow the rule, not the exception.

## Copy

- **Estimates are no longer hatched, but two strings still say they are.** Since 21 September 2026 the map draws an estimate exactly like a reading. Two places still describe the old drawing: the Estimates check row's hint (“Hatched, in the colour the estimate gives. Off, they are gaps.”) and the legend's estimate line (“Estimated, not published — hatched, *N* units”, with a hatched swatch). The Estimates info text already gets it right: estimates are “drawn like any other”.
- **Hyphens standing in for dashes.** Two of the app's strings use an ASCII double hyphen: “Couldn't load that country's data -- click again to retry” and the unplaced-group info text (“-- only the classification is missing”). Two use a spaced hyphen: “Something failed to load - see the browser console” and every source line in the About dialog. The record notes do it too. Every territory drawn inside another state carries “geoBoundaries' global composite has no separate outline for this territory -- it is drawn as part of the state that administers it.” (48 country records, under ⓘ), and about 15,000 notes behind the “i” use “--”. The app's own strings otherwise use the em dash.
- **Wording drift.** The filters toggle's tooltip says “Hide the filter panel”; the panel's ✕ says “Hide the filters panel”. The same panel is also “Map filters”, “Filters” and “What the map shows”; the place panel is “the data panel”, “Selected place details” and “the details panel”.
- **One state, two names.** The About key calls the recorded state “Present”; everywhere else it is “Recorded”. Its chips also carry colour and a bold word but no glyph. The hover readout likewise names an estimate without its glyph, as a bare “(modelled)” or “(derived)” after the value.
- **Two stale “not collected” examples.** The About dialog still cites Japan and the United States as countries that do not collect these fields. Neither is in the not-collected policy table any more: Japan left it on 19 September 2026, and US religion now comes from a self-identification survey. France remains the clean example.
- **Disputed areas count as countries.** “269 countries loaded” includes the 19 disputed and special-status areas, and their breadcrumb reads “Country”.
- **The not-yet state drifts**: “Not yet available”, “not yet gathered”, “Not gathered yet”, “has been fetched … yet”, “unfetched”. Use “Not yet available” for the state, and “fetched” in a sentence about it.
- **Figure, value, unit, area, blank, grey.** The group legend says “No figure for *N* units”, the ramp legend says “No value for *N* units”, the reach line counts “areas”, and the notes alternate “Blank means …” with “Grey areas …”. Prefer “figure”, “unit” and “grey” in new copy.
- **The popup writes “no value”.** On Population, Median age, How concentrated and Share of one group, a unit with no figure reads “Population: no value”; only Most populous group shows “—”.
- **Two figures carry no year.** Life expectancy shows only “CIA World Factbook (public domain)” under its value, and the largest settlement's population (“1.5M people”) has neither year nor source.
- **Two hints run to two sentences**: Second-level divisions (“Districts and counties. Pinning this loads every country's shard.”) and Show estimates.
- **“Family” means three things**: the top tier for language, the middle tier in the Categories bubble, and any parent in the group bubble.
- **Pipeline words reach readers**: “Pinning this loads every country's shard.” “wherever that adapter has been run”. “CGAZ”.
- **Basis sentences paste in the raw basis.** The ordinary basis is matched by the exact string “self-identification”, so a basis such as “survey estimate: self-identification, residents aged 15 and over in private households” is quoted whole (“…the figures below the country count survey estimate: self-identification, … rather than answers people gave”). That breaks the app's own rule that self-identification is the ordinary case and goes unnamed.
- **Plurals and slips.** With exactly one extra group the legend reads “+1 more group lead somewhere”; the reach note reads “At this level: 1 countries.”; a gap tally reads “1 groups”. There is one contraction (“Couldn't” beside “Could not start”), one “per cent” among hundreds of “%”, “CC-BY-SA” beside “CC BY-SA 4.0”, and “Loading the worldwide group list…” with an ellipsis beside “Loading country data” without one.
- **Mixed locales.** Counts follow the reader's locale and percentages do not, so a French reader sees “68,5 M” beside “49.1%”.
- **A fitted ramp can pass 100%.** Rounding up the top of the range on screen produced “Colour scale from 1% to 101%”.
- **Glyph collisions.** ◐ is both the Auto theme icon and the Derived status, and – is both the Not applicable icon and a range dash.

## Components

- **The chosen group is never marked.** The group rows are `role="treeitem"`, so the app writes `aria-checked` on them, not `aria-selected`. The selected-row style (`.g-opt[aria-selected="true"]`: accent border, accent name) therefore never applies, and the chosen group has no highlight.
- **The tree's twist buttons are not keyboard-reachable** (`tabindex="-1"`, outside the arrow-key model), and tree items carry no `aria-level` or `aria-expanded`.
- **Some info dots cannot be pinned.** A click on a dot that has only `data-info-text`, which is every dot in the place panel and the legend's unplaced-group dot, opens the bubble and closes it at once. On touch, where there is no hover, those notes cannot be read.
- **The stacked bar can clip its own tail.** Each segment is `flex: 0 0 <share>%`, plus 2px gaps and a 2px minimum width. With many segments that sums past 100%, and `overflow: hidden` cuts the last ones; France's religion bar loses three segments, including the folded “Other groups”. Size segments so shares, gaps and minimums fit together.
- **One link is unstyled.** The link in the “Why this is empty” panel renders in the browser's default link colour, not `accent`.
- **`status-serious` is borrowed.** The partial-basis chip (“describes 10.6% of the population”) takes the Not collected orange for its text and border, so a coverage note wears a data state's colour.
- **`.panel-year` doubles as a count.** It holds the child count beside “Second-level divisions”. A count is not a year; give it its own class in new work.
- **Inline colours outlive a theme switch.** Swatch and bar colours are written inline when a place is selected, so after switching theme they stay in the old theme's values until the next selection. The group picker's unplaced dot is the same: it keeps the old theme's violet until the list is redrawn by a search, a twist or a topic change.
- **A stale “Still on the map” block.** Picking a group does not redraw the list, so the block can go on naming the previous group.
- **A disclosure inside a paragraph.** The reach note's `<details>` is written into a `<p>` through `innerHTML`. Static HTML cannot express that nesting (the parser closes the paragraph first).

## Map colour

- **“Not applicable” has no legend row.** The coverage view paints such units `status-not-applicable`, but its legend lists only the other five states.
- **Some groups share one colour.** No religion, Agnosticism and Unaffiliated render as the same teal, and Judaism and Atheism share #5D6D7E. A family missing from its band's sibling list falls back to the first sibling's colour: all 35 Turkic languages are #8839ce, and Indo-Aryan takes Germanic's #ee6900. Bands with more than thirteen families repeat exactly: the turn comes round every 13 places, and the saturation list holds 1.0 at four of its eleven places, so the 14th family takes the 1st one's colour.
- **Unrelated bands that render alike.** Because the map keeps only hue and saturation, Dravidian and Hmong-Mien languages, Austroasiatic and Papuan, Afro-Asiatic and Tai-Kadai, and the Indigenous American and Middle Eastern and North African ancestries come out nearly identical (CIE76 ΔE 2–4 at a 60% share). No check covers colour-blind separation.
- **The picker dot is not the map colour.** The dot paints the stored colour as it is, lightness included. The map keeps only its hue and clamped saturation, so #919aa1 is a grey dot but steel blue on the map.
- **Legend swatches ignore Fit to view.** The most-populous-group legend always shades on the fixed 25–100% ramp, so with Fit to view on a swatch no longer matches the map.
- **Unplaced groups.** On Share of one group, an unplaced group is drawn with the blue magnitude ramp, not `unplaced`, and Fit to view is ignored for it. The `unplaced` violet also sits close to the #8B4A9C bands (African diaspora religions, Koreanic languages, Romani) at equal shares.
- **One shade disappears into the sea.** In the light theme, Not stated at 25% renders #dce6ee, almost exactly `water` (#dfe6ee).
- **Residual answers can lead.** “Unclassified language answers” and “Unclassified ethnicity answers” lead some units (Paraguay, Qatar, Vanuatu), though residual rows are meant never to lead.
- **MapLibre's controls are unthemed.** The zoom buttons, scale bar and attribution stay light in the dark theme. They use a #0096ff focus glow, not the app's accent outline, and set their text in Helvetica/Arial.
- **The place sheet hides the attribution on phones.** At 900px and below the place sheet covers the bottom of the map whenever a place is open, the scale bar and the CC BY attribution with it, and the open filters drawer covers most of the attribution.
- **Auto theme follows the OS only halfway.** With Auto, `data-theme` is removed, so app.css's `prefers-color-scheme` block re-themes the panels the moment the OS switches. Nothing listens for the change, though. The map keeps the old `water`, `land-base`, `boundary` and outline colours until the next restyle, and unit fills switch only on the next pan or zoom, so the page shows dark panels over a light map.

## Search

- The combobox never sets `aria-activedescendant`, so a screen reader does not hear which result is highlighted. Tab does not close the list.
- Result chips say “Admin 1” and “Admin 2” where the rest of the app says “first-level” and “second-level divisions”.
- The input's accessible name (“Search for a country, state or district”) leaves out groups, which the placeholder and results include.
- The placeholder's example “Harris County” also returns ten unrelated “… County” rows, because the words are matched with OR. Its list of examples ends without the ellipsis the group search's placeholder uses.
- The topbar search sets no `::placeholder` colour, so it uses the browser's default; the group search uses `ink-muted`.

## Accessibility

- **`ink-muted` on text a reader needs.** The filter eyebrows (Topic, View, Shading…) are the only headings of their sections and name each control through `aria-labelledby`, yet they are `ink-muted`: 3.5:1 on `surface-1` in light at .68rem. The app also sets these readable texts in `ink-muted`: a fact tile's gap words (`.fact-value.is-gap`, 3.1:1 on `surface-sunken`), the “Why this is empty” body (`.note`), the empty panel's note (`.empty-note`), the popup's readout (`.tip-meta`), the legend's end values (`.legend-ends`), every `.control-note` (the reach sentence, the grey note, the level and group counts), the no-match messages (`.group-empty`, `.r-empty`) and the fact tiles' source and year (`.fact-meta`). All are 3.5:1 on `surface-1` in light.
- **Six controls have no accent focus ring.** `.children-list button`, `.entity-breadcrumb button`, `.source-list a`, `details.table-toggle > summary`, the link in the “Why this is empty” note (`.note a`) and the two skip links have no `:focus-visible` rule, so they show the browser's default ring.
- **A blank count.** A child division with no population shows an empty `.c-count`, not “—” or a state.
- **The contrast fails listed under Accessibility**: `ink-muted`, `accent` text, `accent-ink` on `accent`, the partial basis chip and the estimate badges, mostly in the light theme.
- **One info dot has no name.** The “i” beside the legend's “Group not yet classified” line has no `aria-label`, so its accessible name is just “i”.
- **Headings with an “i” lend it their name.** A radiogroup labelled by its heading includes the info button in its accessible name (“SHADING About how the shading is scaled”). Label the group with the heading's text alone.
- **The on-map legend's `aria-label="Map legend"` sits on a `div` with no role.** Its computed role is generic, which ARIA does not allow to be named, so the card is no landmark and the label is not reliably announced.
- **Focus.** Opening the filters drawer does not move focus into it. Escape does not close the place sheet on small screens. The place panel is a skip-link target but has no `:focus-visible` style.

## Unused

- `status-critical` is declared and never used.
- `.g-labels` is styled and never emitted. `.legend-estimate` and `.estimate-why` are emitted with no style, and so can `details.estimate` be, though no shipped value reaches it.
- The religion colour table `HUE` in `scripts/canonical_groups.py` is referenced nowhere. Group colours come from `TIER_HUE` and `FAMILY_HUE` in `scripts/group_tree.py`.
