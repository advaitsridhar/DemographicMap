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

  /* The relative luminance of a colour, as the WCAG defines it.
   *
   * This is what the eye reads as "how dark is that", and it is not what HSL
   * calls lightness. Yellow and blue at the same HSL lightness differ by more
   * than four times in luminance, which is why driving the ramp with HSL
   * produced a map whose shading meant one thing in India and another in
   * Mongolia.
   */
  function luminance(hex) {
    const c = hex.replace("#", "");
    const part = [0, 2, 4].map((i) => {
      const v = parseInt(c.slice(i, i + 2), 16) / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * part[0] + 0.7152 * part[1] + 0.0722 * part[2];
  }

  /* The colour of this hue that reads as dark as `target` asks.
   *
   * Luminance rises monotonically with HSL lightness for a fixed hue and
   * saturation, so a bisection finds the lightness that hits the target. It
   * is a search rather than a formula because the relationship depends on the
   * hue: to look as dark as a mid blue, a yellow has to go much further down.
   */
  function atLuminance(h, s, target) {
    let low = 0;
    let high = 1;
    let hex = "#000000";
    for (let i = 0; i < 16; i += 1) {
      const mid = (low + high) / 2;
      hex = hslToHex(h, s, mid);
      if (luminance(hex) < target) low = mid; else high = mid;
    }
    return hex;
  }

  /* A group's colour at a given share: hue says which group, darkness says
   * how much of it.
   *
   * Two things were wrong before and both made the map say the opposite of
   * what it meant. The band was cut in HSL lightness, so equal shares landed
   * up to five times apart in luminance -- a county 80% gold rendered lighter
   * than one 50% red, and the reader comparing them read the shading
   * backwards. And dark mode ran the band the other way, on the usual
   * dark-interface reasoning that more should glow brighter, which meant
   * every share on the map was encoded upside down for anyone whose browser
   * was in dark mode.
   *
   * So the ramp is now stated in luminance, the same target for every hue,
   * and it runs pale to dark in BOTH themes. What a shade means is a property
   * of the data and must not change with the colour of the surrounding
   * furniture. The two themes differ only in where the dark end stops, so
   * that a full-share unit stays clearly apart from the land beneath it:
   * light mode can go almost to black, dark mode stops well above its own
   * background.
   *
   * Below `floor` every share is drawn at the palest step rather than fading
   * out, because a plurality of 26% is a fact about the place and not a
   * near-absence.
   */
  const SHARE_FLOOR = 25;
  const BAND = {
    light: { pale: 0.78, deep: 0.055 },
    // Dark mode's land sits at about 0.023, so the deep end stops at roughly
    // five times that: still plainly the dark end of the ramp, still plainly
    // not the empty land under it.
    dark: { pale: 0.70, deep: 0.115 },
  };

  function group(hex, share, floor) {
    if (!hex) return NEUTRAL[mode()];
    const [h, s] = hexToHsl(hex);
    // The floor is 25 for the most-populous-group map, where nothing can lead
    // with less, and 0 for a single group's share, where 3% is a real answer
    // that must not be drawn as the same near-white as 0%.
    const base = Number.isFinite(floor) ? floor : SHARE_FLOOR;
    const t = Math.max(0, Math.min(1,
      ((Number.isFinite(share) ? share : 100) - base) / Math.max(1, 100 - base)));
    const band = BAND[mode()] || BAND.light;
    const target = band.pale + t * (band.deep - band.pale);
    // A grey base stays grey: hue 0 of a colourless input is red, and the
    // legend's neutral ramp stands for every group at once.
    const sat = s < 0.02 ? 0 : Math.max(0.35, Math.min(0.95, s));
    return atLuminance(h, sat, target);
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
