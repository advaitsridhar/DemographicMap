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
    // minzoom is where the archive has tiles, not where the level is shown.
    // Second-level divisions are tiled from z2 so they can be pinned at world
    // view; the zoom hand-off below still hands them over at 6.6.
    { id: "admin2", url: "tiles/admin2.pmtiles", minzoom: 2, maxzoom: 9, showFrom: 6.6, showTo: 22 },
  ];

  let map = null;
  let popup = null;
  let selectedId = null;
  let hoverId = null;
  let activeLevel = 0;
  let handlers = {};
  // ISO3 codes whose second level covers only part of the country -- read from
  // build.json, which the build writes from PARTIAL_LEVELS. Empty until it
  // arrives, which is why the layer below filters to a literal list rather
  // than being created conditionally: the style must not depend on the order
  // a fetch happens to complete in.
  let partialCountries = [];
  const colorState = new Map();  // level id -> Map(shapeID -> color)
  // Kept beside the colours, and re-applied with them, so a restyle cannot

  // When set, the viewer has chosen a level explicitly and zoom no longer picks
  // one. Second-level divisions at world view are the point: 49,349 shapes at
  // once, which is a different map from three thousand countries and the only
  // way to read a filtered group at district granularity across borders.
  let pinnedLevel = null;
  // The floor the map was created with, so unpinning restores it rather than
  // quietly widening the map's range to zero.
  const BASE_MIN_ZOOM = 0.6;

  function levelIndex(zoom) {
    if (pinnedLevel !== null) return pinnedLevel;
    if (zoom < LEVELS[1].showFrom) return 0;
    if (zoom < LEVELS[2].showFrom) return 1;
    return 2;
  }

  /* Show one level everywhere, or hand control back to the zoom.
   *
   * The fade expressions and the layers' own zoom ranges are what normally
   * confine a level to its band, so both are overridden here and restored on
   * the way out -- setting opacity alone would leave the layer clipped to its
   * original minzoom and the map empty below it.
   */
  function setPinnedLevel(index) {
    pinnedLevel = index;
    if (!map) return;
    for (let i = 0; i < LEVELS.length; i += 1) {
      const level = LEVELS[i];
      const shown = index === null || i === index;
      for (const suffix of ["fill", "line", "hover"]) {
        const id = `${level.id}-${suffix}`;
        if (!map.getLayer(id)) continue;
        map.setLayoutProperty(id, "visibility", shown ? "visible" : "none");
        if (index === null) {
          map.setLayerZoomRange(id, layerMinZoom(level), layerMaxZoom(level));
          if (suffix === "fill") map.setPaintProperty(id, "fill-opacity", fadeExpression(level));
        } else if (shown) {
          map.setLayerZoomRange(id, level.minzoom, 24);
          if (suffix === "fill") map.setPaintProperty(id, "fill-opacity", 1);
        }
      }
    }
    // A level's archive starts where it starts: second-level divisions are not
    // tiled below z2, so zooming further out while pinned to them would show
    // ocean and read as a broken map rather than as the edge of the data. The
    // floor moves with the choice instead.
    map.setMinZoom(index === null ? BASE_MIN_ZOOM
                                  : Math.max(BASE_MIN_ZOOM, LEVELS[index].minzoom));
    if (index !== null && map.getZoom() < LEVELS[index].minzoom) {
      map.setZoom(LEVELS[index].minzoom);
    }
    const next = levelIndex(map.getZoom());
    if (next !== activeLevel) activeLevel = next;
    if (handlers.onLevelChange) handlers.onLevelChange(activeLevel);

    announceView();
  }

  // Announcing the view is what fetches a country's attributes, so an
  // announcement that comes too early is the difference between a filled map
  // and a blank one. visibleCountries() reads the tiles already parsed, and a
  // move that lands somewhere new -- a jump to a small country, a zoom that
  // crosses into another level -- has none of them yet: the honest answer at
  // that instant is an empty list, and nothing is fetched for what is now on
  // screen. So ask twice. The second ask, once the map falls idle, is when the
  // answer exists. Without it a view stayed grey until some later pan happened
  // to ask again, which is how the Bahamas read as having no data at all: its
  // fourteen recorded islands were never fetched, so not even their gap
  // markers were drawn.
  let idleAnnouncePending = false;
  function announceView() {
    if (handlers.onViewChange) handlers.onViewChange(activeLevel, visibleCountries());
    if (idleAnnouncePending) return;
    idleAnnouncePending = true;
    map.once("idle", () => {
      idleAnnouncePending = false;
      if (handlers.onViewChange) handlers.onViewChange(activeLevel, visibleCountries());
    });
  }

  function getPinnedLevel() { return pinnedLevel; }

  const FADE = 0.35;

  /* Second-level borders give way to their colours when zoomed out.
   *
   * Pinned at world view, a border drawn at full strength around every unit
   * is more ink than the units' own colours wherever the units are small.
   * Romania's 3,181 communes average 75 km2, the finest mesh in Europe, and at
   * zoom 4-5 their borders greyed the whole country into a texture that read
   * as a different kind of data from Hungary's or Bulgaria's beside it. The
   * borders fade in over the zooms where units become large enough to be seen
   * one by one, and are at full strength from where the level normally shows.
   */
  function lineOpacity(level) {
    if (level.id !== "admin2") return 0.9;
    return ["interpolate", ["linear"], ["zoom"], 2, 0.15, 5, 0.35, level.showFrom, 0.9];
  }

  function layerMinZoom(level) { return Math.max(0, level.showFrom - FADE); }
  function layerMaxZoom(level) { return Math.min(24, level.showTo + FADE); }

  /* Cross-fade between levels. MapLibre requires the interpolate stops to be in
   * strictly ascending order, so the stop list is built and then de-duplicated
   * rather than written out literally -- admin-0 starts at zoom 0, where the
   * fade-in stop and the full-opacity stop would otherwise collide. */
  function fadeExpression(level, wrap) {
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
      expr.push(zoom, wrap ? wrap(opacity) : opacity);
    }
    return expr;
  }

  /* An estimate is drawn exactly like a reading, by the owner's decision of
   * 21 September 2026.
   *
   * It used to be hatched as well as coloured: the colour said what the
   * estimate said and the diagonal lines said it was not published, which is
   * two claims a reader needs at once (docs/MODELLING.md, section 6). The
   * owner's words were that a modelled unit "should look normal", and the
   * hatch is gone with the layer, the pattern and the feature-state flag that
   * switched it on.
   *
   * The distinction is not gone with it. It is in the panel, where the badge
   * names the status ("Modelled", "Derived"), the note's first sentence says
   * nothing was read for the unit, and the record carries its own method and
   * vintage; and it is in the estimates control, which still decides whether
   * a modelled unit is coloured at all. What changed is that the map's
   * surface no longer carries the caveat -- a reader who wants it opens the
   * unit.
   */

  function partialFilter() {
    return ["in", ["get", "shapeGroup"], ["literal", partialCountries.slice()]];
  }

  /* Tell the map which countries have a partial second level.
   *
   * Called once build.json is in. Kept in module state as well as applied, so
   * a restyle (theme change) rebuilds the layer with the same list rather than
   * silently dropping it.
   */
  function setPartialLevels(list) {
    partialCountries = Array.isArray(list)
      ? list.map((row) => (typeof row === "string" ? row : row && row.iso3))
            .filter(Boolean)
      : [];
    if (map && map.getLayer("partial-land")) {
      map.setFilter("partial-land", partialFilter());
    }
  }

  function baseStyle() {
    const css = getComputedStyle(document.documentElement);
    const water = css.getPropertyValue("--water").trim() || "#dfe6ee";
    const land = css.getPropertyValue("--land-base").trim() || "#eceae4";
    const boundary = css.getPropertyValue("--boundary").trim() || "#b9b7ae";

    const sources = {};
    const layers = [{ id: "background", type: "background", paint: { "background-color": water } }];

    /* Land that is inside no second-order unit.
     *
     * Every fill below paints a *unit*. Where a country's second level does
     * not tile it there is no unit to paint, so the ground falls through to
     * the background -- which is the water colour. Uruguay's second-order
     * units are municipios, constituted around population centres rather than
     * carved out of the map, and they cover 36.8% of the country; at
     * second-order zoom the other 112,404 km2 was rendering as sea. A missing
     * figure is a gap, but ground drawn as ocean is a false statement about
     * the world, and the worse of the two.
     *
     * So the neutral land colour goes underneath those countries, and the
     * ground reads as land with nothing known about it -- which is what it is.
     * It deliberately carries no data colour: an unmapped stretch of Durazno
     * must not borrow its department's figure, which would invent a
     * measurement for a unit that does not exist.
     *
     * Filtered to the countries the build declares, so nothing else changes.
     * The first-order geometry is the source because that is the level which
     * does cover these countries, and it is drawn only from the zoom where the
     * second-order layer starts to paint.
     */
    layers.push({
      id: "partial-land",
      type: "fill",
      source: "admin1",
      "source-layer": "admin1",
      minzoom: layerMinZoom(LEVELS[2]),
      paint: { "fill-color": land },
      filter: partialFilter(),
    });

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
          "line-opacity": lineOpacity(level),
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

  /** Colour one level. An estimate's colour is a colour like any other. */
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

  function select(id, { fly = false, bbox = null, point = null, level = null } = {}) {
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
      fitBBox(bbox, FIT_MAX_ZOOM[level == null ? 1 : Math.min(level, 2)], point);
    }
  }

  function fitBBox(bbox, maxZoom, point = null) {
    const [w, s, e, n] = bbox;
    if (![w, s, e, n].every(Number.isFinite)) return;
    const cap = Number.isFinite(maxZoom) ? maxZoom : 9;
    // Degenerate or antimeridian-spanning boxes (Russia, Fiji, USA) would make
    // fitBounds zoom all the way out; centre on them instead.
    if (e - w > 180 || e <= w || n <= s) {
      const center = Array.isArray(point) && point.length === 2 && point.every(Number.isFinite)
        ? point : [(w + e) / 2, (s + n) / 2];
      map.easeTo({ center, zoom: Math.min(3, cap), duration: 800 });
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

    // The style loads on the next animation frame, not synchronously: MapLibre's
    // Style.loadJSON defers _load through frameAsync, and getLayer() reads the
    // layer table that _load fills. So a setPartialLevels() call that lands
    // between init() and that frame -- which is the normal case, since
    // build.json is already cached by the time the app reaches init() -- finds
    // no "partial-land" layer to filter, and the style keeps the empty list it
    // was built with. Uruguay rendered as sea until the theme toggle rebuilt
    // the style. Applying the module state here closes that window, and every
    // later restyle, in the same place.
    map.on("style.load", () => {
      if (map.getLayer("partial-land")) map.setFilter("partial-land", partialFilter());
    });

    map.on("load", () => {
      activeLevel = levelIndex(map.getZoom());
      if (handlers.onReady) handlers.onReady(map);
      if (handlers.onLevelChange) handlers.onLevelChange(activeLevel);
      announceView();
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
        announceView();
        // Only the fitted shading cares where the viewport is; the handler is
        // a no-op otherwise, so this costs a call per pan and nothing else.
        if (handlers.onMoved) handlers.onMoved();
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
      if (pinnedLevel !== null) setPinnedLevel(pinnedLevel);
      repaintAll();
      if (selectedId) LEVELS.forEach((level) => setFeatureState(level.id, selectedId, { selected: true }));
    });
  }

  function getMap() { return map; }

  /** Is this point inside what the reader can currently see? */
  function inView(point) {
    if (!map || !Array.isArray(point)) return false;
    const bounds = map.getBounds();
    const [lng, lat] = point;
    return lat >= bounds.getSouth() && lat <= bounds.getNorth()
      && lng >= bounds.getWest() && lng <= bounds.getEast();
  }
  function getLevel() { return activeLevel; }
  function levelId(i) { return LEVELS[i].id; }

  return { init, applyColors, repaintAll, select, fitBBox, visibleCountries, inView,
           getMap, getLevel, levelId, restyle, setPinnedLevel, getPinnedLevel,
           setPartialLevels, LEVELS };
})();
