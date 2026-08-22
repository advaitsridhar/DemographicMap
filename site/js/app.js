/* Application wiring: map <-> data <-> sidebar <-> search <-> URL. */
(function () {
  "use strict";

  const { escape: esc, valueOf, number } = window.Fmt;

  const els = {
    metric: document.getElementById("metric-select"),
    groupRow: document.getElementById("group-row"),
    group: document.getElementById("group-select"),
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

  function populateGroupSelect() {
    const metric = window.Metrics.METRICS[state.metric];
    const records = currentRecords();
    const options = [];
    for (const field of window.Metrics.FIELDS) {
      if (!metric.needsGroup) {
        options.push({ value: groupValue(field.key, null), label: field.label });
        continue;
      }
      for (const group of window.Metrics.topGroups(records, field.key, 24)) {
        options.push({ value: groupValue(field.key, group), label: field.label + ": " + group });
      }
    }
    if (!options.length) {
      els.group.innerHTML = `<option value="${esc(groupValue(state.field, null))}">No groups loaded yet</option>`;
      return;
    }
    els.group.innerHTML = options
      .map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("");
    const wanted = groupValue(state.field, state.group);
    els.group.value = options.some((o) => o.value === wanted) ? wanted : options[0].value;
    const parsed = splitGroupValue(els.group.value);
    state.field = parsed.field;
    state.group = parsed.group;
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

  async function onViewChange(level, countries) {
    if (level === 0) { refreshColors(); return; }
    const changed = await window.DataStore.ensureLoaded(countries.slice(0, 40), level);
    if (changed && window.Metrics.METRICS[state.metric].needsGroup) populateGroupSelect();
    refreshColors();
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

    status("Loading country data", true);
    await window.DataStore.loadCountries();
    status(null);

    window.WorldMap.init({
      onReady: () => refreshColors(),
      onLevelChange: (level) => {
        state.level = level;
        if (window.Metrics.METRICS[state.metric].needsGroup) populateGroupSelect();
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
