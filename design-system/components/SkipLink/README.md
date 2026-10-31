# SkipLink

Two links at the very start of the page that stay off-screen until they take keyboard focus, then appear in the top-left corner and jump past the topbar to the filters panel or the place panel. This page also covers `.visually-hidden`, the class for text that only assistive technology should get.

## When to use

- First in `<body>`, before `.app`: one link per panel a keyboard user needs to reach without tabbing through the topbar.
- Use `.visually-hidden` for a label or live message that has no place on screen but must be read out.

## Anatomy

```html
<a class="skip-link" href="#filters">Skip to the filters</a>
<a class="skip-link" href="#sidebar">Skip to the data panel</a>

<div class="app">
  …
  <aside id="filters" class="filters" aria-label="Map filters" tabindex="-1">…</aside>
  …
  <aside id="sidebar" class="sidebar" aria-label="Selected place details" tabindex="-1">…</aside>
</div>

<label class="visually-hidden" for="search-input">Search for a country, state or district</label>
```

## States and variants

- **At rest** — `position: absolute; left: -9999px; top: 0`: off-screen, but still in the tab order and the accessibility tree.
- **Focused** — `.skip-link:focus` sets `left: 0`. The link sits in the page's top-left corner over the brand, above everything (`z-skip-link`), on an `accent` fill with `accent-ink` text, padding `.6rem 1rem`, and a `radius-sm` corner at the bottom right only. It keeps the browser's underline and focus ring; it sets neither. 160 × 39px and 196 × 39px in Chromium.
- **How it is reached** — the first Tab into the page focuses "Skip to the filters", the second "Skip to the data panel", the third the search box.
- **Followed** — Enter moves focus to the target aside (`tabindex="-1"`). The filters panel draws `:focus-visible` as a 2px `accent` outline inset 2px; the place panel has no rule and shows the browser's ring.
- **Target out of sight** — while the filters panel is closed it is `hidden`: "Skip to the filters" then leaves focus on the page body. That is the default at 900px and below. There, the place panel is also a sheet parked off-screen until a place is picked, and "Skip to the data panel" focuses it unseen.

## .visually-hidden

- `position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap`.
- In the app: the search label ("Search for a country, state or district"), the search's live status line, and the group search label ("Search groups").
- It does not reset margins. The search status `<p>` keeps its `1em` margins and hangs below the topbar. That adds 7px to the scroll height of a topbar that stands alone at desktop width (2px where the bar wraps to 63px, 8px on a phone; measured in Chromium).
- It is for text, not for controls: a focusable element hidden this way would take focus invisibly. The skip links use the off-screen pattern because they must appear on focus.

## Content

- "Skip to the" plus the panel's plain name, in sentence case: "Skip to the filters", "Skip to the data panel". The place panel's landmark is "Selected place details"; the link calls it the data panel.
- Hidden labels say what the control does, in sentence case: "Search for a country, state or district", "Search groups".

## Tokens

- `accent` (fill), `accent-ink` (text), `radius-sm` (bottom-right corner), `z-skip-link` (100).
- The text is the page's 1rem in `--font-sans`; no type style is set.
- White on `accent` is 4.4:1 in light and 3.6:1 in dark at 1rem regular weight, below 4.5:1.

## Accessibility

- They are the first two focus stops, so a keyboard user can leave the topbar in one or two key presses.
- Every target must be focusable (`tabindex="-1"`) and must keep the id the link names.

## In the app

- Static markup, index.html:13-14; CSS app.css:100-110 (`.visually-hidden`, `.skip-link`, `.skip-link:focus`). No script.
- The targets are `#filters` (index.html:48) and `#sidebar` (index.html:145).

## Do / Don't

- Do keep the links first in `<body>` and their targets' ids and `tabindex="-1"`.
- Do give each target a focus style of its own; the filters panel has one, the place panel falls back to the browser's ring.
- Don't hide a skip link with `display: none`, `hidden` or `.visually-hidden`: it has to appear on focus.
- Don't point a link at a panel that can be `hidden` without opening the panel first.
