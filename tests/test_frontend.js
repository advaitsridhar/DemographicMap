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

(async () => {
  await concurrentLoadsAreIndexedOnce();
  await deepSearchWaitsForTheSecondShard();
  uncertainSharesKeepTheirQualifier();
  mapStateSurvivesThemeChangesAndUsesRepresentativePoints();
  console.log("frontend regression tests passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
