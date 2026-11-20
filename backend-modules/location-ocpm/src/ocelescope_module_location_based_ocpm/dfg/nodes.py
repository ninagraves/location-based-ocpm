"""Step 4: the activity nodes of the graph, with their frequency and the object types involved.

Shown activities: every activity that is the source or target of a kept arc.
Frequency of an activity $a$: the number of events $e$ with $act(e) = a$ in the traces of the kept objects
(objects of a selected type whose path is kept), i.e. the events of $a$ that involve at least one of them.
Object types involved: for every object type $ot$ (selected or not), the number of these events that involve
at least one object of $ot$, and the number of distinct objects of $ot$ in them. The page draws the
types that are not selected as circles on the node.
"""

from __future__ import annotations

from collections.abc import Collection

import polars as pl

from ..derivation import columns as c
from . import columns as d
from .traces import FrameLike


def shown_activities(arcs: pl.DataFrame) -> list[str]:
    """The activities that are the source or target of at least one of the given arcs, sorted.

    Args:
        arcs: Kept arcs (`arcs.arc_filter`).

    Returns:
        list[str]: Activity names.
    """
    names = pl.concat([arcs[d.SOURCE], arcs[d.TARGET]]).drop_nulls().unique()
    return sorted(names.to_list())


def activity_frequencies(traces: pl.DataFrame, activities: Collection[str]) -> pl.DataFrame:
    """Number of events per activity in the given traces.

    Args:
        traces: Traces of the kept objects (`variants.path_filter`).
        activities: The shown activities.

    Returns:
        pl.DataFrame: Columns activity, events; one row per activity in `activities` that occurs in the traces.
    """
    return (
        traces.filter(pl.col(c.ACTIVITY).is_in(list(activities)))
        .group_by(c.ACTIVITY)
        .agg(pl.col(c.EVENT).n_unique().alias(d.EVENTS))
        .sort(c.ACTIVITY)
    )


def involved_object_types(traces: pl.DataFrame, activities: Collection[str], typed_e2o: FrameLike) -> pl.DataFrame:
    """Per shown activity and object type: events (of the activity's counted events) and distinct objects.

    Args:
        traces: Traces of the kept objects (`variants.path_filter`); their events are the counted events.
        activities: The shown activities.
        typed_e2o: All event-to-object relations with columns event, object, object_type (any object type).

    Returns:
        pl.DataFrame: Columns activity, object_type, events, objects; sorted by activity, events descending,
        object type.
    """
    counted = traces.lazy().filter(pl.col(c.ACTIVITY).is_in(list(activities))).select(c.EVENT, c.ACTIVITY).unique()
    return (
        typed_e2o.lazy()
        .select(c.EVENT, d.OBJECT, c.OBJECT_TYPE)
        .join(counted, on=c.EVENT)
        .group_by(c.ACTIVITY, c.OBJECT_TYPE)
        .agg(pl.col(c.EVENT).n_unique().alias(d.EVENTS), pl.col(d.OBJECT).n_unique().alias(d.OBJECTS))
        .sort([c.ACTIVITY, d.EVENTS, c.OBJECT_TYPE], descending=[False, True, False])
        .collect()
    )
