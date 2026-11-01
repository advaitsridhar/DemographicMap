# MapStatus

A pill centred at the top of the map that says what the map is waiting for, or that a click or a load failed, one message at a time.

You provide the message and whether it stays (sticky) or clears itself after 2,200 ms. There is one pill per map; each new message replaces the last.

## When to use

- For background work the map depends on (country data, first- and second-level shards) and for a click that found no record.
- Not for what the map shows (that is the filter summary and the legend) and not for gaps in the data (those are gap notes in the place panel).

## Anatomy

```html
<main class="map-wrap">
  <div class="map" role="application" aria-label="Map of world administrative divisions"></div>
  <div class="map-status" role="status" aria-live="polite" hidden></div>
</main>
```

The pill is absolutely positioned inside `.map-wrap` (`position: relative`): `overlay-inset` from the top, centred with `left: 50%` and `translateX(-50%)`, above the on-map legend. The app sets its text with `textContent` and toggles `hidden`.

## States and variants

| Message | Mode | When |
| --- | --- | --- |
| Loading country data | sticky | at startup, until `DataStore.loadCountries()` resolves |
| Loading first-level data — 42 of 172 countries | sticky | on each shard that lands; the total is the countries asked for whose shard is not loaded yet |
| Loading second-level data — 1 of 185 countries | sticky | the same, for second-level data |
| Something failed to load - see the browser console | sticky | on any uncaught `error` event on the window |
| No data record for that unit | transient | a selection (map click, search, deep link) found no record |
| Couldn't load that country's data -- click again to retry | transient | the same, when that country's shard failed to arrive |

- **Hidden**: the `hidden` attribute, the resting state. A sticky message stays until a later call replaces it or clears it, which happens when loading ends.
- **Transient**: hidden 2,200 ms after it appears.
- There is no error variant: a failure looks exactly like progress, and there is no close control.
- **Width**: shrink-to-fit from `left: 50%`, so the pill is at most half the map wide and longer messages wrap. On a 390px map, "Loading second-level data — 1 of 185 countries" breaks onto two lines.

## Content

- A status line, so no full stop. Sentence case. Progress reads "Loading {first-level|second-level} data — {done} of {total} countries".
- Say what to do when there is something to do ("click again to retry"); otherwise say only what happened.
- Two messages break the house punctuation: the ASCII `--` in "Couldn't load that country's data -- click again to retry" and the ASCII ` - ` in "Something failed to load - see the browser console", where the rest of the interface uses the spaced em dash. Write new messages with the em dash.

## Tokens

`surface-1`, `ink-secondary` (7.7:1 on `surface-1` in light, 9.7:1 in dark), `hairline`, `shadow`, `radius-pill`, `overlay-inset` (12px), `z-map-status` (12). Type: `text-context` (.75rem), the style tokens.json names for `.map-status`.

## Accessibility

- `role="status"` with `aria-live="polite"`: each message is announced without moving focus. While `hidden` it is out of the accessibility tree.
- The pill is not focusable and has no dismiss control, so it must never hold anything a reader has to act on before it clears.
- A transient message is gone after 2.2 s. The live region announces it, but a sighted reader who looks away misses it.

## In the app

- Markup: `site/index.html:142`.
- `status(text, sticky)`, `site/js/app.js:113-120`: a falsy text hides the pill and cancels the timer; a non-sticky message starts a 2,200 ms timer; every call cancels the previous timer.
- Callers: startup `app.js:1387-1389`; shard progress `app.js:1378-1385`; cleared after a view's shards load `app.js:1349`; no record `app.js:1253-1254`; window errors `app.js:1479-1482`.
- CSS: `site/css/app.css:423-428`.
- Computed at runtime: the counts in the progress line, from each DataStore `progress` event.

## Do / Don't

- Do keep it to one line at desktop widths; it wraps at half the map's width.
- Do count progress per item, as the app counts shards: a per-batch counter “sat at "168 of 174" for ten seconds at the end and read as a stall” (`site/js/data.js:178-180`).
- Do clear a sticky message when the work it describes ends, as the app does at `done >= total`.
- Do use the em dash and no full stop in new messages.
- Don't stack a second pill or queue messages; the next call replaces the text.
- Don't use it for an error that needs a decision: it looks the same as progress and cannot be dismissed.
