# GhostButton

The app's one style for action buttons: a transparent button with a hairline border for chrome actions, such as opening the filters, switching the theme, opening About, and closing a panel or the dialog.

## When to use

- For every action in the topbar, the filters panel head, the place sheet and the dialog head. The app has no filled or primary button.
- Not for choices. Options, segments, check rows and group rows have their own controls with a checked state; this button has none.

## Anatomy

```html
<!-- words -->
<button class="ghost-button about-open" type="button" aria-haspopup="dialog">About &amp; sources</button>

<!-- glyph and words -->
<button class="ghost-button filters-toggle" type="button" aria-expanded="true"
        aria-controls="filters" title="Hide the filter panel">
  <span aria-hidden="true">☰</span> Filters
</button>

<!-- glyph only -->
<button class="ghost-button" type="button" aria-label="Hide the filters panel">✕</button>
```

## States and variants

- **Rest** — transparent fill, `ink-secondary` text, 1px `hairline` border, `radius-sm`, padding `.38rem .6rem`, `.8rem` text.
- **Hover** — `surface-sunken` fill, `ink-primary` text.
- **Focus** — `:focus-visible` draws a 2px `accent` outline, offset 1px.
- **No pressed, disabled or selected style.** A toggle shows its state only through `aria-expanded` and `title` (the filters toggle).
- **Placement** — `.filters-head button` and `.dialog-head button` take `margin-left: auto`, which pushes the ✕ to the right; `.sidebar-close` pins the sheet's ✕ `.6rem` from the top right and is shown only at 900px and below.
- **Phone (640px and below)** — `.filters-toggle` and `.about-open` collapse to ☰ and a CSS "?" (see Topbar).

## Content

- Words in sentence case: "Filters", "About & sources".
- A glyph beside words is decoration and takes `aria-hidden="true"` (☰).
- A glyph-only button says what it does in `aria-label`, verbatim from the app: "Hide the filters panel", "Close the details panel", "Close", "Switch colour theme".
- Glyphs are Unicode text in the button's own font and colour: ✕ (U+2715) to close, ☰ for the filters, ◐ ☀ ☾ for the theme.

## Tokens

`ink-secondary`, `ink-primary` (hover), `surface-sunken` (hover), `hairline`, `accent` (focus), `radius-sm`, `text-control` (.8rem).

## Accessibility

- Always `type="button"`.
- Every glyph-only button needs an `aria-label`; without one its name would be the glyph.
- `ink-secondary` on `surface-1` is 7.7:1 in light and 9.7:1 in dark. The `hairline` border is about 1.3:1 against `surface-1` in light and 1.2:1 in dark, so the words, not the edge, identify the button.
- At 640px and below the About button's accessible name becomes "?About & sources", because the CSS "?" is counted (Chromium).

## In the app

- Six in the app, all static markup: `#filters-toggle`, `#theme-toggle` and `#about-open` in the topbar (index.html:37-44), `#filters-close` in the filters head (51-52), `#sidebar-close` in the place sheet (146), `#about-close` in the dialog (164). CSS app.css:173-182.
- Actions in app.js: the filters toggle 578; the filters ✕ 579-582, which also returns focus to the toggle; the sheet's ✕ 1294; About 1295; the dialog's ✕ 1296; the theme button 106-109.
- Nothing about the button is computed at runtime except the toggles' `aria-expanded`, `title` and theme glyph.

## Do / Don't

- Do write the action into the `aria-label` of a glyph-only button ("Close the details panel"), not the glyph's name.
- Do return focus to the button that opened a panel when its ✕ closes it, as the filters ✕ does.
- Don't use it for a selected/unselected choice; it cannot show one.
- Don't put it on `surface-sunken`: the hover fill is `surface-sunken`, so there the hover would show only as a change of text colour.
