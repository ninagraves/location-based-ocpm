"""API route of the page "Directly-follows graph" (documented in `docs/pages/directly-follows-graph.md`).

The log's frames and the traces of a selection are cached (small LRU per process), keyed by the cache key of
the current derivation, so that moving a threshold slider only reruns the cheap filter steps.
"""

from collections import OrderedDict
from collections.abc import Callable
from typing import TypeVar

import polars as pl
from fastapi import APIRouter
from ocelescope_backend.app.dependencies import ApiOcel

from ocelescope_module_location_based_ocpm.configuration_routes import CurrentDerivation, State
from ocelescope_module_location_based_ocpm.dfg.graph import (
    DfgRequest,
    DirectlyFollowsGraph,
    LogFrames,
    directly_follows_graph,
    log_frames,
    resolve_selection,
    selected_traces,
)

router = APIRouter()

#: Number of cached entries per cache (frames of logs; traces of selections).
CACHE_SIZE = 4

T = TypeVar("T")
_frames: OrderedDict[str, LogFrames] = OrderedDict()
_traces: OrderedDict[tuple[str, tuple[str, ...]], pl.DataFrame] = OrderedDict()


def _cached(cache: OrderedDict, key, compute: Callable[[], T]) -> T:
    """Return `cache[key]`, computing and storing it first if missing; keep at most `CACHE_SIZE` entries.

    Args:
        cache: The cache (least recently used first).
        key: The key.
        compute: Computes the value if it is missing.

    Returns:
        The cached value.
    """
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    value = cache[key] = compute()
    while len(cache) > CACHE_SIZE:
        cache.popitem(last=False)
    return value


@router.post("/{ocel_id}/dfg", operation_id="getDirectlyFollowsGraph")
def get_directly_follows_graph(
    ocel_id: str, ocel: ApiOcel, derivation: CurrentDerivation, state: State, request: DfgRequest
) -> DirectlyFollowsGraph:
    """The directly-follows graph of the selected object types, projected on their selected activities and variant-filtered, with all arcs of the included traces (the page applies the arc settings)."""
    key = state.cache[ocel_id].key
    frames = _cached(_frames, key, lambda: log_frames(ocel, derivation))
    selection = resolve_selection(request, frames.objects, frames.handling_units.to_list())
    types = tuple(sorted({s.object_type for s in selection}))
    traces = _cached(_traces, (key, types), lambda: selected_traces(frames, types))
    # All arcs of the included traces: the page applies the arc settings itself (lib/dfgArcs.ts; Nina, 2026-11-15).
    all_arcs = [s.model_copy(update={"arc_threshold": 100.0, "arc_count": None}) for s in selection]
    return directly_follows_graph(
        frames, all_arcs, traces, request.activities, stay=False, excluded_categories=request.excluded_categories
    )
