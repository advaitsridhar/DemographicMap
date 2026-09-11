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
  /* A group the classification does not place yet.
   *
   * It has to be a colour and not the neutral, because the neutral means the
   * map has no figure here and this unit has one: a census counted these
   * people and named them, and the only thing missing is the tree's opinion
   * about which family the name belongs to. Drawn in the neutral, that read
   * as a data gap -- the one confusion this project can least afford, since a
   * gap is supposed to be the honest signal that nobody has asked.
   *
   * It is deliberately outside the family palettes, which run warm through
   * the ancestries and saturated through the language families: a violet-grey
   * belongs to no family, so it cannot be mistaken for one.
   */
  const UNPLACED = { light: "#a48fbb", dark: "#6b5980" };

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

  /* A group's colour at a given share.
   *
   * Hue stays the group's; lightness carries the magnitude, and it has to go
   * genuinely dark at the top or the encoding inverts. The first version ran
   * lightness from 0.82 down to 0.38 while pushing saturation up to 0.95,
   * which for a dark base hue produced a *lighter* colour the larger the
   * share: Saudi Arabia at 90% Arab came out #d1ab0e against a base #b7950b.
   * The band now ends below every base hue's own lightness, and saturation
   * barely moves, so "darker" means "more" for every hue in the table.
   *
   * Below `floor` every share is drawn at the palest step rather than fading
   * out, because a plurality of 26% is a fact about the place and not a
   * near-absence. Dark mode runs the band the other way: there, more of a
   * group means a brighter shape against a dark ground.
   */
  function group(hex, share, floor) {
    if (!hex) return NEUTRAL[mode()];
    const [h, s] = hexToHsl(hex);
    // The floor is 25 for the most-populous-group map, where nothing can lead
    // with less, and 0 for a single group's share, where 3% is a real answer
    // that must not be drawn as the same near-white as 0%.
    const base = Number.isFinite(floor) ? floor : SHARE_FLOOR;
    const t = Math.max(0, Math.min(1,
      ((Number.isFinite(share) ? share : 100) - base) / Math.max(1, 100 - base)));
    const dark = mode() === "dark";
    // Light mode: 0.88 (a tint) down to 0.22 (a deep shade).
    // Dark mode: 0.30 (barely off the ground) up to 0.72 (a bright fill).
    const light = dark ? 0.30 + t * 0.42 : 0.88 - t * 0.66;
    const grey = s < 0.02;
    const sat = grey ? 0 : Math.max(0.3, Math.min(0.9, s * (0.85 + t * 0.3)));
    return hslToHex(h, sat, light);
  }

  /** The steps of one group's share ramp, palest first, for a legend. */
  function groupRamp(hex, steps, floor) {
    const n = steps || 5;
    const base = Number.isFinite(floor) ? floor : SHARE_FLOOR;
    return Array.from({ length: n },
      (_, i) => group(hex, base + (i / (n - 1)) * (100 - base), base));
  }

  function ramp() { return SEQUENTIAL[mode()].slice(); }
  function neutral() { return NEUTRAL[mode()]; }
  function unplaced() { return UNPLACED[mode()]; }
  function status(name) { return STATUS[name] || STATUS.not_available; }

  return { categorical, sequential, ramp, neutral, unplaced, status, mode, STATUS,
           group, groupRamp, SHARE_FLOOR,
           MAX_CATEGORIES: CATEGORICAL.light.length };
})();
