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
  const byId = new Map();                 // shapeID -> record
  const countryRecords = new Map();       // ISO3 -> admin-0 record
  const childrenOf = new Map();           // parent id -> [record]
  const loaded = { admin0: false, admin1: new Set(), admin2: new Set() };
  const inflight = new Map();
  const listeners = new Set();
  let coverage = null;

  function on(fn) { listeners.add(fn); return () => listeners.delete(fn); }
  function emit(event) { listeners.forEach((fn) => { try { fn(event); } catch (e) { console.error(e); } }); }

  /** Read the build stamp once, so every other request can be cache-busted. */
  async function loadVersion() {
    if (version) return version;
    try {
      const res = await fetch(BASE + "build.json", { cache: "no-store" });
      if (res.ok) version = (await res.json()).version || "";
    } catch (err) {
      // No stamp is survivable -- requests just fall back to HTTP caching.
      console.warn("build stamp unavailable", err);
    }
    return version;
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
      byId.set(record.id, record);
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
    try {
      const records = await getJSON(`${key}/${iso3}.json`);
      index(records);
      loaded[key].add(iso3);
      emit({ type: key, country: iso3, count: records.length });
      return records;
    } catch (err) {
      // A 404 here means the country genuinely has no units at that level in
      // geoBoundaries -- remember it so we do not retry on every map move.
      loaded[key].add(iso3);
      emit({ type: key, country: iso3, count: 0, error: String(err) });
      return [];
    }
  }

  function childrenOfCountry(iso3, level) {
    const out = [];
    for (const record of byId.values()) {
      if (record.country === iso3 && record.level === (level === 1 ? "admin1" : "admin2")) {
        out.push(record);
      }
    }
    return out;
  }

  async function ensureLoaded(iso3List, level) {
    const pending = iso3List.filter((iso3) => iso3 && !loaded[level === 1 ? "admin1" : "admin2"].has(iso3));
    if (!pending.length) return false;
    await Promise.all(pending.map((iso3) => loadLevel(iso3, level)));
    return true;
  }

  async function loadCoverage() {
    if (!coverage) coverage = await getJSON("coverage.json");
    return coverage;
  }

  function get(id) { return byId.get(id) || null; }
  function country(iso3) { return countryRecords.get(iso3) || null; }
  function children(id) { return childrenOf.get(id) || []; }
  function countries() { return Array.from(countryRecords.values()); }
  function isLoaded(iso3, level) { return loaded[level === 1 ? "admin1" : "admin2"].has(iso3); }
  function all() { return byId; }

  return { loadCountries, loadLevel, ensureLoaded, loadCoverage, get, country,
           children, countries, isLoaded, all, on, url, loadVersion };
})();

/* ------------------------------------------------------------------ format */
window.Fmt = (function () {
  "use strict";

  const GAP_STATUSES = new Set(["not_available", "not_collected", "not_applicable"]);

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

  const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
  const plain = new Intl.NumberFormat();

  function number(n, { style = "compact" } = {}) {
    if (!Number.isFinite(n)) return "—";
    return style === "compact" && Math.abs(n) >= 10000 ? compact.format(n) : plain.format(n);
  }

  function pct(n) {
    if (!Number.isFinite(n)) return "—";
    return `${n >= 10 ? Math.round(n) : Math.round(n * 10) / 10}%`;
  }

  function escape(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  return { isGap, gapStatus, valueOf, number, pct, escape };
})();
