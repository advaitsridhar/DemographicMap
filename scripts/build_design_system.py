#!/usr/bin/env python3
"""Build the generated files of design-system/ and check it against the site.

design-system/ writes down the site's visual language: tokens.json (every
colour, size and type style, each with a note on where it is used), the
component stylesheet, and guidelines with a preview for each component. Two of
its files are generated, and this script generates them:

  design-system/components/bundle.css  from site/css/app.css
  design-system/tokens.css             from design-system/tokens.json

bundle.css is app.css with its theme blocks moved into the tokens, each id
selector given a class of the same name (#sidebar -> .sidebar) so the
components work outside the one page they were written for, and a few
literal radii, sizes and z-indices pointed at the tokens that now hold them.
Every computed style is unchanged: the system was checked by rendering the
app's own DOM under app.css and under tokens.css + bundle.css, in both themes
and at desktop and phone widths, with no difference in any element.

Most token values were copied from a source, so a change there leaves the
design system describing a site that no longer exists. --check catches that:
it writes nothing, compares both generated files with what this script would
write, and compares every token taken from a source with that source now --
app.css's custom properties, the palettes palette.js computes (run in node),
and the group hues in scripts/group_tree.py. It exits 1 on any difference.

    python3 scripts/build_design_system.py           # rebuild both files
    python3 scripts/build_design_system.py --check   # report drift, change nothing

The hand-written parts -- the usage notes, the guidelines, the previews --
cannot be regenerated. When --check reports drift, update the value in
tokens.json, read the notes beside it, then rebuild.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_CSS = ROOT / "site" / "css" / "app.css"
PALETTE_JS = ROOT / "site" / "js" / "palette.js"
GROUP_TREE = ROOT / "scripts" / "group_tree.py"
DS = ROOT / "design-system"
TOKENS_JSON = DS / "tokens.json"
TOKENS_CSS = DS / "tokens.css"
BUNDLE_CSS = DS / "components" / "bundle.css"

# ----------------------------------------------------------------- bundle.css

BUNDLE_HEADER = """/* World Demographics Map — components.
   The app's own stylesheet (site/css/app.css) with its theme blocks moved
   into tokens.json and each id selector given a class of the same name
   (#sidebar -> .sidebar), so the components can be used outside the one page
   they were written for. Declarations and values are the app's, with one
   omission: html, body drop the app's height: 100%, which only the full-page
   grid needs and .app already sizes itself. The layout classes (.app,
   .filters, .sidebar, .map-legend) keep the app's viewport breakpoints, so use
   them for a full-page shell only. */"""

TOKEN_NOTE = """/* Every colour, shadow, radius, size, z-index and the font stack is a token in
   tokens.json, compiled to tokens.css, which loads before this file and themes
   by data-theme. This file sets only what tokens.css does not. */
:root { color-scheme: light; }
[data-theme="dark"] { color-scheme: dark; }

"""

TYPE_UTILITIES = """
/* ----------------------------------------------------------- type utilities */

/* The text-* classes come from tokens.json. The token format has no
   text-transform, so the five label styles get their uppercase here. */
.text-eyebrow, .text-fact-label, .text-breadcrumb, .text-table-head, .text-level-chip {
  text-transform: uppercase;
}
"""

# Longest first, so #map-wrap is never read as #map.
ID_TO_CLASS = ["map-legend-body", "search-results", "filters-toggle", "sidebar-body", "group-reach",
               "group-count", "about-open", "map-wrap", "sidebar", "filters", "topbar", "legend", "app", "map"]

# (text in app.css, its replacement, how many times app.css holds it). The
# counts are what make this safe: if app.css changes under one of these, the
# build stops and names it rather than quietly leaving a literal behind.
REPLACEMENTS = [
    ("html, body {\n  margin: 0; height: 100%;\n  font-family: var(--font);",
     "html, body {\n  margin: 0;\n  font-family: var(--font-sans);", 1),
    ("font-family: var(--font);", "font-family: var(--font-sans);", 1),
    ("border-radius: 999px", "border-radius: var(--radius-pill)", 5),
    ("border-radius: 50%", "border-radius: var(--radius-round)", 1),
    ("padding: .3rem .2rem; border: none; border-radius: 4px;",
     "padding: .3rem .2rem; border: none; border-radius: var(--radius-xs);", 1),
    ("border: 1px solid transparent; border-radius: 4px;",
     "border: 1px solid transparent; border-radius: var(--radius-xs);", 1),
    (".stack-bar { display: flex; height: 16px; border-radius: 4px;",
     ".stack-bar { display: flex; height: 16px; border-radius: var(--radius-xs);", 1),
    (".stack-bar > span:first-child { border-radius: 4px 0 0 4px; }",
     ".stack-bar > span:first-child { border-radius: var(--radius-xs) 0 0 var(--radius-xs); }", 1),
    (".stack-bar > span:last-child { border-radius: 0 4px 4px 0; }",
     ".stack-bar > span:last-child { border-radius: 0 var(--radius-xs) var(--radius-xs) 0; }", 1),
    ("background: transparent; border: none; border-radius: 3px;",
     "background: transparent; border: none; border-radius: var(--radius-swatch);", 1),
    (".legend-scale { display: flex; height: 10px; border-radius: 3px;",
     ".legend-scale { display: flex; height: 10px; border-radius: var(--radius-swatch);", 1),
    (".legend-swatch { width: 12px; height: 12px; border-radius: 3px;",
     ".legend-swatch { width: 12px; height: 12px; border-radius: var(--radius-swatch);", 1),
    (".composition-list .swatch { width: 10px; height: 10px; border-radius: 3px;",
     ".composition-list .swatch { width: 10px; height: 10px; border-radius: var(--radius-swatch);", 1),
    (".chip { display: inline-block; width: 12px; height: 12px; border-radius: 3px;",
     ".chip { display: inline-block; width: 12px; height: 12px; border-radius: var(--radius-swatch);", 1),
    ("border-radius: 2px; box-shadow: inset 0 0 0 1px var(--border-ring);",
     "border-radius: var(--radius-dot); box-shadow: inset 0 0 0 1px var(--border-ring);", 1),
    ("box-shadow: 0 1px 2px rgba(0,0,0,.08);", "box-shadow: var(--shadow-seg);", 1),
    ("box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.25);", "box-shadow: var(--shadow-swatch-provisional);", 1),
    ("dialog::backdrop { background: rgba(11,11,11,.45); }", "dialog::backdrop { background: var(--backdrop); }", 1),
    ("    repeating-linear-gradient(135deg, rgba(0,0,0,.55) 0 1.6px, rgba(255,255,255,.85) 1.6px 2.3px,\n"
     "                              rgba(0,0,0,.55) 2.3px 3px, transparent 3px 6px),\n    #6b6b6b;",
     "    repeating-linear-gradient(135deg, var(--hatch-dark) 0 1.6px, var(--hatch-light) 1.6px 2.3px,\n"
     "                              var(--hatch-dark) 2.3px 3px, transparent 3px 6px),\n    var(--group-any);", 1),
    ("position: absolute; left: -9999px; top: 0; z-index: 100;",
     "position: absolute; left: -9999px; top: 0; z-index: var(--z-skip-link);", 1),
    ("border-bottom: 1px solid var(--hairline);\n  z-index: 20;",
     "border-bottom: 1px solid var(--hairline);\n  z-index: var(--z-topbar);", 1),
    ("max-height: min(60vh, 460px); overflow-y: auto; z-index: 40;",
     "max-height: min(60vh, var(--results-h)); overflow-y: auto; z-index: var(--z-search-results);", 1),
    ("z-index: 16; min-width: 0;", "z-index: var(--z-filters); min-width: 0;", 1),
    ("position: sticky; top: 0; z-index: 2;", "position: sticky; top: 0; z-index: var(--z-sticky-head);", 1),
    ("position: absolute; left: 12px; bottom: 12px; z-index: 10;\n  width: min(280px, calc(100% - 24px));",
     "position: absolute; left: var(--overlay-inset); bottom: var(--overlay-inset); z-index: var(--z-map-legend);\n"
     "  width: min(var(--legend-w), calc(100% - 2 * var(--overlay-inset)));", 1),
    ("position: absolute; top: 12px; left: 50%; transform: translateX(-50%);\n  z-index: 12;",
     "position: absolute; top: var(--overlay-inset); left: 50%; transform: translateX(-50%);\n"
     "  z-index: var(--z-map-status);", 1),
    ("overflow-y: auto; position: relative; z-index: 15;",
     "overflow-y: auto; position: relative; z-index: var(--z-sidebar);", 1),
    ("box-shadow: var(--shadow); z-index: 30;", "box-shadow: var(--shadow); z-index: var(--z-drawer);", 1),
    ("position: fixed; z-index: 60; max-width: min(30rem, calc(100vw - 1rem));",
     "position: fixed; z-index: var(--z-info-bubble); max-width: min(var(--bubble-w), calc(100vw - 1rem));", 1),
    (".search { position: relative; flex: 1 1 auto; max-width: 560px;",
     ".search { position: relative; flex: 1 1 auto; max-width: var(--search-w);", 1),
    ("max-height: min(46vh, 380px); overflow-y: auto;",
     "max-height: min(46vh, var(--group-list-h)); overflow-y: auto;", 1),
    ("max-height: 260px; overflow-y: auto; }", "max-height: var(--children-h); overflow-y: auto; }", 1),
    ("  max-width: 640px; width: calc(100% - 2rem); max-height: 84vh;",
     "  max-width: var(--dialog-w); width: calc(100% - 2rem); max-height: 84vh;", 1),
    ("position: fixed; inset: var(--topbar-h) auto 0 0; width: min(340px, 90vw);",
     "position: fixed; inset: var(--topbar-h) auto 0 0; width: min(var(--drawer-w), 90vw);", 1),
    ("position: fixed; inset: auto 0 0 0; height: min(62vh, 560px);",
     "position: fixed; inset: auto 0 0 0; height: min(62vh, var(--sheet-h));", 1),
    (".map-legend { bottom: 12px; width: calc(100% - 24px); }",
     ".map-legend { bottom: var(--overlay-inset); width: calc(100% - 2 * var(--overlay-inset)); }", 1),
    ("  padding: 0 .9rem 2rem;", "  padding: 0 var(--gutter-panel) 2rem;", 1),
    ("  padding: .55rem .9rem;", "  padding: .55rem var(--gutter-panel);", 1),
    ("display: flex; align-items: center; gap: 1rem;\n  padding: .55rem",
     "display: flex; align-items: center; gap: var(--topbar-gap);\n  padding: .55rem", 1),
    (".sidebar-body { padding: 1rem 1.1rem 3rem; }", ".sidebar-body { padding: 1rem var(--gutter-sidebar) 3rem; }", 1),
    ("dialog article { padding: 1rem 1.2rem 1.6rem;", "dialog article { padding: 1rem var(--gutter-dialog) 1.6rem;", 1),
    (".filter-section { margin-top: 1.1rem; }", ".filter-section { margin-top: var(--section-gap); }", 1),
    (".panel { margin-bottom: 1.15rem; }", ".panel { margin-bottom: var(--panel-gap); }", 1),
    (".facts { display: grid; grid-template-columns: repeat(2, 1fr); gap: .5rem; margin-bottom: 1rem; }",
     ".facts { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--tile-gap); margin-bottom: 1rem; }", 1),
]


class Stale(Exception):
    """app.css no longer has text this script expects to transform."""


def build_bundle(app_css: str) -> str:
    """bundle.css, from the text of app.css."""
    src = app_css
    header = re.match(r"/\* World Demographics Map — application shell\..*?\*/", src, flags=re.S)
    if not header:
        raise Stale("app.css no longer opens with its 'application shell' comment")
    src = BUNDLE_HEADER.replace("#sidebar", "SIDEBAR_ID") + src[header.end():]
    try:
        start, end = src.index(":root {"), src.index("* { box-sizing")
    except ValueError as err:
        raise Stale("app.css's token blocks are not where they were: " + str(err)) from err
    src = src[:start] + TOKEN_NOTE + src[end:]
    for name in ID_TO_CLASS:
        src = re.sub("#" + re.escape(name) + r"(?![\w-])", "." + name, src)
    for old, new, count in REPLACEMENTS:
        if src.count(old) != count:
            raise Stale(f"app.css holds {src.count(old)} of {old!r}, expected {count}")
        src = src.replace(old, new)
    return src.replace("SIDEBAR_ID", "#sidebar", 1) + TYPE_UTILITIES


# ----------------------------------------------------------------- tokens.css

def css_name(name: str) -> str:
    return name.replace(".", "\\.")


def css_value(value: str) -> str:
    alias = re.fullmatch(r"\{([A-Za-z0-9][A-Za-z0-9_.-]*)\}", value)
    return f"var(--{css_name(alias.group(1))})" if alias else value


def build_tokens_css(tokens: dict) -> str:
    """tokens.css, laid out the way the Design System page compiles it."""
    themes = [t["id"] for t in tokens["color"]["themes"]]
    first = themes[0]
    themed = tokens["color"]["tokens"] + tokens.get("shadow", {}).get("tokens", [])
    out = [f"/* {tokens['name']} — generated from tokens.json */", f':root, [data-theme="{first}"] {{']
    for t in themed:
        v = t["value"]
        value = v if isinstance(v, str) else v.get(first, next(iter(v.values())))
        out.append(f"  --{css_name(t['name'])}: {css_value(value)};")
    out.append("}")
    for theme in themes[1:]:
        out.append(f'[data-theme="{theme}"] {{')
        for t in themed:
            v = t["value"]
            if isinstance(v, dict) and theme in v:
                out.append(f"  --{css_name(t['name'])}: {css_value(v[theme])};")
            else:
                base = v if isinstance(v, str) else v.get(first, "")
                if base.startswith("{"):  # an alias is re-declared, so it reads this theme's value
                    out.append(f"  --{css_name(t['name'])}: {css_value(base)};")
        out.append("}")
    out.append(":root {")
    for family, body in tokens.items():
        if family in ("color", "type", "shadow", "name", "version", "meta"):
            continue
        if isinstance(body, dict) and "tokens" in body:
            out.extend(f"  --{css_name(t['name'])}: {t['value']};" for t in body["tokens"])
    out.extend(f"  --font-{key}: {stack};" for key, stack in tokens["type"].get("families", {}).items())
    out.append("}")
    for group in tokens["type"].get("groups", []):
        for s in group["styles"]:
            decl = [f"font-family: var(--font-{s.get('family', group.get('family'))})", f"font-size: {s['fontSize']}"]
            for key, prop in (("lineHeight", "line-height"), ("fontWeight", "font-weight"),
                              ("letterSpacing", "letter-spacing"), ("fontStyle", "font-style")):
                if key in s:
                    decl.append(f"{prop}: {s[key]}")
            out.append(f".{css_name(s['name'])} {{ " + "; ".join(decl) + "; }")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------ source values

def _rgba(value: str) -> str:
    """rgba(11,11,11,.10) -> rgba(11, 11, 11, 0.10), the spelling tokens.json uses."""
    value = " ".join(value.split())
    return re.sub(r"rgba\(\s*(\d+),\s*(\d+),\s*(\d+),\s*\.(\d+)\)",
                  lambda m: f"rgba({m.group(1)}, {m.group(2)}, {m.group(3)}, 0.{m.group(4)})", value)


def app_css_values(app_css: str) -> dict[str, dict[str, str]]:
    """Every custom property app.css declares, per theme."""
    def block(selector: str) -> dict[str, str]:
        i = app_css.index(selector)
        body = app_css[app_css.index("{", i) + 1:app_css.index("}", i)]
        return {k: _rgba(v) for k, v in re.findall(r"--([\w-]+):\s*([^;]+);", body)}
    light = block(":root {")
    return {"light": light, "dark": {**light, **block(':root[data-theme="dark"] {')}}


PALETTE_PROBE = r"""
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8");
const out = {};
for (const theme of ["light", "dark"]) {
  const ctx = { window: { matchMedia: () => ({ matches: theme === "dark" }) },
                document: { documentElement: { getAttribute: () => theme } } };
  vm.createContext(ctx); vm.runInContext(src, ctx);
  const P = ctx.window.Palette;
  out[theme] = {
    categorical: Array.from({ length: P.MAX_CATEGORIES }, (_, i) => P.categorical(i)),
    sequential: P.ramp(), leadingShare: P.groupRamp("#6b6b6b", 5),
    neutral: P.neutral(), unplaced: P.unplaced(),
    status: Object.fromEntries(Object.entries(P.STATUS).map(([k, v]) => [k, v.color])),
  };
}
console.log(JSON.stringify(out));
"""


def palette_values() -> dict | None:
    """The palettes palette.js computes in each theme, or None without node."""
    node = shutil.which("node")
    if not node:
        return None
    run = subprocess.run([node, "-e", PALETTE_PROBE, str(PALETTE_JS)], capture_output=True, text=True, check=True)
    return json.loads(run.stdout)


def group_hue_tables() -> tuple[dict, dict]:
    """TIER_HUE and FAMILY_HUE from group_tree.py, read without importing it."""
    found = {}
    for node in ast.parse(GROUP_TREE.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id in ("TIER_HUE", "FAMILY_HUE"):
            found[node.target.id] = ast.literal_eval(node.value)
    return found["TIER_HUE"], found["FAMILY_HUE"]


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().replace("'", "").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def group_token_names() -> dict[str, str]:
    """Token name -> hue, for the band and conventional family hues."""
    tier, family = group_hue_tables()
    trailing = {"religion": " religions", "language": " languages", "ethnicity": " ancestry"}
    special = {("language", "Language isolates"): "isolates"}
    out = {}
    for field, bands in tier.items():
        for name, hue in bands.items():
            short = special.get((field, name)) or (name[:-len(trailing[field])] if name.endswith(trailing[field]) else name)
            out[f"{field}-{_slug(short)}"] = hue.lower()
    for field, fams in family.items():
        for name, hue in fams.items():
            if name not in tier.get(field, {}):
                out[f"{field}-{_slug(name)}"] = hue.lower()
    return out


def expected_values(app_css: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """What each sourced token should hold now, per theme; and what was skipped."""
    expect: dict[str, dict[str, str]] = {}
    skipped = []
    css = app_css_values(app_css)
    for name in ("surface-1", "surface-2", "surface-sunken", "ink-primary", "ink-secondary", "ink-muted",
                 "hairline", "axis", "border-ring", "accent", "accent-ink", "status-good", "status-warning",
                 "status-serious", "status-critical", "water", "land-base", "boundary", "shadow",
                 "radius", "radius-sm", "sidebar-w", "filters-w", "topbar-h"):
        expect[name] = {"light": css["light"][name], "dark": css["dark"][name]}
    pal = palette_values()
    if pal is None:
        skipped.append("palette.js (node is not installed)")
    else:
        for theme in ("light", "dark"):
            p = pal[theme]
            for i, hex_ in enumerate(p["categorical"]):
                expect.setdefault(f"categorical-{i + 1}", {})[theme] = hex_
            for i, hex_ in enumerate(p["sequential"]):
                expect.setdefault(f"sequential-{i}", {})[theme] = hex_
            for i, hex_ in enumerate(p["leadingShare"]):
                expect.setdefault(f"leading-share-{i}", {})[theme] = hex_
            expect.setdefault("neutral", {})[theme] = p["neutral"]
            expect.setdefault("unplaced", {})[theme] = p["unplaced"]
            for key in ("not_applicable", "derived", "modelled"):
                expect.setdefault("status-" + key.replace("_", "-"), {})[theme] = p["status"][key]
    for name, hue in group_token_names().items():
        expect[name] = {"light": hue, "dark": hue}
    return expect, skipped


def token_drift(tokens: dict, app_css: str) -> tuple[list[str], list[str]]:
    """Each sourced token whose value no longer matches its source."""
    expect, skipped = expected_values(app_css)
    have = {}
    for family, body in tokens.items():
        if isinstance(body, dict) and "tokens" in body:
            for t in body["tokens"]:
                have[t["name"]] = t["value"]
    problems = []
    for name, want in sorted(expect.items()):
        if name not in have:
            problems.append(f"{name}: in the source, missing from tokens.json ({want['light']})")
            continue
        v = have[name]
        for theme in ("light", "dark"):
            got = v if isinstance(v, str) else v.get(theme, v.get("light"))
            if str(got).lower() != str(want[theme]).lower():
                problems.append(f"{name} [{theme}]: tokens.json has {got}, the source has {want[theme]}")
    return problems, skipped


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 on any drift")
    args = ap.parse_args()

    app_css = APP_CSS.read_text(encoding="utf-8")
    tokens = json.loads(TOKENS_JSON.read_text(encoding="utf-8"))
    try:
        bundle = build_bundle(app_css)
    except Stale as err:
        print(f"bundle.css cannot be rebuilt: {err}. Update REPLACEMENTS in {Path(__file__).name}.")
        return 1
    generated = {BUNDLE_CSS: bundle, TOKENS_CSS: build_tokens_css(tokens)}

    stale = [p for p, text in generated.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    drift, skipped = token_drift(tokens, app_css)
    for note in skipped:
        print(f"not checked: {note}")

    if args.check:
        for path in stale:
            print(f"stale: {path.relative_to(ROOT)} (run scripts/build_design_system.py)")
        for line in drift:
            print(f"drift: {line}")
        if stale or drift:
            return 1
        print("design-system/ matches the site")
        return 0

    for path in stale:
        path.write_text(generated[path], encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    if not stale:
        print("both generated files were already current")
    for line in drift:
        print(f"drift: {line}")
    if drift:
        print("Update those values in design-system/tokens.json, read the usage note beside each, then rebuild.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
