# Wave 2 addendum: knowledge-only mode

Read `BRIEF.md` in this directory first. Everything there still applies, with
one change: **the session's WebSearch budget is exhausted. Do not call
WebSearch; it will be refused.** You are working from what you already know,
plus the packet and the repository.

That changes what you can honestly write:

- **`nso.url`** — give the statistical office's homepage from memory. This is
  the single most useful field: a runner with a real network crawls it for the
  census pages and files, and a wrong homepage costs nothing (it measures as a
  404). Set `"confidence": "recalled"` on it.
- **`latest_census`** — year and which of religion / ethnicity / language it
  asked, from memory, with `"confidence": "recalled"` and a one-line reason
  (e.g. "the 2010 questionnaire had a religion item; the 2020 one dropped it").
  If you do not know, say `null`. These feed `not_collected` declarations, and a
  wrong "not asked" would hide real data, so prefer `null` to a guess.
- **`subnational_sources`** — only publications you can name with real
  confidence (an office's known table series, a well-known HDX or USCB
  workbook). For each, set `"url": null` unless the URL is one you are certain
  of (an office homepage, `data.humdata.org/dataset/...` slugs you have seen
  in this repository's own adapters). The runner searches HDX itself, so an
  HDX guess adds nothing; a *table name or series title* does.
- **`wikipedia`** — leave `country_list_articles` as
  `[{"title": "Religion in {Country}"}, {"title": "Demographics of {Country}"}]`
  and `admin2_samples` empty; the runner reads both titles regardless.
- **Tier honestly.** Without a search, A needs a source you know to be
  machine-readable and public; otherwise B or D. C only when you are sure the
  census does not ask and can name why.
- Add `"mode": "knowledge-only"` at the top level of every finding.

Small countries: two or three sentences and `nso.url` are enough. Do not pad.
