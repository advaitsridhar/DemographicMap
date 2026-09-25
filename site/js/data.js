/* Data loading and caching.
 *
 * Geometry lives in PMTiles; attributes live in small JSON files keyed by
 * geoBoundaries shapeID. Nothing below admin-0 is fetched until it is needed:
 * admin-1 for a country loads when that country comes into view or is selected,
 * admin-2 loads when an admin-1 unit is opened. That keeps the first paint to a
 * couple of hundred kilobytes even though the full attribute set is ~30 MB.
 */
window.DataStore = (function () {
  "use strict";

  const BASE = "data/";
  // Appended to every data URL so a redeploy is picked up immediately.
  // Deliberately NOT "force-cache" below: that directive serves the stored
  // response whatever its age and only touches the network when nothing is
  // stored, so a viewer who had opened the map once kept that day's figures
  // for good and every later deploy was invisible to them. The in-memory
  // maps here already stop a shard being fetched twice in one session, which
  // is all the caching this needs.
  let version = "";
  // One map per level, and one over all of them.
  //
  // A shapeID is not unique across levels: 334 polygons are drawn at both,
  // under one id -- every one of Moldova's 37 districts among them. Keyed by id
  // alone, the second level's records replaced the first's the moment a
  // district was clicked (which loads the level below), and the first-level
  // layer, painted from records of its own level, went blank. Each level now
  // keeps its own, and the shared map prefers the shallower record, which is
  // the one a caller that does not say which level means.
  const byLevel = { admin0: new Map(), admin1: new Map(), admin2: new Map() };
  const DEPTH = { admin0: 0, admin1: 1, admin2: 2 };
  const LEVEL_KEYS = ["admin0", "admin1", "admin2"];
  const byId = new Map();                 // shapeID -> record, the shallowest level's
  const countryRecords = new Map();       // ISO3 -> admin-0 record
  const childrenOf = new Map();           // parent id -> [record]
  const loaded = { admin0: false, admin1: new Set(), admin2: new Set() };
  const inflight = new Map();
  const levelInflight = new Map();
  // When a country's shard last failed, so that a map move does not ask for
  // it again on every frame while the host is still answering badly.
  const failedAt = new Map();
  const RETRY_PAUSE = 3000;
  const listeners = new Set();
  let coverage = null;
  let groups = null;
  // Countries whose second level covers only part of the country, from the
  // build stamp. The map needs it to know where to put land under ground that
  // is in no unit.
  let partialLevels = [];

  function on(fn) { listeners.add(fn); return () => listeners.delete(fn); }
  function emit(event) { listeners.forEach((fn) => { try { fn(event); } catch (e) { console.error(e); } }); }

  /** Read the build stamp once, so every other request can be cache-busted. */
  async function loadVersion() {
    if (version) return version;
    try {
      const res = await fetch(BASE + "build.json", { cache: "no-store" });
      if (res.ok) {
        const stamp = await res.json();
        version = stamp.version || "";
        if (Array.isArray(stamp.partial_levels)) partialLevels = stamp.partial_levels;
      }
    } catch (err) {
      // No stamp is survivable -- requests just fall back to HTTP caching.
      console.warn("build stamp unavailable", err);
    }
    return version;
  }

  // "GTM.units.json", never "GTM.json": a content blocker matches the whole
  // URL, case-blind, and ".json" begins with ".js" -- EasyPrivacy's "/gtm.js",
  // aimed at Google Tag Manager and on by default in uBlock Origin, refused
  // Guatemala's file every time. One fixed word before ".json" means no
  // country code is ever read as a script's name (scripts/common.py writes
  // the same names; scripts/probe_blocklists.py checks them).
  function shardPath(key, iso3) {
    return `${key}/${iso3}.units.json`;
  }

  function url(path) {
    return BASE + path + (version ? (path.includes("?") ? "&" : "?") + "v=" + version : "");
  }

  async function getJSON(path) {
    if (inflight.has(path)) return inflight.get(path);
    const p = loadVersion()
      .then(() => fetch(url(path)))
      .then((res) => {
        if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
        return res.json();
      })
      .finally(() => inflight.delete(path));
    inflight.set(path, p);
    return p;
  }

  function index(records) {
    for (const record of records) {
      if (byLevel[record.level]) byLevel[record.level].set(record.id, record);
      const held = byId.get(record.id);
      if (!held || !(held.level in DEPTH) || !(record.level in DEPTH)
          || DEPTH[record.level] <= DEPTH[held.level]) {
        byId.set(record.id, record);
      }
      const parent = record.parent;
      if (parent) {
        if (!childrenOf.has(parent)) childrenOf.set(parent, []);
        childrenOf.get(parent).push(record);
      }
    }
  }

  async function loadCountries() {
    if (loaded.admin0) return countryRecords;
    const records = await getJSON("admin0.json");
    index(records);
    for (const record of records) countryRecords.set(record.id, record);
    loaded.admin0 = true;
    emit({ type: "admin0" });
    return countryRecords;
  }

  /** Load one country's admin-1 (level 1) or admin-2 (level 2) attributes. */
  async function loadLevel(iso3, level) {
    if (!iso3 || level < 1 || level > 2) return [];
    const key = level === 1 ? "admin1" : "admin2";
    if (loaded[key].has(iso3)) return childrenOfCountry(iso3, level);
    const loadKey = `${key}/${iso3}`;
    if (levelInflight.has(loadKey)) return levelInflight.get(loadKey);
    if (Date.now() - (failedAt.get(loadKey) || -Infinity) < RETRY_PAUSE) return [];
    const task = (async () => {
      try {
      const records = await getJSON(shardPath(key, iso3));
      index(records);
      loaded[key].add(iso3);
      emit({ type: key, country: iso3, count: records.length });
      return records;
    } catch (err) {
      // Nothing is remembered as "no units". A dropped connection or a
      // timeout used to be, and then every click in that country said "No
      // data record for that unit" until the page was reloaded: one failed
      // request for Guatemala's municipios left all 342 unreachable. A 404
      // was still remembered, as a country with nothing at that level --
      // but the build writes both files for every one of its 218 countries,
      // so a 404 is only ever a request that met a deploy half-way. The
      // next click or map move asks again, once a short pause has passed.
      failedAt.set(loadKey, Date.now());
      emit({ type: key, country: iso3, count: 0, error: String(err) });
      return [];
      } finally {
        levelInflight.delete(loadKey);
      }
    })();
    levelInflight.set(loadKey, task);
    return task;
  }

  function childrenOfCountry(iso3, level) {
    const out = [];
    for (const record of byLevel[level === 1 ? "admin1" : "admin2"].values()) {
      if (record.country === iso3) out.push(record);
    }
    return out;
  }

  // How many attribute shards to fetch at once. Pinning the map to second-level
  // divisions at world view asks for all 218 of them -- 48 MB -- and firing
  // that as one Promise.all queues hundreds of requests the browser will not
  // run in parallel anyway, delaying the first colour until nearly the last
  // byte. In batches the map fills in as the data arrives.
  const BATCH = 6;

  async function ensureLoaded(iso3List, level) {
    const key = level === 1 ? "admin1" : "admin2";
    const pending = iso3List.filter((iso3) => iso3 && !loaded[key].has(iso3));
    if (!pending.length) return false;
    // Progress is counted per shard, not per batch. The largest files land last
    // and one of them is 13 MB, so a batch-sized counter sat at "168 of 174" for
    // ten seconds at the end and read as a stall.
    let done = 0;
    for (let i = 0; i < pending.length; i += BATCH) {
      const batch = pending.slice(i, i + BATCH);
      await Promise.all(batch.map((iso3) => loadLevel(iso3, level).then((rows) => {
        done += 1;
        emit({ type: "progress", level: key, done, total: pending.length });
        return rows;
      })));
    }
    return true;
  }

  async function loadCoverage() {
    if (!coverage) coverage = await getJSON("coverage.json");
    return coverage;
  }

  // The worldwide list of what can be filtered on, built over every record at
  // build time. It cannot be derived here: at world zoom the app holds only
  // country records, so a picker fed from what is loaded would offer nothing
  // below the national level, and one fed from a single country's shard would
  // offer only that country's spellings of each group.
  async function loadGroups() {
    if (!groups) groups = await getJSON("groups.json");
    return groups;
  }

  /** The record for ``id``; at ``level`` (0-2 or "admin0".."admin2") where
   *  the caller knows which, since one id can be drawn at two levels. */
  function get(id, level) {
    const key = typeof level === "number" ? LEVEL_KEYS[level] : level;
    const hit = key && byLevel[key] ? byLevel[key].get(id) : null;
    return hit || byId.get(id) || null;
  }
  /** Every loaded record at one level. */
  function atLevel(level) {
    const key = typeof level === "number" ? LEVEL_KEYS[level] : level;
    return byLevel[key] ? byLevel[key].values() : [].values();
  }
  function country(iso3) { return countryRecords.get(iso3) || null; }
  function children(id) { return childrenOf.get(id) || []; }
  function countries() { return Array.from(countryRecords.values()); }
  function isLoaded(iso3, level) { return loaded[level === 1 ? "admin1" : "admin2"].has(iso3); }
  function all() { return byId; }

  /** The declared partial levels, once the build stamp has been read. */
  async function loadPartialLevels() {
    await loadVersion();
    return partialLevels;
  }

  return { loadPartialLevels,
           loadCountries, loadLevel, ensureLoaded, loadCoverage, loadGroups,
           get, atLevel, country, children, countries, isLoaded, all, on, url,
           loadVersion, shardPath };
})();

/* ------------------------------------------------------------------ format */
window.Fmt = (function () {
  "use strict";

  // An estimate ("derived", "modelled") is a gap that carries a guess. It is
  // listed here so that everything asking "is there a real value" hears no:
  // gapStatus() falls through to "present" for a status it does not know,
  // and an unregistered estimate would be painted as read data.
  const GAP_STATUSES = new Set(["not_available", "not_collected", "not_applicable",
                                "derived", "modelled"]);

  function isGap(value) {
    return value == null || (typeof value === "object" && !Array.isArray(value) &&
                             GAP_STATUSES.has(value.status)) ||
           (Array.isArray(value) && value.length === 0);
  }

  function gapStatus(value) {
    if (value == null) return "not_available";
    if (Array.isArray(value)) return value.length ? "present" : "not_available";
    if (typeof value === "object" && GAP_STATUSES.has(value.status)) return value.status;
    return "present";
  }

  function valueOf(value) {
    if (isGap(value)) return null;
    if (typeof value === "object" && !Array.isArray(value) && "value" in value) return value.value;
    return value;
  }

  const ESTIMATE_STATUSES = new Set(["derived", "modelled"]);

  /** A gap that carries a guess: a registered estimate status with its rows. */
  function isEstimate(value) {
    return value != null && typeof value === "object" && !Array.isArray(value) &&
           ESTIMATE_STATUSES.has(value.status) && Array.isArray(value.estimate);
  }

  /* The rows of a composition field, and the one place an estimate's rows
   * can be read as if they were one.
   *
   * A real composition is a list and comes back as it is. An estimate is a
   * dict, and its `estimate` array comes back only when the caller says
   * `{estimates: true}` -- otherwise null, the same answer as for any other
   * gap. Every consumer that must never see an estimate (tally, dominant,
   * the filter's counts, the panel's totals) calls this with the default and
   * so cannot; the paint path opts in by name, which is what makes the
   * opt-in greppable.
   */
  function compositionOf(value, { estimates = false } = {}) {
    if (Array.isArray(value)) return value;
    if (estimates && isEstimate(value)) return value.estimate;
    return null;
  }

  const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
  const plain = new Intl.NumberFormat();

  function number(n, { style = "compact" } = {}) {
    if (!Number.isFinite(n)) return "—";
    return style === "compact" && Math.abs(n) >= 10000 ? compact.format(n) : plain.format(n);
  }

  /* Two percentage formats, because they answer different questions.
   *
   * `pct` is for a single figure read on its own -- a hover readout, a legend
   * end -- where "91%" is easier to take in than "90.9%" and the tenth adds
   * nothing.
   *
   * `pct1` is for a figure read in a column with others. There the tenth is
   * the whole point: rounding 90.9 to 91 makes a composition that sums to
   * exactly 100.0 look as though it sums to 100.1, and a reader who checks
   * the arithmetic is entitled to find it correct.
   */
  function pct(n) {
    if (!Number.isFinite(n)) return "—";
    return `${n >= 10 ? Math.round(n) : Math.round(n * 10) / 10}%`;
  }

  function pct1(n) {
    if (!Number.isFinite(n)) return "—";
    return `${(Math.round(n * 10) / 10).toFixed(1)}%`;
  }

  function escape(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  return { isGap, gapStatus, valueOf, isEstimate, compositionOf, number, pct, pct1, escape };
})();
