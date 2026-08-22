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
 * The choropleth deliberately has no "dominant group" categorical mode. Colour-
 * vision-safe separation across all pairs of an eight-hue set is not achievable,
 * and a map has no room for the direct labels that rescue the sidebar charts.
 * The equivalent question is answered by faceting instead: pick a single group
 * and read its share as a sequential ramp.
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

  function ramp() { return SEQUENTIAL[mode()].slice(); }
  function neutral() { return NEUTRAL[mode()]; }
  function status(name) { return STATUS[name] || STATUS.not_available; }

  return { categorical, sequential, ramp, neutral, status, mode, STATUS,
           MAX_CATEGORIES: CATEGORICAL.light.length };
})();
