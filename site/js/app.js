/* Application wiring: map <-> data <-> sidebar <-> search <-> URL. */
(function () {
  "use strict";

  const { escape: esc, valueOf, number } = window.Fmt;

  const els = {
    app: document.getElementById("app"),
    filters: document.getElementById("filters"),
    filtersToggle: document.getElementById("filters-toggle"),
    filtersClose: document.getElementById("filters-close"),
    summary: document.getElementById("filter-summary"),
    metricOptions: document.getElementById("metric-options"),
    fieldSection: document.getElementById("field-section"),
    fieldOptions: document.getElementById("field-options"),
    groupSection: document.getElementById("group-section"),
    groupSearch: document.getElementById("group-search"),
    groupCount: document.getElementById("group-count"),
    groupList: document.getElementById("group-list"),
    detailOptions: document.getElementById("detail-options"),
    groupReach: document.getElementById("group-reach"),
    blankNote: document.getElementById("blank-note"),
    legend: document.getElementById("legend"),
    levelNote: document.getElementById("level-note"),
    miniLegend: document.getElementById("map-legend"),
    miniLegendBody: document.getElementById("map-legend-body"),
    miniSummary: document.getElementById("map-legend-summary"),
    miniNote: document.getElementById("map-legend-note"),
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
    // The group last chosen in each field. Switching from religion to language
    // and back used to land on whatever happened to sort first; remembering
    // costs one line and makes the field buttons safe to press.
    groupByField: {},
    groupIndex: null,      // site/data/groups.json, once it lands
    groupQuery: "",
    level: 0,
    panelOpen: true,
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

  /* --------------------------------------------------------- filter panel */

  /* Whether the panel starts open.
   *
   * Wide screens get it open: it is the map's legend and its caveats, and a
   * first-time reader who never presses the button would otherwise be looking
   * at coloured shapes with no key. Phones get it closed, because at that
   * width it covers the map it describes.
   */
  /* On a narrow screen the panel is a drawer over the map, and it has to start
   * below the topbar or it covers the button that opened it -- and the search
   * box beside it. The topbar's height depends on how its own contents wrap,
   * so it is measured rather than guessed.
   */
  function trackTopbarHeight() {
    const bar = document.getElementById("topbar");
    const set = () => document.documentElement.style.setProperty(
      "--topbar-h", `${Math.round(bar.getBoundingClientRect().height)}px`);
    set();
    if (window.ResizeObserver) new ResizeObserver(set).observe(bar);
    else window.addEventListener("resize", set);
  }

  function panelDefault() {
    try {
      const stored = localStorage.getItem("wdm-filters");
      if (stored) return stored === "open";
    } catch (err) { /* private mode: fall through to the width rule */ }
    return window.innerWidth > 900;
  }

  function setPanel(open) {
    state.panelOpen = open;
    els.filters.hidden = !open;
    els.app.classList.toggle("filters-open", open);
    els.filtersToggle.setAttribute("aria-expanded", String(open));
    els.filtersToggle.title = open ? "Hide the filter panel" : "Show the filter panel";
    // The legend follows the panel out to the map. Hiding the controls is a
    // request for more map, not for a map whose colours mean nothing.
    els.miniLegend.hidden = open;
    try {
      localStorage.setItem("wdm-filters", open ? "open" : "closed");
    } catch (err) { /* private mode: the choice just does not persist */ }
    const map = window.WorldMap.getMap();
    if (map) map.resize();
  }

  /* ------------------------------------------------------ choice controls */

  /* The four choice lists share one keyboard contract: a single tab stop,
   * arrows to move, and moving selects. That is the WAI-ARIA radio pattern,
   * and the group listbox follows it too -- a list that behaved differently
   * from the controls directly above it would be the more surprising choice.
   *
   * These replace four <select>s. A select hid what the options meant: "Colour
   * by" offered five words with no hint that two of them needed a group chosen
   * first, and the group picker welded field and group into one line
   * ("Religion: Christianity (201 countries)") that could not be read at a
   * glance or narrowed without a second control beside it.
   */
  function markChoice(host, value) {
    const items = host.querySelectorAll("[data-value]");
    let found = false;
    for (const item of items) {
      const on = item.dataset.value === value;
      item.setAttribute(
        item.getAttribute("role") === "option" ? "aria-selected" : "aria-checked",
        String(on));
      item.tabIndex = on ? 0 : -1;
      if (on) found = true;
    }
    // Something has to be reachable by Tab even when nothing is selected yet,
    // or the whole control drops out of the keyboard order.
    if (!found && items.length) items[0].tabIndex = 0;
  }

  function wireChoice(host, onPick) {
    host.addEventListener("click", (event) => {
      const item = event.target.closest("[data-value]");
      if (item && host.contains(item)) onPick(item.dataset.value);
    });
    host.addEventListener("keydown", (event) => {
      const items = Array.from(host.querySelectorAll("[data-value]"));
      if (!items.length) return;
      const at = items.indexOf(event.target.closest("[data-value]"));
      let next;
      switch (event.key) {
        case "ArrowDown": case "ArrowRight":
          next = at < 0 ? 0 : (at + 1) % items.length; break;
        case "ArrowUp": case "ArrowLeft":
          next = at < 0 ? items.length - 1 : (at - 1 + items.length) % items.length; break;
        case "Home": next = 0; break;
        case "End": next = items.length - 1; break;
        default: return;
      }
      event.preventDefault();
      items[next].focus();
      onPick(items[next].dataset.value);
    });
  }

  function optionHTML(role, cls, value, label, hint) {
    return `<button type="button" role="${role}" class="${cls}" data-value="${esc(value)}"
                    aria-${role === "option" ? "selected" : "checked"}="false" tabindex="-1">
              <span class="opt-name">${esc(label)}</span>` +
           (hint ? `<span class="opt-hint">${esc(hint)}</span>` : "") +
           `</button>`;
  }

  const DETAIL_LEVELS = [
    ["auto", "Follow zoom", "Countries, then first-level, then second-level as you zoom in."],
    ["0", "Countries", "One shade per country at every zoom."],
    ["1", "First-level divisions", "States, provinces, regions — wherever they are tiled."],
    ["2", "Second-level divisions", "Districts and counties. Pinning this loads every country's shard."],
  ];

  function buildControls() {
    els.metricOptions.innerHTML = Object.entries(window.Metrics.METRICS)
      .map(([key, metric]) => optionHTML("radio", "opt", key, metric.label, metric.hint))
      .join("");
    wireChoice(els.metricOptions, (value) => {
      state.metric = value;
      markChoice(els.metricOptions, value);
      syncSections();
      refreshColors();
    });
    markChoice(els.metricOptions, state.metric);

    els.fieldOptions.innerHTML = window.Metrics.FIELDS
      .map((field) => `<button type="button" role="radio" class="seg" data-value="${esc(field.key)}"
                               aria-checked="false" tabindex="-1">${esc(field.label)}</button>`)
      .join("");
    wireChoice(els.fieldOptions, (value) => {
      if (value !== state.field) {
        state.groupByField[state.field] = state.group;
        state.field = value;
        state.group = state.groupByField[value] || null;
        state.groupQuery = "";
        els.groupSearch.value = "";
      }
      markChoice(els.fieldOptions, state.field);
      syncSections();
      refreshColors();
    });
    markChoice(els.fieldOptions, state.field);

    els.detailOptions.innerHTML = DETAIL_LEVELS
      .map(([value, label, hint]) => optionHTML("radio", "opt", value, label, hint)).join("");
    wireChoice(els.detailOptions, (value) => {
      markChoice(els.detailOptions, value);
      window.WorldMap.setPinnedLevel(value === "auto" ? null : Number(value));
    });
    markChoice(els.detailOptions, "auto");

    els.groupSearch.addEventListener("input", () => {
      state.groupQuery = els.groupSearch.value.trim();
      // No repaint: the selected group survives a search that excludes it (see
      // renderGroupList), so nothing on the map can have changed.
      renderGroupList();
    });
    els.groupSearch.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowDown") return;
      const first = els.groupList.querySelector("[data-value]");
      if (!first) return;
      event.preventDefault();
      first.focus();
    });

    wireChoice(els.groupList, (value) => {
      state.group = value || null;
      state.groupByField[state.field] = state.group;
      markChoice(els.groupList, state.group);
      describeReach();
      renderSummary();
      refreshColors();
    });

    // On a phone the drawer covers the map, so choosing a group there and being
    // left staring at the list is the wrong end of the interaction. Click only:
    // arrowing through the list must not slam the drawer shut mid-browse.
    els.groupList.addEventListener("click", (event) => {
      if (!event.target.closest("[data-value]")) return;
      if (window.innerWidth <= 900) setPanel(false);
    });

    els.filtersToggle.addEventListener("click", () => setPanel(!state.panelOpen));
    els.filtersClose.addEventListener("click", () => {
      setPanel(false);
      els.filtersToggle.focus();
    });
    els.filters.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      setPanel(false);
      els.filtersToggle.focus();
    });

    setPanel(panelDefault());
    syncSections();
  }

  /* Which sections apply to the metric on screen.
   *
   * Population needs no field and no group; coverage needs a field but no
   * group; only "share of one group" needs both. The old panel showed a
   * "Group" row for all of them and quietly changed its label, which meant the
   * same control did two different jobs depending on a setting three rows up.
   */
  function syncSections() {
    const metric = window.Metrics.METRICS[state.metric];
    els.fieldSection.hidden = !metric.needsField;
    els.groupSection.hidden = !metric.needsGroup;
    if (metric.needsGroup) {
      renderGroupList();
    } else {
      describeReach();
      renderSummary();
    }
  }

  function fieldLabel() {
    const field = window.Metrics.FIELDS.find((f) => f.key === state.field);
    return field ? field.label : state.field;
  }

  function currentRecords() {
    const wanted = ["admin0", "admin1", "admin2"][window.WorldMap.getLevel()];
    const out = [];
    for (const record of window.DataStore.all().values()) {
      if (record.level === wanted) out.push(record);
    }
    return out;
  }

  /* --------------------------------------------------------- the group list */

  // Enough that scrolling is the normal way to browse, few enough that a field
  // with 793 ethnicity groups does not build 793 nodes on every keystroke.
  const GROUP_LIMIT = 150;

  /* The groups on offer, drawn from the worldwide index rather than from
   * whatever is on screen.
   *
   * The list used to come from the loaded records, which made the filter local
   * without saying so: at world zoom it offered only groups that appear in
   * country-level records, and inside one country only that country's own
   * spellings. Asking for Islam while looking at Sri Lanka offered "Islam";
   * the same question over India offered "Muslim"; neither said the other
   * existed. The index is built over every record, so one entry stands for
   * both and the map answers for every country that reports it.
   */
  function sortedGroups() {
    const entry = state.groupIndex && state.groupIndex[state.field];
    const all = (entry && entry.groups) || [];
    const query = state.groupQuery.toLowerCase();
    // Matched against the labels a census actually used as well as the
    // canonical name, so typing "Muslim" finds Islam rather than nothing.
    const matched = query
      ? all.filter((g) => [g.name, ...(g.labels || [])].join(" ").toLowerCase().includes(query))
      : all.slice();
    /* Reach first, and residuals last whatever their reach.
     *
     * The index is ordered by unit count, which is the wrong first answer for
     * a worldwide filter: "Unaffiliated or not reported" is 3,130 US counties
     * in one country, and it outranked Islam's 124 countries. How many
     * countries report a group is what makes it comparable across a border, so
     * that is the sort.
     */
    matched.sort((a, b) =>
      ((a.residual ? 1 : 0) - (b.residual ? 1 : 0)) ||
      (b.countries.length - a.countries.length) ||
      (b.units - a.units) ||
      a.name.localeCompare(b.name));
    return matched;
  }

  function groupOptionHTML(group) {
    const countries = group.countries.length;
    const areas = `${number(group.units)} area${group.units === 1 ? "" : "s"}`;
    const reach = countries === 1 ? `1 country · ${areas}`
                                  : `${number(countries)} countries · ${areas}`;
    // The source labels folded into this one entry, so the reader can see that
    // choosing "Christianity" also answers for the census that said "Catholic".
    const labels = group.labels || [];
    const folded = labels.length > 1
      ? `<span class="g-labels">${esc(labels.slice(0, 4).join(", "))}` +
        (labels.length > 4 ? ` +${labels.length - 4} more` : "") + `</span>`
      : "";
    return `<button type="button" role="option" class="g-opt" data-value="${esc(group.name)}"
                    aria-selected="false" tabindex="-1">
              <span class="g-name">${esc(group.name)}</span>
              <span class="g-reach">${esc(reach)}</span>${folded}
            </button>`;
  }

  const RESIDUAL_HEAD =
    `<p class="group-divider"><strong>Residual answers</strong>
       <span>“Other” and “not stated” are the absence of an answer, not a group
             anyone belongs to. They are here because leaving them out would hide
             people, and last because nobody is looking for them.</span></p>`;

  function renderGroupList() {
    if (!state.groupIndex) {
      els.groupList.innerHTML = `<p class="group-empty">Loading the worldwide group list…</p>`;
      els.groupCount.textContent = "";
      renderSummary();
      return;
    }
    const matched = sortedGroups();
    const shown = matched.slice(0, GROUP_LIMIT);
    // Whatever is selected stays in the list even when the search excludes it:
    // dropping it would colour the map by something the picker denied was
    // selected. It goes at the foot under its own heading rather than at the
    // top -- typing "Muslim" and being shown Christianity first, because that
    // was the last choice, reads as a search that does not work.
    let stray = null;
    if (state.group && !shown.some((g) => g.name === state.group)) {
      const entry = state.groupIndex[state.field] || {};
      stray = (entry.groups || []).find((g) => g.name === state.group) || null;
    }

    if (!shown.length && !stray) {
      els.groupList.innerHTML =
        `<p class="group-empty">No ${esc(fieldLabel().toLowerCase())} group matches ` +
        `“${esc(state.groupQuery)}”. Try a census's own word — “Muslim”, “te reo”, “Pardo”.</p>`;
      els.groupCount.textContent = "0 groups";
      renderSummary();
      return;
    }
    // A search that matches nothing still has to show what is on the map.
    if (!shown.length) {
      els.groupList.innerHTML = groupOptionHTML(stray);
      els.groupCount.textContent =
        `Nothing matches “${state.groupQuery}”. Still on the map: ${state.group}.`;
      markChoice(els.groupList, state.group);
      describeReach();
      renderSummary();
      return;
    }

    const html = [];
    let residualOpen = false;
    for (const group of shown) {
      if (group.residual && !residualOpen) {
        residualOpen = true;
        html.push(`<div role="group" aria-label="Residual answers: other, and not stated">` +
                  RESIDUAL_HEAD);
      }
      html.push(groupOptionHTML(group));
    }
    if (residualOpen) html.push("</div>");
    if (stray) {
      html.push(`<div role="group" aria-label="Still on the map">` +
                `<p class="group-divider"><strong>Still on the map</strong>` +
                `<span>Outside the search above, and shading the map until you ` +
                `pick something else.</span></p>` +
                groupOptionHTML(stray) + `</div>`);
    }
    els.groupList.innerHTML = html.join("");

    els.groupCount.textContent = shown.length < matched.length
      ? `Showing the ${number(shown.length)} most widely reported of ` +
        `${number(matched.length)} — search to narrow.`
      : `${number(matched.length)} group${matched.length === 1 ? "" : "s"}` +
        (state.groupQuery
          ? `${matched.length === 1 ? " matches" : " match"} “${state.groupQuery}”.`
          : ", most widely reported first.");

    // Nothing chosen yet, or the field just changed: take the widest-reported
    // real group rather than leaving the map uncoloured with a full list beside
    // it. Never a residual -- "Other religions" is not an opening answer.
    if (!stray && (!state.group || !shown.some((g) => g.name === state.group))) {
      state.group = (shown.find((g) => !g.residual) || shown[0]).name;
      state.groupByField[state.field] = state.group;
    }
    markChoice(els.groupList, state.group);
    describeReach();
    renderSummary();
  }

  /* --------------------------------------------------------- what is shown */

  /* One line naming the current filter, in the panel and again on the map.
   *
   * It is repeated outside the panel on purpose: the panel can be hidden, and
   * a map shaded by "the Sikhism share of religion, second-level divisions
   * only" says nothing without that line.
   */
  function renderSummary() {
    const metric = window.Metrics.METRICS[state.metric];
    const chips = [{ text: metric.label }];
    if (metric.needsField) chips.push({ text: fieldLabel() });
    if (metric.needsGroup && state.group) chips.push({ text: state.group, key: true });
    const pinned = window.WorldMap.getPinnedLevel();
    chips.push({
      text: pinned === null ? "Detail follows zoom"
        : ["Countries only", "First-level only", "Second-level only"][pinned],
    });
    const html = chips.map((chip) =>
      `<span class="fchip${chip.key ? " fchip-key" : ""}">${esc(chip.text)}</span>`).join("");
    els.summary.innerHTML = html;
    els.miniSummary.innerHTML = html;

    const blank = metric.blank || "";
    els.blankNote.textContent = blank;
    els.blankNote.hidden = !blank;
    els.miniNote.textContent = blank;
    els.miniNote.hidden = !blank;
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
  function describeReach() {
    const metric = window.Metrics.METRICS[state.metric];
    if (!metric.needsGroup || !state.group || !state.groupIndex) {
      els.groupReach.hidden = true;
      return;
    }
    const entry = state.groupIndex[state.field];
    const group = entry && (entry.groups || []).find((g) => g.name === state.group);
    if (!group) { els.groupReach.hidden = true; return; }

    // Counted for the level on screen, not for the dataset as a whole. Islam is
    // reported by 124 countries nationally and by five at second level, so a
    // map pinned to districts that claims 124 tells the reader the opposite of
    // what it is showing -- most of the world grey.
    const levelName = ["admin0", "admin1", "admin2"][window.WorldMap.getLevel()];
    const here = (group.levels || {})[levelName];
    const shown = ["countries", "first-level divisions", "second-level divisions"]
      [window.WorldMap.getLevel()];
    const parts = [];
    if (!here || !here.units) {
      // Saying only that it is missing here leaves the reader stuck in front of
      // a blank map. Jainism has no country-level figure but 731 Indian
      // districts, and the fix is one control away.
      const elsewhere = [];
      for (const [name, label] of [["admin1", "first-level divisions"],
                                   ["admin2", "second-level divisions"]]) {
        const at = (group.levels || {})[name];
        if (at && at.units) elsewhere.push(`${number(at.units)} ${label}`);
      }
      parts.push(`No ${shown} carry this figure.` +
                 (elsewhere.length
                   ? ` It is reported for ${elsewhere.join(" and ")} — change Detail level ` +
                     `to see them.`
                   : "") +
                 ` The map is blank here because the figure is missing at this ` +
                 `level, not because the share is zero.`);
    } else {
      // At country level the unit *is* the country, so "124 countries across 124
      // countries" would be the same fact said twice.
      const where = window.WorldMap.getLevel() === 0
        ? `${number(here.units)} countries`
        : `${number(here.units)} ${shown} across ${here.countries.length} ` +
          `${here.countries.length === 1 ? "country" : "countries"}`;
      parts.push(`At this level: ${where}. Everything else is blank because the ` +
                 `figure is missing, not zero.`);
      if (here.countries.length < group.countries.length) {
        parts.push(`${group.countries.length} countries report it nationally.`);
      }
    }
    // Which source labels were folded into this one name. Christianity carries
    // eighty of them, so past a handful the list goes behind a disclosure --
    // hidden it would be a claim the reader cannot check, and inline it would
    // bury the sentence above that says what the map is showing.
    const labels = group.labels || [];
    let folded = "";
    if (labels.length > 6) {
      folded = `<details class="reach-labels"><summary>Combines ${number(labels.length)} ` +
               `source labels</summary>${esc(labels.join(", "))}</details>`;
    } else if (labels.length > 1) {
      parts.push(`Combines: ${labels.join(", ")}.`);
    }
    // Only the sub-national records carry a basis: the US county and state
    // figures count adherents reported by religious bodies, while the country
    // row beside them is the Factbook's self-identification. Saying "the USA
    // measures this as adherents" would be wrong about the country shape the
    // reader is looking at, so the sentence names the level it applies to.
    for (const [iso, basis] of Object.entries((entry && entry.bases) || {})) {
      if (!group.countries.includes(iso)) continue;
      const record = window.DataStore.country(iso);
      parts.push(`Within ${record ? record.name : iso}, state and county figures ` +
                 `count ${basis} reported by religious bodies rather than answers ` +
                 `people gave, so they are not on the same footing as the rest.`);
    }
    els.groupReach.innerHTML = esc(parts.join(" ")) + folded;
    els.groupReach.hidden = false;
  }

  /* Shade the map by one group, from wherever the request came from.
   *
   * The search box and the panel are two doors into the same state, so this
   * drives the panel rather than bypassing it -- otherwise picking "Islam" from
   * the search would colour the map while the controls underneath still read
   * whatever was there before.
   */
  function applyGroupFilter(field, group) {
    state.metric = "group_share";
    state.field = field;
    state.group = group;
    state.groupByField[field] = group;
    // Clear any leftover search text so the chosen group is in the list it is
    // about to be selected from.
    state.groupQuery = "";
    els.groupSearch.value = "";
    markChoice(els.metricOptions, state.metric);
    markChoice(els.fieldOptions, state.field);
    syncSections();
    // Open the panel, so the map's new colouring has its explanation beside it
    // rather than behind a button. Not on a phone, where the panel covers the
    // map it would be explaining.
    if (!state.panelOpen && window.innerWidth > 900) setPanel(true);
    const chosen = els.groupList.querySelector('[aria-selected="true"]');
    if (chosen) chosen.scrollIntoView({ block: "nearest" });
    refreshColors();
  }

  /* -------------------------------------------------------------- legend */

  // Written to both the panel and the on-map copy: only one of them is visible
  // at a time, and which one depends on a button the reader may press at any
  // moment.
  function renderLegend(legend) {
    let html;
    if (!legend || legend.type === "empty") {
      html = `<p class="control-note">No values at this level yet.</p>`;
    } else if (legend.type === "status") {
      html = legend.items.map((item) =>
        `<div class="legend-item">
           <span class="legend-icon" style="color:${item.color}" aria-hidden="true">${item.icon}</span>
           <span class="legend-swatch" style="background:${item.color}"></span>
           <span>${esc(item.label)}</span>
         </div>`).join("");
    } else {
      html =
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
    els.legend.innerHTML = html;
    els.miniLegendBody.innerHTML = html;
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
    await window.DataStore.ensureLoaded(wanted, level);
    // The group list is built from the worldwide index, not from the records
    // that happen to be loaded, so arriving shards do not rebuild it -- doing
    // that used to discard the reader's chosen group mid-pan.
    refreshColors();
    status(null);
  }

  /* -------------------------------------------------------------- startup */

  async function start() {
    applyTheme(currentTheme());
    trackTopbarHeight();
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
      window.Search.setGroups(index);
      syncSections();
      refreshColors();
    }).catch(() => { /* picker stays label-local; the map still works */ });

    window.WorldMap.init({
      onReady: () => refreshColors(),
      onLevelChange: (level) => {
        state.level = level;
        // Both of these are level-specific: the reach sentence counts units at
        // the level on screen, and the summary says which level that is.
        describeReach();
        renderSummary();
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
        if (row.kind === "group") { applyGroupFilter(row.field, row.name); return; }
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
