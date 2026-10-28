"""API routes of the overview page; each reads the cached derivation (`current_derivation`)."""

from fastapi import APIRouter

from ocelescope_module_location_based_ocpm.configuration_routes import CurrentDerivation
from ocelescope_module_location_based_ocpm.overview.flag_badges import FlagCount, flag_counts
from ocelescope_module_location_based_ocpm.overview.key_numbers import KeyNumbers, key_numbers

router = APIRouter()


@router.get("/{ocel_id}/overview/key-numbers", operation_id="getKeyNumbers")
def get_key_numbers(derivation: CurrentDerivation) -> KeyNumbers:
    """Key numbers of the whole log at the selected level."""
    return key_numbers(derivation)


@router.get("/{ocel_id}/overview/flags", operation_id="getFlagCounts")
def get_flag_counts(derivation: CurrentDerivation) -> list[FlagCount]:
    """Flag counts of the whole log at the selected level (never filtered)."""
    return flag_counts(derivation)
