# ThemeToggle

The topbar's theme button: a glyph-only ghost button that cycles the colour theme from auto to light to dark, shows ◐, ☀ or ☾ for the current setting, and names that setting in its title.

## When to use

- Once, in `.topbar-actions`, between Filters and About & sources. It is the only theme control.

## Anatomy

```html
<button id="theme-toggle" class="ghost-button" type="button" aria-label="Switch colour theme" title="Theme: auto">
  <span data-theme-icon>◐</span>
</button>
```

It is a GhostButton; `[data-theme-icon]` marks the span whose text the script replaces, and the script finds the button by its id.

## States and variants

| Setting | `<html data-theme>` | Glyph | `title` |
| --- | --- | --- | --- |
| auto (default) | removed | ◐ | Theme: auto |
| light | `light` | ☀ | Theme: light |
| dark | `dark` | ☾ | Theme: dark |

- A click moves one step along `["auto", "light", "dark"]` and wraps.
- The setting is stored under the `localStorage` key `wdm-theme` on every change and at start-up. Without storage, reading falls back to auto and writing fails quietly: "private mode: the theme just does not persist" (app.js:96).
- Auto in the app removes `data-theme`, and app.css follows `prefers-color-scheme`. `tokens.css` keys only on the attribute, so with this system set `data-theme` yourself when the setting is auto: read `matchMedia("(prefers-color-scheme: dark)")` at load and on change. `Palette.mode()` reads the same attribute first (palette.js:98-102).
- The three glyphs differ in width (about 29px, 35px and 33px wide buttons in Chromium), so the button and the one after it shift a little as it cycles.

## Content

- The `aria-label` never changes: "Switch colour theme", with British "colour".
- The setting is in `title`: "Theme: auto", "Theme: light", "Theme: dark", the stored value as typed.
- ◐ also stands for "Derived from published figures" in the status legend; in the topbar it means auto.

## Tokens

Those of GhostButton: `ink-secondary`, `hairline`, `radius-sm`, `surface-sunken` and `ink-primary` on hover, `accent` for focus, `text-control`. The button switches every themed token by setting `data-theme`.

## Accessibility

- Name "Switch colour theme"; description "Theme: auto" (or light, dark), from `title`. The glyph span is not `aria-hidden`, but the `aria-label` replaces it.
- The current setting reaches assistive technology only as that description, and the next one is never announced.
- A switch restyles the map (`WorldMap.restyle()`) and recolours the legend (`refreshColors()`), but the place panel is not re-rendered: its inline swatch colours keep the old theme until the next selection.
- Focus: 2px `accent` outline, offset 1px.

## In the app

- `currentTheme()` app.js:83-89 reads `wdm-theme` (default auto); `applyTheme(theme)` app.js:91-104 sets or removes `data-theme`, stores the value, writes the glyph and `title`, then restyles the map and legend once the map exists; the click handler is app.js:106-109.
- `start()` calls `applyTheme(currentTheme())` before anything else (app.js:1259).
- The script finds the button by `id="theme-toggle"`; no CSS rule uses that id.
- Why two explicit themes: "both themes are explicitly selected rather than auto-inverted." (app.css:2-3)

## Do / Don't

- Do set `data-theme` from the reader's preference when the setting is auto, and update it when the preference changes.
- Do recompute every colour that was computed for a theme (map paint, legend, inline swatches) after a switch.
- Don't change the `aria-label` per state; keep the state in `title`.
- Don't reorder the cycle or swap the glyphs: ◐ auto, ☀ light, ☾ dark.
