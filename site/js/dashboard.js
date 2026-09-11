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

  /** Percentage with the Factbook's "<1%" upper bounds kept as bounds.
   *
   * One decimal always: these are the figures in a column, and the column has
   * to be seen to add up.
   */
  function pct(value, row) {
    const text = window.Fmt.pct1(value);
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

  /* A measure's unit, written the way a person would say it.
   *
   * "1084" answers nothing on its own: a sex ratio can be counted either way
   * round, and which way this one runs is the whole meaning of the number.
   * The unit used to be appended to the *place's* subtitle, where it read as
   * part of the place's identity -- "Kerala / India - females per 1000
   * males" -- which told the reader nothing about Kerala and hid the one fact
   * that makes the figure legible.
   */
  function unitLabel(measure) {
    if (isGap(measure) || !measure || !measure.unit) return "";
    return String(measure.unit).replace(/_/g, " ");
  }

  function measureCard(label, measure, format, unit) {
    if (isGap(measure)) return factCard(label, measure);
    const raw = valueOf(measure);
    const meta = [];
    if (unit) meta.push(unit);
    if (measure && measure.year) meta.push(String(measure.year));
    if (measure && measure.source) meta.push(measure.source.split(",")[0]);
    return factCard(label, format ? format(raw) : raw, meta.join(" · "));
  }

  /* Make a partition's displayed percentages add to exactly 100.0.
   *
   * Shares arrive rounded to one decimal, so a set that partitions a
   * population lands on 99.9 or 100.1 about a fifth of the time: 95.6% of the
   * 39,858 partition-like compositions shipped here are within a tenth of 100,
   * and the difference is rounding, not a missing category. Printing a column
   * that visibly fails to add up is the kind of thing a reader is right to
   * distrust, so the tenths are put back.
   *
   * Only rounding is corrected. A sum more than half a point from 100 is a
   * real shortfall -- the Philippines omits some categories, so its provinces
   * come to 99.1 -- and those keep their true widths with the gap drawn as an
   * explicit unaccounted segment, because inventing the missing 0.9 would be
   * the one claim the data cannot support. Multi-response sets, which sum past
   * 100 on purpose, are never touched.
   *
   * The tenths go to the largest groups first, which is where the absolute
   * rounding error is largest and where one tenth is the smallest relative
   * change.
   */
  const ROUNDING_SLACK = 0.5;

  function toHundred(rows) {
    const usable = rows.filter((r) => typeof r.pct === "number");
    const total = usable.reduce((sum, r) => sum + r.pct, 0);
    if (!usable.length || Math.abs(total - 100) > ROUNDING_SLACK || total === 100) {
      return { rows, adjusted: 0 };
    }
    // Worked in tenths so the arithmetic is exact: 0.1 + 0.2 !== 0.3 in binary
    // floating point, and this is a function about the last decimal place.
    const tenths = usable.map((r) => Math.round(r.pct * 10));
    let diff = 1000 - tenths.reduce((a, b) => a + b, 0);
    const order = usable.map((r, i) => i)
                        .sort((a, b) => tenths[b] - tenths[a]);
    let at = 0;
    while (diff !== 0 && at < order.length * 10) {
      const i = order[at % order.length];
      // Never push a group below zero or turn a real group into nothing.
      if (diff > 0 || tenths[i] > 1) {
        tenths[i] += diff > 0 ? 1 : -1;
        diff += diff > 0 ? -1 : 1;
      }
      at += 1;
    }
    const fixed = new Map();
    usable.forEach((r, i) => fixed.set(r, tenths[i] / 10));
    return {
      rows: rows.map((r) => (fixed.has(r) ? { ...r, pct: fixed.get(r) } : r)),
      adjusted: Math.abs(Math.round((100 - total) * 10)),
    };
  }

  /** Fold a composition down to at most eight named slots plus "Other". */
  function foldGroups(rows) {
    const MAX = window.Palette.MAX_CATEGORIES;
    const usable = rows.filter((r) => typeof r.pct === "number" && r.pct > 0)
                       .sort((a, b) => b.pct - a.pct);
    if (usable.length <= MAX) return { shown: usable, folded: 0 };
    const shown = usable.slice(0, MAX - 1);
    const tail = usable.slice(MAX - 1);
    // Summed in tenths and taken as the exact remainder, so folding a tail of
    // forty groups into one row cannot move the column's total: rounding each
    // and adding them put Madhya Pradesh's languages back to 100.1.
    const rest = tail.reduce((sum, r) => sum + Math.round(r.pct * 10), 0);
    shown.push({ group: "Other groups", pct: rest / 10, _folded: tail.length });
    return { shown, folded: tail.length };
  }

  /* The "i" that carries a note.
   *
   * Every composition used to print its note as a paragraph under the bar.
   * They run to several hundred words between them -- Switzerland's says the
   * survey lets a person name three languages, Zimbabwe's gives the universe
   * of the mother-tongue table, a summed one names the divisions it came from
   * -- and stacked three deep they pushed the figures off the screen on a
   * laptop. They are worth keeping every word of and not worth reading every
   * time, which is what a bubble is for.
   */
  function infoDot(text, label) {
    if (!text) return "";
    return `<button type="button" class="info" data-info-text="${esc(text)}"
                    aria-label="${esc(label)}">i</button>`;
  }

  /* One word for how the shares relate to the population, where they do not
   * simply partition it.
   *
   * This is the part of the note that changes how the bar should be read, so
   * it stays on the page as a chip while the rest goes behind the bubble. A
   * reader who sees six ethnic groups totalling 114% and no explanation is
   * looking at what appears to be an error.
   */
  function basisChip(total, value) {
    if (!value.length) return "";
    if (total > 105) {
      return `<span class="chip-basis" title="Shares sum to ${window.Fmt.pct1(total)}">
                more than one answer allowed</span>`;
    }
    if (total < 95) {
      return `<span class="chip-basis chip-basis-partial"
                    title="Shares sum to ${window.Fmt.pct1(total)}">
                describes ${window.Fmt.pct1(total)} of the population</span>`;
    }
    return "";
  }

  /* The note, plus a sentence when the last decimal place was moved.
   *
   * A reader comparing this panel with the source has to be able to find out
   * why a figure is a tenth different, and "the totals were made to add up" is
   * the whole answer.
   */
  function noteFor(title, value, note) {
    if (!Array.isArray(value)) return note;
    const squared = toHundred(value);
    if (!squared.adjusted) return note;
    const tenths = squared.adjusted === 1 ? "a tenth of a point"
                                          : `${squared.adjusted} tenths of a point`;
    const said = `Shares are published rounded to one decimal and came to ` +
      `${tenths} off 100%; the difference is rounding, and it has been put ` +
      `back into the largest groups so the column adds up.`;
    return note ? `${note} ${said}` : said;
  }

  function compositionPanel(title, value, note, year) {
    // A reference year only belongs on a value. Printing one beside "not
    // collected" implies a measurement that was never taken.
    const showYear = year && !isGap(value);
    const parts = [`<section class="panel"><div class="panel-head">` +
                   `<h3>${esc(title)}${infoDot(noteFor(title, value, note),
                                   `About the ${title.toLowerCase()} figures`)}</h3>` +
                   (showYear ? `<span class="panel-year">${esc(year)}</span>` : "") + `</div>`];

    if (isGap(value)) {
      parts.push(gapBlock(value, title));
      return parts.join("") + "</section>";
    }

    const squared = toHundred(value);
    const value2 = squared.rows;
    const { shown } = foldGroups(value2);
    const total = shown.reduce((sum, r) => sum + r.pct, 0);
    const unlabelled = value2.filter((r) => r.pct == null).map((r) => r.group);

    if (shown.length) {
      // Shares that fall short of 100% keep their true widths, and the shortfall
      // is drawn as an explicit unaccounted segment. Normalising it away -- which
      // this did -- stretches the bar to full width and asserts the population is
      // entirely described, which for a source like the US Religion Census (about
      // 48.6% of people, the rest uncounted rather than unaffiliated) is the one
      // claim the data cannot support.
      //
      // A total above 100% is different: it means the question allowed more than
      // one answer, so the categories genuinely overlap and there is no remainder
      // to show. Those still normalise.
      const short = total > 0 && total < 99.5;
      const scale = short ? 100 : total;
      const segments = shown.map((row, i) => {
        const width = scale > 0 ? (row.pct / scale) * 100 : 0;
        return `<span style="flex:0 0 ${width.toFixed(2)}%;background:${window.Palette.categorical(i)}"
                      title="${esc(row.group)} ${pct(row.pct, row)}"></span>`;
      }).join("");
      const remainder = short
        ? `<span class="stack-rest" style="flex:0 0 ${(100 - total).toFixed(2)}%"
                 title="Not accounted for by these categories ${pct(100 - total)}"></span>`
        : "";
      const label = shown.map((r) => `${r.group} ${pct(r.pct, r)}`).join(", ") +
        (short ? `, not accounted for ${pct(100 - total)}` : "");
      parts.push(`<div class="stack-bar" role="img"
        aria-label="${esc(label)}">${segments}${remainder}</div>`);
      const chip = basisChip(total, shown);
      if (chip) parts.push(`<p class="basis-line">${chip}</p>`);

      parts.push(`<ul class="composition-list">` + shown.map((row, i) =>
        `<li><span class="swatch" style="background:${window.Palette.categorical(i)}" aria-hidden="true"></span>
             <span class="label">${esc(row.group)}${row._folded ? ` (${row._folded})` : ""}</span>
             <span class="pct">${pct(row.pct, row)}</span></li>`).join("") + `</ul>`);

      parts.push(`<details class="table-toggle"><summary>Table view</summary>
        <table class="data-table"><thead><tr><th>Group</th><th>Share</th></tr></thead><tbody>` +
        value2.filter((r) => typeof r.pct === "number")
              .map((r) => `<tr><td>${esc(r.group)}</td><td>${pct(r.pct, r)}</td></tr>`).join("") +
        `<tr class="total-row"><th scope="row">Total</th><th>` +
        `${window.Fmt.pct1(value2.reduce((sum, r) =>
            sum + (typeof r.pct === "number" ? r.pct : 0), 0))}</th></tr>` +
        `</tbody></table></details>`);
    }

    if (unlabelled.length) {
      parts.push(`<p class="note"><span style="color:${window.Palette.status("not_available").color}"
        aria-hidden="true">▲</span> Named without published shares:
        ${esc(unlabelled.slice(0, 10).join(", "))}.</p>`);
    }
    return parts.join("") + "</section>";
  }

  /** When a unit has no demographic values, say what would fill it -- or why
   *  nothing would. The two are different claims and must not read alike: a
   *  command in a <code> block promises that running it fills the panel, which
   *  is false where the country never published the figures. */
  function hintPanel(record) {
    if (!record.adapter_hint && !record.gap_reason) return "";
    const fields = ["population", "religion", "language", "ethnicity", "median_age"];
    const hasAny = fields.some((field) => !isGap(record[field]));
    if (hasAny) return "";
    if (record.gap_reason) {
      return `<section class="panel"><div class="panel-head"><h3>Why this is empty</h3></div>
        <p class="note">${esc(record.gap_reason)} See <code>docs/SOURCES.md</code>
        for what was tried.</p></section>`;
    }
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
      ${measureCard("Sex ratio", record.sex_ratio, (n) => String(n),
                    unitLabel(record.sex_ratio))}
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
    return bits.filter(Boolean).join(" · ");
  }

  return { render, setNavigator, gapBlock };
})();
