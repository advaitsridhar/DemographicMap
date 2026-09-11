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
    depthSection: document.getElementById("depth-section"),
    spreadSection: document.getElementById("spread-section"),
    spreadOptions: document.getElementById("spread-options"),
    depthOptions: document.getElementById("depth-options"),
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
    // How finely the "most populous group" map reads a composition: the top
    // of each tree, or the finest canonical name a source wrote.
    depth: "2",
    // Whether the shading runs over the whole 25-100% range or over the range
    // actually on screen. Absolute by default, because a shade that means the
    // same thing everywhere is the more honest starting point.
    spread: "absolute",
    // Which parents the group tree is showing the children of. Expanding is
    // per field, because the fields are three different trees.
    openBranches: {},
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

  /* ---------------------------------------------------------- info bubbles */

  /* The long caveats, moved off the page and behind an "i".
   *
   * Every one of these was a paragraph sitting permanently under the control
   * it described. They are all true and worth saying once, and none of them is
   * worth the four lines of panel it took to say on every visit -- the effect
   * was a filter panel that read as a document, where the controls were the
   * things between the prose. Behind a bubble they are one keystroke or one
   * hover away, next to the thing they are about, and the panel is a panel.
   *
   * Hover opens it and so does focus, because hover alone is unreachable by
   * keyboard and unusable on a touchscreen; click pins it open so a reader can
   * select the text.
   */
  const INFO = {
    topic:
      "Religion, language and ethnicity are three separate census questions, " +
      "and the ethnicity one is not the same question everywhere: US race, " +
      "Brazilian cor ou raça, UK ethnic group, Australian ancestry and " +
      "Chinese minzu have different answer sets. Categories are comparable " +
      "within a country and often not across a border.",
    depth:
      "Three widths of the same rows. The widest is the broadest grouping " +
      "this map is willing to make and the one that means the same thing in " +
      "every country: Abrahamic religions, Indo-European languages, African " +
      "ancestry. The middle is the family — Christianity, Germanic, Bantu " +
      "peoples. As reported is each census's own words, which is the most " +
      "detail and the least comparable across a border.",
    spread:
      "The full range always means the same thing, so two places can be " +
      "compared anywhere on the map — but zoom into a region where every " +
      "district is 85 to 95 per cent one group and it is all one flat " +
      "colour. Fit to view stretches the ramp over the range actually on " +
      "screen, which shows that variation at the cost of the shade meaning " +
      "something different from one view to the next. The legend always " +
      "names the two ends, so you can see which you are looking at.",
    group:
      "Picking a family counts every group inside it, so Christianity finds " +
      "the censuses that only ever say Roman Catholic. Open a family to pick " +
      "one of its parts instead. Blank on the map means the figure is " +
      "missing at that level, never that the share is zero.",
  };

  let infoOpen = null;

  function closeInfo() {
    if (!infoOpen) return;
    infoOpen.button.setAttribute("aria-expanded", "false");
    infoOpen.bubble.remove();
    infoOpen = null;
  }

  function openInfo(button, pinned) {
    // Either a key into the table above, for the fixed controls, or the text
    // itself, for the notes the sidebar builds per record.
    const text = button.dataset.infoText || INFO[button.dataset.info];
    if (!text) return;
    if (infoOpen && infoOpen.button === button) {
      if (pinned) infoOpen.pinned = true;
      return;
    }
    closeInfo();
    const bubble = document.createElement("div");
    bubble.className = "info-bubble";
    bubble.setAttribute("role", "note");
    bubble.textContent = text;
    document.body.appendChild(bubble);
    const box = button.getBoundingClientRect();
    // Placed below the button and nudged back inside the viewport rather than
    // anchored to the panel: at phone width the panel is narrower than the
    // bubble needs to be.
    bubble.style.top = `${Math.round(box.bottom + 6)}px`;
    const width = bubble.getBoundingClientRect().width;
    const left = Math.min(Math.max(8, box.left - 8),
                          window.innerWidth - width - 8);
    bubble.style.left = `${Math.round(left)}px`;
    button.setAttribute("aria-expanded", "true");
    infoOpen = { button, bubble, pinned: Boolean(pinned) };
  }

  /* Delegated rather than bound per button, because most of these buttons do
   * not exist yet: the sidebar rebuilds its panels on every selection, and a
   * listener attached at startup would only ever cover the filter panel. */
  function wireInfo() {
    const at = (event) => event.target.closest("[data-info], [data-info-text]");
    document.addEventListener("mouseover", (event) => {
      const button = at(event);
      if (button) openInfo(button, false);
      else if (infoOpen && !infoOpen.pinned) closeInfo();
    });
    document.addEventListener("focusin", (event) => {
      const button = at(event);
      if (button) openInfo(button, false);
      else if (infoOpen && !infoOpen.pinned) closeInfo();
    });
    document.addEventListener("click", (event) => {
      const button = at(event);
      if (!button) return;
      event.preventDefault();
      if (infoOpen && infoOpen.button === button && infoOpen.pinned) closeInfo();
      else openInfo(button, true);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeInfo();
    });
    document.addEventListener("click", (event) => {
      if (infoOpen && !event.target.closest("[data-info]")) closeInfo();
    });
    window.addEventListener("scroll", closeInfo, true);
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

  /* How finely the most-populous-group map reads a composition.
   *
   * Two settings rather than a slider down the tree, because the tree is only
   * two or three deep and the two ends are the two questions people ask.
   * Families is the comparable one: Christianity against Islam against
   * Hinduism, the same distinction in every country. As reported is the
   * interesting one: it splits Catholic from Protestant from Orthodox
   * wherever a census bothered to, which is what makes Europe look like
   * itself rather than like one blue sheet.
   */
  /* How wide a grouping the most-populous-group map reads.
   *
   * Three tiers, the same three in every topic, because the tree is three
   * deep everywhere: the broadest grouping the project is willing to make,
   * the family, and the words a census actually used. The labels change with
   * the topic because the same tier is a different kind of thing in each --
   * tier 1 of religion is a tradition, of language a family, of ethnicity an
   * ancestry -- and a control that said "Tier 1" would be asking the reader
   * to hold the abstraction rather than the question.
   */
  const DEPTH_LABELS = {
    religion: ["Traditions", "Religions", "As reported"],
    language: ["Families", "Branches", "As reported"],
    ethnicity: ["Ancestry", "Peoples", "As reported"],
  };

  function depths() {
    const names = DEPTH_LABELS[state.field] || DEPTH_LABELS.religion;
    return names.map((label, i) => [String(i + 1), label]);
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
      renderDepths();
      syncSections();
      refreshColors();
    });
    markChoice(els.fieldOptions, state.field);

    els.spreadOptions.innerHTML = [["absolute", "Full range"], ["fit", "Fit to view"]]
      .map(([value, label]) => `<button type="button" role="radio" class="seg" data-value="${esc(value)}"
                               aria-checked="false" tabindex="-1">${esc(label)}</button>`)
      .join("");
    markChoice(els.spreadOptions, state.spread);
    wireChoice(els.spreadOptions, (value) => {
      state.spread = value;
      markChoice(els.spreadOptions, value);
      refreshColors();
    });

    renderDepths();
    wireChoice(els.depthOptions, (value) => {
      state.depth = value;
      markChoice(els.depthOptions, value);
      renderSummary();
      refreshColors();
    });

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

    // Opening a branch is not choosing it, so the twist is handled before the
    // choice wiring gets a look at the click.
    els.groupList.addEventListener("click", (event) => {
      const twist = event.target.closest("[data-branch]");
      if (!twist || !els.groupList.contains(twist)) return;
      event.stopPropagation();
      const open = state.openBranches[state.field] || (state.openBranches[state.field] = {});
      open[twist.dataset.branch] = !open[twist.dataset.branch];
      renderGroupList();
      // Keep the keyboard where it was: the row is redrawn, so the old node
      // is gone and focus would otherwise fall back to the document.
      const again = els.groupList.querySelector(
        `[data-branch="${CSS.escape(twist.dataset.branch)}"]`);
      if (again) again.focus();
    }, true);

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

    wireInfo();
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
    els.depthSection.hidden = !metric.needsDepth;
    // The shading choice belongs to the two maps that draw a share: the
    // most-populous-group map and a single group's share.
    els.spreadSection.hidden = !(metric.kind === "group" || metric.needsGroup);
    els.groupSection.hidden = !metric.needsGroup;
    if (metric.needsGroup) {
      renderGroupList();
    } else {
      describeReach();
      renderSummary();
    }
  }

  function renderDepths() {
    els.depthOptions.innerHTML = depths()
      .map(([value, label]) => `<button type="button" role="radio" class="seg" data-value="${esc(value)}"
                               aria-checked="false" tabindex="-1">${esc(label)}</button>`)
      .join("");
    markChoice(els.depthOptions, state.depth);
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
   *
   * It is a tree rather than a list because the flat version could not ask the
   * question a reader actually has. Ethnicity alone carried 1,808 entries in
   * one scroll, and the traditions inside Christianity -- 6,144 records saying
   * "Roman Catholic" -- were not in it at all, having been folded out of sight
   * into their family. Now the families are the top level and open to show
   * what is inside them, and picking either level works: a parent shades every
   * unit that reports any of its children.
   */
  function groupsOf(field) {
    const entry = state.groupIndex && state.groupIndex[field];
    return (entry && entry.groups) || [];
  }

  function groupByName(field, name) {
    return groupsOf(field).find((g) => g.name === name) || null;
  }

  /* Reach first, and residuals last whatever their reach.
   *
   * The index is ordered by unit count, which is the wrong first answer for
   * a worldwide filter: "Unaffiliated or not reported" is 3,130 US counties
   * in one country, and it outranked Islam's 124 countries. How many
   * countries report a group is what makes it comparable across a border, so
   * that is the sort.
   */
  function byReach(a, b) {
    return ((a.residual ? 1 : 0) - (b.residual ? 1 : 0)) ||
           (b.countries.length - a.countries.length) ||
           (b.units - a.units) ||
           a.name.localeCompare(b.name);
  }

  function matchesQuery(group, query) {
    return [group.name, ...(group.labels || [])].join(" ").toLowerCase()
      .includes(query);
  }

  /* The rows to draw, in order, each with its depth.
   *
   * With no search this is the tree: every top-level family, and the children
   * of whichever branches are open. With a search it is a flat list of hits,
   * each carrying the family it belongs to so "Catholicism" does not arrive
   * unexplained -- typing "catholic" should show where the answer sits, not
   * just that it exists.
   */
  function visibleRows() {
    const all = groupsOf(state.field);
    const query = state.groupQuery.toLowerCase();
    if (query) {
      return all.filter((g) => matchesQuery(g, query)).sort(byReach)
                .slice(0, GROUP_LIMIT)
                .map((g) => ({ group: g, depth: 0, flat: true }));
    }
    const open = state.openBranches[state.field] || {};
    const rows = [];
    const walk = (parents, depth) => {
      for (const group of parents.sort(byReach)) {
        rows.push({ group, depth });
        const kids = (group.children || [])
          .map((name) => groupByName(state.field, name))
          .filter(Boolean);
        if (kids.length && open[group.name]) walk(kids, depth + 1);
      }
    };
    walk(all.filter((g) => !g.parent), 0);
    return rows.slice(0, GROUP_LIMIT);
  }

  function groupRowHTML(row) {
    const group = row.group;
    const countries = group.countries.length;
    const areas = `${number(group.units)} area${group.units === 1 ? "" : "s"}`;
    const reach = countries === 1 ? `1 country · ${areas}`
                                  : `${number(countries)} countries · ${areas}`;
    const kids = (group.children || []).length;
    const open = (state.openBranches[state.field] || {})[group.name];
    // The twist is a button of its own, beside the row rather than inside it:
    // opening a branch and choosing it are two different intentions, and a
    // reader who wants Christianity whole must not have to avoid the arrow.
    const twist = kids && !row.flat
      ? `<button type="button" class="g-twist" data-branch="${esc(group.name)}"
                 aria-expanded="${open ? "true" : "false"}"
                 aria-label="${open ? "Hide" : "Show"} the ${kids} groups inside ${esc(group.name)}"
                 tabindex="-1">${open ? "▾" : "▸"}</button>`
      : `<span class="g-twist g-twist-empty" aria-hidden="true"></span>`;
    // Where a search flattened the tree, the family says what the hit is part
    // of. A bare "Sunni Islam" in a list of religions is fine; a bare
    // "Cushitic languages" is not.
    const family = row.flat && group.parent
      ? `<span class="g-parent">in ${esc(group.parent)}</span>` : "";
    // An unplaced group keeps the reserved colour here too, and says why on
    // hover. A grey dot in a list of coloured ones reads as "nothing here";
    // these entries are the opposite -- a real group whose family is the one
    // thing not yet known.
    const swatch = group.hue
      ? `<span class="g-swatch" style="background:${esc(group.hue)}" aria-hidden="true"></span>`
      : `<span class="g-swatch g-swatch-none" title="Not yet placed in the classification"
               style="background:${window.Palette.unplaced()}" aria-hidden="true"></span>`;
    return `<div class="g-row" style="--g-depth:${row.depth}">${twist}
      <button type="button" role="treeitem" class="g-opt" data-value="${esc(group.name)}"
              aria-selected="false" tabindex="-1">
        ${swatch}<span class="g-name">${esc(group.name)}</span>
        <span class="g-reach">${esc(reach)}</span>${family}
      </button></div>`;
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
    const rows = visibleRows();
    // Whatever is selected stays reachable even when the search excludes it:
    // dropping it would colour the map by something the picker denied was
    // selected. It goes at the foot under its own heading rather than at the
    // top -- typing "Muslim" and being shown Christianity first, because that
    // was the last choice, reads as a search that does not work.
    let stray = null;
    if (state.group && !rows.some((r) => r.group.name === state.group)) {
      stray = groupByName(state.field, state.group);
    }

    if (!rows.length && !stray) {
      els.groupList.innerHTML =
        `<p class="group-empty">No ${esc(fieldLabel().toLowerCase())} group matches ` +
        `“${esc(state.groupQuery)}”. Try a census's own word — “Muslim”, “te reo”, “Pardo”.</p>`;
      els.groupCount.textContent = "0 groups";
      renderSummary();
      return;
    }

    const html = [];
    let residualOpen = false;
    for (const row of rows) {
      if (row.group.residual && !row.depth && !residualOpen) {
        residualOpen = true;
        html.push(`<div role="group" aria-label="Residual answers: other, and not stated">` +
                  RESIDUAL_HEAD);
      }
      html.push(groupRowHTML(row));
    }
    if (residualOpen) html.push("</div>");
    if (stray) {
      html.push(`<div role="group" aria-label="Still on the map">` +
                `<p class="group-divider"><strong>Still on the map</strong>` +
                `<span>Outside the list above, and shading the map until you ` +
                `pick something else.</span></p>` +
                groupRowHTML({ group: stray, depth: 0, flat: true }) + `</div>`);
    }
    els.groupList.innerHTML = html.join("");

    const total = state.groupQuery
      ? groupsOf(state.field).filter((g) => matchesQuery(g, state.groupQuery.toLowerCase())).length
      : groupsOf(state.field).length;
    // Counted as "families that have anything inside them" rather than as
    // top-level entries: most top-level entries are a single group nobody
    // else reports, and saying "208 families" of those reads as a promise of
    // structure that is not there.
    const branching = groupsOf(state.field).filter((g) => (g.children || []).length).length;
    els.groupCount.textContent = state.groupQuery
      ? `${number(rows.length)} of ${number(total)} match “${state.groupQuery}”.`
      : `${number(total)} groups, widest reach first. ` +
        `${number(branching)} of them open to show what is inside.`;

    // Nothing chosen yet, or the field just changed: take the widest-reported
    // real group rather than leaving the map uncoloured with a full list beside
    // it. Never a residual -- "Other religions" is not an opening answer.
    if (!stray && (!state.group || !rows.some((r) => r.group.name === state.group))) {
      const first = rows.find((r) => !r.group.residual) || rows[0];
      state.group = first.group.name;
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
    if (metric.needsDepth) {
      const depth = depths().find((d) => d[0] === state.depth);
      if (depth) chips.push({ text: depth[1] });
    }
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

  // What a census or survey does by asking, which is nearly every figure on
  // this map. A basis equal to this is not worth a sentence.
  const ORDINARY_BASIS = "self-identification";

  // Bases that need more than their own name to be understood. Anything not
  // listed still gets a sentence, in the basis's own words.
  const BASIS_WORDS = {
    adherents: "count adherents reported by religious bodies rather than " +
               "answers people gave",
  };

  /* What the current filter actually covers, said out loud.
   *
   * A worldwide filter invites a worldwide reading, and most of these groups
   * are not reported worldwide. A map of Sikhism shaded in six countries and
   * blank everywhere else means "six countries publish this", not "nobody else
   * has any" -- and where a country measured it a different way, counting
   * adherents on religious bodies' rolls rather than answers people gave,
   * comparing its shade with its neighbours' is comparing two questions.
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
    // A basis says what a figure counts, and is worth a sentence only when it
    // is not the thing every other figure on the map already counts. A census
    // or survey asks people what they are, so "self-identification" is the
    // ordinary case and naming it would tell a reader nothing.
    //
    // This sentence was written for the other kind and hard-coded it: the 2020
    // Religion Census counted adherents reported by religious bodies, so the
    // American figures were not on the same footing as the rest and the panel
    // said so. PRRI's survey has since replaced those figures, and the
    // sentence went on interpolating the new basis into the old wording --
    // telling readers that self-identification was "reported by religious
    // bodies rather than answers people gave", which is the opposite of what
    // a survey is. The words now come from the basis rather than from the
    // source that happened to be there when they were written.
    for (const [iso, basis] of Object.entries((entry && entry.bases) || {})) {
      if (basis === ORDINARY_BASIS || !group.countries.includes(iso)) continue;
      const record = window.DataStore.country(iso);
      const said = BASIS_WORDS[basis] ||
                   `count ${basis} rather than answers people gave`;
      // Named down to the level it applies to: the country shape beside these
      // need not be measured the same way, and "the USA counts adherents"
      // would be wrong about the shape the reader is actually looking at.
      parts.push(`Within ${record ? record.name : iso}, the figures below the ` +
                 `country ${said}, so they are not on the same footing as the ` +
                 `rest.`);
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
    } else if (legend.type === "group") {
      /* A colour per group, in the order they lead the most units, with one
       * shared ramp underneath explaining the shade.
       *
       * Capped at twelve entries and a "+N more" line rather than scrolled:
       * the tail of a group legend is groups that lead one district each, and
       * a reader who needs those is reading the map, not the key. Every unit
       * names its own group on hover, so nothing is unreachable.
       */
      const items = legend.items.slice(0, legend.shown);
      const rest = legend.items.length - items.length;
      html =
        `<ul class="legend-groups">` + items.map((item) =>
          `<li>
             <span class="legend-swatch" style="background:${window.Palette.group(item.hue, item.peak)}"></span>
             <span class="legend-group-name">${esc(item.name)}</span>
             <span class="legend-group-count">${number(item.units)}</span>
           </li>`).join("") +
        (rest > 0
          ? `<li class="legend-more">+${number(rest)} more group${rest === 1 ? "" : "s"} lead somewhere</li>`
          : "") +
        `</ul>
         <div class="legend-shade">
           <span class="legend-shade-label">Share of the leading group${
             legend.fitted ? ` <em class="legend-fitted">fitted to this view</em>` : ""}</span>
           <div class="legend-scale" role="img"
                aria-label="Paler is a smaller share, darker is a larger one">
             ${window.Palette.groupRamp("#6b6b6b", 5, legend.floor, legend.ceiling)
                 .map((c) => `<span style="background:${c}"></span>`).join("")}
           </div>
           <div class="legend-ends"><span>${legend.floor}%${legend.fitted ? "" : " or less"}</span><span>${legend.ceiling}%</span></div>
         </div>` +
        (legend.unplaced
          ? `<div class="legend-item">
               <span class="legend-swatch" style="background:${legend.unplacedColor}"></span>
               <span>Group not yet classified in ${number(legend.unplaced)} unit${legend.unplaced === 1 ? "" : "s"}</span>
               <button class="info" type="button" data-info-text="These units have a figure and a group name, but the name is not placed in the tree yet, so the map cannot say which family it belongs to. It is drawn in its own colour rather than left blank, because the data is there -- only the classification is missing.">i</button>
             </div>`
          : "") +
        (legend.missing
          ? `<div class="legend-item">
               <span class="legend-swatch" style="background:${legend.missingColor}"></span>
               <span>No figure for ${number(legend.missing)} unit${legend.missing === 1 ? "" : "s"}</span>
             </div>`
          : "");
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
        (legend.fitted
          ? `<p class="legend-fitted-note">Fitted to the range on screen.</p>` : "") +
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
                                        { field: state.field, group: state.group,
                                          depth: state.depth, spread: state.spread,
                                          inView: (record) =>
                                            window.WorldMap.inView(record.point) });
    window.WorldMap.applyColors(levelId, result.colors);
    renderLegend(result.legend);
    updateLevelNote(level, records.length);
  }

  function updateLevelNote(level, count) {
    const names = ["countries", "first-level divisions", "second-level divisions"];
    els.levelNote.textContent = `${number(count)} ${names[level]} loaded`;
    // The paragraph explaining how the current view encodes its numbers used
    // to sit here, under a control it is not about. It belongs to the legend,
    // and behind the legend's own "i": it is a thing to read once.
    const metric = window.Metrics.METRICS[state.metric];
    const dot = document.querySelector('[data-info="legend"]');
    if (dot) {
      dot.dataset.infoText = metric.note
        ? `${metric.note} Colours are resolved from the data each time you ` +
          `change a control, so the key always describes what is on screen.`
        : "";
    }
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
      point: record.point,
      level: levelIndex < 0 ? 1 : levelIndex,
    });
    if (options.fly && !record.bbox && record.point) {
      window.WorldMap.getMap().easeTo({ center: record.point, zoom: 5, duration: 800 });
    }
    window.Dashboard.render(record, els.sidebarBody);
    els.sidebar.classList.add("is-open");

    // Pull the level below so the children list and the next zoom are ready.
    // Only a country's *primary* profile owns the subdivisions filed under its
    // code. A secondary Factbook profile (the West Bank under PSE, the Coral
    // Sea Islands under AUS) is a distinct place sharing that code, so pulling
    // the code's children here would offer an uninhabited reef Australia's
    // states as its own.
    if (record.level === "admin0" && (!record.country || record.country === record.id)) {
      window.DataStore.loadLevel(record.id, 1).then(afterLoad);
    }
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
      const opts = { field: state.field, group: state.group, depth: state.depth };
      const value = metric.evaluate(record, opts);
      if (metric.kind === "status") {
        const s = window.Palette.status(value);
        const field = window.Metrics.FIELDS.find((f) => f.key === state.field);
        bits.push(s.icon + " " + s.label + " — " + (field ? field.label.toLowerCase() : state.field));
      } else if (Number.isFinite(value)) {
        const shown = metric.display
          ? metric.display(record, opts)
          : (metric.format ? metric.format(value) : value);
        bits.push(metric.label + ": " + shown);
      } else if (metric.kind === "group") {
        // The group map's value is a name, which is not a finite number, so
        // it has to be asked for before the "no value" branch claims it.
        bits.push(metric.display(record, opts));
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
      // A ramp fitted to the range on screen has to be recomputed when the
      // screen changes, or the legend describes the view you just left.
      onMoved: () => { if (state.spread === "fit") refreshColors(); },
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
      const row = await window.Search.getWhenReady(deepLink);
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
