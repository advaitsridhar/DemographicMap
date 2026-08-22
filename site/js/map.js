/* The map: three PMTiles archives read straight from static hosting.
 *
 * MapLibre fetches the archives with HTTP range requests through the pmtiles
 * protocol, so there is no tile server -- GitHub Pages serves a handful of .pmtiles
 * files and the browser pulls only the byte ranges it needs.
 *
 * Zoom hand-off: countries below z4, first-level divisions z4-z7, second-level
 * from z7. Each level fades rather than popping, and the level actually in play
 * drives which attribute files get loaded.
 */
window.WorldMap = (function () {
  "use strict";

  const LEVELS = [
    { id: "admin0", url: "tiles/admin0.pmtiles", minzoom: 0, maxzoom: 5, showFrom: 0,   showTo: 4.4 },
    { id: "admin1", url: "tiles/admin1.pmtiles", minzoom: 0, maxzoom: 7, showFrom: 3.6, showTo: 7.4 },
    { id: "admin2", url: "tiles/admin2.pmtiles", minzoom: 4, maxzoom: 9, showFrom: 6.6, showTo: 22 },
  ];

  let map = null;
  let popup = null;
  let selectedId = null;
  let hoverId = null;
  let activeLevel = 0;
  let handlers = {};
  const colorState = new Map();  // level id -> Map(shapeID -> color)

  function levelIndex(zoom) {
    if (zoom < LEVELS[1].showFrom) return 0;
    if (zoom < LEVELS[2].showFrom) return 1;
    return 2;
  }

  const FADE = 0.35;

  function layerMinZoom(level) { return Math.max(0, level.showFrom - FADE); }
  function layerMaxZoom(level) { return Math.min(24, level.showTo + FADE); }

  /* Cross-fade between levels. MapLibre requires the interpolate stops to be in
   * strictly ascending order, so the stop list is built and then de-duplicated
   * rather than written out literally -- admin-0 starts at zoom 0, where the
   * fade-in stop and the full-opacity stop would otherwise collide. */
  function fadeExpression(level) {
    const stops = [];
    if (level.showFrom > 0) stops.push([layerMinZoom(level), 0]);
    stops.push([level.showFrom, 1]);
    stops.push([Math.min(24, level.showTo), 1]);
    if (level.showTo < 20) stops.push([layerMaxZoom(level), 0]);

    const expr = ["interpolate", ["linear"], ["zoom"]];
    let previous = -Infinity;
    for (const [zoom, opacity] of stops) {
      if (zoom <= previous) continue;
      previous = zoom;
      expr.push(zoom, opacity);
    }
    return expr;
  }

  function baseStyle() {
    const css = getComputedStyle(document.documentElement);
    const water = css.getPropertyValue("--water").trim() || "#dfe6ee";
    const land = css.getPropertyValue("--land-base").trim() || "#eceae4";
    const boundary = css.getPropertyValue("--boundary").trim() || "#b9b7ae";

    const sources = {};
    const layers = [{ id: "background", type: "background", paint: { "background-color": water } }];

    for (const level of LEVELS) {
      sources[level.id] = {
        type: "vector",
        url: `pmtiles://${level.url}`,
        // Promote the shapeID property to the feature id so feature-state
        // (metric colour, hover, selection) survives tile eviction and reload.
        promoteId: level.id === "admin0" ? "shapeGroup" : "shapeID",
        attribution: '<a href="https://www.geoboundaries.org/" target="_blank" rel="noopener">geoBoundaries</a> CC BY 4.0 · ' +
                     '<a href="https://www.cia.gov/the-world-factbook/" target="_blank" rel="noopener">CIA World Factbook</a> (public domain) · ' +
                     '<a href="https://www.naturalearthdata.com/" target="_blank" rel="noopener">Natural Earth</a>',
      };
      layers.push({
        id: `${level.id}-fill`,
        type: "fill",
        source: level.id,
        "source-layer": level.id,
        minzoom: layerMinZoom(level),
        maxzoom: layerMaxZoom(level),
        paint: {
          // feature-state carries the metric colour; land is the fallback so an
          // entity with no data still reads as land rather than as ocean.
          "fill-color": ["coalesce", ["feature-state", "color"], land],
          "fill-opacity": fadeExpression(level),
        },
      });
      layers.push({
        id: `${level.id}-line`,
        type: "line",
        source: level.id,
        "source-layer": level.id,
        minzoom: layerMinZoom(level),
        maxzoom: layerMaxZoom(level),
        paint: {
          "line-color": boundary,
          "line-width": ["interpolate", ["linear"], ["zoom"], 0, 0.3, 6, 0.6, 12, 1],
          "line-opacity": 0.9,
        },
      });
      layers.push({
        id: `${level.id}-hover`,
        type: "line",
        source: level.id,
        "source-layer": level.id,
        minzoom: layerMinZoom(level),
        maxzoom: layerMaxZoom(level),
        paint: {
          "line-color": css.getPropertyValue("--ink-primary").trim() || "#0b0b0b",
          "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.4,
                         ["boolean", ["feature-state", "hover"], false], 1.4, 0],
          "line-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 1, 0.7],
        },
      });
    }
    return { version: 8, sources, layers };
  }

  function featureKey(feature) {
    return feature.properties.shapeID || feature.properties.shapeGroup;
  }

  function setFeatureState(levelId, id, state) {
    if (!id || !map) return;
    try {
      map.setFeatureState({ source: levelId, sourceLayer: levelId, id }, state);
    } catch (err) {
      // The tile holding this feature is not loaded yet; the sourcedata handler
      // repaints once it arrives.
    }
  }

  function applyColors(levelId, colors) {
    colorState.set(levelId, colors);
    repaintLevel(levelId);
  }

  function repaintLevel(levelId) {
    const colors = colorState.get(levelId);
    if (!colors || !map || !map.getSource(levelId)) return;
    const features = map.querySourceFeatures(levelId, { sourceLayer: levelId });
    const seen = new Set();
    for (const feature of features) {
      const key = featureKey(feature);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      const color = colors.get(key);
      map.setFeatureState({ source: levelId, sourceLayer: levelId, id: feature.id },
                          { color: color || null });
    }
  }

  function repaintAll() { LEVELS.forEach((level) => repaintLevel(level.id)); }

  function visibleCountries() {
    const level = LEVELS[activeLevel];
    if (!map.getSource(level.id)) return [];
    const features = map.querySourceFeatures(level.id, { sourceLayer: level.id });
    const out = new Set();
    for (const feature of features) {
      if (feature.properties.shapeGroup) out.add(feature.properties.shapeGroup);
    }
    return Array.from(out);
  }

  // Cap the fly-to zoom per level so selecting a state does not land you inside
  // the district layer, where the state you just picked is no longer drawn.
  const FIT_MAX_ZOOM = [4.2, 6.4, 8.6];

  function select(id, { fly = false, bbox = null, level = null } = {}) {
    for (const level of LEVELS) {
      if (selectedId) setFeatureState(level.id, selectedId, { selected: false });
    }
    selectedId = id;
    for (const level of LEVELS) {
      const colors = colorState.get(level.id);
      if (colors && colors.has(id)) setFeatureState(level.id, id, { selected: true });
    }
    // The selected feature may live in a level whose tiles are not queried yet;
    // set it on all three and let the miss be a no-op.
    LEVELS.forEach((level) => setFeatureState(level.id, id, { selected: true }));
    if (fly && bbox && bbox.length === 4) {
      fitBBox(bbox, FIT_MAX_ZOOM[level == null ? 1 : Math.min(level, 2)]);
    }
  }

  function fitBBox(bbox, maxZoom) {
    const [w, s, e, n] = bbox;
    if (![w, s, e, n].every(Number.isFinite)) return;
    const cap = Number.isFinite(maxZoom) ? maxZoom : 9;
    // Degenerate or antimeridian-spanning boxes (Russia, Fiji, USA) would make
    // fitBounds zoom all the way out; centre on them instead.
    if (e - w > 180 || e <= w || n <= s) {
      map.easeTo({ center: [(w + e) / 2, (s + n) / 2], zoom: Math.min(3, cap), duration: 800 });
      return;
    }
    map.fitBounds([[w, s], [e, n]], { padding: 60, maxZoom: cap, duration: 800 });
  }

  function init(options) {
    handlers = options || {};
    const protocol = new window.pmtiles.Protocol();
    window.maplibregl.addProtocol("pmtiles", protocol.tile);

    map = new window.maplibregl.Map({
      container: "map",
      style: baseStyle(),
      center: [12, 25],
      zoom: 1.7,
      minZoom: 0.6,
      maxZoom: 12,
      renderWorldCopies: true,
      attributionControl: { compact: true },
      hash: false,
    });

    map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new window.maplibregl.ScaleControl({ maxWidth: 90, unit: "metric" }), "bottom-right");

    popup = new window.maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });

    map.on("load", () => {
      activeLevel = levelIndex(map.getZoom());
      if (handlers.onReady) handlers.onReady(map);
      if (handlers.onLevelChange) handlers.onLevelChange(activeLevel);
      if (handlers.onViewChange) handlers.onViewChange(activeLevel, visibleCountries());
    });

    let moveTimer = null;
    map.on("moveend", () => {
      const next = levelIndex(map.getZoom());
      if (next !== activeLevel) {
        activeLevel = next;
        if (handlers.onLevelChange) handlers.onLevelChange(activeLevel);
      }
      clearTimeout(moveTimer);
      moveTimer = setTimeout(() => {
        if (handlers.onViewChange) handlers.onViewChange(activeLevel, visibleCountries());
      }, 120);
    });

    map.on("sourcedata", (event) => {
      if (event.sourceId && event.isSourceLoaded && colorState.has(event.sourceId)) {
        repaintLevel(event.sourceId);
        if (selectedId) setFeatureState(event.sourceId, selectedId, { selected: true });
      }
    });

    for (const level of LEVELS) {
      const layer = `${level.id}-fill`;
      map.on("mousemove", layer, (event) => {
        if (LEVELS.indexOf(level) !== activeLevel) return;
        const feature = event.features && event.features[0];
        if (!feature) return;
        map.getCanvas().style.cursor = "pointer";
        const key = featureKey(feature);
        if (hoverId && hoverId !== key) {
          LEVELS.forEach((l) => setFeatureState(l.id, hoverId, { hover: false }));
        }
        hoverId = key;
        map.setFeatureState({ source: level.id, sourceLayer: level.id, id: feature.id }, { hover: true });
        if (handlers.onHover) {
          const html = handlers.onHover(key, feature.properties);
          if (html) popup.setLngLat(event.lngLat).setHTML(html).addTo(map);
          else popup.remove();
        }
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
        if (hoverId) LEVELS.forEach((l) => setFeatureState(l.id, hoverId, { hover: false }));
        hoverId = null;
        popup.remove();
      });
      map.on("click", layer, (event) => {
        if (LEVELS.indexOf(level) !== activeLevel) return;
        const feature = event.features && event.features[0];
        if (!feature) return;
        const key = featureKey(feature);
        select(key);
        if (handlers.onSelect) handlers.onSelect(key, feature.properties, LEVELS.indexOf(level));
      });
    }

    return map;
  }

  function restyle() {
    if (!map) return;
    const style = baseStyle();
    map.setStyle(style, { diff: false });
    map.once("idle", () => {
      repaintAll();
      if (selectedId) LEVELS.forEach((level) => setFeatureState(level.id, selectedId, { selected: true }));
    });
  }

  function getMap() { return map; }
  function getLevel() { return activeLevel; }
  function levelId(i) { return LEVELS[i].id; }

  return { init, applyColors, repaintAll, select, fitBBox, visibleCountries,
           getMap, getLevel, levelId, restyle, LEVELS };
})();
