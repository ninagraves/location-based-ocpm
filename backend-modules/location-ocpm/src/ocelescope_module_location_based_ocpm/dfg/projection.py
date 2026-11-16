"""Step 1b: the activity selection per object type, applied to the traces first (projection; Nina, 2026-11-15).

For every selected object type the user selects the activities to keep. Default: the `DEFAULT_ACTIVITY_SHARE`
= 40 % most frequent activities of the type (by events of its considered objects; the number of activities
rounded up), but at least `MIN_ACTIVITIES` = 3 and at most `MAX_ACTIVITIES` = 10 (all if the type has fewer).
Before anything else, the events of
deselected activities are removed from the traces of that type: a trace <a, b, c> with b deselected becomes
<a, c>. Paths, arcs and frequencies are then computed on the projected traces, as in Ocelescope's DFG discovery
(`ocelescope.discovery.algorithms.dfg_miner`, which removes the events of excluded activities before the
directly-follows relations). An object whose projected trace is empty has no path and is left out.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

import polars as pl

from ..derivation import columns as c
from . import columns as d
from .traces import FrameLike, considered_objects

#: Share (percent) of a type's activities that is preselected, most frequent first (Nina, 2026-11-15).
DEFAULT_ACTIVITY_SHARE = 40
#: Minimum number of preselected activities per object type.
MIN_ACTIVITIES = 3
#: Maximum number of preselected activities per object type.
MAX_ACTIVITIES = 10
#: Column: time of the first event of an activity (for the order of equally frequent activities).
FIRST_TIME = "first_time"


def type_activity_counts(
    e2o: FrameLike, events: FrameLike, objects: FrameLike, handling_units: Collection[str] | None = None
) -> pl.DataFrame:
    """Events per object type and activity, counting only the considered objects of each type.

    Args:
        e2o: Event-to-object relations, columns event and object.
        events: Events, columns event, time and activity.
        objects: All objects, columns object and object_type.
        handling_units: The handling units HU; a type with handling units counts only events of its handling
            units (`traces.considered_objects`); None = all objects.

    Returns:
        pl.DataFrame: Columns object_type, activity, events (distinct events with at least one considered object
        of the type), first_time; sorted by object type, most events first, then first occurrence, then activity.
    """
    types = objects.lazy().select(c.OBJECT_TYPE).unique().collect()[c.OBJECT_TYPE].to_list()
    considered = considered_objects(objects, types, handling_units)
    return (
        e2o.lazy()
        .select(c.EVENT, d.OBJECT)
        .join(considered, on=d.OBJECT)
        .join(events.lazy().select(c.EVENT, c.TIME, c.ACTIVITY), on=c.EVENT)
        .group_by(c.OBJECT_TYPE, c.ACTIVITY)
        .agg(pl.col(c.EVENT).n_unique().alias(d.EVENTS), pl.col(c.TIME).min().alias(FIRST_TIME))
        .sort([c.OBJECT_TYPE, d.EVENTS, FIRST_TIME, c.ACTIVITY], descending=[False, True, False, False])
        .collect()
    )


def handling_unit_event_counts(e2o: FrameLike, events: FrameLike, handling_units: Collection[str]) -> dict[str, int]:
    """Events per activity that involve at least one handling unit (the frequency shown in the activity list).

    Args:
        e2o: Event-to-object relations, columns event and object.
        events: Events, columns event and activity.
        handling_units: The handling units HU.

    Returns:
        dict[str, int]: Activity -> number of its events with at least one handling unit.
    """
    counts = (
        e2o.lazy()
        .filter(pl.col(d.OBJECT).is_in(list(handling_units)))
        .select(c.EVENT)
        .unique()
        .join(events.lazy().select(c.EVENT, c.ACTIVITY), on=c.EVENT)
        .group_by(c.ACTIVITY)
        .agg(pl.len().alias(d.EVENTS))
        .collect()
    )
    return dict(zip(counts[c.ACTIVITY], counts[d.EVENTS], strict=True))


def default_activity_count(n_activities: int) -> int:
    """Number of preselected activities of a type with `n_activities` activities.

    Args:
        n_activities: Number of activities with events of the type's considered objects.

    Returns:
        int: ceil(40 % of them), but at least 3 and at most 10, and never more than there are.
        Example: 4 activities -> ceil(1.6) = 2 -> 3; 12 -> ceil(4.8) = 5; 30 -> 12 -> 10; 2 -> 2.
    """
    n = -(-n_activities * DEFAULT_ACTIVITY_SHARE // 100)
    return min(n_activities, max(MIN_ACTIVITIES, min(MAX_ACTIVITIES, n)))


def default_activities(
    counts: pl.DataFrame, object_types: Collection[str], shared_from: Collection[str] = ()
) -> dict[str, list[str]]:
    """The preselected activities of each object type: its most frequent ones (`default_activity_count`), plus every
    activity preselected for a type of `shared_from` that the type has events of (Nina, 2026-11-16: an activity
    preselected for one handling-unit type is preselected for all; this may exceed `MAX_ACTIVITIES`).
    Example: coil's own default PR, PI, PA, slab's LO, SH, PA: with both in `shared_from`, coil also gets LO and SH if
    coils take part in them.

    Args:
        counts: `type_activity_counts` (sorted: most events first, ties by first occurrence, then name).
        object_types: The object types to preselect for.
        shared_from: The types whose own defaults are shared with all (e.g. the selected handling-unit types).

    Returns:
        dict[str, list[str]]: Object type -> preselected activities, in the type's frequency order.
    """
    wanted = set(object_types) | set(shared_from)
    ranked: dict[str, list[str]] = {t: [] for t in wanted}
    for object_type, activity in (
        counts.filter(pl.col(c.OBJECT_TYPE).is_in(list(wanted))).select(c.OBJECT_TYPE, c.ACTIVITY).iter_rows()
    ):
        ranked[object_type].append(activity)
    own = {t: a[: default_activity_count(len(a))] for t, a in ranked.items()}
    shared = {a for t in shared_from for a in own[t]}
    return {t: [a for a in ranked[t] if a in set(own[t]) or a in shared] for t in object_types}


def project_traces(traces: pl.DataFrame, included: Mapping[str, Collection[str]]) -> pl.DataFrame:
    """Remove the events of deselected activities from the traces (projection), per object type.

    Args:
        traces: Object traces (`traces.object_traces`), sorted by object and position.
        included: Object type -> activities to keep; a type that is missing keeps all its activities.

    Returns:
        pl.DataFrame: The kept rows, same columns and order, with `position` renumbered from 1 per object.
    """
    if not included:
        return traces
    pairs = pl.DataFrame(
        [(t, a) for t, activities in included.items() for a in activities],
        schema={c.OBJECT_TYPE: pl.String, c.ACTIVITY: pl.String},
        orient="row",
    )
    restricted = pl.col(c.OBJECT_TYPE).is_in(list(included))
    kept = pl.concat(
        [
            traces.filter(~restricted),
            traces.filter(restricted).join(pairs, on=[c.OBJECT_TYPE, c.ACTIVITY], how="semi"),
        ]
    )
    return (
        kept.sort(d.OBJECT, d.POSITION)
        .with_columns(pl.int_range(1, pl.len() + 1, dtype=pl.UInt32).over(d.OBJECT).alias(d.POSITION))
        .select(traces.columns)
    )
