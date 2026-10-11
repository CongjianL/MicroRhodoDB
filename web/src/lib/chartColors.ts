/** Chart colours (colour-blind-safe; every chart also has a data table, so colour never carries meaning alone). */
export const GROUP_COLOR = { member: "#1b7f4b", candidate: "#3b4fb8", boundary: "#6b3fb0", outgroup: "#526175", rejected: "#b42318" } as const;
export const EV_COLOR = { E1: "#0f4f91", E2: "#1665b5", E3: "#4a8fd6", E4: "#6b7f96", E5: "#a5b3c2" } as const;
/* Okabe-Ito based categorical palette. */
export const CATEGORICAL = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#8a7a00", "#5f4b8b", "#2f6b5e", "#7a5230", "#3d5a80", "#9c4f6e"];
export const MISSING_COLOR = "#a5b3c2";
export const OTHER_COLOR = "#7d8b99";
export const cat = (i: number) => CATEGORICAL[i % CATEGORICAL.length];
