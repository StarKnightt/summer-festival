/**
 * The town plan. One straight street runs from the upper town (+Z) down to the shore (−Z),
 * lined with two-storey houses; festival stalls stand in front of the houses, paper lanterns
 * are strung overhead, and three lantern gates (the checkpoints) span the street. At the end, a
 * promenade and stone steps lead down to the beach where the fireworks launch over the sea.
 *
 * Left side = −X, right side = +X. Stalls on the left face +X, on the right face −X.
 */
export const STREET = {
  half: 4.6, // house fronts at |x| = 4.6
  walk: 4.2, // walkable |x| on the street itself
  zStart: 12,
  zEnd: -96, // promenade edge
  lanternY: 4.4,
};

export const SHORE = {
  promenadeZ0: -96,
  promenadeZ1: -100,
  stepsZ1: -104, // bottom of the steps
  beachY: -1.6,
  seaY: -2.05,
  waterZ: -122, // where the waterline sits on the beach
  fireworksZ: -105, // walk past this (on the beach) for the finale
};

export type StallKind = "goldfish" | "candyapple" | "shavedice" | "ringtoss" | "masks" | "lantern" | "food_a" | "food_b";
export type TaskId = "goldfish" | "candyapple" | "ringtoss" | "masks" | "lantern";

export interface StallSpot {
  kind: StallKind;
  side: -1 | 1;
  z: number;
  task?: TaskId;
  /** What the keeper calls out. */
  call: string;
}

export const STALLS: StallSpot[] = [
  { kind: "food_a", side: -1, z: -5, call: "Yakisoba, hot off the grill!" },
  { kind: "food_b", side: 1, z: -7, call: "Fresh takoyaki here!" },
  { kind: "goldfish", side: 1, z: -27, task: "goldfish", call: "Goldfish scooping! Try your luck!" },
  { kind: "candyapple", side: -1, z: -31, task: "candyapple", call: "Candy apples, sweet and shiny!" },
  { kind: "shavedice", side: 1, z: -40, call: "Shaved ice, cool you right down!" },
  { kind: "food_a", side: -1, z: -43, call: "Yakisoba! Come get some!" },
  { kind: "ringtoss", side: -1, z: -62, task: "ringtoss", call: "Ring toss! Win a prize!" },
  { kind: "masks", side: 1, z: -65, task: "masks", call: "Masks! Find your favourite!" },
  { kind: "lantern", side: 1, z: -78, task: "lantern", call: "Light a lantern for the night!" },
];

/** Stall footprint centre: stalls sit against the house fronts. */
export const STALL_W = 2.7;
export const STALL_D = 1.7;
export const stallX = (side: number) => side * (STREET.half - STALL_D / 2 - 0.05);

export const GATES = [-16, -52, -88];
export const SPAWNS: { z: number; x: number }[] = [
  { x: 0, z: 8 },
  { x: 0, z: -18 },
  { x: 0, z: -54 },
  { x: 0, z: -90 },
];

export const TASKS: { id: TaskId; label: string }[] = [
  { id: "goldfish", label: "Scoop a goldfish" },
  { id: "candyapple", label: "Buy a candy apple" },
  { id: "ringtoss", label: "Win the ring toss" },
  { id: "masks", label: "Pick a mask" },
  { id: "lantern", label: "Light a lantern" },
];

/** Sleeping cat on a house step (pet it), and three hidden cats to find. */
export const SLEEPING_CAT = { x: -4.15, y: 0.42, z: -76.2, ry: Math.PI / 2 };
export const HIDDEN_CATS = [
  // On the awning edge of the shaved-ice stall, peeking over.
  { id: "awning", x: 3.55, y: 2.62, z: -40.6, ry: -Math.PI / 2, kind: "cat_loaf" as const },
  // In the alley between houses on the left, behind barrels.
  { id: "alley", x: -5.9, y: 0, z: -48.6, ry: Math.PI / 2 + 0.4, kind: "cat_sit" as const },
  // On the sea wall by the steps, watching the water.
  { id: "seawall", x: 6.6, y: 0.62, z: -99.3, ry: Math.PI, kind: "cat_sit" as const },
];
