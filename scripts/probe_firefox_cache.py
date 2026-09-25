#!/usr/bin/env python3
"""Replay what GitHub Pages can do to a Firefox that has seen the map.

The deployed map loads in a fresh Firefox, and Guatemala's divisions do not
load in the owner's: the difference is what that Firefox has kept. This serves
the site the way Pages does -- an ETag made of the deploy time and the size, a
ten-minute max-age, and If-Range and If-None-Match answered as HTTP says --
and opens it in a Firefox whose profile persists between visits, looking at
Guatemala each time. Two histories are replayed, each from a clean profile:
a redeploy between visits (a new deploy stamp, the same bytes), and a first
visit on which the CDN answers each archive's first range request with the
whole archive, as one can on a cache miss -- a whole file Firefox might keep
and answer later ranges from, and a first read the map must recover from
within the visit.

Read-only; the output is the log. Needs xvfb for Firefox's WebGL.

Usage:
    python -m scripts.probe_firefox_cache
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from email.utils import formatdate
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANGE = re.compile(r"bytes=(\d*)-(\d*)")
STAMP = {"deploy": int(time.time())}
# How many more archive range requests to answer with the whole file, as a
# CDN can on a cache miss.
WHOLE = {"left": 0}
SEEN: list[str] = []


class PagesLike(SimpleHTTPRequestHandler):
    """Static files as GitHub Pages serves them, as far as caching goes."""

    def log_message(self, *args) -> None:  # quiet
        pass

    def tag(self, size: int) -> str:
        return f'"{STAMP["deploy"]:x}-{size:x}"'

    def send_head(self):
        if self.path.startswith("/__redeploy"):
            STAMP["deploy"] += 600
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        path = self.translate_path(self.path.split("?")[0])
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        try:
            fh = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        size = os.fstat(fh.fileno()).st_size
        etag = self.tag(size)
        rng = self.headers.get("Range")
        if_range = self.headers.get("If-Range")
        if_none = self.headers.get("If-None-Match")
        if ".pmtiles" in self.path:
            SEEN.append(f"{rng or '-'} if-range={if_range or '-'} if-none={if_none or '-'}")
        if if_none and if_none == etag and not rng:
            fh.close()
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.end_headers()
            return None
        # If-Range with a validator that no longer matches: the whole file.
        if rng and if_range and if_range != etag:
            rng = None
        if rng and ".pmtiles" in self.path and WHOLE["left"] > 0:
            WHOLE["left"] -= 1
            SEEN.append("answered with the whole file")
            rng = None
        common = [("ETag", etag), ("Cache-Control", "max-age=600"),
                  ("Last-Modified", formatdate(STAMP["deploy"], usegmt=True)),
                  ("Accept-Ranges", "bytes"), ("Content-Type", self.guess_type(path))]
        if rng:
            m = RANGE.fullmatch(rng.strip())
            start = int(m.group(1)) if m and m.group(1) else 0
            end = min(int(m.group(2)) if m and m.group(2) else size - 1, size - 1)
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            for k, v in common:
                self.send_header(k, v)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            fh.seek(start)
            data = fh.read(end - start + 1)
            fh.close()
            return _Bytes(data)
        self.send_response(HTTPStatus.OK)
        for k, v in common:
            self.send_header(k, v)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        return fh


class _Bytes:
    def __init__(self, data: bytes):
        self.data, self.done = data, False

    def read(self, n: int = -1) -> bytes:
        if self.done:
            return b""
        self.done = True
        return self.data

    def close(self) -> None:
        pass


VISIT = r"""
const pw = require(process.env.PW_MODULE);
(async () => {
  const [port, profile, label] = process.argv.slice(2);
  const ctx = await pw.firefox.launchPersistentContext(profile, {
    headless: false, viewport: { width: 1400, height: 900 },
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  const log = [];
  page.on("pageerror", (e) => log.push("pageerror: " + e.message));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const first = m.args()[0];
    const said = first ? first.evaluate((e) => (e && (e.message || (e.error && e.error.message))) || String(e)) : Promise.resolve(m.text());
    said.then((t) => log.push("error: " + String(t).slice(0, 200)), () => log.push("error: " + m.text().slice(0, 200)));
  });
  page.on("response", (r) => { if (/pmtiles/.test(r.url()) && r.status() !== 206) log.push(`tile ${r.status()} ${r.url().slice(-22)} ${r.request().headers().range || ""}`); });
  const out = { label };
  try {
    await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: "load" });
    await page.waitForFunction(() => window.WorldMap && window.WorldMap.getMap() && window.WorldMap.getMap().loaded(), null, { timeout: 90000 });
    for (const zoom of [5.5, 8.5, 5.5]) {
      await page.evaluate((z) => window.WorldMap.getMap().jumpTo({ center: [-90.3, 15.2], zoom: z }), zoom);
      await page.waitForTimeout(10000);
      out["z" + zoom + (out["z" + zoom] ? " again" : "")] = await page.evaluate(() => {
        const m = window.WorldMap.getMap();
        const f = m.queryRenderedFeatures({ layers: ["admin1-fill", "admin2-fill"] }).filter((x) => x.properties.shapeGroup === "GTM");
        const count = (layer) => {
          const g = f.filter((x) => x.layer.id === layer);
          return `${new Set(g.filter((x) => x.state && x.state.color).map((x) => x.properties.shapeID)).size}/${new Set(g.map((x) => x.properties.shapeID)).size}`;
        };
        return `admin1 ${count("admin1-fill")}, admin2 ${count("admin2-fill")} drawn`;
      });
    }
  } catch (e) { out.error = String(e).slice(0, 300); }
  out.log = log.slice(0, 12);
  console.log(JSON.stringify(out));
  await ctx.close();
})();
"""


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="ffcache-"))
    run = lambda cmd, **kw: subprocess.run(cmd, cwd=work, check=True, **kw)  # noqa: E731
    print("installing playwright firefox", flush=True)
    run(["npm", "init", "-y"], stdout=subprocess.DEVNULL)
    run(["npm", "install", "--no-audit", "--no-fund", "playwright"], stdout=subprocess.DEVNULL)
    run(["npx", "playwright", "install", "--with-deps", "firefox"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (work / "visit.js").write_text(VISIT, encoding="utf-8")
    env = {**os.environ, "PW_MODULE": str(work / "node_modules" / "playwright")}

    site = work / "site"
    shutil.copytree(ROOT / "site", site)
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                 lambda *a, **k: PagesLike(*a, directory=str(site), **k))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    scenarios = {
        "a redeploy between visits": ("first visit", "after a redeploy", "a reload later"),
        "the CDN ignores Range on a first visit": ("first visit, whole files", "a reload later", "another reload"),
    }
    for n, (name, labels) in enumerate(scenarios.items()):
        profile = work / f"profile-{n}"
        print(f"=== {name} ===", flush=True)
        for label in labels:
            if label == "after a redeploy":
                subprocess.run(["curl", "-s", f"http://127.0.0.1:{port}/__redeploy"], check=False)
            WHOLE["left"] = 3 if label.endswith("whole files") else 0
            SEEN.clear()
            res = subprocess.run(["xvfb-run", "-a", "-s", "-screen 0 1400x900x24",
                                  "node", "visit.js", str(port), str(profile), label],
                                 cwd=work, env=env, capture_output=True, text=True, timeout=400)
            print(res.stdout.strip() or res.stderr.strip()[-1500:], flush=True)
            conditional = [s for s in SEEN if "if-range=-" not in s or "if-none=-" not in s]
            whole = SEEN.count("answered with the whole file")
            print(f"  archive requests reaching the server {len(SEEN) - whole}, "
                  f"answered whole {whole}, conditional {len(conditional) - whole}: "
                  f"{[c for c in conditional if 'whole' not in c][:4]}", flush=True)
    server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
