// The transformation types as a Sankey diagram (Nina 2026-11-24: a switch between the gozinto graph and a Sankey).
// Same data as the gozinto graph (`TypeGraph`: the shown recipes, their arcs and handling units), drawn in three
// columns: input object types → recipes → output object types. An object type that is input and output (e.g. coil
// cut into coil) gets a node on each side, so the diagram has no cycles. Link width = handling units that flowed.
// Recipes without input (production only) get a grey "∅ no input" node on the left, recipes without output
// (consumption only) a grey "∅ no output" node on the right, so every recipe stays in the middle column.
// Documented in docs/pages/transformations.md, section "Transformation type graph".
//
// Example (running example): nodes "slab" and "coil" (inputs), cast slab, cut, roll (recipes), "slab" and "coil"
// (outputs), "∅ no input"; links ∅ → cast slab (1), cast slab → slab (1), slab → roll (1), roll → coil (2),
// coil → cut (1), cut → coil (1).

import type { TypeGraph } from "../api/locationBasedOcpm";
import { num, pct } from "./format";

/** Label of the grey nodes for recipes without input or output. */
export const NO_INPUT = "∅ no input";
export const NO_OUTPUT = "∅ no output";

/** One node of the Sankey: label, colour and hover text. */
export type SankeyNode = { id: string; label: string; colour: string; hover: string };
/** One link: indices of its nodes, handling units, colour and hover text. */
export type SankeyLink = { source: number; target: number; value: number; colour: string; hover: string };

/**
 * Nodes and links of the Sankey of a type graph.
 *
 * @param graph The type graph from the backend (`getTransformationTypeGraph`).
 * @param colours Colour per object type (`useObjectTypeColours`).
 * @param shades Colour per activity for the recipe nodes (e.g. `activityShades` with a stronger alpha).
 * @param grey Colour of the ∅ nodes and links and of object types without a colour.
 * @param showShare Add the share of the transformation events to a recipe's label ("roll · 5× · 25 %"; without:
 *   "roll · 5×").
 * @returns Nodes (input types, recipes, output types, ∅ nodes) and links with handling units as values.
 */
export const typeSankey = (
  graph: TypeGraph,
  colours: Map<string, string>,
  shades: Map<string, string>,
  grey: string,
  showShare: boolean,
): { nodes: SankeyNode[]; links: SankeyLink[] } => {
  const nodes: SankeyNode[] = [];
  const index = new Map<string, number>();
  const node = (id: string, label: string, colour: string, hover: string) => {
    if (!index.has(id)) {
      index.set(id, nodes.length);
      nodes.push({ id, label, colour, hover });
    }
    return index.get(id) as number;
  };
  const types = new Map(graph.object_types.map((t) => [t.object_type, t]));
  const typeNode = (objectType: string, side: "in" | "out") => {
    const t = types.get(objectType);
    const amount = side === "in" ? `${num(t?.consumed ?? 0)} handling units consumed` : `${num(t?.produced ?? 0)} handling units produced`;
    return node(`${side}:${objectType}`, objectType, colours.get(objectType) ?? grey, `${objectType} (${side === "in" ? "input" : "output"}): ${amount} by the shown recipes`);
  };
  const recipes = new Map(graph.recipes.map((r) => [r.id, r]));
  // Recipe nodes first in frequency order, so that Plotly stacks the most frequent recipes on top.
  for (const r of graph.recipes)
    node(
      `recipe:${r.id}`,
      showShare ? `${r.activity} · ${num(r.frequency)}× · ${pct(r.share)}` : `${r.activity} · ${num(r.frequency)}×`,
      shades.get(r.activity) ?? grey,
      `${r.id} · ${r.recipe} · ${num(r.frequency)} events (${pct(r.share, 1)})`,
    );
  const links: SankeyLink[] = [];
  const fade = (colour: string) => (colour.length === 7 ? `${colour}80` : colour);
  for (const a of graph.arcs) {
    const recipe = recipes.get(a.recipe);
    const label = a.quantity_min === a.quantity_max ? num(a.quantity_min) : `${num(a.quantity_min)}–${num(a.quantity_max)}`;
    const hover = `${recipe?.recipe ?? a.recipe}: ${label} ${a.object_type} per event ${a.role}; ${num(a.hus)} handling units over ${num(recipe?.frequency ?? 0)} events`;
    const r = index.get(`recipe:${a.recipe}`) as number;
    const t = typeNode(a.object_type, a.role === "consumed" ? "in" : "out");
    links.push({
      source: a.role === "consumed" ? t : r,
      target: a.role === "consumed" ? r : t,
      value: a.hus,
      colour: fade(colours.get(a.object_type) ?? grey),
      hover,
    });
  }
  // Recipes without input or output: a grey link from "∅ no input" / to "∅ no output", as wide as the other side.
  for (const r of graph.recipes) {
    const arcs = graph.arcs.filter((a) => a.recipe === r.id);
    const consumed = arcs.filter((a) => a.role === "consumed").reduce((s, a) => s + a.hus, 0);
    const produced = arcs.filter((a) => a.role === "produced").reduce((s, a) => s + a.hus, 0);
    const at = index.get(`recipe:${r.id}`) as number;
    if (!consumed && produced)
      links.push({
        source: node("in:∅", NO_INPUT, grey, "Recipes that consume nothing (production only)"),
        target: at,
        value: produced,
        colour: fade(grey),
        hover: `${r.recipe}: consumes nothing`,
      });
    if (consumed && !produced)
      links.push({
        source: at,
        target: node("out:∅", NO_OUTPUT, grey, "Recipes that produce nothing (consumption only)"),
        value: consumed,
        colour: fade(grey),
        hover: `${r.recipe}: produces nothing`,
      });
  }
  return { nodes, links };
};
