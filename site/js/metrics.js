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
  // field -> canonical name -> its ancestors, nearest first and itself first.
  // This is what makes one row answer for several questions: a "Roman
  // Catholic" row is a Catholic row, a Christian row, and nothing else.
  let lineage = {};
  let byName = {};

  function setGroupIndex(index) {
    canonical = {};
    lineage = {};
    byName = {};
    for (const [field, entry] of Object.entries(index || {})) {
      const map = new Map();
      const index2 = new Map();
      for (const group of entry.groups || []) {
        index2.set(group.name, group);
        for (const label of group.labels || []) map.set(label, group.name);
      }
      canonical[field] = map;
      byName[field] = index2;
      const trail = new Map();
      for (const group of entry.groups || []) {
        const seen = [];
        let at = group;
        // Guarded against a cycle in the shipped file rather than trusted:
        // a parent loop would otherwise hang the first paint.
        while (at && seen.indexOf(at.name) < 0) {
          seen.push(at.name);
          at = at.parent ? index2.get(at.parent) : null;
        }
        trail.set(group.name, seen);
      }
      lineage[field] = trail;
    }
  }

  function canonicalName(field, label) {
    const map = canonical[field];
    return (map && map.get(label)) || label;
  }

  /** A canonical name and every group it counts into, itself first. */
  function ancestry(field, name) {
    const trail = lineage[field];
    return (trail && trail.get(name)) || [name];
  }

  /** The top of a name's tree: what it is on a map of broad families. */
  function familyOf(field, name) {
    const trail = ancestry(field, name);
    return trail[trail.length - 1];
  }

  function groupEntry(field, name) {
    const map = byName[field];
    return (map && map.get(name)) || null;
  }

  /** The colour a group carries wherever it is largest. */
  function hueOf(field, name) {
    for (const step of ancestry(field, name)) {
      const entry = groupEntry(field, step);
      if (entry && entry.hue) return entry.hue;
    }
    return null;
  }

  /* One record's rows added into canonical groups, at a chosen depth.
   *
   * `level` is "family" for the top of each tree -- Christianity, Islam,
   * Indo-European languages -- and "group" for the finest canonical name a
   * source wrote, which is Catholicism where a census said Catholic and
   * Christianity where it said Christian. Nothing is counted twice either
   * way: each row lands in exactly one bucket.
   */
  function tally(record, field, level) {
    const value = record[field];
    const out = new Map();
    if (!Array.isArray(value)) return out;
    for (const row of value) {
      if (typeof row.pct !== "number") continue;
      const name = canonicalName(field, row.group);
      const key = level === "family" ? familyOf(field, name) : name;
      out.set(key, (out.get(key) || 0) + row.pct);
    }
    return out;
  }

  function shareOf(record, field, group) {
    return shareDetail(record, field, group).value;
  }

  function shareDetail(record, field, group) {
    const value = record[field];
    if (!Array.isArray(value)) return { value: null, approximate: false };
    // Summed, not found: one canonical group can be several rows of a record.
    // The US reports Protestant, Catholic, Orthodox, Latter-day Saints and
    // Jehovah's Witnesses where Australia reports one "Christianity" row, so
    // matching a single row would show the US at its largest denomination and
    // call that its Christian share.
    let total = null;
    let approximate = false;
    const matched = [];
    for (const row of value) {
      if (typeof row.pct !== "number") continue;
      // Counted through the tree, not by name: asking for Christianity over
      // Poland has to find the "Roman Catholic" rows that never say the word,
      // and asking for Catholicism must not also collect the Protestants
      // beside them.
      if (ancestry(field, canonicalName(field, row.group)).indexOf(group) < 0) continue;
      total = (total || 0) + row.pct;
      approximate = approximate || Boolean(row.bound || row.range);
      matched.push(row);
    }
    return { value: total, approximate,
             bound: matched.length === 1 ? matched[0].bound : null,
             range: matched.length === 1 ? matched[0].range : null };
  }

  function largestShare(record, field) {
    const value = record[field];
    if (!Array.isArray(value) || !value.length) return null;
    const best = value.reduce((a, b) => ((b.pct || 0) > (a.pct || 0) ? b : a));
    return typeof best.pct === "number" ? best.pct : null;
  }

  function largestShareDetail(record, field) {
    const value = record[field];
    if (!Array.isArray(value) || !value.length) return { value: null, approximate: false };
    const best = value.reduce((a, b) => ((b.pct || 0) > (a.pct || 0) ? b : a));
    return { value: typeof best.pct === "number" ? best.pct : null,
             approximate: Boolean(best.bound || best.range),
             bound: best.bound, range: best.range };
  }

  function formatDetail(detail) {
    if (!detail || !Number.isFinite(detail.value)) return "—";
    if (Array.isArray(detail.range) && detail.range.length === 2) {
      return `${window.Fmt.pct(detail.range[0])}–${window.Fmt.pct(detail.range[1])}`;
    }
    if (detail.bound) return `${detail.bound}${window.Fmt.pct(detail.value)}`;
    return `${detail.approximate ? "about " : ""}${window.Fmt.pct(detail.value)}`;
  }

  /* The largest group in one unit, at the chosen depth of the tree.
   *
   * Residuals are skipped where anything else is available. "Not stated" leads
   * 1,803 US counties on the religion question, and a map that paints them all
   * one colour for it answers "which religion is largest here" with "we did not
   * ask" -- true, and not the question. The residual still wins where it is the
   * only thing a unit reports, because then it is the whole answer; the readout
   * says so either way.
   */
  function dominant(record, field, level) {
    const totals = tally(record, field, level || "family");
    if (!totals.size) return null;
    let best = null;
    let bestResidual = null;
    for (const [name, pct] of totals) {
      const entry = groupEntry(field, name);
      const slot = entry && entry.residual ? "bestResidual" : "best";
      const held = slot === "best" ? best : bestResidual;
      if (!held || pct > held.pct) {
        const found = { group: name, pct, residual: Boolean(entry && entry.residual) };
        if (slot === "best") best = found; else bestResidual = found;
      }
    }
    return best || bestResidual;
  }

  const METRICS = {
    /* The map the reference atlases draw: hue for which group leads, shade
     * for by how much.
     *
     * It is the one view that answers the question at a glance for the whole
     * world rather than one group at a time, and it is the one that most
     * needs to say out loud what it is doing. Two units of the same colour
     * are not necessarily comparable: the categories are each country's own,
     * and a plurality of 28% and a majority of 96% are both "largest".
     */
    group: {
      label: "Most populous group",
      kind: "group",
      needsField: true,
      needsDepth: true,
      hint: "One colour per group, darker where its share is larger.",
      blank: "Grey areas publish no composition for this field at this level.",
      note: "Each unit takes the colour of its largest group and the shade of " +
            "that group's share, from 25% up. Categories are each country's own, " +
            "so a border can be a change of question rather than of population.",
      evaluate(record, opts) {
        const top = dominant(record, opts.field, opts.depth);
        return top ? top.group : null;
      },
      display(record, opts) {
        const top = dominant(record, opts.field, opts.depth);
        if (!top) return "—";
        return `${top.group} ${window.Fmt.pct(top.pct)}` +
               (top.residual ? " (no group named)" : "");
      },
    },
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
      label: "How concentrated",
      kind: "sequential",
      scale: "linear",
      needsField: true,
      domain: [0, 100],
      hint: "The share held by the single largest group, whichever it is.",
      blank: "Grey areas publish no composition for this field at this level.",
      note: "How concentrated the chosen composition is: the percentage held by the " +
            "single largest group. High values mean one group dominates.",
      evaluate(record, opts) { return largestShare(record, opts.field); },
      display(record, opts) { return formatDetail(largestShareDetail(record, opts.field)); },
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
      display(record, opts) {
        return opts.group ? formatDetail(shareDetail(record, opts.field, opts.group)) : "—";
      },
      format: (n) => window.Fmt.pct(n),
    },
  };

  // Short enough to sit in a three-way control without truncating. The longer
  // "Ethnicity / race" was ellipsed to "Ethnicity / ra…", which is worse than
  // the shorter word: the caveat about race and ethnicity being different
  // questions belongs in the topic note, where there is room to say it.
  const FIELDS = [
    { key: "religion", label: "Religion" },
    { key: "language", label: "Language" },
    { key: "ethnicity", label: "Ethnicity" },
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

    if (metric.kind === "group") {
      // Tallied while colouring so the legend can be ordered by how much of
      // the map each group actually leads. A legend in alphabetical order,
      // or in the index's order, buries the four colours that cover half the
      // world under thirty that cover a district each.
      const led = new Map();
      let missing = 0;
      for (const record of records) {
        const top = dominant(record, opts.field, opts.depth);
        if (!top) { out.set(record.id, Palette.neutral()); missing += 1; continue; }
        const hue = hueOf(opts.field, top.group);
        out.set(record.id, Palette.group(hue, top.pct));
        const seen = led.get(top.group) ||
          { name: top.group, hue, units: 0, residual: top.residual, peak: 0 };
        seen.units += 1;
        seen.peak = Math.max(seen.peak, top.pct);
        led.set(top.group, seen);
      }
      const items = Array.from(led.values())
        .sort((a, b) => b.units - a.units || a.name.localeCompare(b.name));
      return {
        colors: out,
        legend: {
          type: "group",
          items,
          shown: Math.min(items.length, 12),
          missing,
          missingColor: Palette.neutral(),
          floor: Palette.SHARE_FLOOR,
          note: metric.note,
        },
        metric,
      };
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
           shareDetail, largestShareDetail, tally,
           setGroupIndex, canonicalName, ancestry, familyOf, hueOf, groupEntry };
})();
