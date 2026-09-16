# Modelling the blank regions

A methodology for putting estimated demographic compositions on units where no
source has been read — and, just as much, for deciding which of them must stay
blank.

Everything below is measured on this repository's own data. The harness is
`scripts/backtest_estimators.py`; every number in this document can be
re-derived by running it, and should be re-derived whenever the data changes,
because an error budget quoted from memory is not an error budget.

---

## 0. The rule that governs the rest

This map's whole discipline is that **an unmatched row is a visible gap and a
mis-matched one is invisible and worse.** A modelled value is, by
construction, the second kind: it looks exactly like a read one. So the first
question is not "which model" but "how does a modelled value stay
distinguishable from a read one at every layer it passes through" — the
schema, the group index, the filter counts, the choropleth, the panel, the
downloadable data. If it can be mistaken for a census figure anywhere in that
chain, the model has done net harm regardless of its accuracy.

The second rule follows from the first: **a model may fill a gap in what this
map has read. It may never fill a gap in what a state has counted.** Those are
different things, and the repository already tells them apart —
`NOT_COLLECTED_POLICY` marks the fields a country does not ask. Modelling
ethnicity for French departments or Rwandan districts would not be estimating
an unpublished number; it would be manufacturing a statistic about a category
the state has deliberately refused to enumerate, often for reasons rooted in
how that category was used against people. **1,834 admin-1 fields are
`not_collected`. They are out of scope, permanently, and not as a default that
a flag can turn off.**

---

## 1. The shape of the problem

Measured across 3,205 non-disputed first-level units:

| field | observed | `not_collected` (refuse) | blank and modellable |
|---|---:|---:|---:|
| religion | 952 | 711 | 1,542 |
| ethnicity | 961 | 670 | 1,574 |
| language | 492 | 453 | 2,260 |

Sorted by what actually constrains an estimate:

| constraint | admin-1 fields | what it permits |
|---|---:|---|
| Exact residual — parent known, one child missing | 9 | arithmetic, not a model |
| Parent known, population weights present | 2,250 | constrained disaggregation |
| Parent known, **no** population weights | 2,833 | disaggregation with no weights to use |
| ≥5 observed neighbours in-country | 7 | spatial smoothing |
| Nothing known in-country | 276 | nothing defensible |
| `not_collected` | 1,834 | **refused** |

Two things in that table matter more than the rest. **The dominant case by far
is a known national composition and unknown units** — 5,083 fields. And
**2,833 of those have no population weights at all**, which is fatal to
weighted disaggregation: only 79% of admin-1 units and 37% of admin-2 units
carry a population. Raising population coverage is a prerequisite for most of
this work, and it is ordinary data-gathering rather than modelling.

---

## 2. What the evidence rules out

Each estimator below was scored by hiding a real unit's composition,
predicting it from what remained, and comparing. The metric is total variation
distance — the share of the population placed in the wrong group — reported
alongside how often the prediction gets the **leading** group right, because
that is what the choropleth paints.

### 2a. Canonicalise first, or measure your own vocabulary

The national row and the unit rows usually come from different adapters with
different words for the same thing: `Muslim`/`Islam`, `Christian`/
`Christianity`, `Buddhist`/`Buddhism`. Scored on raw labels those read as
total disagreement.

| field | median error, raw labels | median error, canonical tier-2 |
|---|---:|---:|
| religion | 17.4% | 8.7% |
| ethnicity | 41.0% | 10.1% |
| language | 15.6% | 12.0% |

Most of the apparent error in ethnicity was vocabulary. **Any modelling must
happen in canonical group space**, or it will spend its effort fitting
noise it invented. Tier 2 is the right level: tier 1 puts Islam and
Christianity both under "Abrahamic religions", at which everything looks
accurate and nothing is.

### 2b. Borders are real. Do not borrow across them.

| field | estimator | median error | leading group right |
|---|---|---:|---:|
| religion | cross-border 3 nearest | 26.5% | 70.5% |
| religion | national prior (own country) | 8.7% | 85.8% |
| ethnicity | cross-border 3 nearest | 59.7% | **45.4%** |
| ethnicity | national prior (own country) | 10.1% | 90.3% |
| language | cross-border 3 nearest | 46.3% | 51.0% |
| language | national prior (own country) | 12.0% | 85.1% |

Geographic proximity across a border predicts ethnicity **worse than chance**.
This is not a subtle result and it has a clear cause: these categories are
made by states. Each census asks its own question, in its own category scheme,
shaped by that country's official languages and its own history of counting
people. A unit 40 km away on the other side of a border may be answering a
different question entirely. **Cross-border spatial smoothing is excluded.**

### 2c. Within a country, space works — where it is available

| field | estimator | median error | leading group right |
|---|---|---:|---:|
| religion | 3 nearest in-country, IDW | 5.1% | 92.4% |
| religion | country mean | 7.3% | 89.7% |
| religion | national prior | 8.7% | 85.8% |
| ethnicity | 3 nearest in-country, IDW | 5.2% | 92.0% |
| ethnicity | national prior | 10.1% | 90.3% |
| language | 3 nearest in-country, IDW | 5.1% | 89.0% |
| language | national prior | 12.0% | 85.1% |

In-country spatial smoothing beats every alternative on every field.

---

## 3. The finding that constrains the whole programme

The backtest scores units that **have** a composition. Those units sit in
better-covered neighbourhoods than the blank ones do, by construction. The
correction is decisive:

| field | blank units with any observed neighbour in their own country |
|---|---:|
| religion | **7%** |
| ethnicity | **9%** |
| language | **0%** |

**The blanks are not scattered among covered units. They are whole countries.**
The estimator that works — in-country spatial smoothing, ~92% on the leading
group — is unavailable for 91% of the units we would want to fill, and for
100% of the language gaps.

So for the great majority of blank regions the only available estimator is the
national prior. And the national prior has a property no accuracy number
captures: **it has zero within-country variance.** It paints every unit in a
country identically. Measured against the countries where units are known:

| field | a unit differs from its own country's mean by (median / p90) | countries where units do **not** share one leading group |
|---|---:|---:|
| religion | 6.6% / 33.7% | 28 of 62 (45%) |
| ethnicity | 8.7% / 33.2% | 27 of 62 (44%) |
| language | 11.6% / 48.6% | 13 of 24 (54%) |

**In roughly half of all countries, the units do not share a single leading
group.** A national-prior fill would paint each of those countries one flat
colour that is demonstrably wrong somewhere inside it — and would do so on a
map whose entire purpose is to show that variation. The estimate would not
merely be imprecise; it would assert homogeneity as a finding, when
homogeneity is exactly what we failed to measure.

---

## 4. The confidence gate

Where estimates are produced, their quality is predictable in advance.
Estimator *disagreement* — the maximum pairwise distance between the
independent estimators available for that unit — is a strong signal:

| agreement between estimators | religion: median err / leading right | ethnicity | language |
|---|---:|---:|---:|
| within 5% | 3.0% / 98.1% | 1.0% / 97.6% | 1.1% / 97.9% |
| 5–15% | 4.1% / 93.0% | 6.2% / 92.6% | 4.6% / 92.6% |
| 15–30% | 11.8% / 87.5% | 8.3% / 94.8% | 13.5% / 83.0% |
| over 30% | 10.4% / 87.5% | **28.1% / 62.7%** | **34.5% / 67.8%** |

Distance to the nearest observed unit is a weaker, secondary signal (religion
2.9% median error under 50 km, 7.3% beyond 400 km).

**The gate: publish only where independent estimators agree within 5%.** That
band holds ~98% leading-group accuracy, which is comparable to the noise
already present in the read data. The over-30% band is worthless — for
ethnicity it gets the leading group right less often than the national prior
does — and must be withheld, not shown with a wide interval.

---

## 5. The methodology

### Tier 0 — Exact residual *(not a model)*
Parent composition known, all children but one known, populations known. The
missing child follows by subtraction. No assumption beyond the arithmetic.
Applies to 9 fields. Should be labelled `derived`, not `modelled`.

### Tier 1 — Constrained disaggregation
Parent known, children unknown. Allocate the parent's counts across children
by population weight, then rake so the children sum exactly to the published
parent (the repository's `whole_hundred` largest-remainder rounding already
does the last step for percentages).
*Assumption:* composition is uniform within the parent — the assumption
section 3 shows is wrong in ~45% of countries. **Defensible only when the
parent is small or the units are being split for geometric reasons**
(a source unit that maps onto exactly the union of several shapes: Ennedi into
Ennedi-Est and Ennedi-Ouest, the six Malagasy provinces onto 22 regions).
Aggregation in the other direction — Kavango East and West into one Kavango —
is exact and needs no tier.

### Tier 2 — In-country spatial smoothing
Inverse-distance weighting over the 3 nearest observed units in the same
country, in canonical tier-2 space, raked to the national total where one
exists. ~92% leading-group accuracy. **Available for 7–9% of blanks.**

### Tier 3 — National prior
Available broadly; **not recommended for publication** for the reasons in
section 3. If ever used, it must be rendered as a country-level statement
rather than as per-unit values, so it cannot masquerade as subnational
variation.

### Refused
- Any `not_collected` field (1,834).
- Any cross-border inference (section 2b).
- Any estimate failing the section 4 gate.

---

## 6. How a modelled value must be represented

The repository already has the invariant that does most of this work: **a
composition is a `list`; anything else is a gap.** Every existing consumer —
the choropleth, `check_percentages`, the group index, the filter counts —
keys off `isinstance(value, list)`.

So a modelled value must be **a dict with a status, never a list**:

```json
{
  "status": "modelled",
  "estimate": [{"group": "Christianity", "pct": 71.2}, ...],
  "method": "tier2-idw-3",
  "inputs": ["<unit id>", "<unit id>", "<unit id>"],
  "agreement": 0.031,
  "backtest": {"leading_group_right": 0.976, "median_error": 0.010, "n": 333},
  "note": "No source has been read for this unit. This is an estimate from
           the three nearest units in the same country that were read, not a
           published figure, and it is not evidence of what the census says."
}
```

This is not decoration. Because it is a dict, **every existing code path
treats it as a gap until something explicitly opts in** — which is the correct
default and comes for free from the current architecture. Then, deliberately:

- **Never** in the dominant-group choropleth on the same footing as read data.
  At the very best measured accuracy, 1 unit in 12 would be painted the wrong
  colour, and a wrong solid colour is indistinguishable from a right one.
  Modelled units render as hatch/stipple, or not at all.
- **Never** counted in the group filter's totals, which readers use as
  population figures.
- **Never** rolled into a parent by `roll_up_parents`. A modelled child must
  not become evidence for its parent, or the estimate launders itself into
  something that looks read.
- Off by default, behind an explicit control that names what it is showing.
- Carried into the downloadable data with the status intact.

---

## 7. Validation is not optional

`scripts/backtest_estimators.py` runs leave-one-out on live data and should
run in CI beside the other checks. An estimator ships only if its band's
backtested leading-group accuracy clears a declared threshold, and the
threshold lives in the repo next to the code, not in a commit message. When
coverage improves, the numbers move, and the gate must be re-derived rather
than inherited.

---

## 8. Recommendation

Build **Tier 0 and the geometric half of Tier 1** — the residual and the
split-and-merge cases, where the arithmetic does the work and the assumption
is about geometry rather than about people. Those are defensible, bounded, and
close the split/merge gaps already documented in `SOURCES.md` (Kavango,
Ennedi, the Grenadines, Madagascar's provinces).

Build **Tier 2** for the 7–9% of blanks that have in-country neighbours, gated
at 5% estimator agreement, rendered as hatching, off by default.

**Do not build Tier 3.** It covers most of the blank map, which is exactly why
it is tempting, and it would flatten roughly half of all countries into a
single colour that the data we do have says is wrong. The blank regions are
overwhelmingly whole countries with nothing read inside them, and for those
the honest answer is the one the map already gives: *a source was read, or it
was not, and here is which.*

The highest-return work is therefore still **reading more sources** — every
country read converts a national prior into real subnational variation and
simultaneously turns its neighbours' Tier 3 cases into Tier 2 ones. Modelling
is worth building for the cases where it is nearly arithmetic. It is not a
substitute for the survey in issue #49.
