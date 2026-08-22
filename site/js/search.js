/* Client-side search over every entity, sharded so the box is usable instantly.
 *
 * Shard 0 (218 countries + 3,224 first-level divisions, ~270 kB) loads with the
 * page. Shard 2 (49,349 second-level divisions, ~4 MB) is fetched in the
 * background and merged when it arrives; until then the box searches what it
 * has and says so. MiniSearch handles prefix and fuzzy matching over the names.
 */
window.Search = (function () {
  "use strict";

  const LEVEL_LABEL = ["Country", "Admin 1", "Admin 2"];
  let index = null;
  const rows = new Map();     // id -> {id, name, level, country, bbox}
  let ready = false;
  let deepReady = false;
  let onPick = () => {};
  let statusEl = null;

  function makeIndex() {
    return new window.MiniSearch({
      fields: ["name"],
      storeFields: ["name", "level", "country"],
      idField: "id",
      searchOptions: {
        prefix: true,
        fuzzy: 0.2,
        boost: { name: 2 },
      },
    });
  }

  function absorb(payload) {
    const fields = payload.fields;
    const docs = [];
    for (const row of payload.rows) {
      const record = {};
      fields.forEach((field, i) => { record[field] = row[i]; });
      if (rows.has(record.id)) continue;
      rows.set(record.id, record);
      docs.push({ id: record.id, name: record.name, level: record.level, country: record.country });
    }
    index.addAll(docs);
    return docs.length;
  }

  async function init({ onSelect, status }) {
    onPick = onSelect;
    statusEl = status;
    index = makeIndex();
    // Same stamp as the attribute shards, and for the same reason: a
    // force-cached search index outlived every redeploy that changed it.
    await DataStore.loadVersion();
    const shard0 = await fetch(DataStore.url("search-index-0.json")).then((r) => r.json());
    absorb(shard0);
    ready = true;
    // Second-level divisions are the long tail; load them without blocking.
    fetch(DataStore.url("search-index-2.json"))
      .then((r) => r.json())
      .then((shard2) => { absorb(shard2); deepReady = true; })
      .catch((err) => console.warn("admin-2 search shard failed", err));
  }

  function query(text, limit) {
    if (!ready || !text || text.trim().length < 2) return [];
    const hits = index.search(text.trim(), { prefix: true, fuzzy: 0.2 });
    // Countries and first-level units outrank districts of the same score, so
    // typing "Georgia" surfaces the country before a US county.
    hits.sort((a, b) => (b.score - a.score) || (a.level - b.level));
    return hits.slice(0, limit || 12).map((hit) => rows.get(hit.id)).filter(Boolean);
  }

  function get(id) { return rows.get(id) || null; }
  function isDeepReady() { return deepReady; }

  /** Wire the combobox: typing filters, arrows move, Enter/click selects. */
  function attach(input, list) {
    let active = -1;
    let current = [];

    function close() {
      list.hidden = true;
      list.innerHTML = "";
      input.setAttribute("aria-expanded", "false");
      active = -1;
    }

    function paint(results) {
      current = results;
      if (!results.length) {
        const message = input.value.trim().length < 2
          ? "Type at least two letters"
          : (deepReady ? "No match" : "No match yet — still loading second-level divisions");
        list.innerHTML = `<li class="r-empty" role="option" aria-disabled="true">${window.Fmt.escape(message)}</li>`;
      } else {
        list.innerHTML = results.map((row, i) => {
          const country = window.DataStore.country(row.country);
          const countryName = country ? country.name : row.country;
          const context = row.level === 0
            ? ""
            : [row.parentName, countryName].filter(Boolean).join(" · ");
          return `<li role="option" id="sr-${i}" aria-selected="${i === active}" data-id="${window.Fmt.escape(row.id)}">
            <span class="r-level">${LEVEL_LABEL[row.level]}</span>
            <span class="r-name">${window.Fmt.escape(row.name)}</span>
            <span class="r-context">${window.Fmt.escape(context)}</span>
          </li>`;
        }).join("");
      }
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      if (statusEl) {
        statusEl.textContent = results.length
          ? `${results.length} result${results.length === 1 ? "" : "s"}`
          : "No results";
      }
    }

    function choose(i) {
      const row = current[i];
      if (!row) return;
      input.value = row.name;
      close();
      onPick(row);
    }

    input.addEventListener("input", () => paint(query(input.value)));
    input.addEventListener("focus", () => { if (input.value.trim().length >= 2) paint(query(input.value)); });
    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        if (list.hidden) return;
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        active = (active + step + current.length) % Math.max(current.length, 1);
        Array.from(list.children).forEach((li, i) => li.setAttribute("aria-selected", String(i === active)));
        const el = list.children[active];
        if (el) el.scrollIntoView({ block: "nearest" });
      } else if (event.key === "Enter") {
        if (!list.hidden) { event.preventDefault(); choose(active >= 0 ? active : 0); }
      } else if (event.key === "Escape") {
        close(); input.blur();
      }
    });
    list.addEventListener("mousedown", (event) => {
      const li = event.target.closest("li[data-id]");
      if (!li) return;
      event.preventDefault();
      choose(Array.from(list.children).indexOf(li));
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".search")) close();
    });
  }

  return { init, attach, query, get, isDeepReady };
})();
