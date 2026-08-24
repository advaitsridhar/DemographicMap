/* Application wiring: map <-> data <-> sidebar <-> search <-> URL. */
(function () {
  "use strict";

  const { escape: esc, valueOf, number } = window.Fmt;

  const els = {
    metric: document.getElementById("metric-select"),
    detail: document.getElementById("detail-select"),
    groupRow: document.getElementById("group-row"),
    group: document.getElementById("group-select"),
    groupSearchRow: document.getElementById("group-search-row"),
    groupSearch: document.getElementById("group-search"),
    groupReach: document.getElementById("group-reach"),
    legend: document.getElementById("legend"),
    levelNote: document.getElementById("level-note"),
    sidebar: document.getElementById("sidebar"),
    sidebarBody: document.getElementById("sidebar-body"),
    sidebarClose: document.getElementById("sidebar-close"),
    status: document.getElementById("map-status"),
    search: document.getElementById("search-input"),
    results: document.getElementById("search-results"),
    searchStatus: document.getElementById("search-status"),
    about: document.getElementById("about-dialog"),
    aboutOpen: document.getElementById("about-open"),
    aboutClose: document.getElementById("about-close"),
    aboutSources: document.getElementById("about-sources"),
    themeToggle: document.getElementById("theme-toggle"),
  };

  const state = {
    metric: "coverage",
    field: "religion",
    group: null,
    groupIndex: null,      // site/data/groups.json, once it lands
    groupQuery: "",
    level: 0,
    selected: null,
  };

  /* ------------------------------------------------------------- theming */

  function currentTheme() {
    try {
      return localStorage.getItem("wdm-theme") || "auto";
    } catch (err) {
      return "auto";
    }
  }

  function applyTheme(theme) {
    if (theme === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("wdm-theme", theme);
    } catch (err) { /* private mode: the theme just does not persist */ }
    const icon = els.themeToggle.querySelector("[data-theme-icon]");
    icon.textContent = theme === "dark" ? "☾" : theme === "light" ? "☀" : "◐";
    els.themeToggle.setAttribute("title", "Theme: " + theme);
    if (window.WorldMap.getMap()) {
      window.WorldMap.restyle();
      refreshColors();
    }
  }

  els.themeToggle.addEventListener("click", () => {
    const order = ["auto", "light", "dark"];
    applyTheme(order[(order.indexOf(currentTheme()) + 1) % order.length]);
  });

  /* --------------------------------------------------------- status line */

  let statusTimer = null;
  function status(text, sticky) {
    clearTimeout(statusTimer);
    if (!text) { els.status.hidden = true; return; }
    els.status.textContent = text;
    els.status.hidden = false;
    if (!sticky) statusTimer = setTimeout(() => { els.status.hidden = true; }, 2200);
  }

  /* ------------------------------------------------------------- controls */

  function buildControls() {
    els.metric.innerHTML = Object.entries(window.Metrics.METRICS)
      .map(([key, metric]) => `<option value="${key}">${esc(metric.label)}</option>`).join("");
    els.metric.value = state.metric;

    els.metric.addEventListener("change", () => {
      state.metric = els.metric.value;
      syncFieldControl();
      refreshColors();
    });
    els.detail.addEventListener("change", () => {
      const value = els.detail.value;
      window.WorldMap.setPinnedLevel(value === "auto" ? null : Number(value));
    });

    els.groupSearch.addEventListener("input", () => {
      state.groupQuery = els.groupSearch.value.trim();
      populateGroupSelect();
      refreshColors();
    });

    els.group.addEventListener("change", () => {
      const parsed = splitGroupValue(els.group.value);
      state.field = parsed.field || state.field;
      state.group = parsed.group;
      refreshColors();
    });
    syncFieldControl();
  }

  // Group option values are "<field>|<group>"; the pipe keeps group names that
  // contain spaces ("Roman Catholic") intact.
  function groupValue(field, group) { return field + "|" + (group || ""); }
  function splitGroupValue(value) {
    const at = String(value || "").indexOf("|");
    if (at < 0) return { field: value, group: null };
    return { field: value.slice(0, at), group: value.slice(at + 1) || null };
  }

  function syncFieldControl() {
    const metric = window.Metrics.METRICS[state.metric];
    els.groupRow.hidden = !metric.needsField;
    els.groupSearchRow.hidden = !metric.needsGroup;
    els.groupReach.hidden = !metric.needsGroup;
    if (!metric.needsField) return;
    els.groupRow.querySelector("label").textContent = metric.needsGroup ? "Group" : "Field";
    populateGroupSelect();
  }

  function currentRecords() {
    const wanted = ["admin0", "admin1", "admin2"][window.WorldMap.getLevel()];
    const out = [];
    for (const record of window.DataStore.all().values()) {
      if (record.level === wanted) out.push(record);
    }
    return out;
  }

  const GROUP_LIMIT = 60;

  /* Options for the group picker, drawn from the worldwide index rather than
   * from whatever is on screen.
   *
   * The old list came from the loaded records, which made the filter local
   * without saying so: at world zoom it offered only groups that appear in
   * country-level records, and inside one country only that country's own
   * spellings. Asking for Islam while looking at Sri Lanka offered "Islam";
   * the same question over India offered "Muslim"; neither said the other
   * existed. The index is built over every record, so one entry now stands for
   * both and the map answers for all 119 countries that report it.
   */
  function groupOptions() {
    const metric = window.Metrics.METRICS[state.metric];
    const options = [];
    for (const field of window.Metrics.FIELDS) {
      if (!metric.needsGroup) {
        options.push({ value: groupValue(field.key, null), label: field.label });
        continue;
      }
      const entry = state.groupIndex && state.groupIndex[field.key];
      const query = state.groupQuery.toLowerCase();
      for (const group of (entry && entry.groups) || []) {
        // Match the labels a census actually used as well as the canonical
        // name, so typing "Muslim" finds Islam rather than nothing.
        const haystack = [group.name, ...(group.labels || [])].join(" ").toLowerCase();
        if (query && !haystack.includes(query)) continue;
        options.push({
          value: groupValue(field.key, group.name),
          label: `${field.label}: ${group.name}` +
                 (group.countries.length > 1 ? `  (${group.countries.length} countries)` : ""),
          countries: group.countries.length,
        });
      }
    }
    // Most widely reported first, so the top of the list is what can actually
    // be compared across borders.
    if (metric.needsGroup) {
      options.sort((a, b) => (b.countries || 0) - (a.countries || 0));
      return options.slice(0, GROUP_LIMIT);
    }
    return options;
  }

  function populateGroupSelect() {
    const options = groupOptions();
    if (!options.length) {
      const label = state.groupQuery ? `Nothing matches “${state.groupQuery}”`
                                     : "No groups loaded yet";
      els.group.innerHTML =
        `<option value="${esc(groupValue(state.field, null))}">${esc(label)}</option>`;
      describeReach(null);
      return;
    }
    els.group.innerHTML = options
      .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("");
    const wanted = groupValue(state.field, state.group);
    els.group.value = options.some((o) => o.value === wanted) ? wanted : options[0].value;
    const parsed = splitGroupValue(els.group.value);
    state.field = parsed.field;
    state.group = parsed.group;
    describeReach(parsed);
  }

  /* What the current filter actually covers, said out loud.
   *
   * A worldwide filter invites a worldwide reading, and most of these groups
   * are not reported worldwide. A map of Sikhism shaded in six countries and
   * blank everywhere else means "six countries publish this", not "nobody else
   * has any" -- and where a country measured it a different way, as the US
   * counts religious adherents reported by bodies rather than answers people
   * gave, comparing its shade with its neighbours' is comparing two questions.
   */
  function describeReach(parsed) {
    if (!parsed || !parsed.group || !state.groupIndex) {
      els.groupReach.hidden = true;
      return;
    }
    const entry = state.groupIndex[parsed.field];
    const group = entry && (entry.groups || []).find((g) => g.name === parsed.group);
    if (!group) { els.groupReach.hidden = true; return; }

    // Counted for the level on screen, not for the dataset as a whole. Islam is
    // reported by 122 countries nationally and by five at second level, so a
    // map pinned to districts that claims 122 tells the reader the opposite of
    // what it is showing -- most of the world grey.
    const levelName = ["admin0", "admin1", "admin2"][window.WorldMap.getLevel()];
    const here = (group.levels || {})[levelName];
    const shown = ["countries", "first-level divisions", "second-level divisions"]
      [window.WorldMap.getLevel()];
    const parts = [];
    if (!here || !here.units) {
      parts.push(`No ${shown} carry this figure, though ${group.countries.length} ` +
                 `${group.countries.length === 1 ? "country reports" : "countries report"} ` +
                 `it at some level. The map is blank here because the figure is ` +
                 `missing at this level, not because the share is zero.`);
    } else {
      // At country level the unit *is* the country, so "122 countries across 122
      // countries" would be the same fact said twice.
      const where = window.WorldMap.getLevel() === 0
        ? `${window.Fmt.number(here.units)} countries`
        : `${window.Fmt.number(here.units)} ${shown} across ${here.countries.length} ` +
          `${here.countries.length === 1 ? "country" : "countries"}`;
      parts.push(`At this level: ${where}. Everything else is blank because the ` +
                 `figure is missing, not zero.`);
      if (here.countries.length < group.countries.length) {
        parts.push(`${group.countries.length} countries report it nationally.`);
      }
    }
    if ((group.labels || []).length > 1) {
      parts.push(`Combines: ${group.labels.join(", ")}.`);
    }
    // Only the sub-national records carry a basis: the US county and state
    // figures count adherents reported by religious bodies, while the country
    // row beside them is the Factbook's self-identification. Saying "the USA
    // measures this as adherents" would be wrong about the country shape the
    // reader is looking at, so the sentence names the level it applies to.
    for (const [iso, basis] of Object.entries(entry.bases || {})) {
      if (!group.countries.includes(iso)) continue;
      const record = window.DataStore.country(iso);
      parts.push(`Within ${record ? record.name : iso}, state and county figures ` +
                 `count ${basis} reported by religious bodies rather than answers ` +
                 `people gave, so they are not on the same footing as the rest.`);
    }
    els.groupReach.textContent = parts.join(" ");
    els.groupReach.hidden = false;
  }

  /* -------------------------------------------------------------- legend */

  function renderLegend(legend) {
    if (!legend || legend.type === "empty") {
      els.legend.innerHTML = `<p class="control-note">No values at this level yet.</p>`;
      return;
    }
    if (legend.type === "status") {
      els.legend.innerHTML = legend.items.map((item) =>
        `<div class="legend-item">
           <span class="legend-icon" style="color:${item.color}" aria-hidden="true">${item.icon}</span>
           <span class="legend-swatch" style="background:${item.color}"></span>
           <span>${esc(item.label)}</span>
         </div>`).join("");
    } else {
      els.legend.innerHTML =
        `<div class="legend-scale" role="img" aria-label="Colour scale from ${esc(legend.low)} to ${esc(legend.high)}">
           ${legend.stops.map((c) => `<span style="background:${c}"></span>`).join("")}
         </div>
         <div class="legend-ends"><span>${esc(legend.low)}</span><span>${esc(legend.high)}</span></div>` +
        (legend.missing
          ? `<div class="legend-item">
               <span class="legend-swatch" style="background:${legend.missingColor}"></span>
               <span>No value for ${number(legend.missing)} unit${legend.missing === 1 ? "" : "s"}</span>
             </div>`
          : "");
    }
  }

  /* ------------------------------------------------------- colour refresh */

  function refreshColors() {
    const level = window.WorldMap.getLevel();
    const levelId = window.WorldMap.levelId(level);
    const records = currentRecords();
    const result = window.Metrics.paint(records, state.metric,
                                        { field: state.field, group: state.group });
    window.WorldMap.applyColors(levelId, result.colors);
    renderLegend(result.legend);
    updateLevelNote(level, records.length);
  }

  function updateLevelNote(level, count) {
    const names = ["countries", "first-level divisions", "second-level divisions"];
    const metric = window.Metrics.METRICS[state.metric];
    const parts = [number(count) + " " + names[level] + " loaded"];
    if (metric.note) parts.push(metric.note);
    els.levelNote.textContent = parts.join(" — ");
  }

  /* ------------------------------------------------------------ selection */

  async function selectEntity(id, opts) {
    const options = opts || {};
    let record = window.DataStore.get(id);

    if (!record && options.country) {
      await window.DataStore.loadLevel(options.country, options.level === 2 ? 2 : 1);
      record = window.DataStore.get(id);
    }
    if (!record) { status("No data record for that unit"); return; }

    state.selected = record;
    const levelIndex = ["admin0", "admin1", "admin2"].indexOf(record.level);
    window.WorldMap.select(id, {
      fly: options.fly,
      bbox: options.bbox || record.bbox,
      level: levelIndex < 0 ? 1 : levelIndex,
    });
    if (options.fly && !record.bbox && record.point) {
      window.WorldMap.getMap().easeTo({ center: record.point, zoom: 5, duration: 800 });
    }
    window.Dashboard.render(record, els.sidebarBody);
    els.sidebar.classList.add("is-open");

    // Pull the level below so the children list and the next zoom are ready.
    if (record.level === "admin0") window.DataStore.loadLevel(record.id, 1).then(afterLoad);
    if (record.level === "admin1") window.DataStore.loadLevel(record.country, 2).then(afterLoad);

    try {
      const url = new URL(location.href);
      url.searchParams.set("id", id);
      history.replaceState(null, "", url);
    } catch (err) { /* file:// has no history API origin */ }
  }

  function afterLoad(records) {
    if (!records || !records.length) return;
    if (state.selected) window.Dashboard.render(state.selected, els.sidebarBody);
    refreshColors();
  }

  /* ----------------------------------------------------------- map events */

  function hoverHTML(id, properties) {
    const record = window.DataStore.get(id);
    const name = (record && record.name) || properties.shapeName || id;
    const bits = [];
    if (record) {
      const metric = window.Metrics.METRICS[state.metric];
      const value = metric.evaluate(record, { field: state.field, group: state.group });
      if (metric.kind === "status") {
        const s = window.Palette.status(value);
        const field = window.Metrics.FIELDS.find((f) => f.key === state.field);
        bits.push(s.icon + " " + s.label + " — " + (field ? field.label.toLowerCase() : state.field));
      } else if (Number.isFinite(value)) {
        bits.push(metric.label + ": " + (metric.format ? metric.format(value) : value));
      } else {
        bits.push(metric.label + ": no value");
      }
      const country = window.DataStore.country(record.country);
      if (country && record.level !== "admin0") bits.push(country.name);
    } else {
      bits.push("Loading");
    }
    return `<span class="tip-name">${esc(name)}</span><span class="tip-meta">${esc(bits.join(" · "))}</span>`;
  }

  // Countries whose attributes are fetched for one view. Following the zoom,
  // forty is plenty -- that is more than fit on screen at the level being
  // shown. Pinned, the cap is the point of the feature: asking for second-level
  // divisions across the world means all 218 shards, and stopping at forty
  // would leave most of the map grey with nothing to say why.
  const VIEW_LIMIT = 40;

  async function onViewChange(level, countries) {
    if (level === 0) { refreshColors(); return; }
    const pinned = window.WorldMap.getPinnedLevel() !== null;
    const wanted = pinned ? countries : countries.slice(0, VIEW_LIMIT);
    const changed = await window.DataStore.ensureLoaded(wanted, level);
    if (changed && window.Metrics.METRICS[state.metric].needsGroup) populateGroupSelect();
    refreshColors();
    status(null);
  }

  /* -------------------------------------------------------------- startup */

  async function start() {
    applyTheme(currentTheme());
    buildControls();

    window.Dashboard.setNavigator((id) => {
      const record = window.DataStore.get(id);
      selectEntity(id, { fly: true, bbox: record && record.bbox });
    });

    els.sidebarClose.addEventListener("click", () => els.sidebar.classList.remove("is-open"));
    els.aboutOpen.addEventListener("click", () => els.about.showModal());
    els.aboutClose.addEventListener("click", () => els.about.close());
    els.about.addEventListener("click", (event) => {
      if (event.target === els.about) els.about.close();
    });

    // Colour what has arrived rather than waiting for the last shard. Pinning
    // the map to second-level divisions pulls 48 MB across 218 files, and a map
    // that stays blank until all of it lands reads as broken.
    // The counter moves on every shard; the repaint does not. Recolouring twenty
    // thousand features once per country turned a 45-second fill into minutes,
    // and the eye cannot follow a repaint that often anyway.
    let lastPaint = 0;
    window.DataStore.on((event) => {
      if (event.type !== "progress") return;
      if (event.done >= event.total) { status(null); refreshColors(); return; }
      status(`Loading ${event.level === "admin2" ? "second-level" : "first-level"} ` +
             `data — ${event.done} of ${event.total} countries`, true);
      const now = Date.now();
      if (now - lastPaint > 700) { lastPaint = now; refreshColors(); }
    });

    status("Loading country data", true);
    await window.DataStore.loadCountries();
    status(null);

    // The group index is small and independent of the map, so it is fetched
    // alongside rather than blocking the first paint. Until it lands the picker
    // is empty and matching falls back to exact labels; both correct themselves
    // the moment it arrives.
    window.DataStore.loadGroups().then((index) => {
      state.groupIndex = index;
      window.Metrics.setGroupIndex(index);
      if (window.Metrics.METRICS[state.metric].needsField) populateGroupSelect();
      refreshColors();
    }).catch(() => { /* picker stays label-local; the map still works */ });

    window.WorldMap.init({
      onReady: () => refreshColors(),
      onLevelChange: (level) => {
        state.level = level;
        describeReach(splitGroupValue(els.group.value));
        // The group list no longer depends on what is loaded, so it is not
        // rebuilt here: doing so used to discard the viewer's chosen group
        // every time the map crossed a zoom threshold.
        refreshColors();
      },
      onViewChange,
      onHover: hoverHTML,
      onSelect: (id, properties, level) => {
        selectEntity(id, { country: properties.shapeGroup, level });
      },
    });

    await window.Search.init({
      status: els.searchStatus,
      onSelect: (row) => {
        selectEntity(row.id, { fly: true, bbox: row.bbox, country: row.country, level: row.level });
      },
    });
    window.Search.attach(els.search, els.results);

    renderAboutSources();

    let deepLink = null;
    try { deepLink = new URL(location.href).searchParams.get("id"); } catch (err) { /* ignore */ }
    if (deepLink) {
      const row = window.Search.get(deepLink);
      selectEntity(deepLink, {
        fly: true,
        bbox: row && row.bbox,
        country: row && row.country,
        level: row && row.level,
      });
    }
  }

  function renderAboutSources() {
    const sources = [
      ["geoBoundaries (gbOpen / CGAZ)", "https://www.geoboundaries.org/",
       "CC BY 4.0 - boundaries at all three levels. A few countries inherit ODbL or CC-BY-SA from OpenStreetMap."],
      ["CIA World Factbook", "https://www.cia.gov/the-world-factbook/",
       "Public domain - country religion, language, ethnicity, median age, sex ratio. Retired February 2026; read through the factbook/factbook.json mirror."],
      ["Natural Earth", "https://www.naturalearthdata.com/",
       "Public domain (CC0) - code concordance and largest-settlement points."],
      ["Wikidata", "https://www.wikidata.org/",
       "CC0 - subnational population, capital and coordinates wherever that adapter has been run."],
      ["National statistical offices", "https://github.com/advaitsridhar/DemographicMap#data-sources",
       "US Census ACS, ONS/Nomis, Statistics Canada, IBGE SIDRA, Eurostat, ABS, Census of India - each under its own licence."],
    ];
    els.aboutSources.innerHTML = sources.map(([name, url, note]) =>
      `<li><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(name)}</a> - ${esc(note)}</li>`).join("");
  }

  window.addEventListener("error", (event) => {
    console.error(event.error || event.message);
    status("Something failed to load - see the browser console", true);
  });

  start().catch((err) => {
    console.error(err);
    els.sidebarBody.innerHTML =
      `<div class="empty-state"><h2>Could not start</h2><p>${esc(String(err))}</p></div>`;
  });
})();
