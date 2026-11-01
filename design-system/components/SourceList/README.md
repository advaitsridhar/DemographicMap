# SourceList

The list of every source behind a place's figures, each with its year and licence, always closed by the boundary source. The About dialog uses the same list for the map as a whole.

## When to use

- As the last section of every place panel, under the heading "Sources", even when the place has no figures.
- In the About dialog, under "Sources & licences", for the sources of the whole map.
- Not to explain why a figure is missing: that is a GapNote or a Note.

## Anatomy

```html
<section class="panel"><div class="panel-head"><h3>Sources</h3></div>
  <ul class="source-list">
    <li>Census of India 2011, table C-01 (Registrar General &amp; Census Commissioner) — 2011 · Government of India open data (GODL-India)<br><span style="color:var(--ink-muted)">India's next census was postponed; 2011 remains the latest official round.</span></li>
    <li><a href="https://www.wikidata.org/wiki/Q1186" target="_blank" rel="noopener noreferrer">Wikidata</a> — CC0</li>
    <!-- five more of Kerala's sources -->
    <li>Boundary: <a href="https://www.geoboundaries.org/" target="_blank" rel="noopener noreferrer">geoBoundaries</a> CGAZ — CC BY 4.0</li>
  </ul></section>
```

- `.source-list`: the list, unbulleted, rows .35rem apart.
- `<li>`: one source. The name (a link when it has a URL), then " — " and the meta, then the note on its own line.
- The note: `<br>` and a `<span style="color:var(--ink-muted)">`, the only inline `var()` the app's panel writes (its other inline colours are hex).
- The boundary row: always last, always present.

## States and variants

- **Linked or plain**: a source with a URL becomes `<a href="…" target="_blank" rel="noopener noreferrer">`; one without is plain text.
- **Meta**: " — " then year and licence joined by " · " ("2011 · Government of India open data (GODL-India)"), the licence alone ("Public domain", "CC0"), or the year alone ("2011", after Antigua and Barbuda's Statistics Division census). Nothing when both are missing.
- **With a note**: the note follows on its own line in `ink-muted`.
- **Boundary only**: a place with no other sources (El Piedrero, Ecuador) still lists "Boundary: geoBoundaries CGAZ — CC BY 4.0".
- **About dialog** (`#about-sources`): seven fixed sources, every one linked. Name, licence and use are joined with an ASCII " - ": "Natural Earth - Public domain (CC0) - code concordance and largest-settlement points."

## Content

- Name the source the way it names itself, in full: "European Social Survey (ESS ERIC), ESS rounds 7, 8, 9, 10, 11 (2014-2024), national samples pooled: religion".
- Give the year alone, then the licence as published: "2023 · CC BY-NC-SA 4.0 (ESS ERIC)".
- List each source once. The app drops repeats with the same name and URL, and skips a source with no name.
- Keep a note to one or two sentences about the source itself: "Published for India and the states only; the table's district column is zero on every row."
- In new work, use the panel's punctuation (" — " before the meta, " · " inside it). The About list's ASCII " - " does not follow the brand book's em dash and middle dot.

## Tokens

`text-note` at line-height 1.45 (rows, .72rem), `ink-secondary` (rows), `accent` (links), `ink-muted` (notes). The list sits on `surface-1`; in the dialog, on the dialog's `surface-1` inside `gutter-dialog`.

Contrast in light: `accent` links measure 4.3:1 on `surface-1` and `ink-muted` notes 3.5:1, both below 4.5:1. In dark both pass (4.8:1 and 4.9:1).

## Accessibility

- Links are underlined by the browser, so they do not rely on colour.
- Links open a new tab (`target="_blank"`) without saying so. Say it in words when you reuse the pattern.
- There is no `:focus-visible` rule for `.source-list a`. Focus shows the browser's default ring.
- The note is plain text in the same list item, read straight after the source.

## In the app

- `sourceList(record)`, `site/js/dashboard.js:459–475`: dedupes on name plus URL, builds each row, then appends the boundary row (472).
- About: `renderAboutSources()`, `site/js/app.js:1458–1477`, fills `<ul id="about-sources" class="source-list">` (`site/index.html:190`).
- In the dialog, `.source-list li` (.72rem, 1.45) is more specific than `dialog li` (.8rem, 1.6), so the list keeps its panel size there.
- CSS: `site/css/app.css:517–519`.
- You provide each source's name, URL, year, licence and note. No colour is computed.

## Do / Don't

Do:
- End every list with the boundary row, so a place with no figures still says where its outline came from.
- Give every source its year and licence when it has them.
- Keep notes about the source; a figure's own caveat goes behind its heading's "i".

Don't:
- Don't leave Sources out of a panel. It is the one section every place shows, disputed and water units included.
- Don't shorten a source's name. It is how a reader finds the table.
- Don't make the name a link when there is no URL to give.
