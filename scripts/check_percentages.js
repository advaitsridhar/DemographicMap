/* Do the panel's percentages add up?
 *
 * The detail panel squares rounding drift so a composition that partitions a
 * population displays as exactly 100.0 (see `toHundred` in
 * site/js/dashboard.js). This runs that function over every composition in
 * site/data and checks the invariant, because the alternative is trusting a
 * function about the last decimal place to a spot check.
 *
 * Compositions that are deliberately not 100 are excluded and counted
 * separately: a multi-response question sums past it, and a source that
 * describes only part of a population falls short of it. Those keep their true
 * widths on the page and say so in a chip.
 *
 *     node scripts/check_percentages.js
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const DATA = path.join(ROOT, "site", "data");
const FIELDS = ["religion", "language", "ethnicity"];

// Lifted out of the module rather than copied, so this cannot drift from what
// the page actually does.
function loadToHundred() {
  const src = fs.readFileSync(path.join(ROOT, "site/js/dashboard.js"), "utf8");
  const start = src.indexOf("const ROUNDING_SLACK");
  const end = src.indexOf("/** Fold a composition");
  if (start < 0 || end < 0) {
    throw new Error("dashboard.js no longer exposes toHundred where expected");
  }
  return new Function(src.slice(start, end) + "; return toHundred;")();
}

function dataFiles() {
  const files = [path.join(DATA, "admin0.json")];
  for (const level of ["admin1", "admin2"]) {
    const dir = path.join(DATA, level);
    if (!fs.existsSync(dir)) continue;
    for (const name of fs.readdirSync(dir)) files.push(path.join(dir, name));
  }
  return files;
}

function main() {
  const toHundred = loadToHundred();
  const tally = { partition: 0, exact: 0, wrong: [], multi: 0, partial: 0 };

  for (const file of dataFiles()) {
    let records;
    try {
      records = JSON.parse(fs.readFileSync(file, "utf8"));
    } catch (err) {
      continue;
    }
    if (!Array.isArray(records)) continue;
    for (const record of records) {
      for (const field of FIELDS) {
        const rows = record[field];
        if (!Array.isArray(rows) || !rows.length) continue;
        const raw = rows.reduce((sum, r) => sum + (r.pct || 0), 0);
        if (raw > 100.5) { tally.multi += 1; continue; }
        if (raw < 99.5) { tally.partial += 1; continue; }
        tally.partition += 1;
        const shown = toHundred(rows).rows
          .reduce((sum, r) => sum + (typeof r.pct === "number" ? r.pct : 0), 0);
        if (Math.round(shown * 10) === 1000) tally.exact += 1;
        else tally.wrong.push(`${record.country} ${record.name} ${field}: ${shown}`);
      }
    }
  }

  console.log(`${tally.partition} compositions that partition a population`);
  console.log(`   ${tally.exact} display exactly 100.0`);
  console.log(`   ${tally.wrong.length} do not`);
  console.log(`${tally.multi} sum past 100 (more than one answer allowed)`);
  console.log(`${tally.partial} fall short (the source describes part of the population)`);
  for (const line of tally.wrong.slice(0, 10)) console.log(`   ${line}`);
  return tally.wrong.length ? 1 : 0;
}

process.exit(main());
