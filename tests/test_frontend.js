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
    hasImage() { return false; } addImage() {}
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
  // The one door to an estimate's rows, and it is shut unless opened by name.
  assert.strictEqual(Fmt.compositionOf(guess), null, "closed by default");
  assert.strictEqual(Fmt.compositionOf(guess, { estimates: false }), null);
  assert.strictEqual(Fmt.compositionOf(guess, { estimates: true }), guess.estimate,
                     "opened only by an explicit opt-in");
  assert.strictEqual(Fmt.compositionOf({ status: "not_available" }, { estimates: true }), null,
                     "an ordinary gap has no rows to read whatever the caller asks");
  const rows = [{ group: "A", pct: 100 }];
  assert.strictEqual(Fmt.compositionOf(rows), rows, "a real composition is itself either way");
  assert.strictEqual(Fmt.compositionOf(rows, { estimates: true }), rows);
  assert.strictEqual(Fmt.isEstimate(guess), true);
  assert.strictEqual(Fmt.isEstimate(rows), false);
  const Palette = context.window.Palette;
  assert.strictEqual(Palette.status("modelled").label, "Estimated, not published");
  assert.strictEqual(Palette.status("derived").label, "Derived from published figures");
  assert.notStrictEqual(Palette.status("modelled").color, Palette.status("not_available").color,
                        "an estimate is not painted as an ordinary gap");
  assert.notStrictEqual(Palette.status("modelled").color, Palette.status("present").color,
                        "an estimate is not painted as a reading");
}

/* An estimate is painted only when asked, and counted never.
 *
 * Before this, an estimate was drawn as the gap colour on every view, so a
 * reader could not tell that one existed without opening the panel. Now the
 * two maps that read shares -- most populous group, share of one group --
 * colour it by its rows when the caller opts in by name, and the paint
 * result names the unit so the map can hatch it and the legend can say so.
 * Everything that counts, sums or ranks still calls the same functions with
 * the opt-in off, and this pins that they never see the guess.
 */
function estimatesPaintOnlyWhenAskedAndNeverCount() {
  const context = vm.createContext({
    window: { matchMedia: () => ({ matches: false }) },
    document: { documentElement: { getAttribute: () => "light" } },
    console,
  });
  vm.runInContext(source("data.js"), context);
  vm.runInContext(source("palette.js"), context);
  vm.runInContext(source("metrics.js"), context);
  context.window.Metrics.setGroupIndex(data("groups.json"));
  const M = context.window.Metrics;
  const P = context.window.Palette;
  const plain = (value) => JSON.parse(JSON.stringify(value));

  const read = { id: "R", religion: [{ group: "Buddhism", pct: 93 },
                                     { group: "Islam", pct: 5 },
                                     { group: "Christianity", pct: 2 }] };
  // Bueng Kan's shape, as site/data carries it.
  const modelled = { id: "E", religion: {
    status: "modelled", method: "tier1-split", note: "n",
    estimate: [{ group: "Buddhism", pct: 99.1 },
               { group: "Other or not stated", pct: 0.8 },
               { group: "Islam", pct: 0.1 }] } };
  const derived = { id: "D", religion: {
    status: "derived", note: "n",
    estimate: [{ group: "Roman Catholic", pct: 90 }, { group: "Other", pct: 10 }] } };
  const blank = { id: "B", religion: { status: "not_available" } };
  const records = [read, modelled, derived, blank];
  const hue = M.hueOf("religion", "Buddhism");
  assert.ok(hue, "the index places Buddhism");

  // Most populous group, estimates on: the estimate takes its leader's colour.
  const on = M.paint(records, "group", { field: "religion", depth: "2", estimates: true });
  assert.strictEqual(on.colors.get("E"), P.group(hue, 99.1, 25, 100),
                     "an estimate paints by its leading group when estimates are on");
  assert.deepStrictEqual(plain(Array.from(on.estimated)).sort(), ["D", "E"],
                         "the paint result names every unit coloured from an estimate");
  assert.deepStrictEqual(plain(on.legend.estimated), { modelled: 1, derived: 1 },
                         "and the legend is told how many of each kind");
  assert.strictEqual(on.legend.missing, 1, "the ordinary gap is still a gap");
  assert.strictEqual(on.colors.get("B"), P.neutral());

  // Estimates off: the same unit is the gap it also is.
  const off = M.paint(records, "group", { field: "religion", depth: "2", estimates: false });
  assert.strictEqual(off.colors.get("E"), P.neutral(),
                     "an estimate paints as a gap when estimates are off");
  assert.strictEqual(off.estimated.size, 0);
  assert.deepStrictEqual(plain(off.legend.estimated), {},
                         "no estimate line when none was painted");
  assert.strictEqual(off.legend.missing, 3);
  // And the default is off: nothing that forgets the flag can paint a guess.
  const silent = M.paint(records, "group", { field: "religion", depth: "2" });
  assert.strictEqual(silent.colors.get("E"), P.neutral());
  assert.strictEqual(silent.estimated.size, 0);

  // A read unit is untouched either way.
  assert.strictEqual(on.colors.get("R"), off.colors.get("R"));
  assert.strictEqual(on.colors.get("R"), P.group(hue, 93, 25, 100));
  assert.ok(!on.estimated.has("R"), "a reading is never marked as an estimate");

  // Share of one group: the derived unit answers for Christianity through
  // its Roman Catholic row; the modelled one has no such row and stays out.
  const share = M.paint(records, "group_share",
                        { field: "religion", group: "Christianity", estimates: true });
  assert.strictEqual(share.colors.get("D"),
                     P.group(M.hueOf("religion", "Christianity"), 90, 0, 100));
  assert.deepStrictEqual(plain(Array.from(share.estimated)), ["D"]);
  assert.deepStrictEqual(plain(share.legend.estimated), { derived: 1 });
  const shareOff = M.paint(records, "group_share",
                           { field: "religion", group: "Christianity", estimates: false });
  assert.strictEqual(shareOff.colors.get("D"), P.neutral());
  assert.deepStrictEqual(plain(shareOff.legend.estimated), {});
  assert.strictEqual(shareOff.colors.get("R"), share.colors.get("R"));

  // The readout says what the map painted, and says what it is -- in the
  // status's own word, the one the coverage map and the panel use.
  assert.strictEqual(
    M.METRICS.group.display(modelled, { field: "religion", depth: "2", estimates: true }),
    "Buddhism 99% (modelled)");
  assert.strictEqual(
    M.METRICS.group_share.display(derived, { field: "religion", group: "Christianity",
                                             estimates: true }),
    "90% (derived)");
  assert.strictEqual(
    M.METRICS.group.display(modelled, { field: "religion", depth: "2" }), "—");
  assert.strictEqual(
    M.METRICS.group.display(read, { field: "religion", depth: "2", estimates: true }),
    "Buddhism 93%");

  // The coverage map keeps the status colours, hatch-free.
  const status = M.paint(records, "coverage", { field: "religion", estimates: true });
  assert.strictEqual(status.colors.get("E"), P.status("modelled").color);
  assert.strictEqual(status.colors.get("D"), P.status("derived").color);
  assert.strictEqual(status.estimated.size, 0, "a status colour needs no hatch");

  // A read head count is not hatched because the religion beside it was
  // modelled: the app passes the field and the flag on every view, and only
  // the two maps that read a composition's rows may act on them.
  const counted = records.map((r) => ({ ...r, population: { value: 400000 } }));
  const heads = M.paint(counted, "population", { field: "religion", estimates: true });
  assert.ok(Number.isFinite(400000) && heads.colors.get("E") !== P.neutral(),
            "the population is painted");
  assert.strictEqual(heads.estimated.size, 0, "and nothing on it is marked as an estimate");
  assert.deepStrictEqual(plain(heads.legend.estimated), {});

  // Nothing that counts has changed its mind, in either mode.
  for (const guess of [modelled, derived]) {
    assert.strictEqual(M.tally(guess, "religion", 2).size, 0, "tally ignores an estimate");
    assert.strictEqual(M.dominant(guess, "religion", 2), null, "dominant ignores an estimate");
    assert.strictEqual(M.shareOf(guess, "religion", "Buddhism"), null);
    assert.strictEqual(M.shareOf(guess, "religion", "Christianity"), null);
    assert.strictEqual(M.largestShare(guess, "religion"), null);
  }
  assert.deepStrictEqual(plain(M.topGroups(records, "religion")),
                         ["Buddhism", "Islam", "Christianity"],
                         "the group picker's tally never sees an estimate's rows");
}

/* The hatch is a layer of its own, switched by feature-state, and it must
 * outlive a restyle.
 *
 * MapLibre will not read feature-state into `fill-pattern`, so the hatch is
 * a second fill over the colour with a constant pattern and an opacity the
 * state switches. Three things have to hold or the rendering lies: the flag
 * is written false as well as true (state persists, and a unit that stops
 * being an estimate must lose its hatch); the pattern image is added on
 * every style load, because a theme change rebuilds the style without its
 * images; and the flag is re-applied with the colour after that rebuild.
 */
function anEstimateIsColouredLikeAReading() {
  const listeners = new Map();
  const states = new Map();
  const images = new Map();
  let styleLayers = [];
  const features = [
    { id: "E", properties: { shapeID: "E", shapeGroup: "THA" } },
    { id: "R", properties: { shapeID: "R", shapeGroup: "THA" } },
  ];
  class Map_ {
    constructor(options) { styleLayers = options.style.layers; }
    on(event, callback) { listeners.set(event, callback); }
    once(event, callback) { if (event === "idle") callback(); }
    addControl() {}
    getLayer(id) { return styleLayers.find((l) => l.id === id); }
    getSource() { return {}; }
    querySourceFeatures() { return features; }
    setFeatureState(target, state) {
      states.set(target.id, Object.assign(states.get(target.id) || {}, state));
    }
    hasImage(id) { return images.has(id); }
    addImage(id, image, options) { images.set(id, { image, options }); }
    setStyle(style) {
      // As MapLibre does with diff off: a new style, no images, then the
      // style.load event.
      styleLayers = style.layers;
      images.clear();
      listeners.get("style.load")();
    }
    setFilter() {} getZoom() { return 5; }
    setLayoutProperty() {} setLayerZoomRange() {} setPaintProperty() {}
    setMinZoom() {} setZoom() {} easeTo() {} resize() {}
  }
  const drawn = [];
  const pixels = { width: 16, height: 16, data: new Uint8ClampedArray(16 * 16 * 4) };
  const canvas = {
    width: 0, height: 0,
    getContext: () => ({ clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {},
                         stroke() { drawn.push(this.strokeStyle); },
                         getImageData: () => pixels }),
  };
  const context = vm.createContext({
    window: {
      maplibregl: { Map: Map_, NavigationControl: class {}, ScaleControl: class {},
                    Popup: class {}, addProtocol() {} },
      pmtiles: { Protocol: class { constructor() { this.tile = () => {}; } } },
    },
    document: { documentElement: {}, getElementById: () => ({}), createElement: () => canvas },
    console,
    getComputedStyle: () => ({ getPropertyValue: () => "" }),
  });
  vm.runInContext(source("map.js"), context);
  const worldMap = context.window.WorldMap;
  worldMap.init({});
  listeners.get("style.load")();

  // Nothing is drawn and no pattern is registered: an estimate is coloured
  // like a reading, by the owner's decision of 21 September 2026.
  assert.ok(!images.has("estimate-hatch"), "no hatch image is registered");
  assert.strictEqual(drawn.length, 0, "nothing is drawn on a canvas");

  // No hatch layer at any level. The fill and the borders are all there is.
  const order = styleLayers.map((l) => l.id);
  for (const level of ["admin0", "admin1", "admin2"]) {
    assert.ok(!styleLayers.some((l) => l.id === `${level}-estimate`),
              `${level} has no hatch layer`);
    assert.ok(order.includes(`${level}-fill`), `${level} still has its colour`);
    assert.ok(order.includes(`${level}-line`), `${level} still has its borders`);
  }

  // A modelled unit and a read one are written identically: a colour and
  // nothing else. This is the test that would fail if a caveat crept back
  // onto the map's surface rather than into the panel.
  const colors = new Map([["E", "#123456"], ["R", "#654321"]]);
  worldMap.applyColors("admin1", colors);
  assert.deepStrictEqual(states.get("E"), { color: "#123456" },
                         "an estimated unit carries its colour and no flag");
  assert.deepStrictEqual(states.get("R"), { color: "#654321" },
                         "a read unit is written the same way");

  // A restyle -- the theme toggle -- loses the states, and must get the
  // colours back from module state without reintroducing a pattern.
  states.clear();
  worldMap.restyle();
  assert.strictEqual(states.get("E").color, "#123456", "the colour returns after a restyle");
  assert.ok(!images.has("estimate-hatch"), "and no hatch comes back with it");
}

// Moldova draws its 37 districts at both levels under the same ids, and
// selecting a district loads the level below. Keyed by id alone, those records
// replaced the first level's, and every district on the map went blank.
async function anIdDrawnAtTwoLevelsKeepsBothRecords() {
  const shards = { "admin1/MDA.json": data("admin1/MDA.json"),
                   "admin2/MDA.json": data("admin2/MDA.json") };
  const context = vm.createContext({
    window: {}, console,
    fetch: async (url) => ({
      ok: true,
      json: async () => url.includes("build.json") ? { version: "test" }
        : shards[Object.keys(shards).find((key) => url.includes(key))],
    }),
  });
  vm.runInContext(source("data.js"), context);
  const store = context.window.DataStore;
  await store.loadLevel("MDA", 1);
  await store.loadLevel("MDA", 2);
  const first = Array.from(store.atLevel(1)).filter((r) => r.country === "MDA");
  const second = Array.from(store.atLevel(2)).filter((r) => r.country === "MDA");
  assert.strictEqual(first.length, shards["admin1/MDA.json"].length,
                     "every district is still a first-level record after the level below loads");
  assert.strictEqual(second.length, shards["admin2/MDA.json"].length);
  const shared = first.find((r) => second.some((s) => s.id === r.id));
  assert.ok(shared, "Moldova still shares ids across the levels, or this test proves nothing");
  assert.strictEqual(store.get(shared.id).level, "admin1", "an unqualified lookup is the shallower");
  assert.strictEqual(store.get(shared.id, 2).level, "admin2");
  assert.strictEqual(store.get(shared.id, "admin1").level, "admin1");
  assert.strictEqual((await store.loadLevel("MDA", 1)).length, first.length);
}

(async () => {
  await concurrentLoadsAreIndexedOnce();
  await anIdDrawnAtTwoLevelsKeepsBothRecords();
  await deepSearchWaitsForTheSecondShard();
  uncertainSharesKeepTheirQualifier();
  mapStateSurvivesThemeChangesAndUsesRepresentativePoints();
  factTilesCarryTheirStatedReason();
  aLeaderIsOnlyNamedWhenNothingMissingCouldBeatIt();
  groundInNoUnitReadsAsLandRatherThanSea();
  thePartialListAppliesWhenTheStyleLoadsAfterIt();
  estimatesAreGapsInTheBrowser();
  estimatesAreDrawnAsFiguresWithOneSentence();
  estimatesPaintOnlyWhenAskedAndNeverCount();
  anEstimateIsColouredLikeAReading();
  console.log("frontend regression tests passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
