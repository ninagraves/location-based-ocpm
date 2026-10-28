"""Requirements RQ1-RQ3 (`overview/Deriving Locations.md`, section "Setting"); each violation blocks."""

import polars as pl

from . import columns as c
from .messages import BlockingError


def check_rq1(relations: pl.DataFrame) -> list[BlockingError]:
    """RQ1: no handling unit has different provided locations at the same time.

    Args:
        relations: Hu-event relations with columns hu, time, event, uloc.

    Returns:
        list[BlockingError]: One error listing the conflicting events, or none.
    """
    located = relations.filter(pl.col(c.ULOC).is_not_null())
    conflicts = located.join(
        located.group_by(c.HU, c.TIME).agg(pl.col(c.ULOC).n_unique().alias("n")).filter(pl.col("n") > 1),
        on=[c.HU, c.TIME],
    )
    ids = conflicts[c.EVENT].unique().sort().to_list()
    return [BlockingError(code="RQ1", message="A handling unit has different provided locations at the same time.", ids=ids)] if ids else []


def check_rq2(events: pl.DataFrame) -> list[BlockingError]:
    """RQ2: every movement event has a provided target location (M ⊆ dom(uloc)).

    Args:
        events: Events with columns event, is_movement, uloc.

    Returns:
        list[BlockingError]: One error listing the movement events without target, or none.
    """
    ids = events.filter(pl.col(c.IS_MOVEMENT) & pl.col(c.ULOC).is_null())[c.EVENT].sort().to_list()
    return [BlockingError(code="RQ2", message="Movement events without a target location.", ids=ids)] if ids else []


def check_rq3(relations: pl.DataFrame) -> list[BlockingError]:
    """RQ3: no handling unit is involved in two movement events at the same time.

    Args:
        relations: Hu-event relations with columns hu, time, event, is_movement.

    Returns:
        list[BlockingError]: One error listing the conflicting events, or none.
    """
    moves = relations.filter(pl.col(c.IS_MOVEMENT))
    conflicts = moves.join(
        moves.group_by(c.HU, c.TIME).agg(pl.col(c.EVENT).n_unique().alias("n")).filter(pl.col("n") > 1),
        on=[c.HU, c.TIME],
    )
    ids = conflicts[c.EVENT].unique().sort().to_list()
    return [BlockingError(code="RQ3", message="A handling unit is in two movement events at the same time.", ids=ids)] if ids else []


def check_requirements(relations: pl.DataFrame, events: pl.DataFrame) -> list[BlockingError]:
    """Check RQ1, RQ2 and RQ3.

    Args:
        relations: Hu-event relations, as in `inputs.ResolvedInputs.relations`.
        events: All events, as in `inputs.ResolvedInputs.events`.

    Returns:
        list[BlockingError]: All violations (empty if the requirements hold).
    """
    return check_rq1(relations) + check_rq2(events) + check_rq3(relations)
