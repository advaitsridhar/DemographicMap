# Accessibility

The map is a reference tool, so a reader using a keyboard, a screen reader or a phone must get the same facts as anyone else. Most of what follows is how the app already behaves. The contrast table records where its colours fall short. Those values are kept exact here and flagged, not quietly re-tinted.

## Never colour alone

- Every status carries a glyph and its words: ● Recorded, ▲ Not yet available, ◼ Not collected. The glyph is `aria-hidden="true"`; the words are the accessible text.
- Every composition segment also appears in a labelled list with its percentage, and again in a table under “Table view”.
- On Most populous group every unit names its group and share in the popup (“Christianity 55%”). On Share of one group the popup gives only the share (“Share of one group: 55%”), and the filter chips name the group. The legend names each colour, and the place panel names it a third time.
- The band hues are hand-picked from the Okabe–Ito set where it stretches, but nothing checks them for colour-blind separation. Because the map keeps only hue and saturation, some unrelated bands render alike even for normal vision: Dravidian and Hmong-Mien languages, Austroasiatic and Papuan, Afro-Asiatic and Tai-Kadai, and in ethnicity Indigenous American and Middle Eastern and North African. The name in the popup, the legend and the panel is what tells them apart.

## Keyboard

- **Choice controls** (option lists, segmented controls, the group list) follow the WAI-ARIA radio pattern. Each control is one tab stop, on the chosen item or else the first. ArrowDown/ArrowRight and ArrowUp/ArrowLeft move and select, wrapping. Home and End jump. Enter and Space activate the native `<button>`. Selection follows focus.
- **Search** is a combobox over a listbox. ArrowDown and ArrowUp move through the results (wrapping). Enter opens the active result, or the first. Escape closes the list. A polite live region announces “3 results” or “No results”.
- **Escape** closes an open info bubble. Inside the filters panel it also closes the panel and returns focus to the Filters button, as the panel's ✕ does.
- **Skip links** (“Skip to the filters”, “Skip to the data panel”) are the first two tab stops. Each appears at the top left when focused.

## Focus

Draw focus as `outline: 2px solid var(--accent)`, never by colour change alone. The offset is 1px on buttons, inputs, rows and summaries, -1px inside tight controls (segments, tree rows, twists), 2px around the round info dot, and -2px on the filters panel when it takes focus. `accent` clears 3:1 against every surface in both themes, so the ring always shows.

## Roles and names

| Pattern | Markup |
| --- | --- |
| Search | `role="search"` wrapper; `input[role="combobox"][aria-autocomplete="list"][aria-controls][aria-expanded]`; `ul[role="listbox"]` of `li[role="option"][aria-selected]`; a visually hidden `role="status" aria-live="polite"` line |
| Option list, segmented control | `role="radiogroup"` labelled by its heading; `button[role="radio"][aria-checked]` |
| Group list | `role="tree"`; rows are `role="treeitem"` |
| Legend, map status, group count | `aria-live="polite"` (status also `role="status"`) |
| Info dot | `button.info` with an `aria-label` that says what it explains (“About how the shading is scaled”), `aria-expanded` while open; the bubble is `role="note"`. The legend's “Group not yet classified” dot has no `aria-label` and is announced as “i” (see Exceptions in the app). |
| Stacked bar | `role="img"` with an `aria-label` listing every row and share |
| Dialog | native `<dialog>` with `aria-labelledby` its title; the close button is labelled “Close” |
| Decorative glyphs | `aria-hidden="true"` beside words. Inside a control with an `aria-label` (“Hide the filters panel” on ✕) the label replaces the glyph; hide the glyph there too in new work. |

Give every input a label. Visible labels are preferred; `.visually-hidden` is for the search boxes, whose placeholder already shows the example.

## Contrast, as measured

WCAG 2 ratios for the pairs the app actually uses. “Small” means text under 18.66px bold or 24px regular, which covers nearly all of this UI.

| Pair | Light | Dark | Verdict |
| --- | --- | --- | --- |
| `ink-primary` on `surface-1` / `surface-sunken` | 19.2 / 17.1 | 17.4 / 15.7 | Passes |
| `ink-secondary` on `surface-1` / `surface-sunken` | 7.7 / 6.9 | 9.7 / 8.8 | Passes |
| `ink-muted` on `surface-1` | 3.5 | 4.85 | **Fails small text in light** |
| `ink-muted` on `surface-sunken` | 3.1 | 4.4 | **Fails small text in both** |
| `accent` text on `surface-1` / `surface-sunken` | 4.3 / 3.8 | 4.8 / 4.3 | **Fails small text in light; on sunken in dark** |
| `accent-ink` on `accent` (key chips) | 4.4 | 3.6 | **Fails small text in both** |
| `status-serious` text (partial basis chip) on `surface-sunken` | 2.3 | 6.0 | **Fails in light** |
| `status-modelled` / `status-derived` badge text on `surface-1` | 3.6 / 3.2 | 4.7 / 5.4 | **Fail in light** |
| `accent` focus ring and selected borders | 3.8–4.3 | 4.3–5.3 | Passes 3:1 |
| `axis` (info dot ring) on `surface-1` | 1.75 | 1.5 | Below 3:1 |
| `hairline` input borders on their surfaces | 1.15–1.3 | 1.1–1.25 | Below 3:1; the fill marks the field |

When you add text, put meaning in `ink-primary` or `ink-secondary`. Keep `ink-muted` for text a reader can safely skip.

## Motion and zoom

- `prefers-reduced-motion: reduce` collapses every animation and transition: CSS durations drop to .001ms and MapLibre skips its camera flights. Otherwise the place sheet slides for .22s at 900px and below, and the map flies to a chosen place over 800ms.
- Inputs are 1rem at phone width so iOS does not zoom the page on focus. The viewport allows zoom to 5×; never disable it.
- The filters panel and the group list scroll on their own (`overscroll-behavior: contain`), so a scroll that reaches the end of the list stops there. The place panel, the child list and the search results do not set it yet.
