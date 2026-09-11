/* Colour tokens for every visual channel on the page.
 *
 * Three separate palettes, because they answer three different questions:
 *
 *   CATEGORICAL  identity  — which religion / language / ethnic group is this?
 *                Fixed slot order, never cycled. Used only where every mark
 *                also carries a text label (the composition bars and lists),
 *                which is what keeps eight slots legible.
 *   SEQUENTIAL   magnitude — how large is this number? One hue, light to dark.
 *                Used for every numeric choropleth.
 *   STATUS       state     — is this datum present, missing, or never collected?
 *                Reserved colours, always shipped with an icon and a label so
 *                the meaning never rests on hue alone.
 *
 * GROUP        identity + magnitude — which group is largest here, and by how
 *               much? Hue comes from the group's own place in the tree, so
 *               Islam is one green everywhere on the map and Catholicism and
 *               Protestantism are two traditions of one religion rather than
 *               two unrelated colours. Lightness carries the share: a province
 *               that is 95% Buddhist is the deep end of the Buddhist hue and
 *               one that is 30% Buddhist is the pale end.
 *
 * The group mode was ruled out here once, on the grounds that colour-vision-safe
 * separation across an eight-hue set is not achievable and a map has no room for
 * the direct labels that rescue the sidebar charts. Both halves have since been
 * answered rather than waived. The hues are drawn from the group tree, which
 * keeps the count at the top of each field in single figures and makes the
 * confusable pairs relatives rather than strangers -- mistaking Sunni for Shia
 * costs a reader far less than mistaking Islam for Buddhism. And the map does
 * have room for a label: every unit names its group and share on hover, the
 * legend names each colour in the order it leads the most units, and the panel
 * names it a third time on selection. Hue is never the only channel.
 */
window.Palette = (function () {
  "use strict";

  const CATEGORICAL = {
    light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
            "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    dark:  ["#3987e5", "#d95926", "#199e70", "#c98500",
            "#d55181", "#008300", "#9085e9", "#e66767"],
  };

  // Blue ramp, 100 -> 700. The lightest steps are only used for sequential
  // encoding, where "nearly the surface colour" correctly means "nearly zero".
  const SEQUENTIAL = {
    light: ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
            "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95"],
    dark:  ["#0d366b", "#104281", "#184f95", "#1c5cab", "#256abf",
            "#2a78d6", "#3987e5", "#5598e7", "#6da7ec", "#86b6ef", "#9ec5f4"],
  };

  const STATUS = {
    present:       { color: "#0ca30c", icon: "●", label: "Recorded" },
    not_available: { color: "#fab219", icon: "▲", label: "Not yet available" },
    not_collected: { color: "#ec835a", icon: "◼", label: "Not collected" },
    not_applicable:{ color: "#898781", icon: "–", label: "Not applicable" },
  };

  const NEUTRAL = { light: "#d8d6ce", dark: "#33332f" };

  function mode() {
    const stamped = document.documentElement.getAttribute("data-theme");
    if (stamped === "dark" || stamped === "light") return stamped;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  /** Categorical hue for slot `i`. Slots past the eighth mean the caller should
   *  have folded the tail into "Other" — we return the neutral so a bug shows up
   *  as grey rather than as a fabricated ninth identity. */
  function categorical(i) {
    const set = CATEGORICAL[mode()];
    return i < set.length ? set[i] : NEUTRAL[mode()];
  }

  function sequential(t) {
    const ramp = SEQUENTIAL[mode()];
    if (!Number.isFinite(t)) return NEUTRAL[mode()];
    const clamped = Math.max(0, Math.min(1, t));
    return ramp[Math.round(clamped * (ramp.length - 1))];
  }

  /* ----------------------------------------------------- group colouring */

  function hexToHsl(hex) {
    const n = parseInt(hex.slice(1), 16);
    const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    if (max === min) return [0, 0, l];
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    const h = max === r ? ((g - b) / d + (g < b ? 6 : 0))
            : max === g ? (b - r) / d + 2
            : (r - g) / d + 4;
    return [h / 6, s, l];
  }

  function hslToHex(h, s, l) {
    const f = (n) => {
      const k = (n + h * 12) % 12;
      const a = s * Math.min(l, 1 - l);
      const v = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
      return Math.round(v * 255).toString(16).padStart(2, "0");
    };
    return `#${f(0)}${f(8)}${f(4)}`;
  }

  /* A group's colour at a given share.
   *
   * Hue and saturation are the group's; only lightness moves, so the shade
   * answers "how much" without ever changing the answer to "which". The band
   * is deliberately narrow at the pale end: a unit where the largest group
   * holds 30% is a plural place, not an empty one, and it still has to be
   * clearly its own colour rather than nearly the page.
   *
   * Below `floor` every share is drawn at the palest step rather than fading
   * out, because a plurality of 26% is a fact about the place and not a
   * near-absence. Dark mode runs the band the other way: there, more of a
   * group means a brighter shape against a dark ground.
   */
  const SHARE_FLOOR = 25;

  function group(hex, share) {
    if (!hex) return NEUTRAL[mode()];
    const [h, s] = hexToHsl(hex);
    const t = Math.max(0, Math.min(1,
      ((Number.isFinite(share) ? share : 100) - SHARE_FLOOR) / (100 - SHARE_FLOOR)));
    const dark = mode() === "dark";
    const light = dark ? 0.30 + t * 0.38 : 0.82 - t * 0.44;
    // A grey base stays grey. Floor-ing saturation at 0.25 turned the legend's
    // neutral share ramp -- drawn from a grey so it stands for every group at
    // once -- into a row of pinks, because hue 0 of a colourless input is red.
    const sat = s < 0.02 ? 0
      : Math.max(0.25, Math.min(0.95, s * (dark ? 0.75 + t * 0.35 : 0.55 + t * 0.5)));
    return hslToHex(h, sat, light);
  }

  /** The steps of one group's share ramp, palest first, for a legend. */
  function groupRamp(hex, steps) {
    const n = steps || 5;
    return Array.from({ length: n },
      (_, i) => group(hex, SHARE_FLOOR + (i / (n - 1)) * (100 - SHARE_FLOOR)));
  }

  function ramp() { return SEQUENTIAL[mode()].slice(); }
  function neutral() { return NEUTRAL[mode()]; }
  function status(name) { return STATUS[name] || STATUS.not_available; }

  return { categorical, sequential, ramp, neutral, status, mode, STATUS,
           group, groupRamp, SHARE_FLOOR,
           MAX_CATEGORIES: CATEGORICAL.light.length };
})();
