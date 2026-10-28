"""API routes of the overview page; each reads the cached derivation (`current_derivation`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ocelescope_module_location_based_ocpm.configuration_routes import CurrentDerivation
from ocelescope_module_location_based_ocpm.overview.data_charts import DataCharts, data_charts
from ocelescope_module_location_based_ocpm.overview.filters import (
    FilterOptions,
    LocationRole,
    PageFilter,
    filter_options,
)
from ocelescope_module_location_based_ocpm.overview.flag_badges import FlagCount, flag_counts
from ocelescope_module_location_based_ocpm.overview.key_numbers import KeyNumbers, key_numbers

router = APIRouter()


def get_page_filter(
    activities: Annotated[list[str] | None, Query()] = None,
    exclude_activities: Annotated[list[str] | None, Query()] = None,
    locations: Annotated[list[str] | None, Query()] = None,
    exclude_locations: Annotated[list[str] | None, Query()] = None,
    location_role: LocationRole = "either",
    object_types: Annotated[list[str] | None, Query()] = None,
    exclude_object_types: Annotated[list[str] | None, Query()] = None,
) -> PageFilter:
    """The filter bar's state from query parameters (repeat a parameter for several values)."""
    return PageFilter(
        activities=activities or [],
        exclude_activities=exclude_activities or [],
        locations=locations or [],
        exclude_locations=exclude_locations or [],
        location_role=location_role,
        object_types=object_types or [],
        exclude_object_types=exclude_object_types or [],
    )


Filter = Annotated[PageFilter, Depends(get_page_filter)]


@router.get("/{ocel_id}/overview/filter-options", operation_id="getFilterOptions")
def get_filter_options(derivation: CurrentDerivation) -> FilterOptions:
    """Values of the filter bar with their counts over the whole log."""
    return filter_options(derivation)


@router.get("/{ocel_id}/overview/key-numbers", operation_id="getKeyNumbers")
def get_key_numbers(derivation: CurrentDerivation, page_filter: Filter) -> KeyNumbers:
    """Key numbers of the whole log at the selected level, plus the filtered values."""
    return key_numbers(derivation, page_filter)


@router.get("/{ocel_id}/overview/flags", operation_id="getFlagCounts")
def get_flag_counts(derivation: CurrentDerivation) -> list[FlagCount]:
    """Flag counts of the whole log at the selected level (never filtered)."""
    return flag_counts(derivation)


@router.get("/{ocel_id}/overview/data-charts", operation_id="getDataCharts")
def get_data_charts(derivation: CurrentDerivation, page_filter: Filter) -> DataCharts:
    """Events sunburst, E2HU chart and HU chart, counted over the kept part of the log."""
    return data_charts(derivation, page_filter)
