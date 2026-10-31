# The map

The map is the page. It draws the world's divisions as flat fills on a plain ground, with no basemap imagery, no relief and no text labels at any zoom. Names come from the popup and the place panel, so the colours carry the whole surface.

## Ground

- **Sea** is `water`. It is both the MapLibre background and the map element's own background.
- **Land with nothing drawn** is `land-base`. Every unit's fill falls back to it when the view gives that unit no colour.
- **Land inside no unit is still land.** Where a country's second level does not tile it (Tonga and Vanuatu today), a `land-base` fill goes underneath from zoom 6.25. “Ground drawn as ocean is a false statement about the world, and the worse of the two.”
- Land and sea differ mostly in hue (1.05:1 in light). Keep the fills between them and the sea legible by luminance, as the ramps do.

## Units and levels

Three levels of units, each a fill plus its own boundary lines. The level shown follows the zoom unless the reader pins one under “Detail level”.

| Level | Shown from | Shown to | Cross-fade |
| --- | --- | --- | --- |
| Countries (admin 0) | zoom 0 | 4.4 | fades out to 4.75 |
| First-level divisions (admin 1) | 3.6 | 7.4 | fades in from 3.25, out to 7.75 |
| Second-level divisions (admin 2) | 6.6 | 22 | fades in from 6.25 |

- The level that answers hover and clicks switches at zoom 3.6 and 6.6. The map opens at zoom 1.7 and is clamped to 0.6–12; pinning second-level divisions raises the floor to 2, where their tiles start.
- Fills are opaque and cross-fade over 0.35 of a zoom step, so the arriving level covers the departing one rather than popping in.
- Each unit's colour is pushed in from the active view (`["coalesce", ["feature-state", "color"], land]`). The map never reads a colour from the tiles.

## Boundaries

- Lines are `boundary`, at opacity 0.9. Width grows with zoom on all levels: 0.3px at zoom 0, 0.6px at zoom 6, 1px at zoom 12.
- Second-level borders fade in when that level is pinned at world view: opacity 0.15 at zoom 2, 0.35 at zoom 5, 0.9 from 6.6. Romania's 3,181 communes would otherwise grey the whole country into a texture that “read as a different kind of data from Hungary's or Bulgaria's beside it”.

## Hover and selection

- One outline layer per level, in `ink-primary`: **selected** 2.4px at full opacity, **hover** 1.4px at 0.7. There is no fill change and no glow.
- Hovering a unit opens the popup: the unit's name in `text-row` at 600, then one line in `ink-muted` that reads the active view:
  - “Population: 9.5M”
  - “Median age: 42.5 yrs”
  - “How concentrated: 48%”
  - “Christianity 55%”
  - “● Recorded — religion”
- The popup is `surface-1` with a `hairline` border, `radius-sm` and `shadow`, at most 240px wide, with no tip.

## Overlays and controls

- **The on-map legend** sits bottom-left, `overlay-inset` from the edges, on `surface-1` at 92% with an 8px backdrop blur. It appears only while the filters panel is hidden: “Hiding the controls is a request for more map, not for a map whose colours mean nothing.”
- **The map status** line sits top-centre, `overlay-inset` from the top: a `radius-pill` on `surface-1`. It says what is loading (“Loading first-level data — 1 of 2 countries”) and reports failures (“No data record for that unit”).
- **Zoom buttons** are top-right, with no compass. The **scale bar** and the **attribution** sit at the bottom right. The attribution is required by CC BY: “geoBoundaries CC BY 4.0 · CIA World Factbook (public domain) · Natural Earth”. The on-map legend must not cover them: where it would, it rises above them by their measured height (`--map-controls-h`), which happens at every width of 900px and below, where it spans the map, and on a desktop map too narrow for the two side by side.
- MapLibre's own controls keep its default light styling and Helvetica/Arial text in both themes. See Exceptions in the app.

## Themes

The map reads `water`, `land-base`, `boundary` and `ink-primary` from CSS each time it builds its style. A theme change from the toggle rebuilds the style and repaints every unit with the new theme's ramp, so the map's colours come from the same tokens as the panels. With Auto, an OS switch is not caught live (see Exceptions in the app).

## Boundaries are not claims

Geometry is geoBoundaries' global composite (CGAZ). It simplifies polygons, fills gaps along shared edges, and draws disputed areas by US Department of State definitions. The 19 disputed and special-status areas it carries are labelled as such in the panel, with an ⓘ note that begins “Disputed or special-status territory as delimited by geoBoundaries CGAZ”. The app still counts them in “269 countries loaded”, and its breadcrumb calls them “Country” (see Exceptions in the app). Say so wherever a boundary could be read as a position.
