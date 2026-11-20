""""Save to session" of the DFG page: the model or the log, projected or as displayed (Nina, 2026-11-16/19).

- **Model**: Ocelescope's `DirectlyFollowsGraph` resource (`dfg_resource`) of the arcs the page sends: projected = the
  graph with Arcs (display) at "all" and no arcs removed by hand (Stay connected as set); displayed = the arcs as drawn.
- **Log**: a new OCEL with the events of the included traces (`kept_event_ids`; after the event categories, the
  activity projection and the variant filter), cut from the log by `filtered_log`; displayed = also without the events
  of activities that are not drawn. An event log has no arcs, so arcs hidden between two drawn activities stay in it.

Example (pallet example of the module note, defaults): the included traces are p1-p8 with PR, PI, PA; the projected
log keeps these 24 events (and the objects related to them); the model has the 4 arcs ▶→PR, PR→PI, PI→PA, PA→■.
"""

from __future__ import annotations

import tempfile
from collections.abc import Collection, Sequence
from pathlib import Path

import polars as pl
from ocelescope import OCEL
from ocelescope.ocel.constants.pm4py import EID_COL
from ocelescope.ocel.constants.tables import EVENTS_TABLE
from ocelescope.ocel.filter.base import BaseFilter, Step
from ocelescope.resource.default.dfg import DFGActivity, DFGEdge, DFGObject
from ocelescope.resource.default.dfg import DirectlyFollowsGraph as DfgResource
from ocelescope.util.sql import ident, literal

from ..derivation import columns as c
from .graph import DfgArc


def dfg_resource(arcs: Sequence[DfgArc]) -> DfgResource:
    """Ocelescope's DFG resource of the given arcs.

    Activities: every activity at an end of an arc, in order of appearance; object types: every type with an arc, in
    order of appearance. Each arc becomes an edge with `count` = traversals and `object_count` = distinct objects
    (None as source / target = the type's start / end node, as in Ocelescope).

    Args:
        arcs: The arcs (e.g. as drawn on the page).

    Returns:
        DfgResource: The resource, shown in Ocelescope like a discovered DFG.
    """
    activities = dict.fromkeys(x for a in arcs for x in (a.source, a.target) if x is not None)
    types = dict.fromkeys(a.object_type for a in arcs)
    return DfgResource(
        activities=[DFGActivity(name=a) for a in activities],
        object_types=[DFGObject(name=t) for t in types],
        edges=[
            DFGEdge(object_type=a.object_type, source=a.source, target=a.target, count=a.count, object_count=a.objects)
            for a in arcs
        ],
    )


def kept_event_ids(kept: pl.DataFrame, activities: Collection[str] | None = None) -> pl.Series:
    """The events of the included traces, optionally only those of the given activities.

    Args:
        kept: The included traces (`graph.IncludedTraces.kept`).
        activities: Keep only events of these activities (e.g. the drawn ones); None = all.

    Returns:
        pl.Series: Distinct event ids, sorted.
    """
    if activities is not None:
        kept = kept.filter(pl.col(c.ACTIVITY).is_in(list(activities)))
    return kept[c.EVENT].unique().sort()


class EventIdFilter(BaseFilter):
    """Keep the events whose ids are listed in a Parquet file (one column `ocel:eid`).

    The ids come as a file rather than a list in the query, so that a large selection (hundreds of thousands of
    events) stays one join in DuckDB.
    """

    path: str

    def build(self, step: Step) -> None:
        """Narrow the events to the listed ids."""
        step.keep(EVENTS_TABLE, f"SELECT {ident(EID_COL)} FROM read_parquet({literal(self.path)})")


def filtered_log(ocel: OCEL, event_ids: pl.Series) -> OCEL:
    """A new OCEL with only the given events of `ocel`; Ocelescope's filter engine then drops the relations to other
    events and the objects left in no relation (`OCEL.filter`).

    Args:
        ocel: The log.
        event_ids: The events to keep.

    Returns:
        OCEL: The new log (in memory; `session.add_ocel` stores it).
    """
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "events.parquet"
        pl.DataFrame({EID_COL: event_ids.cast(pl.String)}).write_parquet(path)
        return ocel.filter([EventIdFilter(path=str(path))])
