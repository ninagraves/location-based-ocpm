"""API route of the page "Directly-follows graph" (documented in `docs/pages/directly-follows-graph.md`).

The log's frames, the traces of a selection and the answers are cached (small LRU per process), keyed by the cache
key of the current derivation, so that moving a slider only reruns the cheap steps. Whenever a new derivation is
cached (a configuration applied, or recomputed after a filter change), the default graph is computed in the
background (`precompute_default_graph`), so the page opens without waiting (Nina, 2026-11-16).
"""

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import TypeVar

import polars as pl
from fastapi import APIRouter
from ocelescope import OCEL
from ocelescope_backend.app.dependencies import ApiOcel

from ocelescope_module_location_based_ocpm.configuration_routes import ON_DERIVED, CurrentDerivation, State
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation
from ocelescope_module_location_based_ocpm.dfg.graph import (
    DfgRequest,
    DirectlyFollowsGraph,
    LogFrames,
    directly_follows_graph,
    log_frames,
    resolve_selection,
    selected_traces,
)
from ocelescope_module_location_based_ocpm.state import CachedDerivation

router = APIRouter()
logger = logging.getLogger(__name__)

#: Number of cached entries per cache (frames of logs; traces of selections; answers).
CACHE_SIZE = 4

T = TypeVar("T")
_frames: OrderedDict[str, LogFrames] = OrderedDict()
_traces: OrderedDict[tuple[str, tuple[str, ...]], pl.DataFrame] = OrderedDict()
_graphs: OrderedDict[tuple[str, str], DirectlyFollowsGraph] = OrderedDict()
#: Guards the caches; `_computing` holds one lock per key being computed, so that a request waits for a running
#: precomputation of the same key instead of computing it a second time.
_guard = threading.Lock()
_computing: dict[tuple[int, Hashable], threading.Lock] = {}


def _cached(cache: OrderedDict, key: Hashable, compute: Callable[[], T]) -> T:
    """Return `cache[key]`, computing and storing it first if missing; keep at most `CACHE_SIZE` entries.

    Thread-safe: a key is computed at most once at a time (a second caller waits for the first).

    Args:
        cache: The cache (least recently used first).
        key: The key.
        compute: Computes the value if it is missing.

    Returns:
        The cached value.
    """
    with _guard:
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        lock = _computing.setdefault((id(cache), key), threading.Lock())
    with lock:
        with _guard:
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
        value = compute()
        with _guard:
            cache[key] = value
            while len(cache) > CACHE_SIZE:
                cache.popitem(last=False)
            _computing.pop((id(cache), key), None)
    return value


def request_key(request: DfgRequest) -> str:
    """The part of a request that changes the answer (the arc settings are applied in the browser), as text.

    Example: `DfgRequest()` and the page's default request (`toRequest(DEFAULT_STATE)`) give the same key.

    Args:
        request: The request.

    Returns:
        str: The key.
    """
    activities = {t: sorted(a) for t, a in sorted(request.activities.items())}
    variants = sorted((t.object_type, t.variant_threshold) for t in request.type_thresholds if t.variant_threshold is not None)
    types = sorted(request.object_types) if request.object_types is not None else None
    return repr((types, request.variant_threshold, variants, activities, sorted(request.excluded_categories)))


def _graph(key: str, ocel: OCEL, derivation: Derivation, request: DfgRequest) -> DirectlyFollowsGraph:
    """The answer to a request: the graph with all arcs of the included traces (cached).

    Args:
        key: Cache key of the derivation.
        ocel: The log.
        derivation: The derivation.
        request: The request.

    Returns:
        DirectlyFollowsGraph: The graph (the page applies the arc settings).
    """

    def compute() -> DirectlyFollowsGraph:
        frames = _cached(_frames, key, lambda: log_frames(ocel, derivation))
        selection = resolve_selection(request, frames.objects, frames.handling_units.to_list())
        types = tuple(sorted({s.object_type for s in selection}))
        traces = _cached(_traces, (key, types), lambda: selected_traces(frames, types))
        # All arcs of the included traces: the page applies the arc settings itself (lib/dfgArcs.ts; Nina, 2026-11-15).
        all_arcs = [s.model_copy(update={"arc_threshold": 100.0, "arc_count": None}) for s in selection]
        return directly_follows_graph(
            frames, all_arcs, traces, request.activities, stay=False, excluded_categories=request.excluded_categories
        )

    return _cached(_graphs, (key, request_key(request)), compute)


def precompute_default_graph(ocel_id: str, open_ocel: Callable[[], OCEL], cached: CachedDerivation) -> None:
    """Compute frames, traces and the default graph of a new derivation (runs in a background thread).

    Args:
        ocel_id: Id of the log.
        open_ocel: Opens the log (closed again here).
        cached: The new derivation and its cache key.
    """
    try:
        ocel = open_ocel()
        try:
            _graph(cached.key, ocel, cached.derivation, DfgRequest())
        finally:
            ocel.close()
    except Exception:  # A failure here must not break anything: the page then computes the graph on request.
        logger.exception("Precomputing the directly-follows graph of %s failed", ocel_id)


ON_DERIVED.append(precompute_default_graph)


@router.post("/{ocel_id}/dfg", operation_id="getDirectlyFollowsGraph")
def get_directly_follows_graph(
    ocel_id: str, ocel: ApiOcel, derivation: CurrentDerivation, state: State, request: DfgRequest
) -> DirectlyFollowsGraph:
    """The directly-follows graph of the selected object types, projected on their selected activities and variant-filtered, with all arcs of the included traces (the page applies the arc settings)."""
    return _graph(state.cache[ocel_id].key, ocel, derivation, request)
