# Vendored frontend libraries

Checked in rather than pulled from a CDN so the app runs behind a firewall, in an
air-gapped copy, and from `file://` — and so a CDN outage cannot take the map down.
Each file is the unmodified `dist` build from npm.

| File | Package | Version | Licence |
|---|---|---|---|
| `maplibre-gl.js`, `maplibre-gl.css` | [maplibre-gl](https://github.com/maplibre/maplibre-gl-js) | 5.24.0 | BSD-3-Clause |
| `pmtiles.js` | [pmtiles](https://github.com/protomaps/PMTiles) | 4.5.0 | BSD-3-Clause |
| `minisearch.js` | [minisearch](https://github.com/lucaong/minisearch) | 7.2.0 | MIT |

Licence texts sit alongside as `*.LICENSE.txt`.

There is no charting library. The composition charts are a flex-box stacked bar plus
a labelled list in `site/js/dashboard.js` — every segment carries its own text label
and percentage, which a canvas-based chart would have hidden from screen readers,
find-in-page and copy-paste.

To refresh:

```bash
npm install maplibre-gl pmtiles minisearch
cp node_modules/maplibre-gl/dist/maplibre-gl.js  site/vendor/
cp node_modules/maplibre-gl/dist/maplibre-gl.css site/vendor/
cp node_modules/pmtiles/dist/pmtiles.js          site/vendor/
cp node_modules/minisearch/dist/umd/index.js     site/vendor/minisearch.js
```
