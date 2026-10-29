# %% [markdown]
# # Trace figure on the running example
# Draft for the visit conceptualisation (`overview/Single Level Visit Mappings.md`).
# Runs as a script or cell by cell (`# %%` cells, e.g. in VS Code or Jupytext):
#
#     uv run python notebooks/trace_figure.py [output folder]
#
# Writes `trace-figure-*.html` into the output folder (default: `notebooks/output/`, not committed).

# %%
import sys
from pathlib import Path

import polars as pl
from ocelescope import OCEL
from ocelescope_module_location_based_ocpm.derivation.config import (
    Activities,
    DerivationConfig,
    LocationAttribute,
    ObjectTypes,
)
from ocelescope_module_location_based_ocpm.derivation.pipeline import derive
from ocelescope_module_location_based_ocpm.visits.trace_figure import (
    relations_for_figure,
    trace_figure,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = (
    Path(sys.argv[1])
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-")
    else ROOT / "notebooks" / "output"
)
OUT.mkdir(parents=True, exist_ok=True)

# %% Running example at Level 3 (the configuration of data/running_example/README.md)
ocel = OCEL.read(ROOT / "data" / "running_example" / "running_example.sqlite")
config = DerivationConfig(
    handling_units=ObjectTypes(object_types=["slab", "coil"]),
    movement_events=Activities(activities=["crane move", "load truck", "unload truck"]),
    transformation_events=Activities(activities=["cast slab", "roll", "cut"]),
    target_locations=LocationAttribute(attribute="to_loc"),
    pickup_locations=LocationAttribute(attribute="from_loc"),
)
derivation = derive(ocel, config)

# %% Suggested additions to the example (claude_notes/review-1-visits.md, section 3); T is not mapped (identity)
AGG = {"A1": "A", "A2": "A", "B1": "B"}
VEHICLES = {"T"}
STORAGE_UNITS = {"B1"}
HUS = ["s1", "c1", "c2", "c3", "c4", "c5"]

# %% Illustration only: the maximal visits at κ = 2 as listed in the review (hand-written, not computed)
VISITS_K2 = pl.DataFrame(
    [
        ("s1", "A", "e1", "e3"),
        ("c1", "A", "e3", "e11"),
        ("c1", "B", "e7", "e7"),
        ("c1", "T", "e8", "e14"),
        ("c2", "A", "e3", "e11"),
        ("c2", "T", "e8", "e8"),
        ("c2", "B", "e12", "e15"),
        ("c3", "T", "e8", "e8"),
        ("c3", "B", "e10", "e14"),
        ("c4", "B", "e15", "e16"),
    ],
    schema=["hu", "high_level", "first_event", "last_event"],
    orient="row",
).with_columns(pl.lit("maximal").alias("group"))

# %% Figures: all axes with the default high-level style, and all high-level styles on the event order axis
for axis in ("event order", "trace position", "time"):
    relations = relations_for_figure(
        derivation, HUS, AGG, VEHICLES, STORAGE_UNITS, axis=axis
    )
    name = axis.replace(" ", "-")
    trace_figure(relations, title=f"Running example, Level 3, x = {axis}").write_html(
        OUT / f"trace-figure-{name}.html", include_plotlyjs="cdn"
    )
    trace_figure(
        relations,
        VISITS_K2,
        title=f"Running example, Level 3, maximal visits at κ = 2 (illustration), x = {axis}",
    ).write_html(OUT / f"trace-figure-visits-{name}.html", include_plotlyjs="cdn")
relations = relations_for_figure(derivation, HUS, AGG, VEHICLES, STORAGE_UNITS)
for style in ("squares", "ribbon", "shading", "outline"):
    trace_figure(
        relations,
        VISITS_K2,
        high_level_style=style,
        title=f"High-level style '{style}': maximal visits at κ = 2 (illustration)",
    ).write_html(OUT / f"trace-figure-style-{style}.html", include_plotlyjs="cdn")
print(f"Written to {OUT}")
