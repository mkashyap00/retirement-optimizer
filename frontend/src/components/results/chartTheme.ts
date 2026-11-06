/**
 * Shared Recharts styling for the private-banker palette.
 *
 * Recharts fills/strokes cannot read CSS custom properties reliably, so the
 * palette values are mirrored here as literals derived from globals.css
 * (emerald / gold / cream). Keep these in sync with the tokens there.
 */

// Series colors — emerald and gold family, with a muted clay for "cost" series.
export const SERIES = {
  emerald: "#064e3b", // --primary
  emeraldMid: "#0d7a5f", // --secondary
  teal: "#0d9488", // bright accent green (distinct from the two emeralds)
  gold: "#b9942f", // --accent, slightly deepened for line/bar strokes
  goldSoft: "#c9a84c",
  clay: "#b4552d", // ordinary-cost / penalty series
} as const;

// Area fills — lighter tints so stacked areas stay legible on cream.
export const FILL = {
  gold: "#ecd9a3",
  emerald: "#8fb9ab",
  teal: "#9fe0d4",
} as const;

// Chart chrome (grid, axes, tooltip) tuned to the cream background.
export const GRID_STROKE = "#ded7c2"; // warm neutral, ~ --border
export const AXIS_TICK = { fill: "#5f7169", fontSize: 12 }; // ~ --muted-foreground
export const AXIS_LINE = { stroke: "#ded7c2" };

export const TOOLTIP_STYLE = {
  contentStyle: {
    backgroundColor: "#faf7ee", // --card
    border: "1px solid #ded7c2",
    borderRadius: 8,
    boxShadow: "0 2px 8px 0 rgba(20, 43, 36, 0.10)",
    fontSize: 13,
  },
  labelStyle: { color: "#0a3d2e", fontWeight: 600 },
} as const;

// Milestone markers (salary ends, Social Security starts, RMDs begin).
export const MILESTONE_STROKE = "#5f7169";
