# Design system

The site's visual language, written down: tokens, the component stylesheet, and guidelines with a preview for every component, extracted from `site/` at commit 3e35ead. The site does not load anything from this folder; `site/css/app.css` is still what the map uses.

| Path | What it holds |
| --- | --- |
| `README.md` | This brand book: principles, voice, visual foundations, iconography and how to use the system |
| `guides/` | Data visualisation, the map, writing, accessibility, and where the app departs from these rules |
| `tokens.json` | Every colour (light and dark), size and type style, each with a note on where it is used |
| `tokens.css` | The tokens as CSS custom properties and `.text-*` classes. Generated. |
| `components/bundle.css` | The component styles: `site/css/app.css` with its theme blocks moved into the tokens. Generated. |
| `components/<Name>/` | Guidelines (`README.md`) and a static preview (`preview.html`) for each of the 32 components |
| `index.html` | A catalogue that renders every preview, in either theme |

To browse the catalogue, run `python3 scripts/serve.py --root design-system` and open http://127.0.0.1:8899/. The previews expect `tokens.css` and `components/bundle.css` to be loaded around them, and the catalogue does that.

`python3 scripts/build_design_system.py` rebuilds the two generated files after a change to `site/css/app.css` or `tokens.json`. With `--check` it changes nothing and exits 1 if either is stale, or if a token no longer matches the source it was taken from. CI runs that check on every push.

---

World Demographics Map is a reference tool: a map of the world's countries, first-level and second-level divisions, joined to population, religion, language and ethnicity figures, and to an explicit record of where those figures do not exist. The interface stays quiet so the data can speak. It uses warm greys, one blue, the system font and small, dense type, and spends nearly all of its colour on the map.

## Principles

- **A gap is data.** Every field is *Recorded* or a gap that says why: *Not yet available*, *Not collected* or *Not applicable*. An estimate in its place is *Derived* or *Modelled*. Each state has its own colour, glyph and words. Never draw an absence like a zero, never leave a field blank, and never infer “not collected” from an empty value. It is asserted from a policy table, because “the source said nothing” and “the state asks nobody” are different facts.
- **Darker always means more**, in both themes. What a shade means belongs to the data, not to the colour of the furniture around it.
- **Hue is never the only channel.** Every colour that carries meaning also carries a glyph, a word or a label. Status colours come with ● ▲ ◼, composition bars with a labelled list, and the popup, the legend and the panel name every group the map colours.
- **Percentages do not cross borders.** US race, Brazilian *cor ou raça*, UK ethnic group and Chinese *minzu* are different questions. Label every composition with the classification it came from, and never set two countries' categories side by side as if they were one scale.
- **Every value says where it came from.** A figure carries its source and reference year (`2011 · Census of India 2011`). Estimates say they are estimates, and an upper bound stays an upper bound (`<0.9%`).
- **Self-contained.** System fonts, Unicode glyphs, no web fonts, no icon font, no image files and no CDN, so the app runs behind a firewall. The Pages deploy (`.github/workflows/pages.yml`) fails if `site/index.html` names an external `src` or `href`. It does not scan the scripts or the stylesheet; the links the scripts write to sources' own sites are links, not assets.

## Content fundamentals

The voice is a careful statistician explaining a table to a colleague. It is plain, exact, unhurried and slightly dry. It says what a thing is, then what it is not.

- **Spelling is British**: colour, licence, grey, modelled, per cent.
- **Sentence case everywhere.** Use it for headings (“What the map shows”, “Pick a place”), buttons (“About & sources”), options (“Most populous group”, “Fit to view”) and filter chips. A few labels are lower-case phrases that read on from what they qualify: the basis chip (“describes 10.6% of the population”), the legend's “fitted to this view” badge and the group list's “in …” asides. Uppercase appears only through CSS, on eyebrows and labels (`text-eyebrow`, `text-fact-label`, `text-breadcrumb`, `text-table-head`, `text-level-chip`). Type the words in sentence case.
- **Headings name the thing**, not a feature: “Religion”, “Second-level divisions”, “Sources”, “Gaps are data too”.
- **A choice says what it does** in one sentence under its name, in the present tense:
  - Most populous group — “One colour per group, darker where its share is larger.”
  - Population — “Latest published count, on a log scale.”
  - First-level divisions — “States, provinces, regions — wherever they are tiled.”
- **Explain absence precisely.** Say which absence it is and why:
  - “Grey means no record for that unit at all, not even a gap marker.”
  - “Everything else is blank because the figure is missing, not zero.”
  - “**Not collected.** France does not collect ethnicity; *statistiques ethniques* are barred by law…”
- **Address the reader as “you” only for actions** (“as you zoom in”, “until you pick something else”). Otherwise write impersonally. Never write “we”, and never apologise.
- **Punctuation.** Use curly quotes (“Kerala”, “Islam”) with straight apostrophes (census's). Use the spaced em dash for a gloss (“Where a figure exists — and whether a gap is unfetched or never collected.”) and the spaced middle dot to separate metadata (“2011 · Wikidata (CC0)”, “200 countries · 24.5K areas · 2 modelled”). Breadcrumbs take ›. The group search's example placeholder ends in a single-glyph ellipsis (‘Search — “Islam”, “Muslim”, “te reo”…’). Sentences end in a full stop, including the group count (‘6 of 6 match “Islam”.’). Labels, chips and status lines don't (“269 countries loaded”, “No match”).
- **Numbers.** Counts are compact from 10,000 and grouped below, in the reader's own locale through `Intl.NumberFormat`: 34.5M and 1,739 in US English, 34.5m and 1.4bn in British English, 34,5 M and 1 739 in French. Percentages are not localised. Shares in a column take one decimal (54.7%); a share read alone is rounded (55%). Keep upper bounds as bounds (<0.9%). Ages take “yrs” (31.8 yrs), and the sex ratio takes its unit (“males per 100 females”). A year stands alone (“2011”). No value is an em dash, never 0.
- **Never**: exclamation marks, emoji in running text, “sorry” or “please”, marketing words (explore, discover, easily, simply), “N/A”, or a figure without its year. The app slips on the last one for life expectancy and settlement sizes (see Exceptions in the app). The full rules and the vocabulary of absence are under Writing.

## Visual foundations

### Colour

- Set the page on `surface-2`, panels and anything floating on `surface-1`, and recessed things (inputs, tiles, the selected row, chips) on `surface-sunken`.
- Text is `ink-primary` for names, values and headings and `ink-secondary` for running text. `ink-muted` is for hints and secondary meta. It measures 3.1–3.5:1 on the light surfaces, so never use it for anything a reader must read. The app breaks this rule widely: its filter eyebrows, the popup's value line, the legend's end values and grey note, the reach sentence under the group list and the fact tiles' source and year are all `ink-muted` (see Exceptions in the app). Set new text a reader needs in `ink-secondary`.
- Lines are 1px `hairline`. Colour keys (swatches, scales, tiles) get the translucent `border-ring` so their edge survives any fill. The info dot's ring is `axis`.
- There is one accent. `accent` marks focus, selection and links, and text on an accent fill is `accent-ink`. There is no second brand colour; the rest of the colour belongs to the data.
- `status-good`, `status-warning` and `status-serious` mean Recorded, Not yet available and Not collected. The app also borrows `status-serious` for the partial-basis chip (“describes 10.6% of the population”); don't copy that (see Exceptions in the app). `status-critical` is reserved and unused.
- The map ground is `water`, with `land-base` under units that have nothing drawn and `boundary` for division lines.
- The dark theme is chosen, not inverted. Neutrals go near-black (`surface-2` #0d0d0d), the accent lifts to #3987e5, and the data ramps still run pale to dark.

### Type

- One family: `--font-sans`, the system UI stack. It loads nothing and reads like the reader's own computer.
- The scale is dense and hand-tuned: 41 styles, 38 of them for text from .65rem to 1.3rem and three for glyphs up to the 1.35rem brand mark. Most of the panel sits between 10.5px and 13px. Pick a style by its role (`text-section-title`, `text-row`, `text-note`, `text-hint`) and don't invent a size between two existing ones.
- Weights: headings, a gap note's state words (“Not collected.”) and the info dot's “i” are bold (700). Names, values, eyebrows, table heads, the checked segment, the key filter chip and the basis and estimate chips are 600. A fact tile's gap words are 500, and everything else is 400.
- Most headings track slightly tight (-.01em; the place name -.02em). The dialog's headings and the empty panel's title keep normal tracking. Uppercase labels track open: .06em on the filter eyebrows, .05em on the breadcrumb and fact labels, .04em on table heads and search level chips.
- Every column of numbers is `font-variant-numeric: tabular-nums`: percentages, counts, reach, table values.

### Space and layout

- The desktop page is three columns under a topbar: filters (`filters-w`, collapsible to zero width so the map can follow the resize), the map, and the place panel (`sidebar-w`). The topbar's height comes from its content; the app measures it into `topbar-h` whenever it changes, and the filters drawer is placed below that value.
- At 900px and below the grid becomes one column. The filters become a drawer from the left (`drawer-w`) under the topbar, and the place panel becomes a bottom sheet (`sheet-h`, at most 62vh) that slides up.
- At 640px and below the wordmark drops so the search box has the row, the topbar buttons collapse to their glyphs, and inputs grow to 1rem so phones don't zoom.
- Gutters: `gutter-panel` in the filters and topbar, `gutter-sidebar` in the place panel, `gutter-dialog` in the dialog. Section rhythm: `section-gap` above each filter section, `panel-gap` below each place-panel section. Fact tiles sit `tile-gap` apart in two columns. The on-map legend and the map status sit `overlay-inset` (12px) from the map's edges; MapLibre's zoom buttons, scale bar and attribution keep its own 10px. Where the legend would cover the scale bar and the attribution, it rises above them.
- Inside a component, space siblings with grid or flex `gap`; sections are spaced by margins (`section-gap`, `panel-gap`). A control row is its name on one line and the sentence that explains it underneath. An option row shows that sentence when chosen, hovered or focused; a check row always shows it.

### Shape, borders and elevation

- Radii are soft and small: `radius` for large frames (search, results, dialog, on-map legend), `radius-sm` for controls and tiles, `radius-xs` inside a control, `radius-swatch` for colour keys, `radius-pill` for chips and the status line, `radius-round` for the info dot.
- Borders do the separating: 1px `hairline` rules under heads and between table rows, and around inputs, chips, popups and the dialog. `shadow` is only for things that float over the page or the map: search results, the on-map legend, popups, info bubbles, the dialog, and the drawer and sheet on small screens.
- Hatching marks the share a composition does not describe: the rest segment of a stacked bar, which has no swatch and must never read as one more group.
- Draw an estimate on the map exactly like a reading. That has been the rule since the owner's decision of 21 September 2026: a modelled unit “should look normal”. The caveat lives in the panel, in the estimate badge (“◌ Modelled”, “◐ Derived”) and the note's first sentence. The legend's hatched estimate key and the word “hatched” in the Estimates hint predate that decision; don't copy them.

### States

- **Hover**: rows, options, results, check rows, ghost buttons and tree twists fill `surface-sunken`. Ghost buttons, child-division rows and tree twists also raise their text to `ink-primary`. Segments and disclosure summaries (“Table view”, “Combines …”) change only their text, to `ink-primary`. Option and group rows change only the fill.
- **Selected** (option rows): `surface-sunken` fill, a 1px `accent` border and the name in `accent`. Group rows define the same look, but the app never switches it on (see Exceptions in the app). A selected segment rises onto `surface-1` with `shadow-seg` and turns 600.
- **Focus**: `outline: 2px solid var(--accent)`, offset 1px on buttons and inputs, -1px inside tight controls (segments, tree rows), 2px around the info dot, and -2px on the filters panel when it takes focus. The place panel, five of its controls and the skip links still fall back to the browser's ring (see Exceptions in the app); give every new control this outline.
- Control state lives in ARIA attributes: `aria-checked` (options, segments), `aria-selected` (search results), `aria-expanded` (info dots, tree twists, the filters toggle). Layout state uses two classes, `.filters-open` on `.app` and `.is-open` on `.sidebar`, and the `hidden` attribute.

### Motion

- Two movements. At 900px and below the place sheet slides with `transform .22s ease`, and choosing a place from search, a breadcrumb or the child list flies the map to it over 800ms. Everything else changes instantly. `prefers-reduced-motion: reduce` collapses both: app.css cuts every CSS duration to .001ms, and MapLibre skips its camera animations.

## Iconography

There is no icon set. Icons are Unicode characters set in the text font, so they inherit colour, size and the reader's platform, and they cost no requests.

| Glyph | Meaning | Where |
| --- | --- | --- |
| ● | Recorded | Status legend, popups (“● Recorded — religion”) |
| ▲ | Not yet available | Status legend, gap notes, fact tiles, the “Named without published shares” note |
| ◼ | Not collected | Status legend, gap notes |
| – | Not applicable | Gap notes and fact tiles (Redonda's fields); the coverage legend has no row for it (see Exceptions in the app) |
| ◐ | Derived from published figures; also the theme toggle at Auto | Status legend, estimate badge (“◐ Derived”), topbar |
| ◌ | Estimated, not published | Status legend, estimate badge (“◌ Modelled”) |
| ☀ ☾ | Theme: light, dark | Topbar theme toggle |
| ☰ | Filters | Topbar button (the glyph alone at phone width) |
| ✕ | Close | Panel heads, dialog, sheet |
| ? | About & sources, at phone width | Topbar |
| i | More about this | Info dot beside headings |
| ⓘ | A note about the record itself: disputed or special-status ground, a territory drawn inside the state that administers it, a lake drawn as a unit, or features merged into one unit | Gap note at the top of the place panel |
| ▸ ▾ | A closed / an open branch | Group tree twist (`aria-label="Show the 7 groups inside Christianity"`) |
| › | Is inside | Breadcrumbs |
| 🗺️ | The app | Brand mark and favicon |

Glyphs beside words (the status icons, ☰, 🗺️) are `aria-hidden`. Inside a control with an `aria-label` (“Switch colour theme”, “Close the details panel”) the label replaces the glyph; hide the glyph there too in new work. The estimate badge's ◐ and ◌ are read out with their word.

There is no logo file. The brand is the 🗺️ mark (`text-brand-mark`) beside the name set in `text-wordmark`, with the subline “countries · first-level · second-level divisions” in `text-count`. The favicon is the same emoji, inlined as a data URI so the page loads nothing extra. It is drawn by the reader's own emoji font, so it differs from platform to platform:

```html
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='26'>🗺️</text></svg>">
```

## Using the system

- Load `tokens.css`, then `components/bundle.css`. Set `data-theme="light"` or `"dark"` on the root element. The app's Auto setting leaves the attribute off and follows `prefers-color-scheme`; `tokens.css` keys on the attribute, so set it from the reader's preference at load and when it changes.
- Components are HTML and CSS. The app renders them from plain scripts with no framework, so copy the markup from each component's preview. The app's ids become classes of the same name: `#app` → `.app`, `#topbar` → `.topbar`, `#search-results` → `.search-results`, `#filters` → `.filters`, `#map-wrap` → `.map-wrap`, `#map` → `.map`, `#legend` → `.legend`, `#map-legend-body` → `.map-legend-body`, `#group-reach` → `.group-reach`, `#group-count` → `.group-count`, `#sidebar` → `.sidebar`, `#sidebar-body` → `.sidebar-body`, `#about-open` → `.about-open` and `#filters-toggle` → `.filters-toggle`. The last two carry the phone-width glyph collapse.
- The layout classes (`.app`, `.filters`, `.sidebar`, `.map-legend`) keep the app's viewport breakpoints. At 900px and below `.filters` becomes a fixed drawer and `.sidebar` a fixed bottom sheet, so use them only for a full-page shell. Inside other layouts, put panel content in your own container at `filters-w` or `sidebar-w`.
- The `text-*` type styles are utility classes for new markup. The components carry the same values in `bundle.css` and need no extra class.
- Colours that depend on a value are computed by `Palette` in `site/js/palette.js`. The tokens hold the steps of the two fixed ramps (`sequential-0` … `sequential-10`, `leading-share-0` … `leading-share-4`) and every fixed input: the categorical slots, the status colours, the tier-1 band hues and the conventional religion family hues. Every other group's hue is computed by `scripts/group_tree.py` into `site/data/groups.json`, and a group's shade at a given share is computed per theme; neither has a token. For a new chart, call the same functions rather than picking shades by eye.
- Charts are DOM, not canvas or SVG. A composition is a flex stacked bar plus a labelled list, so every value stays readable by screen readers, find-in-page and copy-paste.

## Not synced

- **Components are static renditions.** The app builds its markup in plain scripts (`site/js/app.js`, `dashboard.js`, `search.js`, `map.js`) and has no component library to compile, so there is no `components/bundle.js`. Each preview is the app's own rendered markup on `components/bundle.css`, with two changes. The app's ids are the same-named classes (see Using the system). A colour the app computes from a token slot is written as that token, so the card themes as the app does on a fresh load. Group shades, which have no token, are declared per theme in each card as `--shade-*` properties with the values `palette.js` computes.
- **The map does not run in a card.** MapLibre and the PMTiles layers stay in the app; “The map” section records their styling. MapLibre's own controls (zoom, scale, attribution) are not previewed.
- **No fonts or image files.** The type is the system stack, and the only mark is an emoji.
- **One variable renamed.** The app's `--font` is `--font-sans` here. Every other custom property in `app.css` keeps its name.
