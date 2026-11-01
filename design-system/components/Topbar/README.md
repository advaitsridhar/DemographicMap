# Topbar

The bar across the top of the page that holds the brand, the search box and three ghost buttons (Filters, theme, About & sources), and collapses to the mark, the search box and three glyphs on a phone.

## When to use

- Once, as the first child of `.app` (grid area `top`). It is the only home of the search box and of the buttons that open the filters panel and the About dialog.

## Anatomy

```html
<header id="topbar" class="topbar">
  <div class="brand">
    <span class="brand-mark" aria-hidden="true">🗺️</span>
    <span class="brand-text">
      <strong>World Demographics Map</strong>
      <span class="brand-sub">countries · first-level · second-level divisions</span>
    </span>
  </div>

  <div class="search" role="search">…</div>   <!-- see Search -->

  <div class="topbar-actions">
    <button id="filters-toggle" class="ghost-button filters-toggle" type="button" aria-expanded="true"
            aria-controls="filters" title="Hide the filter panel">
      <span aria-hidden="true">☰</span> Filters
    </button>
    <button id="theme-toggle" class="ghost-button" type="button" aria-label="Switch colour theme" title="Theme: auto">
      <span data-theme-icon>◐</span>
    </button>
    <button id="about-open" class="ghost-button about-open" type="button" aria-haspopup="dialog">About &amp; sources</button>
  </div>
</header>
```

- `.topbar` is a flex row, `align-items: center`, gap `topbar-gap`, padding `.55rem var(--gutter-panel)`, on `surface-1` with a `hairline` bottom rule.
- `.search` is `flex: 1 1 auto`, at most `search-w` wide and centred with `margin-inline: auto`; `.topbar-actions` is a flex row with a `.4rem` gap.

## States and variants

- **Desktop (above 900px)** — mark, wordmark over the subline, search centred, actions at the right. 54px tall. The preview shows this bar, laid out 1200px wide; the 641–766px wrap and the 640px collapse below are described here, not drawn.
- **900px and below** — `.brand-sub` is `display: none`.
- **641px to 766px** — nothing else has collapsed yet, so the wordmark, "☰ Filters" and "About & sources" wrap to two lines and the bar grows to 63px (measured in Chromium with the system font). The app re-measures it, so the drawer still starts below it.
- **640px and below** — gap `.5rem`, padding `.5rem .6rem`; `.brand-text` is hidden, leaving the mark; `.search` drops its maximum width and margin, and its input grows to `1rem` so phones do not zoom. `.filters-toggle` is `font-size: 0` with its glyph span at `.85rem`, so only ☰ shows; `.about-open` is `font-size: 0` and draws a `"?"` at `.85rem` with `::before`. 55px tall.
- **Filters toggle** — `aria-expanded="true"` and `title="Hide the filter panel"` while the panel is open; `"false"` and `"Show the filter panel"` when closed. Nothing changes visually.
- **Theme button** — ◐, ☀ or ☾ with `title` "Theme: auto", "Theme: light" or "Theme: dark" (see ThemeToggle).

## Content

- Wordmark "World Demographics Map"; subline "countries · first-level · second-level divisions", lower case, middle dots.
- Button words in sentence case: "Filters", "About & sources" (typed `About &amp; sources`). Glyphs: ☰ for the filters, ◐ ☀ ☾ for the theme, and ? for About at phone width.
- The toggle's title says "filter panel" and the panel's ✕ says "Hide the filters panel"; settle on one when touching either.

## Tokens

- Colour: `surface-1`, `hairline`, `ink-primary` (wordmark), `ink-muted` (subline).
- Spacing and size: `gutter-panel`, `topbar-gap`, `search-w` (560px), `topbar-h` (52px until measured); `z-topbar` (20).
- Type: `text-brand-mark` (1.35rem, line height 1), `text-wordmark` (.95rem, -.01em, line height 1.2), `text-count` (.7rem subline), `text-search`, `text-control` (buttons).
- The subline is `ink-muted` at .7rem: 3.5:1 on `surface-1` in light, below 4.5:1.

## Accessibility

- `<header>` is the page banner; the search box is `role="search"`.
- The mark is `aria-hidden="true"`, and so is ☰; the toggle's name is "Filters" and it carries `aria-controls="filters"` and `aria-expanded`.
- `aria-haspopup="dialog"` on About & sources. At 640px and below the CSS "?" joins the accessible name, which reads "?About & sources" (Chromium).
- Each button shows a 2px `accent` focus outline, offset 1px. Button borders are about 1.3:1 against `surface-1` in light and 1.2:1 in dark; the words identify them.

## In the app

- Static markup, index.html:17-46. CSS app.css:112-182, with the narrow rules at app.css:564-583 and 585-608.
- `trackTopbarHeight()` app.js:136-147 writes the bar's rounded height to `--topbar-h` on `<html>` and re-measures with `ResizeObserver`: "The topbar's height depends on how its own contents wrap, so it is measured rather than guessed." (app.js:133-134)
- `setPanel()` app.js:175-189 sets the toggle's `aria-expanded` and `title`; `applyTheme()` app.js:91-104 sets the glyph and `title`; About opens the dialog with `showModal()` (app.js:1414).
- The script finds the buttons by id (`filters-toggle`, `theme-toggle`, `about-open`), and the app's phone rules select two of them by id too (`#about-open`, `#filters-toggle`, app.css:571-574); in index.html all three carry only `class="ghost-button"`. In this system those two rules are the classes `.filters-toggle` and `.about-open`, so those buttons take the class as well as the id.

## Do / Don't

- Do keep the order brand, search, actions, and let the brand go first on a phone: "the search box is what people actually use, and it needs the row to itself." (app.css:565-566)
- Do re-measure the bar and write `--topbar-h` whenever its contents can change height.
- Don't add a fourth action without testing 641-766px, where the labels already wrap; give the labels `white-space: nowrap` or collapse them earlier.
- Don't style the toggle as pressed; its state is `aria-expanded`.
