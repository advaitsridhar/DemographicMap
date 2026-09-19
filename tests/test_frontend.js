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

/* A leader is only a leader if nothing missing could beat it.
 *
 * Not every composition partitions its population. The Factbook gives the DRC
 * six religions summing to 6.8%; Bangladesh's census enumerates ethnic groups
 * covering 1% of the country and nobody else. Asked which group leads, this
 * map answered from the list it had and said the DRC's largest religion is
 * Kimbanguist at 2.8% -- with 93.2% of Congolese unlisted, any of whom could
 * outweigh it several times over. The panel kept saying the list describes
 * 6.8% of the population while the map painted a winner from it.
 */
function aLeaderIsOnlyNamedWhenNothingMissingCouldBeatIt() {
  const context = vm.createContext({ window: {}, console });
  vm.runInContext(source("data.js"), context);
  context.window.Palette = {
    sequential: () => "blue", neutral: () => "grey", ramp: () => [],
    categorical: () => "blue", group: () => "blue", unplaced: () => "violet",
    status: () => ({ color: "grey" }), groupRamp: () => [], SHARE_FLOOR: 25,
  };
  vm.runInContext(source("metrics.js"), context);
  context.window.Metrics.setGroupIndex(data("groups.json"));
  const M = context.window.Metrics;

  // A composition that partitions its population: unchanged.
  const whole = { religion: [{ group: "Islam", pct: 91 },
                             { group: "Hinduism", pct: 8 },
                             { group: "Christianity", pct: 1 }] };
  assert.strictEqual(M.largestShare(whole, "religion"), 91);
  assert.ok(M.dominant(whole, "religion", 1), "a whole composition still has a leader");

  // 6.8% of a population, led by 2.8%: 2.8 cannot exceed the 93.2 unlisted.
  const sliver = { religion: [{ group: "Kimbanguist", pct: 2.8 },
                              { group: "Christianity", pct: 2.0 },
                              { group: "Islam", pct: 2.0 }] };
  assert.strictEqual(M.largestShare(sliver, "religion"), null,
                     "no leader may be named from a composition of 6.8%");
  assert.strictEqual(M.dominant(sliver, "religion", 1), null,
                     "and the map must not paint one either");

  // Short of 100 but decisively led: 60 beats the 10 unlisted, so it stands.
  const mostly = { religion: [{ group: "Islam", pct: 60 },
                              { group: "Hinduism", pct: 30 }] };
  assert.strictEqual(M.largestShare(mostly, "religion"), 60);

  // Multi-response sums past 100, leaving no remainder at all.
  const several = { language: [{ group: "English", pct: 80 },
                               { group: "Spanish", pct: 40 }] };
  assert.strictEqual(M.largestShare(several, "language"), 80);

  // The readout goes quiet with the map rather than disagreeing with it.
  assert.strictEqual(
    M.METRICS.largest_share.display(sliver, { field: "religion" }), "—");
}

/* Ground in no second-order unit must read as land, not as ocean.
 *
 * Uruguay's second-order units are municipios, and municipios do not tile the
 * country: 124 of them cover 36.8% of it. Every fill in the style paints a
 * *unit*, so the other 63.2% had no polygon over it and fell through to the
 * background -- which is the water colour. Zoomed past the point where the
 * first-order layer has faded out, two thirds of Uruguay was drawn as sea.
 *
 * A missing figure is a gap and the map says so in the panel. Ground drawn as
 * ocean is a different thing: a false statement about the world, made by the
 * map itself, and the one this project ranks as worse.
 *
 * Three things are asserted, because the layer is only right if all three
 * hold: it sits under every data fill (or it would paint over real figures),
 * it carries no data colour (or an unmapped stretch of Durazno would borrow
 * its department's number), and it is filtered rather than global (or every
 * country's lakes and coastline would silently become land).
 */
function groundInNoUnitReadsAsLandRatherThanSea() {
  const layers = new Map();
  const order = [];
  const filters = new Map();
  const map = {
    getLayer: (id) => layers.get(id),
    setFilter: (id, filter) => { filters.set(id, filter); },
    getStyle: () => ({ layers: order.map((id) => layers.get(id)) }),
    setLayoutProperty: () => {}, setLayerZoomRange: () => {},
    setPaintProperty: () => {}, setMinZoom: () => {}, getZoom: () => 8,
    setZoom: () => {}, easeTo: () => {},
    once: (event, callback) => { if (event === "idle") callback(); },
    setStyle: (style) => {
      layers.clear();
      order.length = 0;
      style.layers.forEach((layer) => { layers.set(layer.id, layer); order.push(layer.id); });
    },
  };
  const context = vm.createContext({
    window: {}, document: { documentElement: {} }, console,
    getComputedStyle: () => ({ getPropertyValue: (name) => (name === "--land-base" ? "#eceae4" : "") }),
  });
  const injectable = source("map.js").replace(
    "return { init, applyColors",
    "return { _setMapForTest: value => { map = value; }, init, applyColors",
  );
  vm.runInContext(injectable, context);
  const worldMap = context.window.WorldMap;
  worldMap._setMapForTest(map);
  worldMap.restyle();

  const land = layers.get("partial-land");
  assert.ok(land, "the style must carry a land layer for partial levels");

  // Under every fill that paints a unit, and over the water background.
  assert.ok(order.indexOf("partial-land") > order.indexOf("background"),
            "land must sit above the water background");
  for (const id of ["admin0-fill", "admin1-fill", "admin2-fill"]) {
    assert.ok(order.indexOf("partial-land") < order.indexOf(id),
              `land must sit below ${id} so it never covers a real figure`);
  }

  // A flat colour. No feature-state, so no unit's value leaks onto ground
  // that is in no unit.
  assert.strictEqual(land.paint["fill-color"], "#eceae4",
                     "the land underlay carries no data colour");

  // Nothing until the build says which countries, and only those countries.
  const plain = (value) => JSON.parse(JSON.stringify(value));
  assert.deepStrictEqual(plain(land.filter),
                         ["in", ["get", "shapeGroup"], ["literal", []]],
                         "no country is land-backed before the build stamp arrives");

  worldMap.setPartialLevels([{ iso3: "URY", level: "admin2", coverage_pct: 36.8 }]);
  assert.deepStrictEqual(plain(filters.get("partial-land")),
                         ["in", ["get", "shapeGroup"], ["literal", ["URY"]]],
                         "only the declared countries get land under them");

  // And a restyle (the theme toggle) must not quietly drop it again.
  worldMap.restyle();
  assert.deepStrictEqual(plain(layers.get("partial-land").filter),
                         ["in", ["get", "shapeGroup"], ["literal", ["URY"]]],
                         "a theme change must not lose the declaration");
}

/* The land underlay must survive the style loading after the list arrives.
 *
 * MapLibre does not build the style synchronously: Style.loadJSON defers
 * _load to the next animation frame, and getLayer() reads the table _load
 * fills. build.json is already cached by the time the app reaches init(), so
 * setPartialLevels() normally runs in a microtask *before* that frame -- finds
 * no "partial-land" layer, skips the setFilter, and the style keeps the empty
 * list it was built with. Uruguay rendered as sea on every cold load and was
 * only put right by the theme toggle, which rebuilds the style from state.
 *
 * The test above could not see this because its stub answers getLayer at
 * once. This one answers it the way MapLibre does: undefined until the style
 * has loaded, then the layer -- and asserts the filter is on it afterwards.
 */
function thePartialListAppliesWhenTheStyleLoadsAfterIt() {
  const listeners = new Map();
  let loaded = false;
  let styleLayers = [];
  const filters = new Map();
  class Map_ {
    constructor(options) { styleLayers = options.style.layers; }
    on(event, callback) { listeners.set(event, callback); }
    once() {}
    addControl() {}
    getLayer(id) { return loaded ? styleLayers.find((l) => l.id === id) : undefined; }
    setFilter(id, filter) { filters.set(id, filter); }
    getZoom() { return 2; }
    setStyle(style) { styleLayers = style.layers; }
    setLayoutProperty() {} setLayerZoomRange() {} setPaintProperty() {}
    setMinZoom() {} setZoom() {} easeTo() {} resize() {}
  }
  const context = vm.createContext({
    window: {
      maplibregl: { Map: Map_, NavigationControl: class {}, ScaleControl: class {},
                    Popup: class {}, addProtocol() {} },
      pmtiles: { Protocol: class { constructor() { this.tile = () => {}; } } },
    },
    document: { documentElement: {}, getElementById: () => ({}) },
    console,
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
  });
  vm.runInContext(source("map.js"), context);
  const worldMap = context.window.WorldMap;
  worldMap.init({});

  // The list lands before the style has: nothing to filter yet.
  worldMap.setPartialLevels([{ iso3: "URY" }]);
  assert.strictEqual(filters.get("partial-land"), undefined,
                     "there is no layer to filter before the style loads");

  // Then the style loads, as it does a frame later in the browser.
  loaded = true;
  assert.ok(listeners.has("style.load"), "the map must listen for the style loading");
  listeners.get("style.load")();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(filters.get("partial-land"))),
                         ["in", ["get", "shapeGroup"], ["literal", ["URY"]]],
                         "the declared list reaches the layer once it exists");
}

/* An estimate is drawn as figures, with its caveat in one sentence.
 *
 * The first rendering treated an estimate as a gap and printed its whole note
 * -- a paragraph per panel, three panels per unit -- with the shares folded
 * away under it. The owner's words: "why don't you just publish the estimates
 * with a note? that giant block of text is so annoying". So: the same stacked
 * bar and list a reading gets, a badge naming the status, the note's first
 * sentence in the open, and the rest behind the "i" where every other
 * composition keeps its note.
 */
function estimatesAreDrawnAsFiguresWithOneSentence() {
  const rendered = [];
  const container = {
    set innerHTML(html) { rendered.push(html); },
    get innerHTML() { return rendered[rendered.length - 1] || ""; },
    scrollTop: 0,
    querySelectorAll: () => [],
  };
  // palette.js reads the page's theme stamp to pick a categorical colour, and
  // the harness has no page: give it a bare element that has none stamped.
  const context = vm.createContext({
    window: {}, console,
    document: { documentElement: { getAttribute: () => null } },
    matchMedia: () => ({ matches: false }),
  });
  context.window.matchMedia = context.matchMedia;
  vm.runInContext(source("data.js"), context);
  vm.runInContext(source("palette.js"), context);
  context.window.DataStore = { country: () => null, get: () => null, children: () => [] };
  vm.runInContext(source("dashboard.js"), context);

  const first = "Modelled from the 2000 census home-language table.";
  const rest = "The Tai groups are assigned by region and cannot be separated, and the Thai Chinese are counted as Thai.";
  context.window.Dashboard.render({
    id: "THA-TEST", level: "admin1", name: "Amnat Charoen", country: "THA",
    ethnicity: { status: "modelled", census_year: 2000,
                 estimate: [{ group: "Isan (Lao)", pct: 97.5 }, { group: "Khmer", pct: 2.5 }],
                 note: `${first} ${rest}` },
  }, container);
  const html = container.innerHTML;

  assert.ok(html.includes('class="stack-bar"'), "an estimate gets the stacked bar a reading gets");
  assert.ok(/Isan \(Lao\)<\/span>\s*<span class="pct">97\.5%/.test(html),
            "the estimate's shares are listed like a reading's");
  assert.ok(/chip-estimate[^>]*>[^<]*Modelled</.test(html), "the badge names the status");
  assert.ok(html.includes(`class="estimate-why">${first}<`), "the note's first sentence is in the open");
  // The rest of the note appears exactly once, and only inside the "i".
  const at = html.indexOf(rest);
  assert.ok(at > 0 && html.indexOf(rest, at + 1) === -1, "the rest of the note is printed once");
  assert.ok(html.lastIndexOf("data-info-text=", at) > html.lastIndexOf("</h3>", at),
            "and that once is behind the heading's info button");
  assert.ok(!/<div class="gap-note">[^]*?Modelled/.test(html) || !html.includes(`<strong>Estimated, not published.</strong> ${first}`),
            "the estimate is not also printed as a gap paragraph");
  assert.ok(/class="panel-year">2000</.test(html), "the estimate's own year is shown");

  // An estimate with no shares is still a gap that says why.
  rendered.length = 0;
  context.window.Dashboard.render({
    id: "THA-TEST-2", level: "admin1", name: "Nowhere", country: "THA",
    ethnicity: { status: "modelled", estimate: [], note: "Nothing could be modelled here." },
  }, container);
  assert.ok(container.innerHTML.includes('class="gap-note"'), "no shares, so a gap note");
  assert.ok(container.innerHTML.includes("Nothing could be modelled here."));
}

function estimatesAreGapsInTheBrowser() {
  // An estimate is a gap that carries a guess. gapStatus() falls through to
  // "present" for a status it has not seen, so an unregistered "modelled"
  // dict would be painted as read data -- which is the one thing
  // docs/MODELLING.md says an estimate must never do.
  const context = vm.createContext({ window: {}, console });
  vm.runInContext(source("data.js"), context);
  vm.runInContext(source("palette.js"), context);
  const Fmt = context.window.Fmt;
  const guess = { status: "modelled", estimate: [{ group: "A", pct: 60 }], note: "n" };
  assert.strictEqual(Fmt.isGap(guess), true, "a modelled value is a gap");
  assert.strictEqual(Fmt.gapStatus(guess), "modelled");
  assert.strictEqual(Fmt.isGap({ status: "derived", estimate: [] }), true);
  assert.strictEqual(Fmt.valueOf(guess), null, "nothing reads the guess as a value");
  const Palette = context.window.Palette;
  assert.strictEqual(Palette.status("modelled").label, "Estimated, not published");
  assert.strictEqual(Palette.status("derived").label, "Derived from published figures");
  assert.notStrictEqual(Palette.status("modelled").color, Palette.status("not_available").color,
                        "an estimate is not painted as an ordinary gap");
  assert.notStrictEqual(Palette.status("modelled").color, Palette.status("present").color,
                        "an estimate is not painted as a reading");
}

(async () => {
  await concurrentLoadsAreIndexedOnce();
  await deepSearchWaitsForTheSecondShard();
  uncertainSharesKeepTheirQualifier();
  mapStateSurvivesThemeChangesAndUsesRepresentativePoints();
  factTilesCarryTheirStatedReason();
  aLeaderIsOnlyNamedWhenNothingMissingCouldBeatIt();
  groundInNoUnitReadsAsLandRatherThanSea();
  thePartialListAppliesWhenTheStyleLoadsAfterIt();
  estimatesAreGapsInTheBrowser();
  estimatesAreDrawnAsFiguresWithOneSentence();
  console.log("frontend regression tests passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
