# DataTable

A composition's numbers as a plain table behind a closed “Table view” toggle: every group the source gives, in the source's order, and a total row that shows whether the column adds up.

## When to use

- At the end of every CompositionPanel that has shares, after the list.
- As the full record: it is the only place a folded group or a `0.0%` group appears.
- Not on its own, and not for anything but one composition's shares.

## Anatomy

```html
<details class="table-toggle"><summary>Table view</summary>
  <table class="data-table">
    <thead><tr><th>Group</th><th>Share</th></tr></thead>
    <tbody>
      <tr><td>Scheduled Caste</td><td>9.1%</td></tr>
      <tr><td>Scheduled Tribe</td><td>1.5%</td></tr>
      <tr class="total-row"><th scope="row">Total</th><th>10.6%</th></tr>
    </tbody>
  </table>
</details>
```

- `details.table-toggle` — the toggle, .5rem below the list.
- `.data-table` — full width; the last column is right-aligned in tabular figures.
- `tr.total-row` — the sum, two `th`s, the first with `scope="row"`.

## States and variants

- **Closed** — the default; the app never sets `open`. Only the summary shows: `Table view` in `ink-muted`, `ink-primary` on hover, after the browser's disclosure triangle.
- **Open** — the reader's click puts `open` on the `details`. Column heads are uppercase and muted, every row has a hairline under it, and shares line up on the right.
- **Total row** — `tr.total-row` adds a hairline above and turns `ink-secondary`. It keeps the heads' uppercase and 600 weight, so `Total` displays as “TOTAL”.
- **Total short of 100** — printed as it is: `10.6%` for Kerala's Scheduled Caste / Tribe, whose shares describe part of the population.
- **Bound rows** — print `<0.8%` and count at face value in the total (Gaza: `<0.8%`, `<0.9%`, total `100.0%`). The basis chip leaves bound rows out of its sum, so on a multi-response set the two disagree: Afghanistan's language table totals `153.0%` under a chip titled “Shares sum to 152.0%”.

## Content

- Summary `Table view`; heads `Group` and `Share`; total `Total`. Type them in sentence case; CSS uppercases the heads.
- Rows in the source's order, not sorted and not folded. American Samoa's languages list `English 3.3%` before `other Pacific Islander 4.1%`; the list above sorts them the other way.
- Keep `0.0%` rows: Kerala's religion table ends `Buddhist`, `Jain`, `Other religions (not separately named)`, `Sikh`, all `0.0%`, though the bar and list leave them out.
- One decimal on every share and on the total, as in the list.
- The total exists for one reason: “so a reader can see the column adds up rather than take it on trust” (`site/css/app.css:678–679`).

## Tokens

- `hairline` (row rules and the rule above the total), `ink-muted` (summary and heads), `ink-secondary` (total), `ink-primary` (cells, inherited; the summary on hover).
- Type: `text-legend` (cells), `text-table-head` (heads), `text-note` (summary). The total is .7rem, the size of `text-count`, but keeps the heads' uppercase, 600 weight and .04em tracking.

## Accessibility

- `details` and `summary` are native: Tab reaches the summary, Enter or Space toggles it, and the expanded state is announced.
- The summary has no focus rule of its own, so the browser's default ring shows.
- The table has no `caption` and its column heads no `scope`; the section's `h3` is its only label.
- The total's figure is a second `th` without `scope`, which Chrome exposes as a column header named “100.0%”.
- Contrast: summary and heads are `ink-muted` on `surface-1`, 3.5:1 in light — below 4.5:1 at 11.5px and 10.9px (4.85:1 in dark).
- The module's reason for it: “A table view of the same numbers is one click away for screen readers, print and forced-colours.” (`site/js/dashboard.js:7–8`)

## In the app

- Built inside `compositionPanel()`, `site/js/dashboard.js:373–380`. CSS `site/css/app.css:536–543`, `678–684`.
- Computed at render: the rows are the composition after `toHundred()` (`site/js/dashboard.js:169`), so a partition's tenths match the list; the total is `Fmt.pct1()` (`site/js/data.js:317`) of every numeric share.
- You provide the markup, and each group's name and share, its bound included.

## Do / Don't

- Do list every row the source gives, `0.0%` included, in its order.
- Do print the real total, whatever it comes to.
- Don't open the toggle by default or move it above the list.
- Don't round the rows differently from the list: both read the shares after `toHundred()`.
- Don't sort or fold the table to match the list. The table keeps the source's order and every row; the list is the sorted, folded view.
