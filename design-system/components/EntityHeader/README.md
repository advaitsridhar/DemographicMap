# EntityHeader

The opening block of the place panel: where the selected place sits in the hierarchy, its name, and one line that identifies it — ISO codes for a country, the country for a division.

## When to use

- Once, first, for every selected record. Disputed ground and water get it too: their panel is this header, the record note and the sources, and nothing else.
- Not as a heading inside the panel. Topics below it use PanelSection's `h3`.

## Anatomy

```html
<header class="entity-head">
  <p class="entity-breadcrumb"><button type="button" data-goto="IND">India</button> › <button type="button" data-goto="1811400B45534780755480">Kerala</button> › Second-level division</p>
  <h2 class="entity-name">Malappuram</h2>
  <p class="entity-sub">India</p>
</header>
```

- `.entity-head` — the block, closed by a hairline rule.
- `.entity-breadcrumb` — the ancestors as buttons, then the level word. A flex row that wraps.
- `.entity-breadcrumb button` — an ancestor: accent, underlined, no button chrome.
- `.entity-name` — the place, the largest text in the app.
- `.entity-sub` — the codes or the country.

## States and variants

The record's `level` decides the variant; no class or attribute changes.

| Level | `.entity-breadcrumb` | `.entity-sub` |
| --- | --- | --- |
| `admin0` | `Country` | `FRA · FR`: ISO3 · ISO2, or the record id when there are no codes (Abyei: `111`) |
| `admin1` | country button, then `› First-level division` | the country's name: `India` |
| `admin2` | country button `›` parent button `› Second-level division` | the country's name |

- The parent button appears only when the parent is not the country and its record is loaded. Otherwise an `admin2` trail is the country button, then `› Second-level division`.
- When the country record is not loaded there is no country button and `.entity-sub` is empty; an `admin1` breadcrumb is then the level word alone.
- Ancestor buttons keep their case: the browser's own stylesheet gives `<button>` `text-transform: none`, which the breadcrumb rule does not override, so the trail reads “India › FIRST-LEVEL DIVISION”.

## Content

- Type the level words in sentence case and let CSS uppercase them: `Country`, `First-level division`, `Second-level division`.
- Separate items with › (U+203A) and single spaces. The app joins the trail with one space.
- Print the name as published, punctuation and diacritics kept: `Gaza, Gaza Strip`, `Île-de-France`.
- Keep the subtitle to identity: codes joined with ` · `, or the country's name. No units, years or notes. The unit of a figure “used to be appended to the *place's* subtitle, where it read as part of the place's identity … which told the reader nothing about Kerala” (`site/js/dashboard.js:106–108`).

## Tokens

- Colour: `hairline` (the rule), `ink-muted` (breadcrumb and subtitle), `accent` (ancestor buttons), `ink-primary` (the name, inherited).
- Type: `text-breadcrumb`, `text-place-name`, `text-subtitle` (`.entity-sub`, .76rem at the normal line height).
- Space: .7rem above the rule and .9rem below it, literals in `bundle.css`.

## Accessibility

- The name is the panel's one `h2`; topics below it are `h3`. The `header` sits inside the `aside`, so it is not a banner landmark.
- Ancestors are real `<button type="button">`s named by their text. Tab reaches them; Enter or Space selects that place and flies the map to it.
- The buttons have no focus rule of their own, so the browser's default ring shows.
- The › separators are plain text and are read aloud.
- Contrast: `ink-muted` on `surface-1` is 3.5:1 in light, below 4.5:1 for the 11.2px breadcrumb and the 12.2px subtitle (4.85:1 in dark). Accent text is 4.3:1 in light. Both are the source's values, flagged.

## In the app

- `breadcrumb()` `site/js/dashboard.js:441`, `subtitle()` `site/js/dashboard.js:562`, the template in `render()` `site/js/dashboard.js:500–504`. CSS `site/css/app.css:457–469`.
- Computed at render: the trail from `DataStore.country(record.country)` and `DataStore.get(record.parent)`, the subtitle from `record.codes`.
- After `innerHTML` is set, every `[data-goto]` button gets a click listener (`site/js/dashboard.js:556–558`) that calls the navigator set at `site/js/app.js:1263–1266`.
- Disputed and water records return before that wiring (`site/js/dashboard.js:514–518`), so their ancestor buttons do nothing.
- You provide the markup; the record's name, level and codes; and each ancestor's id and name.

## Do / Don't

- Do give every ancestor its own `button` with `data-goto` set to that record's id.
- Do type level words in sentence case.
- Don't put units, years, sources or notes in `.entity-sub`.
- Don't add a parent button that repeats the country, or a separator other than ›.
