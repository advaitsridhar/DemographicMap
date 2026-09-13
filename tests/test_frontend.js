"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const source = (name) => fs.readFileSync(path.join(ROOT, "site", "js", name), "utf8");
const data = (name) => JSON.parse(fs.readFileSync(path.join(ROOT, "site", "data", name), "utf8"));

async function concurrentLoadsAreIndexedOnce() {
  const records = data("admin1/USA.json");
  const context = vm.createContext({
    window: {}, console,
    fetch: async (url) => ({
      ok: true,
      json: async () => url.includes("build.json") ? { version: "test" } : records,
    }),
  });
  vm.runInContext(source("data.js"), context);
  await Promise.all([
    context.window.DataStore.loadLevel("USA", 1),
    context.window.DataStore.loadLevel("USA", 1),
  ]);
  assert.strictEqual(context.window.DataStore.children("USA").length, records.length);
}

async function deepSearchWaitsForTheSecondShard() {
  let release;
  const delayed = new Promise((resolve) => { release = resolve; });
  const context = vm.createContext({
    window: { MiniSearch: class { addAll() {} search() { return []; } } },
    DataStore: { loadVersion: async () => {}, url: (url) => url }, console,
    fetch: async (url) => ({
      json: async () => url.includes("-0") ? data("search-index-0.json") : delayed,
    }),
  });
  vm.runInContext(source("search.js"), context);
  await context.window.Search.init({});
  const shard = data("search-index-2.json");
  const id = shard.rows[0][0];
  const lookup = context.window.Search.getWhenReady(id);
  release(shard);
  assert.strictEqual((await lookup).id, id);
}

function uncertainSharesKeepTheirQualifier() {
  const context = vm.createContext({ window: {}, console });
  vm.runInContext(source("data.js"), context);
  context.window.Palette = {
    sequential: () => "blue", neutral: () => "grey", ramp: () => [],
    status: () => ({ color: "grey" }),
  };
  vm.runInContext(source("metrics.js"), context);
  context.window.Metrics.setGroupIndex(data("groups.json"));
  const cuba = data("admin0.json").find((row) => row.id === "CUB");
  const metric = context.window.Metrics.METRICS.group_share;
  assert.strictEqual(metric.display(cuba, { field: "religion", group: "Islam" }), "<1%");
}

function mapStateSurvivesThemeChangesAndUsesRepresentativePoints() {
  const layers = new Map();
  const idle = [];
  let lastEase = null;
  const map = {
    getLayer: (id) => layers.get(id),
    getSource: () => null,
    setLayoutProperty: (id, key, value) => {
      const layer = layers.get(id);
      if (!layer.layout) layer.layout = {};
      layer.layout[key] = value;
    },
    setLayerZoomRange: (id, minzoom, maxzoom) => Object.assign(layers.get(id), { minzoom, maxzoom }),
    setPaintProperty: () => {}, setMinZoom: () => {}, getZoom: () => 2, setZoom: () => {},
    easeTo: (options) => { lastEase = options; },
    setStyle: (style) => { layers.clear(); style.layers.forEach((layer) => layers.set(layer.id, layer)); },
    once: (event, callback) => { if (event === "idle") idle.push(callback); },
  };
  const context = vm.createContext({
    window: {}, document: { documentElement: {} }, console,
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
  });
  const injectable = source("map.js").replace(
    "return { init, applyColors",
    "return { _setMapForTest: value => { map = value; }, init, applyColors",
  );
  vm.runInContext(injectable, context);
  const worldMap = context.window.WorldMap;
  worldMap._setMapForTest(map);
  worldMap.restyle();
  idle.shift()();
  worldMap.setPinnedLevel(2);
  while (idle.length) idle.shift()();
  worldMap.restyle();
  while (idle.length) idle.shift()();
  assert.strictEqual(worldMap.getPinnedLevel(), 2);
  assert.strictEqual(layers.get("admin2-fill").minzoom, 2);
  assert.strictEqual(layers.get("admin0-fill").layout.visibility, "none");

  const usa = data("admin0.json").find((row) => row.id === "USA");
  worldMap.fitBBox(usa.bbox, 4.2, usa.point);
  assert.deepStrictEqual(Array.from(lastEase.center), Array.from(usa.point));
}

/* A fact tile has to carry the sentence that says how to read it.
 *
 * Both halves of this were shipped and neither reached a reader. A gap built
 * by common.py's `gap()` carries its reason inside the value; a figure that
 * needs a caveat carries it beside the record as `<field>_note`. The
 * composition panels printed theirs and the fact tiles printed neither, so
 * India's 98 districts with no 2011 head count said "Not available" and
 * nothing else -- which is the blank this project exists to prevent, because
 * it reads as "nobody ran the adapter" rather than "the district did not
 * exist when the census counted" -- and the 75 that show the undivided
 * district's count said nothing about the ground that count is really for.
 *
 * Asserted on both a gap and a value, because the second is the worse case:
 * there the panel shows a number and the note is the only thing saying what
 * the number is about.
 */
function factTilesCarryTheirStatedReason() {
  const rendered = [];
  const container = {
    set innerHTML(html) { rendered.push(html); },
    get innerHTML() { return rendered[rendered.length - 1] || ""; },
    scrollTop: 0,
    querySelectorAll: () => [],
  };
  const context = vm.createContext({ window: {}, console });
  vm.runInContext(source("data.js"), context);
  vm.runInContext(source("palette.js"), context);
  context.window.DataStore = { country: () => null, get: () => null, children: () => [] };
  vm.runInContext(source("dashboard.js"), context);

  const uncounted = "Agar did not exist at the 2011 census: it was created in 2013.";
  const undivided = "This figure is for Shajapur as the 2011 census measured it.";
  context.window.Dashboard.render({
    id: "IND-TEST", level: "admin2", name: "Agar", country: "IND",
    population: { status: "not_available", note: uncounted },
    sex_ratio: { value: 938, unit: "females_per_1000_males", year: 2011 },
    sex_ratio_note: undivided,
  }, container);

  const html = container.innerHTML;
  // The reason itself, not merely some note: a panel that prints "Not
  // available" and a generic apology is the state this test exists to fail.
  assert.ok(html.includes(uncounted),
            "a gap's own note must reach the population tile");
  assert.ok(html.includes(undivided),
            "a value's <field>_note must reach its tile");
  // Behind the same "i" a composition heading uses, rather than loose in a
  // two-column grid of tiles.
  assert.ok(/class="fact-label">Population<button type="button" class="info"/.test(html),
            "the note belongs to the tile's own label");

  // And a gap with nothing written about it must not grow an empty bubble.
  rendered.length = 0;
  context.window.Dashboard.render({
    id: "IND-TEST-2", level: "admin2", name: "Nowhere", country: "IND",
    population: { status: "not_available" },
  }, container);
  assert.ok(!/class="fact-label">Population<button/.test(container.innerHTML),
            "a gap with no stated reason gets no info button");
}

(async () => {
  await concurrentLoadsAreIndexedOnce();
  await deepSearchWaitsForTheSecondShard();
  uncertainSharesKeepTheirQualifier();
  mapStateSurvivesThemeChangesAndUsesRepresentativePoints();
  factTilesCarryTheirStatedReason();
  console.log("frontend regression tests passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
