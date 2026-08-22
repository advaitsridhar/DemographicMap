# Entity record schema

Every place in `site/data/` — country, first-level division, second-level division —
is one JSON object with the same shape. The contract below is what the app renders
and what every `scripts/fetch_*` adapter must emit.

## The core rule

**A missing value is never a bare `null`.** It is an object saying *why* it is
missing:

```json
{ "status": "not_collected", "note": "France does not collect ethnicity; statistiques ethniques are barred by law." }
```

| `status` | Meaning | Who asserts it |
|---|---|---|
| `not_collected` | The country does not gather this at all. | A hand-maintained policy table, never inference. |
| `not_available` | It exists somewhere; this build has not fetched it. | The adapter, when a source returns nothing. |
| `not_applicable` | Meaningless for this entity (a capital of an ocean). | The adapter. |

`common.gap(status, note)` builds these; `common.is_gap(value)` tests for them;
`Fmt.isGap` / `Fmt.gapStatus` do the same in the browser.

## A value with provenance

Scalars carry their source and reference year, because reference years differ wildly
between countries and a bare number invites false comparison:

```json
"population": { "value": 33406061, "year": 2011, "source": "Census of India 2011, table C-01" }
```

`common.measure(value, year=, source=, unit=)` builds these.

## Compositions

Religion, language, ethnicity and ancestry are arrays of shares, largest first:

```json
"religion": [
  { "group": "Hindu", "pct": 54.7 },
  { "group": "Muslim", "pct": 26.6 },
  { "group": "Christian", "pct": 18.4 }
]
```

- `pct` is a percentage of the entity's population, `null` when the source names a
  group without publishing its share (paired with `"pct_status": "not_available"`).
- `bound` is `"<"` or `">"` when the source published an inequality (`"<1%"`). The
  UI renders the bound rather than promoting it to an exact value.
- `count` is the underlying absolute count when the source gave one.
- A sibling `"<field>_note"` carries the classification caveat — what question was
  asked, whether it was voluntary, whether responses are multi-select.
- A sibling `"<field>_year"` carries the reference year, and is only rendered when
  the field actually holds values.

## Full record

```json
{
  "id": "1811400B45534780755480",
  "level": "admin1",
  "name": "Kerala",
  "parent": "IND",
  "country": "IND",
  "point": [76.45069, 10.54374],
  "bbox": [74.868, 8.2925, 77.4123, 12.7956],

  "capital": "Thiruvananthapuram",
  "largest_settlement": "Kochi",
  "largest_settlement_population": { "value": 1508000, "source": "Natural Earth populated places (CC0)" },

  "population": { "value": 33406061, "year": 2011, "source": "Census of India 2011, table C-01" },
  "median_age": { "status": "not_available" },
  "sex_ratio": { "value": 1084, "unit": "females_per_1000_males", "year": 2011, "source": "..." },
  "life_expectancy": { "value": 68.2, "unit": "years", "source": "..." },

  "religion": [ { "group": "Hindu", "pct": 54.7 } ],
  "religion_note": "India's next census was postponed; 2011 remains the latest official round.",
  "language": { "status": "not_available" },
  "ethnicity": { "status": "not_collected", "note": "India does not collect ethnicity..." },

  "adapter_hint": "Census of India 2011 tables C-01 and C-16: python -m scripts.fetch_census.india_census --level district",
  "match": "curated:name",
  "sources": [ { "field": "religion/population", "name": "...", "url": "...", "license": "..." } ]
}
```

### Field notes

| Field | Notes |
|---|---|
| `id` | geoBoundaries `shapeID` for ADM1/ADM2; the ISO3 code for countries. This is also the vector tile's promoted feature id, which is what lets the map colour features without a second lookup table. |
| `parent` | The containing entity's `id`. CGAZ carries no ADM2→ADM1 link, so `build_entities.py` derives it by point-in-polygon and reports how many units it resolved. |
| `bbox` | `[west, south, east, north]`, used to fly the map to a search hit. `null` for entities with no polygon. |
| `sex_ratio.unit` | Either `females_per_1000_males` (census convention in South Asia) or `males_per_1000_females` (Factbook convention). Always read the unit. |
| `match` | How a statistical row was joined to this shape (`curated:name`, `curated:alias`, `curated:prefix`, `adapter:name`, `adapter:name+state`). A bad join is auditable rather than invisible; a `+state` suffix means the row named its parent division, which is what separates the thirty-one US counties called Washington, or India's two Hamirpurs, from each other. A row whose name is ambiguous and that names no parent is refused rather than guessed. |
| `disputed` | `true` for geoBoundaries' numeric special-status polygons. No demographic source is joined to them. |
| `geometry_available` | `false` for Factbook entities that CGAZ folds into their administering state. |
| `adapter_hint` | The exact command that would fill an empty unit, surfaced in the UI. |

## Sidecar files

| File | Contents |
|---|---|
| `admin0.json` | Every country, loaded with the page. |
| `admin1/{ISO3}.json`, `admin2/{ISO3}.json` | Per-country shards, lazy-loaded. |
| `search-index-0.json` | Countries + first-level divisions. Rows are positional arrays `[id, name, level, country, bbox, parentName]` — about 40% smaller than the equivalent objects across 52k entities. |
| `search-index-2.json` | The same for second-level divisions; fetched in the background. |
| `coverage.json` | Per country, per level, per field: how many units are `present` / `not_available` / `not_collected`. |
