# Writing

The copy is written for a reader of the map, not for whoever built it. It names what a figure is, where it came from, and what it is not. Every rule below is drawn from the app's own strings.

## Voice

- **Impersonal and declarative for facts**: “Estimates never count in a group's totals.” “Grey means no record for that unit at all, not even a gap marker.”
- **Imperative for what the reader can do**: “Pick a place”. “Open a family to pick one of its parts instead.” “Type at least two letters”.
- **“You” only for the reader's own actions**, and rarely: “as you zoom in”, “until you pick something else”.
- **Never “we”, “our” or “us”.** The product is “this map”, “this build”, “the panel”, “the legend”.
- **Absence belongs to the publisher, not the app**: “This country does not collect ethnicity.” “France records neither ethnicity nor religion (barred by law)”.
- **State the claim, then rule out the misreading**, with the reason in the same sentence: “Everything else is blank because the figure is missing, not zero.”
- **Examples are real** places, groups and census words, never “e.g.” or filler: “Kerala”, “Islam”, “te reo”, “Pardo”.
- **Long caveats go behind an “i”.** The page keeps only the one fact that changes how a figure is read, such as the basis chip “describes 10.6% of the population”.

## Length and casing

- **Labels are short noun or imperative phrases**, usually one to four words: Population, Share of one group, Follow zoom, Fit to view, As reported.
- **Hints are one sentence**, often verbless, ending in a full stop: “Latest published count, on a log scale.” “States, provinces, regions — wherever they are tiled.” Two app hints run to two sentences (Second-level divisions, Show estimates); see Exceptions in the app.
- **Sentence case everywhere**: headings, buttons, options, filter chips and aria-labels. A few labels are lower-case phrases that read on from what they qualify: the basis chip (“describes 10.6% of the population”), the legend's “fitted to this view” badge and the group list's “in …” asides. Uppercase is CSS only, so type “Detail level”, never “DETAIL LEVEL”. Title case is for proper nouns: World Demographics Map, CIA World Factbook, Scheduled Caste / Tribe.
- **Name a control mid-sentence with its on-screen capital**, without quotes or bold: “change Detail level to see them”, “Fit to view stretches the ramp”.
- **Labels, chips and status lines take no full stop** (“Loading country data”, “No match”, “269 countries loaded”). Sentences do, even short ones: ‘6 of 6 match “Islam”.’ “Fitted to the range on screen.”

## Spelling and punctuation

- **British spelling**: colour, licence, grey, modelled, per cent, untick. No -ize forms.
- **Quotation marks are curly** (“Islam”), **apostrophes straight** (census's, Japan's). Quote inside a quotation with single marks.
- **The dash is a spaced em dash** ( — ) for a gloss or an aside: “No match yet — still loading second-level divisions”. Use the en dash only in computed numeric ranges (55%–65%). Prose ranges say “to”: “from 16.6 yrs to 48.8 yrs”.
- **The spaced middle dot** ( · ) separates metadata, never sentences: “2011 · Census of India 2011”, “158 countries · 11.6K areas · 4 modelled”, “FRA · FR”.
- **The ellipsis is one glyph** (…), for an unfinished example or a loading state.
- **Ampersands only in short labels** (“About & sources”, “Sources & licences”); prose says “and”.
- **No serial comma in a list of nouns**: “population, religion, language and ethnicity”.
- **Colons introduce a value or a list**: “Median age: 42.5 yrs”, “Combines: Islam, Islamic, Muslim, Muslims.”
- **Never**: exclamation marks, emoji in text, “sorry”, “please”, “oops”, marketing words (explore, discover, powerful, easily, simply), “N/A”, “unknown”, “TBD”.

## Numbers

| What | Write | Not |
| --- | --- | --- |
| A count of 10,000 or more | 34.5M, 12.3K, 1.4B (US English; the reader's locale decides) | 34,512,806 |
| A smaller count | 1,739 | 1.7K |
| A share in a column | 54.7%, 0.3%, 100.0% | 55% |
| A share read alone (popup, legend end) | 91%, 9.9% | 90.9% |
| An upper bound | <0.3%, <1.0% | 0.3%, ~0% |
| No value | — | 0, N/A, blank |
| An age | 31.8 yrs | 31.8 years old |
| A sex ratio | 92.3, then “males per 100 females” | 92.3 M/F |
| A year | 2011 | '11, FY2011 |
| A date | February 2026 | 02/2026 |
| Progress | 1 of 2 countries | 1/2 |

Counts go through `Intl.NumberFormat` in the reader's own locale: 34.5m and 1.4bn in British English, 34,5 M and 1 739 in French. Percentages are not localised. The percent sign is attached (91%, 25% or less). Generated counts are numerals, even 0 and 1 (“1 country”); static prose spells small numbers out (“three levels”, “the two ends”).

## The vocabulary of absence

Keep these exact. They are the app's terms of art, and a reader learns them.

| Say | Meaning |
| --- | --- |
| **Recorded** | A value with a named source and reference year |
| **Not yet available** | The figure exists somewhere; this build has not fetched it |
| **Not collected** | The country does not gather it at all |
| **Not applicable** | The question does not apply to this unit |
| **Derived from published figures** / badge **Derived** | Computed from published figures |
| **Estimated, not published** / badge **Modelled** | A modelled estimate; never counted in a group's totals |
| **unit** | Any mapped division, at any level |
| **place** | What the reader picks or searches |
| **first-level / second-level divisions** | The levels below countries. Codes (ADM1) appear only in parentheses in About. |
| **figure** | A published number. Prefer it in prose. |
| **share**, **composition** | A group's percentage; the set of shares |
| **as reported** | A census's own category words |
| **residual answers** | “Other” and “not stated” rows. They are “the absence of an answer, not a group anyone belongs to.” |

- **Never let absence read as zero.** Say so wherever it could: “Blank means the figure is missing at this level — not that the share is zero.”
- **Give absence a cause**: “No ethnicity figure has been fetched for this unit yet.”
- **Quantify partial coverage**: “describes 10.6% of the population”, “Named without published shares: Arabic, Hebrew, English.”
- **A year belongs only on a value.** “Printing one beside ‘not collected’ implies a measurement that was never taken.”
- **Admit rounding**: “the difference is rounding, and it has been put back into the largest groups so the column adds up.”
- **Failures are short and practical**, with no blame and no apology: “No data record for that unit”.

## Labels and accessible names

- An aria-label says what the control does to what: “Hide the filters panel”, “Close the details panel”, “About how the shading is scaled”.
- An info button's label is “About …” plus its subject, so a list of them reads as a table of contents.
- A label names the question, not the abstraction. “A control that said ‘Tier 1’ would be asking the reader to hold the abstraction rather than the question.”
- Keep pipeline words out of the panel (“shard”, “adapter”, file names, commands): “the panel is for a reader of the map”.
