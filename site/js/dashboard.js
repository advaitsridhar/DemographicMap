/* The detail panel.
 *
 * Composition (religion / language / ethnicity) is drawn as a 100% stacked bar
 * with a 2px surface gap between segments, followed by a labelled list. Every
 * segment therefore carries a text label and a percentage, which is what lets the
 * eight-slot categorical palette be used safely: identity never rests on hue.
 * A table view of the same numbers is one click away for screen readers, print
 * and forced-colours.
 */
window.Dashboard = (function () {
  "use strict";

  const { escape: esc, isGap, gapStatus, valueOf, number } = window.Fmt;

  /** Percentage with the Factbook's "<1%" upper bounds kept as bounds. */
  function pct(value, row) {
    const text = window.Fmt.pct(value);
    return row && row.bound ? `${row.bound}${text}` : text;
  }
  let onNavigate = () => {};

  function setNavigator(fn) { onNavigate = fn; }

  function gapBlock(value, fieldLabel) {
    const status = gapStatus(value);
    const meta = window.Palette.status(status);
    const note = (value && value.note) ||
      (status === "not_collected"
        ? `This country does not collect ${fieldLabel.toLowerCase()}.`
        : `No ${fieldLabel.toLowerCase()} figure has been fetched for this unit yet.`);
    return `<div class="gap-note">
      <span class="gap-icon" style="color:${meta.color}" aria-hidden="true">${meta.icon}</span>
      <span><strong>${esc(meta.label)}.</strong> ${esc(note)}</span>
    </div>`;
  }

  function factCard(label, value, meta) {
    if (isGap(value)) {
      const status = gapStatus(value);
      const s = window.Palette.status(status);
      return `<div class="fact">
        <div class="fact-label">${esc(label)}</div>
        <div class="fact-value is-gap">
          <span style="color:${s.color}" aria-hidden="true">${s.icon}</span> ${esc(s.label)}
        </div>
      </div>`;
    }
    return `<div class="fact">
      <div class="fact-label">${esc(label)}</div>
      <div class="fact-value">${esc(value)}</div>
      ${meta ? `<div class="fact-meta">${esc(meta)}</div>` : ""}
    </div>`;
  }

  function measureCard(label, measure, format) {
    if (isGap(measure)) return factCard(label, measure);
    const raw = valueOf(measure);
    const meta = [];
    if (measure && measure.year) meta.push(String(measure.year));
    if (measure && measure.source) meta.push(measure.source.split(",")[0]);
    return factCard(label, format ? format(raw) : raw, meta.join(" · "));
  }

  /** Fold a composition down to at most eight named slots plus "Other". */
  function foldGroups(rows) {
    const MAX = window.Palette.MAX_CATEGORIES;
    const usable = rows.filter((r) => typeof r.pct === "number" && r.pct > 0)
                       .sort((a, b) => b.pct - a.pct);
    if (usable.length <= MAX) return { shown: usable, folded: 0 };
    const shown = usable.slice(0, MAX - 1);
    const tail = usable.slice(MAX - 1);
    const rest = tail.reduce((sum, r) => sum + r.pct, 0);
    shown.push({ group: "Other groups", pct: Math.round(rest * 10) / 10, _folded: tail.length });
    return { shown, folded: tail.length };
  }

  function compositionPanel(title, value, note, year) {
    // A reference year only belongs on a value. Printing one beside "not
    // collected" implies a measurement that was never taken.
    const showYear = year && !isGap(value);
    const parts = [`<section class="panel"><div class="panel-head"><h3>${esc(title)}</h3>` +
                   (showYear ? `<span class="panel-year">${esc(year)}</span>` : "") + `</div>`];

    if (isGap(value)) {
      parts.push(gapBlock(value, title));
      if (note) parts.push(`<p class="note">${esc(note)}</p>`);
      return parts.join("") + "</section>";
    }

    const { shown } = foldGroups(value);
    const total = shown.reduce((sum, r) => sum + r.pct, 0);
    const unlabelled = value.filter((r) => r.pct == null).map((r) => r.group);

    if (shown.length) {
      const segments = shown.map((row, i) => {
        const width = total > 0 ? (row.pct / total) * 100 : 0;
        return `<span style="flex:0 0 ${width.toFixed(2)}%;background:${window.Palette.categorical(i)}"
                      title="${esc(row.group)} ${pct(row.pct, row)}"></span>`;
      }).join("");
      parts.push(`<div class="stack-bar" role="img"
        aria-label="${esc(shown.map((r) => `${r.group} ${pct(r.pct, r)}`).join(", "))}">${segments}</div>`);

      parts.push(`<ul class="composition-list">` + shown.map((row, i) =>
        `<li><span class="swatch" style="background:${window.Palette.categorical(i)}" aria-hidden="true"></span>
             <span class="label">${esc(row.group)}${row._folded ? ` (${row._folded})` : ""}</span>
             <span class="pct">${pct(row.pct, row)}</span></li>`).join("") + `</ul>`);

      parts.push(`<details class="table-toggle"><summary>Table view</summary>
        <table class="data-table"><thead><tr><th>Group</th><th>Share</th></tr></thead><tbody>` +
        value.filter((r) => typeof r.pct === "number")
             .map((r) => `<tr><td>${esc(r.group)}</td><td>${pct(r.pct, r)}</td></tr>`).join("") +
        `</tbody></table></details>`);
    }

    if (unlabelled.length) {
      parts.push(`<p class="note"><span style="color:${window.Palette.status("not_available").color}"
        aria-hidden="true">▲</span> Named without published shares:
        ${esc(unlabelled.slice(0, 10).join(", "))}.</p>`);
    }
    if (Math.abs(total - 100) > 4 && shown.length) {
      parts.push(`<p class="note">Shares total ${pct(total)}, not 100% — categories may
        overlap, exclude non-responses, or come from a multi-response question.</p>`);
    }
    if (note) parts.push(`<p class="note">${esc(note)}</p>`);
    return parts.join("") + "</section>";
  }

  /** When a unit has no demographic values, say what would fill it. */
  function hintPanel(record) {
    if (!record.adapter_hint) return "";
    const fields = ["population", "religion", "language", "ethnicity", "median_age"];
    const hasAny = fields.some((field) => !isGap(record[field]));
    if (hasAny) return "";
    return `<section class="panel"><div class="panel-head"><h3>Filling this gap</h3></div>
      <p class="note">This build has not fetched demographics for this unit. The
      pipeline in this repository can: <code>${esc(record.adapter_hint)}</code></p></section>`;
  }

  function breadcrumb(record) {
    const trail = [];
    const country = window.DataStore.country(record.country);
    if (record.level !== "admin0" && country) {
      trail.push(`<button type="button" data-goto="${esc(country.id)}">${esc(country.name)}</button>`);
    }
    if (record.level === "admin2" && record.parent && record.parent !== record.country) {
      const parent = window.DataStore.get(record.parent);
      if (parent) {
        trail.push("›");
        trail.push(`<button type="button" data-goto="${esc(parent.id)}">${esc(parent.name)}</button>`);
      }
    }
    const levelLabel = { admin0: "Country", admin1: "First-level division", admin2: "Second-level division" }[record.level];
    trail.push(trail.length ? `› ${esc(levelLabel)}` : esc(levelLabel));
    return `<p class="entity-breadcrumb">${trail.join(" ")}</p>`;
  }

  function sourceList(record) {
    const seen = new Set();
    const rows = [];
    for (const source of record.sources || []) {
      const key = `${source.name}|${source.url || ""}`;
      if (!source.name || seen.has(key)) continue;
      seen.add(key);
      const link = source.url
        ? `<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.name)}</a>`
        : esc(source.name);
      const extra = [source.year, source.license].filter(Boolean).join(" · ");
      rows.push(`<li>${link}${extra ? ` — ${esc(extra)}` : ""}${source.note ? `<br><span style="color:var(--ink-muted)">${esc(source.note)}</span>` : ""}</li>`);
    }
    rows.push(`<li>Boundary: <a href="https://www.geoboundaries.org/" target="_blank" rel="noopener noreferrer">geoBoundaries</a> CGAZ — CC BY 4.0</li>`);
    return `<section class="panel"><div class="panel-head"><h3>Sources</h3></div>
      <ul class="source-list">${rows.join("")}</ul></section>`;
  }

  function childrenPanel(record) {
    const kids = window.DataStore.children(record.id)
      .filter((c) => c.level !== record.level)
      .sort((a, b) => (valueOf(b.population) || 0) - (valueOf(a.population) || 0) ||
                       a.name.localeCompare(b.name));
    if (!kids.length) return "";
    const label = record.level === "admin0" ? "First-level divisions" : "Second-level divisions";
    return `<section class="panel"><div class="panel-head"><h3>${label}</h3>
      <span class="panel-year">${kids.length}</span></div>
      <ul class="children-list">${kids.slice(0, 400).map((kid) => {
        const pop = valueOf(kid.population);
        return `<li><button type="button" data-goto="${esc(kid.id)}">
          <span>${esc(kid.name)}</span>
          <span class="c-count">${pop ? number(pop) : ""}</span></button></li>`;
      }).join("")}</ul></section>`;
  }

  function render(record, container) {
    if (!record) return;
    const capital = record.capital;
    const largest = record.largest_settlement;
    const html = [];

    html.push(`<header class="entity-head">
      ${breadcrumb(record)}
      <h2 class="entity-name">${esc(record.name)}</h2>
      <p class="entity-sub">${esc(subtitle(record))}</p>
    </header>`);

    if (record.note) {
      html.push(`<div class="gap-note" style="margin-bottom:1rem">
        <span class="gap-icon" aria-hidden="true">ⓘ</span>
        <span>${esc(record.note)}</span></div>`);
    }

    if (record.disputed) {
      container.innerHTML = html.join("") + sourceList(record);
      container.scrollTop = 0;
      return;
    }

    html.push(`<div class="facts">
      ${measureCard("Population", record.population, (n) => number(n))}
      ${factCard("Capital", isGap(capital) ? capital : capital)}
      ${factCard("Largest settlement", isGap(largest) ? largest : largest,
                 record.largest_settlement_population
                   ? `${number(valueOf(record.largest_settlement_population))} people`
                   : null)}
      ${measureCard("Median age", record.median_age, (n) => `${n} yrs`)}
      ${measureCard("Sex ratio", record.sex_ratio, (n) => String(n))}
      ${measureCard("Life expectancy", record.life_expectancy, (n) => `${n} yrs`)}
    </div>`);

    html.push(compositionPanel("Religion", record.religion, record.religion_note, record.religion_year));
    html.push(compositionPanel("Language", record.language, record.language_note, record.language_year));
    html.push(compositionPanel("Ethnicity", record.ethnicity, record.ethnicity_note, record.ethnicity_year));
    if (record.ancestry) {
      html.push(compositionPanel("Ancestry", record.ancestry, record.ancestry_note));
    }
    if (record.scheduled_groups) {
      // India's constitutional-schedule classification. Shown as its own panel
      // rather than under "Ethnicity", which India does not collect.
      html.push(compositionPanel("Scheduled Caste / Tribe", record.scheduled_groups,
                                 record.scheduled_groups_note));
    }
    html.push(hintPanel(record));
    html.push(childrenPanel(record));
    html.push(sourceList(record));

    container.innerHTML = html.join("");
    container.querySelectorAll("[data-goto]").forEach((button) => {
      button.addEventListener("click", () => onNavigate(button.dataset.goto));
    });
    container.scrollTop = 0;
  }

  function subtitle(record) {
    const bits = [];
    if (record.level === "admin0") {
      const codes = record.codes || {};
      bits.push([codes.iso3, codes.iso2].filter(Boolean).join(" · ") || record.id);
    } else {
      const country = window.DataStore.country(record.country);
      if (country) bits.push(country.name);
    }
    const sexRatio = record.sex_ratio;
    if (!isGap(sexRatio) && sexRatio.unit) {
      bits.push(sexRatio.unit.replace(/_/g, " "));
    }
    return bits.filter(Boolean).join(" · ");
  }

  return { render, setNavigator, gapBlock };
})();
