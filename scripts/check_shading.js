/* Does a darker shape always mean more of the group?
 *
 * The map encodes one number in two channels: hue says which group leads,
 * darkness says what share it has. That only works if darkness means the same
 * thing everywhere on the map, and twice it did not.
 *
 * The first version cut the ramp in HSL lightness, which is not what the eye
 * reads as darkness: a county 80% gold came out lighter than one 50% red, so
 * comparing two differently-coloured places gave the wrong answer. The second
 * ran the band the other way in dark mode, on the usual dark-interface
 * reasoning that more should glow brighter -- which silently inverted the
 * whole map for every reader whose browser was in dark mode.
 *
 * Both are the kind of bug that looks fine in a screenshot of one country, so
 * they are checked here instead of looked at:
 *
 *   1. within one hue, luminance falls as the share rises, in both themes;
 *   2. across hues, equal shares land at equal luminance, so no unit is ever
 *      drawn darker than another that holds a larger share.
 *
 *     node scripts/check_shading.js
 */
"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

/** Load palette.js against a stub window fixed to one theme. */
function paletteIn(theme) {
  const sandbox = {
    window: {},
    document: { documentElement: { getAttribute: () => theme } },
  };
  sandbox.window.matchMedia = () => ({ matches: theme === "dark" });
  const src = fs.readFileSync(path.join(ROOT, "site/js/palette.js"), "utf8");
  // eslint-disable-next-line no-new-func
  new Function("window", "document", src)(sandbox.window, sandbox.document);
  return sandbox.window.Palette;
}

function luminance(hex) {
  const c = hex.replace("#", "");
  const part = [0, 2, 4].map((i) => {
    const v = parseInt(c.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * part[0] + 0.7152 * part[1] + 0.0722 * part[2];
}

// Every tier-1 and family hue the shipped index actually uses, so the check
// covers the colours on the real map rather than a chosen handful.
function shippedHues() {
  const file = path.join(ROOT, "site/data/groups.json");
  if (!fs.existsSync(file)) return ["#2a6fb0", "#1e8449", "#b7950b", "#ee6900"];
  const index = JSON.parse(fs.readFileSync(file, "utf8"));
  const hues = new Set();
  for (const field of ["religion", "language", "ethnicity"]) {
    for (const group of (index[field] || {}).groups || []) {
      if (group.hue) hues.add(group.hue);
    }
  }
  return Array.from(hues);
}

// How far apart two luminances may sit before a reader could misread which
// shape is darker.
//
// The floor here is the colour space, not the code: one step of an 8-bit
// channel near the pale end of the ramp is worth about 0.009 of luminance, so
// two colours agreeing to better than a couple of steps is the closest any
// hex value can come. Measured spread across the 128 hues the index ships is
// about 0.012 -- roughly one step. Anything materially larger is a real
// design fault and is what this catches.
const SLACK = 0.02;

function main() {
  const hues = shippedHues();
  const shares = [25, 35, 45, 55, 65, 75, 85, 95, 100];
  let failures = 0;

  for (const theme of ["light", "dark"]) {
    const P = paletteIn(theme);

    for (const hex of hues) {
      let last = Infinity;
      for (const share of shares) {
        const here = luminance(P.group(hex, share));
        if (here > last + 1e-6) {
          console.log(`${theme}: ${hex} gets LIGHTER from ${share}% ` +
                      `(${here.toFixed(3)} vs ${last.toFixed(3)})`);
          failures += 1;
        }
        last = here;
      }
    }

    for (const share of shares) {
      const band = hues.map((hex) => luminance(P.group(hex, share)));
      const low = Math.min(...band);
      const high = Math.max(...band);
      if (high - low > SLACK) {
        console.log(`${theme}: at ${share}% share, luminance spans ` +
                    `${low.toFixed(3)}..${high.toFixed(3)} across ${hues.length} hues`);
        failures += 1;
      }
    }

    // The encoding must point the same way in both themes: what a shade means
    // is a property of the data, not of the surrounding furniture.
    const pale = luminance(P.group(hues[0], 25));
    const deep = luminance(P.group(hues[0], 100));
    if (!(deep < pale)) {
      console.log(`${theme}: the ramp does not run pale to dark`);
      failures += 1;
    }
    console.log(`${theme}: ${hues.length} hues, ramp ${pale.toFixed(3)} -> ${deep.toFixed(3)}`);
  }

  console.log(failures ? `${failures} shading problems` : "shading is monotone and hue-independent in both themes");
  return failures ? 1 : 0;
}

process.exit(main());
