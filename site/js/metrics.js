/* Choropleth metrics.
 *
 * Each metric turns one attribute record into either a number on a sequential
 * ramp or a status category, plus a legend. Colours are resolved in JS and
 * pushed into MapLibre through `feature-state`, so a metric change repaints
 * without re-fetching tiles.
 */
window.Metrics = (function () {
  "use strict";

  const { isGap, gapStatus, valueOf } = window.Fmt;

  function topGroups(records, field, limit) {
    // Which groups are worth offering for the "share of group" facet: the ones
    // that actually appear across the current selection, most common first.
    const tally = new Map();
    for (const record of records) {
      const value = record[field];
      if (!Array.isArray(value)) continue;
      for (const row of value.slice(0, 6)) {
        if (typeof row.pct !== "number") continue;
        tally.set(row.group, (tally.get(row.group) || 0) + 1);
      }
    }
    return Array.from(tally.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit || 40)
      .map(([group]) => group);
  }

  // field -> source label -> canonical group, from site/data/groups.json. Until
  // it arrives, matching falls back to the label itself, which is correct but
  // country-local: "Islam" would find Sri Lanka and miss the places that say
  // "Muslim".
  let canonical = {};

  function setGroupIndex(index) {
    canonical = {};
    for (const [field, entry] of Object.entries(index || {})) {
      const map = new Map();
      for (const group of entry.groups || []) {
        for (const label of group.labels || []) map.set(label, group.name);
      }
      canonical[field] = map;
    }
  }

  function canonicalName(field, label) {
    const map = canonical[field];
    return (map && map.get(label)) || label;
  }

  function shareOf(record, field, group) {
    const value = record[field];
    if (!Array.isArray(value)) return null;
    // Summed, not found: one canonical group can be several rows of a record.
    // The US reports Protestant, Catholic, Orthodox, Latter-day Saints and
    // Jehovah's Witnesses where Australia reports one "Christianity" row, so
    // matching a single row would show the US at its largest denomination and
    // call that its Christian share.
    let total = null;
    for (const row of value) {
      if (typeof row.pct !== "number") continue;
      if (canonicalName(field, row.group) !== group) continue;
      total = (total || 0) + row.pct;
    }
    return total;
  }

  function largestShare(record, field) {
    const value = record[field];
    if (!Array.isArray(value) || !value.length) return null;
    const best = value.reduce((a, b) => ((b.pct || 0) > (a.pct || 0) ? b : a));
    return typeof best.pct === "number" ? best.pct : null;
  }

  function dominant(record, field) {
    const value = record[field];
    if (!Array.isArray(value) || !value.length) return null;
    const best = value.reduce((a, b) => ((b.pct || 0) > (a.pct || 0) ? b : a));
    return best.group || null;
  }

  const METRICS = {
    coverage: {
      label: "Data coverage",
      kind: "status",
      needsField: true,
      hint: "Where a figure exists — and whether a gap is unfetched or never collected.",
      blank: "Grey means no record for that unit at all, not even a gap marker.",
      note: "Whether a value exists for the chosen field, is not yet fetched, or is " +
            "never collected by that country.",
      evaluate(record, opts) { return gapStatus(record[opts.field]); },
    },
    population: {
      label: "Population",
      kind: "sequential",
      scale: "log",
      unit: "people",
      hint: "Latest published count, on a log scale.",
      blank: "Grey areas have no published population at this level.",
      note: "Latest published count for each unit. Reference years differ by country.",
      evaluate(record) { return valueOf(record.population); },
      format: (n) => window.Fmt.number(n),
    },
    median_age: {
      label: "Median age",
      kind: "sequential",
      scale: "linear",
      unit: "years",
      hint: "Median age of the resident population.",
      blank: "Grey areas have no published median age at this level.",
      note: "Median age of the resident population.",
      evaluate(record) { return valueOf(record.median_age); },
      format: (n) => `${Math.round(n * 10) / 10} yrs`,
    },
    largest_share: {
      label: "Share of the largest group",
      kind: "sequential",
      scale: "linear",
      needsField: true,
      domain: [0, 100],
      hint: "How concentrated the composition is — the share held by the single largest group.",
      blank: "Grey areas publish no composition for this field at this level.",
      note: "How concentrated the chosen composition is: the percentage held by the " +
            "single largest group. High values mean one group dominates.",
      evaluate(record, opts) { return largestShare(record, opts.field); },
      format: (n) => window.Fmt.pct(n),
    },
    group_share: {
      label: "Share of one group",
      kind: "sequential",
      scale: "linear",
      needsField: true,
      needsGroup: true,
      domain: [0, 100],
      hint: "One group at a time, shaded by its percentage.",
      blank: "Blank means the figure is missing at this level — not that the share is zero.",
      note: "The percentage belonging to a single chosen group. This is the faceted " +
            "answer to “which group dominates?” — one group at a time on a single " +
            "hue, rather than a colour-per-group map that colour-blind readers " +
            "cannot separate.",
      evaluate(record, opts) {
        return opts.group ? shareOf(record, opts.field, opts.group) : null;
      },
      format: (n) => window.Fmt.pct(n),
    },
  };

  const FIELDS = [
    { key: "religion", label: "Religion" },
    { key: "language", label: "Language" },
    { key: "ethnicity", label: "Ethnicity / race" },
  ];

  /** Compute colours for a set of records under one metric. */
  function paint(records, metricKey, opts) {
    const metric = METRICS[metricKey] || METRICS.coverage;
    const Palette = window.Palette;
    const out = new Map();

    if (metric.kind === "status") {
      for (const record of records) {
        const state = metric.evaluate(record, opts);
        out.set(record.id, Palette.status(state).color);
      }
      return { colors: out, legend: statusLegend(), metric };
    }

    const values = [];
    for (const record of records) {
      const value = metric.evaluate(record, opts);
      if (Number.isFinite(value)) values.push(value);
    }
    if (!values.length) {
      return { colors: out, legend: { type: "empty", metric }, metric };
    }

    values.sort((a, b) => a - b);
    const domain = metric.domain || [values[0], values[values.length - 1]];
    // Percentiles rather than min/max: one Tokyo-sized outlier should not flatten
    // the rest of the map into a single shade.
    const low = metric.domain ? domain[0] : values[Math.floor(values.length * 0.02)];
    const high = metric.domain ? domain[1] : values[Math.floor(values.length * 0.98)];
    const log = metric.scale === "log";

    const project = (v) => {
      if (!Number.isFinite(v)) return null;
      const lo = log ? Math.log10(Math.max(1, low)) : low;
      const hi = log ? Math.log10(Math.max(10, high)) : high;
      const x = log ? Math.log10(Math.max(1, v)) : v;
      return hi === lo ? 0.5 : (x - lo) / (hi - lo);
    };

    let missing = 0;
    for (const record of records) {
      const value = metric.evaluate(record, opts);
      if (Number.isFinite(value)) {
        out.set(record.id, Palette.sequential(project(value)));
      } else {
        // Neutral grey, not a status colour: on a sequential map the status
        // palette would read as a value at one end of the ramp.
        out.set(record.id, Palette.neutral());
        missing += 1;
      }
    }

    return {
      colors: out,
      legend: {
        type: "ramp",
        stops: Palette.ramp(),
        low: metric.format ? metric.format(low) : String(low),
        high: metric.format ? metric.format(high) : String(high),
        missing,
        missingColor: Palette.neutral(),
        note: metric.note,
      },
      metric,
    };
  }

  function statusLegend() {
    return {
      type: "status",
      items: ["present", "not_available", "not_collected"].map((key) => {
        const s = window.Palette.status(key);
        return { color: s.color, icon: s.icon, label: s.label };
      }),
      note: METRICS.coverage.note,
    };
  }

  return { METRICS, FIELDS, paint, topGroups, dominant, largestShare, shareOf,
           setGroupIndex, canonicalName };
})();
