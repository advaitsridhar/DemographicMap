#!/usr/bin/env python3
"""Open the deployed map in real browsers and report what one country draws.

Everything the build checks is the data; nothing checks the page as a
visitor's browser meets it on GitHub Pages. When a country's divisions are
reported blank on the live site while every local check passes, the
difference is the host or the browser, and this looks at both: it installs
Chromium, Firefox and WebKit (Safari's engine) on the runner, opens the live
page in each, zooms to the country at first- and second-level zoom, and
prints what is drawn, what a click shows, and every error, failed request and
warning on the way.

Read-only; the output is the log.

Usage:
    python -m scripts.probe_live_map --iso3 GTM --center -90.3,15.2
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SITE = "https://advaitsridhar.github.io/DemographicMap/"

PROBE = r"""
const pw = require(process.env.PW_MODULE);
(async () => {
  const [engine, site, iso3, lon, lat] = process.argv.slice(2);
  const browser = await pw[engine].launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const log = [];
  page.on("pageerror", (e) => log.push("pageerror: " + e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type())) log.push(m.type() + ": " + m.text().slice(0, 300)); });
  page.on("requestfailed", (r) => log.push("failed: " + r.url() + " " + ((r.failure() || {}).errorText || "")));
  page.on("response", (r) => { if (r.status() >= 400) log.push("http " + r.status() + ": " + r.url()); });
  const out = { engine };
  try {
    await page.goto(site, { waitUntil: "load", timeout: 90000 });
    out.userAgent = await page.evaluate(() => navigator.userAgent);
    out.webgl = await page.evaluate(() => { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); });
    await page.waitForFunction(() => window.WorldMap && window.WorldMap.getMap() && window.WorldMap.getMap().loaded(), null, { timeout: 90000 });
    for (const zoom of [5.5, 8.5]) {
      await page.evaluate(([x, y, z]) => window.WorldMap.getMap().jumpTo({ center: [x, y], zoom: z }), [+lon, +lat, zoom]);
      await page.waitForTimeout(12000);
      const seen = await page.evaluate((iso3) => {
        const m = window.WorldMap.getMap();
        const layers = ["admin1-fill", "admin2-fill"].filter((l) => m.getLayer(l));
        const f = m.queryRenderedFeatures({ layers }).filter((x) => x.properties.shapeGroup === iso3);
        const byLayer = {};
        for (const x of f) {
          const k = x.layer.id;
          byLayer[k] = byLayer[k] || { shapes: new Set(), coloured: new Set() };
          byLayer[k].shapes.add(x.properties.shapeID);
          if (x.state && x.state.color) byLayer[k].coloured.add(x.properties.shapeID);
        }
        const summary = {};
        for (const [k, v] of Object.entries(byLayer)) summary[k] = { shapes: v.shapes.size, coloured: v.coloured.size };
        const status = [...document.querySelectorAll("#sidebar *")].map((e) => e.childElementCount ? "" : e.textContent.trim())
          .filter((t) => /divisions loaded|loading|Loading/.test(t)).slice(0, 3);
        return { zoom: m.getZoom(), drawn: summary, status };
      }, iso3);
      await page.mouse.click(700 - 330 + 330, 450);
      await page.waitForTimeout(4000);
      seen.panel = await page.evaluate(() => {
        const b = document.getElementById("sidebar-body") || document.querySelector("aside:last-of-type");
        return b ? b.innerText.slice(0, 160).replace(/\n+/g, " | ") : null;
      });
      out["z" + zoom] = seen;
      await page.screenshot({ path: `live_${engine}_z${zoom}.png` });
    }
  } catch (e) {
    out.error = String(e).slice(0, 400);
  }
  out.log = log.slice(0, 25);
  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})();
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iso3", default="GTM")
    ap.add_argument("--center", default="-90.3,15.2", help="lon,lat")
    ap.add_argument("--site", default=SITE)
    ap.add_argument("--engines", default="chromium,firefox,webkit")
    args = ap.parse_args()
    lon, lat = args.center.split(",")
    work = Path(tempfile.mkdtemp(prefix="livemap-"))
    engines = [e for e in args.engines.split(",") if e]
    run = lambda cmd, **kw: subprocess.run(cmd, cwd=work, check=True, **kw)  # noqa: E731
    print(f"installing playwright and {', '.join(engines)}", flush=True)
    run(["npm", "init", "-y"], stdout=subprocess.DEVNULL)
    run(["npm", "install", "--no-audit", "--no-fund", "playwright"], stdout=subprocess.DEVNULL)
    run(["npx", "playwright", "install", "--with-deps", *engines],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (work / "probe.js").write_text(PROBE, encoding="utf-8")
    env = {**os.environ, "PW_MODULE": str(work / "node_modules" / "playwright")}
    for engine in engines:
        print(f"=== {engine} ===", flush=True)
        result = subprocess.run(["node", "probe.js", engine, args.site, args.iso3, lon, lat],
                                cwd=work, env=env, capture_output=True, text=True, timeout=600)
        print(result.stdout.strip() or "(no output)")
        if result.returncode:
            print(result.stderr.strip()[-2000:])
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
