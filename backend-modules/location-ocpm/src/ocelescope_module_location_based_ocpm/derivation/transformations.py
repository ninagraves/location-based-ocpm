"""Transformation events T and the consumed/produced handling units ($cons$, $prod$) from the user's inputs.

Concept: `overview/concepts/Transformations.md` (outside this repo), sections "Assumption" (AS-T1 to AS-T4) and
"Deriving Starting Points" (options 1 to 6). One function per option; each works on plain frames, so it can be
tested without a log. `resolve_transformations` picks the option of the configuration and runs it on the log.

All option functions return the roles as one frame with the columns event, hu and role (`consumed` or
`produced`), the same format as `data/running_example/inputs/transformation_roles.csv` and the input of the
lineage package. A handling unit consumed and produced at the same event has two rows.

First and last events (concept: before the options): among the events at the first (last) timestamp of a hu,
processing operations come first, then the smallest event id (`first_last_events`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from . import columns as c
from .config import (
    DERIVES_TRANSFORMATION_EVENTS,
    ObjectAttributeValues,
    ObjectSetInput,
    RolesFromFirstLast,
    RolesFromFrequency,
    RolesFromObjectSets,
    RolesFromParents,
    RolesFromQualifiers,
    RolesFromTable,
    TransformationRolesInput,
)
from .messages import Notice

#: Role values of the roles frame.
CONSUMED, PRODUCED = "consumed", "produced"
#: Column of the role.
ROLE = "role"
#: Columns of the first and last event of a handling unit.
FIRST_EVENT, LAST_EVENT = "first_event", "last_event"
#: Columns of the parent relations.
CHILD, PARENT = "child", "parent"

_ROLES_SCHEMA = {c.EVENT: pl.String, c.HU: pl.String, ROLE: pl.String}
_EVENTS_SCHEMA = {c.EVENT: pl.String}

#: Number of ids listed in a notice.
MAX_IDS = 50


def empty_roles() -> pl.DataFrame:
    """An empty roles frame (columns event, hu, role)."""
    return pl.DataFrame(schema=_ROLES_SCHEMA)


def _as_roles(frame: pl.DataFrame) -> pl.DataFrame:
    """Cast a frame to the roles schema, drop duplicates and sort it by event, role, hu."""
    return frame.select(c.EVENT, c.HU, ROLE).cast(_ROLES_SCHEMA).unique().sort(c.EVENT, ROLE, c.HU)


@dataclass
class ResolvedTransformations:
    """T and the roles after the AS-T1 filter, plus the reports.

    Attributes:
        events: T as unique event ids (sorted).
        roles: $cons$ and $prod$ of the events in T (columns event, hu, role).
        notices: Reports: dropped events (AS-T1), violations of AS-T2 to AS-T4, ignored inputs.
    """

    events: pl.Series
    roles: pl.DataFrame
    notices: list[Notice] = field(default_factory=list)


def first_last_events(e2hu: pl.DataFrame, processing: pl.Series | None = None) -> pl.DataFrame:
    """The first event $e^{first}(hu)$ and the last event $e^{last}(hu)$ of every handling unit.

    Among the events at the first (last) timestamp of a hu, processing operations come before all other events,
    then the smallest event id ($\\prec$ in the concept).

    Args:
        e2hu: hu-event relations with the columns event, hu and time.
        processing: The processing operations P used for the tie-break; None = none.

    Returns:
        DataFrame with the columns hu, first_event and last_event, one row per hu with at least one event.
    """
    p = processing.cast(pl.String).implode() if processing is not None else pl.Series([], dtype=pl.String).implode()
    ranked = e2hu.select(c.EVENT, c.HU, c.TIME).with_columns((~pl.col(c.EVENT).is_in(p)).alias("_not_p"))
    first = (
        ranked.sort(c.HU, c.TIME, "_not_p", c.EVENT)
        .group_by(c.HU, maintain_order=True)
        .agg(pl.col(c.EVENT).first().alias(FIRST_EVENT))
    )
    last = (
        ranked.sort([c.HU, c.TIME, "_not_p", c.EVENT], descending=[False, True, False, False])
        .group_by(c.HU, maintain_order=True)
        .agg(pl.col(c.EVENT).first().alias(LAST_EVENT))
    )
    return first.join(last, on=c.HU, how="inner").sort(c.HU)


# --- option 1 ------------------------------------------------------------------------------------------------


def roles_from_qualifiers(e2o: pl.DataFrame, handling_units: pl.Series, option: RolesFromQualifiers) -> pl.DataFrame:
    """Option 1: $cons$ and $prod$ from e2o qualifiers; relations to objects that are no handling units are dropped.

    Args:
        e2o: e2o relations with the columns event, hu (the object) and qualifier.
        handling_units: The handling units HU.
        option: The consumed and the produced qualifiers.

    Returns:
        The roles (columns event, hu, role); T are the events in it.
    """
    hus = e2o.filter(pl.col(c.HU).is_in(handling_units.implode()))
    consumed = hus.filter(pl.col("qualifier").is_in(option.consumed_qualifiers)).with_columns(pl.lit(CONSUMED).alias(ROLE))
    produced = hus.filter(pl.col("qualifier").is_in(option.produced_qualifiers)).with_columns(pl.lit(PRODUCED).alias(ROLE))
    return _as_roles(pl.concat([consumed, produced]))


# --- option 2 ------------------------------------------------------------------------------------------------


def roles_from_table(
    table: pl.DataFrame, option: RolesFromTable, events: pl.Series, handling_units: pl.Series
) -> tuple[pl.DataFrame, list[Notice]]:
    """Option 2: $cons$ and $prod$ from a table with one row per (event, handling unit, role).

    Rows with unknown events are dropped and reported, rows with objects that are no handling units are dropped
    silently (concept), rows with a role value that is neither a consumed nor a produced value are reported.

    Args:
        table: The user table.
        option: Column names and the role values.
        events: All event ids of the log.
        handling_units: The handling units HU.

    Returns:
        The roles and the notices.
    """
    rows = table.select(
        pl.col(option.event_column).cast(pl.String).alias(c.EVENT),
        pl.col(option.object_column).cast(pl.String).alias(c.HU),
        pl.col(option.role_column).cast(pl.String).alias("_value"),
    ).drop_nulls()
    notices = []
    unknown = rows.filter(~pl.col(c.EVENT).is_in(events.implode()))
    if unknown.height:
        notices.append(_notice("unknown_ids_dropped", f"Consumed and produced: {unknown.height} table rows refer to events that are not in the log and were dropped.", unknown[c.EVENT]))
    rows = rows.filter(pl.col(c.EVENT).is_in(events.implode()) & pl.col(c.HU).is_in(handling_units.implode()))
    role = (
        pl.when(pl.col("_value").is_in(option.consumed_values)).then(pl.lit(CONSUMED))
        .when(pl.col("_value").is_in(option.produced_values)).then(pl.lit(PRODUCED))
    )
    both = rows.filter(pl.col("_value").is_in(option.consumed_values) & pl.col("_value").is_in(option.produced_values))
    if both.height:
        raise KeyError("Consumed and produced: a role value cannot mean both consumed and produced.")
    rows = rows.with_columns(role.alias(ROLE))
    other = rows.filter(pl.col(ROLE).is_null())
    if other.height:
        notices.append(_notice("other_role_values_ignored", f"Consumed and produced: {other.height} table rows have a role value that means neither consumed nor produced and were ignored.", other[c.EVENT]))
    return _as_roles(rows.filter(pl.col(ROLE).is_not_null())), notices


# --- option 3 ------------------------------------------------------------------------------------------------


def roles_from_parents(
    e2hu: pl.DataFrame, parents: pl.DataFrame, candidates: pl.Series, first_last: pl.DataFrame
) -> pl.DataFrame:
    """Option 3: $cons$ and $prod$ from parent-child relations of the handling units, for the candidate events.

    For every candidate e:
    - a hu whose first event is e is produced, unless it has known parents of which none is involved in e;
      every involved parent is consumed;
    - a hu whose last event is e is consumed if all its children start at or before time(e).

    Args:
        e2hu: hu-event relations with the columns event, hu and time.
        parents: Parent relations with the columns child and parent (both handling units).
        candidates: The transformation events given by the user.
        first_last: First and last events per hu (`first_last_events`).

    Returns:
        The roles (columns event, hu, role).
    """
    involved = e2hu.select(c.EVENT, c.HU).unique()
    times = e2hu.select(c.EVENT, c.TIME).unique(subset=c.EVENT)
    starts = first_last.filter(pl.col(FIRST_EVENT).is_in(candidates.implode())).select(
        pl.col(FIRST_EVENT).alias(c.EVENT), c.HU
    )
    with_parents = starts.join(parents, left_on=c.HU, right_on=CHILD, how="left")
    parent_involved = with_parents.join(
        involved.rename({c.HU: PARENT}).with_columns(pl.lit(True).alias("_in")), on=[c.EVENT, PARENT], how="left"
    ).with_columns(pl.col("_in").fill_null(False))
    produced = (
        parent_involved.group_by(c.EVENT, c.HU)
        .agg((pl.col(PARENT).is_null().all() | pl.col("_in").any()).alias("_keep"))
        .filter("_keep")
        .with_columns(pl.lit(PRODUCED).alias(ROLE))
    )
    consumed_parents = parent_involved.filter("_in").select(c.EVENT, pl.col(PARENT).alias(c.HU)).with_columns(
        pl.lit(CONSUMED).alias(ROLE)
    )
    ends = first_last.filter(pl.col(LAST_EVENT).is_in(candidates.implode())).select(pl.col(LAST_EVENT).alias(c.EVENT), c.HU)
    child_starts = (
        parents.join(first_last.select(c.HU, FIRST_EVENT), left_on=CHILD, right_on=c.HU, how="inner")
        .join(times.rename({c.EVENT: FIRST_EVENT, c.TIME: "_child_start"}), on=FIRST_EVENT, how="left")
        .select(pl.col(PARENT).alias(c.HU), "_child_start")
    )
    consumed_ends = (
        ends.join(times, on=c.EVENT, how="left")
        .join(child_starts, on=c.HU, how="left")
        .group_by(c.EVENT, c.HU)
        .agg((pl.col("_child_start").is_null() | (pl.col("_child_start") <= pl.col(c.TIME))).all().alias("_keep"))
        .filter("_keep")
        .with_columns(pl.lit(CONSUMED).alias(ROLE))
    )
    return _as_roles(pl.concat([produced.select(c.EVENT, c.HU, ROLE), consumed_parents, consumed_ends.select(c.EVENT, c.HU, ROLE)]))


# --- option 4 ------------------------------------------------------------------------------------------------


def roles_from_object_sets(
    e2hu: pl.DataFrame,
    candidates: pl.Series,
    first_last: pl.DataFrame,
    produced: pl.Series,
    consumed: pl.Series,
    consumption: str = "final",
) -> pl.DataFrame:
    """Option 4: $cons$ and $prod$ from the sets of handling units produced ($HU_{prod}$) and consumed ($HU_{cons}$).

    prod(e): the hus of $HU_{prod}$ whose first event is e. cons(e): the hus of $HU_{cons}$ whose last event is e
    (`final`) or that are involved in e (`partial`).

    Args:
        e2hu: hu-event relations with the columns event and hu.
        candidates: The transformation events given by the user.
        first_last: First and last events per hu (`first_last_events`).
        produced: $HU_{prod}$.
        consumed: $HU_{cons}$.
        consumption: `final` or `partial`.

    Returns:
        The roles (columns event, hu, role).
    """
    cand = candidates.implode()
    prod = first_last.filter(pl.col(c.HU).is_in(produced.implode()) & pl.col(FIRST_EVENT).is_in(cand)).select(
        pl.col(FIRST_EVENT).alias(c.EVENT), c.HU, pl.lit(PRODUCED).alias(ROLE)
    )
    if consumption == "final":
        cons = first_last.filter(pl.col(c.HU).is_in(consumed.implode()) & pl.col(LAST_EVENT).is_in(cand)).select(
            pl.col(LAST_EVENT).alias(c.EVENT), c.HU, pl.lit(CONSUMED).alias(ROLE)
        )
    elif consumption == "partial":
        cons = e2hu.filter(pl.col(c.HU).is_in(consumed.implode()) & pl.col(c.EVENT).is_in(cand)).select(
            c.EVENT, c.HU, pl.lit(CONSUMED).alias(ROLE)
        )
    else:
        raise ValueError(f"consumption must be 'final' or 'partial', not {consumption!r}")
    return _as_roles(pl.concat([prod, cons]))


# --- option 5 ------------------------------------------------------------------------------------------------


def roles_from_first_last(candidates: pl.Series, first_last: pl.DataFrame) -> pl.DataFrame:
    """Option 5: prod(e) = the hus whose first event is e, cons(e) = the hus whose last event is e, for e in the candidates.

    Args:
        candidates: The transformation events given by the user.
        first_last: First and last events per hu (`first_last_events`).

    Returns:
        The roles (columns event, hu, role).
    """
    cand = candidates.implode()
    prod = first_last.filter(pl.col(FIRST_EVENT).is_in(cand)).select(pl.col(FIRST_EVENT).alias(c.EVENT), c.HU, pl.lit(PRODUCED).alias(ROLE))
    cons = first_last.filter(pl.col(LAST_EVENT).is_in(cand)).select(pl.col(LAST_EVENT).alias(c.EVENT), c.HU, pl.lit(CONSUMED).alias(ROLE))
    return _as_roles(pl.concat([prod, cons]))


# --- option 6 ------------------------------------------------------------------------------------------------


def activity_frequencies(e2hu: pl.DataFrame, first_last: pl.DataFrame) -> pl.DataFrame:
    """$freq^{ttype}_{hut}(a)$: the share of each activity among the first (prod) and last (cons) events per hu type.

    Args:
        e2hu: hu-event relations with the columns event, hu, object_type and activity.
        first_last: First and last events per hu (`first_last_events`).

    Returns:
        DataFrame with the columns object_type, ttype (`prod`/`cons`), activity, count and frequency.
    """
    activity = e2hu.select(c.EVENT, c.ACTIVITY).unique(subset=c.EVENT)
    types = e2hu.select(c.HU, c.OBJECT_TYPE).unique(subset=c.HU)
    parts = []
    for ttype, column in (("prod", FIRST_EVENT), ("cons", LAST_EVENT)):
        parts.append(
            first_last.select(c.HU, pl.col(column).alias(c.EVENT))
            .join(types, on=c.HU)
            .join(activity, on=c.EVENT)
            .group_by(c.OBJECT_TYPE, c.ACTIVITY)
            .agg(pl.len().alias("count"))
            .with_columns(pl.lit(ttype).alias("ttype"))
        )
    counts = pl.concat(parts)
    return (
        counts.with_columns((pl.col("count") / pl.col("count").sum().over(c.OBJECT_TYPE, "ttype")).alias("frequency"))
        .select(c.OBJECT_TYPE, "ttype", c.ACTIVITY, "count", "frequency")
        .sort(c.OBJECT_TYPE, "ttype", "frequency", c.ACTIVITY, descending=[False, True, True, False])
    )


def roles_from_frequency(e2hu: pl.DataFrame, first_last: pl.DataFrame, threshold: float) -> pl.DataFrame:
    """Option 6: T, $cons$ and $prod$ from the activity frequencies of the first and last events.

    T are the first (last) events of the hus of a type whose activity has a frequency of at least `threshold`
    among the first (last) events of that type; prod(e) (cons(e)) are all hus whose first (last) event is e.

    Args:
        e2hu: hu-event relations with the columns event, hu, object_type and activity.
        first_last: First and last events per hu (`first_last_events`).
        threshold: $\\tau$ in [0, 1].

    Returns:
        The roles (columns event, hu, role); T are the events in it.
    """
    qualifying = activity_frequencies(e2hu, first_last).filter(pl.col("frequency") >= threshold)
    types = e2hu.select(c.HU, c.OBJECT_TYPE).unique(subset=c.HU)
    activity = e2hu.select(c.EVENT, c.ACTIVITY).unique(subset=c.EVENT)
    selected = []
    for ttype, column in (("prod", FIRST_EVENT), ("cons", LAST_EVENT)):
        acts = qualifying.filter(pl.col("ttype") == ttype).select(c.OBJECT_TYPE, c.ACTIVITY)
        selected.append(
            first_last.select(c.HU, pl.col(column).alias(c.EVENT))
            .join(types, on=c.HU)
            .join(activity, on=c.EVENT)
            .join(acts, on=[c.OBJECT_TYPE, c.ACTIVITY], how="semi")
            .select(c.EVENT)
        )
    events = pl.concat(selected).unique()[c.EVENT]
    return roles_from_first_last(events, first_last)


# --- assumptions ---------------------------------------------------------------------------------------------


def _count(n: int, one: str, many: str) -> str:
    """'1 event has' or '2 events have': the number with the singular or plural phrase."""
    return f"{n} {one if n == 1 else many}"


def _notice(code: str, message: str, ids: pl.Series) -> Notice:
    """A notice with the unique ids (at most MAX_IDS)."""
    unique = ids.cast(pl.String).unique(maintain_order=True)
    return Notice(code=code, message=message, count=unique.len(), ids=unique.head(MAX_IDS).to_list())


def apply_as_t1(candidates: pl.Series, roles: pl.DataFrame) -> tuple[pl.Series, pl.DataFrame, list[Notice]]:
    """AS-T1: only events with at least one consumed or produced hu are transformation events.

    Args:
        candidates: The (candidate or derived) transformation events.
        roles: The roles; rows of events outside the candidates are dropped.

    Returns:
        T, the roles of T, and a notice listing the dropped events (if any).
    """
    candidates = candidates.cast(pl.String).unique()
    roles = roles.filter(pl.col(c.EVENT).is_in(candidates.implode()))
    with_roles = roles[c.EVENT].unique()
    dropped = candidates.filter(~candidates.is_in(with_roles.implode())).sort()
    notices = []
    if dropped.len():
        notices.append(_notice("AS-T1", f"Transformation events: {_count(dropped.len(), 'event has', 'events have')} no consumed or produced handling unit (AS-T1); dropped from the transformation events.", dropped))
    return with_roles.sort().alias(c.EVENT), roles, notices


def check_assumptions(e2hu: pl.DataFrame, roles: pl.DataFrame) -> list[Notice]:
    """Report violations of AS-T2, AS-T3 and AS-T4 (non-blocking).

    - AS-T2: a produced hu has an event earlier than the event producing it.
    - AS-T3: a hu consumed by an event that produces nothing occurs in a later event.
    - AS-T4: two transformation events at the same timestamp share a consumed or produced hu.

    Args:
        e2hu: hu-event relations with the columns event, hu and time.
        roles: The roles of T.

    Returns:
        One notice per violated assumption, listing the events concerned.
    """
    times = e2hu.select(c.EVENT, c.TIME).unique(subset=c.EVENT)
    span = e2hu.group_by(c.HU).agg(pl.col(c.TIME).min().alias("_first"), pl.col(c.TIME).max().alias("_last"))
    timed = roles.join(times, on=c.EVENT, how="left").join(span, on=c.HU, how="left")
    notices = []
    t2 = timed.filter((pl.col(ROLE) == PRODUCED) & (pl.col("_first") < pl.col(c.TIME))).sort(c.EVENT)
    if t2.height:
        notices.append(_notice("AS-T2", f"Transformation events: {_count(t2.height, 'produced handling unit has', 'produced handling units have')} an event before its producing event (AS-T2).", t2[c.EVENT]))
    producing = roles.filter(pl.col(ROLE) == PRODUCED)[c.EVENT].unique().implode()
    t3 = timed.filter((pl.col(ROLE) == CONSUMED) & ~pl.col(c.EVENT).is_in(producing) & (pl.col("_last") > pl.col(c.TIME))).sort(c.EVENT)
    if t3.height:
        notices.append(_notice("AS-T3", f"Transformation events: {_count(t3.height, 'fully consumed handling unit occurs', 'fully consumed handling units occur')} in a later event (AS-T3).", t3[c.EVENT]))
    pairs = timed.select(c.EVENT, c.HU, c.TIME).unique()
    t4 = pairs.join(pairs, on=[c.HU, c.TIME], suffix="_other").filter(pl.col(c.EVENT) != pl.col(f"{c.EVENT}_other")).sort(c.EVENT)
    if t4.height:
        notices.append(_notice("AS-T4", f"Transformation events: {_count(t4[c.EVENT].n_unique(), 'transformation event shares', 'transformation events share')} a handling unit with another transformation event at the same timestamp (AS-T4).", t4[c.EVENT]))
    return notices


# --- resolution ----------------------------------------------------------------------------------------------


def resolve_transformations(
    option: TransformationRolesInput | None,
    candidates: pl.Series | None,
    e2hu: pl.DataFrame,
    handling_units: pl.Series,
    events: pl.Series,
    processing: pl.Series | None = None,
    e2o: pl.DataFrame | None = None,
    parents: pl.DataFrame | None = None,
    tables: dict[str, pl.DataFrame] | None = None,
    object_sets: tuple[pl.Series, pl.Series] | None = None,
) -> ResolvedTransformations:
    """T and the roles for the chosen option, after AS-T1, with the assumption reports.

    Args:
        option: The option; None = option 5 if candidates are given, otherwise T = ∅.
        candidates: The transformation-events input (None if not given).
        e2hu: hu-event relations with the columns event, hu, object_type, time and activity.
        handling_units: The handling units HU.
        events: All event ids of the log.
        processing: Processing operations for the first/last tie-break.
        e2o: e2o relations (event, hu, qualifier); needed for option 1.
        parents: Parent relations (child, parent); needed for option 3.
        tables: User tables by name; needed for option 2.
        object_sets: ($HU_{prod}$, $HU_{cons}$); needed for option 4.

    Returns:
        ResolvedTransformations.
    """
    notices: list[Notice] = []
    if option is None:
        if candidates is None:
            return ResolvedTransformations(pl.Series(c.EVENT, [], dtype=pl.String), empty_roles())
        option = RolesFromFirstLast()
    if option.option in DERIVES_TRANSFORMATION_EVENTS and candidates is not None:
        notices.append(Notice(code="transformation_events_ignored", message="Transformation events: not used, because the consumed and produced handling units determine them.", count=0, ids=[]))
        candidates = None
    first_last = first_last_events(e2hu, processing)
    if isinstance(option, RolesFromQualifiers):
        roles = roles_from_qualifiers(e2o, handling_units, option)
    elif isinstance(option, RolesFromTable):
        if tables is None or option.table not in tables:
            raise KeyError(f"Table '{option.table}' is not available.")
        missing = [col for col in (option.event_column, option.object_column, option.role_column) if col not in tables[option.table].columns]
        if missing:
            raise KeyError(f"Table '{option.table}' has no column(s) {', '.join(missing)}.")
        roles, found = roles_from_table(tables[option.table], option, events, handling_units)
        notices += found
    elif isinstance(option, RolesFromParents):
        roles = roles_from_parents(e2hu, parents, candidates, first_last)
    elif isinstance(option, RolesFromObjectSets):
        produced, consumed = object_sets
        roles = roles_from_object_sets(e2hu, candidates, first_last, produced, consumed, option.consumption)
    elif isinstance(option, RolesFromFirstLast):
        roles = roles_from_first_last(candidates, first_last)
    elif isinstance(option, RolesFromFrequency):
        roles = roles_from_frequency(e2hu, first_last, option.threshold)
    else:  # pragma: no cover - the config only allows the options above
        raise ValueError(f"Unknown option {option!r}")
    if candidates is None:
        candidates = roles[c.EVENT].unique()
    t, roles, found = apply_as_t1(candidates, roles)
    notices += found
    notices += check_assumptions(e2hu, roles)
    return ResolvedTransformations(t, roles, notices)


def object_set_ids(
    option: ObjectSetInput | None, objects: pl.DataFrame, attribute_values: pl.DataFrame | None, tables: dict[str, pl.DataFrame]
) -> pl.Series:
    """Resolve a set of objects for option 4.

    Args:
        option: Object attribute values or a table with an object column; None = no objects.
        objects: All objects of the log (column hu).
        attribute_values: For the attribute option: the last provided value per object (columns hu, value).
        tables: User tables by name.

    Returns:
        The object ids (only objects of the log).
    """
    if option is None:
        return pl.Series(c.HU, [], dtype=pl.String)
    if isinstance(option, ObjectAttributeValues):
        if attribute_values is None:
            raise KeyError(f"The log has no object attribute '{option.attribute}'.")
        return attribute_values.filter(pl.col("value").is_in(option.values))[c.HU]
    if option.table not in tables:
        raise KeyError(f"Table '{option.table}' is not available.")
    table = tables[option.table]
    if option.object_column not in table.columns:
        raise KeyError(f"Table '{option.table}' has no column(s) {option.object_column}.")
    ids = table[option.object_column].cast(pl.String)
    return ids.filter(ids.is_in(objects[c.HU].implode())).unique()
