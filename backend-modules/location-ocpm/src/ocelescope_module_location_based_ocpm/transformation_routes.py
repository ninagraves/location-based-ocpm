"""API routes of the transformations page (draft; documented in `docs/pages/transformations.md`).

Every route reads the transformation events of the current derivation (`transformations.events`), cached per
derivation key (small LRU per process), and applies the page filters given as query parameters.
"""

from collections import OrderedDict
from typing import Annotated

import polars as pl
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.configuration_routes import CurrentDerivation, State
from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation
from ocelescope_module_location_based_ocpm.overview.overview_charts import BarChart, End
from ocelescope_module_location_based_ocpm.transformations.charts import (
    DiversityPer,
    TransformationBy,
    TransformationChart,
    transformation_bar_chart,
)
from ocelescope_module_location_based_ocpm.transformations.events import (
    KindFilter,
    TransformationFilter,
    filter_events,
    transformation_events,
)
from ocelescope_module_location_based_ocpm.transformations.key_numbers import (
    Count,
    TransformationKeyNumbers,
    key_numbers,
    type_counts,
)
from ocelescope_module_location_based_ocpm.transformations.profile import TransformationTypeRow, type_profile
from ocelescope_module_location_based_ocpm.transformations.type_graph import (
    DEFAULT_COVERAGE,
    Quantities,
    TypeGraph,
    type_graph,
)

router = APIRouter()

#: Number of cached event tables (one per derivation key and location column).
CACHE_SIZE = 4
_tables: OrderedDict[tuple[str, str], pl.DataFrame] = OrderedDict()


def location_column(derivation: Derivation) -> str:
    """The location column of the charts: hat-hl in high-level mode, else loc (both at the selected level).

    In low mode the effective configuration has no high-level locations (`global_settings.effective_config`), so
    `has_high_level` tells the mode.
    """
    return derivation.hl if derivation.has_high_level else derivation.loc


def cached_events(key: str, derivation: Derivation) -> pl.DataFrame:
    """The transformation events of the derivation (`transformation_events`), computed once per derivation key.

    Args:
        key: Cache key of the derivation (`state.cache[ocel_id].key`).
        derivation: The derivation.

    Returns:
        pl.DataFrame: One row per transformation event, with locations.
    """
    location = location_column(derivation)
    entry = (key, location)
    if entry in _tables:
        _tables.move_to_end(entry)
        return _tables[entry]
    table = _tables[entry] = transformation_events(
        derivation.events, derivation.roles, derivation.handling_units, derivation.relations, location
    )
    while len(_tables) > CACHE_SIZE:
        _tables.popitem(last=False)
    return table


def get_transformation_filter(
    consumes: Annotated[list[str] | None, Query()] = None,
    produces: Annotated[list[str] | None, Query()] = None,
    kind: KindFilter = "all",
) -> TransformationFilter:
    """The page filters from query parameters (repeat a parameter for several values)."""
    return TransformationFilter(consumes=consumes or [], produces=produces or [], kind=kind)


Filter = Annotated[TransformationFilter, Depends(get_transformation_filter)]


def kept_events(ocel_id: str, derivation: Derivation, state: State, page_filter: TransformationFilter) -> pl.DataFrame:
    """The transformation events kept by the page filters."""
    return filter_events(cached_events(state.cache[ocel_id].key, derivation), page_filter)


class TransformationOverview(BaseModel):
    """Key numbers and the options of the page filters.

    Attributes:
        configured: False if the configuration has no transformation events (then everything is empty).
        key_numbers: The key numbers of the kept events.
        consumed_types: Object types consumed somewhere, with their events (all transformation events).
        produced_types: Object types produced somewhere, with their events.
    """

    configured: bool
    key_numbers: TransformationKeyNumbers
    consumed_types: list[Count]
    produced_types: list[Count]


@router.get("/{ocel_id}/transformations/overview", operation_id="getTransformationOverview")
def get_transformation_overview(
    ocel_id: str, derivation: CurrentDerivation, state: State, page_filter: Filter
) -> TransformationOverview:
    """Key numbers of the kept transformation events, and the filter options."""
    table = cached_events(state.cache[ocel_id].key, derivation)
    kept = filter_events(table, page_filter)
    with_events = derivation.relations[c.HU].n_unique()
    return TransformationOverview(
        configured=derivation.config.has_transformation_input,
        key_numbers=key_numbers(kept, derivation.roles, with_events),
        consumed_types=type_counts(table, "consumed_types"),
        produced_types=type_counts(table, "produced_types"),
    )


@router.get("/{ocel_id}/transformations/bar-chart", operation_id="getTransformationBarChart")
def get_transformation_bar_chart(
    ocel_id: str,
    derivation: CurrentDerivation,
    state: State,
    page_filter: Filter,
    chart: TransformationChart = "activities",
    by: TransformationBy = "none",
    per: DiversityPer = "activity",
    end: End = "top",
) -> BarChart:
    """One chart of the transformations page."""
    table = kept_events(ocel_id, derivation, state, page_filter)
    return transformation_bar_chart(table, chart=chart, by=by, per=per, end=end, level=derivation.level)


@router.get("/{ocel_id}/transformations/profile", operation_id="getTransformationProfile")
def get_transformation_profile(
    ocel_id: str, derivation: CurrentDerivation, state: State, page_filter: Filter
) -> list[TransformationTypeRow]:
    """The transformation profile: one row per transformation type (sorted, searched and paged in the browser)."""
    return type_profile(kept_events(ocel_id, derivation, state, page_filter))


@router.get("/{ocel_id}/transformations/type-graph", operation_id="getTransformationTypeGraph")
def get_transformation_type_graph(
    ocel_id: str,
    derivation: CurrentDerivation,
    state: State,
    page_filter: Filter,
    coverage: Annotated[float, Query(ge=0, le=1)] = DEFAULT_COVERAGE,
    quantities: Quantities = "exact",
) -> TypeGraph:
    """The transformation type graph of the recipes the frequency slider keeps."""
    return type_graph(kept_events(ocel_id, derivation, state, page_filter), coverage=coverage, quantities=quantities)
