# Survey brief: find the best subnational demographic source for each country

You are one of several research agents working for the **World Demographics Map**
project (repo at `/home/user/DemographicMap`). The map joins administrative
boundaries (admin1 = states/provinces, admin2 = districts/counties/municipalities)
to religion, ethnicity and language compositions, **and to an explicit record of
where that data does not exist**. Its governing principle:

> An unmatched row is a visible gap. A mis-matched one is invisible, and worse.

Your job is research, not data entry. You will produce, for each country in your
batch, one structured JSON finding describing where the best subnational
religion / ethnicity / language data lives, at what geography, in what format, and
how confident you are. Someone else will fetch and build from it.

## Your one working tool, and the one that does not work

- **`WebSearch` works.** Use it freely. Every URL you report MUST be copied from a
  search result. Search snippets and titles are evidence; quote them.
- **`WebFetch`, `curl`, and anything that opens a URL do NOT work** from this
  sandbox: the egress proxy blocks every external host with `EGRESS_BLOCKED`.
  Do not try. If you do try and it fails, that failure is a fact about the
  sandbox, **not about the source** — never report a block as "the site is down"
  or "the data is not there".
- You may `Read` files in the repo and in the scratchpad. Do **not** modify the
  repo, do not run `git`, do not write adapters, do not write anything except
  your findings files.

## The packet you start from

For each ISO3 in your batch, read
`/tmp/claude-0/-home-user-DemographicMap/9af6d0a7-c732-5c9f-810e-91187f1788a4/scratchpad/survey/packets/{ISO3}.json`.
It tells you: population; whether the country currently has `nothing`
subnational, `partial` coverage, or fields `declared` not-collected; how many
admin1 and admin2 shapes the boundary file draws and a **sample of their names**
(these are the names any source must join to); what the national record holds;
which fields are already filled and from what; and any **routes this project has
already measured as closed** — do not re-research those unless you find something
genuinely new.

The repo's `docs/SOURCES.md` records every source used and every dead end, with
reasons. `grep -n "### " docs/SOURCES.md` lists the sections; read the one for
your country if it exists before searching.

## What to establish, per country

1. **The national statistical office**: name and site.
2. **The latest census**: year, and whether it asked **religion**, **ethnicity**
   (or the local equivalent: caste, nationality/minzu, race, population group,
   ancestry, indigenous status) and **language** (mother tongue, home language,
   main language). "Asked" and "published subnationally" are different facts;
   record both. Note legal bars (e.g. France) and "asked in 1965, never since".
3. **Subnational publications** of those fields: title, URL, publisher, whether
   it is a **census** (a count), a **survey** (DHS, MICS, Afrobarometer, LSMS —
   an estimate from a sample; this project ranks these below any count), a
   **register**, or other. Format: PDF / XLSX / CSV / API / table-builder / HTML.
   **Which geography** — name the level (e.g. "county", "LGA", "district",
   "kabupaten", "NUTS 3") and its count if the search result says. Compare that
   count to the packet's admin1 and admin2 counts and say whether it matches one
   of them, since a table published for 26 counties fills nothing when the
   boundary file draws 166 electoral areas.
4. **Secondary routes** worth checking: HDX (`data.humdata.org`), the US Census
   Bureau's international tables, IPUMS-International (microdata; note it needs
   registration), open-data portals (`open.africa`, `data.gov.xx`), Eurostat for
   EU states, PxWeb / PxStat / `.Stat` instances, and the country's own open-data
   site. Do not list a route you did not find a result for.
5. **Wikipedia, honestly.** Two searches only:
   - The country-level *list* article: search e.g. `"Religion in {country}"
     wikipedia table by state`, `"{country} ethnic groups by region" wikipedia`.
     These list articles sometimes carry a census-sourced table by admin1 —
     that is the realistic Wikipedia route, not 700 district pages.
   - **Three** of the packet's `admin2.sample_names`: search
     `"{name}" {country} wikipedia`. Report whether an article appears to exist
     and what the *snippet* suggests. **Never assert what an infobox contains** —
     you cannot see it. A runner will read the article later; your job is to say
     whether it is worth reading.
6. **Tier** the country:
   - **A** — a count (census/register) of at least one field, published
     subnationally in a machine-readable form (CSV/XLSX/API/HDX), at a
     geography that plausibly joins to admin1 or admin2. Build next.
   - **B** — exists but costly: PDF tables, a table-builder with no API, needs a
     key/registration, or a geography that matches neither level.
   - **C** — the census does not ask (or the state bars it). The right output
     is a `not_collected` declaration with the reason and the evidence.
   - **D** — could not establish; say what you searched.
7. **`replaces_existing`**: `true` if what you found would improve or supersede
   data the packet says is already present (e.g. a census where a survey now
   fills admin1). The repo owner reviews those before anything is pushed.
   `false` if the level/fields in question currently hold nothing.

## Budget and discipline

- Roughly 6–10 searches for a country over 20M people, 3–5 for a small one.
  Stop when you have the answer or when two more searches add nothing.
- Prefer the office's own publication over a mirror; list both if both surfaced.
- Write down what you searched for and did not find — a recorded absence is
  worth more to the next person than silence.
- No invented numbers, years, table names, or URLs. `null` is a valid answer.
- Small islands and microstates: a quick pass. If the packet shows one admin1
  and no admin2, say so and tier it C or D in two sentences.

## Output

Write **one file per country**:
`/tmp/claude-0/-home-user-DemographicMap/9af6d0a7-c732-5c9f-810e-91187f1788a4/scratchpad/survey/findings/{ISO3}.json`

```json
{
  "iso3": "KEN",
  "name": "Kenya",
  "researched_at": "2026-09-10",
  "nso": {"name": "Kenya National Bureau of Statistics", "url": "https://www.knbs.or.ke/"},
  "latest_census": {
    "year": 2019,
    "asks": {"religion": true, "ethnicity": true, "language": false},
    "notes": "Volume IV covers religion and ethnicity by county."
  },
  "subnational_sources": [
    {
      "fields": ["religion"],
      "title": "2019 KPHC - Distribution of Population by Religious Affiliation and County",
      "url": "https://open.africa/dataset/...",
      "publisher": "openAFRICA (mirror of KNBS)",
      "kind": "census",
      "format": "csv",
      "geography": "county",
      "geography_count": 47,
      "matches_boundary_level": "admin1",
      "year": 2019,
      "confidence": "high",
      "evidence": "Search result title names the table and the county breakdown."
    }
  ],
  "wikipedia": {
    "country_list_articles": [
      {"title": "Religion in Kenya", "url": "https://en.wikipedia.org/wiki/Religion_in_Kenya",
       "appears_to_contain": "snippet mentions a census table by county; unverified"}
    ],
    "admin2_samples": [
      {"shape_name": "Kisumu East", "search_hit_title": "Kisumu East Constituency",
       "url": "https://en.wikipedia.org/wiki/Kisumu_East_Constituency",
       "note": "article exists; snippet gives population only"}
    ]
  },
  "tier": "A",
  "tier_reason": "Census religion and ethnicity by county, machine-readable on openAFRICA, 47 counties = admin1.",
  "replaces_existing": true,
  "recommended_action": "Read the openAFRICA CSVs for admin1; sub-counties (admin2, 290) are not covered by Volume IV -- check whether KNBS publishes by sub-county.",
  "searches_run": ["Kenya 2019 census Volume IV religion by county", "..."],
  "not_found": ["religion by sub-county"],
  "summary": "Three to five sentences a person can act on."
}
```

Use `null` for anything you could not establish. Keep `subnational_sources`
ordered best-first. When you finish your batch, reply with one line per country:
`ISO3 tier — one-sentence summary`.
